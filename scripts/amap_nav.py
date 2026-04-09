#!/usr/bin/env python3
"""
travel-planner/scripts/amap_nav.py
====================================
基于高德地图 Web 服务 API 的导航路线查询工具。

功能：
  1. 地理编码（地点名 → 经纬度）
  2. 驾车路线规划
  3. 公交路线规划（城内）
  4. 步行路线规划
  5. 景点间最优顺序推荐（TSP 简化版）
  6. 行程导航汇总（多景点链式规划）

依赖：
  pip install requests python-dotenv

.env 配置：
  AMAP_KEY=你的高德Web服务API密钥
  （免费注册：https://lbs.amap.com/ ，个人开发者每日5000次配额）
"""

import argparse
import json
import math
import os
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from typing import Optional
from itertools import permutations

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("⚠️  请先安装 requests：pip install requests")
    sys.exit(1)


# ─── 高德 API 配置 ────────────────────────────────────────────────────────────
AMAP_BASE = "https://restapi.amap.com/v3"
AMAP_KEY  = os.getenv("AMAP_KEY", "").strip()

# 驾车策略
DRIVING_STRATEGY = {
    "0": "速度优先（推荐）",
    "1": "费用优先（经济路线）",
    "2": "距离优先（短程路线）",
    "3": "不走快速路",
    "4": "躲避拥堵",
    "5": "不走高速",
    "6": "躲避拥堵且不走高速",
    "7": "普通道路优先",
    "8": "途经多终点时综合最优",
    "9": "夜间驾驶",
    "10": "极端天气路线",
    "11": "用户最优备选",
}

# 公交策略
TRANSIT_STRATEGY = {
    "0": "最快捷模式（默认）",
    "1": "最经济模式（最少换乘）",
    "2": "最少换乘",
    "3": "最少步行",
    "4": "最舒适模式",
    "5": "不乘地铁",
}


# ─── 数据模型 ─────────────────────────────────────────────────────────────────

@dataclass
class Location:
    name: str
    address: Optional[str] = None
    lat: Optional[float] = None   # 纬度
    lng: Optional[float] = None   # 经度

    @property
    def coord_str(self) -> str:
        if self.lat is None or self.lng is None:
            raise ValueError(f"地点 '{self.name}' 缺少坐标，请先调用地理编码")
        return f"{self.lng},{self.lat}"

    def __repr__(self):
        return f"Location({self.name}, {self.lat},{self.lng})"


@dataclass
class RouteSegment:
    from_loc: Location
    to_loc: Location
    mode: str  # 'driving' | 'transit' | 'walking'
    distance_km: float
    duration_min: int
    cost_yuan: float = 0.0
    route_tips: str = ""
    path_description: str = ""

    def format_summary(self) -> str:
        cost_str = f"（约 ¥{self.cost_yuan:.0f}）" if self.cost_yuan > 0 else ""
        tips_str = f"\n   💡 {self.route_tips}" if self.route_tips else ""
        return (
            f"  {self.from_loc.name} → {self.to_loc.name}\n"
            f"  方式: {self.mode_zh} | 距离: {self.distance_km:.1f}km | "
            f"耗时: {self._fmt_dur(self.duration_min)}{cost_str}{tips_str}\n"
            f"   路线: {self.path_description}"
        )

    @property
    def mode_zh(self) -> str:
        return {"driving": "🚗 驾车", "transit": "🚇 公交/地铁", "walking": "🚶 步行"}.get(self.mode, self.mode)

    @staticmethod
    def _fmt_dur(minutes: int) -> str:
        if minutes < 60:
            return f"{minutes}分钟"
        h, m = divmod(minutes, 60)
        return f"{h}小时{m}分钟" if m else f"{h}小时"


# ─── 高德 API 核心 ────────────────────────────────────────────────────────────

