#!/usr/bin/env bash
#
# loop_translate.sh — 逐段独立命令翻译（每段一条隔离的 claude -p，互不累积上下文）
#
# 方案验证用：脚本是一个 for 循环，循环体内每次只翻译「一个段落」，
# 每段都通过 translate_batch.sh 的单段调用完成 —— 即每段一次全新的 claude -p
# 进程，段与段之间上下文完全隔离，不会在单个 session 内累积。
#
# 用法：
#   ./loop_translate.sh <book_id> <start_para> <end_para> [--method <name>]
#
# 与直接 `translate_batch.sh <book> <start> <end>` 的区别：
#   行为等价（translate_batch 内部本就逐段独立调用），但这里把「每段一条命令」
#   显式摊开，便于单段定位、单独重跑、逐段观察。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

echo "######## loop_translate: book=$BOOK_ID para=$START_PARA..$END_PARA method=$METHOD ########"

DONE=0; FAIL=0
for PARA in $(seq "$START_PARA" "$END_PARA"); do
    echo "──── 命令 $((PARA - START_PARA + 1)): 翻译 book=$BOOK_ID para=$PARA（独立 session）────"
    # 每段一条独立命令：单段范围调用，内部是一次隔离的 claude -p
    if "$SCRIPT_DIR/translate_batch.sh" "$BOOK_ID" "$PARA" "$PARA" --method "$METHOD"; then
        :
    else
        echo "  段 $PARA 命令返回非零" >&2
    fi
    # 判定该段是否产出 v1
    OUT="$(cd "$SCRIPT_DIR/.." && pwd)/workspace/tipitaka/$METHOD/jsonl/$BOOK_ID/$PARA/${PARA}_v1.jsonl"
    if [[ -s "$OUT" ]]; then DONE=$((DONE + 1)); else FAIL=$((FAIL + 1)); fi
done

echo "######## loop_translate 完成: 成功 $DONE 段, 失败 $FAIL 段 ########"
