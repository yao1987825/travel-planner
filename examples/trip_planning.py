#!/usr/bin/env python3
"""示例：一次旅游出行的完整规划。

    python3 examples/trip_planning.py
    python3 examples/trip_planning.py 北京 首都机场 天安门东
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from metroman import MetroMan  # noqa: E402
from metroman.resolver import resolve_station  # noqa: E402


def plan(city_name: str, origin_text: str, dest_text: str) -> None:
    mm = MetroMan()
    city = mm.city(city_name)
    stations = mm.stations(city.key)

    origin = resolve_station(origin_text, stations)[0].station
    dest = resolve_station(dest_text, stations)[0].station

    print(f"=== {city.name}地铁 · {origin.name} → {dest.name} ===\n")

    routes = mm.plan(city.key, origin.slug, dest.slug)
    for index, route in enumerate(routes[:3], 1):
        print(f"方案 {index}：{route.depart_time} 出发 → {route.arrive_time} 到达"
              f"，{route.duration_text}，票价 {route.fare}，{route.transfers}")
        for leg in route.legs:
            print(f"   {leg.line_name}（{leg.direction}）"
                  f" {leg.from_name} {leg.board_time} → {leg.to_name} {leg.alight_time}"
                  f"（{leg.stop_count} 站 / {leg.duration_min} 分钟）")
            print("      " + " → ".join(f"{s.name} {s.time}" for s in leg.stops))
        print()

    print("--- 出发站首末班车 ---")
    for entry in mm.station_info(city.key, origin.slug).timetables[:6]:
        suffix = "（次日）" if entry.day_offset else ""
        print(f"   {entry.line_name} {entry.direction}｜{entry.day_type}："
              f"{entry.first} - {entry.last}{suffix}")


if __name__ == "__main__":
    if len(sys.argv) == 4:
        plan(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        plan("北京", "首都机场", "天安门东")
