#!/usr/bin/env bash
# sync_from_public.sh —— 把 public canvas-scout 的框架更新同步到 private repo
#
# 用法（在 private repo 根目录）：
#   ./scripts/sync_from_public.sh
#
# 首次使用前：
#   git remote add upstream git@github.com:<user>/canvas-scout.git
#
# 原则：单向同步 public → private。永不反向。

set -euo pipefail

# ── 颜色 ──────────────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;36m'; N='\033[0m'

echo -e "${B}=== canvas-scout 框架同步 ===${N}"

# ── 1. 安全检查 ───────────────────────────────────────────────
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${R}✗ 不在 git repo 里${N}"
    exit 1
fi

if ! git remote get-url upstream > /dev/null 2>&1; then
    echo -e "${R}✗ 没配 upstream remote。先跑：${N}"
    echo "   git remote add upstream git@github.com:<user>/canvas-scout.git"
    exit 1
fi

UPSTREAM_URL=$(git remote get-url upstream)
echo -e "Upstream: ${UPSTREAM_URL}"

if [ -n "$(git status --porcelain)" ]; then
    echo -e "${R}✗ 工作树有未提交改动。先 commit 或 stash：${N}"
    git status --short
    exit 1
fi

BRANCH=$(git branch --show-current)
echo -e "当前分支: ${BRANCH}"

# ── 2. 拉取 upstream ──────────────────────────────────────────
echo -e "\n${B}→ 拉取 upstream/main...${N}"
git fetch upstream main

# ── 3. 看看有没有新 commit ────────────────────────────────────
NEW_COMMITS=$(git log HEAD..upstream/main --oneline 2>/dev/null || echo "")
if [ -z "$NEW_COMMITS" ]; then
    echo -e "${G}✓ 已经和 upstream/main 同步，无需动作${N}"
    exit 0
fi

echo -e "\n${Y}upstream/main 有 $(echo "$NEW_COMMITS" | wc -l | tr -d ' ') 个新 commit：${N}"
echo "$NEW_COMMITS" | head -20
echo ""

# ── 4. 预演冲突范围 ───────────────────────────────────────────
echo -e "${B}→ 预演 merge 看会不会冲突...${N}"
DIFF_FILES=$(git diff --name-only HEAD upstream/main)

# 私有路径清单（CEO 改这些是对的，upstream 不应该动这些）
PRIVATE_PATHS=(
    ".claude/skills/canvas-ics33"
    ".claude/skills/canvas-reading-annotation"
    ".claude/skills/canvas-inside"
    ".claude/skills/canvas-zybooks"
    ".claude/skills/canvas-skip"
    "SECRETS.yaml"
    ".env"
    "HISTORY-ceo.md"
    "courses.yaml"
    "delivery.yaml"
    "runs/"
    "final_drafts/"
)

# 框架路径清单（CEO 不应该改这些，upstream 会改）
FRAMEWORK_PATHS=(
    "src/"
    "skill_helpers/"
    ".claude/skills/router/"
    ".claude/hooks/_lib.py"
    ".claude/hooks/inject_context.py"
    ".claude/hooks/result_schema.py"
    ".claude/hooks/stop_complete.py"
    "README.md"
    "ARCHITECTURE.md"
    "PATTERN.md"
    "WRITING_SKILLS.md"
    "QUICKSTART.md"
)

WARNED=0
for file in $DIFF_FILES; do
    for pp in "${PRIVATE_PATHS[@]}"; do
        if [[ "$file" == "$pp"* ]]; then
            echo -e "${R}⚠ upstream 改了私有路径 ${file}（理论上不应该）${N}"
            WARNED=1
        fi
    done
done

# 检查 private 有没有碰过框架路径（对比 merge-base）
MERGE_BASE=$(git merge-base HEAD upstream/main)
LOCAL_FRAMEWORK_CHANGES=$(git diff --name-only "$MERGE_BASE" HEAD)
for file in $LOCAL_FRAMEWORK_CHANGES; do
    for fp in "${FRAMEWORK_PATHS[@]}"; do
        if [[ "$file" == "$fp"* ]]; then
            echo -e "${Y}⚠ 你在 private 改过框架文件 ${file}（这些改动应该先进 public）${N}"
            WARNED=1
        fi
    done
done

if [ $WARNED -eq 1 ]; then
    echo -e "\n${Y}有警告。看一下 merge 会不会破坏私有逻辑，按回车继续、Ctrl-C 取消。${N}"
    read -r
fi

# ── 5. 真 merge ──────────────────────────────────────────────
echo -e "\n${B}→ 执行 merge...${N}"
if git merge upstream/main --no-edit; then
    echo -e "${G}✓ merge 成功${N}"
else
    echo -e "${R}✗ merge 冲突。按以下步骤：${N}"
    echo "   1. 手工解决冲突文件"
    echo "   2. git add <files>"
    echo "   3. git commit 完成 merge"
    echo "   4. 跑 FUNCTIONAL_CHECKLIST.md 25 项核对"
    exit 1
fi

# ── 6. 提醒跑核对 ─────────────────────────────────────────────
echo ""
echo -e "${G}=== 同步完成 ===${N}"
echo ""
echo "现在必须跑一遍 FUNCTIONAL_CHECKLIST.md 确认框架更新没破坏私有 skill："
echo "   1. /canvas-scan 做一次扫描（然后批准 → /canvas-execute 执行）"
echo "   2. 对 🟢 核心 11 项 + 🔴 私有 7 项都核对"
echo "   3. 全过才算同步成功"
echo ""
echo "如果发现问题，回滚："
echo "   git reset --hard HEAD~1"
