#!/usr/bin/env bash
#
# translate_batch.sh — 批量翻译巴利三藏
#
# 为什么用注入而不是依赖 Skills 自动触发：
#   Skills 自动触发依赖模型在运行时识别 skill 名称并决定调用，这是软约束。
#   批量处理需要确定性：每次调用的上下文完全相同，出问题可精确定位。
#   本脚本直接读取 SKILL.md 和 knowledge 文件内容，拼接为完整提示词，
#   用 `claude -p` 非交互模式执行，绕过模型自主决策环节。
#
# 用法：
#   ./translate_batch.sh <book_id> <start_para> <end_para> [--method <name>]
#
# 断点续传：
#   脚本在输出目录检查已有 v1.jsonl，跳过已完成的段落。
#   中断后重新运行同一命令即可继续。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_DIR="$PROJECT_DIR/.claude/skills/pali-translate"

# --- 参数解析 ---
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

# --- 加载内容 ---
SKILL_CONTENT=$(cat "$SKILL_DIR/SKILL.md")

# 加载 method：项目覆盖优先
METHOD_FILE="$PROJECT_DIR/methods/$METHOD/translate.md"
if [[ ! -f "$METHOD_FILE" ]]; then
    METHOD_FILE="$SKILL_DIR/methods/default/translate.md"
fi
METHOD_CONTENT=$(cat "$METHOD_FILE")

# 加载 knowledge
STYLE=""
TERMS=""
RULES=""
GLOSSARY=""
KNOWN_ISSUES=""

[[ -f "$PROJECT_DIR/knowledge/style.md" ]] && STYLE=$(cat "$PROJECT_DIR/knowledge/style.md")
[[ -f "$PROJECT_DIR/knowledge/terms.md" ]] && TERMS=$(cat "$PROJECT_DIR/knowledge/terms.md")
[[ -f "$PROJECT_DIR/knowledge/translation-rules.md" ]] && RULES=$(cat "$PROJECT_DIR/knowledge/translation-rules.md")
[[ -f "$PROJECT_DIR/knowledge/term-glossary.jsonl" ]] && GLOSSARY=$(cat "$PROJECT_DIR/knowledge/term-glossary.jsonl")
[[ -f "$PROJECT_DIR/knowledge/known-issues.md" ]] && KNOWN_ISSUES=$(cat "$PROJECT_DIR/knowledge/known-issues.md")

# 加载 references
WIKIPALI_API=$(cat "$SKILL_DIR/references/wikipali_api.md")
NISSAYA_FORMAT=$(cat "$SKILL_DIR/references/nissaya_format.md")

# Pali VRI 原文 channel（见 references/wikipali_api.md）
PALI_UID="00b577c0-13b9-11ee-a05a-b7307efd9ee6"
FETCH_SENTENCE="$SKILL_DIR/scripts/fetch_sentence.py"

# --- 输出目录 ---
OUTPUT_BASE="$PROJECT_DIR/workspace/tipitaka/$METHOD/jsonl/$BOOK_ID"

# --- 审计日志 ---
AUDIT_LOG="$SCRIPT_DIR/audit.log"
touch "$AUDIT_LOG"

echo "=== translate_batch: book=$BOOK_ID para=$START_PARA..$END_PARA method=$METHOD ==="
echo "    输出目录: $OUTPUT_BASE"

# --- 逐段处理（claude 内部按 chunk 批处理） ---
SKIP_COUNT=0
DONE_COUNT=0
FAIL_COUNT=0

