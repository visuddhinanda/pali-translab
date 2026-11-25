#!/usr/bin/env bash
# plan_solo 项目的并行池：**一个 project 一条流水线，同时跑 N 条**（默认 10）。
# 这批书大多很小（几个到几十个 task），一个接一个跑时 10 个 worker 大半空转；
# 改成多个项目并行，每个项目内部 1 个 worker（--per），一条做完由下一个项目补位。
#
# 每条流水线（--one <name>）：
#   · 已发信（.mailed）→ 跳过
#   · 该项目已有守护进程或收尾脚本在跑（别处起的）→ 等它结束再接手，不重复发信
#   · 跑 translate；有失败 → 把失败 task 的模型缓存移走（重试会复用同一份坏产物）、
#     reset-failed 再跑一轮
#   · done → finish_and_mail.sh（补编号、导出、epub、发信）→ 写 .mailed；
#     有句子待人工补时收尾脚本 exit 3，不发信，记进队列日志
#
# 守护进程开跑时会刷新凭据（ensure-model / grant --force，写 ~/.wikipali/credentials.json），
# 多个同时写会互相覆盖，所以开跑用一把锁串行、间隔 LAUNCH_GAP 秒。
#
# 用法：
#   setsid nohup bash scripts/run_solo_pool.sh --slots 10 --per 1 --model claude-opus-5-5 \
#       >> workspace/solo_queue.out 2>&1 &
#   停：touch workspace/STOP_SOLO_QUEUE（不再开新项目，在跑的跑完收尾）；touch workspace/STOP（全停）
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SLOTS=10
PER=1
BIG=50          # task 数 ≥ BIG 的算大项目
PER_BIG=3       # 大项目的 worker 数
MODEL="claude-opus-5-5"
CHANNEL="73c03e1a-f333-11f0-808a-438f0af4b9e9"
ONE=""
SEQ_RANGE=""    # 只跑这个编号段（如 52-62）；空 = 全部
CACHE_ONLY=""   # 只翻译不上传：原文从本地服务器读，产物只留 llm-cache，跑完打 .cached、不导出不发信
while [[ $# -gt 0 ]]; do
    case "$1" in
        --slots)   SLOTS="$2";   shift 2 ;;
        --per)     PER="$2";     shift 2 ;;
        --big)     BIG="$2";     shift 2 ;;
        --per-big) PER_BIG="$2"; shift 2 ;;
        --model)   MODEL="$2";   shift 2 ;;
        --channel) CHANNEL="$2"; shift 2 ;;
        --one)     ONE="$2";     shift 2 ;;
        --cache-only) CACHE_ONLY=1; shift ;;
        --seq)     SEQ_RANGE="$2"; shift 2 ;;
        *) echo "认不出的参数：$1"; exit 2 ;;
    esac
done

WP_DIR=/home/deploy/workspace/wikipali-plugins/plugins/wikipali/bin
export WIKIPALI_BIN="$WP_DIR/wikipali" PATH="$WP_DIR:$PATH"
DAEMON_EXTRA=()
if [[ -n "$CACHE_ONLY" ]]; then
    # 读原文走本地服务器（next.wikipali.cc 慢到读一段几十秒）；不写 channel，所以不需要线上
    export WIKIPALI_API_URL="${LOCAL_API:-http://127.0.0.1:8000/api}"
    # 本地库里 _System_Pali_VRI_ 的 channel uid 与线上不同
    export WIKIPALI_PALI_UID="${LOCAL_PALI_UID:-f4d07a00-8a5f-11ed-a044-a7a26c844686}"
    DAEMON_EXTRA=(--cache-only)
fi
QSTOP="workspace/STOP_SOLO_QUEUE"
LAUNCH_LOCK="workspace/.solo_launch.lock"
LAUNCH_GAP=20
log() { echo "[$(date '+%F %T')] $*"; }

