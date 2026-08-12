#!/usr/bin/env bash
#
# pipeline_batch.sh — 三层批量流水线：本文 / 义注 / 复注全部翻译，再跨层统稿
#
# 译文的唯一去处是 wikipali channel（覆盖式写入），**不落本地 jsonl**。
# 每一步都从 channel 读回上一步的结果，所以任何一步中断后重跑都能接上。
#
# ── 三层与父层 ────────────────────────────────────────────────────────────
#   mūla（本文）      → 只看巴利原文，独立译出
#   aṭṭhakathā（义注） → 父层是本文；义注里的**黑体是被解释词，引自本文**
#   ṭīkā（复注）      → 父层是义注；复注里的**黑体是被解释词，引自义注**
#
#   被解释词必须与所注文本**逐字同译**，否则读者看不出这条注在注哪个词——
#   随文注的对应关系就断了。所以翻译子层时，把父层的原文与译文一并注入作为对照。
#   坐标由 `wikipali related` 逐层解析（见 scripts/layers.py），三层在不同的书里。
#
# ── 步骤与粒度 ────────────────────────────────────────────────────────────
#   translate / review / revise / evaluate   按 chunk（累加巴利字符到 --chunk-chars）
#   harmonize                                **跨三层**一次统稿
#
#   写 channel 的是 translate / revise / harmonize；review 与 evaluate 不碰译文，
#   只在本地出报告 md。evaluate 排在最后：评的是走完全部改动步骤之后的定稿。
#
# ── 阶段 ──────────────────────────────────────────────────────────────────
#   阶段一  逐层（本文→义注→复注）逐 chunk 做 translate → review → revise
#   阶段二  跨三层统稿：统一被解释词与术语语体，并修正通读发现的问题
#   阶段三  逐层逐 chunk 做 evaluate，出报告
#
# 用法：
#   ./scripts/pipeline_batch.sh <本文book> <start_para> <end_para> \
#       [--channel <uid>] [--method <name>] \
#       [--steps translate,review,revise,harmonize,evaluate] \
#       [--layers mula,atthakatha,tika] [--chunk-chars N] [--max-paras N] \
#       [--tries N] [--model sonnet] [--nissaya] [--dry-run] [--force]
#
# 断点续传：
#   audit.log 按 <层book>:<段> 记账；重跑时整个 chunk 都做过就跳过。--force 强制重做。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS="$PROJECT_DIR/.claude/skills"

BOOK="${1:?用法: $0 <本文book> <start_para> <end_para> [选项]}"
START="${2:?缺少 start_para}"
END="${3:?缺少 end_para}"
shift 3

METHOD="default"
STEPS="translate,review,revise,harmonize,evaluate"
WANT_LAYERS="mula,atthakatha,tika"
MAX_TRY=3
MODEL="sonnet"
CHANNEL=""
NISSAYA=""
FORCE=""
DRYRUN=""
CHUNK_CHARS=5000
MAX_PARAS=12

while [[ $# -gt 0 ]]; do
    case "$1" in
        --channel)     CHANNEL="$2"; shift 2 ;;
        --method)      METHOD="$2";  shift 2 ;;
        --steps)       STEPS="$2";   shift 2 ;;
        --layers)      WANT_LAYERS="$2"; shift 2 ;;
        --tries)       MAX_TRY="$2"; shift 2 ;;
        --model)       MODEL="$2";   shift 2 ;;
        --chunk-chars) CHUNK_CHARS="$2"; shift 2 ;;
        --max-paras)   MAX_PARAS="$2";   shift 2 ;;
        --nissaya)     NISSAYA="--nissaya"; shift ;;   # 只给复核步骤，translate 永远不给
        --force)       FORCE=1; shift ;;
        --dry-run)     DRYRUN="--dry-run"; shift ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

# 目标 channel：命令行 > config.toml [wikipali].channel
if [[ -z "$CHANNEL" && -f "$PROJECT_DIR/config.toml" ]]; then
    CHANNEL=$(python3 - "$PROJECT_DIR/config.toml" <<'PY'
import re, sys
text = open(sys.argv[1], encoding='utf-8').read()
m = re.search(r'^\s*channel\s*=\s*[\'"]([^\'"]+)', text, re.M)
print(m.group(1) if m else '')
PY
)
fi
[[ -n "$CHANNEL" ]] || { echo "缺少目标 channel：用 --channel <uid> 或在 config.toml 的 [wikipali] 下写 channel" >&2; exit 1; }

