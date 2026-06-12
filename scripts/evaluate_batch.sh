#!/usr/bin/env bash
#
# evaluate_batch.sh — 批量最终评估（带 nissaya 词级基准 + span 原地标注）
#
# 读取每段最新 v{n}.jsonl，输出 {para}_final.jsonl（stdout）+ reviews/{p}-{p}_final.md（模型 Write）。
# 单段即一个 chunk（start=end=para）。模型在 claude -p 内自行拉 pali / nissaya 并对齐。
#
# 用法：
#   ./evaluate_batch.sh <book_id> <start_para> <end_para> [--method <name>]
#
# 前提：目标段落已有 v{n}.jsonl（通常是 revise 产出的 v2）。
# 断点续传：已存在 {para}_final.jsonl 与 reviews/{p}-{p}_final.md 则跳过。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_DIR="$PROJECT_DIR/.claude/skills/pali-evaluate"
SKILL_SCRIPTS="$SKILL_DIR/scripts"

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

METHOD_FILE="$PROJECT_DIR/methods/$METHOD/evaluate.md"
[[ -f "$METHOD_FILE" ]] || METHOD_FILE="$SKILL_DIR/methods/default/evaluate.md"
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

echo "=== evaluate_batch: book=$BOOK_ID para=$START_PARA..$END_PARA method=$METHOD ==="

SKIP_COUNT=0; DONE_COUNT=0; FAIL_COUNT=0

for PARA in $(seq "$START_PARA" "$END_PARA"); do
    PARA_DIR="$OUTPUT_BASE/$PARA"

    SRC_FILE=$(ls "$PARA_DIR/${PARA}_v"*.jsonl 2>/dev/null | sort -V | tail -1 || true)
    if [[ -z "$SRC_FILE" ]] || [[ ! -s "$SRC_FILE" ]]; then
        echo "  跳过 para=$PARA（无 v(n).jsonl）"; SKIP_COUNT=$((SKIP_COUNT + 1)); continue
    fi
    N=$(basename "$SRC_FILE" | sed -E "s/^${PARA}_v([0-9]+)\.jsonl$/\1/")

    FINAL_JSONL="$PARA_DIR/${PARA}_final.jsonl"
    FINAL_MD="$OUTPUT_BASE/reviews/${PARA}-${PARA}_final.md"
    if [[ -s "$FINAL_JSONL" ]] && [[ -s "$FINAL_MD" ]]; then
        SKIP_COUNT=$((SKIP_COUNT + 1)); continue
    fi
    mkdir -p "$OUTPUT_BASE/reviews"

    TRANSLATION_CONTENT=$(cat "$SRC_FILE")
    echo "[$(date +%H:%M:%S)] 评估 book=$BOOK_ID para=$PARA (基于 v$N) ..."

    PROMPT="$(cat <<PROMPT_EOF
${SKILL_CONTENT}

---评估方法---
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

---待评估译文 (book=${BOOK_ID} paragraph=${PARA} v${N}.jsonl)---
${TRANSLATION_CONTENT}

---任务---
最终评估 book=${BOOK_ID} paragraph=${PARA}（单段 chunk，start=end=${PARA}）的最新译文（上方 v${N}）。

取数：从目录 ${SKILL_SCRIPTS} 运行 skill 脚本拉取原文与 nissaya：
  python3 ${SKILL_SCRIPTS}/fetch_channels.py --view paragraphs --book ${BOOK_ID} --para ${PARA} --type nissaya --lang my --uids-only
  python3 ${SKILL_SCRIPTS}/fetch_sentence.py --book ${BOOK_ID} --para ${PARA} --channels <uid>
按 (word_start, word_end) 把 pali / nissaya 对齐到每条译文句，以 nissaya 为词级标准答案评分。
nissaya 返回 0 个 channel 时降级为纯 pali 评估，并在理由中说明该段无 nissaya。

按评估方法执行，并把结果**全部打到标准输出**（不要写文件、不要用 Write 工具）：
1. 对译文中有问题的最小片段按「标注方法」用单引号属性的 <span> 原地包裹（保证整行是合法 JSON）；
   残留的 ⚠️[候选?] 必须逐一处理，final.jsonl 中不得再出现。
2. 先逐行输出 per-para final.jsonl（每行一句，与输入逐行对应，合法 JSON）。
3. 然后单独输出一行精确分隔符：
===FINAL_MD===
4. 分隔符之后输出 per-chunk 总评 md（格式见评估方法）。
不要输出旁白、代码围栏或其他内容；第一行就是 JSON，分隔符前只有 JSONL。
PROMPT_EOF
)"

    RAW="$PARA_DIR/${PARA}_final.raw"
    if claude -p --model sonnet -- "$PROMPT" > "$RAW" 2>>"$SCRIPT_DIR/evaluate_batch.err" \
        && grep -q '^===FINAL_MD===$' "$RAW"; then
        # 按分隔符切分：前段抽 JSONL → final.jsonl；后段 → final.md
        sed '/^===FINAL_MD===$/,$d' "$RAW" > "$RAW.jsonl"
        sed '1,/^===FINAL_MD===$/d' "$RAW" > "$FINAL_MD"
        EXPECT=$(grep -c '^{' "$SRC_FILE" || true)
        GOT=0
        python3 "$SCRIPT_DIR/_extract_jsonl.py" "$RAW.jsonl" "$FINAL_JSONL" && GOT=$(grep -c '^{' "$FINAL_JSONL" || true)
        if [[ "$GOT" -eq "$EXPECT" ]] && [[ -s "$FINAL_MD" ]]; then
            rm -f "$RAW" "$RAW.jsonl"
            DONE_COUNT=$((DONE_COUNT + 1))
            echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"evaluate\", \"book\": $BOOK_ID, \"para\": $PARA, \"based_on\": $N, \"method\": \"$METHOD\", \"status\": \"ok\", \"lines\": $GOT, \"output\": \"$FINAL_JSONL\"}" >> "$AUDIT_LOG"
        else
            FAIL_COUNT=$((FAIL_COUNT + 1))
            echo "  ⚠ 失败 para=$PARA（期望 $EXPECT 句得到 $GOT，或 md 缺失，原始留在 $RAW）" >&2
            echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"evaluate\", \"book\": $BOOK_ID, \"para\": $PARA, \"based_on\": $N, \"method\": \"$METHOD\", \"status\": \"fail\", \"expected\": $EXPECT, \"got\": $GOT}" >> "$AUDIT_LOG"
            [[ -f "$FINAL_JSONL" ]] && rm -f "$FINAL_JSONL"
            [[ -f "$FINAL_MD" ]] && rm -f "$FINAL_MD"
        fi
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"evaluate\", \"book\": $BOOK_ID, \"para\": $PARA, \"based_on\": $N, \"method\": \"$METHOD\", \"status\": \"fail\"}" >> "$AUDIT_LOG"
        echo "  ⚠ 失败，见 evaluate_batch.err（无分隔符/调用失败，原始留在 $RAW）" >&2
    fi
done

echo "=== 完成: done=$DONE_COUNT skip=$SKIP_COUNT fail=$FAIL_COUNT ==="