# ── 一条流水线 ──
one() {
    local NAME="$1" HOME_DIR="workspace/projects/$1" PJ="workspace/projects/$1/project.json"
    local BOOK ST BAD
    BOOK=$(python3 -c "import json;print(json.load(open('$PJ'))['book'])")
    mkdir -p "$HOME_DIR/logs"

    # 别处起的守护进程 / 收尾脚本还在跑：等它
    while :; do
        local busy=""
        if [[ -f "$HOME_DIR/daemon.lock" ]] && kill -0 "$(cat "$HOME_DIR/daemon.lock")" 2>/dev/null; then busy=1; fi
        pgrep -f "finish_and_mail.sh $NAME " >/dev/null && busy=1
        # 上一版池子起的同名流水线还在（重排时留下的）
        pgrep -f "^bash [^ ]*run_solo_pool[.]sh --one $NAME " | grep -vqx "$$" && busy=1
        [[ -z "$busy" ]] && break
        waited=1
        sleep 30
    done
    # 别处的收尾脚本退出后才写 .mailed，留点余量再看
    [[ -n "${waited:-}" ]] && sleep 10
    if [[ -f "$HOME_DIR/.mailed" ]]; then return 0; fi
    if [[ -n "$CACHE_ONLY" && -f "$HOME_DIR/.cached" ]]; then return 0; fi
    if [[ -f "$QSTOP" || -f workspace/STOP ]]; then return 0; fi

    pstate() { python3 -c "
import json; p = json.load(open('$PJ'))
print(p.get('state'), sum(1 for x in p['tasks'] if x.get('status') == 'failed'))"; }

    run_daemon() {
        # 开跑串行：拿锁 → 起守护进程 → 等它刷新完凭据 → 放锁
        exec 9>"$LAUNCH_LOCK"; flock 9
        python3 scripts/run_daemon.py run --project "$NAME" --channel "$CHANNEL" \
            --workers "$PER" --model "$MODEL" "${DAEMON_EXTRA[@]}" >> "$HOME_DIR/logs/daemon.out" 2>&1 9>&- &
        local pid=$!
        sleep "$LAUNCH_GAP"; flock -u 9; exec 9>&-
        wait "$pid"
    }

    read -r ST BAD <<<"$(pstate)"
    if [[ "$ST" != "done" ]]; then
        log "$NAME 开跑"
        run_daemon
        read -r ST BAD <<<"$(pstate)"
        [[ "$ST" == "paused" ]] && { log "$NAME 被停下（paused）"; return 0; }
        if [[ "$ST" != "done" && "$BAD" -gt 0 ]]; then
            # 失败 task 的模型缓存移走：重试复用同一份坏产物是补不上的
            mkdir -p "$HOME_DIR/llm-cache.bad"
            python3 -c "
import json; p = json.load(open('$PJ'))
print('\n'.join(t['id'] for t in p['tasks'] if t.get('status') == 'failed'))" | while read -r T; do
                f="$HOME_DIR/llm-cache/${MODEL}__${T}.out"
                [[ -f "$f" ]] && mv "$f" "$HOME_DIR/llm-cache.bad/"
            done
            log "$NAME 有 $BAD 个失败 task，移走缓存、重置后再跑一轮"
            python3 scripts/run_daemon.py reset-failed --project "$NAME" > /dev/null
            run_daemon
            read -r ST BAD <<<"$(pstate)"
        fi
    fi
    if [[ "$ST" != "done" ]]; then
        log "⚠ $NAME 未完成（state=$ST，失败 $BAD），不发信"
        return 0
    fi
    if [[ -n "$CACHE_ONLY" ]]; then
        date '+%F %T' > "$HOME_DIR/.cached"
        log "$NAME 翻译完成（仅缓存，未上传、未发信）"
        return 0
    fi
    if [[ -f workspace/UPLOAD_ONLY ]]; then
        date '+%F %T' > "$HOME_DIR/.uploaded"
        log "$NAME 上传完成（UPLOAD_ONLY，不导出不发信）"
        return 0
    fi
    log "$NAME 完成，导出发信"
    MERGE_TITLE="$NAME" bash scripts/finish_and_mail.sh "$NAME" "$BOOK" >> "$HOME_DIR/logs/finish.out" 2>&1
    local rc=$?
    if [[ $rc -eq 0 ]]; then
        date '+%F %T' > "$HOME_DIR/.mailed"; log "$NAME 已发信"
    elif [[ $rc -eq 4 ]]; then
        date '+%F %T' > "$HOME_DIR/.uploaded"; log "$NAME 上传完成（UPLOAD_ONLY，不导出不发信）"
    elif [[ $rc -eq 3 ]]; then
        log "⚠ $NAME 有句子待人工补，未发信（manual_fix.py list --project $NAME）"
    else
        log "⚠ $NAME 收尾出错（rc=$rc），见 $HOME_DIR/logs/finish.out"
    fi
}

if [[ -n "$ONE" ]]; then
    one "$ONE"
    exit 0
fi

# ── 池：**先大后小**把项目喂给 N 条并行流水线；大项目（task ≥ BIG）每条 PER_BIG 个 worker ──
# 大的排在最后会单独拖尾，所以先开跑
LIST=$(CACHE_ONLY="$CACHE_ONLY" SEQ_RANGE="$SEQ_RANGE" python3 - <<'PY'
import json, glob, os
rows = []
lo, _, hi = (os.environ.get("SEQ_RANGE") or "0-999999").partition("-")
lo, hi = int(lo), int(hi or lo)
for f in glob.glob("workspace/projects/x[0-9][0-9]-*/project.json"):
    p = json.load(open(f, encoding="utf-8"))
    d = os.path.dirname(f)
    if "seq" in p and lo <= p["seq"] <= hi and not os.path.exists(os.path.join(d, ".mailed")) \
            and not (os.environ.get("CACHE_ONLY") and os.path.exists(os.path.join(d, ".cached"))):
        rows.append((len(p["tasks"]), sum(t.get("chars") or 0 for t in p["tasks"]), p["seq"], p["name"]))
for n_task, chars, seq, name in sorted(rows, key=lambda r: (-r[0], -r[1], r[2])):
    print(name, n_task)
PY
)
log "并行池开始：$(printf '%s\n' "$LIST" | grep -c .) 个未发信项目（先大后小），$SLOTS 条流水线，每条 $PER worker（task ≥ $BIG 的 $PER_BIG worker），model=$MODEL"
printf '%s\n' "$LIST" | grep . | while read -r NAME NT; do
    W=$PER; [[ "$NT" -ge "$BIG" ]] && W=$PER_BIG
    printf '%s %s\n' "$NAME" "$W"
done | xargs -P "$SLOTS" -L1 bash -c 'exec bash "$0" --one "$5" --per "$6" --model "$3" --channel "$4" ${1:+--cache-only}' \
    "$0" "$CACHE_ONLY" _ "$MODEL" "$CHANNEL"
log "并行池结束"