WORK="$PROJECT_DIR/workspace"
REPORTS="$WORK/reports/$BOOK"
AUDIT="$WORK/audit.log"
GROUPS_FILE="$WORK/.groups_${BOOK}_${START}-${END}"
mkdir -p "$REPORTS" "$WORK"
touch "$AUDIT"

# --- 加载 knowledge（固定文件 + 规则文件）---
read_or_empty() { [[ -f "$1" ]] && cat "$1" || true; }
K="$PROJECT_DIR/knowledge"

KNOWLEDGE=$(cat <<EOF
---翻译风格（knowledge/style.md）---
$(read_or_empty "$K/style.md")

---术语偏好（knowledge/terms.md）---
$(read_or_empty "$K/terms.md")

---已知坑（knowledge/pitfalls.md）---
$(read_or_empty "$K/pitfalls.md")

---翻译规则（knowledge/translation-rules.md）---
$(read_or_empty "$K/translation-rules.md")

---术语表（knowledge/term-glossary.jsonl）---
$(read_or_empty "$K/term-glossary.jsonl")

---已知难点（knowledge/known-issues.md）---
$(read_or_empty "$K/known-issues.md")
EOF
)

# load_step <skill> <step> —— SKILL.md + method（项目覆盖优先）+ references
load_step() {
    local skill="$1" step="$2" mfile
    cat "$SKILLS/$skill/SKILL.md"
    mfile="$PROJECT_DIR/methods/$METHOD/$step.md"
    [[ -f "$mfile" ]] || mfile="$SKILLS/$skill/methods/default/$step.md"
    echo; echo "---方法（$step）---"; [[ -f "$mfile" ]] && cat "$mfile"
    if [[ -f "$SKILLS/$skill/references/nissaya_format.md" ]]; then
        echo; echo "---nissaya 体例---"; cat "$SKILLS/$skill/references/nissaya_format.md"
    fi
}

audit_one() {  # audit_one <step> <book> <para> <status> <detail>
    [[ -n "$DRYRUN" ]] && return 0      # dry-run 不记账，否则真跑时会误跳过
    printf '{"ts":"%s","step":"%s","book":%s,"para":%s,"channel":"%s","method":"%s","status":"%s","detail":"%s"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$CHANNEL" "$METHOD" "$4" "${5:-}" >> "$AUDIT"
}

audit_chunk() {  # audit_chunk <step> <book> <status> <detail> <para...>
    local step="$1" bk="$2" status="$3" detail="$4"; shift 4
    local p; for p in "$@"; do audit_one "$step" "$bk" "$p" "$status" "$detail"; done
}

chunk_done() {  # chunk_done <step> <book> <para...> —— 整个 chunk 都做过才算做过
    [[ -n "$FORCE" ]] && return 1
    local step="$1" bk="$2"; shift 2
    local p
    for p in "$@"; do
        grep -q "\"step\":\"$step\",\"book\":$bk,\"para\":$p,\"channel\":\"$CHANNEL\",\"method\":\"$METHOD\",\"status\":\"ok\"" \
            "$AUDIT" || return 1
    done
    return 0
}

has_step() { [[ ",$STEPS," == *",$1,"* ]]; }

# 报告必须是 markdown（首个非空行以 # 开头）。嵌套会话若改口要权限或吐旁白，
# 输出就不是报告——判失败重跑，不要把「请批准…」当成审稿意见存下来。
valid_report() {
    [[ -s "$1" ]] || return 1
    [[ "$(grep -m1 -v '^[[:space:]]*$' "$1")" == \#* ]]
}

# run_claude <提示词> —— 数据已全部注入，禁掉工具，避免非交互下的权限请求污染输出
run_claude() { claude -p --model "$MODEL" --tools "" -- "$1"; }

count_mula() { printf '%s' "$1" | grep -c '^{"layer":"mula"' || true; }
count_zh()   { printf '%s' "$1" | grep -c '^{"layer":"mula".*"zh":' || true; }

layer_cn() {
    case "$1" in
        mula)       echo "本文（mūla）" ;;
        atthakatha) echo "义注（aṭṭhakathā）" ;;
        tika)       echo "复注（ṭīkā）" ;;
        *)          echo "$1" ;;
    esac
}

