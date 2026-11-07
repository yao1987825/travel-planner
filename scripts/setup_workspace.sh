#!/usr/bin/env bash
#
# setup_workspace.sh —— RikkaHub 工作区 / 裸 Linux 上的一键安装与自检
#
# 干什么:
#   1. 确认 python3 / git 在不在(不在就 apt 装 —— RikkaHub 工作区默认 apt)
#   2. 把技能仓库 clone 到当前目录(已经在仓库里就跳过)
#   3. 跑一次公交自检 + 地铁自检 + 天气自检 —— 确认网络和接口都通
#
# 注意: 本技能所有脚本都是纯标准库, **不需要 pip 装任何东西, 也不需要任何 API Key**。
#
# 用法:
#   bash setup_workspace.sh
#   REPO=https://github.com/yao1987825/travel-planner.git bash setup_workspace.sh
#   SKIP_INSTALL=1 bash setup_workspace.sh     # 只自检, 不装东西
#
set -uo pipefail

REPO="${REPO:-https://github.com/yao1987825/travel-planner.git}"
DIRNAME="${DIRNAME:-travel-planner}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"

G=$'\033[1;32m'; R=$'\033[1;31m'; Y=$'\033[1;33m'; B=$'\033[1;34m'; N=$'\033[0m'
ok()  { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
bad() { printf '  %s✗%s %s\n' "$R" "$N" "$1"; }
warn(){ printf '  %s!%s %s\n' "$Y" "$N" "$1"; }

echo
echo "== 1. 依赖 =="
if command -v python3 >/dev/null 2>&1; then
  ok "python3  $(python3 -V 2>&1 | awk '{print $2}')"
else
  bad "没有 python3"
  if [[ "$SKIP_INSTALL" != "1" ]] && command -v apt-get >/dev/null 2>&1; then
    echo "     正在安装: apt-get update && apt-get install -y python3 python3-pip git"
    apt-get update -qq && apt-get install -y -qq python3 python3-pip git >/dev/null 2>&1
    command -v python3 >/dev/null 2>&1 && ok "python3 装好了" || bad "python3 装失败, 手动跑一次 apt-get install -y python3"
  else
    warn "没法自动装 —— 手动: apt-get install -y python3 python3-pip git"
  fi
fi
command -v git >/dev/null 2>&1 && ok "git" || warn "没有 git(装不了仓库时会用)"

echo
echo "== 2. 技能仓库 =="
if [[ -f "SKILL.md" ]] && [[ -d "scripts" ]]; then
  ok "已经在技能目录里了(当前目录就是技能根)"
  SKILL_ROOT="$(pwd)"
elif [[ -d "${DIRNAME}/scripts" ]]; then
  ok "已存在 ${DIRNAME}/"
  SKILL_ROOT="$(cd "${DIRNAME}" && pwd)"
else
  if [[ "$SKIP_INSTALL" == "1" ]]; then
    warn "跳过安装(SKIP_INSTALL=1)"
    SKILL_ROOT=""
  elif command -v git >/dev/null 2>&1; then
    echo "     正在 clone ${REPO}"
    if git clone --depth 1 "${REPO}" "${DIRNAME}" >/dev/null 2>&1; then
      ok "clone 成功"
      SKILL_ROOT="$(cd "${DIRNAME}" && pwd)"
    else
      bad "clone 失败 —— 手动: git clone --depth 1 ${REPO}"
      SKILL_ROOT=""
    fi
  else
    warn "没有 git, 无法自动 clone —— 手动下载后解压"
    SKILL_ROOT=""
  fi
fi

echo
echo "== 3. 自检(公交 / 地铁 / 天气 / 火车票) =="
if [[ -n "${SKILL_ROOT}" && -f "${SKILL_ROOT}/scripts/bus_query.py" ]]; then
  _out="$(timeout 40 python3 "${SKILL_ROOT}/scripts/bus_query.py" lines 郴州 --limit 3 2>&1)"
  if printf '%s' "$_out" | grep -q '线路方向数'; then
    ok "公交查询可用"
    printf '%s\n' "$_out" | sed 's/^/     /' | head -3
  else
    bad "公交查询没跑通(通常是工作区没网):"
    printf '%s\n' "$_out" | sed 's/^/     /' | head -4
  fi

  _out="$(timeout 60 python3 "${SKILL_ROOT}/scripts/metro_query.py" station 上海 徐家汇 2>&1)"
  if printf '%s' "$_out" | grep -q '途经线路'; then
    ok "地铁查询可用(地铁通 metroman.cn)"
  else
    warn "地铁查询没跑通(见下面):"
    printf '%s\n' "$_out" | sed 's/^/     /' | head -4
  fi

  _out="$(timeout 40 python3 "${SKILL_ROOT}/scripts/weather_query.py" live 郴州 2>&1)"
  if printf '%s' "$_out" | grep -q '实况天气'; then
    ok "天气查询可用(中国天气网)"
  else
    warn "天气查询没跑通(见下面):"
    printf '%s\n' "$_out" | sed 's/^/     /' | head -4
  fi

  _out="$(timeout 40 python3 -c "
import sys; sys.path.insert(0, '${SKILL_ROOT}/scripts')
import train_store
print('车站表', len(train_store._load_station_cache()), '个')
" 2>&1)"
  if printf '%s' "$_out" | grep -q '车站表'; then
    ok "12306 火车票可用(${_out})"
  else
    warn "12306 车站表没读到(见下面):"
    printf '%s\n' "$_out" | sed 's/^/     /' | head -3
  fi
else
  warn "跳过自检(技能不在本地)"
fi

echo
# ── 命令 wrapper ─────────────────────────────────────────────────────────────
# 让工作区里也能直接敲 travel / train / bus / metro / journey
if [[ -z "${SKILL_ROOT}" ]]; then
  echo "技能不在本地, 跳过 wrapper 安装"
else
BIN_DIR="${HOME}/.local/bin"
mkdir -p "${BIN_DIR}"
for name in travel train bus metro journey; do
  case "${name}" in
    travel)  script="travel.py";    prefix="" ;;
    train)   script="train_cli.py"; prefix="" ;;
    bus)     script="bus_query.py"; prefix="" ;;
    metro)   script="metro_query.py"; prefix="" ;;
    journey) script="transit.py";   prefix="journey" ;;
  esac
  cat > "${BIN_DIR}/${name}" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${SKILL_ROOT}/scripts:\${PYTHONPATH:-}"
exec python3 "${SKILL_ROOT}/scripts/${script}" ${prefix} "\$@"
EOF
  chmod +x "${BIN_DIR}/${name}"
done
ok "命令 wrapper 装好: ${BIN_DIR}/ (travel / train / bus / metro / journey)"
case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *) echo "     把 ${BIN_DIR} 加进 PATH:  export PATH=\"${BIN_DIR}:\$PATH\"" ;;
esac
fi  # end SKILL_ROOT guard

echo
cat <<EOF
接下来:
  统一入口: travel help
  公交实时: travel bus live 郴州 2路 --to 湘南幼专
  地铁换乘: travel metro plan 上海 徐家汇 陆家嘴
  天气:     travel weather live 郴州
  火车票:   travel train 郴州 长沙 明天
  整段出行: travel journey --from 郴州西 --to 陆家嘴 --date 明天 --weather

EOF
