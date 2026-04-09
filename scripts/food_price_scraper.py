#!/usr/bin/env python3
"""
食品价格爬虫 - travel-planner 配套工具
数据来源：
  1. 上海发改委每日主副食品价格 (Excel)
  2. 中国价格信息网 36城蔬菜/肉禽蛋价格 (HTML)
  3. 上海发改委价格监管动态页面 (HTML 摘要)

输出：
  data/latest_prices.json   - 各城市最新价格
  data/price_history.json   - 历史价格归档
  data/latest_summary.md     - 人类可读的摘要报告
"""

import os
import re
import json
import datetime
import urllib.request
import urllib.error
from typing import Optional

# ============================================================
# 配置
# ============================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # 项目根目录（scripts 的上一层）
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.json")
SUMMARY_FILE = os.path.join(DATA_DIR, "latest_summary.md")
TODAY = datetime.date.today().isoformat()


# ============================================================
# 工具函数
# ============================================================

def fetch(url: str, timeout: int = 15) -> Optional[str]:
    """抓取页面内容，失败返回 None"""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # 处理重定向编码
            charset = "utf-8"
            content_type = resp.headers.get("Content-Type", "")
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].strip()
            data = resp.read()
            return data.decode(charset, errors="replace")
    except Exception as e:
        print(f"  [WARN] fetch failed: {url} -> {e}")
        return None


def save_json(filepath: str, data):
    """安全写入 JSON 文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(filepath: str, default=None):
    """安全读取 JSON 文件，文件不存在时返回 default"""
    if not os.path.exists(filepath):
        return default or {}
    try:
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default or {}


def compute_change(current: float, previous: float) -> str:
    """计算环比变化，返回字符串如 '+2.5%' 或 '-1.2%' 或 '持平'"""
    if previous == 0 or previous == "-":
        return "—"
    try:
        diff = (float(current) - float(previous)) / float(previous) * 100
        if abs(diff) < 0.05:
            return "持平"
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff:.1f}%"
    except (ValueError, TypeError):
        return "—"


# ============================================================
# 数据源 1：上海发改委每日价格（Excel）
# ============================================================

def get_shanghai_latest_page() -> Optional[str]:
    """获取上海发改委价格监管动态首页，返回最新价格页URL"""
    url = "https://fgw.sh.gov.cn/fgw_jgjgdt/index.html"
    html = fetch(url)
    if not html:
        return None
    # 匹配最新一条价格信息表链接
    # 格式: /fgw_jgjgdt/YYYYMMDD/hash.html
    pattern = r'href="(/fgw_jgjgdt/\d{8}/[a-f0-9]+\.html)"[^>]*>[^<]*上海市主要主副食品品种价格信息表[^<]*</a>'
    matches = re.findall(pattern, html)
    if matches:
        return "https://fgw.sh.gov.cn" + matches[0]
    return None


def parse_shanghai_price_page(html: str) -> dict:
    """
    解析上海价格页面，提取摘要中的关键价格 + 下载 Excel
    返回结构化数据
    """
    result = {
        "city": "上海",
        "date": TODAY,
        "source": "上海市发展和改革委员会 (fgw.sh.gov.cn)",
        "items": [],
        "note": "",
    }

    # 1. 从页面摘要提取关键价格
    # 典型格式："青菜2.65元/500克和鸡毛菜3.85元/500克"
    vege_pattern = r"青菜[^和，,]*?(\d+\.?\d*)元/500克[^和，,]*?鸡毛菜[^和，,]*?(\d+\.?\d*)元/500克"
    vege_match = re.search(vege_pattern, html)
    if vege_match:
        result["items"].append({
            "category": "蔬菜", "name": "青菜", "price": vege_match.group(1),
            "unit": "元/500克", "trend": ""
        })
        result["items"].append({
            "category": "蔬菜", "name": "鸡毛菜", "price": vege_match.group(2),
            "unit": "元/500克", "trend": ""
        })

    # 猪肉: "猪精瘦肉价格17.67元/500克"
    pork_match = re.search(r"猪精瘦肉价格(\d+\.?\d*)元/500克", html)
    if pork_match:
        result["items"].append({
            "category": "肉禽蛋", "name": "猪精瘦肉", "price": pork_match.group(1),
            "unit": "元/500克", "trend": ""
        })

    # 鸡蛋: "鸡蛋价格4.84元/500克"
    egg_match = re.search(r"鸡蛋价格(\d+\.?\d*)元/500克", html)
    if egg_match:
        result["items"].append({
            "category": "肉禽蛋", "name": "鸡蛋", "price": egg_match.group(1),
            "unit": "元/500克", "trend": ""
        })

    # 提取备注信息（环比变化说明），清理 HTML 标签
    note_match = re.search(r"据监测，(.+?)(?:\s*相关附件|$)", html, re.DOTALL)
    if note_match:
        note = note_match.group(1).strip()
        note = re.sub(r'<[^>]+>', '', note)  # 移除 HTML 标签
        note = re.sub(r'\s+', ' ', note).strip()
        result["note"] = note[:200]

    # 2. 下载 Excel 附件获取完整数据
    xls_links = re.findall(r'href="(/cmsres/[^"\']+\.xls)"', html)
    if xls_links:
        xls_url = "https://fgw.sh.gov.cn" + xls_links[0]
        xls_data = fetch_xls(xls_url)
        if xls_data:
            items = parse_shanghai_xls(xls_data)
            # 合并，避免重复
            existing_names = {it["name"] for it in result["items"]}
            for it in items:
                if it["name"] not in existing_names:
                    result["items"].append(it)
                    existing_names.add(it["name"])

    return result


def fetch_xls(url: str) -> Optional[bytes]:
    """下载 Excel 文件"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except Exception as e:
        print(f"  [WARN] xls download failed: {e}")
        return None


