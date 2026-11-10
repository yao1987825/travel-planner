#!/usr/bin/env python3
"""transit.py —— 跨方式出行编排（把火车 / 地铁 / 公交 / 步行拼成一条时间线）

这是「出行」这件事的主入口。其它脚本（train_store / metroman / bus_query / weather_query）
各自只管一种交通方式，transit.py 负责把它们**串起来**并做跨方式的约束校验。

    python3 transit.py journey --from 郴州西 --to 上海虹桥 --date 明天
    python3 transit.py journey --from 郴州西 --to 上海外滩 --date 明天 --arrive-by 18:00
    python3 transit.py journey --city 上海 --from 人民广场 --to 陆家嘴
    python3 transit.py journey --city 郴州 --from 五岭广场 --to 火车站 --mode bus
    python3 transit.py journey --from 郴州西 --to 上海虹桥 --date 明天 --json

为什么要有这一层（而不是让模型分别去查）：
  1. **末班车是跨方式的坑**：坐 23:40 的火车到上海，落地 05:30，地铁还没首班车 ——
     只有把火车时刻和地铁首末班放在一起才知道。
  2. **arrive-by 反推**：「我 18:00 必须到天安门」要倒推出最晚几点从火车站发车。
  3. **换乘缓冲**：火车→地铁要出站换乘(≥20 分钟)，地铁站内换乘(≥4 分钟)。
  4. **同名不同物**：12306 的「上海虹桥」对应地铁的「虹桥火车站」，
     「长沙南」对应「长沙火车南站」—— 不做映射就会接不上。
  5. 各方式数据源粒度不同(火车给车次、地铁给逐站时刻、公交给实时车辆)，
     统一成 Leg 模型后，输出层不用为每种方式写一套渲染。

分段来源：
    train  -> train_store.train_query        (12306)
    metro  -> metroman                       (地铁通 metroman.cn)
    bus    -> bus_query                      (掌上公交/车来了)
    walk   -> 末段步行提示（站到目的地之间）
    weather -> weather_query                   (中国天气网)

只用标准库；高德部分缺 requests 或缺 Key 时自动降级，不影响其它分段。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:  # Python 3.9+ 自带 zoneinfo；旧版本回退到系统本地时区
    from zoneinfo import ZoneInfo

    _CHINA_TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    _CHINA_TZ = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 各方式之间的最小换乘缓冲（分钟）
BUFFER = {
    ("train", "metro"): 20,
    ("train", "bus"): 20,
    ("train", "walk"): 15,
    ("metro", "bus"): 8,
    ("metro", "walk"): 5,
    ("bus", "walk"): 5,
    ("bus", "metro"): 8,
    ("walk", "metro"): 5,
    ("walk", "bus"): 5,
}

MODE_ZH = {
    "train": "火车",
    "metro": "地铁",
    "bus": "公交",
    "walk": "步行",
    "drive": "驾车",
}

# 地铁城市索引优先扫描的常用城市（覆盖绝大多数「地标->城市」反查场景）
# 优先读 references/travel_data.json 的 metro_priority_cities（数据可改，不用改代码）
def _load_priority_cities() -> Tuple[str, ...]:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "references", "travel_data.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        cities = data.get("metro_priority_cities") or []
        if cities:
            return tuple(cities)
    except (OSError, ValueError):
        pass
    return ("北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "重庆", "武汉", "西安")


PREFER_CITIES = _load_priority_cities()


# ═══════════════════════════════════════════════════════════════ 数据模型


@dataclass
class Leg:
    """行程中的一段。"""

    mode: str
    title: str
    origin: str
    dest: str
    depart: Optional[datetime] = None
    arrive: Optional[datetime] = None
    duration_min: Optional[int] = None
    cost: float = 0.0
    cost_text: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def mode_zh(self) -> str:
        return MODE_ZH.get(self.mode, self.mode)


@dataclass
class Journey:
    """一次完整出行。"""

    origin: str = ""
    dest: str = ""
    date: Optional[datetime] = None
    legs: List[Leg] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    weather: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_min(self) -> Optional[int]:
        first = next((l.depart for l in self.legs if l.depart), None)
        last = next((l.arrive for l in self.legs if l.arrive), None)
        if first and last:
            return int((last - first).total_seconds() // 60)
        return None

    @property
    def total_cost(self) -> float:
        return sum(l.cost for l in self.legs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin,
            "dest": self.dest,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "legs": [
                {
                    "mode": leg.mode,
                    "mode_zh": leg.mode_zh,
                    "title": leg.title,
                    "origin": leg.origin,
                    "dest": leg.dest,
                    "depart": leg.depart.strftime("%Y-%m-%d %H:%M") if leg.depart else None,
                    "arrive": leg.arrive.strftime("%Y-%m-%d %H:%M") if leg.arrive else None,
                    "duration_min": leg.duration_min,
                    "cost": leg.cost,
                    "cost_text": leg.cost_text,
                    "detail": leg.detail,
                    "warnings": leg.warnings,
                    "notes": leg.notes,
                }
                for leg in self.legs
            ],
            "total_min": self.total_min,
            "total_cost": self.total_cost,
            "warnings": self.warnings,
            "weather": self.weather,
        }


# ═══════════════════════════════════════════════════════════════ 时间工具


def now() -> datetime:
    """当前时间。

    出行场景以北京时间为准：工作区/容器经常跑在 UTC，直接用 ``datetime.now()``
    会让「今天/明天」和地铁 ``now`` 模式算错（北京时间已过午夜，UTC 还是前一天）。
    有 zoneinfo 时取 Asia/Shanghai 的墙钟时间（去掉 tzinfo，保持 naive datetime，
    后续 timedelta / strftime 行为不变）。
    """
    if _CHINA_TZ is not None:
        return datetime.now(_CHINA_TZ).replace(tzinfo=None)
    return datetime.now()


def parse_date(text: Optional[str]) -> datetime:
    """解析日期：今天/明天/后天/M月D日/YYYY-MM-DD/YYYYMMDD。"""
    if not text:
        return now().replace(hour=0, minute=0, second=0, microsecond=0)
    text = text.strip()
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    offsets = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2, "大后天": 3}
    if text in offsets:
        return today + timedelta(days=offsets[text])
    match = re.fullmatch(r"[+-](\d+)", text)
    if match:
        return today + timedelta(days=int(match.group(1)))
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%m-%d", "%m/%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt in ("%m-%d", "%m/%d"):
                parsed = parsed.replace(year=today.year)
            return parsed
        except ValueError:
            continue
    match = re.fullmatch(r"(\d{1,2})月(\d{1,2})[日号]?", text)
    if match:
        try:
            return datetime(today.year, int(match.group(1)), int(match.group(2)))
        except ValueError:
            pass
    return today


def parse_clock(text: str) -> Optional[Tuple[int, int]]:
    """解析 HH:MM。"""
    match = re.search(r"(\d{1,2}):(\d{2})", text or "")
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def parse_moment(text: str, base: datetime, cross_day: bool = True) -> Optional[datetime]:
    """把 '09:12' 解析成 base 那天的时刻。

    ``cross_day=True`` 时，若解析出的时刻比 base 早 90 分钟以上，视为**次日**
    （12:58 发车、次日 07:02 到；23:50 发车、次日 01:20 到）。
    """
    clock = parse_clock(text)
    if not clock:
        return None
    moment = base.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
    if cross_day and moment < base - timedelta(minutes=90):
        moment += timedelta(days=1)
    return moment


def weekday_type(moment: datetime) -> str:
    """周一~周四=workday，周五=friday，周六=saturday，周日=sunday。"""
    weekday = moment.weekday()
    if weekday <= 3:
        return "workday"
    if weekday == 4:
        return "friday"
    if weekday == 5:
        return "saturday"
    return "sunday"


def weekday_label(moment: datetime) -> str:
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][moment.weekday()]


def fmt_duration(minutes: Optional[int]) -> str:
    if minutes is None:
        return "-"
    if minutes < 60:
        return f"{minutes}分钟"
    hours, mins = divmod(int(minutes), 60)
    return f"{hours}小时{mins}分钟" if mins else f"{hours}小时"


def fmt_money(amount: float) -> str:
    if not amount:
        return ""
    return f"¥{amount:.0f}" if float(amount).is_integer() else f"¥{amount:.2f}"


# ═══════════════════════════════════════════════════ 地铁时刻表 & 车站映射


def _timetable_day_match(day_type: str, wtype: str) -> bool:
    """站点时刻表里的「适用日期」是否适用于当前星期类型。"""
    text = day_type or ""
    if wtype == "workday":
        return "工作日" in text
    if wtype == "friday":
        return "周五" in text
    if wtype == "saturday":
        return "周六" in text
    if wtype == "sunday":
        return "周日" in text or "国定假日" in text or "节假日" in text
    return False


def metro_service_window(timetables, wtype: str) -> Tuple[Optional[int], Optional[int]]:
    """当天最早首班 / 最晚末班，单位是「从当天零点起的分钟数」。

    跨日末班会 > 1440（例如 26:36 = 次日 02:36），调用方自己换算成日期。
    """
    earliest: Optional[int] = None
    latest: Optional[int] = None
    for entry in timetables:
        if not _timetable_day_match(entry.day_type, wtype):
            continue
        clock = parse_clock(entry.first)
        if clock:
            value = clock[0] * 60 + clock[1]
            earliest = value if earliest is None else min(earliest, value)
        clock = parse_clock(entry.last)
        if clock:
            value = clock[0] * 60 + clock[1] + entry.day_offset * 24 * 60
            latest = value if latest is None else max(latest, value)
    return earliest, latest


def fmt_service_minutes(value: Optional[int]) -> str:
    """把分钟数格式化成 HH:MM（超过一天标「次日」）。"""
    if value is None:
        return "-"
    days, rest = divmod(int(value), 24 * 60)
    text = f"{rest // 60:02d}:{rest % 60:02d}"
    return f"次日{text}" if days else text


def station_core(name: str) -> str:
    """车站名核心词：去掉「站/火车站/火车/高铁」等后缀，便于跨系统匹配。"""
    text = name or ""
    for token in ("火车站", "高铁站", "动车组", "火车", "高铁", "站"):
        text = text.replace(token, "")
    return text


def build_rail_index(rail_names: List[str]) -> Dict[str, List[str]]:
    """铁路站名核心词 -> 站名列表。"""
    index: Dict[str, List[str]] = {}
    for name in rail_names:
        core = station_core(name)
        if not core:
            continue
        index.setdefault(core, []).append(name)
    return index


def build_rail_metro_xref(stations, rail_names: List[str]) -> Dict[str, List[Any]]:
    """铁路站名 -> 该城市里的地铁车站（跨系统接驳的关键映射）。

    例：12306 的「上海虹桥」-> 地铁「虹桥火车站」；「长沙南」->「长沙火车南站」。
    """
    index = build_rail_index(rail_names)
    xref: Dict[str, List[Any]] = {}
    for station in stations:
        core = station_core(station.name)
        if len(core) < 2:
            continue
        hits: List[Any] = []
        for rail_name in index.get(core, []):
            hits.append(station)
        if not hits:
            for rail_core, names in index.items():
                if len(core) >= 3 and rail_core.endswith(core):
                    hits.extend([station] * len(names))
                    break
        for rail_name in index.get(core, []) + [n for c, ns in index.items()
                                                 if len(core) >= 3 and c.endswith(core) for n in ns]:
            xref.setdefault(rail_name, [])
            if station not in xref[rail_name]:
                xref[rail_name].append(station)
    return xref


# ═══════════════════════════════════════════════════════════════ 方式适配器


class MetroAdapter:
    """地铁：metroman（地铁通 metroman.cn）。"""

    name = "metro"

    def __init__(self) -> None:
        from metroman import MetroMan

        self.mm = MetroMan()
        self._xref: Dict[str, Dict[str, List[Any]]] = {}
        self._index: Optional[Dict[str, List[str]]] = None

    # ── 城市 ─────────────────────────────────────────────────────────────
    def city_of(self, text: str) -> Optional[str]:
        """地名 -> 地铁城市 key。

        顺序：城市名精确 -> 城市名前缀（「上海虹桥」-> 上海）-> 铁路站名反推城市
        （「郴州西」-> 郴州）-> 全网车站名索引（「陆家嘴」-> 上海，带磁盘缓存、
        常用城市优先，避免首次构建 55 城索引导致 journey 长时间卡住）。
        """
        from metroman.resolver import resolve_city

        cities = self.mm.cities()
        try:
            return resolve_city(text, cities).key
        except Exception:
            pass
        for city in cities:
            if city.name and text.startswith(city.name):
                return city.key
            if city.en and text.lower().startswith(city.en.lower()):
                return city.key
        # 铁路站名 -> 城市：12306 站名通常以城市名开头（上海虹桥、长沙南、郴州西）
        if rail_station_code(text):
            city = self._city_of_rail_station(text, cities)
            if city:
                return city
            # 是铁路站名但没推出地铁城市（如「郴州西」）：只在已有缓存时查一下，
            # 避免为铁路站名触发全网地铁站扫描（它几乎不可能是别城的地铁站）。
            cached = self._load_station_index_cache()
            if cached:
                self._index = cached
                for candidate in (text, text.replace("站", "")):
                    hits = cached.get(candidate)
                    if hits:
                        return hits[0]
            return None
        return self.city_of_station(text)

    def _city_of_rail_station(self, name: str, cities: List[Any]) -> Optional[str]:
        """铁路站名 -> 地铁城市 key。按城市名长度降序匹配，避免短名误伤。"""
        for city in sorted(cities, key=lambda c: len(c.name or ""), reverse=True):
            if city.name and name.startswith(city.name):
                return city.key
        return None

    # 全网车站索引的磁盘缓存（~/.cache/metroman/station_index.json）
    _CITIES_KEY = "__cities__"

    @staticmethod
    def _station_index_path() -> str:
        base = os.environ.get("METROMAN_CACHE_DIR")
        if not base:
            xdg = os.environ.get("XDG_CACHE_HOME")
            base = xdg or os.path.join(os.path.expanduser("~"), ".cache")
        return os.path.join(base, "metroman", "station_index.json")

    def _load_station_index_cache(self) -> Optional[Dict[str, List[str]]]:
        path = self._station_index_path()
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and self._CITIES_KEY in data:
                    self._index_cities = set(data.get(self._CITIES_KEY, []))
                    return {k: v for k, v in data.items() if k != self._CITIES_KEY}
                # 旧格式（纯站名->城市列表）：从 value 推断已覆盖城市
                covered = set()
                for city_list in data.values():
                    if isinstance(city_list, list):
                        covered.update(city_list)
                self._index_cities = covered
                return data
        except (OSError, ValueError):
            pass
        return None

    def _save_station_index_cache(self, index: Dict[str, List[str]],
                                   cities: Optional[List[str]] = None) -> None:
        path = self._station_index_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = dict(index)
            data[self._CITIES_KEY] = sorted(
                cities or getattr(self, "_index_cities", []))
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
        except OSError:
            pass

    def station_index(self, refresh: bool = False) -> Dict[str, List[str]]:
        """站名/slug -> 城市 key 列表（覆盖全部 55 城）。

        带磁盘缓存（默认 7 天），首次构建按「常用城市优先」的顺序，命中即可提前返回，
        避免联网遍历全部城市把 journey 卡死。
        """
        if self._index is not None and not refresh:
            return self._index
        cached = self._load_station_index_cache()
        if cached and not refresh:
            self._index = cached
            return cached
        index: Dict[str, List[str]] = {}
        covered: List[str] = []
        for city in self.mm.cities():
            try:
                stations = self.mm.stations(city.key)
            except Exception:
                continue
            covered.append(city.key)
            for station in stations:
                for key in {station.name, station.slug, *station.aliases}:
                    if not key:
                        continue
                    bucket = index.setdefault(key, [])
                    if city.key not in bucket:
                        bucket.append(city.key)
        self._index = index
        self._index_cities = set(covered)
        self._save_station_index_cache(index, covered)
        return index

    def city_of_station(self, text: str) -> Optional[str]:
        """用地铁站名反查城市。

        先读磁盘缓存；没有缓存时按常用城市优先逐个拉取，命中即返回并写缓存。
        缓存未命中（比如非常用城市的地铁站）时继续扫描未覆盖城市并扩展缓存。
        这样「陆家嘴」这类地标在首次运行也只扫常用 10 城，而不是 55 城全量。
        """
        candidates = (text, text.replace("站", ""))
        cached = self._load_station_index_cache()
        if cached:
            self._index = cached
            for candidate in candidates:
                hits = cached.get(candidate)
                if hits:
                    return hits[0]
            # 缓存未命中：继续扫描尚未覆盖的城市
            covered = set(getattr(self, "_index_cities", []))
            remaining = [c for c in self.mm.cities() if c.key not in covered]
            if not remaining:
                return None
            index = dict(cached)
            for city in remaining:
                try:
                    stations = self.mm.stations(city.key)
                except Exception:
                    continue
                covered.add(city.key)
                for station in stations:
                    for key in {station.name, station.slug, *station.aliases}:
                        if not key:
                            continue
                        bucket = index.setdefault(key, [])
                        if city.key not in bucket:
                            bucket.append(city.key)
                for candidate in candidates:
                    hits = index.get(candidate)
                    if hits:
                        self._index = index
                        self._index_cities = covered
                        self._save_station_index_cache(index, sorted(covered))
                        return hits[0]
            self._index = index
            self._index_cities = covered
            self._save_station_index_cache(index, sorted(covered))
            return None

        cities = self.mm.cities()
        prefer = [c for c in cities if c.name in PREFER_CITIES]
        rest = [c for c in cities if c not in prefer]
        index: Dict[str, List[str]] = {}
        covered_list: List[str] = []
        for city in prefer + rest:
            try:
                stations = self.mm.stations(city.key)
            except Exception:
                continue
            covered_list.append(city.key)
            for station in stations:
                for key in {station.name, station.slug, *station.aliases}:
                    if not key:
                        continue
                    bucket = index.setdefault(key, [])
                    if city.key not in bucket:
                        bucket.append(city.key)
            for candidate in candidates:
                hits = index.get(candidate)
                if hits:
                    self._index = index
                    self._index_cities = set(covered_list)
                    self._save_station_index_cache(index, covered_list)
                    return hits[0]
        self._index = index
        self._index_cities = set(covered_list)
        self._save_station_index_cache(index, covered_list)
        return None

    def stations(self, city: str) -> List[Any]:
        return self.mm.stations(city)

    def match_station(self, city: str, name: str) -> List[Any]:
        from metroman.resolver import resolve_station

        return resolve_station(name, self.stations(city), limit=5)

    def match_rail_station(self, city: str, rail_name: str) -> List[Any]:
        """用铁路站名反查地铁站（「上海虹桥」-> 「虹桥火车站」）。"""
        if city not in self._xref:
            try:
                rail_names = list(_rail_station_names())
            except Exception:
                rail_names = []
            self._xref[city] = build_rail_metro_xref(self.stations(city), rail_names)
        return self._xref[city].get(rail_name, [])

    def city_name(self, city: str) -> str:
        """地铁城市 key -> 中文名（shanghai -> 上海）。"""
        for c in self.mm.cities():
            if c.key == city or c.id == city:
                return c.name or city
        return city

    def city_rail_stations(self, city: str, metro_station_slug: str = "") -> List[str]:
        """该城市的铁路到达站候选（按「与目的地地铁站的映射 -> 城市同名站 -> 其它」排序）。

        例：目的地是「上海火车站」地铁站时，优先给出 12306 的「上海」站。
        """
        from metroman.resolver import resolve_city

        try:
            city_obj = resolve_city(city, self.mm.cities())
        except Exception:
            city_obj = None
        city_name = city_obj.name if city_obj else city
        rail_names = [n for n in _rail_station_names() if n.startswith(city_name)]

        candidates: List[str] = []
        if metro_station_slug:
            for station in self.stations(city):
                if station.slug != metro_station_slug:
                    continue
                for rail_name, mapped in self._xref.get(city, {}).items():
                    if any(m.slug == station.slug for m in mapped):
                        candidates.append(rail_name)
        for name in rail_names:
            if name not in candidates:
                candidates.append(name)
        return candidates[:6]

    def plan(self, city: str, from_slug: str, to_slug: str,
             moment: Optional[datetime] = None) -> List[Any]:
        mode = "now"
        dt = None
        if moment and moment > now():
            mode = "depart"
            dt = moment.strftime("%Y%m%d%H%M")
        return self.mm.plan(city, from_slug, to_slug, mode=mode, datetime=dt)

    def station_info(self, city: str, slug: str) -> Any:
        return self.mm.station_info(city, slug)

    def last_train(self, city: str, station_slug: str, moment: datetime) -> Optional[datetime]:
        """该站当天最晚一班车的发车时刻（考虑跨日末班）。"""
        try:
            info = self.station_info(city, station_slug)
        except Exception:
            return None
        _, latest = metro_service_window(info.timetables, weekday_type(moment))
        if latest is None:
            return None
        return moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=latest)

    def first_train(self, city: str, station_slug: str, moment: datetime) -> Optional[datetime]:
        try:
            info = self.station_info(city, station_slug)
        except Exception:
            return None
        earliest, _ = metro_service_window(info.timetables, weekday_type(moment))
        if earliest is None:
            return None
        return moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=earliest)


class TrainAdapter:
    """火车：12306（train_store）。"""

    name = "train"

    def query(self, from_station: str, to_station: str, date: datetime,
              train_type: str = "") -> Dict[str, Any]:
        import train_store

        args = {
            "date": date.strftime("%Y-%m-%d"),
            "from_station": from_station,
            "to_station": to_station,
        }
        if train_type:
            args["train_type"] = train_type
        try:
            return train_store.train_query(args)
        except Exception as exc:
            return {"error": str(exc)}


class BusAdapter:
    """公交：bus_query（掌上公交 / 车来了）。"""

    name = "bus"

    def route(self, city: str, origin: str, dest: str) -> Dict[str, Any]:
        import bus_query

        namespace = argparse.Namespace(
            city=city, origin=origin, dest=dest,
            src=None, json=True, limit=20,
        )
        try:
            bus_query.cmd_route(namespace)
        except SystemExit:
            pass
        return {}


_RAIL_NAMES: Optional[List[str]] = None


def _rail_station_names() -> List[str]:
    """12306 全部车站名（懒加载）。"""
    global _RAIL_NAMES
    if _RAIL_NAMES is None:
        try:
            import train_store

            # _get_station_code 会先把离线缓存装进 _station_map
            train_store._get_station_code("北京")
            _RAIL_NAMES = list((train_store._station_map or {}).keys())
        except Exception:
            _RAIL_NAMES = []
    return _RAIL_NAMES


def rail_station_code(name: str) -> str:
    """查 12306 电报码；查不到返回空串。"""
    try:
        import train_store

        return train_store._get_station_code(name) or ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════ 编排主体


def build_train_leg(train: TrainAdapter, origin: str, dest: str, moment: datetime,
                    arrive_by: Optional[datetime],
                    depart_at: Optional[datetime] = None) -> Optional[Leg]:
    """城际段：查 12306，挑一班车。"""
    payload = train.query(origin, dest, moment)
    if payload.get("error"):
        return None
    trains = payload.get("has_ticket_trains") or []
    if not trains:
        return None

    def rank(item: Dict[str, Any]) -> Tuple[int, int]:
        depart = parse_moment(item.get("start_time", ""), moment)
        # 到达时刻相对发车时刻解析：12:58 发车、次日 07:02 到
        arrive = parse_moment(item.get("arrive_time", ""), depart or moment)
        if depart_at and depart and depart < depart_at:
            return (3, 0)           # 发车太早，不满足
        if arrive_by and arrive:
            if arrive > arrive_by:
                # 都超时：挑最早能到的（越早越接近目标）
                return (2, int(arrive.timestamp() // 60))
            # 满足且尽量晚出发（少候车）
            return (0, -int(depart.timestamp() // 60) if depart else 0)
        # 默认：优先高铁/动车，其次早班车
        is_high = 1 if str(item.get("train_type")) in ("高铁", "动车") else 0
        depart_min = int((depart - moment).total_seconds() // 60) if depart else 0
        return (1 - is_high, depart_min)

    trains_sorted = sorted(trains, key=rank)
    best = trains_sorted[0]
    depart = parse_moment(best.get("start_time", ""), moment)
    # 到达时刻要相对「发车时刻」解析：12:58 发车、次日 07:02 到
    arrive = parse_moment(best.get("arrive_time", ""), depart or moment)
    duration = int((arrive - depart).total_seconds() // 60) if depart and arrive else None
    seats = best.get("seats") or {}
    seat_text = "、".join(f"{k}{v}" for k, v in seats.items() if v and v != "无")

    leg = Leg(
        mode="train",
        title=f"{best.get('station_train_code', '')} {origin}→{dest}".strip(),
        origin=origin,
        dest=dest,
        depart=depart,
        arrive=arrive,
        duration_min=duration,
        detail={
            "train_no": best.get("station_train_code"),
            "start_time": best.get("start_time"),
            "arrive_time": best.get("arrive_time"),
            "lishi": best.get("lishi"),
            "train_type": best.get("train_type"),
            "seats": seats,
            "seat_text": seat_text,
            "ticket_count": payload.get("ticket_count"),
            "total_count": payload.get("train_count"),
        },
        notes=["票价与余票以 12306 官网/App 为准（此处不估算票价）"],
    )
    if arrive_by and arrive and arrive > arrive_by:
        leg.warnings.append(
            f"当天没有 {arrive_by:%H:%M} 前到达的车次；最早的一班 {arrive:%H:%M} 到，"
            f"请考虑前一晚出发或改其它交通方式"
        )
    return leg


def build_metro_leg(metro: MetroAdapter, city: str, origin_name: str, dest_name: str,
                    moment: Optional[datetime]) -> Optional[Leg]:
    """市内段：地铁换乘方案。"""
    origin = _pick_station(metro, city, origin_name)
    dest = _pick_station(metro, city, dest_name)
    if origin is None or dest is None or origin.slug == dest.slug:
        return None
    try:
        routes = metro.plan(city, origin.slug, dest.slug, moment)
    except Exception:
        return None
    if not routes:
        return None
    route = routes[0]
    base = moment or now()
    depart = parse_moment(route.depart_time, base)
    arrive = parse_moment(route.arrive_time, base)
    duration = None
    if depart and arrive:
        duration = int((arrive - depart).total_seconds() // 60)
    cost = 0.0
    match = re.search(r"(\d+(?:\.\d+)?)", route.fare or "")
    if match:
        cost = float(match.group(1))
    return Leg(
        mode="metro",
        title=f"{origin.name} → {dest.name}",
        origin=origin.name,
        dest=dest.name,
        depart=depart,
        arrive=arrive,
        duration_min=duration if duration is not None else route.duration_min,
        cost=cost,
        cost_text=route.fare,
        detail={
            "city": city,
            "from_station": origin.name,
            "to_station": dest.name,
            "from_slug": origin.slug,
            "to_slug": dest.slug,
            "transfers": route.transfers,
            "transfer_count": route.transfer_count,
            "distance_km": route.distance_km,
            "advantages": route.advantages,
            "legs": [
                {
                    "line": leg.line_name,
                    "direction": leg.direction,
                    "from": leg.from_name,
                    "to": leg.to_name,
                    "board": leg.board_time,
                    "alight": leg.alight_time,
                    "stops": leg.stop_count,
                    "stops_detail": [{"name": s.name, "time": s.time} for s in leg.stops],
                }
                for leg in route.legs
            ],
            "alternatives": len(routes),
        },
    )


def _pick_station(metro: MetroAdapter, city: str, name: str):
    """车站名 -> 地铁车站。

    铁路站名优先用「铁路->地铁」映射（「上海」-> 上海火车站），再做普通模糊匹配；
    匹配太弱就放弃（宁可说没找到，也不要乱指一个站）。
    """
    if rail_station_code(name):
        rail_matches = metro.match_rail_station(city, name)
        if rail_matches:
            return rail_matches[0]
    matches = metro.match_station(city, name)
    if matches and matches[0].score >= 0.75:
        return matches[0].station
    rail_matches = metro.match_rail_station(city, name)
    if rail_matches:
        return rail_matches[0]
    if matches and matches[0].score >= 0.5:
        return matches[0].station
    return None


def build_walk_leg(origin: str, dest: str) -> Optional[Leg]:
    """末段步行：没有地图服务，只能给个提示（具体路线让用户查地图 App）。"""
    if not origin or not dest or origin == dest:
        return None
    return Leg(
        mode="walk",
        title=f"{origin} → {dest}",
        origin=origin,
        dest=dest,
        detail={"note": "步行段，具体路线请用地图 App 查询"},
        notes=["末段步行：站到目的地之间还有一段路，步行导航请用地图 App"],
    )


def build_bus_leg(city: str, origin: str, dest: str) -> Optional[Leg]:
    """公交兜底段：地铁不可达时，用 bus_query 的「直达线路」接口拼一段公交。

    公交接口只做**直达**查询（不做换乘规划），也没有精确发车时刻，
    所以这一段只给线路/方向/大概站数，实时到站交给 bus_query live。
    查询放在子线程里并设超时，避免公交接口慢时把整个 journey 卡住。
    """
    import contextlib
    import io
    import threading

    import bus_query

    namespace = argparse.Namespace(
        city=city, origin=origin, destination=dest,
        src=None, json=True, limit=5,
    )
    buf = io.StringIO()
    result: dict = {}

    def _run() -> None:
        nonlocal result
        try:
            with contextlib.redirect_stdout(buf):
                rc = bus_query.cmd_route(namespace)
            if rc == 0:
                try:
                    result = json.loads(buf.getvalue())
                except ValueError:
                    result = {}
        except SystemExit:
            result = {}
        except Exception:
            result = {}

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout=25)
    if worker.is_alive() or not result:
        return None
    usable = [d for d in result.get("direct", []) if d.get("usable")]
    if not usable:
        return None
    best = usable[0]
    stops = best.get("stops")
    return Leg(
        mode="bus",
        title=f"{best.get('lineName')} {origin}→{dest}",
        origin=origin,
        dest=dest,
        duration_min=None,
        cost=2.0,
        cost_text="2元",
        detail={
            "city": result.get("city", city),
            "routes": usable[:3],
            "note": "公交为直达方案，无精确发车时刻；实时到站请用 bus_query live 查询",
        },
        notes=[
            f"{best.get('lineName')}：起点第 {best.get('originOrder')} 站 → "
            f"终点第 {best.get('destOrder')} 站（约 {stops} 站）",
            "公交实时到站请用 `bus_query.py live` 查看车辆位置与到站预测",
        ],
    )


def compose_journey(args: argparse.Namespace) -> Journey:
    """按参数拼一条完整出行时间线。"""
    journey = Journey(origin=args.origin, dest=args.dest, date=parse_date(args.date))
    arrive_by = getattr(args, "arrive_by_dt", None)

    metro = MetroAdapter()
    train = TrainAdapter()

    origin_city = args.city or metro.city_of(args.origin)
    dest_city = args.city or metro.city_of(args.dest)

    origin_rail = bool(rail_station_code(args.origin))
    dest_rail = bool(rail_station_code(args.dest))

    # ── 1. 城际段判定 ───────────────────────────────────────────────────
    intercity = False
    if args.mode == "train":
        intercity = True
    elif args.mode in ("metro", "bus", "walk"):
        intercity = False
    elif origin_city and dest_city:
        intercity = origin_city != dest_city
    elif origin_rail and dest_rail:
        intercity = True
    elif origin_rail and dest_city:
        intercity = True      # 从火车站去另一座城市的某个地方
    elif dest_rail and origin_city:
        intercity = True      # 从某地坐火车去火车站

    leg_from = args.origin
    leg_to = args.dest
    next_start: Optional[datetime] = None

    if intercity:
        # 目的城市的到达站：优先「目的地地铁站对应的铁路站」，其次城市同名站
        arrival_candidates: List[str] = []
        anchor_slug = ""
        if dest_city:
            dest_station = _pick_station(metro, dest_city, args.dest)
            if dest_station is not None:
                anchor_slug = dest_station.slug
            arrival_candidates = metro.city_rail_stations(dest_city, anchor_slug)
        if not arrival_candidates:
            arrival_candidates = [args.dest]

        leg = None
        candidate = args.dest
        for option in arrival_candidates[:3]:
            candidate = option
            leg = build_train_leg(train, args.origin, option, journey.date, arrive_by,
                                  getattr(args, "depart_at_dt", None))
            if leg:
                leg.detail["arrival_station"] = option
                break
        if leg:
            journey.legs.append(leg)
            leg_from = candidate
            if candidate != args.dest:
                if dest_rail:
                    journey.warnings.append(
                        f"12306 上没查到直达「{args.dest}」，先到「{candidate}」，"
                        f"再在目的城市内换乘")
                else:
                    journey.warnings.append(
                        f"「{args.dest}」不是铁路站名，先坐火车到「{candidate}」，"
                        f"再在目的城市内换乘")
            if leg.arrive:
                next_start = leg.arrive + timedelta(
                    minutes=BUFFER.get(("train", "metro"), 20))
        else:
            journey.warnings.append(
                "城际车次没查到（12306 需要标准站名，或当天无直达车）")

    # ── 2. 市内段：地铁优先，其次公交 ────────────────────────────────────
    city = dest_city or origin_city
    city_name = metro.city_name(city) if city else ""
    # 城市是推断出来的（用户没给 --city）：显式提醒，避免把「武林广场」默认当成杭州
    if args.mode in ("auto", "bus") and not args.city and city and not intercity:
        if origin_city != dest_city:
            journey.warnings.append(
                f"起终点没落在同一个地铁城市（{args.origin}→{origin_city or '未知'}，"
                f"{args.dest}→{dest_city or '未知'}）；"
                f"如果实际城市不是「{city_name or city}」，请用 --city 明确指定")
        else:
            journey.warnings.append(
                f"根据起终点推断城市为「{city_name or city}」；"
                f"如果不对，请用 --city 明确指定城市")
    if city and leg_from and leg_to and leg_from != leg_to:
        metro_leg = None
        if args.mode in ("auto", "metro"):
            moment = next_start
            if moment is None:
                moment = getattr(args, "depart_at_dt", None)
            if moment is None:
                moment = max(now(), journey.date + timedelta(hours=9))
            metro_leg = build_metro_leg(metro, city, leg_from, leg_to, moment)
        if metro_leg:
            journey.legs.append(metro_leg)
            leg_to = metro_leg.dest
            if metro_leg.arrive:
                next_start = metro_leg.arrive + timedelta(
                    minutes=BUFFER.get(("metro", "walk"), 5))
        else:
            # 公交兜底：地铁不可达时给直达公交方案，而不是只报一句「没找到」
            bus_leg = None
            if args.mode in ("auto", "bus"):
                bus_leg = build_bus_leg(city_name or city, leg_from, leg_to)
            if bus_leg:
                journey.legs.append(bus_leg)
                leg_to = bus_leg.dest
                journey.warnings.append(
                    f"地铁没有直达方案，已改用公交兜底（{city}·{leg_from}→{leg_to}）")
            else:
                journey.warnings.append(
                    f"市内段没找到地铁直达方案，公交也没有直达线路"
                    f"（{city}·{leg_from}→{leg_to}）")
    elif args.mode in ("auto", "bus"):
        # 城市没解析出来（比如两个端点都是不知名的公交站）——
        # 不要静默默认城市，明确要求用户补充。
        journey.warnings.append(
            "无法确定城市：请补充城市名后再查公交/市内换乘"
            "（例如 journey --city 郴州 --from 香麓山花园 --to 武林广场 --mode bus）")

    # ── 3. 接驳段：地铁站 → 目的地常需要走一段 ───────────────────────────
    if args.mode in ("auto", "walk") and leg_to and leg_to != args.dest:
        walk_leg = build_walk_leg(leg_to, args.dest)
        if walk_leg:
            journey.legs.append(walk_leg)

    # ── 4. 跨方式约束校验：末班车 / 换乘缓冲 ──────────────────────────────
    check_constraints(journey, metro)

    # ── 5. 目的地天气（可选）：把天气也串进行程 ──────────────────────────
    if getattr(args, "weather", False):
        add_weather(journey, dest_city)
    return journey


def _weather_city_name(city: Optional[str], dest: str) -> str:
    """把城市参数转成天气查询用的中文城市名。

    - ``city`` 为地铁城市 key（shanghai）-> 查中文名（上海）；
    - ``city`` 为空 -> 尝试用目的地文字直接作为城市名；
    - 已经是中文 -> 原样返回。
    """
    if city:
        if city.isascii():
            try:
                metro = MetroAdapter()
                for c in metro.mm.cities():
                    if c.key == city or c.id == city:
                        return c.name or city
            except Exception:
                pass
        return city
    return (dest or "").replace("市", "")


def add_weather(journey: Journey, city: Optional[str]) -> None:
    """把目的地天气挂进行程；有预警就提示改期/备选。

    ``city`` 可能是地铁城市 key（shanghai），也可能是中文城市名；
    统一先转成中文名再查天气，避免依赖 weather_query 的在线搜索兜底。
    """
    try:
        import weather_query

        name, areaid = weather_query.resolve_area(_weather_city_name(city, journey.dest))
        data = weather_query.fetch_live(areaid)
    except Exception as exc:
        journey.warnings.append(f"天气没查到（{exc}）")
        return

    live = data.get("live", {})
    info = data.get("city", {})
    alarms = data.get("alarms") or []
    journey.weather = {
        "city": name,
        "weather": live.get("weather", ""),
        "temp": live.get("temp", ""),
        "wind": f"{live.get('WD','')}{live.get('WS','')}",
        "humidity": live.get("SD", ""),
        "aqi": live.get("aqi", ""),
        "today": f"{info.get('weather','')} {info.get('temp','')}/{info.get('tempn','')}",
        "alarms": alarms,
    }
    for alarm in alarms:
        journey.warnings.append(
            f"目的地有气象预警：[{alarm.get('level','')}{alarm.get('type','')}] "
            f"{alarm.get('title','')}（{alarm.get('issued','')}）")


def check_constraints(journey: Journey, metro: MetroAdapter) -> None:
    """跨方式约束校验 —— 这是把各方式「联系起来」的关键。"""
    legs = journey.legs
    for index in range(len(legs) - 1):
        current, following = legs[index], legs[index + 1]
        if not current.arrive:
            continue
        buffer = BUFFER.get((current.mode, following.mode), 10)
        if following.depart:
            gap = int((following.depart - current.arrive).total_seconds() // 60)
            if gap < buffer:
                message = (f"{current.mode_zh}→{following.mode_zh} 只有 {gap} 分钟换乘，"
                           f"建议至少 {buffer} 分钟")
                following.warnings.append(message)
                journey.warnings.append(message)
        elif following.mode == "metro" and following.detail.get("from_slug"):
            last = metro.last_train(
                following.detail.get("city", ""),
                following.detail.get("from_slug", ""),
                current.arrive,
            )
            if last and last < current.arrive:
                journey.warnings.append(
                    f"{following.detail.get('from_station')} 末班车 {last:%H:%M}，"
                    f"而上一段 {current.arrive:%H:%M} 才到 —— 落地时地铁可能已收班，"
                    f"请改乘公交/打车或调整班次"
                )
            elif last:
                following.notes.append(
                    f"{following.detail.get('from_station')} 当天末班车 {last:%H:%M}（含跨日末班）")
            # 地铁段自己有发车时刻时：核对是否还在当天运营时间内
            if following.depart and last and following.depart > last:
                journey.warnings.append(
                    f"{following.detail.get('from_station')} 的末班车是 {last:%H:%M}，"
                    f"方案里的 {following.depart:%H:%M} 发车属于次日班次，请确认"
                )
    journey.warnings = list(dict.fromkeys(journey.warnings))


# ═══════════════════════════════════════════════════════════════ 渲染输出


def render(journey: Journey) -> str:
    lines: List[str] = []
    date_text = ""
    if journey.date:
        date_text = f"{journey.date:%Y-%m-%d}（{weekday_label(journey.date)}）"
    lines.append(f"╭ {journey.origin} → {journey.dest} ╮")
    if date_text:
        lines.append(f"  {date_text}")

    if not journey.legs:
        lines.append("")
        lines.append("没拼出可行方案。")
        for warning in journey.warnings:
            lines.append(f"  ⚠️ {warning}")
        return "\n".join(lines)

    for index, leg in enumerate(journey.legs, 1):
        head = f"{index}. {leg.mode_zh}"
        if leg.depart and leg.arrive:
            head += f"   {leg.depart:%H:%M} → {leg.arrive:%H:%M}"
        head += f"   {fmt_duration(leg.duration_min)}"
        if leg.cost_text:
            head += f"   {leg.cost_text}"
        lines.append("")
        lines.append(f"{head}   {leg.title}")

        if leg.mode == "train":
            detail = leg.detail
            seat = detail.get("seat_text") or "有票"
            lines.append(f"   {detail.get('train_no')} 次 · {detail.get('train_type')} · {seat}")
            lines.append(f"   在途 {detail.get('lishi')}")
        elif leg.mode == "metro":
            for sub in leg.detail.get("legs", []):
                lines.append(
                    f"   ▸ {sub['line']}（{sub['direction']}）"
                    f" {sub['from']} {sub['board']} 上车 → {sub['to']} {sub['alight']} 下车"
                    f"（{sub['stops']}站）"
                )
                stops = sub.get("stops_detail") or []
                if stops:
                    lines.append("       " + " → ".join(
                        f"{s['name']} {s['time']}" for s in stops))
            if leg.detail.get("transfers"):
                lines.append(f"   {leg.detail['transfers']}")
        elif leg.mode == "bus":
            for route in (leg.detail.get("routes") or [])[:3]:
                line_name = (route.get("lineName") or route.get("name")
                             or route.get("line") or "")
                direction = route.get("direction", "")
                stops = route.get("stops")
                stops_text = f"{stops}站" if stops else ""
                lines.append(f"   ▸ {line_name}（方向{direction}）{stops_text}")
        elif leg.mode == "walk":
            info = leg.detail
            dist = info.get("distance_km")
            dur = info.get("duration_min")
            if dist or dur:
                lines.append(f"   {dist}公里 · 约 {dur}分钟")
            else:
                lines.append(f"   {info.get('note', '步行前往')}")

        for note in leg.notes:
            lines.append(f"   ℹ️ {note}")
        for warning in leg.warnings:
            lines.append(f"   ⚠️ {warning}")

    total = journey.total_min
    summary = f"总计 {fmt_duration(total)}"
    cost_text = fmt_money(journey.total_cost) if journey.total_cost else ""
    if cost_text:
        summary += f" · 约 {cost_text}"
    summary += " · " + " + ".join(leg.mode_zh for leg in journey.legs)
    lines.append("")
    lines.append(summary)
    weather = journey.weather or {}
    if weather:
        lines.append(
            f"目的地天气：{weather.get('city','')} {weather.get('weather','')}"
            f" {weather.get('temp','')}℃  {weather.get('wind','')}"
            f" 湿度 {weather.get('humidity','')}  AQI {weather.get('aqi','')}"
            f"  今日 {weather.get('today','')}")
    for warning in journey.warnings:
        lines.append(f"⚠️ {warning}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════ 命令行


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transit.py",
        description="跨方式出行编排：把火车/地铁/公交/步行拼成一条时间线",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("journey", help="拼一条完整出行时间线")
    p.add_argument("--from", dest="origin", required=True, help="起点（车站名/地标/地址）")
    p.add_argument("--to", dest="dest", required=True, help="终点")
    p.add_argument("--city", help="城市（市内行程时指定，跨城会自动推断）")
    p.add_argument("--date", help="出行日期：今天/明天/后天/2026-11-08")
    p.add_argument("--arrive-by", dest="arrive_by", help="必须到达的时刻，如 18:00")
    p.add_argument("--depart-at", dest="depart_at", help="必须出发的时刻，如 09:00")
    p.add_argument("--mode", default="auto",
                   choices=["auto", "train", "metro", "bus", "walk"],
                   help="优先使用的方式")
    p.add_argument("--weather", action="store_true", help="附带目的地天气")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.set_defaults(func=cmd_journey)

    return parser


def cmd_journey(args: argparse.Namespace) -> int:
    base = parse_date(args.date)
    args.arrive_by_dt = parse_moment(args.arrive_by, base) if args.arrive_by else None
    args.depart_at_dt = parse_moment(args.depart_at, base) if args.depart_at else None
    journey = compose_journey(args)
    if args.json:
        print(json.dumps(journey.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render(journey))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover
        print(f"[transit] 失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
