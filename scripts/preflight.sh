#!/usr/bin/env bash
#
# preflight.sh —— 出行功能环境体检(旅行规划 + 公交实时)
#
# 检查: python3 / requests、高德 Key、公交两个数据源通不通、
#       技能脚本齐不齐、参考数据齐不齐、默认城市有没有覆盖。
# 每一项不过, 都给可以直接抄的修复命令。
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
echo "== 1. Python 环境 =="
if command -v python3 >/dev/null 2>&1; then
  ok "python3  ($(command -v python3))"
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null \
    && ok "版本 $(python3 -V 2>&1 | awk '{print $2}')" \
    || bad "python3 版本太低, 需要 3.8+"
else
  bad "没有 python3 —— 修: sudo pacman -S --needed python python-pip"
fi
if python3 -c 'import requests' 2>/dev/null; then
  ok "requests 已装(高德导航与天气要用)"
else
  bad "requests 没装 —— 修: sudo pacman -S --needed python python-pip && pip install requests"
fi

echo
echo "== 2. 高德 Key(行程规划/导航/天气) =="
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
echo "== 3. 公交数据源 =="
# 掌上公交: Origin 头错了会回 47 字节占位串, 所以要检查长度
if command -v curl >/dev/null 2>&1; then
  _n="$(curl -s --max-time 12 \
        -H 'Origin: https://h5.mygolbs.com' \
        -H 'Referer: https://h5.mygolbs.com/' \
        -H 'User-Agent: Mozilla/5.0 (Linux; Android 12) Mobile Safari/537.36' \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        --data 'CMD=101' 'https://h5.mygolbs.com/ApiData.do' 2>/dev/null | wc -c)"
  if [[ "${_n}" -gt 1000 ]]; then
    ok "掌上公交可达 (城市列表 ${_n} 字节, 579 城)"
  elif [[ "${_n}" -gt 0 ]]; then
    bad "掌上公交只返回 ${_n} 字节 —— Origin 头不对或被上游拦了, 查一下网络/代理"
  else
    warn "没测到掌上公交(可能没网) —— 先跑 net doctor"
  fi
else
  warn "没有 curl, 跳过连通性测试"
fi

if [[ -x "${HERE}/bus_query.py" || -f "${HERE}/bus_query.py" ]]; then
  _t="$(timeout 30 python3 "${HERE}/bus_query.py" lines 郴州 --limit 1 2>&1)"
  if printf '%s' "$_t" | grep -q '线路方向数'; then
    ok "公交查询脚本端到端可用"
  else
    warn "公交查询脚本跑不出结果(见下面):"
    printf '%s\n' "$_t" | sed 's/^/      /' | head -5
  fi
else
  bad "缺少 scripts/bus_query.py —— 重新安装本技能"
fi

echo
echo "== 4. 技能脚本 =="
for f in generate_plan.py amap_nav.py food_price_scraper.py bus_query.py; do
  if [[ -f "${SKILL_DIR}/scripts/${f}" ]]; then
    ok "scripts/${f}"
  else
    bad "scripts/${f} 缺失 —— 重新安装本技能"
  fi
done

echo
echo "== 5. 参考资料 =="
for f in cities_attractions.md food_guide.md money_saving.md amap_api.md bus_api.md; do
  if [[ -f "${SKILL_DIR}/references/${f}" ]]; then
    ok "references/${f}"
  else
    bad "references/${f} 缺失 —— 重新安装本技能"
  fi
done
for f in mygolbs_cities.json bus_cities.json districts.json; do
  if [[ -f "${SKILL_DIR}/references/${f}" ]]; then
    ok "references/${f}"
  else
    bad "references/${f} 缺失 —— 重新安装本技能"
  fi
done

echo
echo "== 6. 默认城市 =="
if [[ -f "${HERE}/bus_query.py" ]] && command -v python3 >/dev/null 2>&1; then
  _c="$(python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('bq', r'${HERE}/bus_query.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
c = m.normalize_city(m.DEFAULT_CITY)
print('YES' if (c in m.mygolbs_cities() or c in m.chelaile_cities()) else 'NO')
" 2>/dev/null)"
  _d="$(python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('bq', r'${HERE}/bus_query.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.DEFAULT_CITY)
" 2>/dev/null)"
  if [[ "$_c" == "YES" ]]; then
    ok "默认城市 ${_d} —— 数据源有覆盖"
  else
    bad "默认城市 ${_d} —— 数据源没有覆盖, 改 bus_query.py 里的 DEFAULT_CITY"
  fi
fi

echo
if [[ $problems -gt 0 ]]; then
  printf '%s有 %d 项必须修的问题%s\n' "$R" "$problems" "$N"
  exit 1
fi
printf '%s全部就绪%s\n' "$G" "$N"
exit 0
