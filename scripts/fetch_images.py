#!/usr/bin/env python3
"""fetch_images.py —— 景点实景图片检索 / 下载 / GitHub raw 链接。

数据来源用 Bing 图片搜索（返回的是该景点的**真实照片**，来自百度百科/携程/
去哪儿/人民网/新浪等站点），并把**原始页面 URL 一起记下来**做署名溯源。

    python3 scripts/fetch_images.py index --city 郴州     # 检索并建索引（只写链接，不下图）
    python3 scripts/fetch_images.py download --limit 10   # 下载到 images/<城市>/（随仓库提交）
    python3 scripts/fetch_images.py github-url            # 把 md 图片列换成 GitHub raw 链接
    python3 scripts/fetch_images.py sync                  # 把索引链接写回景点表（热链模式）
    python3 scripts/fetch_images.py list --city 郴州      # 查看索引

展示链路（推荐）：
    images/（已提交）---> https://raw.githubusercontent.com/<owner>/<repo>/<branch>/images/...
    raw 国内访问不稳定时，加代理前缀：https://gh-proxy.com/https://raw.githubusercontent.com/...

产物：
    references/image_index.json   图片索引（城市 -> 景点 -> {url, page, title, source, local, raw_url}）
    images/<城市>/xxx.jpg         实景图二进制（**随 git 提交**，用 GitHub raw 展示）

⚠️ 版权：图片版权归原站点/作者所有，脚本保留原始页面 URL 便于溯源；
   是否可商用需自行确认。
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
# 图片下载到仓库顶层的 images/，随 git 提交后用 GitHub raw 链接展示。
IMAGE_DIR = ROOT / "images"

# GitHub raw 链接默认值（可用 --repo / --branch 覆盖）
GITHUB_RAW = "https://raw.githubusercontent.com"
DEFAULT_PROXY = "https://gh-proxy.com/"

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

def download_one(url: str, dest: Path, page: str = "") -> bool:
    """下载图片。防盗链常见，所以换 Referer 重试。"""
    referers = []
    if page:
        m = re.match(r"https?://([^/]+)", page)
        if m:
            referers.append(f"https://{m.group(1)}/")
    referers.append("https://www.bing.com/")
    referers.append("")

    for ref in referers:
        try:
            headers = {
                "User-Agent": UA,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            if ref:
                headers["Referer"] = ref
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
            if len(data) < 3000:            # 太小多半是占位图/错误页
                continue
            if "html" in ctype:           # 返回了网页而不是图
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
        except Exception:
            continue
    return False


def github_raw_url(rel: str, repo: str, branch: str, proxy: str = "") -> str:
    """本地相对路径 -> GitHub raw 链接（可选代理前缀）。

    rel 形如 images/丹东/鸭绿江断桥.jpg
    """
    base = f"{GITHUB_RAW}/{repo}/{branch}/{rel}"
    if proxy:
        return f"{proxy.rstrip('/')}/{base}"
    return base


def find_local_image(city: str, name: str) -> Optional[Path]:
    """找本地已下载的图片（jpg/jpeg/png/webp 任意扩展名）。"""
    safe = re.sub(r"[^\w一-鿿-]+", "_", name)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = IMAGE_DIR / city / f"{safe}{ext}"
        if path.exists():
            return path
    return None


def cmd_github_url(args) -> int:
    """把 md 图片列 + 索引更新为 GitHub raw 链接。

    图片必须已下载到 images/（跑过 download）。链接格式：
      https://raw.githubusercontent.com/<repo>/<branch>/images/<城市>/<景点>.jpg
    国内访问不稳定时可加代理前缀（--proxy https://gh-proxy.com/）。
    """
    repo = args.repo or ""
    if not repo:
        # 从 git remote 自动推断 owner/repo
        try:
            import subprocess

            remote = subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
            m = re.search(r"(?:github\.com[:/])([^/]+/[^/]+?)(?:\.git)?$", remote)
            if m:
                repo = m.group(1)
        except Exception:
            repo = ""
    if not repo:
        print("无法推断 GitHub 仓库，请用 --repo yao1987825/travel-planner", file=sys.stderr)
        return 1
    branch = args.branch or "main"
    proxy = args.proxy

    # 1) 更新 md 图片列
    md_path = REFS / "cities_attractions.md"
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
                local = find_local_image(city, name)
                if local is not None:
                    rel = str(local.relative_to(ROOT)).replace(os.sep, "/")
                    raw = github_raw_url(rel, repo, branch, proxy)
                    img_cell = f"![{name}]({raw})"
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
    print(f"已更新 md 图片列：{changed} 行 -> GitHub raw（repo={repo} branch={branch}）")

    # 2) 更新索引的 raw_url 字段
    index = load_index()
    for cname, items in index.get("cities", {}).items():
        for aname, meta in items.items():
            local = find_local_image(cname, aname)
            if local is not None:
                rel = str(local.relative_to(ROOT)).replace(os.sep, "/")
                meta["raw_url"] = github_raw_url(rel, repo, branch, proxy)
                meta["local"] = rel
    save_index(index)
    return 0


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
            if download_one(meta["url"], dest, meta.get("page", "")):
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


def cmd_manifest(args) -> int:
    """打印「图片应该放在哪」的清单（手动补图时照着放即可）。

    输出格式：<状态> images/<城市>/<文件名>   ← 索引里的 raw_url / 原始链接
    状态：OK=本地已有；MISSING=缺图（原始链接仍可用）；LOCAL_ONLY=本地有但没进索引
    """
    index = load_index()
    cities = index.get("cities", {})
    if args.city:
        cities = {k: v for k, v in cities.items() if k == args.city}
    ok = missing = 0
    for city, items in cities.items():
        if not items:
            continue
        print(f"\n== {city} ==")
        for name, meta in items.items():
            local = find_local_image(city, name)
            rel = meta.get("local") or ""
            if not rel:
                safe = re.sub(r"[^\w一-鿿-]+", "_", name)
                rel = f"images/{city}/{safe}.jpg"
            if local is not None:
                status = "OK      "
                ok += 1
            else:
                status = "MISSING "
                missing += 1
            extra = meta.get("raw_url") or meta.get("url") or ""
            print(f"  {status} {rel}")
            if extra and not local:
                print(f"           备用(原站直链): {extra}")
                if meta.get("page"):
                    print(f"           原始页面: {meta['page']}")
    print(f"\n本地已有 {ok} 张，缺 {missing} 张")
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

    p = sub.add_parser("github-url", help="把 md 图片列换成 GitHub raw 链接（图片需先下载）")
    p.add_argument("--repo", default="", help="GitHub 仓库 owner/repo，默认从 git remote 推断")
    p.add_argument("--branch", default="main", help="分支名，默认 main")
    p.add_argument("--proxy", default=DEFAULT_PROXY,
                   help="raw 链接代理前缀（默认 gh-proxy.com，不需要传空串）")
    p.set_defaults(func=cmd_github_url)

    p = sub.add_parser("manifest", help="打印图片应放位置的清单（手动补图用）")
    p.add_argument("--city", help="只显示某个城市")
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("list", help="查看索引")
    p.add_argument("--city", help="只显示某个城市")
    p.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
