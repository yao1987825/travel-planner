#!/usr/bin/env bash
#
# install.sh —— 把本技能装进 opencode 的技能目录
#
# 装完之后, opencode(以及任何认 SKILL.md 的 AI 客户端)就能按需加载这个技能。
# 镜像里已经预装过的, 重装是安全的:
#   SKILL.md / references / scripts 覆盖安装;
#   data/(采集数据)属于运行期数据, **不动**。
#
# 本技能所有脚本都是纯标准库, **不需要 .env、不需要任何 API Key**。
#
# 用法:
#   bash install.sh
#   SKILLS_DIR=/somewhere bash install.sh
#
set -Eeuo pipefail

SKILL_NAME="travel-planner"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# opencode 的技能目录有两种布局，先看哪个真实存在
if [[ -z "${SKILLS_DIR:-}" ]]; then
  if [[ -d "${HOME}/.opencode/skills" ]]; then
    SKILLS_DIR="${HOME}/.opencode/skills"
  else
    SKILLS_DIR="${HOME}/.config/opencode/skills"
  fi
fi
TARGET="${SKILLS_DIR}/${SKILL_NAME}"

if [[ ! -f "${HERE}/SKILL.md" ]]; then
  echo "错误: ${HERE} 下没有 SKILL.md, 这不是一个技能目录" >&2
  exit 1
fi

# ── 开发模式：目标目录是指向仓库的符号链接 ───────────────────────────────────
# 这时**不能** rm -rf 目标下的子目录 —— 那会顺着链接把仓库删了。
# 仓库本身已经是最新代码，直接用它当技能根目录即可。
if [[ -L "${TARGET}" ]]; then
  SKILL_DIR="$(readlink -f "${TARGET}")"
  echo "检测到 ${TARGET} 是符号链接 -> ${SKILL_DIR}"
  echo "开发模式：直接使用仓库内容，不覆盖任何文件。"
else
  SKILL_DIR="${TARGET}"
  mkdir -p "${SKILL_DIR}"

  for item in SKILL.md references scripts; do
    [[ -e "${HERE}/${item}" ]] || continue
    rm -rf "${SKILL_DIR:?}/${item}"
    cp -r "${HERE}/${item}" "${SKILL_DIR}/${item}"
  done

  # data/ 是运行期数据: 目录要留着, 但不覆盖已有文件
  if [[ -d "${HERE}/data" ]]; then
    mkdir -p "${SKILL_DIR}/data"
    cp -rn "${HERE}/data/." "${SKILL_DIR}/data/" 2>/dev/null || true
  fi

  if [[ -d "${SKILL_DIR}/scripts" ]]; then
    find "${SKILL_DIR}/scripts" -type f -name '*.sh' -exec chmod +x {} + 2>/dev/null || true
    find "${SKILL_DIR}/scripts" -type f -name '*.py' -exec chmod +x {} + 2>/dev/null || true
  fi
fi

# ── 命令 wrapper ──────────────────────────────────────────────────────────────
# SKILL.md / README 承诺 travel / train / bus / metro / journey 这几个命令
# 能直接敲 —— 那就得真的把 wrapper 装出来，否则文档就是假的。
#
# 优先装到已经在 PATH 里的目录；都没有就用 ~/.local/bin（多数发行版默认在 PATH）。
BIN_DIR=""
for cand in "${HOME}/.local/bin" "${HOME}/bin"; do
  if [[ -d "${cand}" ]] && [[ ":${PATH}:" == *":${cand}:"* ]]; then
    BIN_DIR="${cand}"
    break
  fi
done
if [[ -z "${BIN_DIR}" ]]; then
  for cand in "${HOME}/.local/bin" "${HOME}/bin"; do
    if [[ -d "${cand}" ]]; then BIN_DIR="${cand}"; break; fi
  done
fi
[[ -z "${BIN_DIR}" ]] && BIN_DIR="${HOME}/.local/bin"
mkdir -p "${BIN_DIR}"

make_wrapper() {
  local name="$1"; shift
  local script="$1"; shift
  local prefix="$*"
  cat > "${BIN_DIR}/${name}" <<EOF
#!/usr/bin/env bash
# travel-planner 命令 wrapper —— 由 scripts/install.sh 生成，重装可覆盖
export PYTHONPATH="${SKILL_DIR}/scripts:\${PYTHONPATH:-}"
exec python3 "${SKILL_DIR}/scripts/${script}" ${prefix} "\$@"
EOF
  chmod +x "${BIN_DIR}/${name}"
}

make_wrapper "travel"  "travel.py"
make_wrapper "train"  "train_cli.py"
make_wrapper "bus"    "bus_query.py"
make_wrapper "metro"  "metro_query.py"
make_wrapper "journey" "transit.py" "journey"

if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
  echo
  echo "⚠️  ${BIN_DIR} 不在 PATH 里 —— 命令装好了但敲不出来。"
  echo "   把它加进 PATH:  echo 'export PATH=\"${BIN_DIR}:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
fi

cat <<EOF

已安装: ${SKILL_DIR}
命令 wrapper: ${BIN_DIR}/  (travel / train / bus / metro / journey)

下一步:
  1. 重启 opencode(或新开一个会话), 让它重新扫描技能目录
  2. 体检:  bash ${SKILL_DIR}/scripts/preflight.sh
  3. 试一把: travel metro plan 上海 徐家汇 陆家嘴
              travel weather live 郴州
              travel journey --from 郴州西 --to 陆家嘴 --date 明天
              travel train 郴州 长沙 明天

EOF
