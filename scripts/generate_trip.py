#!/usr/bin/env python3
"""Run the travel planner and automatically write its image gallery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import generate_gallery
import generate_plan


def main(argv: list[str] | None = None) -> int:
    """Generate a plan and its companion image-and-description Markdown gallery."""
    args = list(argv or [])

    # Keep argument handling delegated to generate_plan; inspect only options
    # needed to locate the resulting JSON for the follow-up gallery step.
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

    return generate_gallery.main(["--plan", str(plan_path)])


if __name__ == "__main__":
    raise SystemExit(main())
