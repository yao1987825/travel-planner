"""数据模型：地铁通站点数据的结构化表示。"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class City:
    """城市（线网）。"""

    id: str
    key: str
    name: str
    en: str
    length_km: str = ""
    lines: str = ""
    stations: str = ""

    @property
    def aliases(self) -> List[str]:
        return [self.name, self.en, self.key, self.id]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Station:
    """车站。"""

    city: str
    slug: str
    name: str
    en: str = ""
    aliases: List[str] = field(default_factory=list)
    station_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Line:
    """线路。"""

    city: str
    slug: str
    name: str
    en: str = ""
    code: str = ""
    color: str = ""
    line_id: Optional[int] = None
    station_slugs: List[str] = field(default_factory=list)
    station_names: List[str] = field(default_factory=list)
    stats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimetableEntry:
    """某条线、某个方向、某类日期的首末班车。"""

    line: str
    line_name: str
    direction: str
    day_type: str
    first: str
    last: str
    day_offset: int = 0

    @property
    def last_day_offset(self) -> int:
        return self.day_offset

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StationInfo:
    """车站详情。"""

    city: str
    slug: str
    name: str
    en: str = ""
    lines: List[str] = field(default_factory=list)
    timetables: List[TimetableEntry] = field(default_factory=list)
    data_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["timetables"] = [t.to_dict() for t in self.timetables]
        return data


@dataclass
class RouteStop:
    """途经站。"""

    name: str
    time: str = ""
    slug: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RouteLeg:
    """乘车区间（一条线上的连续一段）。"""

    line_name: str
    line_code: str = ""
    color: str = ""
    direction: str = ""
    from_name: str = ""
    to_name: str = ""
    from_slug: str = ""
    to_slug: str = ""
    duration_min: Optional[int] = None
    stop_count: Optional[int] = None
    distance_km: Optional[float] = None
    board_time: str = ""
    alight_time: str = ""
    fare: str = ""
    stops: List[RouteStop] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["stops"] = [s.to_dict() for s in self.stops]
        return data


@dataclass
class Route:
    """一条换乘方案。"""

    id: str
    title: str = ""
    depart_time: str = ""
    arrive_time: str = ""
    duration_min: Optional[int] = None
    duration_text: str = ""
    fare: str = ""
    transfers: str = ""
    transfer_count: Optional[int] = None
    distance_km: Optional[float] = None
    advantages: List[str] = field(default_factory=list)
    legs: List[RouteLeg] = field(default_factory=list)
    connections: List[str] = field(default_factory=list)
    map_geometry: Optional[Dict[str, Any]] = None

    @property
    def line_names(self) -> List[str]:
        return [leg.line_name for leg in self.legs]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["legs"] = [leg.to_dict() for leg in self.legs]
        data["line_names"] = self.line_names
        return data