class AmapClient:
    """高德地图 API 客户端（地理编码 + 三种路线规划）。"""

    def __init__(self, key: str = ""):
        self.key = key or AMAP_KEY
        if not self.key:
            print("⚠️  未设置 AMAP_KEY 环境变量。")
            print("   请在 .env 文件中配置：AMAP_KEY=你的密钥")
            print("   免费注册：https://lbs.amap.com/  → 控制台 → 应用管理 → 添加Key")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "TravelPlanner/1.0"})

    def _get(self, endpoint: str, params: dict) -> dict:
        params["key"] = self.key
        url = f"{AMAP_BASE}/{endpoint}"
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            infocode = data.get("infocode", "?")
            info = data.get("info", "未知错误")
            print(f"❌ API 错误 [{infocode}]: {info}")
            return {}
        return data

    # ── 地理编码 ────────────────────────────────────────────────────────────────
    def geocode(self, address: str, city: str = "") -> Optional[Location]:
        """
        将地点名称转为经纬度坐标。
        :param address: 地点名称，如 '上海外滩' 或完整地址
        :param city: 城市名（辅助提高准确性），如 '上海'
        :return: Location 对象（含 lat/lng）
        """
        params = {"address": address}
        if city:
            params["city"] = city
        data = self._get("geocode/geo", params)
        if not data or data.get("count", "0") == "0":
            return None
        geom = data["geocodes"][0]
        return Location(
            name=address,
            address=geom.get("formatted_address", address),
            lng=float(geom["location"].split(",")[0]),
            lat=float(geom["location"].split(",")[1]),
        )

    # ── 驾车路线 ───────────────────────────────────────────────────────────────
    def driving(
        self,
        origin: Location,
        destination: Location,
        strategy: str = "0",
        extensions: str = "base",
    ) -> Optional[RouteSegment]:
        """
        驾车路线规划。
        strategy: 0=速度优先, 1=费用优先, 2=距离优先
        """
        params = {
            "origin":     origin.coord_str,
            "destination": destination.coord_str,
            "strategy":   strategy,
            "extensions": extensions,
        }
        data = self._get("direction/driving", params)
        if not data:
            return None
        paths = data.get("route", {}).get("paths", [])
        if not paths:
            return None
        path = paths[0]
        steps_text = self._parse_driving_steps(path.get("steps", []))
        distance_km = float(path.get("distance", 0)) / 1000
        duration_sec = float(path.get("duration", path.get("time", 0)))
        duration_min = int(duration_sec / 60)
        tolls = float(data.get("route", {}).get("cost", {}).get("toll", 0))
        return RouteSegment(
            from_loc=origin,
            to_loc=destination,
            mode="driving",
            distance_km=distance_km,
            duration_min=duration_min,
            cost_yuan=tolls,
            route_tips=DRIVING_STRATEGY.get(strategy, ""),
            path_description=steps_text,
        )

    # ── 公交路线 ────────────────────────────────────────────────────────────────
    def transit(
        self,
        origin: Location,
        destination: Location,
        city: str,
        strategy: str = "0",
        nightflag: str = "0",
    ) -> Optional[RouteSegment]:
        """
        公交路线规划（城内）。
        city: 起点所在城市
        strategy: 0=最快捷, 1=最经济, 2=最少换乘, 3=最少步行, 5=不乘地铁
        """
        params = {
            "origin":      origin.coord_str,
            "destination": destination.coord_str,
            "city":        city,
            "strategy":    strategy,
            "nightflag":   nightflag,
            "extensions":  "base",
        }
        data = self._get("direction/transit/integrated", params)
        if not data:
            return None
        # 正确 key：transits（在 route 节点下）
        route_obj = data.get("route", {})
        transits = route_obj.get("transits", []) if route_obj else []
        if not transits:
            return None
        best = transits[0]
        # 取第一条方案的概览
        distance_km = float(best.get("distance", 0)) / 1000
        duration_min = int(float(best.get("duration", 0)) / 60)
        cost_yuan = float(best.get("cost", 0))
        segments = best.get("segments", [])
        segments_text = self._parse_transit_steps(segments)
        return RouteSegment(
            from_loc=origin,
            to_loc=destination,
            mode="transit",
            distance_km=distance_km,
            duration_min=duration_min,
            cost_yuan=cost_yuan,
            route_tips=TRANSIT_STRATEGY.get(strategy, ""),
            path_description=segments_text,
        )

    # ── 步行路线 ───────────────────────────────────────────────────────────────
    def walking(self, origin: Location, destination: Location) -> Optional[RouteSegment]:
        params = {
            "origin":      origin.coord_str,
            "destination": destination.coord_str,
        }
        # 步行用 v3 版本（稳定）
        data = self._get("direction/walking", params)
        if not data:
            return None
        # 步行 API 响应：data.route.paths
        route_obj = data.get("route", {})
        paths = route_obj.get("paths", []) if route_obj else []
        if not paths:
            return None
        path = paths[0]
        steps_text = self._parse_walking_steps(path.get("steps", []))
        distance_km = float(path.get("distance", 0)) / 1000
        duration_sec = float(path.get("duration", path.get("time", 0)))
        duration_min = int(duration_sec / 60)
        return RouteSegment(
            from_loc=origin,
            to_loc=destination,
            mode="walking",
            distance_km=distance_km,
            duration_min=duration_min,
            cost_yuan=0,
            path_description=steps_text,
        )

    # ── 步骤解析工具 ───────────────────────────────────────────────────────────
    @staticmethod
    def _parse_driving_steps(steps: list) -> str:
        """从驾车步骤中提取关键道路名（最多3段）。"""
        roads = []
        for s in steps:
            road = s.get("road_name", "")
            instr = s.get("instruction", "")
            if road and road not in roads:
                roads.append(road)
            if len(roads) >= 3:
                break
        return " → ".join(roads) if roads else textwrap.shorten(
            steps[0]["instruction"] if steps else "高德推荐路线", width=60, placeholder="..."
        )

    @staticmethod
    def _parse_transit_steps(segments: list) -> str:
        """从公交方案中提取换乘信息。"""
        lines = []
        for seg in segments:
            # 优先取公交线路名；步行段/打车段取步行信息
            buslines = seg.get("bus", {}).get("buslines", [])
            if buslines:
                line_name = buslines[0].get("name", "")
            else:
                # 步行段
                walk_dist = seg.get("walk", {}).get("distance", 0)
                taxi_dist = seg.get("taxi", {}).get("distance", 0) if isinstance(seg.get("taxi"), dict) else 0
                if taxi_dist > 0:
                    line_name = f"打车({int(taxi_dist)}m)"
                elif walk_dist > 0:
                    line_name = f"步行({int(walk_dist)}m)"
                else:
                    line_name = "未知"
            walk_dist = seg.get("walk", {}).get("distance", 0)
            walk_str = f"步行{int(walk_dist)}m → " if walk_dist > 0 else ""
            lines.append(f"{walk_str}{line_name}" if line_name else walk_str.rstrip(" → "))
        return " | ".join(lines[:5])

    @staticmethod
    def _parse_walking_steps(steps: list) -> str:
        roads = [s.get("road_name", "") or s.get("instruction", "") for s in steps]
        return " → ".join(r for r in roads if r)[:80]


