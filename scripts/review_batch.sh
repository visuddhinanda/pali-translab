#!/usr/bin/env bash
#
# review_batch.sh — 批量审读译文（带 nissaya 词级核对）
#
# 与 translate_batch.sh 同理：直接注入 SKILL.md + method + knowledge + references，
# 用 claude -p 非交互执行，绕过 Skills 自动触发的软约束。
#
# 单段即一个 chunk（start=end=para），与现有 reviews/{p}-{p}_v{n}.md 产出一致。
# 模型在 claude -p 内自行调 skill scripts 拉 pali / nissaya 并对齐。
#
# 用法：
#   ./review_batch.sh <book_id> <start_para> <end_para> [--method <name>] [--version <n>]
#
# 前提：目标段落已有 v{n}.jsonl。
# 断点续传：已存在 reviews/{p}-{p}_v{n}.md 则跳过。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_DIR="$PROJECT_DIR/.claude/skills/pali-review"
SKILL_SCRIPTS="$SKILL_DIR/scripts"

# --- 参数解析 ---
BOOK_ID="${1:?用法: $0 <book_id> <start_para> <end_para> [--method <name>] [--version <n>]}"
START_PARA="${2:?缺少 start_para}"
END_PARA="${3:?缺少 end_para}"
METHOD="default"
VERSION=""   # 空 = 自动取每段最新 v(n)

