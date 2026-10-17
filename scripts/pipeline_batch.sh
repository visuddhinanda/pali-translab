#!/usr/bin/env bash
#
# pipeline_batch.sh — 多层批量流水线：本文 / 义注 / 复注（论藏还有根本复注 / 随复注）
# 全部翻译，再跨层统稿。层次链见 scripts/_wp.py 的 LAYER_CHAIN
#
# 译文的唯一去处是 wikipali channel（覆盖式写入），**不落本地 jsonl**。
# 每一步都从 channel 读回上一步的结果，所以任何一步中断后重跑都能接上。
#
# ── 层次与父层 ────────────────────────────────────────────────────────────
#   mūla（本文）      → 只看巴利原文，独立译出
#   aṭṭhakathā（义注） → 父层是本文；义注里的**黑体是被解释词，引自本文**
#   ṭīkā（复注）      → 父层是义注；复注里的**黑体是被解释词，引自义注**
#
#   被解释词必须与所注文本**逐字同译**，否则读者看不出这条注在注哪个词——
#   随文注的对应关系就断了。所以翻译子层时，把父层的原文与译文一并注入作为对照。
#   坐标由 cs_para 逐层解析（见 scripts/layers.py），各层在不同的书里。
#   **做整章时加 --chapter**：各层按该层书自己的目录扩成完整一章。不加的话拿到的是
#   related 的段级范围，边界必然错位——注释章的首段常注的是上一章的本文。
#
# ── 步骤与粒度 ────────────────────────────────────────────────────────────
#   translate / review / revise / evaluate   按 chunk（累加巴利字符到 --chunk-chars）
#   harmonize                                **跨各层**一次统稿
#
#   写 channel 的是 translate / revise / harmonize；review 与 evaluate 不碰译文，
#   只在本地出报告 md。evaluate 排在最后：评的是走完全部改动步骤之后的定稿。
#
# ── 阶段 ──────────────────────────────────────────────────────────────────
#   阶段一  逐层（本文→义注→复注）逐 chunk 做 translate → review → revise
#   阶段二  跨层统稿：统一被解释词与术语语体，并修正通读发现的问题
#   阶段三  逐层逐 chunk 做 evaluate，出报告
#   阶段四  把本作业负责的每一层导出成 markdown（跑完一章立刻能看）
#
# 用法：
#   ./scripts/pipeline_batch.sh <本文book> <start_para> <end_para> \
#       [--channel <uid>] [--method <name>] \
#       [--steps translate,review,revise,harmonize,evaluate,export] \
#       [--layers mula,atthakatha,tika] [--chapter] [--chunk-chars N] [--max-paras N] \
#       [--tries N] [--model sonnet] [--nissaya] [--dry-run] [--force]
#
# 断点续传：
#   audit.log 按 <层book>:<段> 记账；重跑时整个 chunk 都做过就跳过。--force 强制重做。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 守护进程跑的是 workspace/projects/<name>/.snapshot 里的副本（见 run_daemon.snapshot_scripts），
# 那时 $SCRIPT_DIR/.. 并不是项目根，必须由 PROJECT_ROOT 指定。
PROJECT_DIR="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SKILLS="$PROJECT_DIR/.claude/skills"

# 两种调用形态：
#   作业模式（schema 2）：位置参数给本文的 book 与段范围，跑完这一章的整条流水线
#   单 task 模式（schema 3）：没有位置参数，坐标从 --plan 里那个 task 查
TASK=""
for _a in "$@"; do [[ "$_a" == "--task" || "$_a" == --task=* ]] && TASK="?" && break; done
if [[ -z "$TASK" ]]; then
    BOOK="${1:?用法: $0 <本文book> <start_para> <end_para> [选项]｜或 --plan <json> --task <id>}"
    START="${2:?缺少 start_para}"
    END="${3:?缺少 end_para}"
    shift 3
else
    BOOK=0; START=0; END=0                 # 查到 task 之后再填
fi

METHOD="default"
STEPS="translate,review,revise,harmonize,evaluate,export"
WANT_LAYERS="mula,atthakatha,tika,mulatika,anutika"   # 本卷没有的层自动跳过
MAX_TRY=3
MODEL="sonnet"
CHANNEL=""
NISSAYA=""
FORCE=""
DRYRUN=""
NO_CACHE=""
# 余量从这里留：实测模型一次约 100 行 JSONL 就被输出上限截断。复注短句多，
# 一句约 30 巴利字符，3,500 字符大致对应 110 句上下——比截断线略紧，留出余量。
CHUNK_CHARS=3500
MAX_PARAS=12
HARMONIZE_MAX=120      # 单批统稿的句数上限，超过就按层分批。**只在无计划时用**——
                       # 有 project 计划时，统稿单元与体量在规划阶段就按 cs_para 排好了。
                       # 实测模型一次最多吐约 100 行 JSONL 就被截断，
                       # 定 300 会让 200+ 句的作业三次重试全废——比截断更贵。
# 分块只卡**段数**与**巴利字符数**：字符多的段句子必然多，字符少的段句子必然少，
# 个别例外用余量兜住。为此专门去数句数要逐段调接口，不划算，也不该在规划期做。
CHAPTER=""
PLAN=""
JOB=""

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
        --harmonize-max) HARMONIZE_MAX="$2"; shift 2 ;;
        --chapter)     CHAPTER="--chapter"; shift ;;   # 各层扩成目录里的完整一章
        --plan)        PLAN="$2"; shift 2 ;;   # 作业计划 json（plan_jobs.py 产出）
        --job)         JOB="$2";  shift 2 ;;   # 计划里的作业 id
        --task)        TASK="$2"; shift 2 ;;   # 计划里的 task id（schema 3，单 task 模式）
        --task=*)      TASK="${1#*=}"; shift ;;
        --nissaya)     NISSAYA="--nissaya"; shift ;;   # 只给复核步骤，translate 永远不给
        --no-llm-cache) NO_CACHE=1; shift ;;   # 不读不写产物缓存，每步都真调模型
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
# 一项目一目录：计划文件就躺在项目目录里，其余产物（账本、报告、导出）都跟着它走。
# 没有 --plan 的临时跑（skill 直调）落到 workspace/adhoc，不去污染任何项目。
if [[ -n "$PLAN" ]]; then
    PROJ_HOME="$(cd "$(dirname "$PLAN")" && pwd)"
else
    PROJ_HOME="$WORK/adhoc"
fi
REPORTS="$PROJ_HOME/reports/$BOOK"
EXPORT_DIR="$PROJ_HOME/export"
# LLM 产物缓存：每次模型调用的产物都落在这里，重试直接复用（见 cached_claude）
LLM_CACHE="$PROJ_HOME/llm-cache"
AUDIT="$PROJ_HOME/audit.log"
GROUPS_FILE="$PROJ_HOME/.groups_job${JOB:-0}"
CHUNKS_FILE="$PROJ_HOME/.chunks_job${JOB:-0}"
mkdir -p "$REPORTS" "$EXPORT_DIR" "$PROJ_HOME"
touch "$AUDIT"

# translate 的两张便条：本轮期望的坐标清单、上一轮缺失的段号
IDS_FILE="$(mktemp)"; MISS_FILE="$(mktemp)"
trap 'rm -f "$IDS_FILE" "$MISS_FILE"' EXIT

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

# 账本只记 **task_id**：守护进程照它查表落状态，不再反推。
# book/para/step 只为人读，程序不认。
audit_task() {  # audit_task <task_id> <status> <detail> [book] [para范围]
    [[ -n "$DRYRUN" ]] && return 0      # dry-run 不记账，否则真跑时会误跳过
    printf '{"ts":"%s","task":"%s","status":"%s","detail":"%s","book":"%s","para":"%s","channel":"%s","method":"%s"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "${3:-}" "${4:-}" "${5:-}" "$CHANNEL" "$METHOD" >> "$AUDIT"
}

task_done() {  # task_done <task_id> —— 这个 task 已了结？
    # skip 与 ok 同样算了结：按规矩不该做的（如复注无缅文 nissaya 就不复核）
    # 不是待办事项，账上要留痕，否则续跑会一遍遍去做同一件不该做的事。
    [[ -n "$FORCE" ]] && return 1
    grep -qE "\"task\":\"$1\",\"status\":\"(ok|skip)\"" "$AUDIT"
}

has_step() { [[ ",$STEPS," == *",$1,"* ]]; }

FAILED_STEPS=0        # 任一步用尽重试仍失败 → 作业以非零退出，守护进程才会标 ❌ 并重排
fail_step() { FAILED_STEPS=$((FAILED_STEPS + 1)); echo "  ⚠ $1" >&2; }