def parse_shanghai_xls(data: bytes) -> list:
    """
    解析上海 Excel 文件，提取各品类代表性商品均价
    使用 xlrd 直接解析（不依赖 pandas）
    """
    try:
        import xlrd
    except ImportError:
        print("  [WARN] xlrd not installed, skip XLS parsing")
        return []

    items = []
    try:
        import io
        wb = xlrd.open_workbook(file_contents=data)
        sh = wb.sheet_by_index(0)

        # 读取标题行（第3行=index 3）获取列名
        # 格式: [区, 菜市场名, 粳米, 粳米, 面粉, ...]
        if sh.nrows < 10:
            return []

        # 找品种行（row index 4）
        variety_row = sh.row_values(4)  # 品种名称

        # 找单位行（row index 6）
        unit_row = sh.row_values(6) if sh.nrows > 6 else [""] * sh.ncols

        # 提取价格数据行（从 row 7 开始，跳过标题区）
        # 数据格式: [区名, 菜市场名, 价格1, 价格2, ...]
        # 关键列（基于 variety_row）：
        #  蔬菜: 青菜(col ~27), 鸡毛菜(col ~28), 黄瓜, 西红柿, 土豆
        #  肉禽蛋: 猪精瘦肉, 鸡蛋
        #  鱼虾: 带鱼, 黄鱼, 草鱼
        key_items = ["青菜", "鸡毛菜", "黄瓜", "西红柿", "土豆",
                     "猪精瘦肉", "肋条肉", "鸡蛋",
                     "带鱼", "黄鱼", "草鱼", "鲫鱼", "基围虾",
                     "粳米", "花生油(鲁花)", "大豆油"]

        col_indices = {}
        for col_idx, name in enumerate(variety_row):
            for key in key_items:
                if key in str(name):
                    if key not in col_indices:
                        col_indices[key] = col_idx

        # 收集各商品所有市场价格
        item_prices = {k: [] for k in col_indices}
        for row_idx in range(7, sh.nrows):
            row = sh.row_values(row_idx)
            if not row or not str(row[0]).strip():
                continue
            for item_name, col_idx in col_indices.items():
                if col_idx < len(row):
                    val = row[col_idx]
                    try:
                        p = float(val)
                        item_prices[item_name].append(p)
                    except (ValueError, TypeError):
                        pass

        # 计算各商品均价
        category_map = {
            "青菜": "蔬菜", "鸡毛菜": "蔬菜", "黄瓜": "蔬菜",
            "西红柿": "蔬菜", "土豆": "蔬菜",
            "猪精瘦肉": "肉禽蛋", "肋条肉": "肉禽蛋", "鸡蛋": "肉禽蛋",
            "带鱼": "鱼虾", "黄鱼": "鱼虾", "草鱼": "鱼虾",
            "鲫鱼": "鱼虾", "基围虾": "鱼虾",
            "粳米": "粮食", "花生油(鲁花)": "食用油", "大豆油": "食用油",
        }
        unit_map = {
            "青菜": "元/500克", "鸡毛菜": "元/500克", "黄瓜": "元/500克",
            "西红柿": "元/500克", "土豆": "元/500克",
            "猪精瘦肉": "元/500克", "肋条肉": "元/500克", "鸡蛋": "元/500克",
            "带鱼": "元/500克", "黄鱼": "元/500克", "草鱼": "元/500克",
            "鲫鱼": "元/500克", "基围虾": "元/500克",
            "粳米": "元/500克", "花生油(鲁花)": "元/5升", "大豆油": "元/5升",
        }

        for item_name, prices in item_prices.items():
            if prices:
                avg = sum(prices) / len(prices)
                items.append({
                    "category": category_map.get(item_name, "其他"),
                    "name": item_name,
                    "price": round(avg, 2),
                    "unit": unit_map.get(item_name, "元/500克"),
                    "sample_count": len(prices),
                    "price_range": f"{min(prices):.1f}~{max(prices):.1f}",
                    "trend": "",
                })

    except Exception as e:
        print(f"  [WARN] XLS parse error: {e}")

    return items


