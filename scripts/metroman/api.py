"""高层查询接口。

用法::

    from metroman import MetroMan

    mm = MetroMan()
    mm.city("北京").key                # -> 'beijing'
    mm.stations("shanghai")           # -> [Station(...), ...]
    mm.plan("shanghai", "xujiahui", "lujiazui")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import parsers
from .client import MetroManClient, NotFoundError
from .models import (
    City,
    Line,
    Route,
    RouteLeg,
    RouteStop,
    Station,
    StationInfo,
    TimetableEntry,
)

TTL_CITIES = 24 * 3600
TTL_INDEX = 12 * 3600
TTL_NETWORK = 6 * 3600
TTL_STATIC = 6 * 3600
TTL_ROUTE = 60

MODES = ("now", "depart", "arrive", "first", "last")
FARES = ("ic", "cash")


class MetroMan:
    """地铁通数据查询门面。"""

    def __init__(self, client: Optional[MetroManClient] = None, **kwargs: Any) -> None:
        self.client = client or MetroManClient(**kwargs)
        self._cities: Optional[List[City]] = None
        self._stations: Dict[str, List[Station]] = {}
        self._lines: Dict[str, List[Line]] = {}
        self._network: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ 城市

    def cities(self, refresh: bool = False) -> List[City]:
        if self._cities is None or refresh:
            page = self.client.get("/", ttl=TTL_CITIES, use_cache=not refresh)
            self._cities = [
                City(
                    id=item["id"],
                    key=item["key"],
                    name=item["name"],
                    en=item["en"],
                    length_km=item["length_km"],
                    lines=item["lines"],
                    stations=item["stations"],
                )
                for item in parsers.parse_home_cities(page)
            ]
        return self._cities

    def city(self, query: str) -> City:
        """按中文名 / 英文名 / key 精确匹配城市。"""
        from .resolver import resolve_city

        return resolve_city(query, self.cities())

    def city_key(self, query: str) -> str:
        return self.city(query).key

    # ------------------------------------------------------------------ 车站

    def stations(self, city: str, refresh: bool = False) -> List[Station]:
        key = self.city_key(city) if not _looks_like_key(city) else city
        if key in self._stations and not refresh:
            return self._stations[key]
        page = self.client.get(
            f"/planner/{key}", ttl=TTL_INDEX, use_cache=not refresh
        )
        stations = [
            Station(
                city=key,
                slug=item["slug"],
                name=item["name"],
                en=item.get("en", ""),
                aliases=item.get("aliases", []),
            )
            for item in parsers.parse_planner_stations(page)
        ]
        self._stations[key] = stations
        return stations

    # ------------------------------------------------------------------ 线路

    def network(self, city: str, refresh: bool = False) -> Dict[str, Any]:
        key = self.city_key(city) if not _looks_like_key(city) else city
        if key in self._network and not refresh:
            return self._network[key]
        page = self.client.get(
            f"/network/{key}", ttl=TTL_NETWORK, use_cache=not refresh
        )
        payload = parsers.parse_network_payload(page) or {}
        self._network[key] = payload
        return payload

    def lines(self, city: str, refresh: bool = False) -> List[Line]:
        key = self.city_key(city) if not _looks_like_key(city) else city
        if key in self._lines and not refresh:
            return self._lines[key]

        payload = self.network(key, refresh=refresh)
        station_by_id = {s["id"]: s for s in payload.get("stations", [])}
        lines: List[Line] = []
        for item in payload.get("lines", []):
            slugs: List[str] = []
            names: List[str] = []
            for sid in item.get("stationIds", []):
                station = station_by_id.get(sid)
                if not station:
                    continue
                slugs.append(station["slug"])
                names.append(station["name"])
            lines.append(
                Line(
                    city=key,
                    slug=item.get("slug", ""),
                    name=item.get("name", ""),
                    en=item.get("en", ""),
                    code=item.get("code", ""),
                    color=item.get("color", ""),
                    line_id=item.get("id"),
                    station_slugs=slugs,
                    station_names=names,
                    stats=item.get("stats", []),
                )
            )
        self._lines[key] = lines
        return lines

    # ------------------------------------------------------------------ 换乘

    def plan(
        self,
        city: str,
        from_slug: str,
        to_slug: str,
        mode: str = "now",
        datetime: Optional[str] = None,
        fare: str = "ic",
        refresh: bool = False,
    ) -> List[Route]:
        """查询换乘方案（解析服务端渲染的方案卡片，含逐站时刻）。"""
        key = self.city_key(city) if not _looks_like_key(city) else city
        if mode not in MODES:
            raise ValueError(f"mode 需为 {MODES} 之一")
        if fare not in FARES:
            raise ValueError(f"fare 需为 {FARES} 之一")

        params: Dict[str, Any] = {"mode": mode, "fare": fare}
        if datetime:
            params["datetime"] = datetime
        path = f"/planner/{key}/{from_slug}-to-{to_slug}"
        page = self.client.get(path, params=params, ttl=TTL_ROUTE, use_cache=not refresh)

        routes: List[Route] = []
        for card in parsers.parse_plan_cards(page):
            legs = []
            for leg in card["legs"]:
                legs.append(
                    RouteLeg(
                        line_name=leg["line_name"],
                        line_code=leg["line_code"],
                        color=leg["color"],
                        direction=leg["direction"],
                        from_name=leg["from_name"],
                        to_name=leg["to_name"],
                        from_slug=leg["from_slug"],
                        to_slug=leg["to_slug"],
                        duration_min=leg["duration_min"],
                        stop_count=leg["stop_count"],
                        distance_km=leg["distance_km"],
                        board_time=leg["board_time"],
                        alight_time=leg["alight_time"],
                        fare=leg["fare"],
                        stops=[
                            RouteStop(name=s["name"], time=s["time"]) for s in leg["stops"]
                        ],
                    )
                )
            routes.append(
                Route(
                    id=card["id"],
                    title=card["title"],
                    depart_time=card["depart_time"],
                    arrive_time=card["arrive_time"],
                    duration_min=card["duration_min"],
                    duration_text=card["duration_text"],
                    fare=card["fare"],
                    transfers=card["transfers"],
                    transfer_count=card["transfer_count"],
                    distance_km=card["distance_km"],
                    advantages=card["advantages"],
                    legs=legs,
                    connections=card["connections"],
                    map_geometry=card["map_geometry"],
                )
            )
        return routes

    def plan_api(
        self,
        city: str,
        from_slug: str,
        to_slug: str,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """调用站点自身的 JSON 路线接口 ``/network/{city}/routes``。"""
        key = self.city_key(city) if not _looks_like_key(city) else city
        path = f"/network/{key}/routes"
        try:
            return self.client.get_json(
                path,
                params={"from": from_slug, "to": to_slug},
                ttl=TTL_ROUTE,
                use_cache=not refresh,
            )
        except NotFoundError:
            return {"status": "Error", "message": "未找到路线", "plans": []}

    # ------------------------------------------------------------------ 车站详情

    def station_info(self, city: str, slug: str, refresh: bool = False) -> StationInfo:
        key = self.city_key(city) if not _looks_like_key(city) else city
        page = self.client.get(
            f"/cities/{key}/stations/{slug}", ttl=TTL_STATIC, use_cache=not refresh
        )
        parsed = parsers.parse_station_page(page)

        name, en = slug, ""
        for station in self.stations(key):
            if station.slug == slug:
                name, en = station.name, station.en
                break

        timetables = [
            TimetableEntry(
                line=item["line"],
                line_name=item["line_name"],
                direction=item["direction"],
                day_type=item["day_type"],
                first=item["first"],
                last=item["last"],
                day_offset=item["day_offset"],
            )
            for item in parsed["timetables"]
        ]
        return StationInfo(
            city=key,
            slug=slug,
            name=name,
            en=en,
            lines=parsed["lines"],
            timetables=timetables,
            data_version=parsed.get("data_version", ""),
        )

    # ------------------------------------------------------------------ 线路详情

    def line_info(self, city: str, slug: str, refresh: bool = False) -> Dict[str, Any]:
        key = self.city_key(city) if not _looks_like_key(city) else city
        page = self.client.get(
            f"/cities/{key}/lines/{slug}", ttl=TTL_STATIC, use_cache=not refresh
        )
        parsed = parsers.parse_line_page(page)
        stations = parsed["stations"]
        if not stations:
            for line in self.lines(key):
                if line.slug == slug:
                    stations = [
                        {"slug": s, "name": n}
                        for s, n in zip(line.station_slugs, line.station_names)
                    ]
                    break
        parsed["stations"] = stations
        return parsed


def _looks_like_key(value: str) -> bool:
    """判断字符串是否已经是城市 key（如 shanghai）。"""
    return bool(value) and value.isascii() and value.replace("-", "").isalnum() and " " not in value
