#!/usr/bin/env python3
"""
通过 Bing 搜索发现郴州市商务局最新周报 URL。
找到后写入 GITHUB_ENV，供后续步骤使用。
"""
import os
import re
import sys

try:
    import requests
except ImportError:
    print("[WARN] requests not installed, try urllib fallback")
    import urllib.request
    req = urllib.request
else:
    req = requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

SEARCH_URL = (
    "https://www.bing.com/search?q="
    "site%3Acif.mofcom.gov.cn+%E9%83%BD%E5%B7%9E+%E7%94%9F%E6%B4%BB%E5%BF%85%E9%9C%81%E5%93%81+%E6%83%85%E5%86%B5%E5%88%86%E6%9E%90+2026"
)

GITHUB_ENV = os.environ.get("GITHUB_ENV", "")

def write_env(key: str, value: str):
    """写入 GITHUB_ENV 文件（job 间传递变量的标准方式）"""
    if GITHUB_ENV:
        with open(GITHUB_ENV, "a") as f:
            f.write(f"{key}={value}\n")

def main():
    print(f"[discover] Searching: {SEARCH_URL}")
    try:
        r = req.get(SEARCH_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERROR] HTTP request failed: {e}")
        sys.exit(0)  # 不阻塞 workflow，静默跳过

    matches = re.findall(
        r'href="(https?://cif\.mofcom\.gov\.cn/cif/html/market_scanner/\d+/\d+/\d+\.html)"',
        r.text
    )
    if matches:
        url = matches[0]
        print(f"[discover] Found: {url}")
        write_env("CHENZHOU_REPORT_URL", url)
    else:
        print("[discover] No 郴州 report URL found via Bing search")

if __name__ == "__main__":
    main()
