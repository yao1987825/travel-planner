"""HTML / JSON 解析层（纯标准库）。

metroman.cn 是服务端渲染站点，本模块把页面里的结构化信息抽出来：

* 首页 `#home-data` 里的 JSON  -> 城市列表
* 线网页面内嵌 JSON            -> 线网拓扑数据
* `/planner/{city}` 索引页      -> 城市全部车站（名称 + slug + 检索别名）
* `/planner/{city}/{from}-to-{to}` -> 换乘方案卡片（含逐站时刻）
* `/cities/{city}/stations/{slug}` -> 车站首末班车时刻表
* `/cities/{city}/lines/{slug}` -> 线路途经站
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .htmldom import Node, clean_text, parse_html

JSON_BLOCK_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S
)


# --------------------------------------------------------------------- 工具


def _text(node: Optional[Node]) -> str:
    if node is None:
        return ""
    return clean_text(node.text_content())


def _first(node: Optional[Node], tag: Optional[str] = None,
           cls: Optional[str] = None) -> Optional[Node]:
    if node is None:
        return None
    return node.find(tag=tag, cls=cls)


def _int(text: str) -> Optional[int]:
    match = re.search(r"-?\d+", text or "")
    return int(match.group()) if match else None


def _float(text: str) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else None


def _slug_from_href(href: str) -> str:
    if not href:
        return ""
    match = re.search(r"/stations/([^/?#]+)", href)
    return match.group(1) if match else ""


def json_blocks(page: str) -> List[Any]:
    """提取页面中所有 ``application/json`` 脚本块。"""
    blocks: List[Any] = []
    for raw in JSON_BLOCK_RE.findall(page):
        raw = raw.strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except ValueError:
            continue
    return blocks


# ------------------------------------------------------------------ 城市列表


def parse_home_cities(page: str) -> List[Dict[str, Any]]:
    """解析首页城市列表。"""
    match = re.search(
        r'<script id="home-data" type="application/json">(.*?)</script>', page, re.S
    )
    if not match:
        return []
    payload = json.loads(match.group(1))
    cities = []
    for item in payload.get("cities", []):
        cities.append(
            {
                "id": item.get("id", ""),
                "key": item.get("key", ""),
                "name": item.get("name", ""),
                "en": item.get("secondary", ""),
                "length_km": item.get("length", ""),
                "lines": item.get("lines", ""),
                "stations": item.get("stations", ""),
            }
        )
    return cities


# ---------------------------------------------------------------- 车站索引页


def parse_planner_stations(page: str) -> List[Dict[str, Any]]:
    """解析换乘索引页，得到城市内全部车站及其检索别名。"""
    root = parse_html(page)
    stations: List[Dict[str, Any]] = []
    seen = set()
    for node in root.find_all(cls="planner-station-modal__item"):
        slug = node.get("data-station-slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        key_attr = node.get("data-key")
        aliases = [part.strip() for part in key_attr.split("|") if part.strip()]
        subname = node.find(cls="planner-station-modal__item-subname")
        stations.append(
            {
                "slug": slug,
                "name": node.get("data-station-name"),
                "en": _text(subname),
                "aliases": aliases,
            }
        )
    return stations


# ---------------------------------------------------------------- 线网数据


def parse_network_payload(page: str) -> Optional[Dict[str, Any]]:
    """从线网页面里取出内嵌的线网拓扑 JSON。"""
    for block in json_blocks(page):
        if isinstance(block, dict) and "stations" in block and "lines" in block:
            return block
    return None


# ------------------------------------------------------------------ 换乘结果


def _parse_ride(node: Node) -> Dict[str, Any]:
    board = node.find(cls="planner-result-card__station--board")
    alight = node.find(cls="planner-result-card__station--alight")
    copy = node.find(cls="planner-result-card__ride-copy")

    def _station_time(section: Optional[Node]) -> str:
        if section is None:
            return ""
        strong = section.find(tag="strong")
        return _text(strong) if strong is not None else _text(
            section.find(cls="planner-result-card__time")
        )

    def _station_name(section: Optional[Node]) -> str:
        if section is None:
            return ""
        holder = section.find(cls="planner-result-card__station-name")
        if holder is None:
            return ""
        anchor = holder.find(tag="a")
        return _text(anchor) if anchor is not None else _text(holder)

    def _station_slug(section: Optional[Node]) -> str:
        if section is None:
            return ""
        holder = section.find(cls="planner-result-card__station-name")
        anchor = holder.find(tag="a") if holder is not None else None
        return _slug_from_href(anchor.get("href")) if anchor is not None else ""

    fare_node = board.find(cls="planner-result-card__station-fare") if board else None
    duration_number = node.find(cls="planner-result-card__duration-number")
    duration_unit = node.find(cls="planner-result-card__duration-unit")
    line_name = copy.find(cls="planner-result-card__line-name") if copy else None
    line_dir = copy.find(cls="planner-result-card__line-direction") if copy else None
    line_meta = copy.find(cls="planner-result-card__line-meta") if copy else None

    meta_text = _text(line_meta)
    stop_count = None
    distance_km = None
    if meta_text:
        parts = re.split(r"[·,]", meta_text)
        if parts:
            stop_count = _int(parts[0])
        if len(parts) > 1:
            distance_km = _float(parts[1])

    stops = []
    stop_list = node.find(cls="planner-result-card__stop-list")
    if stop_list is not None:
        for li in stop_list.find_all(tag="li"):
            stops.append(
                {
                    "name": _text(li.find(cls="planner-result-card__stop-name")),
                    "time": _text(li.find(cls="planner-result-card__stop-time")),
                }
            )

    color = ""
    style = node.get("style")
    color_match = re.search(r"--line-color:\s*([^;]+)", style or "")
    if color_match:
        color = color_match.group(1).strip()

    return {
        "line_name": _text(line_name),
        "line_code": "",
        "color": color,
        "direction": _text(line_dir),
        "from_name": _station_name(board),
        "to_name": _station_name(alight),
        "from_slug": _station_slug(board),
        "to_slug": _station_slug(alight),
        "board_time": _station_time(board),
        "alight_time": _station_time(alight),
        "fare": _text(fare_node),
        "duration_min": _int(_text(duration_number)),
        "duration_unit": _text(duration_unit),
        "stop_count": stop_count,
        "distance_km": distance_km,
        "meta": meta_text,
        "stops": stops,
    }


def parse_plan_cards(page: str) -> List[Dict[str, Any]]:
    """解析换乘结果页中的方案卡片（按方案去重）。"""
    root = parse_html(page)
    cards = root.find_all(tag="article", cls="planner-result-card")
    plans: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for card in cards:
        plan_id = card.get("data-plan-id")
        if not plan_id:
            continue
        if plan_id in plans:
            continue

        title = _text(card.find(cls="planner-result-card__title"))
        time_main = card.find(cls="planner-result-card__summary-time-main")
        times = [_text(span) for span in time_main.find_all(tag="span")] if time_main else []
        depart_time = times[0] if times else ""
        arrive_time = times[1] if len(times) > 1 else ""

        duration_text = _text(card.find(cls="planner-result-card__summary-duration"))
        meta_node = card.find(cls="planner-result-card__summary-meta")
        fare = transfers = ""
        distance_km = None
        if meta_node is not None:
            for span in meta_node.children:
                if span.tag != "span":
                    continue
                classes = span.classes
                if any("advantages" in c for c in classes):
                    continue
                value = _text(span)
                if not value:
                    continue
                if "换乘" in value:
                    transfers = value
                elif "公里" in value:
                    distance_km = _float(value)
                elif "元" in value or "¥" in value or "$" in value:
                    fare = value
                elif value in ("直达", "直達"):
                    transfers = value

        advantages = [
            node.get("title")
            for node in card.find_all(cls="planner-result-card__advantage")
            if node.get("title")
        ]

        legs = [
            _parse_ride(ride)
            for ride in card.find_all(tag="section", cls="planner-result-card__ride")
        ]
        connections = [
            _text(node)
            for node in card.find_all(cls="planner-result-card__connection-name")
        ]

        geometry = None
        script = card.find(tag="script", cls="")
        for candidate in card.find_all(tag="script"):
            if (candidate.get("type") or "") == "application/json":
                script = candidate
                break
        if script is not None:
            try:
                geometry = json.loads(script.text_content())
            except ValueError:
                geometry = None

        transfer_count = None
        match = re.search(r"(\d+)", transfers)
        if match:
            transfer_count = int(match.group(1))
        elif transfers in ("直达", "直達"):
            transfer_count = 0

        plan = {
            "id": plan_id,
            "title": title,
            "depart_time": depart_time,
            "arrive_time": arrive_time,
            "duration_text": duration_text,
            "duration_min": _int(duration_text),
            "fare": fare,
            "transfers": transfers,
            "transfer_count": transfer_count,
            "distance_km": distance_km,
            "advantages": advantages,
            "legs": legs,
            "connections": connections,
            "map_geometry": geometry,
        }
        plans[plan_id] = plan
        order.append(plan_id)

    return [plans[pid] for pid in order]


def parse_plan_query(page: str) -> Dict[str, Any]:
    """解析结果页顶部的查询条件（时间、模式、计费方式）。"""
    root = parse_html(page)
    query = root.find(cls="planner-results__query")
    result: Dict[str, Any] = {}
    if query is None:
        return result
    result["text"] = _text(query)
    times = query.find_all(tag="time")
    if times:
        result["date"] = times[0].get("datetime")
        result["text_date"] = _text(times[0])
    if len(times) > 1:
        result["datetime"] = times[1].get("datetime")
        result["text_time"] = _text(times[1])
    result["labels"] = [
        _text(node)
        for node in query.find_all(cls="planner-results__query-part")
    ]
    result["route"] = _text(root.find(tag="h1", cls="planner-results__summary"))
    return result


# ------------------------------------------------------------------ 车站详情


def parse_station_page(page: str) -> Dict[str, Any]:
    """解析车站页：途经线路 + 各方向首末班车。"""
    root = parse_html(page)
    info: Dict[str, Any] = {"lines": [], "timetables": []}

    version_node = root.find(cls="city-timetable-version")
    if version_node is None:
        for candidate in root.find_all():
            if candidate.get("data-timetable-version"):
                version_node = candidate
                break
    if version_node is not None:
        info["data_version"] = version_node.get("data-timetable-version")

    for card in root.find_all(tag="article", cls="city-timetable-card"):
        line_link = card.find(cls="city-timetable-line-link")
        headings = card.find_all(tag="h3")
        line_name = _text(headings[0]) if headings else ""
        line_slug = ""
        if line_link is not None:
            match = re.search(r"/lines/([^/?#]+)", line_link.get("href") or "")
            line_slug = match.group(1) if match else ""
        if line_name:
            info["lines"].append(line_name)

        for direction in card.find_all(cls="city-timetable-direction"):
            direction_name = _text(direction.find(tag="h4"))
            for row in direction.find_all(tag="tr"):
                header = row.find(tag="th")
                day_type = _text(header)
                first_node = row.find(attr="data-first-time")
                last_node = row.find(attr="data-last-time")
                first_time = last_time = ""
                offset = 0
                if first_node is not None:
                    time_node = first_node.find(tag="time")
                    if time_node is not None:
                        first_time = time_node.get("datetime")
                if last_node is not None:
                    time_node = last_node.find(tag="time")
                    if time_node is not None:
                        last_time = time_node.get("datetime")
                        try:
                            offset = int(time_node.get("data-service-day-offset") or 0)
                        except ValueError:
                            offset = 0
                if not first_time and not last_time:
                    continue
                info["timetables"].append(
                    {
                        "line": line_slug,
                        "line_name": line_name,
                        "direction": direction_name,
                        "day_type": day_type,
                        "first": first_time,
                        "last": last_time,
                        "day_offset": offset,
                    }
                )
    return info


# ------------------------------------------------------------------ 线路详情


def parse_line_page(page: str) -> Dict[str, Any]:
    """解析线路页：按顺序的途经车站。"""
    root = parse_html(page)
    stations: List[Dict[str, str]] = []
    for anchor in root.find_all(tag="a"):
        slug = _slug_from_href(anchor.get("href"))
        name = _text(anchor)
        if not slug or not name:
            continue
        if stations and stations[-1]["slug"] == slug:
            continue
        stations.append({"slug": slug, "name": name})

    heading = _text(root.find(tag="h1"))
    return {"title": heading, "stations": stations}
