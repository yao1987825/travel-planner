#!/usr/bin/env python3
"""weather_query.py —— 中国天气网（weather.com.cn）天气查询（纯标准库，零第三方依赖）。

    python3 weather_query.py live 北京              # 实时天气 + 空气质量 + 生活指数
    python3 weather_query.py forecast 北京          # 7 天预报 + 逐小时 + 24 小时实况
    python3 weather_query.py alerts 北京            # 气象预警
    python3 weather_query.py resolve 北京           # 查城市编码
    python3 weather_query.py all 北京 --json       # 全部

逆向结论（2026-11 实测）：

  weather.com.cn 没有开放 API 文档，但前端在服务端渲染的页面上挂了一组
  JSONP 数据接口（d1.weather.com.cn），内容与页面一致：

    GET http://d1.weather.com.cn/weather_index/{城市码}.html
        var cityDZ  = {...}   今日天气（最高/最低温、白天夜间天气、风向风力）
        var alarmDZ = {...}   气象预警列表
        var dataSK  = {...}   实况（温度/湿度/气压/风/降水/AQI）
        var dataZS  = {...}   生活指数（穿衣/旅游/运动/紫外线/感冒…）

    GET http://d1.weather.com.cn/dingzhi/{城市码}.html
        var cityDZ{城市码}  = {...}   同上（另一份）
        var alarmDZ{城市码} = {...}

    GET http://d1.weather.com.cn/aqi/{城市码}.html
        setAirData({...})           空气质量逐小时

    GET http://www.weather.com.cn/weather/{城市码}.shtml
        服务端渲染的 7 天预报页，内含
        var hour3data = {...}       3 小时逐小时预报
        var observe24h_data = {...} 24 小时实况

  城市码（AREAID）取自 http://j.i8tq.com/weather2020/search/city.js，
  已离线整理进 references/weather_cities.json（3137 个城市/区县）。

  注意：d1.weather.com.cn 对 Referer 有要求，带上 http://www.weather.com.cn/ 更稳。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(HERE), "references")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

D1 = "http://d1.weather.com.cn"
WW = "http://www.weather.com.cn"
REFERER = "http://www.weather.com.cn/"

CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")),
    "weather_query",
)


def die(msg: str, code: int = 1) -> None:
    print(f"[weather] 错误: {msg}", file=sys.stderr)
    sys.exit(code)


# ═══════════════════════════════════════════════════════════════ HTTP


def http_get(url: str, referer: str = REFERER, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "close",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {url}") from exc
    except Exception as exc:
        raise RuntimeError(f"请求失败: {url} ({exc})") from exc
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def http_get_cached(url: str, name: str, ttl: int = 1800,
                    referer: str = REFERER) -> str:
    """带磁盘缓存的 GET（天气数据变化快，默认缓存 30 分钟）。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path):
        import time

        if time.time() - os.path.getmtime(path) < ttl:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
    body = http_get(url, referer=referer)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    except OSError:
        pass
    return body