shift 3
while [[ $# -gt 0 ]]; do
    case "$1" in
        --method)  METHOD="$2";  shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

# --- 加载内容 ---
SKILL_CONTENT=$(cat "$SKILL_DIR/SKILL.md")

METHOD_FILE="$PROJECT_DIR/methods/$METHOD/review.md"
[[ -f "$METHOD_FILE" ]] || METHOD_FILE="$SKILL_DIR/methods/default/review.md"
METHOD_CONTENT=$(cat "$METHOD_FILE")

STYLE=""; TERMS=""; RULES=""; GLOSSARY=""; KNOWN_ISSUES=""
[[ -f "$PROJECT_DIR/knowledge/style.md" ]]             && STYLE=$(cat "$PROJECT_DIR/knowledge/style.md")
[[ -f "$PROJECT_DIR/knowledge/terms.md" ]]             && TERMS=$(cat "$PROJECT_DIR/knowledge/terms.md")
[[ -f "$PROJECT_DIR/knowledge/translation-rules.md" ]] && RULES=$(cat "$PROJECT_DIR/knowledge/translation-rules.md")
[[ -f "$PROJECT_DIR/knowledge/term-glossary.jsonl" ]]  && GLOSSARY=$(cat "$PROJECT_DIR/knowledge/term-glossary.jsonl")
[[ -f "$PROJECT_DIR/knowledge/known-issues.md" ]]      && KNOWN_ISSUES=$(cat "$PROJECT_DIR/knowledge/known-issues.md")

WIKIPALI_API=$(cat "$SKILL_DIR/references/wikipali_api.md")
NISSAYA_FORMAT=$(cat "$SKILL_DIR/references/nissaya_format.md")

OUTPUT_BASE="$PROJECT_DIR/workspace/tipitaka/$METHOD/jsonl/$BOOK_ID"
AUDIT_LOG="$SCRIPT_DIR/audit.log"
touch "$AUDIT_LOG"

echo "=== review_batch: book=$BOOK_ID para=$START_PARA..$END_PARA method=$METHOD version=${VERSION:-auto} ==="

SKIP_COUNT=0; DONE_COUNT=0; FAIL_COUNT=0

for PARA in $(seq "$START_PARA" "$END_PARA"); do
    PARA_DIR="$OUTPUT_BASE/$PARA"

    # 确定要审的版本号 N
    if [[ -n "$VERSION" ]]; then
        N="$VERSION"
        SRC_FILE="$PARA_DIR/${PARA}_v${N}.jsonl"
    else
        SRC_FILE=$(ls "$PARA_DIR/${PARA}_v"*.jsonl 2>/dev/null | sort -V | tail -1 || true)
        if [[ -n "$SRC_FILE" ]]; then
            N=$(basename "$SRC_FILE" | sed -E "s/^${PARA}_v([0-9]+)\.jsonl$/\1/")
        fi
    fi

    if [[ -z "${SRC_FILE:-}" ]] || [[ ! -s "$SRC_FILE" ]]; then
        echo "  跳过 para=$PARA（无 v${VERSION:-n}.jsonl）"
        SKIP_COUNT=$((SKIP_COUNT + 1)); continue
    fi

    OUTPUT_FILE="$OUTPUT_BASE/reviews/${PARA}-${PARA}_v${N}.md"
    if [[ -f "$OUTPUT_FILE" ]] && [[ -s "$OUTPUT_FILE" ]]; then
        SKIP_COUNT=$((SKIP_COUNT + 1)); continue
    fi
    mkdir -p "$OUTPUT_BASE/reviews"

    TRANSLATION_CONTENT=$(cat "$SRC_FILE")
    echo "[$(date +%H:%M:%S)] 审读 book=$BOOK_ID para=$PARA v$N ..."

    PROMPT="$(cat <<PROMPT_EOF
${SKILL_CONTENT}

---审读方法---
${METHOD_CONTENT}

---API 参考---
${WIKIPALI_API}

---Nissaya 格式---
${NISSAYA_FORMAT}

---翻译风格---
${STYLE}

---术语偏好---
${TERMS}

---术语表---
${GLOSSARY}

---翻译规则---
${RULES}

---已知难点---
${KNOWN_ISSUES}

---待审译文 (book=${BOOK_ID} paragraph=${PARA} v${N}.jsonl)---
${TRANSLATION_CONTENT}

---任务---
审读 book=${BOOK_ID} paragraph=${PARA}（单段 chunk，start=end=${PARA}）的 v${N} 译文。

取数：从目录 ${SKILL_SCRIPTS} 运行 skill 脚本拉取原文与 nissaya：
  python3 ${SKILL_SCRIPTS}/fetch_channels.py --view paragraphs --book ${BOOK_ID} --para ${PARA} --type nissaya --lang my --uids-only
  python3 ${SKILL_SCRIPTS}/fetch_sentence.py --book ${BOOK_ID} --para ${PARA} --channels <uid>
按 (word_start, word_end) 把 pali / nissaya 对齐到每条 v${N} 译文句，以 nissaya 为词级核对基准。
nissaya 返回 0 个 channel 时降级为纯 pali 审查，并在审稿意见中注明该段无 nissaya。

按上述审读方法逐句审查，只输出审稿意见 Markdown（格式见审读方法）到标准输出，不要写文件、不要输出其他内容。无问题的句子不必列出；整段无问题时输出一行说明即可。
PROMPT_EOF
)"

    if claude -p --model sonnet -- "$PROMPT" > "$OUTPUT_FILE" 2>>"$SCRIPT_DIR/review_batch.err"; then
        DONE_COUNT=$((DONE_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"review\", \"book\": $BOOK_ID, \"para\": $PARA, \"version\": $N, \"method\": \"$METHOD\", \"status\": \"ok\", \"output\": \"$OUTPUT_FILE\"}" >> "$AUDIT_LOG"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"review\", \"book\": $BOOK_ID, \"para\": $PARA, \"version\": $N, \"method\": \"$METHOD\", \"status\": \"fail\"}" >> "$AUDIT_LOG"
        echo "  ⚠ 失败，见 review_batch.err" >&2
        [[ -f "$OUTPUT_FILE" ]] && [[ ! -s "$OUTPUT_FILE" ]] && rm "$OUTPUT_FILE"
    fi
done

echo "=== 完成: done=$DONE_COUNT skip=$SKIP_COUNT fail=$FAIL_COUNT ==="
