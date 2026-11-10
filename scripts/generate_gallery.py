#!/usr/bin/env python3
"""Build a Markdown image-and-description gallery for a generated travel plan.

The planner's existing attraction gallery is enriched with descriptions from
itinerary tips. Curated attraction, food, restaurant, and check-in stories can
be added to references/visual_stories.json without changing planning logic.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORIES = ROOT / "references" / "visual_stories.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON 文件 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return data


def _valid_image(url: str) -> bool:
    """图片地址是否可用：只接受 http(s) 或仓库内相对路径。

    挡掉 javascript:/data: 这类协议（渲染出来是破图，还可能有安全风险）。
    """
    if not url:
        return False
    if url.startswith(("http://", "https://", "/", "./", "../")):
        return True
    if "://" in url or url.lower().startswith(("data:", "javascript:", "file:", "vbscript:")):
        return False
    return True


def build_gallery(plan: dict[str, Any], story_data: dict[str, Any]) -> list[dict[str, str]]:
    """Merge selected attraction images with curated visual stories for the city."""
    city = str(plan.get("city") or "").strip()
    descriptions: dict[str, str] = {}
    for day in plan.get("days") or []:
        for item in day.get("items") or []:
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or item.get("tips") or "").strip()
            if name and description:
                descriptions[name] = description

    cards: list[dict[str, str]] = []
    positions: dict[str, int] = {}
    for item in plan.get("gallery") or []:
        name = str(item.get("name") or "").strip()
        image = str(item.get("image") or "").strip()
        if not name or not _valid_image(image):
            continue
        card = {
            "name": name,
            "kind": "景点",
            "district": str(item.get("district") or "").strip(),
            "image": image,
            "description": str(item.get("description") or descriptions.get(name) or "").strip(),
            "source": str(item.get("source") or "").strip(),
            "source_url": str(item.get("source_url") or "").strip(),
        }
        positions[name] = len(cards)
        cards.append(card)

    city_stories = (story_data.get("cities") or {}).get(city) or []
    if not isinstance(city_stories, list):
        raise ValueError(f"visual_stories.json 中 {city!r} 的内容必须是数组")
    for item in city_stories:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        image = str(item.get("image") or "").strip()
        if not name or not _valid_image(image):
            continue
        card = {
            "name": name,
            "kind": str(item.get("kind") or "推荐打卡").strip(),
            "district": str(item.get("district") or "").strip(),
            "image": image,
            "description": str(item.get("description") or "").strip(),
            "source": str(item.get("source") or "").strip(),
            "source_url": str(item.get("source_url") or "").strip(),
        }
        if name in positions:
            # Curated content is more specific than the generic attraction record.
            old = cards[positions[name]]
            for key, value in card.items():
                if value:
                    old[key] = value
        else:
            positions[name] = len(cards)
            cards.append(card)
    return cards


def render_gallery(title: str, cards: list[dict[str, str]]) -> str:
    lines = [
        f"# {title} · 图片与打卡描述",
        "",
        "> 图片用于帮助识别景点、美食与店铺；请尊重图片原作者版权。描述仅作出行参考，价格和营业信息以现场为准。",
        "",
    ]
    if not cards:
        lines.extend(["暂无已配置图片的内容。可在 `references/visual_stories.json` 添加图片与描述。", ""])
        return "\n".join(lines)

    for card in cards:
        name = card["name"]
        label = card.get("kind") or "推荐打卡"
        heading = f"### {name}"
        if card.get("district"):
            heading += f"（{card['district']}）"
        lines.extend([heading, "", f"![{name}]({card['image']})", ""])
        if card.get("description"):
            lines.extend([card["description"], ""])
        else:
            lines.extend([f"*{label} · 暂无补充描述*", ""])
        if card.get("source_url"):
            source = card.get("source") or "图片来源"
            lines.extend([f"图片来源：[ {source} ]({card['source_url']})", ""])
        elif card.get("source"):
            lines.extend([f"图片来源：{card['source']}", ""])
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成旅行图片与描述图集")
    parser.add_argument("--plan", required=True, help="generate_plan.py 输出的 travel_plan.json")
    parser.add_argument("--output", help="图集 Markdown 路径；默认写到计划 JSON 同目录")
    parser.add_argument("--stories", default=str(DEFAULT_STORIES), help="图片与描述数据 JSON")
    args = parser.parse_args(argv)

    try:
        plan_path = Path(args.plan)
        plan = _read_json(plan_path)
        story_data = _read_json(Path(args.stories))
        cards = build_gallery(plan, story_data)
        output_path = Path(args.output) if args.output else plan_path.parent / "travel_gallery.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_gallery(str(plan.get("title") or "旅行行程"), cards), encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    print(f"✅ 图片与描述图集已保存：{output_path}（{len(cards)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