# 报告必须是 markdown（首个非空行以 # 开头）。嵌套会话若改口要权限或吐旁白，
# 输出就不是报告——判失败重跑，不要把「请批准…」当成审稿意见存下来。
valid_report() {
    [[ -s "$1" ]] || return 1
    # 模型有时会把整份报告裹进 ```markdown 围栏——那是格式噪声，不是失败。
    # 先就地剥掉围栏，再判首个非空行是不是标题。
    python3 - "$1" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p, encoding='utf-8').read()
t = re.sub(r'^\s*```[a-zA-Z]*\s*\n', '', t)
t = re.sub(r'\n```\s*$', '\n', t)
open(p, 'w', encoding='utf-8').write(t)
sys.exit(0 if t.lstrip().startswith('#') else 1)
PY
}

# run_claude <提示词> —— 提示词走 **stdin**，不能当命令行参数传：
# Linux 单个参数上限 128KB，而父层对照动辄整章义注，几百段就爆
# 「Argument list too long」，三次重试全挂还悄悄退出 0。
# 另：数据已全部注入，禁掉工具，避免非交互下的权限请求污染输出。
# 模型没给出 JSONL 时，把**原始输出、stderr、退出码、提示词**留档到 workspace/logs/raw/。
# 「没有抽到任何 JSONL 行」是最高频的失败，但输出直接管进 wp_push 就没了，无从判断
# 是撞额度、是拒答、还是提示词太长——留档才诊断得了。
run_claude() {
    local f out err rc dst
    f="$(mktemp)"; out="$(mktemp)"; err="$(mktemp)"
    printf '%s' "$1" > "$f"
    claude -p --model "$MODEL" --tools "" < "$f" > "$out" 2> "$err"
    rc=$?
    cat "$err" >&2
    # 只在**真的没输出**或进程异常时留档。review / evaluate 出的是 markdown 报告，
    # 本来就没有 JSONL 行，按「无 JSONL」留档会全是误报。
    if [[ $rc -ne 0 || ! -s "$out" ]] || ! grep -q '[^[:space:]]' "$out" \
       || { ! grep -q '^[[:space:]]*{' "$out" && ! grep -q '^#' "$out"; }; then
        mkdir -p "$WORK/logs/raw"
        dst="$WORK/logs/raw/$(date +%m%d-%H%M%S)-$$-$RANDOM"
        {
            echo "rc=$rc  model=$MODEL  提示词 $(wc -c < "$f") 字节  输出 $(wc -c < "$out") 字节"
            echo "--- stderr ---"; cat "$err"
            echo "--- stdout ---"; cat "$out"
        } > "$dst.out"
        cp "$f" "$dst.prompt"
        echo "  ⚠ 模型没有输出（rc=$rc），现场已存 ${dst##*/}.out / .prompt" >&2
    fi
    # 撞额度时 claude 把提示写在 **stdout**，直接管进 wp_push 就进不了作业日志，
    # 守护进程扫日志判 RATE_LIMIT 因此永远匹配不到，白白把作业判成失败。
    # 这里把它复述到 stderr（= 作业日志），守护进程才看得见。
    # 文案不止一种：「resets Sep 1, 8pm」里 resets 后面跟的是月份不是数字，
    # 早先的 `resets [0-9]` 认不出来，70 个作业因此被当成普通失败一路重试到废。
    if grep -qiE "session limit|usage limit|rate limit|limit reached|weekly limit|5-hour limit|hit your|resets " "$out" "$err"; then
        echo "  🚦 撞到额度限制：$(tr -d '\n' < "$out" | head -c 200)" >&2
    fi
    cat "$out"
    rm -f "$f" "$out" "$err"
    return $rc
}

# ══════════ LLM 产物本地缓存 ══════════
# 模型产物一律落盘，键是**这一步的任务坐标**（chunk id + 步骤 + 层 book + 段），由调用方给。
# 重试时先看缓存：命中就把那份产物重新喂给 wp_push，**不再调模型**。
# 服务端写入 504 把一批打断是最常见的失败，重新生成只会换个说法、不会更对，
# 还要再花一次模型调用——所以重试复用产物，只重做写入。
#
# 只缓存**看起来是产物**的输出（有 JSONL 行或 markdown 标题）。OAuth 过期、撞额度
# 那类空输出或纯提示文本不入缓存，否则下次重跑会一直吃到空壳，永远好不了。
# 键里带段范围：translate 补缺句时只译剩下那几段，段变了键就变，不会错拿整批的旧产物。
cache_path() {
    # 文件名带模型：换模型重跑是「想要一份新产物」，不该吃到上一个模型的缓存
    printf '%s/%s__%s.out' "$LLM_CACHE" "$MODEL" \
        "$(printf '%s' "$1" | tr -c 'A-Za-z0-9._:-' '_')"
}

cached_claude() {
    local key="$1" prompt="$2" f tmp rc
    f="$(cache_path "$key")"
    if [[ -z "$NO_CACHE" && -s "$f" ]]; then
        echo "  ♻ 复用缓存产物 ${f##*/}（$(wc -c < "$f") 字节，不再调模型）" >&2
        cat "$f"
        return 0
    fi
    tmp="$(mktemp)"; rc=0
    run_claude "$prompt" > "$tmp" || rc=$?
    # 产物判定与 run_claude 的留档判定同一套：有 JSONL 行或 markdown 标题才算
    if [[ -z "$NO_CACHE" && $rc -eq 0 ]] \
       && grep -qE '^[[:space:]]*\{|^[[:space:]]*#' "$tmp"; then
        mkdir -p "$LLM_CACHE"
        cp "$tmp" "$f.part" && mv "$f.part" "$f"
    fi
    cat "$tmp"
    rm -f "$tmp"
    return $rc
}

# ══════════ 五个步骤的提示词 ══════════
# 提示词只写一份，两条执行路径共用：
#   · 作业模式（schema 2，--job）——下面的阶段一～四按章跑完整条流水线
#   · 单 task 模式（schema 3，--task）——按阶段推进时一次只做一个 task
# 参数是缓存键（见 cached_claude）；正文引用的 $KNOWLEDGE / $SRC / $N 等是调用处的变量。