# ---------- 解析三层坐标 ----------
echo "######## 本文 book=$BOOK $START..$END → channel $CHANNEL｜method=$METHOD ########"
echo "steps=$STEPS｜layers=$WANT_LAYERS"
echo "解析三层坐标（wikipali related）..."

LAYERS_JSON="$WORK/layers_${BOOK}_${START}-${END}.json"
python3 "$SCRIPT_DIR/layers.py" --book "$BOOK" --para "$START-$END" > "$LAYERS_JSON"

# 每行一个组："层 书号 段列表(逗号) 父书号(无则 -) 标题"
python3 - "$LAYERS_JSON" "$WANT_LAYERS" > "$GROUPS_FILE" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding='utf-8'))
want = set(sys.argv[2].split(','))
for g in data["groups"]:
    if g["layer"] not in want or not g["paras"]:
        continue
    print(g["layer"], g["book"], ",".join(str(p) for p in g["paras"]),
          g["parent_book"] if g["parent_book"] else "-", g["title"] or "-")
PY

[[ -s "$GROUPS_FILE" ]] || { echo "没解析出任何层次，无事可做" >&2; exit 1; }
while read -r L B P PB T; do
    echo "  $(layer_cn "$L")  $B:${P%%,*}-${P##*,}  父层=$PB  $T"
done < "$GROUPS_FILE"

# parent_spec <层book> <段列表> —— 该 chunk 对应的父层段号（逗号分隔），无则空
parent_spec() {
    python3 - "$LAYERS_JSON" "$1" "$2" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding='utf-8'))
book, paras = int(sys.argv[2]), set(sys.argv[3].split(','))
for g in data["groups"]:
    if g["book"] != book:
        continue
    out = []
    for cp, parents in g["map"].items():
        if cp in paras:
            out += parents
    print(",".join(str(x) for x in sorted(set(out))))
    break
PY
}

# chunk_list <book> <段列表> —— 按巴利字符切 chunk，每行一个逗号分隔的段组
chunk_list() {
    python3 - "$SCRIPT_DIR" "$1" "$2" "$CHUNK_CHARS" "$MAX_PARAS" <<'PY'
import json, subprocess, sys
script_dir, book, spec, budget, max_paras = sys.argv[1:]
budget, max_paras = int(budget), int(max_paras)

chunks, cur, size = [], [], 0
for para in spec.split(","):
    out = subprocess.run(
        [sys.executable, f"{script_dir}/wp_pull.py", "--book", book, "--para", para],
        capture_output=True, text=True).stdout
    rows = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
    if not rows:                       # 无原文：不进任何 chunk
        continue
    n = sum(len(r.get("pali", "")) for r in rows)
    if cur and (size + n > budget or len(cur) >= max_paras):
        chunks.append(cur); cur, size = [], 0
    cur.append(para); size += n
if cur:
    chunks.append(cur)

for c in chunks:
    print(",".join(c))
PY
}

# pull_review <book> <段列表> —— 复核输入：现有译文 + pali (+ nissaya)
pull_review() {
    python3 "$SCRIPT_DIR/wp_pull.py" --book "$1" --para "$2" $NISSAYA --channel "$CHANNEL"
}

# ══════════ 阶段一：逐层 translate → review → revise ══════════
while read -r LAYER LBOOK LPARAS PBOOK TITLE; do
    [[ -z "${LAYER:-}" ]] && continue
    LCN="$(layer_cn "$LAYER")"
    echo "╔══════ 阶段一 $LCN  book=$LBOOK  $TITLE ══════╗"

    # 父层对照：翻译子层时要保证被解释词与父层逐字同译
    PARENT_BLOCK=""
    if [[ "$PBOOK" != "-" ]]; then
        PSPEC="$(parent_spec "$LBOOK" "$LPARAS")"
        if [[ -n "$PSPEC" ]]; then
            PARENT_TXT="$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$PBOOK" --para "$PSPEC" --channel "$CHANNEL" || true)"
            if [[ "$(count_zh "$PARENT_TXT")" -gt 0 ]]; then
                PARENT_BLOCK="
