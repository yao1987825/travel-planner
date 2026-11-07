#!/usr/bin/env python3
"""travel.py —— 出行助手统一命令入口。

一个命令族覆盖全部能力，模型只需要记住 `travel`：

    travel metro plan 上海 徐家汇 陆家嘴        地铁换乘
    travel metro station 上海 徐家汇            车站首末班车
    travel metro line 北京 机场线               线路途经站
    travel metro stations 上海 --search 机场    车站检索
    travel metro lines 上海                     线路清单
    travel metro cities                         覆盖城市

    travel bus live 郴州 2路 --to 湘南幼专       公交实时/到站预测
    travel bus station 郴州 五岭广场
    travel bus route 郴州 五岭广场 火车站
    travel bus scan 郴州 --limit 10
    travel bus lines 郴州

    travel train 北京 上海 明天                 12306 火车票
    travel train --transfer 北京 徐州 西安
    travel train --stations 北京

    travel weather live 郴州                   天气（实况/预警/生活指数）
    travel weather forecast 郴州
    travel weather alerts 郴州

    travel journey --from 郴州西 --to 陆家嘴 --date 明天 --weather
                                                   整段出行时间线

    travel plan --profile profile.json --output ./trip   行程规划
    travel price [城市]                                  查本地价格（只读，不采集）
    travel help                                         命令清单

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
#
# transit.py 是「子命令式」argparse（transit.py journey ...），
# travel.py 吃掉了 "journey" 这个词，所以转发时要补回去。
# 其余模块都是扁平参数，直接转发即可。
DISPATCH = {
    "metro": ("metroman.cli", False),
    "bus": ("bus_query", False),
    "weather": ("weather_query", False),
    "train": ("train_cli", False),
    "journey": ("transit", True),
    "plan": ("generate_plan", False),
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
        # 只读查询本地价格，绝不触发采集（采集会覆盖 data/ 下的价格文件）
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
