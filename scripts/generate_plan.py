#!/usr/bin/env python3
"""
travel-planner/scripts/generate_plan.py
========================================
根据用户旅行偏好，自动生成个性化旅游计划（含数据库 SQL 和 API 代码）。

用法:
    python generate_plan.py --profile profile.json [--output ./output]
    python generate_plan.py --interactive

profile.json 格式见 --help 或 references/travel_api.md
"""

import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


# ─── 实时价格数据加载 ──────────────────────────────────────────────────────
def load_live_price_data() -> dict:
    """
    加载 GitHub Actions 定时更新的实时价格数据。
    文件路径：data/latest_prices.json
    如果文件不存在或读取失败，返回空字典（静默降级）。
    """
    # 优先从项目根目录读取（独立运行场景）
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent
    price_file = project_root / "data" / "latest_prices.json"

    # Dify mini_claw 插件场景：skill 目录下的 data/
    skill_root = Path(__file__).parent.parent
    skill_price_file = skill_root / "data" / "latest_prices.json"

    for fp in [price_file, skill_price_file]:
        if fp.exists():
            try:
                with open(fp, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def format_price_context(price_data: dict, city: str) -> str:
    """生成城市实时价格参考文本"""
    if not price_data:
        return ""

    # 找到对应城市的价格数据
    city_data = price_data.get("cities", {}).get(city)
    if not city_data or not city_data.get("items"):
        return ""

    items = city_data["items"]
    lines = [f"\n## {city} · 实时市场价格参考（{price_data.get('updated_at','')[:10]}）\n"]

    # 按类别分组
    by_cat = {}
    for item in items:
        by_cat.setdefault(item.get("category", "其他"), []).append(item)

    cat_icons = {
        "蔬菜": "🥬", "肉禽蛋": "🥩", "鱼虾": "🐟",
        "粮食": "🍚", "食用油": "🫒", "水果": "🍎",
    }
    for cat in ["蔬菜", "肉禽蛋", "鱼虾", "粮食", "食用油", "水果"]:
        if cat in by_cat:
            icon = cat_icons.get(cat, "📦")
            lines.append(f"**{icon} {cat}**：")
            for item in by_cat[cat][:5]:  # 每类最多5项
                name = item.get("name", "")
                price = item.get("price", "—")
                unit = item.get("unit", "")
                p_range = item.get("price_range", "")
                if p_range:
                    lines.append(f"  - {name}：{price} {unit}（市场区间 {p_range}）")
                else:
                    lines.append(f"  - {name}：{price} {unit}")
            lines.append("")

    if city_data.get("note"):
        lines.append(f"> {city_data['note']}")

    return "\n".join(lines)


# ─── 参考数据注册表（references/travel_data.json） ──────────────────────────
# 城市注册表：别名、地铁覆盖、数据来源、核实状态、风格类别词表。
# 新增城市只改数据文件，不用改脚本 —— 规范见 references/data_schema.md。

REFS_DIR = Path(__file__).resolve().parent.parent / "references"
REGISTRY_PATH = REFS_DIR / "travel_data.json"

_KNOWN_CITY_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")


_REGISTRY_CACHE: Optional[dict] = None


def load_registry(refresh: bool = False) -> dict:
    """读取 references/travel_data.json（城市注册表）。读不到返回空 dict。"""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None and not refresh:
        return _REGISTRY_CACHE
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as fh:
            _REGISTRY_CACHE = json.load(fh)
    except (OSError, ValueError):
        _REGISTRY_CACHE = {}
    return _REGISTRY_CACHE


def registry_cities() -> dict:
    return load_registry().get("cities", {}) or {}


def load_image_index() -> dict:
    """读取 references/image_index.json（景点图片来源索引：城市 -> 景点 -> 元信息）。"""
    path = REFS_DIR / "image_index.json"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("cities", {}) or {}
    except (OSError, ValueError):
        return {}


def style_categories() -> dict:
    """风格 -> 类别关键词表（数据驱动；注册表缺失时用内置默认值）。"""
    data = load_registry().get("style_categories")
    if data:
        return data
    return dict(DEFAULT_STYLE_CATEGORIES)


def city_has_metro(city: str) -> bool:
    """该城市是否有地铁（决定行程里写「地铁/打车」还是「公交/打车」）。"""
    info = registry_cities().get(city, {})
    if "metro" in info:
        return bool(info["metro"])
    return False


def category_is_matched(category: str, styles: Optional[list] = None) -> bool:
    """这个类别能不能被任一风格命中（校验器用）。

    命中不了说明类别词表缺关键词 —— 提示补 travel_data.json 的 style_categories。
    """
    if not category:
        return False
    table = style_categories()
    styles = styles if styles is not None else list(table.keys())
    segments = [s.strip() for s in category.split("/") if s.strip()]
    for style in styles:
        for keyword in table.get(style, []):
            if not keyword:
                continue
            if keyword == category:
                return True
            if any(keyword == seg or keyword in seg or seg in keyword
                   for seg in segments):
                return True
    return False


def resolve_city_key(city: str, known: Optional[list] = None) -> Optional[str]:
    """用户输入 -> 注册表里的城市 key（含别名/区域名）。"""
    city = (city or "").strip()
    if not city:
        return None
    registry = registry_cities()
    if city in registry:
        return city
    for key, info in registry.items():
        aliases = [key] + list(info.get("aliases") or [])
        if city in aliases:
            return key
    if known:
        for key in known:
            if key in city or city in key:
                return key
    return None


def _parse_ticket(text: str) -> Optional[float]:
    """门票列 -> 价格；**未知返回 None**（不是 0，避免把「未知」说成「免费」）。

    '免费' / '免费（小火车20)' -> 0；'40（学生20）' -> 40；'150-298' -> 150；
    '5（缆车单程25）' -> 5；'待核实' / '—' -> None（未知）。
    """
    text = (text or "").strip()
    if not text or text in ("待核实", "未知", "—", "-"):
        return None
    if text == "免费":
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    # 「免费（小火车20)」这种：免费出现在数字前，说明景点本身免费，附加项才收费
    if "免费" in text[:m.start()]:
        return 0.0
    return float(m.group(1))


def _parse_duration(text: str) -> float:
    """游玩时长列 -> 小时。'3-4h' -> 3.5；'半天' -> 4；'半天-1天' -> 5；'1-2天'/'全天' -> 8。"""
    text = (text or "").strip()
    if "天" in text:
        if text == "半天":
            return 4.0
        if text.startswith("半天"):
            return 5.0
        return 8.0
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    if not nums:
        return 2.0
    return sum(nums) / len(nums) if len(nums) > 1 else nums[0]


def _star_rating(text: str) -> float:
    """必去指数列（★★★★☆）-> 评分（4.0）。"""
    text = (text or "").strip()
    full = text.count("★")
    half = text.count("☆")
    if full or half:
        return float(full)
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 3.0


def _parse_image(text: str) -> str:
    """图片列 -> 图片 URL。

    支持 `![名称](url)` 与裸 URL；解析不出来返回空串（没有图不影响其它数据）。
    """
    text = (text or "").strip()
    if not text:
        return ""
    m = re.search(r"!\[[^\]]*\]\(([^)\s]+)", text)
    if m:
        return m.group(1)
    if text.startswith("http"):
        return text
    return ""


def _parse_attraction_table(section: str) -> list:
    """解析一个城市章节里的 markdown 表格为景点 dict 列表。"""
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7:
            continue
        if cells[0] in ("景点", "路线") or "门票" in cells[0]:
            continue
        if cells[0].startswith("---"):
            continue
        rows.append(cells)

    attractions = []
    for idx, cells in enumerate(rows, 1):
        name = cells[0]
        ticket = _parse_ticket(cells[1]) if len(cells) > 1 else 0.0
        duration = _parse_duration(cells[2]) if len(cells) > 2 else 2.0
        district = cells[3] if len(cells) > 3 else ""
        category = cells[4] if len(cells) > 4 else "文化"
        stars = cells[6] if len(cells) > 6 else "★★★"
        tips = cells[8] if len(cells) > 8 else ""
        image = _parse_image(cells[9]) if len(cells) > 9 else ""
        rating = _star_rating(stars)
        attractions.append({
            "id": idx,
            "name": name,
            "category": category,
            "district": district,
            "avg_duration_h": duration,
            "ticket_price": ticket,
            "rating": rating,
            "crowd_level": "mid",
            "tags": [],
            "best_time": "",
            "priority": int(round(rating)),
            "tips": tips,
            "description": "",
            "image": image,
        })
    return attractions


def load_attractions_from_md() -> dict:
    """解析 references/cities_attractions.md -> {城市: [景点dict, ...]}。

    额外返回 ``_food_tips``：{城市: {必吃/早餐/午餐/晚餐: 文案}}，
    来自 md 里的 ``**<城市名>必吃：**`` / ``**<城市名>早餐：**`` 这类行。
    """
    md_path = REFS_DIR / "cities_attractions.md"
    if not md_path.exists():
        return {}
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    result = {}
    food_tips = {}
    for section in re.split(r"\n##\s+", text):
        title_line = section.splitlines()[0] if section.splitlines() else ""
        m = re.match(r"^[一二三四五六七八九十]、\s*([^（(]+)", title_line)
        city_name = m.group(1).strip() if m else ""
        if not _KNOWN_CITY_RE.match(city_name):
            continue
        attractions = _parse_attraction_table(section)
        if attractions:
            result[city_name] = attractions
        # 「<城市名>必吃：」/「<城市名>早餐：」这类行 -> 餐饮提示
        for fm in re.finditer(r"\*\*([^*\n]{0,16}?)(必吃|早餐|午餐|晚餐)：\*\*\s*(.+)",
                              section):
            prefix, meal, value = fm.group(1).strip(), fm.group(2), fm.group(3).strip()
            if prefix.endswith(city_name):
                prefix = prefix[: -len(city_name)].strip()
            if prefix:            # 前缀还有别的字，说明不是本城市，忽略
                continue
            food_tips.setdefault(city_name, {})[meal] = value
    if food_tips:
        result["_food_tips"] = food_tips
    return result


# ─── 旅行风格 → 景点类别偏好映射 ─────────────────────────────────────────────
# 首选 references/travel_data.json 的 style_categories（数据驱动，可随数据一起扩展）；
# 这里只是注册表缺失时的兜底默认值。
DEFAULT_STYLE_CATEGORIES = {
    "文化": ["文化", "地标"],
    "美食": [],          # 不过滤，通过 meal tip 体现
    "购物": ["购物"],
    "亲子": ["亲子"],
    "自然": ["自然"],
    "夜景": ["文化", "地标"],
    "历史": ["文化"],
    "艺术": ["文化"],
    "网红打卡": [],
}

# ─── 预算档次 → 日均消费参考 ─────────────────────────────────────────────────
BUDGET_DAILY = {"budget": 300, "mid": 700, "luxury": 1500}

# ─── 体力档次 → 每天最多景点数 ──────────────────────────────────────────────
MOBILITY_MAX_ITEMS = {"high": 4, "mid": 3, "low": 2}

# 游玩时长 >= 该值（小时）视为「整天级」景点：迪士尼、长隆、莽山这类
FULL_DAY_HOURS = 8.0

# ─── 餐食兜底文案（城市级餐饮提示走数据，见 load_food_tips） ─────────────────
DEFAULT_MEAL_TIPS = {
    "早餐": "附近早餐店 / 便利店",
    "午餐": "就近餐厅",
    "晚餐": "当地特色餐厅",
}


class TravelPlanner:
    """根据用户偏好生成旅游计划的核心规划器。"""

    def __init__(self, profile: dict):
        self.profile = profile
        self.city = profile.get("dest_city", "上海")
        self.days = int(profile.get("travel_days", 3))
        self.budget = float(profile.get("budget_cny", 3000))
        self.budget_level = profile.get("budget_level", "mid")
        if self.budget_level not in BUDGET_DAILY:
            self.budget_level = "mid"
        self.styles = profile.get("travel_style", ["文化", "美食"])
        self.group_type = profile.get("group_type", "solo")
        self.mobility = profile.get("mobility", "mid")
        if self.mobility not in MOBILITY_MAX_ITEMS:
            self.mobility = "mid"
        self.depart_date = profile.get("depart_date", str(date.today()))
        try:
            date.fromisoformat(self.depart_date)
        except ValueError:
            self.depart_date = str(date.today())
        self.daily_start = profile.get("options", {}).get("daily_start_time", "09:00")
        self.daily_end = profile.get("options", {}).get("daily_end_time", "21:00")
        self.avoid_crowded = profile.get("options", {}).get("avoid_crowded", False)
        self.prefer_free = profile.get("options", {}).get("prefer_free", False)
        self.include_disney = profile.get("options", {}).get("include_disney", False)
        # 「整天级景点」开关（include_disney 是旧名，保持兼容）
        self.include_full_day = bool(
            profile.get("options", {}).get("include_full_day", self.include_disney)
        )

        # 景点库：优先解析 references/cities_attractions.md 里的多城市数据，
        # 解析不到再退回内置上海库。
        self._md_data = load_attractions_from_md()
        md_attractions = {k: v for k, v in self._md_data.items() if k != "_food_tips"}
        self._food_tips = self._md_data.get("_food_tips", {})
        self._attractions = self._pick_attractions(md_attractions)
        if not self._attractions:
            available = sorted(set(list(md_attractions) + list(registry_cities())))
            print(f"⚠️  暂未内置「{self.city}」的景点库; 可用城市: "
                  f"{'、'.join(available) or '（无）'}")

    def _pick_attractions(self, md_attractions: dict) -> list:
        """按城市选择景点库：精确 -> 注册表别名 -> 包含匹配。

        全部走数据（travel_data.json 的 aliases），加城市不用改代码。
        """
        city = (self.city or "").strip()
        if city in md_attractions:
            return md_attractions[city]
        key = resolve_city_key(city, known=list(md_attractions))
        if key and key in md_attractions:
            return md_attractions[key]
        for name in md_attractions:
            if name in city or city in name:
                return md_attractions[name]
        return []

    # ── 景点评分 ──────────────────────────────────────────────────────────────
    def _score_attraction(self, a: dict) -> float:
        score = a["priority"] * 1.0

        # 风格匹配加分（类别关键词表来自数据，可随数据扩展）
        if self._category_matches(a.get("category", "")):
            score += 2

        # 标签匹配
        for s in self.styles:
            if s in a.get("tags", []):
                score += 1

        # 预算限制（票价未知(None)时不参与惩罚，也不当作免费）
        ticket = a.get("ticket_price")
        if ticket is not None:
            if self.prefer_free and ticket > 0:
                score -= 3
            if self.budget_level == "budget" and ticket > 100:
                score -= 2

        # 人流量偏好
        if self.avoid_crowded and a.get("crowd_level") == "high":
            score -= 2

        # 亲子家庭加分
        if self.group_type == "family" and "亲子" in (a.get("category") or ""):
            score += 2

        return score

    def _category_matches(self, category: str) -> bool:
        """景点类别是否命中用户风格。

        类别写法是「主类/子类」（如 `自然/湖泊`），按整串 + 各分段做**双向子串匹配**，
        关键词表来自 travel_data.json，新增城市/子类无需改代码。
        """
        if not category:
            return False
        table = style_categories()
        segments = [s.strip() for s in category.split("/") if s.strip()]
        for style in self.styles:
            for keyword in table.get(style, []):
                if not keyword:
                    continue
                if keyword == category:
                    return True
                if any(keyword == seg or keyword in seg or seg in keyword
                       for seg in segments):
                    return True
        return False

    # ── 筛选和排序可去景点 ────────────────────────────────────────────────────
    def _select_attractions(self):
        candidates = []
        skipped = []

        for a in self._attractions:
            # 「整天级」景点（时长 >= 8h，如迪士尼/长隆/莽山）单独处理
            if a.get("avg_duration_h", 0) >= FULL_DAY_HOURS and not self.include_full_day:
                if self.days < 2:
                    skipped.append({"name": a["name"], "reason": "需要单独一整天，行程天数不足"})
                else:
                    skipped.append({"name": a["name"],
                                    "reason": "需要单独一整天，如需游览请在选项中开启 include_full_day"})
                continue

            score = self._score_attraction(a)
            candidates.append((score, a))

        candidates.sort(key=lambda x: x[0], reverse=True)
        max_items = MOBILITY_MAX_ITEMS[self.mobility] * self.days
        selected = [a for _, a in candidates[:max_items]]
        not_selected = [a for _, a in candidates[max_items:]]
        for a in not_selected:
            skipped.append({"name": a["name"], "reason": "时间有限，优先安排评分更高的景点"})

        return selected, skipped

    # ── 构建每日行程 ──────────────────────────────────────────────────────────
    def _build_days(self, selected: list) -> list:
        max_per_day = MOBILITY_MAX_ITEMS[self.mobility]
        depart = date.fromisoformat(self.depart_date)
        days_out = []

        # 按区域分组：同区域的景点尽量排在同一天，减少跨区奔波（通用逻辑，不限上海）
        groups: "dict[str, list]" = {}
        for a in selected:
            groups.setdefault(a["district"] or "市区", []).append(a)
        ordered = [a for group in groups.values() for a in group]

        idx = 0
        for d in range(self.days):
            day_attractions = ordered[idx: idx + max_per_day]
            idx += max_per_day
            current_date = depart + timedelta(days=d)

            items = []
            current_time_h = int(self.daily_start.split(":")[0])
            has_metro = city_has_metro(self.city)

            for i, a in enumerate(day_attractions):
                visit_time = f"{current_time_h:02d}:00"
                if i == 0:
                    transport = "步行"
                else:
                    transport = "地铁/打车（约15分钟）" if has_metro else "公交/打车（约15分钟）"
                items.append({
                    "seq": i + 1,
                    "type": "attraction",
                    "name": a["name"],
                    "district": a["district"],
                    "visit_time": visit_time,
                    "duration_h": a["avg_duration_h"],
                    "est_cost": a["ticket_price"],
                    "transport_to": transport,
                    "tips": a.get("tips", ""),
                    "description": a.get("description", ""),
                    "image": a.get("image", ""),
                })
                current_time_h += int(a["avg_duration_h"]) + 1  # +1 交通/休息

            # 餐饮建议：取当天出现最多的区域，避免 set 顺序不稳定
            districts_today = [a["district"] for a in day_attractions]
            main_district = (max(set(districts_today), key=districts_today.count)
                             if districts_today else "市区")

            days_out.append({
                "day_index": d + 1,
                "date": str(current_date),
                "theme": self._day_theme(day_attractions, d),
                "breakfast_tip": self._meal_tip("早餐", main_district),
                "lunch_tip": self._meal_tip("午餐", main_district),
                "dinner_tip": self._meal_tip("晚餐", main_district),
                "hotel_area": main_district,
                "budget_estimate": self._day_budget(day_attractions),
                "items": items
            })

        return days_out

    def _day_theme(self, attractions: list, day_idx: int) -> str:
        if not attractions:
            return f"第{day_idx+1}天自由活动"
        districts = sorted({a["district"] for a in attractions if a["district"]})
        names = "、".join(a["name"] for a in attractions[:2])
        if len(districts) == 1:
            return f"{districts[0]}精华游 · {names}等"
        return f"{'、'.join(districts[:2])}联游 · {names}等"

    def _meal_tip(self, meal: str, district: str) -> str:
        """餐饮提示：全部走数据（md 里的 `<城市名>必吃/早餐/午餐/晚餐` 行），没有就兜底。"""
        tips = self._food_tips.get(self.city) or {}
        if meal in tips:
            return tips[meal]
        if meal == "晚餐" and "必吃" in tips:
            return f"{tips['必吃']}（详见 references/food_guide.md）"
        return DEFAULT_MEAL_TIPS.get(meal, "就近选择")

    def _day_budget(self, attractions: list) -> float:
        # 票价未知的景点不计入（不编数字，也不当作免费）
        ticket = sum(a["ticket_price"] for a in attractions
                     if a.get("ticket_price") is not None)
        meal = BUDGET_DAILY[self.budget_level] * 0.35  # 餐饮占 35%
        transport = 80
        shopping = BUDGET_DAILY[self.budget_level] * 0.2
        return round(ticket + meal + transport + shopping, 2)

    # ── 主入口 ────────────────────────────────────────────────────────────────
    def generate(self) -> dict:
        selected, skipped = self._select_attractions()
        days = self._build_days(selected)
        est_total = sum(d["budget_estimate"] for d in days)
        highlights = [a["name"] for a in selected[:6]]

        # AI 摘要（规则生成）
        style_str = "、".join(self.styles)
        group_map = {"solo": "独自出行", "couple": "情侣出行", "family": "家庭出行", "friends": "朋友出行"}
        summary = (
            f"本次{self.days}日{self.city}行程专为{group_map.get(self.group_type,'出行')}定制，"
            f"聚焦【{style_str}】主题。"
            f"行程覆盖{', '.join(highlights[:4])}等精华地标，"
            f"预估总花费约 ¥{est_total:.0f} 元（含景点门票、餐饮及日常交通）。"
        )
        if skipped:
            skip_names = "、".join(s["name"] for s in skipped[:3])
            summary += f"因时间或偏好因素，{skip_names}等暂未纳入行程。"

        # 加载实时价格数据
        live_price_data = load_live_price_data()
        price_context_md = format_price_context(live_price_data, self.city)

        # 实景图集（来自 attractions 的图片列）+ 图片来源（来自 image_index.json）
        image_meta = load_image_index().get(self.city, {}) or {}
        gallery = []
        for a in selected:
            url = a.get("image", "")
            if not url:
                continue
            meta = image_meta.get(a["name"], {}) or {}
            gallery.append({
                "name": a["name"],
                "district": a.get("district", ""),
                "image": url,
                # 溯源信息：来源站点 + 原始页面（没有索引时留空，不编造）
                "source": meta.get("source", ""),
                "source_url": meta.get("page", ""),
            })

        return {
            "plan_id": None,
            "title": f"{self.city}{self.days}日游 · {style_str}主题",
            "city": self.city,
            "total_days": self.days,
            "budget_input": self.budget,
            "est_total_cost": est_total,
            "ai_summary": summary,
            "highlights": highlights,
            "skipped": skipped,
            "days": days,
            "gallery": gallery,
            "price_context": price_context_md,
            "price_updated_at": live_price_data.get("updated_at", ""),
        }


# ─── 代码生成器 ───────────────────────────────────────────────────────────────

def generate_sql_schema() -> str:
    """读取 references/travel_schema.md 中的 SQL（此处返回简化版 DDL）。"""
    return """-- ====================================
-- 旅游攻略规划系统：数据库建表 SQL
-- ====================================

-- 用户旅行偏好
CREATE TABLE IF NOT EXISTS user_travel_profiles (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id       VARCHAR(64)   NOT NULL UNIQUE,
    dest_city     VARCHAR(50)   NOT NULL,
    origin_city   VARCHAR(50),
    travel_days   TINYINT       NOT NULL,
    depart_date   DATE,
    budget_cny    DECIMAL(10,2),
    budget_level  ENUM('budget','mid','luxury') DEFAULT 'mid',
    travel_style  JSON,
    group_type    ENUM('solo','couple','family','friends') DEFAULT 'solo',
    mobility      ENUM('high','mid','low') DEFAULT 'mid',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 旅行计划主表
CREATE TABLE IF NOT EXISTS travel_plans (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    profile_id    BIGINT NOT NULL,
    title         VARCHAR(200),
    city          VARCHAR(50),
    total_days    TINYINT,
    est_total_cost DECIMAL(10,2),
    highlights    JSON,
    skipped       JSON,
    ai_summary    TEXT,
    status        ENUM('draft','confirmed','completed') DEFAULT 'draft',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 每日行程
CREATE TABLE IF NOT EXISTS itinerary_days (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    plan_id       BIGINT NOT NULL,
    day_index     TINYINT NOT NULL,
    date          DATE,
    theme         VARCHAR(200),
    breakfast_tip VARCHAR(300),
    lunch_tip     VARCHAR(300),
    dinner_tip    VARCHAR(300),
    hotel_area    VARCHAR(100),
    budget_estimate DECIMAL(8,2)
);

-- 每日景点明细
CREATE TABLE IF NOT EXISTS itinerary_items (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    day_id        BIGINT NOT NULL,
    seq           TINYINT NOT NULL,
    name          VARCHAR(200),
    type          ENUM('attraction','meal','transport','free') DEFAULT 'attraction',
    visit_time    TIME,
    duration_h    DECIMAL(3,1),
    est_cost      DECIMAL(8,2),
    transport_to  VARCHAR(300),
    tips          TEXT
);
"""


def generate_fastapi_code(plan: dict) -> str:
    """生成 FastAPI 风格的接口代码骨架。"""
    return f'''# ============================================================
# 旅游攻略规划 API — FastAPI 代码骨架
# 自动生成于计划: {plan["title"]}
# ============================================================

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import date
import json

app = FastAPI(title="旅游攻略规划 API", version="1.0.0")


# ─── 请求/响应模型 ─────────────────────────────────────────

class TravelOptions(BaseModel):
    prefer_free: bool = False
    include_disney: bool = False
    avoid_crowded: bool = False
    daily_start_time: str = "09:00"
    daily_end_time: str = "21:00"

class CreateProfileRequest(BaseModel):
    user_id: str
    nickname: Optional[str] = None
    dest_city: str = Field(..., example="上海")
    origin_city: Optional[str] = None
    depart_date: date
    return_date: Optional[date] = None
    travel_days: int = Field(..., ge=1, le=30)
    budget_cny: float = Field(..., gt=0)
    budget_level: Literal["budget", "mid", "luxury"] = "mid"
    travel_style: List[str] = Field(default=["文化", "美食"])
    group_type: Literal["solo", "couple", "family", "friends"] = "solo"
    mobility: Literal["high", "mid", "low"] = "mid"

class GeneratePlanRequest(BaseModel):
    profile_id: int
    options: TravelOptions = TravelOptions()

class ItineraryItem(BaseModel):
    seq: int
    type: str
    name: str
    visit_time: Optional[str]
    duration_h: float
    est_cost: Optional[float]
    transport_to: str
    tips: str

class ItineraryDay(BaseModel):
    day_index: int
    date: str
    theme: str
    breakfast_tip: str
    lunch_tip: str
    dinner_tip: str
    hotel_area: str
    budget_estimate: float
    items: List[ItineraryItem]

class TravelPlanResponse(BaseModel):
    plan_id: Optional[int]
    title: str
    city: str
    total_days: int
    est_total_cost: float
    ai_summary: str
    highlights: List[str]
    skipped: List[dict]
    days: List[ItineraryDay]


# ─── 路由 ─────────────────────────────────────────────────

@app.post("/travel/profile", summary="创建旅行偏好")
def create_profile(req: CreateProfileRequest):
    # TODO: 持久化到 user_travel_profiles 表
    return {{"code": 0, "message": "success", "data": {{"profile_id": 1}}}}


@app.post("/travel/plan/generate", response_model=TravelPlanResponse, summary="生成旅游计划")
def generate_plan(req: GeneratePlanRequest):
    # TODO: 1. 读取 profile，2. 调用 TravelPlanner，3. 持久化，4. 返回结果
    raise HTTPException(status_code=501, detail="请在此实现规划逻辑")


@app.get("/travel/plan/{{plan_id}}", summary="查询计划详情")
def get_plan(plan_id: int):
    # TODO: 从数据库读取 travel_plans + itinerary_days + itinerary_items
    raise HTTPException(status_code=404, detail="计划不存在")


@app.get("/attractions", summary="获取景点列表")
def list_attractions(
    city: str,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    page: int = 1,
    page_size: int = 20
):
    # TODO: 查询 attractions 表
    return {{"code": 0, "data": {{"total": 0, "items": []}}}}


@app.delete("/travel/plan/{{plan_id}}", summary="删除计划")
def delete_plan(plan_id: int):
    # TODO: 软删除或物理删除
    return {{"code": 0, "message": "已删除"}}
'''


def print_plan(plan: dict):
    """美化打印计划到终端。"""
    print("\n" + "=" * 60)
    print(f"  ✈  {plan['title']}")
    print("=" * 60)
    print(f"📍 目的地  : {plan['city']}")
    print(f"📅 行程天数: {plan['total_days']} 天")
    print(f"💰 预估花费: ¥{plan['est_total_cost']:.0f} 元")
    print(f"\n📝 行程概述:\n   {plan['ai_summary']}")

    # 实时价格参考
    if plan.get("price_context"):
        print("\n" + "=" * 60)
        print("  📊 实时市场价格参考（政府公开数据，每日自动更新）")
        print("=" * 60)
        for line in plan["price_context"].split("\n"):
            if line.startswith("## "):
                continue
            elif line.startswith("**"):
                print(f"  {line}")
            elif line.startswith("  - "):
                print(f"    {line[4:]}")
            elif line.startswith("> "):
                print(f"    {line}  ")
            elif line.strip():
                print(f"  {line}")

    print(f"\n⭐ 行程亮点: {' | '.join(plan['highlights'])}")

    if plan["skipped"]:
        print("\n⏭  因时间/偏好暂跳过:")
        for s in plan["skipped"]:
            print(f"   • {s['name']}：{s['reason']}")

    for day in plan["days"]:
        print(f"\n{'─'*60}")
        print(f"  第 {day['day_index']} 天 ({day['date']}) — {day['theme']}")
        print(f"{'─'*60}")
        print(f"  🍳 早餐: {day['breakfast_tip']}")
        for item in day["items"]:
            cost = item["est_cost"]
            if cost is None:
                cost_str = "票价待核实"
            else:
                cost_str = f"¥{cost:.0f}" if cost > 0 else "免费"
            print(f"  {item['seq']}. [{item['visit_time']}] {item['name']} ({item['duration_h']}h, {cost_str})")
            print(f"     🚇 {item['transport_to']}")
            if item.get("image"):
                print(f"     🖼  {item['image']}")
            if item.get("tips"):
                print(f"     💡 {item['tips']}")
        print(f"  🍜 午餐: {day['lunch_tip']}")
        print(f"  🍽  晚餐: {day['dinner_tip']}")
        print(f"  🏨 住宿区域建议: {day['hotel_area']}")
        print(f"  💴 当日预算: ¥{day['budget_estimate']:.0f}")

    print("\n" + "=" * 60)


def interactive_mode():
    """交互式命令行引导用户输入偏好。"""
    print("\n🌟 欢迎使用旅游攻略规划生成器！\n")

    city = input("目的地城市 [上海]: ").strip() or "上海"
    days = int(input("出行天数 (1-7) [3]: ").strip() or "3")
    budget = float(input("总预算（元）[3000]: ").strip() or "3000")
    budget_level_input = input("预算档次 budget/mid/luxury [mid]: ").strip() or "mid"
    depart_date = input(f"出发日期 YYYY-MM-DD [{date.today()}]: ").strip() or str(date.today())

    print("\n旅行风格（可多选，逗号分隔）: 文化, 美食, 购物, 亲子, 自然, 夜景, 历史, 艺术, 网红打卡")
    styles_input = input("选择风格 [文化,美食]: ").strip() or "文化,美食"
    styles = [s.strip() for s in styles_input.split(",")]

    print("\n出行类型: solo/couple/family/friends")
    group_type = input("出行类型 [solo]: ").strip() or "solo"

    print("\n体力/行动力: high(每天4景点) / mid(3景点) / low(2景点)")
    mobility = input("体力档次 [mid]: ").strip() or "mid"

    include_disney = input("\n是否纳入迪士尼（需单独一天）? y/n [n]: ").strip().lower() == "y"
    avoid_crowded = input("偏好避开人流高峰景点? y/n [n]: ").strip().lower() == "y"
    prefer_free = input("偏好免费景点? y/n [n]: ").strip().lower() == "y"

    profile = {
        "dest_city": city,
        "travel_days": days,
        "budget_cny": budget,
        "budget_level": budget_level_input,
        "depart_date": depart_date,
        "travel_style": styles,
        "group_type": group_type,
        "mobility": mobility,
        "options": {
            "include_disney": include_disney,
            "avoid_crowded": avoid_crowded,
            "prefer_free": prefer_free
        }
    }
    return profile


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="旅游攻略规划代码生成器")
    parser.add_argument("--profile", type=str, help="用户偏好 JSON 文件路径")
    parser.add_argument("--output",  type=str, default="./travel_output", help="输出目录")
    parser.add_argument("--interactive", action="store_true", help="交互式输入")
    parser.add_argument("--sql-only", action="store_true", help="仅输出数据库建表 SQL")
    args = parser.parse_args(argv)

    # 读取或交互式获取 profile
    if args.profile:
        with open(args.profile, "r", encoding="utf-8") as f:
            profile = json.load(f)
    elif args.interactive:
        profile = interactive_mode()
    else:
        # 默认示例
        profile = {
            "dest_city": "上海",
            "travel_days": 3,
            "budget_cny": 3000,
            "budget_level": "mid",
            "depart_date": str(date.today()),
            "travel_style": ["文化", "美食", "购物"],
            "group_type": "couple",
            "mobility": "mid",
            "options": {"include_disney": False, "avoid_crowded": False}
        }
        print("💡 未指定 profile，使用默认示例（上海3日文化美食游）。")
        print("   使用 --interactive 进入交互模式，或 --profile <path> 指定配置文件。\n")

    # 生成计划
    planner = TravelPlanner(profile)
    plan = planner.generate()

    # 打印到终端
    print_plan(plan)

    # 输出文件
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    # 1. 行程 JSON
    plan_file = output / "travel_plan.json"
    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 行程 JSON 已保存: {plan_file}")

    # 说明：图片图集由 generate_gallery.py 统一渲染（travel plan / generate_trip.py 入口），
    # 这里不再重复写 travel_gallery.md —— 否则同一个文件会被写两遍、两种格式并存。

    # 2. 数据库 SQL
    sql_file = output / "travel_schema.sql"
    with open(sql_file, "w", encoding="utf-8") as f:
        f.write(generate_sql_schema())
    print(f"✅ 数据库建表 SQL 已保存: {sql_file}")

    # 3. FastAPI 代码
    api_file = output / "travel_api.py"
    with open(api_file, "w", encoding="utf-8") as f:
        f.write(generate_fastapi_code(plan))
    print(f"✅ FastAPI 代码骨架已保存: {api_file}")

    print(f"\n📁 所有文件已保存至: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
