#!/usr/bin/env python3
"""validate_data.py —— 参考数据校验器。

按 references/data_schema.md 的规范检查景点库/美食手册/城市注册表，
保证「持续加数据」时不会悄悄引入坏数据。

    python3 scripts/validate_data.py                # 全量校验
    python3 scripts/validate_data.py --city 丹东     # 只查某个城市
    python3 scripts/validate_data.py --strict        # 把 warn 也当成失败

退出码：0 = 无 error；1 = 有 error。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(HERE).parent
REFS = ROOT / "references"

sys.path.insert(0, HERE)
import generate_plan  # noqa: E402  (复用同一套解析逻辑，避免两处实现漂移)

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
          "九": 9, "十": 10}
TITLE_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*(.+?)(?:（(.+?)）)?\s*$")
TABLE_COLS = ["景点", "门票(元)", "游玩时长", "区域", "类别", "省钱等级",
              "必去指数", "开放时间", "核心评价", "图片"]
STAR_RE = re.compile(r"^★{1,5}[☆]{0,4}$")
SAVING_RE = re.compile(r"^(⭐|💰)+$")
VALID_TICKET = re.compile(
    r"^(?:待核实|未知|—|-|免费.*"
    r"|约?\d+(?:\.\d+)?(?:\s*[-~～]\s*\d+(?:\.\d+)?)?(?:\s*[（(][^）)]*[）)])?)$"
)

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


# ────────────────────────────────────────────────────────── 景点库

def check_attractions(city_filter: str = "") -> None:
    path = REFS / "cities_attractions.md"
    if not path.exists():
        err(f"缺少 references/cities_attractions.md")
        return
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"\n##\s+", text)
    registry = generate_plan.registry_cities()
    image_index = {}
    idx_path = REFS / "image_index.json"
    if idx_path.exists():
        try:
            image_index = (json.loads(idx_path.read_text(encoding="utf-8"))
                           .get("cities") or {})
        except ValueError:
            err("image_index.json 不是合法 JSON")

    seen_sections = 0
    expected_no = 1
    for section in sections:
        lines = section.splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        m = TITLE_RE.match(title)
        if not m:
            continue
        num_text, city, note = m.group(1), m.group(2).strip(), m.group(3)
        if "跨城市联游建议" in city or city.startswith("跨城市"):
            continue
        seen_sections += 1
        if city_filter and city != city_filter:
            continue

        # 章节序号连续性
        num = CN_NUM.get(num_text)
        if num is None:
            err(f"[{city}] 章节序号无法识别：{title}")
        elif num != expected_no:
            err(f"[{city}] 章节序号不连续：期望 {expected_no}，实际 {num}（{title}）")
        else:
            expected_no += 1

        if not generate_plan._KNOWN_CITY_RE.match(city):
            err(f"[{city}] 城市名必须是 2-4 个汉字")
            continue

        # 必须注册
        if city not in registry:
            err(f"[{city}] 未在 references/travel_data.json 的 cities 里注册")

        # 表格列数（「图片」列可选）
        rows = []
        ncols_ok = (len(TABLE_COLS), len(TABLE_COLS) - 1)
        for line in section.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) not in ncols_ok:
                if cells and cells[0] in TABLE_COLS:
                    err(f"[{city}] 表头列数 {len(cells)}，应为 {len(TABLE_COLS)}"
                        f"（含「图片」列）或 {len(TABLE_COLS) - 1}（不含）")
                continue
            if cells[0] in TABLE_COLS:
                continue
            if cells[0].startswith("---"):
                continue
            rows.append(cells)

        if not rows:
            warn(f"[{city}] 没有景点数据行")

        names = set()
        for cells in rows:
            name, ticket, duration, district, category, saving, stars, opening = cells[:8]
            if name in names:
                err(f"[{city}] 景点名重复：{name}")
            names.add(name)

            # 门票写法
            if not VALID_TICKET.match(ticket):
                err(f"[{city}] {name}：门票列写法非法 → {ticket!r}"
                    f"（合法写法见 data_schema.md §2.3）")
            elif ticket in ("待核实", "未知", "—", "-"):
                warn(f"[{city}] {name}：票价待核实（预算估算会跳过）")
            elif re.search(r"约\s*\d", ticket) and "网购约" not in ticket:
                warn(f"[{city}] {name}：票价是估算值（约XX），核实后请改成确切数字或「待核实」"
                     f" → {ticket}")

            # 必去指数
            if not STAR_RE.match(stars):
                err(f"[{city}] {name}：必去指数格式错 → {stars!r}（应形如 ★★★★☆）")
            # 省钱等级
            if not SAVING_RE.match(saving):
                err(f"[{city}] {name}：省钱等级格式错 → {saving!r}（⭐/💰/💰💰）")
            # 必填项
            if not duration:
                err(f"[{city}] {name}：游玩时长为空")
            if not opening:
                warn(f"[{city}] {name}：开放时间为空")
            if not district:
                warn(f"[{city}] {name}：区域为空")
            # 类别是否能被风格词表命中
            if category and not generate_plan.category_is_matched(category):
                warn(f"[{city}] {name}：类别「{category}」匹配不到任何风格 —— "
                     f"请在 travel_data.json 的 style_categories 补关键词")

            # 图片列
            if len(cells) > 9 and cells[9]:
                url = generate_plan._parse_image(cells[9])
                if not url:
                    err(f"[{city}] {name}：图片列写法非法 → {cells[9][:40]!r}"
                        f"（应为 ![名称](URL)）")
                elif not url.startswith("http"):
                    local = REFS.parent / url if not url.startswith("references/") \
                        else ROOT / url
                    if not local.exists():
                        err(f"[{city}] {name}：图片本地文件不存在 → {url}")
                else:
                    known = (image_index.get(city) or {}).get(name)
                    if known is None:
                        warn(f"[{city}] {name}：图片不在 image_index.json 里"
                             f"（跑 fetch_images.py index 补）")
                    elif known.get("url") and known["url"] != url:
                        warn(f"[{city}] {name}：图片链接与索引不一致"
                             f"（跑 fetch_images.py sync 更新）")

        # 必吃行
        if not re.search(r"\*\*[^*\n]{0,16}?(必吃|早餐|午餐|晚餐)：\*\*", section):
            warn(f"[{city}] 缺少「**<城市名>必吃：**」行（餐饮提示会退化为通用文案）")

    if seen_sections == 0:
        err("cities_attractions.md 里没解析出任何城市章节")


# ────────────────────────────────────────────────────────── 美食手册

def check_food_guide(city_filter: str = "") -> None:
    path = REFS / "food_guide.md"
    if not path.exists():
        err("缺少 references/food_guide.md")
        return
    text = path.read_text(encoding="utf-8")
    registry = generate_plan.registry_cities()
    sections = re.split(r"\n##\s+", text)
    for section in sections:
        lines = section.splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        if not title.endswith("美食"):
            continue
        city = TITLE_RE.match(title[:-2].strip())
        city = city.group(2).strip() if city else title[:-2].strip()
        if city_filter and city != city_filter:
            continue
        if city and city not in registry:
            err(f"[美食] 「{city}」未在 travel_data.json 注册")
        if "**" not in section:
            warn(f"[美食] 「{city}」章节内容偏少")


# ────────────────────────────────────────────────────────── 城市注册表

def check_registry(city_filter: str = "") -> None:
    path = REFS / "travel_data.json"
    if not path.exists():
        err("缺少 references/travel_data.json")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        err(f"travel_data.json 不是合法 JSON：{exc}")
        return

    cities = data.get("cities") or {}
    if not cities:
        err("travel_data.json 的 cities 为空")
        return

    alias_owner = {}
    for city, info in cities.items():
        if city_filter and city != city_filter:
            continue
        if not isinstance(info, dict):
            err(f"[{city}] 注册信息必须是对象")
            continue
        for field in ("attractions_source", "food_source", "verified"):
            if not info.get(field):
                err(f"[{city}] 注册信息缺字段 {field}（来源/核实状态必须登记）")
        if "metro" not in info:
            err(f"[{city}] 注册信息缺字段 metro（是否有地铁）")
        for alias in [city] + list(info.get("aliases") or []):
            if alias in alias_owner and alias_owner[alias] != city:
                err(f"别名冲突：「{alias}」同时属于 {alias_owner[alias]} 和 {city}")
            alias_owner[alias] = city

    # 注册表里的城市是否都有景点数据
    md = generate_plan.load_attractions_from_md()
    md_cities = {k: v for k, v in md.items() if k != "_food_tips"}
    for city in cities:
        if city_filter and city != city_filter:
            continue
        if city not in md_cities:
            err(f"[{city}] 已注册但 cities_attractions.md 里没有对应章节")

    # 风格类别词表
    style = data.get("style_categories") or {}
    if not style:
        warn("travel_data.json 缺 style_categories（风格匹配将退化为内置默认）")


# ────────────────────────────────────────────────────────── 入口

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="参考数据校验器")
    parser.add_argument("--city", help="只校验某个城市")
    parser.add_argument("--strict", action="store_true", help="把 warn 也算失败")
    args = parser.parse_args(argv)

    print("== 校验景点库 cities_attractions.md ==")
    check_attractions(args.city)
    print("== 校验美食手册 food_guide.md ==")
    check_food_guide(args.city)
    print("== 校验城市注册表 travel_data.json ==")
    check_registry(args.city)

    print()
    if warnings:
        print(f"⚠️  {len(warnings)} 条提醒：")
        for msg in warnings:
            print(f"   ! {msg}")
        print()
    if errors:
        print(f"❌ {len(errors)} 条错误：")
        for msg in errors:
            print(f"   ✗ {msg}")
        return 1
    print("✅ 数据校验通过")
    return 1 if (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
