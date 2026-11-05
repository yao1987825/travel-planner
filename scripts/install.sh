#!/usr/bin/env bash
#
# install.sh —— 把本技能装进 opencode 的技能目录
#
# 装完之后, opencode(以及任何认 SKILL.md 的 AI 客户端)就能按需加载这个技能。
# 镜像里已经预装过的, 重装是安全的:
#   SKILL.md / references / scripts 覆盖安装;
#   .env(高德 Key)和 data/(采集数据)属于运行期数据, **不动**。
#
# 用法:
#   bash install.sh
#   SKILLS_DIR=/somewhere bash install.sh
#
set -Eeuo pipefail

SKILL_NAME="travel-planner"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="${SKILLS_DIR:-${HOME}/.config/opencode/skills}"
TARGET="${SKILLS_DIR}/${SKILL_NAME}"

if [[ ! -f "${HERE}/SKILL.md" ]]; then
  echo "错误: ${HERE} 下没有 SKILL.md, 这不是一个技能目录" >&2
  exit 1
fi

mkdir -p "${TARGET}"

for item in SKILL.md references scripts; do
  [[ -e "${HERE}/${item}" ]] || continue
  rm -rf "${TARGET:?}/${item}"
  cp -r "${HERE}/${item}" "${TARGET}/${item}"
done

# data/ 是运行期数据: 目录要留着, 但不覆盖已有文件
if [[ -d "${HERE}/data" ]]; then
  mkdir -p "${TARGET}/data"
  cp -rn "${HERE}/data/." "${TARGET}/data/" 2>/dev/null || true
fi

# .env 是密钥: 目标没有才复制(仓库里只有 .env.example, 所以要靠用户自己填)
if [[ ! -f "${TARGET}/.env" && -f "${HERE}/.env" ]]; then
  cp "${HERE}/.env" "${TARGET}/.env"
  chmod 600 "${TARGET}/.env"
  echo "已复制 .env(含高德 Key)"
fi
if [[ ! -f "${TARGET}/.env" ]]; then
  if [[ -f "${HERE}/.env.example" ]]; then
    cp "${HERE}/.env.example" "${TARGET}/.env"
    chmod 600 "${TARGET}/.env"
    echo "已生成 ${TARGET}/.env —— 记得把 AMAP_KEY 填上"
  fi
fi

if [[ -d "${TARGET}/scripts" ]]; then
  find "${TARGET}/scripts" -type f -name '*.sh' -exec chmod +x {} + 2>/dev/null || true
fi

cat <<EOF

已安装: ${TARGET}

下一步:
  1. 确认高德 Key: ${TARGET}/.env  (AMAP_KEY=...)
  2. 重启 opencode(或新开一个会话), 让它重新扫描技能目录
  3. 体检:  bash ${TARGET}/scripts/preflight.sh
  4. 试一把: travel weather 郴州

EOF