for PARA in $(seq "$START_PARA" "$END_PARA"); do
    OUTPUT_DIR="$OUTPUT_BASE/$PARA"
    OUTPUT_FILE="$OUTPUT_DIR/${PARA}_v1.jsonl"

    # 断点续传：跳过已完成
    if [[ -f "$OUTPUT_FILE" ]] && [[ -s "$OUTPUT_FILE" ]]; then
        SKIP_COUNT=$((SKIP_COUNT + 1))
        continue
    fi

    mkdir -p "$OUTPUT_DIR"

    # 取 pali 原文（逐句），slim 为 {id,word_start,word_end,pali} 注入提示词，并据此校验句数
    PALI_SLIM=$(python3 "$FETCH_SENTENCE" --book "$BOOK_ID" --para "$PARA" --format text --channels "$PALI_UID" 2>>"$SCRIPT_DIR/translate_batch.err" \
        | python3 -c "
import sys, json
for l in sys.stdin:
    l = l.strip()
    if not l: continue
    r = json.loads(l)
    t = (r.get('html') or r.get('content') or '').strip()
    if not t: continue
    rid = f\"{r['book']}-{r['paragraph']}-{r['word_start']}-{r['word_end']}\"
    print(json.dumps({'id': rid, 'word_start': r['word_start'], 'word_end': r['word_end'], 'pali': t}, ensure_ascii=False))
" 2>>"$SCRIPT_DIR/translate_batch.err")

    N=$(printf '%s\n' "$PALI_SLIM" | grep -c '^{' || true)
    if [[ "$N" -eq 0 ]]; then
        echo "  跳过 para=$PARA（无 pali 原文）"
        SKIP_COUNT=$((SKIP_COUNT + 1)); continue
    fi

    echo "[$(date +%H:%M:%S)] 翻译 book=$BOOK_ID para=$PARA （$N 句）..."

    # 拼接完整提示词
    PROMPT="$(cat <<PROMPT_EOF
${SKILL_CONTENT}

---翻译方法---
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

---待翻译 pali 原文（book=${BOOK_ID} paragraph=${PARA}，共 ${N} 句，逐句已含 id/word_start/word_end）---
${PALI_SLIM}

---任务---
把上面 ${N} 句 pali 逐句译为现代书面汉语。
**必须输出且仅输出 ${N} 行 JSONL，与输入逐句一一对应**，不得合并、拆分、增删或漏译任何一句。
每行格式：{"id": 同输入, "book": ${BOOK_ID}, "paragraph": ${PARA}, "word_start": 同输入, "word_end": 同输入, "pali": 同输入, "zh": "你的译文", "confidence": 0-100}
保持 id / word_start / word_end / pali 与输入完全一致，只新增 zh 与 confidence。
硬约束：所有标点用中文全角；引号一律用全角 “”（双）/ ‘’（单），严禁出现 ASCII 双引号 " 或单引号 '——否则整行 JSON 非法、整句被丢弃。
不确定的译法不要留空，给出最不坏候选并标 ⚠️[候选?]，evaluate 步会处理。
只输出 JSONL，不要输出旁白、代码围栏或其他内容。
PROMPT_EOF
)"

    # 执行翻译（原始 stdout → RAW，抽取合法 JSONL → OUTPUT_FILE，再校验句数 == N）
    RAW="$OUTPUT_DIR/${PARA}_v1.raw"
    GOT=0
    if claude -p --model sonnet -- "$PROMPT" > "$RAW" 2>>"$SCRIPT_DIR/translate_batch.err" \
        && python3 "$SCRIPT_DIR/_extract_jsonl.py" "$RAW" "$OUTPUT_FILE"; then
        GOT=$(grep -c '^{' "$OUTPUT_FILE" || true)
    fi

    if [[ "$GOT" -eq "$N" ]]; then
        rm -f "$RAW"
        DONE_COUNT=$((DONE_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"translate\", \"book\": $BOOK_ID, \"para\": $PARA, \"method\": \"$METHOD\", \"status\": \"ok\", \"lines\": $GOT, \"output\": \"$OUTPUT_FILE\"}" >> "$AUDIT_LOG"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"op\": \"translate\", \"book\": $BOOK_ID, \"para\": $PARA, \"method\": \"$METHOD\", \"status\": \"fail\", \"expected\": $N, \"got\": $GOT}" >> "$AUDIT_LOG"
        echo "  ⚠ 失败 para=$PARA：期望 $N 句，得到 $GOT 句（原始留在 $RAW）" >&2
        # 句数不符的输出不可信，删除以便重跑
        [[ -f "$OUTPUT_FILE" ]] && rm -f "$OUTPUT_FILE"
    fi
done

echo "=== 完成: done=$DONE_COUNT skip=$SKIP_COUNT fail=$FAIL_COUNT ==="
