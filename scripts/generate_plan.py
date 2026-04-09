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
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# ─── 内置上海景点库 ────────────────────────────────────────────────────────────
SHANGHAI_ATTRACTIONS = [
    {
        "id": 1, "name": "外滩", "category": "文化", "district": "黄浦区",
        "avg_duration_h": 2.0, "ticket_price": 0, "rating": 4.8,
        "crowd_level": "high", "tags": ["必去", "夜景", "免费"],
        "best_time": "傍晚/夜晚", "priority": 10,
        "tips": "建议傍晚 18:30 后前往，灯光秀最美。",
        "description": "上海最具标志性的历史街区，可欣赏浦东天际线。"
    },
    {
        "id": 2, "name": "东方明珠塔", "category": "地标", "district": "浦东新区",
        "avg_duration_h": 2.0, "ticket_price": 189, "rating": 4.5,
        "crowd_level": "high", "tags": ["地标", "观光台"],
        "best_time": "白天/夜晚", "priority": 9,
        "tips": "建议提前网上购票，节假日排队超长。",
        "description": "上海地标性观光塔，登顶可俯瞰全城。"
    },
    {
        "id": 3, "name": "豫园", "category": "文化", "district": "黄浦区",
        "avg_duration_h": 2.5, "ticket_price": 40, "rating": 4.6,
        "crowd_level": "high", "tags": ["历史", "园林", "购物"],
        "best_time": "上午", "priority": 9,
        "tips": "建议上午 9 点开门即入园，人少体验更好。",
        "description": "明代古典园林，周边城隍庙小吃街值得一逛。"
    },
    {
        "id": 4, "name": "田子坊", "category": "文化", "district": "黄浦区",
        "avg_duration_h": 1.5, "ticket_price": 0, "rating": 4.4,
        "crowd_level": "mid", "tags": ["文艺", "购物", "免费"],
        "best_time": "下午", "priority": 8,
        "tips": "弄堂里有很多特色小店和咖啡馆，适合下午闲逛。",
        "description": "石库门弄堂改造的文创街区。"
    },
    {
        "id": 5, "name": "新天地", "category": "购物", "district": "黄浦区",
        "avg_duration_h": 2.0, "ticket_price": 0, "rating": 4.3,
        "crowd_level": "mid", "tags": ["购物", "餐饮", "夜生活"],
        "best_time": "晚上", "priority": 8,
        "tips": "餐厅均价偏高，晚餐预算 150+/人。",
        "description": "融合石库门建筑与现代商业的时尚街区。"
    },
    {
        "id": 6, "name": "上海博物馆", "category": "文化", "district": "黄浦区",
        "avg_duration_h": 3.0, "ticket_price": 0, "rating": 4.7,
        "crowd_level": "mid", "tags": ["历史", "艺术", "免费"],
        "best_time": "上午", "priority": 8,
        "tips": "需提前在官网预约，免费参观。",
        "description": "中国顶级历史艺术博物馆，青铜器、陶瓷馆尤为精彩。"
    },
    {
        "id": 7, "name": "迪士尼乐园", "category": "亲子", "district": "浦东新区",
        "avg_duration_h": 10.0, "ticket_price": 535, "rating": 4.9,
        "crowd_level": "high", "tags": ["亲子", "主题乐园"],
        "best_time": "全天", "priority": 10,
        "tips": "需单独一整天，建议提前网上购票并提前 30 分钟入园。",
        "description": "中国最大的迪士尼主题乐园。",
        "requires_full_day": True
    },
    {
        "id": 8, "name": "朱家角古镇", "category": "文化", "district": "青浦区",
        "avg_duration_h": 4.0, "ticket_price": 0, "rating": 4.5,
        "crowd_level": "mid", "tags": ["古镇", "水乡", "免费"],
        "best_time": "上午", "priority": 7,
        "tips": "距市区约 1 小时，来回交通时间较长，建议半天以上。",
        "description": "上海郊区江南水乡古镇。",
        "far_from_center": True
    },
    {
        "id": 9, "name": "南京路步行街", "category": "购物", "district": "黄浦区",
        "avg_duration_h": 2.0, "ticket_price": 0, "rating": 4.2,
        "crowd_level": "high", "tags": ["购物", "免费"],
        "best_time": "下午/晚上", "priority": 7,
        "tips": "购物为主，餐饮可选择旁边的云南路美食街。",
        "description": "中国最著名的商业步行街之一。"
    },
    {
        "id": 10, "name": "上海科技馆", "category": "亲子", "district": "浦东新区",
        "avg_duration_h": 3.0, "ticket_price": 60, "rating": 4.6,
        "crowd_level": "mid", "tags": ["科技", "亲子"],
        "best_time": "上午", "priority": 7,
        "tips": "适合亲子游，节假日提前预约。",
        "description": "国家级科技类博物馆，展品丰富互动性强。"
    },
    {
        "id": 11, "name": "武康路", "category": "文化", "district": "徐汇区",
        "avg_duration_h": 1.5, "ticket_price": 0, "rating": 4.4,
        "crowd_level": "mid", "tags": ["网红", "建筑", "免费"],
        "best_time": "上午/下午", "priority": 7,
        "tips": "适合拍照打卡，法式梧桐大道，秋天最美。",
        "description": "上海最美历史风貌道路，咖啡馆众多。"
    },
    {
        "id": 12, "name": "上海自然博物馆", "category": "亲子", "district": "静安区",
        "avg_duration_h": 3.0, "ticket_price": 55, "rating": 4.7,
        "crowd_level": "mid", "tags": ["科普", "亲子"],
        "best_time": "上午", "priority": 7,
        "tips": "恐龙化石展非常震撼，需提前预约。",
        "description": "亚洲规模最大的自然博物馆之一。"
    },
    {
        "id": 13, "name": "思南公馆", "category": "文化", "district": "黄浦区",
        "avg_duration_h": 1.5, "ticket_price": 0, "rating": 4.3,
        "crowd_level": "low", "tags": ["文艺", "建筑", "免费"],
        "best_time": "下午", "priority": 6,
        "tips": "安静的历史建筑群，附近有很多精品餐厅。",
        "description": "上海历史最悠久的独栋花园住宅群。"
    },
]

