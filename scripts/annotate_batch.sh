#!/usr/bin/env bash
#
# annotate_batch.sh — 批量为现有译文加脚注
#
# 与 translate_batch.sh 同理：直接注入 SKILL.md 内容，不依赖 Skills 自动触发。
#
# 用法：
#   ./annotate_batch.sh <book_id> <start_para> <end_para> [--method <name>]
#
# 前提：目标段落必须已有 final.jsonl 或至少 v1.jsonl。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_DIR="$PROJECT_DIR/.claude/skills/pali-footnote"

BOOK_ID="${1:?用法: $0 <book_id> <start_para> <end_para> [--method <name>]}"
START_PARA="${2:?缺少 start_para}"
END_PARA="${3:?缺少 end_para}"
METHOD="default"

shift 3
while [[ $# -gt 0 ]]; do
    case "$1" in
        --method) METHOD="$2"; shift 2 ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

SKILL_CONTENT=$(cat "$SKILL_DIR/SKILL.md")
STYLE=""
[[ -f "$PROJECT_DIR/knowledge/style.md" ]] && STYLE=$(cat "$PROJECT_DIR/knowledge/style.md")

OUTPUT_BASE="$PROJECT_DIR/workspace/tipitaka/$METHOD/jsonl/$BOOK_ID"
AUDIT_LOG="$SCRIPT_DIR/audit.log"
touch "$AUDIT_LOG"

echo "=== annotate_batch: book=$BOOK_ID para=$START_PARA..$END_PARA method=$METHOD ==="

SKIP_COUNT=0
DONE_COUNT=0
FAIL_COUNT=0

for PARA in $(seq "$START_PARA" "$END_PARA"); do
    PARA_DIR="$OUTPUT_BASE/$PARA"

    # 查找最新译文
    TRANSLATION_FILE=""
    if [[ -f "$PARA_DIR/${PARA}_final.jsonl" ]]; then
        TRANSLATION_FILE="$PARA_DIR/${PARA}_final.jsonl"
    else
        # 找最新 v(n)
        LATEST=$(ls "$PARA_DIR/${PARA}_v"*.jsonl 2>/dev/null | sort -V | tail -1)
        [[ -n "$LATEST" ]] && TRANSLATION_FILE="$LATEST"
    fi

    if [[ -z "$TRANSLATION_FILE" ]]; then
        echo "  跳过 para=$PARA（无译文）"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    TRANSLATION_CONTENT=$(cat "$TRANSLATION_FILE")

    echo "[$(date +%H:%M:%S)] 加注 book=$BOOK_ID para=$PARA ..."

    PROMPT="$(cat <<PROMPT_EOF
${SKILL_CONTENT}

---翻译风格---
${STYLE}

---现有译文---
${TRANSLATION_CONTENT}

---任务---
为 book=${BOOK_ID} paragraph=${PARA} 的现有译文添加脚注。
查找义注（atthakatha）中对应的解释，为关键术语和难解句生成脚注。
输出完整的 JSONL，在每行追加 "footnotes" 数组字段。
只输出 JSONL，不要输出其他内容。
PROMPT_EOF
)"

    OUTPUT_FILE="$PARA_DIR/${PARA}_annotated.jsonl"

    if claude -p --model sonnet -- "$PROMPT" > "$OUTPUT_FILE" 2>>"$SCRIPT_DIR/annotate_batch.err"; then
        DONE_COUNT=$((DONE_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"annotate\", \"book\": $BOOK_ID, \"para\": $PARA, \"method\": \"$METHOD\", \"status\": \"ok\"}" >> "$AUDIT_LOG"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"annotate\", \"book\": $BOOK_ID, \"para\": $PARA, \"method\": \"$METHOD\", \"status\": \"fail\"}" >> "$AUDIT_LOG"
        echo "  ⚠ 失败" >&2
        [[ -f "$OUTPUT_FILE" ]] && [[ ! -s "$OUTPUT_FILE" ]] && rm "$OUTPUT_FILE"
    fi
done

echo "=== 完成: done=$DONE_COUNT skip=$SKIP_COUNT fail=$FAIL_COUNT ==="
