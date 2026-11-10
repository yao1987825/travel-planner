#!/usr/bin/env python3
"""generate_trip.py —— 生成行程 + 图片描述图集（统一入口 travel plan 的实现）。

    python3 scripts/generate_trip.py --profile profile.json --output ./trip

先跑 generate_plan 产出 travel_plan.json，再自动生成 travel_gallery.md。
generate_plan.py 仍保留为「只生成计划」的兼容入口。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import generate_gallery
import generate_plan


def main(argv: list[str] | None = None) -> int:
    """Generate a plan and its companion image-and-description Markdown gallery."""
    # argv=None 时取命令行实参 —— 早期版本写成 list(argv or [])，直接运行脚本时
    # 会把所有参数丢掉（--profile/--output 失效，静默生成默认示例行程）。
    args = list(sys.argv[1:] if argv is None else argv)

    # 解析参数交给 generate_plan，这里只取定位行程 JSON 需要的选项
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", default="./travel_output")
    parser.add_argument("--sql-only", action="store_true")
    parsed, _ = parser.parse_known_args(args)

    result = generate_plan.main(args)
    if result != 0 or parsed.sql_only:
        return result

    plan_path = Path(parsed.output) / "travel_plan.json"
    if not plan_path.is_file():
        print(f"⚠️ 未找到行程 JSON，跳过图片图集：{plan_path}")
        return result

    # 图集失败不应该让整条命令失败 —— 行程本身已经生成好了
    try:
        return generate_gallery.main(["--plan", str(plan_path)])
    except SystemExit as exc:
        print(f"⚠️ 图片图集生成失败（不影响行程）：{exc}", file=sys.stderr)
        return result


if __name__ == "__main__":
    raise SystemExit(main())
