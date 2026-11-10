#!/usr/bin/env python3
"""fetch_images.py —— 景点实景图片索引 / 本地缓存。

数据来源用 Bing 图片搜索（返回的是该景点的**真实照片**，来自百度百科/携程/
去哪儿/人民网/新浪等站点），并把**原始页面 URL 一起记下来**做署名溯源。

    python3 scripts/fetch_images.py index                 # 建立/更新图片索引（只写链接，不下图）
    python3 scripts/fetch_images.py index --city 郴州
    python3 scripts/fetch_images.py download --limit 5     # 下载到 references/images/<城市>/
    python3 scripts/fetch_images.py download --city 郴州 --limit 3
    python3 scripts/fetch_images.py list --city 郴州

产物：
    references/image_index.json   图片索引（城市 -> 景点 -> {url, page, title, source, local}）
    references/images/<城市>/xxx.jpg   本地缓存（默认不入 git，见 .gitignore）

⚠️ 版权：索引里的图片版权归原站点/作者所有，脚本只记录来源页 URL 便于溯源；
   是否可商用需自行确认。仓库不提交图片二进制，默认只提交索引。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = Path(HERE).parent
REFS = ROOT / "references"
INDEX_PATH = REFS / "image_index.json"
IMAGE_DIR = REFS / "images"

sys.path.insert(0, HERE)
import generate_plan  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_IUSC = re.compile(r'class="iusc"[^>]*?\sm="(\{.*?\})"', re.S)

# 搜索时追加的限定词，提高结果相关性
CITY_HINT = {
    "郴州": "郴州", "长沙": "长沙", "衡阳": "衡阳", "广州": "广州",
    "上海": "上海", "清远": "清远", "丹东": "丹东",
}


# ────────────────────────────────────────────────────────── 搜索

def bing_images(query: str, limit: int = 24, timeout: int = 15,
                retries: int = 2) -> List[Dict[str, str]]:
    """Bing 图片搜索 -> [{url, title, page, thumb}]。"""
    url = ("https://www.bing.com/images/async?q=" + urllib.parse.quote(query) +
           f"&first=1&count={limit}&safe=off")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.bing.com/images",
    })
    page = ""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                page = html.unescape(resp.read().decode("utf-8", "replace"))
            break
        except Exception:
            if attempt >= retries:
                return []
            time.sleep(1.5 * (attempt + 1))
    out = []
    for m in _IUSC.finditer(page):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        if not d.get("murl"):
            continue
        out.append({
            "url": d["murl"],
            "thumb": d.get("turl", ""),
            "title": d.get("t", ""),
            "page": d.get("purl", ""),
        })
    return out


def score_hit(result: Dict[str, str], name: str, city: str) -> int:
    """标题相关性打分。

    **硬门槛**：标题/页面里必须出现景点名本身（去掉括号修饰后的核心名，
    或其前 3 个字），否则直接判不相关 —— 只匹配到城市名是不够的
    （否则「阳山秤架干坑古树群」会被配到「阳山某公园」的新闻图）。
    """
    title = result.get("title", "")
    page = result.get("page", "")
    hay = f"{title} {page}"
    core = re.sub(r"[（(].*?[）)]", "", name).strip()

    # 硬门槛：核心名或它的前 3 个字必须出现
    hit = False
    if core and core in hay:
        hit = True
    elif len(core) >= 4 and core[:3] in hay:
        hit = True
    elif len(core) >= 3 and core in hay:
        hit = True
    if not hit:
        return -100

    score = 10
    if name and name in hay:
        score += 5
    if city and city in hay:
        score += 3
    if re.search(r"菜谱|做法|食谱|游戏|动漫|小说|漫画|房价|二手房", hay):
        score -= 20
    return score


def pick_image(results: List[Dict[str, str]], name: str, city: str) -> Optional[Dict[str, str]]:
    """从搜索结果里挑最相关的一条。"""
    scored = [(score_hit(r, name, city), r) for r in results]
    scored = [(s, r) for s, r in scored if s > 0]
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    best = dict(scored[0][1])
    best["score"] = scored[0][0]
    return best


# ────────────────────────────────────────────────────────── 索引

def load_index() -> Dict[str, Any]:
    if INDEX_PATH.exists():
        try:
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"version": "1.0", "updated": "", "cities": {}}


def save_index(index: Dict[str, Any]) -> None:
    index["updated"] = time.strftime("%Y-%m-%d")
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  索引已写入: {INDEX_PATH}")


def cmd_index(args) -> int:
    md = generate_plan.load_attractions_from_md()
    cities = {k: v for k, v in md.items() if k != "_food_tips"}
    if args.city:
        cities = {k: v for k, v in cities.items() if k == args.city}
        if not cities:
            print(f"没有「{args.city}」的景点数据", file=sys.stderr)
            return 1

    index = load_index()
    cities_idx = index.setdefault("cities", {})
    total = ok = 0
    for city, items in cities.items():
        bucket = cities_idx.setdefault(city, {})
        hint = CITY_HINT.get(city, city)
        for a in items:
            name = a["name"]
            if not args.force and name in bucket:
                continue
            total += 1
            query = f"{hint} {name}"
            try:
                results = bing_images(query)
            except Exception as exc:
                print(f"  ! {city}/{name} 搜索失败: {exc}")
                time.sleep(args.delay)
                continue
            hit = pick_image(results, name, hint)
            if hit:
                bucket[name] = {
                    "url": hit["url"],
                    "page": hit.get("page", ""),
                    "title": hit.get("title", ""),
                    "source": source_of(hit.get("page", "")),
                    "query": query,
                    "local": "",
                }
                ok += 1
                print(f"  ✓ {city}/{name}  ← {hit['title'][:32]}", flush=True)
            else:
                print(f"  - {city}/{name}  无相关结果", flush=True)
            time.sleep(args.delay)
        save_index(index)          # 每城存一次，中断也不丢进度
    print(f"索引完成：{ok}/{total} 个景点配到实景图")
    return 0


def source_of(page_url: str) -> str:
    """从原始页面 URL 推断来源站点。"""
    if not page_url:
        return ""
    m = re.match(r"https?://([^/]+)", page_url)
    host = m.group(1) if m else page_url
    host = host.replace("www.", "")
    known = {
        "baike.baidu.com": "百度百科", "bkimg.cdn.bcebos.com": "百度百科",
        "you.ctrip.com": "携程", "youimg1.c-ctrip.com": "携程",
        "qunar.com": "去哪儿", "qunarzz.com": "去哪儿",
        "mafengwo.cn": "马蜂窝", "mafengwo.net": "马蜂窝",
        "people.com.cn": "人民网", "xinhuanet.com": "新华网",
        "sina.com.cn": "新浪", "sinaimg.cn": "新浪",
        "163.com": "网易", "qq.com": "腾讯", "sohu.com": "搜狐",
        "douyin.com": "抖音", "xiaohongshu.com": "小红书",
        "hnlyxh.org": "湖南省旅游协会", "gov.cn": "政府网站",
    }
    for key, name in known.items():
        if key in host:
            return name
    return host


# ────────────────────────────────────────────────────────── 下载

def download_one(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Referer": "https://www.bing.com/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = resp.read()
        if len(data) < 3000:            # 太小多半是占位图
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def cmd_download(args) -> int:
    index = load_index()
    cities = index.get("cities", {})
    if args.city:
        cities = {k: v for k, v in cities.items() if k == args.city}
    saved = 0
    for city, items in cities.items():
        for name, meta in list(items.items())[: args.limit]:
            if not meta.get("url"):
                continue
            safe = re.sub(r"[^\w一-鿿-]+", "_", name)
            ext = os.path.splitext(urllib.parse.urlparse(meta["url"]).path)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            dest = IMAGE_DIR / city / f"{safe}{ext}"
            if dest.exists() and not args.force:
                meta["local"] = str(dest.relative_to(ROOT))
                saved += 1
                continue
            if download_one(meta["url"], dest):
                meta["local"] = str(dest.relative_to(ROOT))
                saved += 1
                print(f"  ✓ {city}/{name} -> {meta['local']}")
            else:
                print(f"  ! {city}/{name} 下载失败")
            time.sleep(args.delay)
    save_index(index)
    print(f"本地缓存完成：{saved} 张 -> {IMAGE_DIR}")
    return 0


def cmd_sync(args) -> int:
    """把索引里的图片链接写回 references/cities_attractions.md 的「图片」列。

    只改表格最后一列，其余内容原样保留；已有图片链接会被更新为最新索引。
    """
    md_path = REFS / "cities_attractions.md"
    if not md_path.exists():
        print("找不到 cities_attractions.md", file=sys.stderr)
        return 1
    index = load_index().get("cities", {})
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out = []
    city = ""
    changed = 0
    for line in lines:
        m = re.match(r"^##\s+(?:[一二三四五六七八九十]+、)?([^\s（(]+)", line)
        if m:
            city = m.group(1).strip()
        stripped = line.strip()
        if stripped.startswith("|") and city and "---" not in stripped:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells and cells[0] not in ("景点", "路线") and "门票" not in cells[0]:
                name = cells[0]
                meta = (index.get(city) or {}).get(name) or {}
                url = meta.get("url", "")
                if url:
                    img_cell = f"![{name}]({url})"
                    if len(cells) >= 10 and cells[9].startswith("!["):
                        if cells[9] != img_cell:
                            cells[9] = img_cell
                            changed += 1
                    else:
                        cells.append(img_cell)
                        changed += 1
                    line = "| " + " | ".join(cells) + " |"
        out.append(line)
    md_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"已同步图片列：{changed} 行 -> {md_path}")
    return 0


def cmd_list(args) -> int:
    index = load_index()
    cities = index.get("cities", {})
    if args.city:
        cities = {k: v for k, v in cities.items() if k == args.city}
    for city, items in cities.items():
        print(f"\n{city}（{len(items)}）")
        for name, meta in items.items():
            local = meta.get("local") or "-"
            print(f"  {name:<18} {meta.get('source','-'):<10} {local}")
            print(f"      {meta.get('url','')[:100]}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="景点实景图片索引/缓存")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="搜索并更新图片索引（只写链接）")
    p.add_argument("--city", help="只处理某个城市")
    p.add_argument("--force", action="store_true", help="已存在的也重新搜")
    p.add_argument("--delay", type=float, default=1.2, help="每次搜索间隔秒")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("download", help="把索引里的图片下载到 references/images/")
    p.add_argument("--city", help="只处理某个城市")
    p.add_argument("--limit", type=int, default=10, help="每城最多下载几张")
    p.add_argument("--force", action="store_true", help="已存在也重新下载")
    p.add_argument("--delay", type=float, default=0.8, help="每次下载间隔秒")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("sync", help="把索引里的图片链接写回 cities_attractions.md")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("list", help="查看索引")
    p.add_argument("--city", help="只显示某个城市")
    p.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