# ─── 行程导航器 ──────────────────────────────────────────────────────────────

class TripNavigator:
    """
    多景点链式导航：自动按最优顺序排列景点，计算每段路线，
    并汇总全行程时间和费用。
    """

    def __init__(self, amap: AmapClient):
        self.amap = amap
        self.segments: list[RouteSegment] = []

    def plan_route(
        self,
        locations: list[Location],
        mode: str = "transit",
        city: str = "上海",
        strategy: str = "0",
        auto_optimize: bool = True,
    ) -> list[RouteSegment]:
        """
        按顺序计算多景点间的导航路线。
        :param locations: 地点列表
        :param mode: 'driving' | 'transit' | 'walking'
        :param city: 公交规划时的城市名
        :param strategy: 路线策略
        :param auto_optimize: True=穷举找最优顺序（景点≤8时）
        :return: 各段路线列表
        """
        if len(locations) < 2:
            print("⚠️  地点数量不足2个，无需规划路线。")
            return []

        # 景点过多时跳过穷举
        if auto_optimize and len(locations) <= 8:
            print(f"🧮 正在穷举最优顺序（{len(locations)}个景点，共{math.factorial(len(locations))}种排列）...")
            best_order, best_time = self._find_best_order(
                locations, mode, city, strategy
            )
            locations = best_order
            print(f"✅ 最优顺序找到！总耗时减少约 {best_time:.0f} 分钟\n")
        else:
            print(f"📍 规划 {len(locations)} 个景点的链式路线（顺序固定）")

        self.segments = []
        for i in range(len(locations) - 1):
            seg = self._calc_segment(locations[i], locations[i + 1], mode, city, strategy)
            if seg:
                self.segments.append(seg)

        return self.segments

    def _calc_segment(
        self, origin: Location, dest: Location,
        mode: str, city: str, strategy: str
    ) -> Optional[RouteSegment]:
        if mode == "driving":
            return self.amap.driving(origin, dest, strategy)
        elif mode == "transit":
            return self.amap.transit(origin, dest, city, strategy)
        elif mode == "walking":
            return self.amap.walking(origin, dest)
        return None

    def _find_best_order(
        self, locs: list[Location], mode: str, city: str, strategy: str
    ) -> tuple[list[Location], float]:
        """穷举找总耗时最短的景点顺序（TSP 简化）。"""
        best_order, best_time = locs, float("inf")
        for perm in permutations(locs):
            total = 0
            for i in range(len(perm) - 1):
                seg = self._calc_segment(perm[i], perm[i + 1], mode, city, strategy)
                if seg:
                    total += seg.duration_min
                else:
                    total = float("inf")
                    break
            if total < best_time:
                best_time = total
                best_order = perm
        return best_order, float("inf") if best_time == float("inf") else best_time

    def print_summary(self):
        """美化打印全行程导航汇总。"""
        if not self.segments:
            print("📭 暂无路线数据。")
            return

        total_km = sum(s.distance_km for s in self.segments)
        total_min = sum(s.duration_min for s in self.segments)
        total_cost = sum(s.cost_yuan for s in self.segments)

        print("\n" + "=" * 55)
        print(f"  🚄 行程导航总览（共 {len(self.segments)} 段）")
        print("=" * 55)
        print(f"  总距离: {total_km:.1f} km  |  总耗时: {RouteSegment._fmt_dur(total_min)}")
        if total_cost > 0:
            print(f"  预估通行费（驾车）: ¥{total_cost:.0f}")
        print("=" * 55)

        for i, seg in enumerate(self.segments, 1):
            print(f"\n  [{i}/{len(self.segments)}] {seg.from_loc.name} → {seg.to_loc.name}")
            print(f"      {seg.mode_zh}  |  {seg.distance_km:.1f}km  |  {RouteSegment._fmt_dur(seg.duration_min)}")
            if seg.cost_yuan > 0:
                print(f"      通行费: ¥{seg.cost_yuan:.0f}")
            print(f"      🛣 路线: {seg.path_description}")