# ─── 旅行风格 → 景点类别偏好映射 ─────────────────────────────────────────────
STYLE_CATEGORY_MAP = {
    "文化": ["文化", "地标"],
    "美食": [],  # 不过滤，通过 meal tip 体现
    "购物": ["购物"],
    "亲子": ["亲子"],
    "自然": ["自然"],
    "夜景": ["文化", "地标"],  # 夜景景点通过 tags 筛选
    "历史": ["文化"],
    "艺术": ["文化"],
    "网红打卡": [],  # 通过 tags 筛选
}

# ─── 预算档次 → 日均消费参考 ─────────────────────────────────────────────────
BUDGET_DAILY = {"budget": 300, "mid": 700, "luxury": 1500}

# ─── 体力档次 → 每天最多景点数 ──────────────────────────────────────────────
MOBILITY_MAX_ITEMS = {"high": 4, "mid": 3, "low": 2}


class TravelPlanner:
    """根据用户偏好生成旅游计划的核心规划器。"""

    def __init__(self, profile: dict):
        self.profile = profile
        self.city = profile.get("dest_city", "上海")
        self.days = int(profile.get("travel_days", 3))
        self.budget = float(profile.get("budget_cny", 3000))
        self.budget_level = profile.get("budget_level", "mid")
        self.styles = profile.get("travel_style", ["文化", "美食"])
        self.group_type = profile.get("group_type", "solo")
        self.mobility = profile.get("mobility", "mid")
        self.depart_date = profile.get("depart_date", str(date.today()))
        self.daily_start = profile.get("options", {}).get("daily_start_time", "09:00")
        self.daily_end = profile.get("options", {}).get("daily_end_time", "21:00")
        self.avoid_crowded = profile.get("options", {}).get("avoid_crowded", False)
        self.prefer_free = profile.get("options", {}).get("prefer_free", False)
        self.include_disney = profile.get("options", {}).get("include_disney", False)

        self._attractions = SHANGHAI_ATTRACTIONS if self.city == "上海" else []

    # ── 景点评分 ──────────────────────────────────────────────────────────────
    def _score_attraction(self, a: dict) -> float:
        score = a["priority"] * 1.0

        # 风格匹配加分
        preferred_cats = set()
        for s in self.styles:
            preferred_cats.update(STYLE_CATEGORY_MAP.get(s, []))
        if a["category"] in preferred_cats:
            score += 2

        # 标签匹配
        for s in self.styles:
            if s in a.get("tags", []):
                score += 1

        # 预算限制
        if self.prefer_free and a["ticket_price"] > 0:
            score -= 3
        if self.budget_level == "budget" and a["ticket_price"] > 100:
            score -= 2

        # 人流量偏好
        if self.avoid_crowded and a["crowd_level"] == "high":
            score -= 2

        # 亲子家庭加分
        if self.group_type == "family" and a["category"] == "亲子":
            score += 2

        return score

    # ── 筛选和排序可去景点 ────────────────────────────────────────────────────
    def _select_attractions(self):
        candidates = []
        skipped = []

        for a in self._attractions:
            # 迪士尼单独处理
            if "迪士尼" in a["name"] and not self.include_disney:
                if self.days < 2:
                    skipped.append({"name": a["name"], "reason": "需要单独一整天，行程天数不足"})
                    continue
                else:
                    skipped.append({"name": a["name"], "reason": "需要单独一整天，如需游览请在选项中开启 include_disney"})
                    continue

            # 远郊景点（天数不足时跳过）
            if a.get("far_from_center") and self.days <= 2:
                skipped.append({"name": a["name"], "reason": f"距市区较远，{self.days}日行程时间紧张，不建议安排"})
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

        # 按区域分组（简化版：前半段黄浦/静安，后半段浦东/其他）
        central = [a for a in selected if a["district"] in ("黄浦区", "静安区", "徐汇区")]
        others  = [a for a in selected if a not in central]
        ordered = central + others

        idx = 0
        for d in range(self.days):
            day_attractions = ordered[idx: idx + max_per_day]
            idx += max_per_day
            current_date = depart + timedelta(days=d)

            items = []
            current_time_h = int(self.daily_start.split(":")[0])

            for i, a in enumerate(day_attractions):
                visit_time = f"{current_time_h:02d}:00"
                transport = "步行" if i == 0 else f"地铁/打车（约15分钟）"
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
                    "description": a.get("description", "")
                })
                current_time_h += int(a["avg_duration_h"]) + 1  # +1 交通/休息

            # 餐饮建议
            districts_today = list({a["district"] for a in day_attractions})
            main_district = districts_today[0] if districts_today else "市区"

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
        districts = list({a["district"] for a in attractions})
        names = "、".join(a["name"] for a in attractions[:2])
        return f"{districts[0]}精华游 · {names}等"

    def _meal_tip(self, meal: str, district: str) -> str:
        tips = {
            "黄浦区": {
                "早餐": "城隍庙南翔馒头店 / 附近便利店",
                "午餐": "老正兴（本帮菜）/ 小南国",
                "晚餐": "外滩附近滨江餐厅，可边吃边看夜景"
            },
            "浦东新区": {
                "早餐": "正大广场附近早餐店",
                "午餐": "国金中心商场美食广场",
                "晚餐": "陆家嘴餐厅（预算较高）"
            },
            "徐汇区": {
                "早餐": "武康路附近咖啡馆",
                "午餐": "衡山路沿线餐厅",
                "晚餐": "天平路美食街"
            },
            "静安区": {
                "早餐": "南京西路早餐店",
                "午餐": "久光百货美食楼",
                "晚餐": "静安寺附近特色餐厅"
            },
        }
        default = {"早餐": "附近酒店早餐或便利店", "午餐": "就近餐厅", "晚餐": "当地特色餐厅"}
        return tips.get(district, default).get(meal, "就近选择")

    def _day_budget(self, attractions: list) -> float:
        ticket = sum(a["ticket_price"] for a in attractions)
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
            "days": days
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
    est_cost: float
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
            cost_str = f"¥{item['est_cost']:.0f}" if item["est_cost"] > 0 else "免费"
            print(f"  {item['seq']}. [{item['visit_time']}] {item['name']} ({item['duration_h']}h, {cost_str})")
            print(f"     🚇 {item['transport_to']}")
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


def main():
    parser = argparse.ArgumentParser(description="旅游攻略规划代码生成器")
    parser.add_argument("--profile", type=str, help="用户偏好 JSON 文件路径")
    parser.add_argument("--output",  type=str, default="./travel_output", help="输出目录")
    parser.add_argument("--interactive", action="store_true", help="交互式输入")
    parser.add_argument("--sql-only", action="store_true", help="仅输出数据库建表 SQL")
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
