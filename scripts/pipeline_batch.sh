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
# 逐阶段跑完整个 para 区间再进下一阶段；各阶段脚本各自断点续传。
# 每阶段最多重试 MAX_TRY 次：重跑时 resume 跳过已成功段，只补失败段
# （失败段无产物 → 被再次尝试）。模型偶发的 JSON/句数违规由此自动消化。
#
# 用法：
#   ./pipeline_batch.sh <book_id> <start_para> <end_para> [--method <name>] [--tries N]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

ARGS=("$BOOK_ID" "$START_PARA" "$END_PARA" --method "$METHOD")

# run_stage <label> <script> [extra args...]
# 重试直到该脚本报告 fail=0，或用尽 MAX_TRY 次。
run_stage() {
    local label="$1" script="$2"; shift 2
    local try out
    for ((try = 1; try <= MAX_TRY; try++)); do
        echo ">>> [$label] 第 $try/$MAX_TRY 次"
        out=$("$SCRIPT_DIR/$script" "${ARGS[@]}" "$@" 2>&1) || true
        echo "$out"
        # 末行形如 "=== 完成: done=.. skip=.. fail=N ==="
        if echo "$out" | grep -qE '完成: .*fail=0'; then
            return 0
        fi
        echo ">>> [$label] 仍有失败段，准备重试..."
    done
    echo ">>> [$label] 用尽 $MAX_TRY 次仍有失败段（见上）" >&2
    return 0   # 不中断流水线，失败段留待人工/后续补跑
}

echo "######## pipeline_batch: book=$BOOK_ID para=$START_PARA..$END_PARA method=$METHOD tries=$MAX_TRY ########"

run_stage "1/4 translate"         translate_batch.sh
run_stage "2/4 review(nissaya)"   review_batch.sh   --version 1
run_stage "3/4 revise(v1→v2)"     revise_batch.sh   --version 1
run_stage "4/4 evaluate(nissaya)" evaluate_batch.sh

# 收尾：把模型顽固使用的直角引号「」『』统一为弯引号 “” ‘’（style.md 要求）
echo ">>> [收尾] 引号归一化 「」→“” 、 『』→‘’"
python3 "$SCRIPT_DIR/convert_quotes.py" \
    "$(cd "$SCRIPT_DIR/.." && pwd)/workspace/tipitaka/$METHOD/jsonl/$BOOK_ID" >/dev/null 2>&1 || true

echo "######## pipeline_batch 完成 ########"
