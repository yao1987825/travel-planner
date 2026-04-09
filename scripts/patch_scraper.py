#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re

with open('food_price_scraper.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到 get_chenzhou_report_url 函数的位置范围
fn_start = content.find('def get_chenzhou_report_url')
if fn_start == -1:
    print('Function not found!')
    exit(1)

# 找这个函数的 "return None" （在 get_chenzhou_report_url 之后，但在 parse_chenzhou_report 之前）
next_fn = content.find('def parse_chenzhou_report', fn_start)
segment = content[fn_start:next_fn]

# 在这个片段里找 "return None"
ret_idx = segment.rfind('return None')
if ret_idx == -1:
    print('return None not found in function!')
    exit(1)

# 整个函数到 parse_chenzhou_report
old_fn_end = fn_start + ret_idx + len('return None')
old_segment = content[fn_start:old_fn_end]
print(f'Old segment length: {len(old_segment)} chars')
print('First 200 chars:', repr(old_segment[:200]))

new_fn = '''def get_chenzhou_report_url() -> Optional[str]:
    """
    查找郴州市最新周报 URL，依次尝试：
      1. 环境变量 CHENZHOU_REPORT_URL（workflow 可预传）
      2. Bing 搜索（curl 方式）
      3. 已知历史 ID 递增尝试
    """
    # 1. 环境变量优先
    env_url = os.environ.get("CHENZHOU_REPORT_URL", "").strip()
    if env_url:
        print(f"  [郴州] 使用环境变量指定 URL: {env_url}")
        return env_url

    # 2. Bing 搜索（curl 绕过 SSL）
    print("  [郴州] 通过 Bing 搜索最新周报 URL...")
    search_url = (
        "https://www.bing.com/search?q="
        "site%3Acif.mofcom.gov.cn+%E9%83%BD%E5%B7%9E+%E7%94%9F%E6%B4%BB%E5%BF%85%E9%9C%81%E5%93%81+%E6%83%85%E5%86%B5%E5%88%86%E6%9E%90+2026"
    )
    html = fetch_curl(search_url, timeout=15)
    if html:
        matches = re.findall(
            r'href="(https?://cif\\.mofcom\\.gov\\.cn/cif/html/market_scanner/\\d+/\\d+/\\d+\\.html)"',
            html
        )
        if matches:
            print(f"  [郴州] Bing 找到: {matches[0]}")
            return matches[0]

    # 3. 已知历史 ID 递增尝试（近 8 周）
    # 已知：第 10 周(03/03~03/09) ID=13153，每周约+26
    print("  [郴州] 尝试已知历史 ID 递增搜索...")
    base_id = 13153
    for offset in range(1, 9):
        for direction in [1, -1]:
            candidate_id = base_id + offset * 26 * direction
            for month in ["4", "3", "2"]:
                test_url = f"https://cif.mofcom.gov.cn/cif/html/market_scanner/2026/{month}/{candidate_id}.html"
                html2 = fetch_curl(test_url, timeout=8)
                if html2 and len(html2) > 500 and "郴州" in html2[:3000]:
                    print(f"  [郴州] ID 试探找到: {test_url}")
                    return test_url

    return None
'''

if old_segment in content:
    new_content = content.replace(old_segment, new_fn, 1)
    with open('food_price_scraper.py', 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_content)
    print('Replacement done!')
else:
    print('Pattern not found - length mismatch')
    print('Expected length:', len(old_segment))
    # Try a different approach - use regex
    print('Trying regex replacement...')
    # Replace the whole function with regex
    pattern = r'def get_chenzhou_report_url\(\)[^:]*""".*?return None\n'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        print(f'Regex found: {match.start()} to {match.end()}')
        print(repr(match.group()[:300]))
