#!/usr/bin/env python3
"""
发现郴州市商务局最新周报 URL。
策略：
  1. Bing 搜索（可能在中国大陆 IP 被拦截）
  2. 扫描 cif.mofcom.gov.cn 近期页面列表（直接抓索引页）
  3. 已知历史 URL 备用（格式固定，ID 递增）
找到后写入 GITHUB_ENV。
"""
import os
import re
import sys
import urllib.request
import urllib.error

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

GITHUB_ENV = os.environ.get("GITHUB_ENV", "")


def fetch(url: str, timeout: int = 15) -> str:
    """带 UA 的简单 fetch，返回文本，失败抛异常"""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ct = resp.headers.get("Content-Type", "")
        charset = "utf-8"
        if "charset=" in ct:
            charset = ct.split("charset=")[-1].strip()
        data = resp.read()
        return data.decode(charset, errors="replace")


def write_env(key: str, value: str):
    if GITHUB_ENV:
        with open(GITHUB_ENV, "a") as f:
            f.write(f"{key}={value}\n")


def try_bing_search() -> str:
    """策略1：Bing 搜索"""
    url = (
        "https://www.bing.com/search?q="
        "site%3Acif.mofcom.gov.cn+%E9%83%BD%E5%B7%9E+%E7%94%9F%E6%B4%BB%E5%BF%85%E9%9C%81%E5%93%81+%E6%83%85%E5%86%B5%E5%88%86%E6%9E%90+2026"
    )
    print(f"[discover] Trying Bing search...")
    try:
        html = fetch(url, timeout=15)
        matches = re.findall(
            r'href="(https?://cif\.mofcom\.gov\.cn/cif/html/market_scanner/\d+/\d+/\d+\.html)"',
            html
        )
        if matches:
            print(f"[discover] Bing found: {matches[0]}")
            return matches[0]
        else:
            print("[discover] Bing returned page but no matches (IP may be blocked)")
    except Exception as e:
        print(f"[discover] Bing search failed: {e}")
    return None


def try_index_scan() -> str:
    """策略2：直接扫描 cif.mofcom.gov.cn 市场监测索引页，找郴州相关最新页面"""
    base = "https://cif.mofcom.gov.cn/cif/html/market_scanner"
    months = ["3", "4", "2", "1"]  # 从最新月份往前试
    year = "2026"
    found_url = None
    found_date = None

    for month in months:
        idx_url = f"{base}/{year}/{month}/"
        try:
            html = fetch(idx_url, timeout=15)
            # 找所有周报链接，优先选标题含"郴州"的
            all_links = re.findall(
                r'href="(\d+\.html)"[^>]*>([^<]*)',
                html
            )
            for rel_link, title in all_links:
                full_url = f"{base}/{year}/{month}/{rel_link}"
                if "郴州" in title or "郴州" in html[html.find(rel_link)-200:html.find(rel_link)+200]:
                    # 提取链接附近的文本判断是否郴州
                    snippet_start = max(0, html.find(rel_link) - 300)
                    snippet = html[snippet_start:snippet_start + 500]
                    if "郴州" in snippet:
                        # 提取日期
                        date_m = re.search(r'(\d{4})[年-](\d{1,2})[月-](\d{1,2})', snippet)
                        date_str = f"{date_m.group(1)}{date_m.group(2).zfill(2)}{date_m.group(3).zfill(2)}" if date_m else "00000000"
                        print(f"[discover] Index scan found candidate: {full_url} ({date_str})")
                        if found_date is None or date_str > found_date:
                            found_url = full_url
                            found_date = date_str
        except Exception as e:
            print(f"[discover] Index scan failed for {idx_url}: {e}")
            continue

    return found_url


def try_fallback_urls() -> str:
    """策略3：已知历史格式，直接尝试近几周的 ID"""
    base = "https://cif.mofcom.gov.cn/cif/html/market_scanner/2026"
    # 已知第10周(03/03~03/09) ID=13153，第9周 ID=13127...
    # 近期周报 ID 通常每周递增，尝试近 8 周
    last_known_id = 13153  # 第10周（2026-03-03~03-09）
    for week_offset in range(8):
        # 每周约增加 26
        candidate_id = last_known_id + week_offset * 26
        for month in ["4", "3", "2"]:
            for day in range(1, 29, 7):  # 每周大概这个时间段
                url = f"{base}/{month}/{candidate_id}.html"
                try:
                    html = fetch(url, timeout=10)
                    if "郴州" in html[:3000]:  # 前3K字符判断
                        print(f"[discover] Fallback found valid URL: {url}")
                        return url
                except Exception:
                    break  # ID 无效，换月份或方向
    return None


def main():
    print("[discover] === 郴州周报 URL 发现 ===")

    # 策略1：Bing 搜索
    url = try_bing_search()
    if url:
        write_env("CHENZHOU_REPORT_URL", url)
        print(f"[discover] Done: {url}")
        return

    # 策略2：直接扫描索引页
    url = try_index_scan()
    if url:
        write_env("CHENZHOU_REPORT_URL", url)
        print(f"[discover] Done: {url}")
        return

    # 策略3：已知格式备用
    url = try_fallback_urls()
    if url:
        write_env("CHENZHOU_REPORT_URL", url)
        print(f"[discover] Done (fallback): {url}")
        return

    print("[discover] All strategies failed, skipping 郴州 data")


if __name__ == "__main__":
    main()