---父层对照（book=$PBOOK，段 $PSPEC；pali 为父层原文，zh 为**已定稿的父层译文**）---
本层的**黑体被解释词引自父层**。凡是黑体词，译法必须与下面父层译文中同一处**逐字相同**，
一个字都不能改——不一致读者就看不出这条注在注哪个词。父层没提到的词才由你自己定译法。
$PARENT_TXT
"
            else
                echo "  ⚠ 父层 $PBOOK:$PSPEC 还没有译文，本层无法对齐被解释词" >&2
            fi
        fi
    fi

    while read -r CH; do
        [[ -z "$CH" ]] && continue
        PARAS="${CH//,/ }"
        FIRST="${CH%%,*}"; LAST="${CH##*,}"
        TAG="$LBOOK-$FIRST-$LAST"
        echo "════════ $LCN $LBOOK:$FIRST-$LAST ════════"

        SRC=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$CH" || true)
        N=$(count_mula "$SRC")
        if [[ "$N" -eq 0 ]]; then
            echo "  跳过（无巴利原文）"; continue
        fi

        # ---------- translate ----------
        if has_step translate && ! chunk_done translate "$LBOOK" $PARAS; then
            for ((try = 1; try <= MAX_TRY; try++)); do
                echo ">>> translate 第 $try/$MAX_TRY 次（$N 句 / $(echo $PARAS | wc -w) 段）"
                if run_claude "$(load_step pali-translate translate)

$KNOWLEDGE

