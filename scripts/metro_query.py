#!/usr/bin/env python3
"""metro_query.py —— 地铁查询统一入口（纯标准库，零第三方依赖）。

    python3 metro_query.py <子命令> [参数...]

子命令:
    cities                       列出全部城市
    stations <城市> [--search 关键字]   城市车站列表 / 按名字模糊找站
    lines <城市>                 城市线路列表
    plan <城市> <起点> <终点>     换乘方案(含逐站时刻、票价、换乘次数)
    station <城市> <车站>         车站详情(各方向首末班车)
    line <城市> <线路>            线路详情(途经站顺序)

通用选项:
    --mode now|depart|arrive|first|last   查询时刻类型(默认 now)
    --datetime YYYYMMDDHHMM               指定时刻(非 now 时必填)
    --fare ic|cash                        交通卡 / 现金
    --pick N                              车站有多个候选时指定序号
    --json                                输出结构化 JSON
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from metroman.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
