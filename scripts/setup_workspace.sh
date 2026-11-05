#!/usr/bin/env bash
#
# setup_workspace.sh —— RikkaHub 工作区 / 裸 Linux 上的一键安装与自检
#
# 干什么:
#   1. 确认 python3 / git 在不在(不在就 apt 装 —— RikkaHub 工作区默认 apt)
#   2. 把技能仓库 clone 到当前目录(已经在仓库里就跳过)
#   3. 检查高德 Key(没有就提示怎么配)
#   4. 跑一次公交查询自检 —— 确认网络和接口都通
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
echo "== 3. 高德 Key(天气/导航需要;公交不需要) =="
if [[ -n "${SKILL_ROOT}" && -f "${SKILL_ROOT}/.env" ]]; then
  if grep -q '^AMAP_KEY=..' "${SKILL_ROOT}/.env" 2>/dev/null; then
    ok ".env 里已有 AMAP_KEY"
  else
    warn ".env 里还没有 AMAP_KEY"
    echo "     申请: https://lbs.amap.com/dev/key/app"
    echo "     填写: echo 'AMAP_KEY=你的key' >> ${SKILL_ROOT}/.env"
  fi
else
  warn "没有 .env —— 天气和导航会不可用(公交不受影响)"
  echo "     申请: https://lbs.amap.com/dev/key/app"
fi

echo
echo "== 4. 自检 =="
if [[ -n "${SKILL_ROOT}" && -f "${SKILL_ROOT}/scripts/bus_query.py" ]]; then
  _out="$(timeout 40 python3 "${SKILL_ROOT}/scripts/bus_query.py" lines 郴州 --limit 3 2>&1)"
  if printf '%s' "$_out" | grep -q '线路方向数'; then
    ok "公交查询可用 —— $_out" | head -1
    printf '%s\n' "$_out" | sed 's/^/     /' | head -4
  else
    bad "公交查询没跑通(通常是工作区没网):"
    printf '%s\n' "$_out" | sed 's/^/     /' | head -5
  fi
  if python3 -c 'import requests' 2>/dev/null; then
    ok "requests 已装(高德导航/天气可用)"
  else
    warn "requests 没装 —— pip install requests"
  fi
else
  warn "跳过自检(技能不在本地)"
fi

echo
cat <<EOF
接下来:
  查公交: python3 ${DIRNAME}/scripts/bus_query.py live 郴州 2路 --to 湘南幼专
  查天气: python3 ${DIRNAME}/scripts/amap_nav.py --weather 郴州
  查火车票: 工具箱上有 train 命令;工作区里没有, 用 12306 官网或第三方查

EOF