emit_translate() {
    cached_claude "$1" "$(load_step pali-translate translate)

$KNOWLEDGE

---本次要译的文献层次：$LCN（book=$LBOOK $TITLE）---
$PARENT_BLOCK$DONE_CTX
---待翻译（book=$LBOOK，段 $TODO，共 $N 句，按段落顺序排列）---
pali 里的 \`**词**\` 是原文的黑体；在义注/复注里它就是**被解释词**，译文要保留 \`**…**\` 标记。
$SRC

---任务---
把上面 $N 句 pali 逐句译为现代书面汉语。这些段落是连续上下文，术语与语体要通篇一致。
**只输出 $N 行 JSONL，与输入逐句一一对应**，不得合并、拆分、增删或漏译。
最容易漏的是这三种，一句也不能少：**偈颂的每一行**（一行就是一句，哪怕只有几个词、哪怕
与上一行句法相连）、**「…niṭṭhitā / …vaggo」这类结语与品末标记**、**重复定型句的省略号段**
（「…pe…」「…peyyālaṃ」）。输出前请核对行数是否正好 $N 行。
反过来，**只有标点、没有巴利词的句子不要输出**（pali 形如 \"**.**\" 的那种），它们不算漏译。
每行：{\"id\": 同输入, \"zh\": \"你的译文\", \"confidence\": 0-100}
坐标以输入为准，不要编造 id。标点用中文全角；引号用全角 “” ‘’，不要出现 ASCII 引号。
不确定时给出最好的一个译法并调低该句 confidence，**不要在译文里留任何工作标记**（候选、待定、问号之类）。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 JSONL，不要旁白或代码围栏。"
}

emit_review() {
    cached_claude "$1" "$(load_step pali-review review)

$KNOWLEDGE

---本次审的文献层次：$LCN（book=$LBOOK $TITLE）---
$PARENT_BLOCK
$ATT_REF
---待审译文（book=$LBOOK，段 $CH，channel=$CHANNEL）---
$REVIEW_SRC

---任务---
按方法文档逐句审查，输出 markdown 审稿意见。
本层若有父层对照，**第一项就查被解释词是否与父层译文逐字相同**，不同即必改项。
整个 chunk 一起审，跨段的术语与语体不一致也要列出。无问题的句子不必列出。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 markdown，不要旁白或代码围栏。"
}

emit_revise() {
    cached_claude "$1" "$(load_step pali-revise revise)

$KNOWLEDGE

---本次修订的文献层次：$LCN（book=$LBOOK $TITLE）---
$PARENT_BLOCK
$ATT_REF
---现有译文与资源（book=$LBOOK，段 $CH）---
$REVIEW_SRC

---审稿意见---
$(read_or_empty "$REVIEW_MD")

---任务---
按审稿意见修正译文。**只输出你真正改动过的句子**，每行：{\"id\": 同输入, \"zh\": \"修正后译文\", \"confidence\": 0-100}
写入是按坐标覆盖的，没提交的句子原样保留——所以**不要回传未改动的句子**（至多 $N 行）。一句都没改就只输出一行 {\"no_change\": true}——不要输出空。
未被审稿意见提及的句子不要顺手改。
原文里的黑体是**被解释词**（义注引自本文、复注引自义注）。译文里这些词必须照样用双星号包起来——不要改成引号、不要去掉。它是读者辨认「这条注在注哪个词」的唯一线索，也是逐字同译的机械核查依据。
坐标不要编造。译文里不要留任何工作标记。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 JSONL，不要旁白或代码围栏。"
}

emit_harmonize() {
    cached_claude "$1" "$(load_step pali-harmonize harmonize)

$KNOWLEDGE

---待统稿（每块以 === 开头，标明 book、段范围，以及它是只读对照还是要改的那一层）---
$USRC

---任务---
$WHAT
每处改动都要有具体理由（对齐、一致性，或明确的错误）；**不要为「读起来更顺」而改**，不要重译。
原文里的黑体是**被解释词**，译文里必须照样用双星号包起来——不要改成引号、不要去掉。
**只输出你真正改动过的句子**：{\"id\": 同输入, \"zh\": \"统稿后译文\"}
写入是按坐标覆盖的，没提交的句子原样保留——不要回传未改动的句子（至多 $UN 行）。一句都没改就只输出一行 {\"no_change\": true}——不要输出空。
id 照抄输入，不要编造坐标。译文里不要留任何工作标记。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 JSONL，不要旁白或代码围栏。"
}

emit_evaluate() {
    cached_claude "$1" "$(load_step pali-evaluate evaluate)

$KNOWLEDGE

---本次评估的文献层次：$LCN（book=$LBOOK $TITLE）---

---待评估译文（book=$LBOOK，段 $CH，channel=$CHANNEL，已走完 translate/review/revise/harmonize）---
$EVAL_SRC

---任务---
按方法文档逐句评估，输出 markdown 总评（总分 / 信心 / 理由 / 问题清单）。
问题清单每条给出句 id 与原样摘出的问题片段；句 id 不要编造。
**不要改译文、不要输出 JSONL**——这是流水线的最后一步，只出报告。
所需数据已全部注入上文，不要试图调用任何工具取数。
只输出 markdown，不要旁白或代码围栏。"
}

count_mula() { printf '%s' "$1" | grep -c '^{"layer":"mula"' || true; }
count_zh()   { printf '%s' "$1" | grep -c '^{"layer":"mula".*"zh":' || true; }
count_nis()  { printf '%s' "$1" | grep -c '"nissaya":' || true; }

layer_cn() {
    case "$1" in
        mula)       echo "本文（mūla）" ;;
        atthakatha) echo "义注（aṭṭhakathā）" ;;
        tika)       echo "复注（ṭīkā）" ;;
        mulatika)   echo "根本复注（mūlaṭīkā）" ;;
        anutika)    echo "随复注（anuṭīkā）" ;;
        *)          echo "$1" ;;
    esac
}

# 复核各步都从 channel 读回译文——**channel 就是流水线各步之间的交接处**
# （见 ARCHITECTURE「数据流」）。两条执行路径都要用，所以定义放在这里。
pull_review() {
    python3 "$SCRIPT_DIR/wp_pull.py" --book "$1" --para "$2" $NISSAYA --channel "$CHANNEL"
}

# ══════════ 单 task 模式（schema 3）══════════
# 按阶段推进时一次只做一个 task：坐标、父层对照、统稿 spans 全部从计划里查，
# 执行期不再解析层次、不再重切块——边界在规划期就定死了（见 plan_scan.py）。
# 提示词与作业模式共用上面那五个 emit_* 函数，只有「取数据、写回、记账」这一圈在这里。
if [[ -n "$TASK" ]]; then
    [[ -n "$PLAN" ]] || { echo "--task 要和 --plan 一起给" >&2; exit 2; }
    eval "$(python3 - "$PLAN" "$TASK" <<'PYTASK'
import json, shlex, sys
plan = json.load(open(sys.argv[1], encoding='utf-8'))
tid = sys.argv[2]
t = next((x for x in plan.get("tasks") or [] if x["id"] == tid), None)
if t is None:
    print(f'echo "计划里没有 task {tid}" >&2; exit 2')
    sys.exit(0)
LCN = {"mula": "本文 mūla", "atthakatha": "义注 aṭṭhakathā", "tika": "复注 ṭīkā",
       "mulatika": "根本复注 mūlaṭīkā", "anutika": "随复注 anuṭīkā"}
chunk = None
for m in plan.get("layers", []):
    for ch in m.get("chunks", []):
        if tid.startswith(ch["id"] + ":"):
            chunk = ch
out = []


def put(k, v):
    out.append(f'{k}={shlex.quote("" if v is None else str(v))}')


def paras(spans):
    return ",".join(str(p) for sp in spans
                    for p in range(int(sp["start"]), int(sp["end"]) + 1))


put("T_STEP", t["step"])
put("T_LAYER", t.get("layer", ""))
put("T_BOOK", t.get("book") or "")
put("T_START", t.get("start") or "")
put("T_END", t.get("end") or "")
put("T_TITLE", t.get("title", ""))
put("T_LCN", LCN.get(t.get("layer", ""), t.get("layer", "")))
put("T_SENTS", t.get("sents") or 0)
# export 用 --from/--to，段列表对它没用（整层八百多段，展开只是把命令行撑长）
if t.get("book") and t.get("start") and t["step"] != "export":
    put("T_PARAS", paras([{"start": t["start"], "end": t["end"]}]))
else:
    put("T_PARAS", "")
pb = (chunk or {}).get("parent") or {}
put("T_PBOOK", pb.get("book") or "")
put("T_PPARAS", paras(pb.get("spans", [])))
ar = (chunk or {}).get("att_ref") or {}
put("T_ABOOK", ar.get("book") or "")
put("T_APARAS", paras(ar.get("spans", [])))
# 统稿是**相邻两层配对**：write = 要改的子层，read = 只读的父层对照。
# 旧结构只有 spans（三层一起、都可写），兼容着读一下。
w = t.get("write") or t.get("spans") or []
rd = t.get("read") or []
put("T_WRITE", " ".join(f'{sp["book"]}:{paras([sp])}' for sp in w))
put("T_READ", " ".join(f'{sp["book"]}:{paras([sp])}' for sp in rd))
put("T_PAIR", "+".join(t.get("pair") or []))
put("T_NBOOK", len({sp["book"] for sp in w + rd}))
print("\n".join(out))
PYTASK
)"

    # 这个 task 的坐标就位，报告路径跟着它的 book 走
    LBOOK="$T_BOOK"; LAYER="$T_LAYER"; LCN="$T_LCN"; TITLE="$T_TITLE"
    TODO="$T_PARAS"; CH="$T_PARAS"
    CHID="$TASK"
    [[ -n "$T_BOOK" ]] && REPORTS="$PROJ_HOME/reports/$T_BOOK"
    mkdir -p "$REPORTS"
    TAG="$T_BOOK-$T_START-$T_END"
    REVIEW_MD="$REPORTS/${TAG}_review.md"
    DONE_CTX=""; PARENT_BLOCK=""; ATT_REF=""

    echo "######## task $TASK｜$T_STEP｜$T_LCN $T_BOOK:$T_START-$T_END｜$T_TITLE ########"
    echo "channel=$CHANNEL｜method=$METHOD｜计划 $PLAN"

    if [[ -z "$FORCE" ]] && task_done "$TASK"; then
        echo "  跳过：$TASK 已了结（--force 可强制重做）"; exit 0
    fi

    # 父层对照：翻译/复核子层时，黑体被解释词必须与父层译文逐字相同
    if [[ -n "$T_PBOOK" && -n "$T_PPARAS" ]]; then
        PARENT_TXT="$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$T_PBOOK" --para "$T_PPARAS" --channel "$CHANNEL" || true)"
        if [[ "$(count_zh "$PARENT_TXT")" -gt 0 ]]; then
            PARENT_BLOCK="
---父层对照（book=$T_PBOOK，段 $T_PPARAS；pali 为父层原文，zh 为**已定稿的父层译文**）---
本层的**黑体被解释词引自父层**。凡是黑体词，译法必须与下面父层译文中同一处**逐字相同**，
一个字都不能改——不一致读者就看不出这条注在注哪个词。父层没提到的词才由你自己定译法。
$PARENT_TXT
"
        else
            echo "  ⚠ 父层 $T_PBOOK:$T_PPARAS 还没有译文，本层无法对齐被解释词" >&2
        fi
    fi

    # 义注参考：只给本文层的复核步骤用（**义注定释义**），translate 永远不给
    if [[ "$T_LAYER" == "mula" && -n "$T_ABOOK" && -n "$T_APARAS" \
          && ( "$T_STEP" == "review" || "$T_STEP" == "revise" ) ]]; then
        ATT_REF="
---义注参考（校对用；本 task **不翻译**义注）---
$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$T_ABOOK" --para "$T_APARAS" --channel "$CHANNEL" || true)
"
    fi

    case "$T_STEP" in
    translate)
        for ((try = 1; try <= MAX_TRY; try++)); do
            SRC=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$T_BOOK" --para "$TODO" || true)
            # 期望清单与句数**只算真有巴利词的句子**：句子表会把孤立的标点切成
            # 独立句（实测有 pali 就是 `**.**` 的），模型不会为它输出译文，
            # 按「缺句」算会让整块必然重试到失败。见 scripts/pali_ids.py
            N=$(printf '%s' "$SRC" | python3 "$SCRIPT_DIR/pali_ids.py" "$IDS_FILE")
            if [[ "$N" -eq 0 ]]; then
                echo "  跳过：$T_BOOK:$TODO 没有可译的巴利句"
                audit_task "$TASK" skip "无可译巴利句" "$T_BOOK" "$T_START-$T_END"; exit 0
            fi
            echo ">>> translate 第 $try/$MAX_TRY 次（$N 句 / $(echo ${TODO//,/ } | wc -w) 段）"
            : > "$MISS_FILE"
            set +e
            emit_translate "$TASK" \
                | python3 "$SCRIPT_DIR/wp_push.py" --book "$T_BOOK" --para "$TODO" \
                    --channel "$CHANNEL" --expect "$N" --expect-ids "$IDS_FILE" \
                    --missing-out "$MISS_FILE" $DRYRUN
            PUSH_RC=${PIPESTATUS[1]}
            set -e
            if [[ "$PUSH_RC" -eq 0 ]]; then
                audit_task "$TASK" ok "$N 句" "$T_BOOK" "$T_START-$T_END"; exit 0
            fi
            # 退出码 2 = 能写的都写进去了，只差几段：下一轮只补缺的
            if [[ "$PUSH_RC" -eq 2 && -s "$MISS_FILE" && $try -lt $MAX_TRY ]]; then
                TODO="$(tr -d '[:space:]' < "$MISS_FILE")"
                echo "  只补缺失的段：$TODO"
                continue
            fi
        done
        audit_task "$TASK" fail "$MAX_TRY 次未成" "$T_BOOK" "$T_START-$T_END"
        echo "######## 未完成：task $TASK ########" >&2; exit 1
        ;;
    review|evaluate)
        SRC_TXT=$(pull_review "$T_BOOK" "$CH" || true)
        if [[ "$(count_zh "$SRC_TXT")" -eq 0 ]]; then
            echo "  跳过：channel 上 $T_BOOK:$T_START-$T_END 还没有译文"
            audit_task "$TASK" skip "channel 上还没有译文" "$T_BOOK" "$T_START-$T_END"; exit 0
        fi
        # 复注的 review 全靠缅文 nissaya 定词法，没有它只剩自说自话
        if [[ "$T_STEP" == "review" && "$T_LAYER" == "tika" && -n "$NISSAYA" \
              && "$(count_nis "$SRC_TXT")" -eq 0 ]]; then
            echo "  跳过 review：复注 $T_BOOK:$T_START-$T_END 没有缅文 nissaya"
            audit_task "$TASK" skip "复注无缅文 nissaya" "$T_BOOK" "$T_START-$T_END"; exit 0
        fi
        if [[ "$T_STEP" == "review" ]]; then
            REVIEW_SRC="$SRC_TXT"; OUT_MD="$REVIEW_MD"
        else
            EVAL_SRC="$SRC_TXT"; OUT_MD="$REPORTS/${TAG}_final.md"
        fi
        for ((try = 1; try <= MAX_TRY; try++)); do
            echo ">>> $T_STEP 第 $try/$MAX_TRY 次"
            if [[ "$T_STEP" == "review" ]]; then
                emit_review "$TASK" > "$OUT_MD" && valid_report "$OUT_MD" && {
                    audit_task "$TASK" ok "$OUT_MD" "$T_BOOK" "$T_START-$T_END"; exit 0; }
            else
                emit_evaluate "$TASK" > "$OUT_MD" && valid_report "$OUT_MD" && {
                    audit_task "$TASK" ok "$OUT_MD" "$T_BOOK" "$T_START-$T_END"; exit 0; }
            fi
        done
        audit_task "$TASK" fail "$MAX_TRY 次未成（输出不是报告）" "$T_BOOK" "$T_START-$T_END"
        echo "######## 未完成：task $TASK ########" >&2; exit 1
        ;;
    revise)
        REVIEW_SRC=$(pull_review "$T_BOOK" "$CH" || true)
        if [[ "$(count_zh "$REVIEW_SRC")" -eq 0 ]]; then
            echo "  跳过：channel 上 $T_BOOK:$T_START-$T_END 还没有译文"
            audit_task "$TASK" skip "channel 上还没有译文" "$T_BOOK" "$T_START-$T_END"; exit 0
        fi
        if [[ ! -s "$REVIEW_MD" ]]; then
            echo "  跳过 revise：没有审稿意见（$REVIEW_MD）"
            audit_task "$TASK" skip "没有审稿意见" "$T_BOOK" "$T_START-$T_END"; exit 0
        fi
        N=$(count_mula "$REVIEW_SRC")
        for ((try = 1; try <= MAX_TRY; try++)); do
            echo ">>> revise 第 $try/$MAX_TRY 次"
            set +e
            emit_revise "$TASK" \
                | python3 "$SCRIPT_DIR/wp_push.py" --book "$T_BOOK" --para "$CH" \
                    --channel "$CHANNEL" --at-most "$N" --allow-empty $DRYRUN
            PUSH_RC=${PIPESTATUS[1]}
            set -e
            [[ "$PUSH_RC" -eq 0 ]] && {
                audit_task "$TASK" ok "至多 $N 句" "$T_BOOK" "$T_START-$T_END"; exit 0; }
        done
        audit_task "$TASK" fail "$MAX_TRY 次未成" "$T_BOOK" "$T_START-$T_END"
        echo "######## 未完成：task $TASK ########" >&2; exit 1
        ;;
    harmonize)
        # 相邻两层配对：$T_READ 是父层（**只读**），$T_WRITE 是子层（要改的）。
        # 父层只读的理由见 plan_scan.harmonize_pairs——并列的几部复注都以同一部
        # 义注为基准，谁都能改义注的话，几套统稿会轮流改同一批句子、互相打架。
        USRC=""; UN=0
        for SP in $T_READ; do
            UB="${SP%%:*}"; UR="${SP#*:}"
            T=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$UB" --para "$UR" --channel "$CHANNEL" || true)
            USRC="$USRC
=== 父层对照〔只读，一句都不要输出〕 book=$UB  段 $UR ===
$T
"
        done
        for SP in $T_WRITE; do
            UB="${SP%%:*}"; UR="${SP#*:}"
            T=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$UB" --para "$UR" --channel "$CHANNEL" || true)
            UN=$(( UN + $(count_mula "$T") ))
            USRC="$USRC
=== 待统稿〔要改的就是这一层〕 book=$UB  段 $UR ===
$T
"
        done
        if [[ "$UN" -eq 0 ]]; then
            echo "  跳过：这个统稿单元还没有译文"
            audit_task "$TASK" skip "没有译文"; exit 0
        fi
        if [[ -n "$T_READ" ]]; then
            WHAT="两层同看，**被解释词与父层逐字对齐**是最高优先（下一层的黑体引自它的上一层：义注引本文、复注引义注、随复注引根本复注）；顺带统一术语与语体。父层标了〔只读〕，**一句都不要输出**——它的问题不在这一步修。"
        else
            WHAT="这一单元没有父层对照（独立作品，或在父层里没有 cs 对应）。只看这一层，通读求**同层一致**——术语、语体、称谓、重复定型句同译；不要凭想象改被解释词的译法。"
        fi
        echo ">>> 统稿 $TASK（$T_PAIR｜待改 $UN 句 / 计划 $T_SENTS 句）"
        UOUT="$(mktemp)"; OK=0
        for ((try = 1; try <= MAX_TRY; try++)); do
            if emit_harmonize "$TASK" > "$UOUT"; then
                PUSH_OK=1
                # **只写子层**：父层那几段不在 --para 范围里，模型若回传了
                # 父层的句子，wp_push 会按 --ignore-foreign 丢弃
                for SP in $T_WRITE; do
                    UB="${SP%%:*}"; UR="${SP#*:}"
                    NL=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$UB" --para "$UR" | grep -c '^{' || true)
                    python3 "$SCRIPT_DIR/wp_push.py" --book "$UB" --para "$UR" \
                        --channel "$CHANNEL" --at-most "$NL" --allow-empty --ignore-foreign $DRYRUN \
                        < "$UOUT" || PUSH_OK=0
                done
                [[ "$PUSH_OK" -eq 1 ]] && { OK=1; break; }
            fi
        done
        rm -f "$UOUT"
        [[ "$OK" -eq 1 ]] && { audit_task "$TASK" ok "$T_PAIR $T_WRITE"; exit 0; }
        audit_task "$TASK" fail "用尽 $MAX_TRY 次"
        echo "######## 未完成：task $TASK ########" >&2; exit 1
        ;;
    export)
        if [[ -n "$DRYRUN" ]]; then
            echo "  --dry-run：不导出"; exit 0
        fi
        if python3 "$SCRIPT_DIR/export_markdown.py" --book "$T_BOOK" --channel "$CHANNEL" \
               --from "$T_START" --to "$T_END" --out "$EXPORT_DIR" --model claude-opus-5; then
            audit_task "$TASK" ok "$EXPORT_DIR" "$T_BOOK" "$T_START-$T_END"; exit 0
        fi
        audit_task "$TASK" fail "导出失败" "$T_BOOK" "$T_START-$T_END"
        echo "######## 未完成：task $TASK ########" >&2; exit 1
        ;;
    *)
        echo "不认识的步骤：$T_STEP" >&2; exit 2
        ;;
    esac
fi

# ---------- 解析各层坐标 ----------
echo "######## 本文 book=$BOOK $START..$END → channel $CHANNEL｜method=$METHOD ########"
echo "steps=$STEPS｜layers=$WANT_LAYERS"
echo "解析各层坐标（cs_para）..."

if [[ -n "$PLAN" ]]; then
    # 计划模式：own=1 的组本作业负责翻译，own=0 的只读参考（归别的作业翻译）
    # GROUPS_FILE 用上面按项目算好的那个（$PROJ_HOME/.groups_job<JOB>），
    # **不要再指回公共 workspace/**：两个项目都有 job 5，会写同一个文件，
    # 层坐标串台之后可能拿着别的项目的 book 和段去写 channel。
    SCRIPT_DIR="$SCRIPT_DIR" python3 - "$PLAN" "$JOB" "$WANT_LAYERS" > "$GROUPS_FILE" <<'PY'
import json, sys, os
sys.path.insert(0, os.environ["SCRIPT_DIR"])
from _wp import parent_layer
plan, jid, want = json.load(open(sys.argv[1], encoding='utf-8')), int(sys.argv[2]), set(sys.argv[3].split(','))
job = next(j for j in plan["pipelines"] if j["id"] == jid)
# 本流水线负责翻译的层在 layers[]（含 mula）；ref[] 是只读参考，归别的流水线翻译
own = [e for e in job.get("layers", []) if e["layer"] != "mula"]
job = {**job, "own": own, "ref": job.get("ref", [])}
# 前置作业（注释书开头，与本文无对应）没有本文层：mula 为 None，
# 此时义注就是最上层，父层为空，统稿是义注↔复注。
mula = job["mula"]
rows = ([(mula, 1)] if mula else []) + [(e, 1) for e in job["own"]] + [(e, 0) for e in job["ref"]]
# 父层按 _wp.LAYER_CHAIN 在**本作业实有的层**里回退一格：经藏是复注→义注，
# 论藏是随复注→根本复注→义注。写死"非本文非义注一律以义注为父"会让随复注对错父层。
present = {e["layer"] for e, _o in rows}
by_layer = {}
for e, _o in rows:
    by_layer.setdefault(e["layer"], []).append(e)
for e, own in rows:
    if e["layer"] not in want:
        continue
    pl = parent_layer(e["layer"], present)
    parent = by_layer[pl][0]["book"] if pl else "-"
    title = (e.get("title") or "-").replace(" ", "_")
    print(e["layer"], e["book"], f"{e['start']}-{e['end']}", parent, title, own)
PY
    # 分块表：`<book> <chunk_id> <段,列表>`。**边界由计划定死**，执行期不再重切——
    # 重切一遍就会与计划错位一两段，task 编号也就对不上了。
    python3 - "$PLAN" "$JOB" > "$CHUNKS_FILE" <<'PY'
import json, sys
plan, jid = json.load(open(sys.argv[1], encoding='utf-8')), int(sys.argv[2])
job = next(j for j in plan["pipelines"] if j["id"] == jid)
for lay in job.get("layers", []):
    for ch in lay.get("chunks", []):
        paras = ",".join(str(p) for p in range(ch["start"], ch["end"] + 1))
        print(ch["book"], ch["id"], paras)
PY
else
    LAYERS_JSON="$PROJ_HOME/layers_${BOOK}_${START}-${END}.json"
    python3 "$SCRIPT_DIR/layers.py" --book "$BOOK" --para "$START-$END" $CHAPTER > "$LAYERS_JSON"

    # 每行一个组："层 书号 段列表 父书号(无则 -) 标题 是否本作业翻译"
    python3 - "$LAYERS_JSON" "$WANT_LAYERS" > "$GROUPS_FILE" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding='utf-8'))
want = set(sys.argv[2].split(','))
for g in data["groups"]:
    if g["layer"] not in want or not g["paras"]:
        continue
    print(g["layer"], g["book"], ",".join(str(p) for p in g["paras"]),
          g["parent_book"] if g["parent_book"] else "-",
          (g.get("chapter") or g["title"] or "-").replace(" ", "_"), 1)
PY
fi

[[ -s "$GROUPS_FILE" ]] || { echo "没解析出任何层次，无事可做" >&2; exit 1; }

while read -r L B P PB T OWN; do
    [[ "$OWN" == 1 ]] && M="译" || M="参考"
    R="${P%%,*}"; R2="${P##*,}"
    [[ "$R" == "$R2" ]] && SHOW="$R" || SHOW="${R%%-*}-${R2##*-}"
    echo "  [$M] $(layer_cn "$L")  $B:$SHOW  父层=$PB  $T"
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

# chunk_list <book> <段列表> —— 按巴利字符数切 chunk。
# 字符数来自一次 `wikipali paras`（整本书缓存），不再逐段拉正文——
# 那是每个作业启动时最大的一块固定开销。
chunk_list() {
    python3 - "$SCRIPT_DIR" "$1" "$2" "$CHUNK_CHARS" "$MAX_PARAS" <<'PY'
import sys
script_dir, book, spec, budget, max_paras = sys.argv[1:]
sys.path.insert(0, script_dir)
from _wp import chunk_paras, parse_paras
for c in chunk_paras(int(book), parse_paras(spec), int(budget), int(max_paras)):
    print(",".join(str(x) for x in c))
PY
}

# pull_review <book> <段列表> —— 复核输入：现有译文 + pali (+ nissaya)
if [[ -z "$PLAN" ]]; then
    # 临时跑没有计划，就地切一次，id 用 adhoc 前缀——它不进任何项目的账
    : > "$CHUNKS_FILE"
    while read -r L B P _PB _T OWN; do
        [[ "$OWN" == 1 ]] || continue
        n=0
        while read -r CH; do
            n=$((n + 1)); echo "$B adhoc.$B.$n $CH" >> "$CHUNKS_FILE"
        done < <(chunk_list "$B" "$P")
    done < "$GROUPS_FILE"
fi



# ══════════ 阶段一：逐层 translate → review → revise ══════════
while read -r LAYER LBOOK LPARAS PBOOK TITLE OWN; do
    [[ -z "${LAYER:-}" ]] && continue
    [[ "${OWN:-1}" == 1 ]] || continue          # 只读参考层不在这里翻译
    LCN="$(layer_cn "$LAYER")"
    echo "╔══════ 阶段一 $LCN  book=$LBOOK  $TITLE ══════╗"

    # 本文层在 review/revise 时参考义注原文（只参考，不翻译；见用户约定）
    ATT_REF=""
    if [[ "$LAYER" == "mula" ]]; then
        ASPEC="$(awk '$1=="atthakatha" {printf "%s ", $2" "$3}' "$GROUPS_FILE")"
        if [[ -n "$ASPEC" ]]; then
            ATT_REF="
---义注参考（校对用；本作业**不翻译**义注）---
$(set -- $ASPEC; while [[ $# -ge 2 ]]; do python3 "$SCRIPT_DIR/wp_pull.py" --book "$1" --para "$2" --channel "$CHANNEL" || true; shift 2; done)
"
        fi
    fi

    # 父层对照：翻译子层时要保证被解释词与父层逐字同译
    PARENT_BLOCK=""
    if [[ "$PBOOK" != "-" ]]; then
        if [[ -n "$PLAN" || -n "$CHAPTER" ]]; then
            # 计划/整章模式：父层对照给该父书的**全部**组（own + ref）——
            # 被解释词可能引自父层本章任何一处，逐段映射反而会漏
            PSPEC="$(awk -v b="$PBOOK" '$2==b {printf "%s%s", (n++?",":""), $3}' "$GROUPS_FILE")"
        else
            PSPEC="$(parent_spec "$LBOOK" "$LPARAS")"
        fi
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

    while read -r CB CHID CH; do
        [[ "$CB" == "$LBOOK" && -n "$CH" ]] || continue
        PARAS="${CH//,/ }"
        FIRST="${CH%%,*}"; LAST="${CH##*,}"
        TAG="$LBOOK-$FIRST-$LAST"
        echo "════════ $LCN $LBOOK:$FIRST-$LAST（$CHID）════════"

        SRC=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$CH" || true)
        N=$(count_mula "$SRC")
        if [[ "$N" -eq 0 ]]; then
            echo "  跳过（无巴利原文）"; continue
        fi

        # ---------- translate ----------
        # 只译本 chunk 里还没译过的段——已译过的不重译，但作为上下文注入保证术语一致
        TODO="$CH"
        task_done "$CHID:translate" && TODO=""
        if has_step translate && [[ -n "$TODO" ]]; then
            for ((try = 1; try <= MAX_TRY; try++)); do
                # 每轮都按**本轮要译的段**重新取原文与上下文：第一轮是整个 TODO，
                # 之后只剩上一轮缺的那几段（见下面的退出码 2）
                SRC=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$TODO" || true)
                # 只算真有巴利词的句子，纯标点句不计入漏译（见 scripts/pali_ids.py）
                N=$(printf '%s' "$SRC" | python3 "$SCRIPT_DIR/pali_ids.py" "$IDS_FILE")
                [[ "$N" -eq 0 ]] && { echo "  跳过 translate（$TODO 没有可译的巴利句）"; break; }
                DONE_CTX=""
                if [[ "$TODO" != "$CH" ]]; then
                    echo "  （本 chunk 只译 $TODO，其余已有译文，作术语对照注入）"
                    DONE_CTX="
---同一 chunk 内已有的译文（**只作术语与语体对照，不要重复输出**）---
$(pull_review "$LBOOK" "$CH" || true)
"
                fi

                echo ">>> translate 第 $try/$MAX_TRY 次（$N 句 / $(echo ${TODO//,/ } | wc -w) 段）"
                : > "$MISS_FILE"
                # 这条管道的非零退出是**正常控制流**（2 = 缺句），不能让 set -e 掐掉脚本
                set +e
                emit_translate "$CHID:translate:$LBOOK:$TODO" \
                    | python3 "$SCRIPT_DIR/wp_push.py" --book "$LBOOK" --para "$TODO" \
                        --channel "$CHANNEL" --expect "$N" --expect-ids "$IDS_FILE" \
                        --missing-out "$MISS_FILE" $DRYRUN
                PUSH_RC=${PIPESTATUS[1]}
                set -e

                if [[ "$PUSH_RC" -eq 0 ]]; then
                    audit_task "$CHID:translate" ok "$N 句" "$LBOOK" "$FIRST-$LAST"; break
                fi

                # 退出码 2 = 能写的都写进去了，只有几句没提交。整块重译是浪费——
                # 下一轮只补缺失那几段。
                if [[ "$PUSH_RC" -eq 2 && -s "$MISS_FILE" ]]; then
                    MISS="$(tr -d '[:space:]' < "$MISS_FILE")"
                    if [[ $try -lt $MAX_TRY ]]; then
                        echo "  只补缺失的段：$MISS（原 $TODO）"
                        TODO="$MISS"; continue
                    fi
                    audit_task "$CHID:translate" fail "$MAX_TRY 次仍缺 $MISS" "$LBOOK" "$FIRST-$LAST"
                    fail_step "translate 缺句（$CHID，段 $MISS）"; break
                fi

                [[ $try -eq $MAX_TRY ]] && { audit_task "$CHID:translate" fail "$MAX_TRY 次未成" "$LBOOK" "$FIRST-$LAST"; fail_step "translate 失败（$CHID）"; }
            done
        fi

        # 后续步骤按整个 chunk 走（补译只影响 translate 的范围）
        N=$(count_mula "$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$CH" || true)")

        # review / revise 都要有译文才有意义
        REVIEW_SRC=""
        if has_step review || has_step revise; then
            REVIEW_SRC=$(pull_review "$LBOOK" "$CH" || true)
            if [[ "$(count_zh "$REVIEW_SRC")" -eq 0 ]]; then
                echo "  跳过复核（channel 上 $LBOOK:$FIRST-$LAST 还没有译文）"
                REVIEW_SRC=""
            fi
            # 复注层没有缅文 nissaya 就不复核：复注的 review 全靠词级基准，
            # 缺了它只剩自说自话，改出来的是「更顺」而不是「更对」。
            # 本文/义注不受此限——它们还有义注可依。该 chunk 的 translate、
            # harmonize、evaluate 照常。
            if [[ -n "$REVIEW_SRC" && "$LAYER" == "tika" && -n "$NISSAYA" \
                  && "$(count_nis "$REVIEW_SRC")" -eq 0 ]]; then
                echo "  跳过 review/revise（复注 $LBOOK:$FIRST-$LAST 没有缅文 nissaya）"
                REVIEW_SRC=""
                # 记账：这是**按规矩不该做**，不是没做成。不留痕的话 audit 里既非 ok
                # 也非 fail，rollup 永远等不到这一步，chunk 升不到 done，早先真失败过
                # 的 chunk 就再也洗不白，作业每轮都被重新打回 FAILED。
                audit_task "$CHID:review" skip "复注无缅文 nissaya" "$LBOOK" "$FIRST-$LAST"
                audit_task "$CHID:revise" skip "复注无缅文 nissaya" "$LBOOK" "$FIRST-$LAST"
            fi
        fi

        # ---------- review ----------
        REVIEW_MD="$REPORTS/${TAG}_review.md"
        if has_step review && [[ -n "$REVIEW_SRC" ]] && ! task_done "$CHID:review"; then
            for ((try = 1; try <= MAX_TRY; try++)); do
                echo ">>> review 第 $try/$MAX_TRY 次"
                if emit_review "$CHID:review:$LBOOK:$CH" > "$REVIEW_MD" && valid_report "$REVIEW_MD"; then
                    audit_task "$CHID:review" ok "$REVIEW_MD" "$LBOOK" "$FIRST-$LAST"; break
                fi
                [[ $try -eq $MAX_TRY ]] && { audit_task "$CHID:review" fail "$MAX_TRY 次未成" "$LBOOK" "$FIRST-$LAST"; fail_step "review 失败（$CHID，输出不是报告）"; }
            done
        fi

        # ---------- revise ----------
        if has_step revise && [[ -n "$REVIEW_SRC" ]] && ! task_done "$CHID:revise"; then
            for ((try = 1; try <= MAX_TRY; try++)); do
                echo ">>> revise 第 $try/$MAX_TRY 次"
                if emit_revise "$CHID:revise:$LBOOK:$CH" \
                    | python3 "$SCRIPT_DIR/wp_push.py" --book "$LBOOK" --para "$CH" \
                        --channel "$CHANNEL" --at-most "$N" --allow-empty $DRYRUN; then
                    audit_task "$CHID:revise" ok "$N 句" "$LBOOK" "$FIRST-$LAST"; break
                fi
                [[ $try -eq $MAX_TRY ]] && { audit_task "$CHID:revise" fail "$MAX_TRY 次未成" "$LBOOK" "$FIRST-$LAST"; fail_step "revise 失败（$CHID）"; }
            done
        fi
    done < "$CHUNKS_FILE"
done < "$GROUPS_FILE"

# ══════════ 阶段二：跨层统稿 ══════════
# 各层分头译完，被解释词和术语难免对不上。这一步把各层放在一起通读，统一并修正。
if has_step harmonize; then
# 统稿有两条路：
#   计划模式——project 文件里已按 cs_para 排好统稿单元（横向 cross + 纵向 layer），
#              体量在规划阶段就算过，这里只管照着跑。见 WORKFLOW.md「harmonize 的规模分级」。
#   无计划——退回旧路：按体量临时决定（整章一次；超过句数上限就按层分批）。
HUNITS=""
if [[ -n "$PLAN" ]]; then
    HUNITS="$PROJ_HOME/.hunits_job${JOB}"
    python3 - "$PLAN" "$JOB" > "$HUNITS" <<'PYUNITS' || true
import json, sys
plan, jid = json.load(open(sys.argv[1], encoding='utf-8')), int(sys.argv[2])
job = next((j for j in plan.get("pipelines", []) if j["id"] == jid), None)
h = (job or {}).get("harmonize") or {}
# 每行：kind<TAB>id<TAB>chars<TAB>book:起-止,book:起-止…
for c in h.get("cross", []):
    spans = ",".join("%s:%d-%d" % (b, r[0], r[1])
                     for b, r in sorted((c.get("layers") or {}).items()))
    if spans:
        print("\t".join([c.get("kind", "cross"), c["id"], str(c.get("chars", 0)), spans]))
for c in h.get("layer", []):
    print("\t".join(["layer", c["id"], str(c.get("chars", 0)),
                     "%s:%d-%d" % (c["book"], c["start"], c["end"])]))
PYUNITS
fi

if [[ -s "${HUNITS:-/nonexistent}" ]]; then
    echo "╔══════ 阶段二 统稿（按计划：$(wc -l < "$HUNITS") 个单元）══════╗"
    while IFS=$'\t' read -r KIND HUID UCHARS SPANS; do
        [[ -z "${KIND:-}" ]] && continue

        # 断点续传：统稿单元的 id 就是 task id，查一次账即可
        task_done "$HUID" && { echo "  跳过 $HUID（已统稿过）"; continue; }

        # 取各层译文：横向单元自带多层，纵向单元只有一层
        USRC=""; UN=0
        for SP in ${SPANS//,/ }; do
            UB="${SP%%:*}"; UR="${SP#*:}"
            T=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$UB" --para "$UR" --channel "$CHANNEL" || true)
            UN=$(( UN + $(count_mula "$T") ))
            USRC="$USRC
=== book=$UB  段 $UR ===
$T
"
        done
        [[ "$UN" -eq 0 ]] && { echo "  跳过 $HUID（没有译文）"; continue; }

        if [[ "$KIND" == "layer" ]]; then
            WHAT="纵向：只看这一层，通读求**同层一致**——术语、语体、称谓、重复定型句同译。跨层对齐已在横向那一步做过，这里不要再改被解释词的译法。"
        else
            WHAT="横向：各层同看，**被解释词与父层逐字对齐**是最高优先（下一层的黑体引自它的上一层：义注引本文、复注引义注、随复注引根本复注）；顺带统一术语与语体。"
        fi

        echo ">>> 统稿 $HUID（$KIND，$UCHARS 巴利字符 / $UN 句）"
        UOUT="$(mktemp)"; OK=0
        for ((try = 1; try <= MAX_TRY; try++)); do
            if emit_harmonize "$HUID" > "$UOUT"; then
                PUSH_OK=1
                for SP in ${SPANS//,/ }; do
                    UB="${SP%%:*}"; UR="${SP#*:}"
                    NL=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$UB" --para "$UR" | grep -c '^{' || true)
                    python3 "$SCRIPT_DIR/wp_push.py" --book "$UB" --para "$UR" \
                        --channel "$CHANNEL" --at-most "$NL" --allow-empty --ignore-foreign $DRYRUN \
                        < "$UOUT" || PUSH_OK=0
                done
                [[ "$PUSH_OK" -eq 1 ]] && { OK=1; break; }
            fi
        done
        rm -f "$UOUT"

        if [[ "$OK" -eq 1 ]]; then
            audit_task "$HUID" ok "$SPANS"
        else
            audit_task "$HUID" fail "用尽 $MAX_TRY 次" 
            fail_step "统稿单元 $HUID 失败（用尽 $MAX_TRY 次）"
        fi
    done < "$HUNITS"
else
        echo "╔══════ 阶段二 跨层统稿 ══════╗"

        ALL_SRC=""
        HAVE=1
        while read -r LAYER LBOOK LPARAS PBOOK TITLE OWN; do
            [[ -z "${LAYER:-}" ]] && continue
            TXT=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$LPARAS" --channel "$CHANNEL" || true)
            NL=$(count_mula "$TXT"); NZ=$(count_zh "$TXT")
            if [[ "${OWN:-1}" == 1 ]]; then
                echo "  [译] $(layer_cn "$LAYER") book=$LBOOK：$NZ/$NL 句有译文"
                # 只有**本作业负责翻译**的层要求译全；ref 层归别的作业，此刻没译完是正常的
                if [[ "$NZ" -ne "$NL" ]]; then
                    echo "  ⚠ 本作业负责的层译文不全（$NZ/$NL），先补齐再统稿——跳过统稿" >&2; HAVE=0
                fi
                MARK="本作业负责，需回写"
            else
                echo "  [参考] $(layer_cn "$LAYER") book=$LBOOK：$NZ/$NL 句有译文（归别的作业，只读）"
                MARK="**只读参考，不要输出这一层的句子**"
            fi
            ALL_SRC="$ALL_SRC
    === $(layer_cn "$LAYER")  book=$LBOOK  段 $LPARAS  $TITLE 〔$MARK〕===
    $TXT
    "
        done < "$GROUPS_FILE"

        # 只统计 own 层的句子——ref 层只进上下文，不要求模型回吐
        TOTAL=0
        while read -r LAYER LBOOK LPARAS PBOOK TITLE OWN; do
            [[ -z "${LAYER:-}" ]] && continue
            [[ "${OWN:-1}" == 1 ]] || continue
            TOTAL=$(( TOTAL + $(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$LPARAS" | grep -c '^{' || true) ))
        done < "$GROUPS_FILE"

        # 超大作业（最大的一章注释有一千多段）没法一次塞进上下文，也没法让模型一次吐回来。
        # 这时改为**按子层分批**：每个 own 注释层按 chunk 切，每批都带上完整本文译文当
        # 被解释词的对齐锚点（本文最多几十段，永远塞得下）。
        if [[ "$HAVE" -eq 1 && "$TOTAL" -gt "$HARMONIZE_MAX" ]]; then
            echo ">>> 本作业 $TOTAL 句，超过单批上限 $HARMONIZE_MAX——改为按层分批统稿"
            MULA_TXT="$(awk '$1=="mula" {print $2, $3}' "$GROUPS_FILE" | while read -r mb mp; do
                python3 "$SCRIPT_DIR/wp_pull.py" --book "$mb" --para "$mp" --channel "$CHANNEL" || true
            done)"
            while read -r LAYER LBOOK LPARAS PBOOK TITLE OWN; do
                [[ -z "${LAYER:-}" ]] && continue
                [[ "${OWN:-1}" == 1 ]] || continue
                [[ "$LAYER" == "mula" ]] && continue        # 本文随第一批一起统
                while read -r HCH; do
                    [[ -z "$HCH" ]] && continue
                    HSRC=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$HCH" --channel "$CHANNEL" || true)
                    HN=$(count_mula "$HSRC")
                    [[ "$HN" -eq 0 ]] && continue
                    echo ">>> 统稿分批 $(layer_cn "$LAYER") $LBOOK:${HCH%%,*}-${HCH##*,}（$HN 句）"
                    cached_claude "adhoc.$LBOOK.H:$HCH" "$(load_step pali-harmonize harmonize)

    $KNOWLEDGE

    ---本文译文（对齐锚点，**只读，一句都不要输出**）---
    $MULA_TXT

    ---待统稿：$(layer_cn "$LAYER") book=$LBOOK 段 $HCH $TITLE---
    $HSRC

    ---任务---
    只对上面这一层这一批做统稿：被解释词与本文/父层逐字对齐、术语与语体统一、就地修正明显错误。
    原文里的黑体是被解释词，译文里必须照样用双星号包起来，不要改成引号、不要去掉。
    **只输出你真正改动过的句子**：{\"id\": 同输入, \"zh\": \"统稿后译文\"}
    写入是按坐标覆盖的，没提交的句子原样保留——不要回传未改动的句子（至多 $HN 行）。一句都没改就只输出一行 {\"no_change\": true}——不要输出空。
    所需数据已全部注入上文，不要试图调用任何工具取数。
    只输出 JSONL，不要旁白或代码围栏。" \
                        | python3 "$SCRIPT_DIR/wp_push.py" --book "$LBOOK" --para "$HCH" \
                            --channel "$CHANNEL" --at-most "$HN" --allow-empty $DRYRUN \
                        || fail_step "分批统稿失败 $LBOOK:$HCH"
                done < <(chunk_list "$LBOOK" "$LPARAS")
                audit_task "adhoc.$LBOOK.H" ok "分批" "$LBOOK" "$LPARAS"
            done < "$GROUPS_FILE"
        elif [[ "$HAVE" -eq 1 && "$TOTAL" -gt 0 ]]; then
            for ((try = 1; try <= MAX_TRY; try++)); do
                echo ">>> harmonize（跨层）第 $try/$MAX_TRY 次（共 $TOTAL 句）"
                OUT="$(mktemp)"
                if cached_claude "adhoc.${JOB:-x}.H.all" "$(load_step pali-harmonize harmonize)

    $KNOWLEDGE

    ---各层译文（同一部经的本文 / 义注 / 复注等，已分头译完）---
    每块以 === 开头标出层次与 book；pali 里的 \`**词**\` 是黑体被解释词。
    $ALL_SRC

    ---任务---
    把各层放在一起通读，做统稿，两件事：
    1. **统一**——
       a) **被解释词逐字对齐（最高优先）**：义注的黑体引自本文，其译法必须与本文同一处逐字相同；
          复注的黑体引自义注，必须与义注同一处逐字相同。不一致就改子层去迁就父层；
          除非父层本身译错——那就把父层一并改对。
       b) 各层之间术语译法统一、语体统一、称谓与专名统一、标点体例统一。
    2. **修正**——通读中发现的实际问题就地改掉：误译、漏译、指代接不上、汉语语病、
       文言/半文半白、引号配对断裂。
    每处改动都要有具体理由（对齐、一致性，或明确的错误）；**不要为「读起来更顺」而改**，不要重译。
    **只输出本作业负责的那几层里你真正改动过的句子**：{\"id\": 同输入, \"zh\": \"统稿后译文\"}
    写入是按坐标覆盖的，没提交的句子原样保留——不要回传未改动的句子（至多 $TOTAL 行）。一句都没改就只输出一行 {\"no_change\": true}——不要输出空。
    标了〔只读参考〕的层**一句都不要输出**——那些归别的作业写，这里只用来对齐被解释词与术语。
    原文里的黑体是**被解释词**（义注引自本文、复注引自义注）。译文里这些词必须照样用双星号包起来——不要改成引号、不要去掉。它是读者辨认「这条注在注哪个词」的唯一线索，也是逐字同译的机械核查依据。
    id 里带着 book 与段号，照抄输入，不要编造。译文里不要留任何工作标记。
    所需数据已全部注入上文，不要试图调用任何工具取数。
    只输出 JSONL，不要旁白或代码围栏。" > "$OUT"; then
                    OK=1
                    # 一份输出分层提交：每层只收自己 book 的行，别层静默跳过
                    while read -r LAYER LBOOK LPARAS PBOOK TITLE OWN; do
                        [[ -z "${LAYER:-}" ]] && continue
                        [[ "${OWN:-1}" == 1 ]] || continue      # 参考层不回写
                        NL=$(python3 "$SCRIPT_DIR/wp_pull.py" --book "$LBOOK" --para "$LPARAS" | grep -c '^{' || true)
                        if ! python3 "$SCRIPT_DIR/wp_push.py" --book "$LBOOK" --para "$LPARAS" \
                            --channel "$CHANNEL" --at-most "$NL" --allow-empty --ignore-foreign $DRYRUN < "$OUT"; then
                            OK=0
                        fi
                    done < "$GROUPS_FILE"
                    if [[ "$OK" -eq 1 ]]; then
                        rm -f "$OUT"
                        while read -r LAYER LBOOK LPARAS PBOOK TITLE OWN; do
                            [[ -z "${LAYER:-}" ]] && continue
                            [[ "${OWN:-1}" == 1 ]] || continue
                            audit_task "adhoc.$LBOOK.H" ok "跨层" "$LBOOK" "$LPARAS"
                        done < "$GROUPS_FILE"
                        break
                    fi
                fi
                rm -f "$OUT"
                [[ $try -eq $MAX_TRY ]] && fail_step "harmonize 失败（用尽 $MAX_TRY 次）"
            done
        fi
fi
fi

# ══════════ 阶段三：evaluate（最后一步，只出报告）══════════
if has_step evaluate; then
    echo "╔══════ 阶段三 评估 ══════╗"
    while read -r LAYER LBOOK LPARAS PBOOK TITLE OWN; do
        [[ -z "${LAYER:-}" ]] && continue
        [[ "${OWN:-1}" == 1 ]] || continue
        LCN="$(layer_cn "$LAYER")"
        while read -r CB CHID CH; do
            [[ "$CB" == "$LBOOK" && -n "$CH" ]] || continue
            PARAS="${CH//,/ }"
            FIRST="${CH%%,*}"; LAST="${CH##*,}"
            TAG="$LBOOK-$FIRST-$LAST"
            task_done "$CHID:evaluate" && continue

            EVAL_SRC=$(pull_review "$LBOOK" "$CH" || true)
            if [[ "$(count_zh "$EVAL_SRC")" -eq 0 ]]; then
                echo "  跳过评估（$LBOOK:$FIRST-$LAST 还没有译文）"; continue
            fi

            echo "════════ 评估 $LCN $LBOOK:$FIRST-$LAST ════════"
            for ((try = 1; try <= MAX_TRY; try++)); do
                echo ">>> evaluate 第 $try/$MAX_TRY 次"
                if emit_evaluate "$CHID:evaluate:$LBOOK:$CH" > "$REPORTS/${TAG}_final.md" \
                    && valid_report "$REPORTS/${TAG}_final.md"; then
                    audit_task "$CHID:evaluate" ok "$REPORTS/${TAG}_final.md" "$LBOOK" "$FIRST-$LAST"; break
                fi
                [[ $try -eq $MAX_TRY ]] && { audit_task "$CHID:evaluate" fail "$MAX_TRY 次未成" "$LBOOK" "$FIRST-$LAST"; fail_step "evaluate 失败（$CHID）"; }
            done
        done < "$CHUNKS_FILE"
    done < "$GROUPS_FILE"
fi

# ══════════ 阶段四：导出 markdown（本作业负责的每一层各一份）══════════
# 每章跑完立刻出 md，不用等全书跑完才能看结果。
if has_step export && [[ -z "$DRYRUN" ]]; then
    echo "╔══════ 阶段四 导出 markdown ══════╗"
    while read -r LAYER LBOOK LPARAS PBOOK TITLE OWN; do
        [[ -z "${LAYER:-}" ]] && continue
        [[ "${OWN:-1}" == 1 ]] || continue
        EXP_TASK="${JOB:-adhoc}.$LBOOK:export"
        task_done "$EXP_TASK" && { echo "  跳过导出 $LBOOK（已导出）"; continue; }
        # 一个作业可能含好几章（小章合并），按整段范围导出，与之相交的章都出；
        # 只给首段（--para）就只会导出第一章。LPARAS 形如 5-9 或 5,6,9。
        EFROM="${LPARAS%%,*}"; EFROM="${EFROM%%-*}"
        ETO="${LPARAS##*,}"; ETO="${ETO##*-}"
        if python3 "$SCRIPT_DIR/export_markdown.py" --book "$LBOOK" --channel "$CHANNEL" \
               --from "$EFROM" --to "$ETO" --out "$EXPORT_DIR" --model claude-opus-5; then
            audit_task "$EXP_TASK" ok "$EXPORT_DIR" "$LBOOK" "$LPARAS"
        else
            audit_task "$EXP_TASK" fail "导出失败" "$LBOOK" "$LPARAS"
            echo "  ⚠ 导出失败 $LBOOK:$EFROM-$ETO" >&2
        fi
    done < "$GROUPS_FILE"
fi

rm -f "$GROUPS_FILE" "$CHUNKS_FILE"
if [[ "$FAILED_STEPS" -gt 0 ]]; then
    echo "######## 未完成：本文 $BOOK $START..$END 有 $FAILED_STEPS 个步骤失败 ########" >&2
    exit 1
fi
echo "######## 完成：本文 $BOOK $START..$END（各层）→ channel $CHANNEL（报告在 $REPORTS/）########"