---本次要译的文献层次：$LCN（book=$LBOOK $TITLE）---
$PARENT_BLOCK
---待翻译（book=$LBOOK，段 $CH，共 $N 句，按段落顺序排列）---
pali 里的 \`**词**\` 是原文的黑体；在义注/复注里它就是**被解释词**，译文要保留 \`**…**\` 标记。
$SRC

---任务---
把上面 $N 句 pali 逐句译为现代书面汉语。这些段落是连续上下文，术语与语体要通篇一致。
**只输出 $N 行 JSONL，与输入逐句一一对应**，不得合并、拆分、增删或漏译。
每行：{\"id\": 同输入, \"zh\": \"你的译文\", \"confidence\": 0-100}
坐标以输入为准，不要编造 id。标点用中文全角；引号用全角 “” ‘’，不要出现 ASCII 引号。
不确定时给出最好的一个译法并调低该句 confidence，**不要在译文里留任何工作标记**（候选、待定、问号之类）。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 JSONL，不要旁白或代码围栏。" \
                    | python3 "$SCRIPT_DIR/wp_push.py" --book "$LBOOK" --para "$CH" \
                        --channel "$CHANNEL" --expect "$N" $DRYRUN; then
                    audit_chunk translate "$LBOOK" ok "$N" $PARAS; break
                fi
                [[ $try -eq $MAX_TRY ]] && { audit_chunk translate "$LBOOK" fail "$MAX_TRY 次未成" $PARAS; echo "  ⚠ translate 失败" >&2; }
            done
        fi

        # review / revise 都要有译文才有意义
        REVIEW_SRC=""
        if has_step review || has_step revise; then
            REVIEW_SRC=$(pull_review "$LBOOK" "$CH" || true)
            if [[ "$(count_zh "$REVIEW_SRC")" -eq 0 ]]; then
                echo "  跳过复核（channel 上 $LBOOK:$FIRST-$LAST 还没有译文）"
                REVIEW_SRC=""
            fi
        fi

        # ---------- review ----------
        REVIEW_MD="$REPORTS/${TAG}_review.md"
        if has_step review && [[ -n "$REVIEW_SRC" ]] && ! chunk_done review "$LBOOK" $PARAS; then
            for ((try = 1; try <= MAX_TRY; try++)); do
                echo ">>> review 第 $try/$MAX_TRY 次"
                if run_claude "$(load_step pali-review review)

$KNOWLEDGE

---本次审的文献层次：$LCN（book=$LBOOK $TITLE）---
$PARENT_BLOCK
---待审译文（book=$LBOOK，段 $CH，channel=$CHANNEL）---
$REVIEW_SRC

---任务---
按方法文档逐句审查，输出 markdown 审稿意见。
本层若有父层对照，**第一项就查被解释词是否与父层译文逐字相同**，不同即必改项。
整个 chunk 一起审，跨段的术语与语体不一致也要列出。无问题的句子不必列出。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 markdown，不要旁白或代码围栏。" > "$REVIEW_MD" && valid_report "$REVIEW_MD"; then
                    audit_chunk review "$LBOOK" ok "$REVIEW_MD" $PARAS; break
                fi
                [[ $try -eq $MAX_TRY ]] && { audit_chunk review "$LBOOK" fail "$MAX_TRY 次未成" $PARAS; echo "  ⚠ review 失败（输出不是报告）" >&2; }
            done
        fi

        # ---------- revise ----------
        if has_step revise && [[ -n "$REVIEW_SRC" ]] && ! chunk_done revise "$LBOOK" $PARAS; then
            for ((try = 1; try <= MAX_TRY; try++)); do
                echo ">>> revise 第 $try/$MAX_TRY 次"
                if run_claude "$(load_step pali-revise revise)

$KNOWLEDGE

---本次修订的文献层次：$LCN（book=$LBOOK $TITLE）---
$PARENT_BLOCK
---现有译文与资源（book=$LBOOK，段 $CH）---
$REVIEW_SRC

---审稿意见---
$(read_or_empty "$REVIEW_MD")

---任务---
按审稿意见修正译文。**只输出 $N 行 JSONL**，每行：{\"id\": 同输入, \"zh\": \"修正后译文\", \"confidence\": 0-100}
未被审稿意见提及的句子原样输出，不要顺手改；但每一句都要输出，漏掉就等于漏写。
坐标不要编造。译文里不要留任何工作标记。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 JSONL，不要旁白或代码围栏。" \
                    | python3 "$SCRIPT_DIR/wp_push.py" --book "$LBOOK" --para "$CH" \
                        --channel "$CHANNEL" --expect "$N" $DRYRUN; then
                    audit_chunk revise "$LBOOK" ok "$N" $PARAS; break
                fi
                [[ $try -eq $MAX_TRY ]] && { audit_chunk revise "$LBOOK" fail "$MAX_TRY 次未成" $PARAS; echo "  ⚠ revise 失败" >&2; }
            done
        fi
    done < <(chunk_list "$LBOOK" "$LPARAS")
done < "$GROUPS_FILE"

# ══════════ 阶段二：跨三层统稿 ══════════
# 三层分头译完，被解释词和术语难免对不上。这一步把三层放在一起通读，统一并修正。
if has_step harmonize; then
    echo "╔══════ 阶段二 跨三层统稿 ══════╗"

    ALL_SRC=""
    HAVE=1
    while read -r LAYER LBOOK LPARAS PBOOK TITLE; do
        [[ -z "${LAYER:-}" ]] && continue
        TXT=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$LPARAS" --channel "$CHANNEL" || true)
        NL=$(count_mula "$TXT"); NZ=$(count_zh "$TXT")
        echo "  $(layer_cn "$LAYER") book=$LBOOK：$NZ/$NL 句有译文"
        if [[ "$NZ" -ne "$NL" ]]; then
            echo "  ⚠ 该层译文不全，先补齐再统稿——本次跳过统稿" >&2; HAVE=0
        fi
        ALL_SRC="$ALL_SRC
=== $(layer_cn "$LAYER")  book=$LBOOK  段 $LPARAS  $TITLE ===
$TXT
"
    done < "$GROUPS_FILE"

    TOTAL=$(printf '%s' "$ALL_SRC" | grep -c '^{"layer":"mula"' || true)

    if [[ "$HAVE" -eq 1 && "$TOTAL" -gt 0 ]]; then
        for ((try = 1; try <= MAX_TRY; try++)); do
            echo ">>> harmonize（跨三层）第 $try/$MAX_TRY 次（共 $TOTAL 句）"
            OUT="$(mktemp)"
            if run_claude "$(load_step pali-harmonize harmonize)

$KNOWLEDGE

---三层译文（同一部经的本文 / 义注 / 复注，已分头译完）---
每块以 === 开头标出层次与 book；pali 里的 \`**词**\` 是黑体被解释词。
$ALL_SRC

---任务---
把三层放在一起通读，做统稿，两件事：
1. **统一**——
   a) **被解释词逐字对齐（最高优先）**：义注的黑体引自本文，其译法必须与本文同一处逐字相同；
      复注的黑体引自义注，必须与义注同一处逐字相同。不一致就改子层去迁就父层；
      除非父层本身译错——那就把父层一并改对。
   b) 三层之间术语译法统一、语体统一、称谓与专名统一、标点体例统一。
2. **修正**——通读中发现的实际问题就地改掉：误译、漏译、指代接不上、汉语语病、
   文言/半文半白、引号配对断裂。
每处改动都要有具体理由（对齐、一致性，或明确的错误）；**不要为「读起来更顺」而改**，不要重译。
**输出 $TOTAL 行 JSONL**（三层全部句子，未改动的原样输出）：{\"id\": 同输入, \"zh\": \"统稿后译文\"}
id 里带着 book 与段号，照抄输入，不要编造。译文里不要留任何工作标记。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 JSONL，不要旁白或代码围栏。" > "$OUT"; then
                OK=1
                # 一份输出分层提交：每层只收自己 book 的行，别层静默跳过
                while read -r LAYER LBOOK LPARAS PBOOK TITLE; do
                    [[ -z "${LAYER:-}" ]] && continue
                    NL=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$LPARAS" | grep -c '^{' || true)
                    if ! python3 "$SCRIPT_DIR/wp_push.py" --book "$LBOOK" --para "$LPARAS" \
                        --channel "$CHANNEL" --expect "$NL" --ignore-foreign $DRYRUN < "$OUT"; then
                        OK=0
                    fi
                done < "$GROUPS_FILE"
                if [[ "$OK" -eq 1 ]]; then
                    rm -f "$OUT"
                    while read -r LAYER LBOOK LPARAS PBOOK TITLE; do
                        [[ -z "${LAYER:-}" ]] && continue
                        audit_chunk harmonize "$LBOOK" ok "跨三层" ${LPARAS//,/ }
                    done < "$GROUPS_FILE"
                    break
                fi
            fi
            rm -f "$OUT"
            [[ $try -eq $MAX_TRY ]] && echo "  ⚠ harmonize 失败（用尽 $MAX_TRY 次）" >&2
        done
    fi
fi

# ══════════ 阶段三：evaluate（最后一步，只出报告）══════════
if has_step evaluate; then
    echo "╔══════ 阶段三 评估 ══════╗"
    while read -r LAYER LBOOK LPARAS PBOOK TITLE; do
        [[ -z "${LAYER:-}" ]] && continue
        LCN="$(layer_cn "$LAYER")"
        while read -r CH; do
            [[ -z "$CH" ]] && continue
            PARAS="${CH//,/ }"
            FIRST="${CH%%,*}"; LAST="${CH##*,}"
            TAG="$LBOOK-$FIRST-$LAST"
            chunk_done evaluate "$LBOOK" $PARAS && continue

            EVAL_SRC=$(pull_review "$LBOOK" "$CH" || true)
            if [[ "$(count_zh "$EVAL_SRC")" -eq 0 ]]; then
                echo "  跳过评估（$LBOOK:$FIRST-$LAST 还没有译文）"; continue
            fi

            echo "════════ 评估 $LCN $LBOOK:$FIRST-$LAST ════════"
            for ((try = 1; try <= MAX_TRY; try++)); do
                echo ">>> evaluate 第 $try/$MAX_TRY 次"
                if run_claude "$(load_step pali-evaluate evaluate)

$KNOWLEDGE

---本次评估的文献层次：$LCN（book=$LBOOK $TITLE）---

---待评估译文（book=$LBOOK，段 $CH，channel=$CHANNEL，已走完 translate/review/revise/harmonize）---
$EVAL_SRC

---任务---
按方法文档逐句评估，输出 markdown 总评（总分 / 信心 / 理由 / 问题清单）。
问题清单每条给出句 id 与原样摘出的问题片段；句 id 不要编造。
**不要改译文、不要输出 JSONL**——这是流水线的最后一步，只出报告。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 markdown，不要旁白或代码围栏。" > "$REPORTS/${TAG}_final.md" \
                    && valid_report "$REPORTS/${TAG}_final.md"; then
                    audit_chunk evaluate "$LBOOK" ok "$REPORTS/${TAG}_final.md" $PARAS; break
                fi
                [[ $try -eq $MAX_TRY ]] && { audit_chunk evaluate "$LBOOK" fail "$MAX_TRY 次未成" $PARAS; echo "  ⚠ evaluate 失败" >&2; }
            done
        done < <(chunk_list "$LBOOK" "$LPARAS")
    done < "$GROUPS_FILE"
fi

rm -f "$GROUPS_FILE"
echo "######## 完成：本文 $BOOK $START..$END（三层）→ channel $CHANNEL（报告在 $REPORTS/）########"
