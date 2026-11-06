"""命令行入口。

    python -m metroman cities
    python -m metroman stations 上海 --search 徐家汇
    python -m metroman lines 北京
    python -m metroman plan 上海 徐家汇 陆家嘴
    python -m metroman station 上海 徐家汇
    python -m metroman line 上海 1号线
    python -m metroman ask "从首都机场到天安门怎么坐地铁"
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Sequence

from .api import MetroMan
from .models import Route, StationInfo
from .resolver import resolve_station, resolve_trip

# 城市未指明时，按以下顺序尝试自动定位
PREFER_CITIES = ("北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "重庆", "武汉", "西安")


def _pad(text: str, width: int) -> str:
    """按终端显示宽度对齐（中日韩字符算 2 格）。"""
    size = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - size)


# --------------------------------------------------------------------- 输出


def _fmt_route(route: Route, index: int) -> str:
    lines: List[str] = []
    title = route.title or f"方案 {index}"
    tags = "、".join(route.advantages) if route.advantages else ""
    lines.append(f"── {title}" + (f"（{tags}）" if tags else ""))
    lines.append(
        f"   出发 {route.depart_time} → 到达 {route.arrive_time}"
        f" ｜ 全程 {route.duration_text or '-'}｜ 票价 {route.fare or '-'}"
        f" ｜ {route.transfers or '无需换乘'}"
        + (f" ｜ {route.distance_km}公里" if route.distance_km else "")
    )
    for leg in route.legs:
        lines.append(
            f"   ▸ {leg.line_name}"
            + (f"（{leg.direction}）" if leg.direction else "")
            + f"  {leg.from_name} {leg.board_time} 上车"
        )
        if leg.stops:
            path = " → ".join(f"{s.name} {s.time}".strip() for s in leg.stops)
            lines.append(f"       经停：{path}")
        meta = []
        if leg.stop_count is not None:
            meta.append(f"{leg.stop_count}站")
        if leg.distance_km is not None:
            meta.append(f"{leg.distance_km}公里")
        if leg.duration_min is not None:
            meta.append(f"{leg.duration_min}分钟")
        lines.append(
            f"       {leg.to_name} {leg.alight_time} 下车"
            + (f"（{' · '.join(meta)}）" if meta else "")
            + (f"  票价 {leg.fare}" if leg.fare else "")
        )
    return "\n".join(lines)


def _fmt_routes(routes: Sequence[Route], header: str) -> str:
    if not routes:
        return f"{header}\n未找到可用路线。"
    body = "\n\n".join(_fmt_route(route, i + 1) for i, route in enumerate(routes))
    return f"{header}\n\n{body}"


def _fmt_station_info(info: StationInfo) -> str:
    lines = [f"{info.name}站（{info.en}）" if info.en else f"{info.name}站"]
    if info.lines:
        lines.append("途经线路：" + "、".join(info.lines))
    if info.data_version:
        lines.append(f"时刻表版本：{info.data_version}")

    by_direction: Dict[str, List[Any]] = {}
    for entry in info.timetables:
        key = f"{entry.line_name} · {entry.direction}"
        by_direction.setdefault(key, []).append(entry)

    for key, entries in by_direction.items():
        lines.append("")
        lines.append(f"【{key}】")
        for entry in entries:
            last = entry.last
            if entry.day_offset:
                last += "（次日）"
            lines.append(f"   {_pad(entry.day_type, 20)} {entry.first} – {last}")
    return "\n".join(lines)


# --------------------------------------------------------------------- 命令


def cmd_cities(args: argparse.Namespace) -> int:
    mm = MetroMan()
    cities = mm.cities()
    if args.json:
        print(json.dumps([c.to_dict() for c in cities], ensure_ascii=False, indent=2))
        return 0
    for city in cities:
        print(
            f"{city.name:<8} {city.key:<16} {city.en:<16}"
            f" 线路 {city.lines:<4} 车站 {city.stations:<5} 里程 {city.length_km}km"
        )
    return 0


def cmd_stations(args: argparse.Namespace) -> int:
    mm = MetroMan()
    city = mm.city(args.city)
    stations = mm.stations(city.key)
    if args.search:
        matches = resolve_station(args.search, stations, limit=args.limit)
        if args.json:
            print(json.dumps([m.to_dict() for m in matches], ensure_ascii=False, indent=2))
            return 0
        if not matches:
            print(f"未找到与「{args.search}」匹配的车站。")
            return 1
        for match in matches:
            print(f"{match.station.name:<24} {match.station.en:<32} {match.station.slug:<32} {match.score:.2f} {match.reason}")
        return 0

    if args.json:
        print(json.dumps([s.to_dict() for s in stations], ensure_ascii=False, indent=2))
        return 0
    print(f"{city.name}地铁共 {len(stations)} 座车站：")
    for station in stations:
        print(f"{station.name}\t{station.en}\t{station.slug}")
    return 0


def cmd_lines(args: argparse.Namespace) -> int:
    mm = MetroMan()
    city = mm.city(args.city)
    lines = mm.lines(city.key)
    if args.json:
        print(json.dumps([line.to_dict() for line in lines], ensure_ascii=False, indent=2))
        return 0
    print(f"{city.name}地铁共 {len(lines)} 条线路：")
    for line in lines:
        stats = " / ".join(line.stats)
        print(f"{line.name:<14} {line.code:<8} {line.color:<9} {len(line.station_slugs):>3}站  {stats}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    mm = MetroMan()
    city = mm.city(args.city)
    stations = mm.stations(city.key)

    origin = _pick_station(args.from_text, stations, args)
    destination = _pick_station(args.to_text, stations, args)
    if origin is None or destination is None:
        return 1

    routes = mm.plan(
        city.key,
        origin.slug,
        destination.slug,
        mode=args.mode,
        datetime=args.datetime,
        fare=args.fare,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "city": city.to_dict(),
                    "from": origin.to_dict(),
                    "to": destination.to_dict(),
                    "mode": args.mode,
                    "fare": args.fare,
                    "routes": [r.to_dict() for r in routes],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    header = (
        f"{city.name}地铁 · {origin.name} → {destination.name}"
        f"（模式 {args.mode}，计费 {args.fare}）"
    )
    print(_fmt_routes(routes, header))
    return 0


def cmd_station(args: argparse.Namespace) -> int:
    mm = MetroMan()
    city = mm.city(args.city)
    stations = mm.stations(city.key)
    station = _pick_station(args.station_text, stations, args)
    if station is None:
        return 1
    info = mm.station_info(city.key, station.slug)
    if args.json:
        print(json.dumps(info.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(f"{city.name}地铁 · {_fmt_station_info(info)}")
    return 0


def cmd_line(args: argparse.Namespace) -> int:
    mm = MetroMan()
    city = mm.city(args.city)
    lines = mm.lines(city.key)
    from .resolver import resolve_line

    candidates = resolve_line(args.line_text, lines)
    if not candidates:
        print(f"未找到与「{args.line_text}」匹配的线路。")
        return 1
    line = candidates[0]
    info = mm.line_info(city.key, line.slug)
    if args.json:
        print(json.dumps({"line": line.to_dict(), "detail": info}, ensure_ascii=False, indent=2))
        return 0
    print(f"{city.name}地铁 · {line.name}（{line.en}，{line.code}）")
    if line.stats:
        print("  " + " / ".join(line.stats))
    print(f"共 {len(info['stations'])} 站：")
    for index, stop in enumerate(info["stations"], 1):
        print(f"  {index:>2}. {stop['name']}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    mm = MetroMan()
    cities = mm.cities()

    def provider(key: str):
        return mm.stations(key)

    trip = resolve_trip(args.question, cities, provider, prefer_cities=PREFER_CITIES)

    payload: Dict[str, Any] = {"question": args.question, "parsed": trip.to_dict()}

    if trip.city is None:
        payload["error"] = "未能确定城市，请明确说明城市名或换乘车站。"
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["error"])
            print("已识别：", trip.from_text, "->", trip.to_text)
        return 1

    city = trip.city
    stations = mm.stations(city.key)
    origin = trip.origin
    destination = trip.destination

    if origin is None or destination is None:
        missing = []
        if origin is None:
            missing.append("起点")
        if destination is None:
            missing.append("终点")
        payload["error"] = f"未能识别{'、'.join(missing)}车站，请补充具体站名。"
        payload["from_candidates"] = [m.to_dict() for m in trip.from_matches]
        payload["to_candidates"] = [m.to_dict() for m in trip.to_matches]
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{city.name}地铁 · {payload['error']}")
            for label, matches in (("起点", trip.from_matches), ("终点", trip.to_matches)):
                if matches:
                    print(f"{label}候选：")
                    for match in matches:
                        print(f"   {match.station.name}（{match.station.en}） {match.score:.2f} {match.reason}")
        return 1

    routes = mm.plan(
        city.key,
        origin.slug,
        destination.slug,
        mode=trip.intent.mode,
        datetime=trip.intent.datetime,
        fare=trip.intent.fare,
    )

    origin_info = mm.station_info(city.key, origin.slug)
    dest_info = mm.station_info(city.key, destination.slug)

    payload.update(
        {
            "city": city.to_dict(),
            "from": origin.to_dict(),
            "to": destination.to_dict(),
            "mode": trip.intent.mode,
            "datetime": trip.intent.datetime,
            "fare": trip.intent.fare,
            "routes": [r.to_dict() for r in routes],
            "origin_timetable": [t.to_dict() for t in origin_info.timetables],
            "destination_timetable": [t.to_dict() for t in dest_info.timetables],
        }
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"{city.name}地铁 · {origin.name} → {destination.name}")
    print(f"查询方式：{trip.intent.mode}｜ 计费：{trip.intent.fare}｜ 车站匹配：{origin.name} / {destination.name}")
    print()
    print(_fmt_routes(routes, "换乘方案"))
    print()
    print("【出发站首末班车】")
    print(_fmt_station_info(origin_info))
    print()
    print("【到达站首末班车】")
    print(_fmt_station_info(dest_info))
    return 0


def _pick_station(text: str, stations, args):
    matches = resolve_station(text, stations, limit=5)
    if not matches:
        print(f"未找到与「{text}」匹配的车站。", file=sys.stderr)
        return None
    if len(matches) > 1 and matches[1].score >= matches[0].score - 0.02 and not args.pick:
        print(
            f"「{text}」有多个候选车站，请用 --pick 指定序号："
            + "、".join(f"{i + 1}){m.station.name}" for i, m in enumerate(matches[:5])),
            file=sys.stderr,
        )
        return None
    index = (args.pick - 1) if args.pick else 0
    if index < 0 or index >= len(matches):
        print(f"--pick 超出范围（1-{len(matches)}）", file=sys.stderr)
        return None
    return matches[index].station


# --------------------------------------------------------------------- 入口


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="metroman", description="地铁通 metroman.cn 查询工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cities", help="列出全部城市")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cities)

    p = sub.add_parser("stations", help="查询城市车站")
    p.add_argument("city")
    p.add_argument("--search", help="按名称模糊查找车站")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stations)

    p = sub.add_parser("lines", help="查询城市线路")
    p.add_argument("city")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_lines)

    p = sub.add_parser("plan", help="换乘方案查询")
    p.add_argument("city")
    p.add_argument("from_text")
    p.add_argument("to_text")
    p.add_argument("--mode", default="now", choices=["now", "depart", "arrive", "first", "last"])
    p.add_argument("--datetime", help="YYYYMMDDHHMM")
    p.add_argument("--fare", default="ic", choices=["ic", "cash"])
    p.add_argument("--pick", type=int, help="指定候选车站序号")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("station", help="车站详情（首末班车）")
    p.add_argument("city")
    p.add_argument("station_text")
    p.add_argument("--pick", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_station)

    p = sub.add_parser("line", help="线路详情（途经站）")
    p.add_argument("city")
    p.add_argument("line_text")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_line)

    p = sub.add_parser("ask", help="自然语言提问")
    p.add_argument("question")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ask)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover
        print(f"查询失败：{exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