# ============================================================
# 数据源 2：中国价格信息网 36城蔬菜/肉禽蛋
# ============================================================

def get_36city_price_pages() -> list:
    """获取 36 城价格数据页面 URL 列表"""
    url = "https://jgjc.ndrc.gov.cn/sp/index.jhtml"
    html = fetch(url)
    if not html:
        return []

    pages = []
    # 从 jgjc.ndrc.gov.cn 找指向 chinaprice.cn 的链接
    # 典型: http://www.chinaprice.cn/spscdt/59683.jhtml
    links = re.findall(r'href="(http://www\.chinaprice\.cn/spscdt/\d+\.jhtml)"', html)
    seen = set()
    for link in links:
        page_id = re.search(r'/(\d+)\.jhtml', link)
        if page_id and page_id.group(1) not in seen:
            seen.add(page_id.group(1))
            pages.append(link)
    return pages[:5]  # 最多5条


def parse_36city_page(url: str) -> list:
    """
    解析 36 城价格页面
    注意：这些页面通常需要 JS 渲染，直接抓取可能只返回骨架
    尝试提取页面中的价格文本
    """
    html = fetch(url)
    if not html:
        return []

    items = []
    # 提取价格文本中的数字模式
    # 格式：城市名  价格  单位
    price_text = re.findall(
        r'([\u4e00-\u9fa5]{2,6})\s+(\d+\.?\d*)\s*(元/500克|元/公斤|元/吨|元)',
        html
    )
    for city, price, unit in price_text:
        if city not in ["价格", "单位", "平均", "最高", "最低", "品种"]:
            items.append({
                "city_raw": city,
                "price": price,
                "unit": unit,
                "source_url": url,
            })
    return items


# ============================================================
# 数据源 3：本地政府网站（郴州/长沙/衡阳）
# ============================================================

def try_fetch_city_price(city_name: str, url: str) -> dict:
    """尝试从城市政府网站获取价格数据"""
    html = fetch(url)
    if not html:
        return {}

    result = {
        "city": city_name,
        "date": TODAY,
        "source": url,
        "items": [],
        "note": "",
    }

    # 提取价格数字（通用模式）
    prices = re.findall(
        r'([\u4e00-\u9fa5]{2,6}(?:米|粉|面|菜|肉|蛋|鸡|鱼|虾|豆腐))\s*[:：]?\s*(\d+\.?\d*)\s*(元/斤|元/500克|元/公斤|元)',
        html
    )
    for name, price, unit in prices:
        result["items"].append({
            "category": "民生食品",
            "name": name,
            "price": price,
            "unit": unit,
            "trend": "",
        })

    if result["items"]:
        return result
    return {}


# ============================================================
# 主程序：采集所有数据
# ============================================================

