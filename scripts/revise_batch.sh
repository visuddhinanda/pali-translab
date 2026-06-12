#!/usr/bin/env bash
#
# revise_batch.sh — 批量按审稿意见修订译文
#
# 读取 v{n}.jsonl + reviews/{p}-{p}_v{n}.md，输出 v{n+1}.jsonl。
# 单段即一个 chunk（start=end=para）。不取数（review 已对齐过），纯按意见改。
#
# 用法：
#   ./revise_batch.sh <book_id> <start_para> <end_para> [--method <name>] [--version <n>]
#
# 前提：目标段落已有 v{n}.jsonl 与 reviews/{p}-{p}_v{n}.md。
# 断点续传：已存在 v{n+1}.jsonl 则跳过。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_DIR="$PROJECT_DIR/.claude/skills/pali-revise"

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

SKILL_CONTENT=$(cat "$SKILL_DIR/SKILL.md")

METHOD_FILE="$PROJECT_DIR/methods/$METHOD/revise.md"
[[ -f "$METHOD_FILE" ]] || METHOD_FILE="$SKILL_DIR/methods/default/revise.md"
METHOD_CONTENT=$(cat "$METHOD_FILE")

STYLE=""; TERMS=""; RULES=""; GLOSSARY=""; KNOWN_ISSUES=""
[[ -f "$PROJECT_DIR/knowledge/style.md" ]]             && STYLE=$(cat "$PROJECT_DIR/knowledge/style.md")
[[ -f "$PROJECT_DIR/knowledge/terms.md" ]]             && TERMS=$(cat "$PROJECT_DIR/knowledge/terms.md")
[[ -f "$PROJECT_DIR/knowledge/translation-rules.md" ]] && RULES=$(cat "$PROJECT_DIR/knowledge/translation-rules.md")
[[ -f "$PROJECT_DIR/knowledge/term-glossary.jsonl" ]]  && GLOSSARY=$(cat "$PROJECT_DIR/knowledge/term-glossary.jsonl")
[[ -f "$PROJECT_DIR/knowledge/known-issues.md" ]]      && KNOWN_ISSUES=$(cat "$PROJECT_DIR/knowledge/known-issues.md")

OUTPUT_BASE="$PROJECT_DIR/workspace/tipitaka/$METHOD/jsonl/$BOOK_ID"
AUDIT_LOG="$SCRIPT_DIR/audit.log"
touch "$AUDIT_LOG"

echo "=== revise_batch: book=$BOOK_ID para=$START_PARA..$END_PARA method=$METHOD version=${VERSION:-auto} ==="

SKIP_COUNT=0; DONE_COUNT=0; FAIL_COUNT=0

for PARA in $(seq "$START_PARA" "$END_PARA"); do
    PARA_DIR="$OUTPUT_BASE/$PARA"

    if [[ -n "$VERSION" ]]; then
        N="$VERSION"
        SRC_FILE="$PARA_DIR/${PARA}_v${N}.jsonl"
    else
        SRC_FILE=$(ls "$PARA_DIR/${PARA}_v"*.jsonl 2>/dev/null | sort -V | tail -1 || true)
        [[ -n "$SRC_FILE" ]] && N=$(basename "$SRC_FILE" | sed -E "s/^${PARA}_v([0-9]+)\.jsonl$/\1/")
    fi

    if [[ -z "${SRC_FILE:-}" ]] || [[ ! -s "$SRC_FILE" ]]; then
        echo "  跳过 para=$PARA（无 v${VERSION:-n}.jsonl）"; SKIP_COUNT=$((SKIP_COUNT + 1)); continue
    fi

    REVIEW_FILE="$OUTPUT_BASE/reviews/${PARA}-${PARA}_v${N}.md"
    if [[ ! -s "$REVIEW_FILE" ]]; then
        echo "  跳过 para=$PARA（无 reviews/${PARA}-${PARA}_v${N}.md）"; SKIP_COUNT=$((SKIP_COUNT + 1)); continue
    fi

    NEXT=$((N + 1))
    OUTPUT_FILE="$PARA_DIR/${PARA}_v${NEXT}.jsonl"
    if [[ -f "$OUTPUT_FILE" ]] && [[ -s "$OUTPUT_FILE" ]]; then
        SKIP_COUNT=$((SKIP_COUNT + 1)); continue
    fi

    TRANSLATION_CONTENT=$(cat "$SRC_FILE")
    REVIEW_CONTENT=$(cat "$REVIEW_FILE")
    echo "[$(date +%H:%M:%S)] 修订 book=$BOOK_ID para=$PARA v$N→v$NEXT ..."

    PROMPT="$(cat <<PROMPT_EOF
${SKILL_CONTENT}

---修订方法---
${METHOD_CONTENT}

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

---当前译文 (book=${BOOK_ID} paragraph=${PARA} v${N}.jsonl)---
${TRANSLATION_CONTENT}

---审稿意见 (reviews/${PARA}-${PARA}_v${N}.md)---
${REVIEW_CONTENT}

---任务---
按审稿意见修订 book=${BOOK_ID} paragraph=${PARA}（单段 chunk）的 v${N} 译文，产出 v${NEXT}。
逐条采纳/拒绝审稿意见：采纳则改 zh 字段；不采纳则在该行追加 "revise_skip_reason"。
保持 id / book / paragraph / word_start / word_end / pali 不变，不要改未被 review 提及的句子。
**必须输出且仅输出 ${N} 行 JSONL，与输入 v${N} 逐行一一对应，不得合并、拆分或删除任何一句。**
所有标点用中文全角，引号用全角 “” ‘’，严禁 ASCII " '。
只输出 v${NEXT} 的 JSONL 到标准输出，不要写文件、不要输出其他内容。
PROMPT_EOF
)"

    EXPECT=$(grep -c '^{' "$SRC_FILE" || true)
    RAW="$PARA_DIR/${PARA}_v${NEXT}.raw"
    GOT=0
    if claude -p --model sonnet -- "$PROMPT" > "$RAW" 2>>"$SCRIPT_DIR/revise_batch.err" \
        && python3 "$SCRIPT_DIR/_extract_jsonl.py" "$RAW" "$OUTPUT_FILE"; then
        GOT=$(grep -c '^{' "$OUTPUT_FILE" || true)
    fi
    if [[ "$GOT" -eq "$EXPECT" ]]; then
        rm -f "$RAW"
        DONE_COUNT=$((DONE_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"revise\", \"book\": $BOOK_ID, \"para\": $PARA, \"version\": $NEXT, \"method\": \"$METHOD\", \"status\": \"ok\", \"lines\": $GOT, \"output\": \"$OUTPUT_FILE\"}" >> "$AUDIT_LOG"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"revise\", \"book\": $BOOK_ID, \"para\": $PARA, \"version\": $NEXT, \"method\": \"$METHOD\", \"status\": \"fail\", \"expected\": $EXPECT, \"got\": $GOT}" >> "$AUDIT_LOG"
        echo "  ⚠ 失败 para=$PARA：期望 $EXPECT 句，得到 $GOT 句（原始留在 $RAW）" >&2
        [[ -f "$OUTPUT_FILE" ]] && rm -f "$OUTPUT_FILE"
    fi
done

echo "=== 完成: done=$DONE_COUNT skip=$SKIP_COUNT fail=$FAIL_COUNT ==="
