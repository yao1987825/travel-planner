#!/usr/bin/env python3
"""train_cli.py —— 12306 火车票查询命令行（纯标准库）。

    train 北京 上海                 # 今天
    train 北京 上海 明天            # 也支持 今天/后天/大后天/+3/2026-11-08
    train -g 北京 上海              # 只看高铁/城际(G/C)
    train -d 北京 上海              # 只看动车(D)
    train --json 北京 上海          # JSON 输出
    train --stations 北京           # 查车站名/电报码
    train --transfer 北京 徐州 西安 # 中转方案
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import train_store  # noqa: E402

TRAIN_TYPES = {
    "g": ("G", "C"),     # 高铁 / 城际
    "d": ("D",),         # 动车
    "z": ("Z", "T", "K"),  # 直达特快快速
}


def render_direct(payload: dict) -> str:
    lines = [
        f"{payload.get('depart_station')} → {payload.get('arrive_station')}"
        f"  {payload.get('trip_date')}"
    ]
    trains = payload.get("has_ticket_trains") or []
    lines.append(
        f"共 {payload.get('train_count', 0)} 趟，"
        f"有票 {payload.get('ticket_count', 0)} 趟，"
        f"售罄 {payload.get('soldout_count', 0)} 趟"
    )
    for item in trains[:20]:
        seats = "、".join(f"{k}{v}" for k, v in (item.get("seats") or {}).items()
                          if v and v != "无")
        lines.append(
            f"  {item.get('station_train_code'):<8} {item.get('start_time')} → "
            f"{item.get('arrive_time')}  在途 {item.get('lishi')}  "
            f"{item.get('train_type','')}  {seats or '有票'}"
        )
    if not trains:
        lines.append("  没有可售的车次")
    lines.append("  ⚠️ 余票随时变，以 12306 官网/App 为准")
    return "\n".join(lines)


def render_transfer(payload: dict) -> str:
    lines = [f"{payload.get('depart_station')} → {payload.get('arrive_station')}"
             f"  {payload.get('trip_date')}  中转方案"]
    routes = payload.get("routes") or []
    lines.append(f"共 {len(routes)} 个方案")
    for item in routes[:15]:
        lines.append(
            f"  {item.get('train_no1','')} {item.get('from_station','')}→"
            f"{item.get('middle_station','')} {item.get('arrive_time1','')} 转 "
            f"{item.get('train_no2','')} →{item.get('to_station','')} "
            f"{item.get('arrive_time2','')}  在途 {item.get('lishi','')}"
        )
    if not routes:
        lines.append("  没查到中转方案")
    lines.append("  ⚠️ 余票随时变，以 12306 官网/App 为准")
    return "\n".join(lines)


def cmd_query(args: argparse.Namespace) -> int:
    payload = train_store.train_query({
        "date": args.date or "",
        "from_station": args.from_station,
        "to_station": args.to_station,
        "train_type": args.train_type or "",
    })
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if payload.get("error"):
            print(f"[train] {payload['error']}", file=sys.stderr)
            return 1
        print(render_direct(payload))
    return 0


def cmd_transfer(args: argparse.Namespace) -> int:
    payload = train_store.train_transfer_query({
        "date": args.date or "",
        "from_station": args.from_station,
        "to_station": args.to_station,
        "middle_station": args.middle_station or "",
    })
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_transfer(payload))
    return 0


def cmd_stations(args: argparse.Namespace) -> int:
    mapping = train_store._load_station_cache()
    keyword = (args.keyword or "").strip()
    if not keyword:
        print(f"共 {len(mapping)} 个车站。用法: train --stations 北京")
        return 0
    hits = [(name, code) for name, code in mapping.items() if keyword in name]
    if not hits:
        print(f"没找到含「{keyword}」的车站")
        return 1
    print(f"含「{keyword}」的车站 {len(hits)} 个：")
    for name, code in hits[:50]:
        print(f"  {name}\t{code}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="train", description="12306 火车票余票查询")
    parser.add_argument("from_station", nargs="?", help="出发站（标准站名，不带'市'）")
    parser.add_argument("to_station", nargs="?", help="到达站")
    parser.add_argument("date", nargs="?", help="日期：今天/明天/后天/+3/2026-11-08")
    parser.add_argument("-g", "--g", dest="train_type", action="store_const",
                        const="高铁", help="只看高铁/城际")
    parser.add_argument("-d", "--d", dest="train_type2", action="store_const",
                        const="动车", help="只看动车")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--stations", metavar="KEYWORD", help="查车站名/电报码")
    parser.add_argument("--transfer", action="store_true", help="查中转方案")
    parser.add_argument("--middle", dest="middle_station", help="中转站（配合 --transfer）")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.train_type2 and not args.train_type:
        args.train_type = args.train_type2

    if args.stations:
        return cmd_stations(args)
    if not args.from_station or not args.to_station:
        print("用法: train <出发站> <到达站> [日期] | train --stations <关键词>",
              file=sys.stderr)
        return 2
    if args.transfer:
        return cmd_transfer(args)
    return cmd_query(args)


if __name__ == "__main__":
    raise SystemExit(main())