def collect_all() -> dict:
    """采集所有城市的价格数据"""
    all_data = {
        "updated_at": datetime.datetime.now().isoformat(),
        "cities": {},
    }

    # 1. 上海（主要数据源）
    print("[1/3] 抓取上海发改委价格数据...")
    shanghai_page_url = get_shanghai_latest_page()
    if shanghai_page_url:
        print(f"  找到最新页面: {shanghai_page_url}")
        html = fetch(shanghai_page_url)
        if html:
            sh_data = parse_shanghai_price_page(html)
            all_data["cities"]["上海"] = sh_data
            print(f"  提取到 {len(sh_data['items'])} 项商品价格")
    else:
        print("  [WARN] 无法获取上海价格页面")

    # 2. 36城数据
    print("[2/3] 抓取36城价格信息...")
    pages = get_36city_price_pages()
    if pages:
        for page_url in pages[:2]:  # 蔬菜 + 肉禽蛋
            data = parse_36city_page(page_url)
            if data:
                # 归入"全国参考"分类
                all_data["_36city_raw"] = data
                print(f"  {page_url}: 提取到 {len(data)} 条记录")
    else:
        print("  [WARN] 36城数据页面获取失败")

    # 3. 尝试郴州/长沙/衡阳
    print("[3/3] 尝试获取其他城市数据...")
    # 如果有各地价格页面URL，可以在这里添加
    # 示例: try_fetch_city_price("郴州", "https://xxx/czsgov/price.html")
    # 目前郴州/长沙/衡阳暂无稳定的公开价格数据URL，先跳过

    return all_data


# ============================================================
# 生成摘要 Markdown
# ============================================================

def generate_summary(data: dict) -> str:
    """生成人类可读的 Markdown 摘要"""
    lines = [
        f"# 各地食品价格参考（{data['updated_at'][:10]} 更新）",
        "",
        "> 数据来源：政府公开价格监测信息，每日自动更新",
        "",
    ]

    sh = data.get("cities", {}).get("上海", {})
    if sh.get("items"):
        lines.append("## 上海 · 主副食品均价")
        lines.append("")
        lines.append("| 类别 | 品种 | 价格 | 单位 | 参考区间 |")
        lines.append("|------|------|------|------|----------|")

        # 按类别分组
        by_cat = {}
        for item in sh.get("items", []):
            cat = item.get("category", "其他")
            by_cat.setdefault(cat, []).append(item)

        for cat in ["蔬菜", "肉禽蛋", "鱼虾", "粮食", "食用油", "水果"]:
            if cat in by_cat:
                lines.append(f"\n### {cat}")
                for item in by_cat[cat]:
                    name = item.get("name", "")
                    price = item.get("price", "—")
                    unit = item.get("unit", "")
                    p_range = item.get("price_range", "")
                    lines.append(f"- **{name}**：{price} {unit} {f'（区间 {p_range}）' if p_range else ''}")

        if sh.get("note"):
            lines.append("")
            lines.append(f"> {sh['note']}")

    lines.append("")
    lines.append("---")
    lines.append("*本文件由 GitHub Actions 自动更新，每日定时抓取政府公开价格数据。*")

    return "\n".join(lines)


# ============================================================
# 更新历史记录
# ============================================================

def update_history(data: dict):
    """将当日数据追加到历史记录"""
    history = load_json(HISTORY_FILE, default=[])
    # 按日期去重：移除同一天的旧记录
    today = TODAY
    history = [h for h in history if h.get("date") != today]
    # 追加当日数据
    for city_id, city_data in data.get("cities", {}).items():
        history.append({
            "date": today,
            "city": city_id,
            "items": city_data.get("items", []),
        })
    # 只保留最近90天
    history = history[-90:]
    save_json(HISTORY_FILE, history)


# ============================================================
# 入口
# ============================================================

def main():
    print(f"=== 食品价格爬虫 {datetime.datetime.now().isoformat()} ===")

    # 采集数据
    data = collect_all()

    # 保存 JSON
    save_json(os.path.join(DATA_DIR, "latest_prices.json"), data)

    # 生成摘要
    summary = generate_summary(data)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"\n摘要已写入: {SUMMARY_FILE}")

    # 更新历史
    update_history(data)
    print(f"历史已更新: {HISTORY_FILE}")

    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()
