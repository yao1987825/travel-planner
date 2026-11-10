#!/usr/bin/env python3
"""端到端冒烟测试：验证四条数据源 + 跨方式编排是否正常。

    python3 tests/test_journey.py          # 全部(需要网络)
    python3 tests/test_journey.py --offline # 只跑不联网的解析逻辑
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

PASSED = 0
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ✓ {name}")
    else:
        FAILED += 1
        print(f"  ✗ {name}  {detail}")


def run(args, timeout=180):
    proc = subprocess.run(
        [sys.executable] + args, capture_output=True, text=True, timeout=timeout,
        cwd=str(SCRIPTS),
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_offline() -> None:
    print("[离线] 时间与映射逻辑")
    import transit

    base = transit.parse_date("2026-11-08")
    check("parse_date", base.strftime("%Y-%m-%d") == "2026-11-08", str(base))
    check("parse_date 明天", transit.parse_date("明天") > transit.parse_date("今天"))

    depart = transit.parse_moment("12:58", base)
    arrive = transit.parse_moment("07:02", depart)
    check("跨天到达算成次日", arrive.day == 9, str(arrive))
    same = transit.parse_moment("13:20", depart)
    check("当天到达不跨天", same.day == 8, str(same))

    check("station_core 去站", transit.station_core("虹桥火车站") == "虹桥")
    check("station_core 去火车", transit.station_core("长沙火车南站") == "长沙南")
    check("末班跨日折算", transit.fmt_service_minutes(1476) == "次日00:36")
    check("服务窗口分钟数", transit.metro_service_window([], "saturday") == (None, None))

    print("[离线] 行程规划多城市景点库")
    import generate_plan

    md = generate_plan.load_attractions_from_md()
    check("景点库含郴州", "郴州" in md and len(md["郴州"]) >= 5)
    check("景点库含长沙", "长沙" in md and len(md["长沙"]) >= 5)
    check("景点库含上海", "上海" in md and len(md["上海"]) >= 5)
    check("景点库含清远", "清远" in md and len(md["清远"]) >= 10)
    check("清远含古龙峡", any(a["name"] == "古龙峡" for a in md["清远"]))
    check("清远含桃花湖", any(a["name"] == "桃花湖" for a in md["清远"]))
    check("清远含免费景点", any(a["ticket_price"] == 0 for a in md["清远"]))
    check("景点库含丹东", "丹东" in md and len(md["丹东"]) >= 5)
    check("丹东含断桥", any(a["name"] == "鸭绿江断桥" for a in md["丹东"]))
    check("门票解析免费", generate_plan._parse_ticket("免费（小火车20)") == 0.0)
    check("门票解析付费", generate_plan._parse_ticket("40（学生20）") == 40.0)
    check("门票待核实=未知", generate_plan._parse_ticket("待核实") is None)
    check("时长解析", generate_plan._parse_duration("3-4h") == 3.5)
    check("时长半天", generate_plan._parse_duration("半天-1天") == 5.0)

    print("[离线] 城市注册表与别名")
    registry = generate_plan.registry_cities()
    check("注册表含丹东", "丹东" in registry)
    check("注册表含来源", bool(registry.get("丹东", {}).get("attractions_source")))
    check("注册表含核实年份", bool(registry.get("丹东", {}).get("verified")))
    check("鸭绿江别名->丹东",
          generate_plan.resolve_city_key("鸭绿江") == "丹东")
    check("地铁覆盖可查", generate_plan.city_has_metro("上海") is True)
    check("非地铁城市", generate_plan.city_has_metro("郴州") is False)
    check("类别匹配历史", generate_plan.category_is_matched("历史文化"))
    check("类别匹配自然细分", generate_plan.category_is_matched("自然/湖泊"))

    print("[离线] 数据规范校验器")
    import contextlib
    import io as _io

    import validate_data

    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = validate_data.main([])
    check("validate_data 无 error", rc == 0, buf.getvalue()[-400:])

    print("[离线] 景点实景图")
    import json as _json

    idx_path = ROOT / "references" / "image_index.json"
    if idx_path.exists():
        idx = _json.loads(idx_path.read_text(encoding="utf-8"))
        cities = idx.get("cities") or {}
        total = sum(len(v) for v in cities.values())
        check("图片索引有数据", total > 0, str(total))
        sample = next(iter(cities.values()), {})
        one = next(iter(sample.values()), None)
        if one:
            check("图片条目含直链", str(one.get("url", "")).startswith("http"))
            check("图片条目含原始页面", str(one.get("page", "")).startswith("http"))
            check("图片条目含来源站点", bool(one.get("source")))
        # 景点表里的图片列要能解析出来
        md = generate_plan.load_attractions_from_md()
        with_img = [a for city, items in md.items() if city != "_food_tips"
                    for a in items if a.get("image")]
        check("景点表带图片列", len(with_img) > 0, str(len(with_img)))
    else:
        print("   - 跳过：还没有 image_index.json（跑 fetch_images.py index）")

    check("图片列解析", generate_plan._parse_image("![外滩](https://x/1.jpg)") == "https://x/1.jpg")
    check("图片列解析裸链", generate_plan._parse_image("https://x/2.jpg") == "https://x/2.jpg")
    check("图片列解析空", generate_plan._parse_image("") == "")


def test_metro() -> None:
    print("[在线] 地铁")
    # 用「明天的 10:00」作为查询时刻，避免深夜（末班车后）mode=now 查不到方案
    from datetime import datetime, timedelta

    future = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d1000")
    code, out, err = run([
        "metro_query.py", "plan", "上海", "徐家汇", "陆家嘴",
        "--mode", "depart", "--datetime", future,
    ])
    check("地铁换乘方案", code == 0 and "号线" in out, err[:120])
    check("地铁含票价", "元" in out)

    code, out, err = run(["metro_query.py", "station", "上海", "徐家汇"])
    check("地铁首末班车", code == 0 and "途经线路" in out and "05:" in out, out[:120])

    code, out, err = run(["metro_query.py", "line", "北京", "机场线"])
    check("地铁线路途经站", code == 0 and "3号航站楼" in out, out[:120])

    code, out, err = run(["metro_query.py", "cities"])
    check("城市列表", code == 0 and out.count("\n") >= 50)


def test_weather() -> None:
    print("[在线] 天气")
    code, out, err = run(["weather_query.py", "live", "郴州"])
    check("实况天气", code == 0 and "实况天气" in out, err[:120])
    check("生活指数", "生活指数" in out)

    code, out, err = run(["weather_query.py", "forecast", "郴州"])
    check("7 天预报", code == 0 and "预报" in out and "℃" in out, err[:120])

    code, out, err = run(["weather_query.py", "resolve", "郴州"])
    check("城市码解析", code == 0 and "101250501" in out, out[:80])


def test_train() -> None:
    print("[在线] 火车票")
    import train_store

    payload = train_store.train_query(
        {"date": "明天", "from_station": "郴州", "to_station": "长沙"}
    )
    check("12306 有车次", len(payload.get("has_ticket_trains") or []) > 0,
          str(payload.get("error", "")))
    if payload.get("has_ticket_trains"):
        train = payload["has_ticket_trains"][0]
        check("车次有时刻", bool(train.get("start_time") and train.get("arrive_time")))


def test_journey() -> None:
    print("[在线] 跨方式编排")
    # 用「明天」避免深夜 mode=now 查不到地铁；跨城 journey 已优化为常用城市优先，
    # 不会再花几分钟构建全网车站索引。
    code, out, err = run(
        ["transit.py", "journey", "--city", "上海", "--from", "人民广场",
         "--to", "陆家嘴", "--date", "明天"]
    )
    check("市内 journey", code == 0 and "地铁" in out, err[:150])

    code, out, err = run(
        ["transit.py", "journey", "--from", "郴州西", "--to", "陆家嘴",
         "--date", "明天", "--weather"]
    )
    check("跨城 journey", code == 0 and "火车" in out, err[:150])
    check("跨城接上地铁", "地铁" in out, out[:200])
    check("附带天气", "目的地天气" in out, out[-200:])

    code, out, err = run(
        ["transit.py", "journey", "--from", "郴州西", "--to", "陆家嘴",
         "--date", "明天", "--arrive-by", "18:00"]
    )
    check("arrive-by 反推", code == 0 and ("到" in out), err[:150])


def main() -> int:
    global PASSED, FAILED
    offline = "--offline" in sys.argv
    test_offline()
    if not offline:
        for fn in (test_metro, test_weather, test_train, test_journey):
            try:
                fn()
            except Exception as exc:
                print(f"  ! {fn.__name__} 异常：{exc}")
                FAILED += 1
    print(f"\n通过 {PASSED} 项，失败 {FAILED} 项")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