# ─── 天气预报 ────────────────────────────────────────────────────────────────

@dataclass
class WeatherForecast:
    date: str
    day_weather: str
    night_weather: str
    day_temp: str
    night_temp: str
    day_wind: str
    night_wind: str
    day_power: str
    night_power: str

    def format(self) -> str:
        return (
            f"  📅 {self.date}  白天{self.day_weather} {self.day_temp}° "
            f"| 夜间{self.night_weather} {self.night_temp}°  "
            f"{self.day_wind}{self.day_power}级"
        )


@dataclass
class LiveWeather:
    city: str
    weather: str
    temperature: str
    wind_direction: str
    wind_power: str
    humidity: str
    report_time: str
    dressing_advice: str = ""
    uv_advice: str = ""
    comfort_level: str = ""

    def format(self) -> str:
        return (
            f"{self.city} · {self.weather} {self.temperature}°\n"
            f"  风向: {self.wind_direction} {self.wind_power}级  "
            f"湿度: {self.humidity}%\n"
            f"  更新时间: {self.report_time}"
        )


class WeatherClient:
    """
    高德地图天气预报客户端。
    支持实时天气 + 未来3天预报 + 穿衣/紫外线/舒适度指数。
    """

    def __init__(self, key: str = ""):
        self.key = key or AMAP_KEY
        if not self.key:
            print("⚠️  未设置 AMAP_KEY 环境变量。")
            print("   请在 .env 文件中配置：AMAP_KEY=你的密钥")
            print("   免费注册：https://lbs.amap.com/  → 控制台 → 应用管理 → 添加Key")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "TravelPlanner/1.0 (Weather)"})

    def _get(self, params: dict) -> dict:
        params["key"] = self.key
        params["output"] = "JSON"
        resp = self.session.get(
            "https://restapi.amap.com/v3/weather/weatherInfo",
            params=params, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            infocode = data.get("infocode", "?")
            info = data.get("info", "未知错误")
            print(f"❌ 天气 API 错误 [{infocode}]: {info}")
            return {}
        return data

    def get_live(self, city: str) -> Optional[LiveWeather]:
        """
        获取实时天气（base）。
        city: 城市中文名，如 '上海'、'郴州'、'长沙'、'广州'
        """
        data = self._get({"city": city, "extensions": "base"})
        if not data or data.get("count", "0") == "0":
            return None
        live = data["lives"][0]
        return LiveWeather(
            city=live.get("city", city),
            weather=live.get("weather", "未知"),
            temperature=live.get("temperature", "--"),
            wind_direction=live.get("winddirection", "未知"),
            wind_power=live.get("windpower", "--"),
            humidity=live.get("humidity", "--"),
            report_time=live.get("report_time", ""),
        )

    def get_all(self, city: str) -> tuple[Optional[LiveWeather], list[WeatherForecast]]:
        """
        获取实时天气 + 未来3天预报（extensions=all）。
        返回 (实时天气, 未来3天预报列表)
        """
        data = self._get({"city": city, "extensions": "all"})
        if not data or data.get("count", "0") == "0":
            return None, []

        lives = data.get("lives", [])
        forecasts = data.get("forecasts", [])

        live_weather = None
        if lives:
            live = lives[0]
            # 尝试从 forecasts 里取穿衣指数
            dressing = ""
            comfort = ""
            uv = ""
            if forecasts:
                for idx in forecasts[0].get("index", []):
                    name = idx.get("iname", "")
                    if name == "穿衣指数":
                        dressing = idx.get("detail", "")[:80]
                    elif name == "舒适度指数":
                        comfort = idx.get("detail", "")[:80]
                    elif name == "紫外线指数":
                        uv = idx.get("detail", "")[:80]
            live_weather = LiveWeather(
                city=live.get("city", city),
                weather=live.get("weather", "未知"),
                temperature=live.get("temperature", "--"),
                wind_direction=live.get("winddirection", "未知"),
                wind_power=live.get("windpower", "--"),
                humidity=live.get("humidity", "--"),
                report_time=live.get("report_time", ""),
                dressing_advice=dressing,
                uv_advice=uv,
                comfort_level=comfort,
            )

        forecast_list = []
        seen_dates = set()
        from datetime import date as DateType
        today_str = DateType.today().isoformat()
        for fc in forecasts:
            for f in fc.get("casts", []):
                date = f.get("date", "")
                if date in seen_dates:
                    continue
                seen_dates.add(date)
                # 跳过今天（今天的天气已在实时天气中显示）
                if date == today_str:
                    continue
                forecast_list.append(WeatherForecast(
                    date=f.get("date", ""),
                    day_weather=f.get("dayweather", "未知"),
                    night_weather=f.get("nightweather", "未知"),
                    day_temp=f.get("daytemp", "--"),
                    night_temp=f.get("nighttemp", "--"),
                    day_wind=f.get("daywind", "未知"),
                    night_wind=f.get("nightwind", "未知"),
                    day_power=f.get("daypower", "--"),
                    night_power=f.get("nightpower", "--"),
                ))

        return live_weather, forecast_list

    def print_weather(self, city: str, extensions: str = "all"):
        """
        打印城市天气预报。
        extensions='all' → 实时+3天预报+生活指数
        extensions='base' → 仅实时天气
        """
        if extensions == "base":
            live = self.get_live(city)
            if live:
                print("\n" + "=" * 50)
                print(f"  🌤️  {live.format()}")
                print("=" * 50)
            return

        live, forecasts = self.get_all(city)
        print("\n" + "=" * 55)
        print(f"  🌤️  {city} 天气预报")
        print("=" * 55)

        if live:
            print(f"\n  【实时天气】")
            print(f"  {live.weather} {live.temperature}°  |  {live.wind_direction} {live.wind_power}级  |  湿度 {live.humidity}%")
            print(f"  更新时间: {live.report_time}")
            if live.dressing_advice:
                print(f"\n  👕 穿衣建议: {live.dressing_advice}")
            if live.uv_advice:
                print(f"  ☀️ 紫外线:   {live.uv_advice}")
            if live.comfort_level:
                print(f"  🌡 舒适度:   {live.comfort_level}")

        if forecasts:
            print(f"\n  【未来3天预报】")
            for fc in forecasts:
                print(f"  {fc.format()}")

        print("=" * 55)


# ─── CLI 主程序 ───────────────────────────────────────────────────────────────

def interactive_nav(amap: AmapClient):
    """交互式引导用户输入起终点并查询路线。"""
    print("\n🗺  高德地图路线查询 — 交互模式\n")
    city = input("所在城市（用于公交查询，如'上海'）[上海]: ").strip() or "上海"
    mode_map = {"1": "driving", "2": "transit", "3": "walking"}
    print("出行方式：1=驾车  2=公交/地铁  3=步行")
    mode_input = input("选择 [1]: ").strip() or "1"
    mode = mode_map.get(mode_input, "transit")

    if mode == "transit":
        print("公交策略：0=最快捷  1=最经济  2=最少换乘  3=最少步行  5=不乘地铁")
        strategy = input("选择策略 [0]: ").strip() or "0"
    elif mode == "driving":
        print("驾车策略：0=速度优先  1=费用优先  2=距离优先  4=躲避拥堵")
        strategy = input("选择策略 [0]: ").strip() or "0"
    else:
        strategy = "0"

    print("\n📍 起点（输入地名或地址）：")
    origin_raw = input("  > ").strip()
    print("📍 终点（输入地名或地址）：")
    dest_raw = input("  > ").strip()

    # 地理编码（始终传入 city 提高准确性）
    print(f"\n🔍 正在查询坐标：{origin_raw} ...")
    origin = amap.geocode(origin_raw, city)
    if not origin:
        print(f"❌ 未找到起点：{origin_raw}")
        return

    print(f"🔍 正在查询坐标：{dest_raw} ...")
    destination = amap.geocode(dest_raw, city)
    if not destination:
        print(f"❌ 未找到终点：{dest_raw}")
        return

    print(f"\n📍 起点坐标: {origin.lat},{origin.lng}")
    print(f"📍 终点坐标: {destination.lat},{destination.lng}\n")

    # 路线规划
    if mode == "driving":
        seg = amap.driving(origin, destination, strategy)
    elif mode == "transit":
        seg = amap.transit(origin, destination, city, strategy)
    else:
        seg = amap.walking(origin, destination)

    if seg:
        print(seg.format_summary())
    else:
        print("❌ 未找到推荐路线，请尝试其他方式或调整关键词。")


def main():
    parser = argparse.ArgumentParser(
        description="高德地图路线查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
    示例:
      python amap_nav.py --from "上海外滩" --to "豫园" --mode transit --city 上海
      python amap_nav.py --from "长沙橘子洲" --to "岳麓山" --mode driving
      python amap_nav.py --plan plan.json --mode transit --city 上海
      python amap_nav.py --interactive
        """)
    )
    parser.add_argument("--key",       help="高德 API Key（覆盖环境变量）")
    parser.add_argument("--from",     dest="origin_raw", help="起点地名/地址")
    parser.add_argument("--to",       dest="dest_raw",   help="终点地名/地址")
    parser.add_argument("--mode",     default="transit", choices=["driving","transit","walking"], help="出行方式")
    parser.add_argument("--city",     default="上海",     help="公交规划城市名")
    parser.add_argument("--strategy", default="0",        help="路线策略（mode=driving/transit时）")
    parser.add_argument("--plan",     help="从行程 JSON 文件读取景点列表，批量规划导航")
    parser.add_argument("--output",   help="保存结果到 JSON 文件")
    parser.add_argument("--interactive", action="store_true", help="交互式查询")
    parser.add_argument("--weather", help="查询城市天气预报（如'上海'），同时输出实时+3天预报+生活指数")
    parser.add_argument("--weather-live", dest="weather_live", help="仅查询城市实时天气（如'郴州'）")
    args = parser.parse_args()

    key = args.key or AMAP_KEY
    if not key:
        print("❌ 缺少 AMAP_KEY，请设置环境变量或在 .env 文件中配置。")
        sys.exit(1)

    amap = AmapClient(key)

    # 天气预报模式
    if args.weather:
        WeatherClient(key).print_weather(args.weather, extensions="all")
        return
    if args.weather_live:
        WeatherClient(key).print_weather(args.weather_live, extensions="base")
        return

    # 交互模式
    if args.interactive:
        interactive_nav(amap)
        return

    # 单段路线查询
    if args.origin_raw and args.dest_raw:
        # 始终传入 city 提高地理编码准确性，避免同名地点歧义（如多地岳麓山）
        origin = amap.geocode(args.origin_raw, args.city)
        destination = amap.geocode(args.dest_raw, args.city)
        if not origin or not destination:
            sys.exit(1)

        if args.mode == "driving":
            seg = amap.driving(origin, destination, args.strategy)
        elif args.mode == "transit":
            seg = amap.transit(origin, destination, args.city, args.strategy)
        else:
            seg = amap.walking(origin, destination)

        if seg:
            print(seg.format_summary())
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(asdict(seg), f, ensure_ascii=False, indent=2)
                print(f"\n✅ 结果已保存: {args.output}")
        else:
            print("❌ 未找到路线")
            sys.exit(1)
        return

    # 行程 JSON 批量规划
    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as f:
            plan = json.load(f)
        # 收集所有景点名称
        loc_names = []
        for day in plan.get("days", []):
            for item in day.get("items", []):
                if item.get("type") == "attraction":
                    loc_names.append(item.get("name", ""))

        if not loc_names:
            print("⚠️  行程中未找到景点")
            sys.exit(1)

        print(f"📋 正在对 {len(loc_names)} 个景点进行地理编码和路线规划...")
        locations = []
        for name in loc_names:
            loc = amap.geocode(name, args.city)
            if loc:
                locations.append(loc)
                print(f"  ✅ {name} → {loc.lat:.4f},{loc.lng:.4f}")
            else:
                print(f"  ⚠️  跳过（未找到）: {name}")

        if len(locations) < 2:
            print("⚠️  有效景点不足2个")
            sys.exit(1)

        nav = TripNavigator(amap)
        nav.plan_route(locations, mode=args.mode, city=args.city, strategy=args.strategy)
        nav.print_summary()

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(
                    {i: asdict(s) for i, s in enumerate(nav.segments)},
                    f, ensure_ascii=False, indent=2
                )
            print(f"\n✅ 导航数据已保存: {args.output}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
