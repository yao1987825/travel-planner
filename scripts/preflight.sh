#!/usr/bin/env bash
#
# preflight.sh —— 旅游/出行功能环境体检
#
# 检查: travel / train 命令在不在、高德 Key 配了没、python3 有没有、
#       requests 装没装、技能自己的脚本齐不齐。
# 每一项不过, 都会给可以直接抄的修复命令。
#
# 用法:
#   bash preflight.sh
#
# 退出码:
#   0 = 全部就绪
#   1 = 有必须修的问题
#
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${HERE}/.." && pwd)"

G=$'\033[1;32m'; R=$'\033[1;31m'; Y=$'\033[1;33m'; N=$'\033[0m'
problems=0

ok()  { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
bad() { printf '  %s✗%s %s\n' "$R" "$N" "$1"; problems=$((problems + 1)); }
warn(){ printf '  %s!%s %s\n' "$Y" "$N" "$1"; }

echo
echo "== 1. 命令 =="
for c in travel train; do
  if command -v "$c" >/dev/null 2>&1; then
    ok "$c  ($(command -v "$c"))"
  else
    bad "$c  没装 —— 镜像装坏了, 或 PATH 里没有 /usr/local/bin"
  fi
done

echo
echo "== 2. Python =="
if command -v python3 >/dev/null 2>&1; then
  ok "python3  ($(command -v python3))"
  if python3 -c 'import requests' 2>/dev/null; then
    ok "requests 已装"
  else
    bad "requests 没装 —— 修: sudo pacman -S --needed python python-pip && pip install requests"
  fi
else
  bad "没有 python3 —— 修: sudo pacman -S --needed python python-pip"
fi

echo
echo "== 3. 高德 Key =="
KEY=""
if [[ -f "${SKILL_DIR}/.env" ]]; then
  KEY="$(sed -n 's/^AMAP_KEY=//p' "${SKILL_DIR}/.env" | tail -1 | tr -d '"'"'"' \r')"
fi
if [[ -n "${KEY}" && "$KEY" != *"在这里填"* ]]; then
  ok "AMAP_KEY 已配置 (${SKILL_DIR}/.env)"
elif [[ -f "${SKILL_DIR}/.env" ]]; then
  bad "AMAP_KEY 还是模板值 —— 改 ${SKILL_DIR}/.env, 申请: https://lbs.amap.com/dev/key/app"
else
  bad "没有 ${SKILL_DIR}/.env —— cp .env.example .env 然后填 AMAP_KEY"
fi

echo
echo "== 4. 技能脚本 =="
for f in generate_plan.py amap_nav.py food_price_scraper.py; do
  if [[ -f "${SKILL_DIR}/scripts/${f}" ]]; then
    ok "scripts/${f}"
  else
    bad "scripts/${f} 缺失 —— 重新安装本技能"
  fi
done

echo
echo "== 5. 参考资料 =="
_n=0
for f in "${SKILL_DIR}"/references/*.md; do
  [[ -e "$f" ]] && _n=$((_n + 1))
done
if [[ $_n -gt 0 ]]; then
  ok "references/ 有 ${_n} 份参考文档"
else
  warn "references/ 是空的 —— 重新安装本技能"
fi

echo
echo "== 6. 连通性(高德) =="
if [[ -n "${KEY}" && "$KEY" != *"在这里填"* ]]; then
  _r="$(curl -s --max-time 10 "https://restapi.amap.com/v3/weather/weatherInfo?key=${KEY}&city=%E9%83%B4%E5%B7%9E&extensions=base" 2>/dev/null || true)"
  case "$_r" in
    *'"status":"1"'*) ok "高德接口可达" ;;
    *'"infocode"'*)  bad "高德返回: $(printf '%s' "$_r" | head -c 200)" ;;
    *)               warn "没测到高德接口(可能没网) —— 先跑 net doctor" ;;
  esac
else
  warn "没 Key, 跳过连通性测试"
fi

echo
if [[ $problems -gt 0 ]]; then
  printf '%s有 %d 项必须修的问题%s\n' "$R" "$problems" "$N"
  exit 1
fi
printf '%s全部就绪%s\n' "$G" "$N"
exit 0
