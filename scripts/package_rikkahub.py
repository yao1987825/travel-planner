#!/usr/bin/env python3
"""
package_rikkahub.py —— 把技能打包成 RikkaHub 能导入的 .zip

RikkaHub 的两种导入方式(设置 → 扩展管理 → 技能):
  - 从 GitHub 导入: 粘仓库 URL, Rikka 直接读默认分支 —— 所以仓库根目录有
    SKILL.md 就能用, 这个脚本是给"从文件导入"准备的
  - 从文件导入: 选一个 .zip, Rikka 解压后当技能目录用

打包出两个版本, 应对不同解压习惯:
  travel-planner-rikkahub.zip        内含顶层目录 travel-planner/(压缩"技能文件夹")
  travel-planner-rikkahub-flat.zip   根目录直接是 SKILL.md(解压即技能目录)

注意:
  - 不打包 data/ —— 那是运行时采集的价格数据, 几百 KB, 重新采集即可
  - 不打包 .git / .github

用法:
  python3 scripts/package_rikkahub.py
  python3 scripts/package_rikkahub.py --out /some/dir
"""
from __future__ import annotations

import argparse
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_NAME = "travel-planner"

INCLUDE_FILES = ["SKILL.md", "README.md", "LICENSE", "requirements.txt"]
INCLUDE_DIRS = ["references", "scripts"]
SKIP_NAMES = {".git", ".github", "data", "__pycache__", ".venv", "venv", ".idea", ".vscode"}


def collect(base):
    """收集要打包的文件, 返回 [(绝对路径, 相对路径)]"""
    items = []
    for name in INCLUDE_FILES:
        path = os.path.join(base, name)
        if os.path.isfile(path):
            items.append((path, name))
        else:
            print(f"  ! 缺少 {name}, 跳过")
    for d in INCLUDE_DIRS:
        top = os.path.join(base, d)
        if not os.path.isdir(top):
            print(f"  ! 缺少目录 {d}/, 跳过")
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [x for x in dirnames if x not in SKIP_NAMES]
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, base).replace(os.sep, "/")
                items.append((path, rel))
    return items


def build(dest, prefix, items):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for src, rel in items:
            arc = f"{prefix}/{rel}" if prefix else rel
            z.write(src, arc)
    size = os.path.getsize(dest)
    print(f"  ✓ {os.path.basename(dest)}  ({size / 1024:.1f} KB, {len(items)} 个文件)")


def main():
    ap = argparse.ArgumentParser(description="打包 RikkaHub 技能 zip")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"), help="输出目录(默认 ./dist)")
    args = ap.parse_args()

    # Windows 控制台默认 GBK, 打印 ✓/中文会 UnicodeEncodeError —— 兜个底
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    os.makedirs(args.out, exist_ok=True)
    items = collect(ROOT)
    if not items:
        print("没有可打包的文件", file=sys.stderr)
        return 1

    print("打包:")
    build(os.path.join(args.out, f"{SKILL_NAME}-rikkahub.zip"), SKILL_NAME, items)
    build(os.path.join(args.out, f"{SKILL_NAME}-rikkahub-flat.zip"), "", items)

    print()
    print("RikkaHub 里怎么用:")
    print("  1. 设置 → 扩展管理 → 技能 → + → 从文件导入 → 选 zip")
    print("  2. 设置 → 扩展管理 → 工作区 → 新建 → 安装 Rootfs")
    print("  3. 在工作区里执行: bash setup_workspace.sh(或直接 git clone 仓库)")
    print("  4. 聊天页点 + → 绑定工作区 → 给助手启用这个技能")
    return 0


if __name__ == "__main__":
    sys.exit(main())
