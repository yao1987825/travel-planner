#!/usr/bin/env bash
#
# preflight.sh —— 出行功能环境体检(行程规划 / 公交实时 / 地铁 / 天气 / 火车票)
#
# 检查: python3、四个数据源通不通、技能脚本齐不齐、参考数据齐不齐、默认城市有没有覆盖。
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
# 本技能的所有脚本都是纯标准库, 不需要 pip 装任何东西
python3 -c 'import json,urllib.request,html.parser' 2>/dev/null \
  && ok "标准库齐全(全部脚本零第三方依赖)" \
  || bad "python3 标准库不完整 —— 换个官方 python 装"

echo
echo "== 2. 公交数据源 =="
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

if [[ -f "${HERE}/bus_query.py" ]]; then
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
echo "== 3. 地铁数据源(地铁通 metroman.cn) =="
if [[ -f "${HERE}/metro_query.py" ]]; then
  _t="$(timeout 60 python3 "${HERE}/metro_query.py" station 上海 徐家汇 2>&1)"
  if printf '%s' "$_t" | grep -q '首末班车\|途经线路'; then
    ok "地铁查询脚本端到端可用"
  else
    warn "地铁查询脚本跑不出结果(见下面):"
    printf '%s\n' "$_t" | sed 's/^/      /' | head -5
  fi
else
  bad "缺少 scripts/metro_query.py —— 重新安装本技能"
fi

echo
echo "== 4. 天气数据源(中国天气网 weather.com.cn) =="
if [[ -f "${HERE}/weather_query.py" ]]; then
  _t="$(timeout 40 python3 "${HERE}/weather_query.py" live 郴州 2>&1)"
  if printf '%s' "$_t" | grep -q '实况天气'; then
    ok "天气查询脚本端到端可用"
  else
    warn "天气查询脚本跑不出结果(见下面):"
    printf '%s\n' "$_t" | sed 's/^/      /' | head -5
  fi
else
  bad "缺少 scripts/weather_query.py —— 重新安装本技能"
fi

echo
echo "== 5. 火车票(12306) =="
if [[ -f "${HERE}/train_store.py" ]]; then
  _t="$(timeout 40 python3 -c "
import sys; sys.path.insert(0, '${HERE}')
import train_store
m = train_store._load_station_cache()
print('车站表', len(m), '个')
" 2>&1)"
  if printf '%s' "$_t" | grep -q '车站表'; then
    ok "12306 车站表就绪(${_t})"
  else
    warn "12306 车站表没读到(见下面):"
    printf '%s\n' "$_t" | sed 's/^/      /' | head -3
  fi
else
  bad "缺少 scripts/train_store.py —— 重新安装本技能"
fi

echo
echo "== 6. 技能脚本 =="
for f in generate_plan.py food_price_scraper.py bus_query.py metro_query.py weather_query.py transit.py train_store.py train_cli.py travel.py; do
  if [[ -f "${SKILL_DIR}/scripts/${f}" ]]; then
    ok "scripts/${f}"
  else
    bad "scripts/${f} 缺失 —— 重新安装本技能"
  fi
done
if [[ -d "${SKILL_DIR}/scripts/metroman" ]]; then
  ok "scripts/metroman/ (地铁数据层)"
else
  bad "scripts/metroman/ 缺失 —— 重新安装本技能"
fi

echo
echo "== 7. 参考资料 =="
for f in cities_attractions.md food_guide.md money_saving.md bus_api.md; do
  if [[ -f "${SKILL_DIR}/references/${f}" ]]; then
    ok "references/${f}"
  else
    bad "references/${f} 缺失 —— 重新安装本技能"
  fi
done
for f in transit_link.md metro_api.md weather_api.md; do
  if [[ -f "${SKILL_DIR}/references/${f}" ]]; then
    ok "references/${f}"
  else
    warn "references/${f} 缺失(新版本文档, 不影响功能)"
  fi
done
for f in mygolbs_cities.json bus_cities.json districts.json weather_cities.json; do
  if [[ -f "${SKILL_DIR}/references/${f}" ]]; then
    ok "references/${f}"
  else
    bad "references/${f} 缺失 —— 重新安装本技能"
  fi
done

echo
echo "== 8. 默认城市 =="
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
