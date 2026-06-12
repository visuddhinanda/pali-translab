#!/usr/bin/env bash
#
# pipeline_batch.sh — 全流程批处理：translate → review → revise → evaluate
#
# 固定一轮修正（WORKFLOW.md 二）：
#   translate  → v1.jsonl
#   review v1  → reviews/{p}-{p}_v1.md
#   revise v1  → v2.jsonl
#   evaluate   → {p}_final.jsonl + reviews/{p}-{p}_final.md
#
# 处理粒度：**逐段跑完整 4 步**——一个段落 translate→review→revise→evaluate 全部
# 做完（含引号归一化），再进下一段。每步本就是单段独立的 claude -p，段间上下文隔离。
# 各阶段最多重试 MAX_TRY 次：重跑时 resume 跳过已成功产物，只补该段失败的步骤。
#
# 用法：
#   ./pipeline_batch.sh <book_id> <start_para> <end_para> [--method <name>] [--tries N]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BOOK_ID="${1:?用法: $0 <book_id> <start_para> <end_para> [--method <name>] [--tries N]}"
START_PARA="${2:?缺少 start_para}"
END_PARA="${3:?缺少 end_para}"
METHOD="default"
MAX_TRY=3

shift 3
while [[ $# -gt 0 ]]; do
    case "$1" in
        --method) METHOD="$2"; shift 2 ;;
        --tries)  MAX_TRY="$2"; shift 2 ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

# run_stage <label> <script> <para> [extra args...]
# 对单个段落重试某一步，直到该步报告 fail=0，或用尽 MAX_TRY 次。
run_stage() {
    local label="$1" script="$2" para="$3"; shift 3
    local try out
    for ((try = 1; try <= MAX_TRY; try++)); do
        echo ">>> [§$para $label] 第 $try/$MAX_TRY 次"
        out=$("$SCRIPT_DIR/$script" "$BOOK_ID" "$para" "$para" --method "$METHOD" "$@" 2>&1) || true
        echo "$out"
        # 末行形如 "=== 完成: done=.. skip=.. fail=N ==="
        if echo "$out" | grep -qE '完成: .*fail=0'; then
            return 0
        fi
        echo ">>> [§$para $label] 该步失败，准备重试..."
    done
    echo ">>> [§$para $label] 用尽 $MAX_TRY 次仍失败（见上）" >&2
    return 0   # 不中断流水线，留待人工/后续补跑
}

OUTPUT_BASE="$PROJECT_DIR/workspace/tipitaka/$METHOD/jsonl/$BOOK_ID"

echo "######## pipeline_batch: book=$BOOK_ID para=$START_PARA..$END_PARA method=$METHOD tries=$MAX_TRY（逐段全流程）########"

for PARA in $(seq "$START_PARA" "$END_PARA"); do
    echo "════════ 段落 $PARA 全流程开始 ════════"

    run_stage "1/4 translate"         translate_batch.sh "$PARA"
    run_stage "2/4 review(nissaya)"   review_batch.sh    "$PARA" --version 1
    run_stage "3/4 revise(v1→v2)"     revise_batch.sh    "$PARA" --version 1
    run_stage "4/4 evaluate(nissaya)" evaluate_batch.sh  "$PARA"

    # 收尾：把该段直角引号「」『』统一为弯引号 “” ‘’（style.md 要求）
    echo ">>> [§$PARA 收尾] 引号归一化"
    python3 "$SCRIPT_DIR/convert_quotes.py" \
        "$OUTPUT_BASE/$PARA" \
        "$OUTPUT_BASE/reviews/${PARA}-${PARA}_v1.md" \
        "$OUTPUT_BASE/reviews/${PARA}-${PARA}_final.md" >/dev/null 2>&1 || true

    echo "════════ 段落 $PARA 全流程结束 ════════"
done

echo "######## pipeline_batch 完成 ########"