def extract_jsonp(text: str, var: str) -> Optional[Dict[str, Any]]:
    """从 `var xxx = {...};` 里抠出 JSON 对象。"""
    match = re.search(r"var\s+" + re.escape(var) + r"\s*=\s*(\{.*?\})\s*;",
                      text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def extract_jsonp_array(text: str, var: str) -> Optional[List[Any]]:
    match = re.search(r"var\s+" + re.escape(var) + r"\s*=\s*(\[.*?\])\s*;",
                      text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def extract_call(text: str, func: str) -> Optional[Dict[str, Any]]:
    """从 `setAirData({...})` 里抠出 JSON 对象。"""
    match = re.search(re.escape(func) + r"\s*\(\s*(\{.*?\})\s*\)", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════════ 城市解析


def load_city_map() -> Dict[str, Any]:
    path = os.path.join(REFS, "weather_cities.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"cities": {}, "prefecture": {}}


def resolve_area(city: str) -> Tuple[str, str]:
    """城市名 -> (标准名, AREAID)。找不到时走在线搜索兜底。"""
    data = load_city_map()
    name = (city or "").strip().replace("市", "") if city else ""
    if not name:
        die("城市不能为空")

    if name in data.get("prefecture", {}):
        return name, data["prefecture"][name]["areaid"]
    if name in data.get("cities", {}):
        return name, data["cities"][name]

    # 在线搜索兜底
    url = f"{WW.replace('www.', 'toy1.')}/search?cityname={urllib.parse.quote(city)}"
    try:
        text = http_get(url, referer=REFERER)
    except Exception:
        text = ""
    match = re.search(r"\(\[(.*)\]\)", text, re.S)
    if match:
        try:
            items = json.loads("[" + match.group(1) + "]")
        except ValueError:
            items = []
        for item in items:
            ref = item.get("ref", "")
            parts = ref.split("~")
            if len(parts) >= 3:
                return parts[2], parts[0]
    die(f"没找到城市「{city}」")


# ═══════════════════════════════════════════════════════════════ 数据获取


def fetch_live(areaid: str) -> Dict[str, Any]:
    """实时天气 + 生活指数 + 预警。"""
    text = http_get_cached(f"{D1}/weather_index/{areaid}.html", f"live_{areaid}.js")
    city = extract_jsonp(text, "cityDZ") or {}
    alarm = extract_jsonp(text, "alarmDZ") or {}
    sk = extract_jsonp(text, "dataSK") or {}
    zs = extract_jsonp(text, "dataZS") or {}

    info = dict(city.get("weatherinfo", {}))
    # weather_index 里的温度有时是占位符 999，用 dingzhi 的真实值补齐
    if not info.get("temp") or str(info.get("temp")).strip() in ("999", "0"):
        dz = fetch_dingzhi(areaid)
        if dz:
            info.update({k: v for k, v in dz.items() if v})
    return {
        "city": info,
        "live": sk,
        "index": zs.get("zs", {}),
        "alarms": parse_alarms(alarm.get("w") or []),
    }


def fetch_dingzhi(areaid: str) -> Dict[str, Any]:
    """今日/明日白天夜间天气（文本最可靠的一份）。"""
    text = http_get_cached(f"{D1}/dingzhi/{areaid}.html", f"dz_{areaid}.js")
    data = extract_jsonp(text, f"cityDZ{areaid}") or {}
    info = data.get("weatherinfo", {})
    return {
        "cityname": info.get("cityname"),
        "fctime": info.get("fctime"),
        "temp": info.get("temp"),
        "tempn": info.get("tempn"),
        "weather": info.get("weather"),
        "weathercode": info.get("weathercode"),
        "weathercoden": info.get("weathercoden"),
        "wd": info.get("wd"),
        "ws": info.get("ws"),
    }


def parse_alarms(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alarms = []
    for item in items:
        if not isinstance(item, dict):
            continue
        alarms.append({
            "area": " ".join(x for x in (item.get("w1"), item.get("w2"), item.get("w3")) if x),
            "type": item.get("w5"),
            "level": item.get("w7"),
            "issued": item.get("w8"),
            "content": item.get("w9"),
            "title": item.get("w13"),
            "expire": item.get("w15"),
            "file": item.get("w11"),
        })
    return alarms


def fetch_aqi(areaid: str) -> Dict[str, Any]:
    text = http_get_cached(f"{D1}/aqi/{areaid}.html", f"aqi_{areaid}.js")
    data = extract_call(text, "setAirData") or {}
    return data


def fetch_forecast(areaid: str) -> Dict[str, Any]:
    """7 天预报 + 逐小时 + 24 小时实况（服务端渲染页面内嵌）。"""
    page = http_get_cached(f"{WW}/weather/{areaid}.shtml", f"fc_{areaid}.html", ttl=3600)
    days = parse_seven_days(page)
    # 今天那一格只给最低温，最高温从 dingzhi 补
    if days:
        try:
            dz = fetch_dingzhi(areaid)
        except Exception:
            dz = {}
        if dz.get("temp"):
            days[0]["high"] = re.sub(r"[^\-\d]", "", dz["temp"]) or days[0]["high"]
        if dz.get("tempn"):
            days[0]["low"] = re.sub(r"[^\-\d]", "", dz["tempn"]) or days[0]["low"]
    hourly = parse_hourly(page)
    observe = parse_observe(page)
    return {"days": days, "hourly": hourly, "observe": observe}


def _strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def parse_seven_days(page: str) -> List[Dict[str, Any]]:
    """解析 7 天预报块。"""
    match = re.search(r'<ul class="t clearfix">(.*?)</ul>', page, re.S)
    if not match:
        return []
    days: List[Dict[str, Any]] = []
    for item in re.findall(r'<li class="sky[^"]*">(.*?)</li>', match.group(1), re.S):
        title = re.search(r"<h1>(.*?)</h1>", item, re.S)
        wea = re.search(r'<p[^>]*class="wea"[^>]*>(.*?)</p>', item, re.S)
        tem = re.search(r'<p class="tem">(.*?)</p>', item, re.S)
        win = re.search(r'<p class="win">(.*?)</p>', item, re.S)
        highs = re.findall(r"<span>(\d+)℃</span>", tem.group(1)) if tem else []
        lows = re.findall(r"<i>(-?\d+)℃</i>", tem.group(1)) if tem else []
        winds = re.findall(r'<span title="([^"]+)"', win.group(1)) if win else []
        # 风力写在 <i> 里，内容可能是 "<3级"，正则要容许 '<' 出现在开头
        forces = re.findall(r"<i>(.*?)</i>", win.group(1), re.S) if win else []
        days.append({
            "date": _strip_tags(title.group(1)) if title else "",
            "weather": _strip_tags(wea.group(1)) if wea else "",
            "high": highs[0] if highs else (lows[0] if lows else ""),
            "low": lows[0] if lows else "",
            "wind": winds[0] if winds else "",
            "wind_force": _strip_tags(forces[-1]) if forces else "",
        })
    return days


def parse_hourly(page: str) -> Dict[str, List[List[str]]]:
    """3 小时逐小时预报：{'1d': [...], '23d': [[...], ...]}。"""
    match = re.search(r"var\s+hour3data\s*=\s*(\{.*?\})\s*;", page, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except ValueError:
        return {}


def parse_observe(page: str) -> Dict[str, Any]:
    """24 小时实况。"""
    match = re.search(r"var\s+observe24h_data\s*=\s*(\{.*?\})\s*;", page, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return {}
    od = data.get("od", {})
    rows = []
    for item in od.get("od2", []):
        rows.append({
            "time": f"{item.get('od21')}:00",
            "temp": item.get("od22"),
            "wind": item.get("od24"),
            "force": item.get("od25"),
            "rain": item.get("od26"),
            "humidity": item.get("od27"),
        })
    return {"updated": od.get("od0"), "city": od.get("od1"), "rows": rows}


def parse_hourly_rows(hourly: Dict[str, Any]) -> List[Dict[str, str]]:
    """把 hour3data 摊平成一行一条。"""
    rows: List[Dict[str, str]] = []
    day_one = hourly.get("1d") or []
    for entry in day_one:
        rows.append(_hourly_row(entry))
    for group in (hourly.get("23d") or []):
        for entry in group:
            rows.append(_hourly_row(entry))
    return rows


def _hourly_row(entry: str) -> Dict[str, str]:
    parts = entry.split(",")
    return {
        "time": parts[0] if len(parts) > 0 else "",
        "weather": parts[2] if len(parts) > 2 else "",
        "temp": parts[3] if len(parts) > 3 else "",
        "wind": parts[4] if len(parts) > 4 else "",
        "force": parts[5] if len(parts) > 5 else "",
        "rain": parts[6] if len(parts) > 6 else "",
    }


# ═══════════════════════════════════════════════════════════════ 渲染


def render_live(data: Dict[str, Any], city: str) -> str:
    live = data.get("live", {})
    info = data.get("city", {})
    index = data.get("index", {})
    lines = [f"{city} · 实况天气"]

    if live:
        lines.append(
            f"  {live.get('weather','')}  {live.get('temp','')}℃"
            f"  {live.get('WD','')} {live.get('WS','')}"
            f"  湿度 {live.get('SD','')}  气压 {live.get('qy','')}hPa"
            f"  能见度 {live.get('njd','')}"
        )
        lines.append(
            f"  观测时间 {live.get('date','')} {live.get('time','')}"
            f"   AQI {live.get('aqi','')}（PM2.5 {live.get('aqi_pm25','')}）"
            f"   降水 {live.get('rain24h','')}mm"
        )
    if info:
        lines.append(
            f"  今日 {info.get('weather','')}  {info.get('temp','')}/{info.get('tempn','')}"
            f"  {info.get('wd','')} {info.get('ws','')}"
        )

    if index:
        picks = [("ct", "穿衣"), ("tr", "旅游"), ("yd", "运动"), ("uv", "紫外线"),
                 ("gm", "感冒"), ("xc", "洗车"), ("cl", "晨练"), ("co", "舒适度")]
        parts = []
        for key, label in picks:
            hint = index.get(f"{key}_hint")
            if hint:
                parts.append(f"{label}{hint}")
        if parts:
            lines.append("  生活指数：" + " · ".join(parts))
        detail = index.get("ct_des_s") or index.get("tr_des_s")
        if detail:
            lines.append(f"  提示：{detail}")

    alarms = data.get("alarms") or []
    if alarms:
        lines.append("  ⚠️ 气象预警：")
        for alarm in alarms:
            lines.append(f"     [{alarm.get('level','')}{alarm.get('type','')}] {alarm.get('title','')}"
                         f"（{alarm.get('issued','')}）")
            if alarm.get("content"):
                lines.append(f"       {alarm['content'][:120]}")
    else:
        lines.append("  无气象预警")
    return "\n".join(lines)


def render_forecast(data: Dict[str, Any], city: str) -> str:
    lines = [f"{city} · 预报"]
    for day in data.get("days", []):
        lines.append(
            f"  {day['date']:<12} {day['weather']:<10}"
            f" {day['high']}/{day['low']}℃   {day['wind']} {day['wind_force']}"
        )
    hourly = data.get("hourly") or {}
    rows = parse_hourly_rows(hourly)
    if rows:
        lines.append("  逐小时（未来 24~48 小时，每 3 小时）：")
        for row in rows[:16]:
            lines.append(
                f"    {row['time']:<10} {row['weather']:<8} {row['temp']:<6}"
                f" {row['wind']} {row['force']}"
            )
    observe = data.get("observe") or {}
    rows = observe.get("rows") or []
    if rows:
        lines.append("  近 12 小时实况：")
        for row in rows[:12]:
            lines.append(
                f"    {row['time']:<8} {row['temp']}℃  {row['wind']} {row['force']}级"
                f"  湿度 {row['humidity']}%  降水 {row['rain']}mm"
            )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════ 命令


def cmd_live(args: argparse.Namespace) -> int:
    name, areaid = resolve_area(args.city)
    data = fetch_live(areaid)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_live(data, name))
    return 0


def cmd_forecast(args: argparse.Namespace) -> int:
    name, areaid = resolve_area(args.city)
    data = fetch_forecast(areaid)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_forecast(data, name))
    return 0


def cmd_alerts(args: argparse.Namespace) -> int:
    name, areaid = resolve_area(args.city)
    data = fetch_live(areaid)
    alarms = data.get("alarms") or []
    if args.json:
        print(json.dumps(alarms, ensure_ascii=False, indent=2))
        return 0
    if not alarms:
        print(f"{name}：暂无气象预警")
        return 0
    print(f"{name}：{len(alarms)} 条气象预警")
    for alarm in alarms:
        print(f"  [{alarm.get('level','')}{alarm.get('type','')}] {alarm.get('title','')}")
        print(f"    发布 {alarm.get('issued','')}  区域 {alarm.get('area','')}")
        if alarm.get("content"):
            print(f"    {alarm['content']}")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    name, areaid = resolve_area(args.city)
    print(f"{name}\t{areaid}")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    name, areaid = resolve_area(args.city)
    payload: Dict[str, Any] = {"city": name, "areaid": areaid}
    try:
        payload["live"] = fetch_live(areaid)
    except Exception as exc:
        payload["live_error"] = str(exc)
    try:
        payload["forecast"] = fetch_forecast(areaid)
    except Exception as exc:
        payload["forecast_error"] = str(exc)
    try:
        payload["aqi"] = fetch_aqi(areaid)
    except Exception as exc:
        payload["aqi_error"] = str(exc)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    live = payload.get("live")
    if live:
        print(render_live(live, name))
        print()
    forecast = payload.get("forecast")
    if forecast:
        print(render_forecast(forecast, name))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weather_query.py",
        description="中国天气网（weather.com.cn）天气查询",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("live", help="实况天气 + 空气质量 + 生活指数 + 预警")
    p.add_argument("city")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_live)

    p = sub.add_parser("forecast", help="7 天预报 + 逐小时 + 24 小时实况")
    p.add_argument("city")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_forecast)

    p = sub.add_parser("alerts", help="气象预警")
    p.add_argument("city")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_alerts)

    p = sub.add_parser("resolve", help="查城市编码")
    p.add_argument("city")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("all", help="实况 + 预报全给")
    p.add_argument("city")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_all)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        die(str(exc), 3)
    except Exception as exc:  # pragma: no cover
        die(str(exc), 3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
