#!/usr/bin/env python3
"""travel.py —— 出行助手统一命令入口。

一个命令族覆盖全部能力：travel plan 生成行程与图片描述图集；其它子命令
负责公交、地铁、天气、火车票与整段出行查询。

所有子命令都支持 `--help`。
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

USAGE = __doc__

# 子命令 -> (模块名, 转发时是否要把子命令名补回 argv)
DISPATCH = {
    "metro": ("metroman.cli", False),
    "bus": ("bus_query", False),
    "weather": ("weather_query", False),
    "train": ("train_cli", False),
    "journey": ("transit", True),
    # The trip wrapper adds the visual image-and-description gallery after
    # generate_plan writes travel_plan.json.
    "plan": ("generate_trip", False),
}


def _dispatch(module_name: str, argv: list[str]) -> int:
    """把子命令转交给对应脚本的 main()。"""
    import importlib

    module = importlib.import_module(module_name)
    return module.main(argv)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    group = argv[0]
    rest = argv[1:]

    if group in DISPATCH:
        module_name, needs_word = DISPATCH[group]
        if needs_word:
            rest = [group] + rest
        return _dispatch(module_name, rest)

    if group == "price":
        # 只读查询本地价格，绝不触发采集。
        args = ["--query"]
        for token in rest:
            if token in ("-h", "--help"):
                print("用法: travel price [城市]\n  --json  JSON 输出")
                return 0
            if token == "--json":
                args.append("--json")
            elif not token.startswith("-"):
                args += ["--city", token]
        return _dispatch("food_price_scraper", args)

    print(f"未知命令：{group}\n", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
