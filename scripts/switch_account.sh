#!/usr/bin/env bash
# 换账号重启守护进程——撞周额度时用，不需要任何 LLM 参与。
#
#   scripts/switch_account.sh alt     # 切到备用账号 ~/.claude-alt
#   scripts/switch_account.sh main    # 切回主账号   ~/.claude
#   scripts/switch_account.sh alt 2   # 顺便把并发改成 2（默认沿用 3）
#
# 做四件事：停掉守护进程与它派出去的作业 → 清锁 → 把失败作业退回队列 →
# 带上 CLAUDE_CONFIG_DIR 重新起来。已完成的分块在 channel 上，重跑会跳过。
set -u
cd "$(dirname "$0")/.." || exit 1

PROJECT=mn-mulapannasa
CHANNEL=73c03e1a-f333-11f0-808a-438f0af4b9e9
WORKERS="${2:-3}"

case "${1:-}" in
    alt)  CFG="$HOME/.claude-alt"; WHO="备用账号" ;;
    main) CFG="$HOME/.claude";     WHO="主账号"   ;;
    *)    echo "用法: $0 {alt|main} [并发数]"; exit 1 ;;
esac
[ -f "$CFG/.credentials.json" ] || {
    echo "✗ $CFG 里没有 .credentials.json——这个账号还没登录。"
    echo "  先跑：CLAUDE_CONFIG_DIR=$CFG claude    然后在里面 /login"
    echo "  注意 CLAUDE_CONFIG_DIR 必须和 claude 写在同一行，否则会把主账号顶掉。"
    exit 1
}

echo "==> 停守护进程"
pkill -9 -f "run_daemon.py run --project $PROJECT"
pkill -9 -f "\.snapshot/pipeline_batch\.sh"
sleep 4
rm -f workspace/daemon.lock workspace/STOP

echo "==> 退回失败作业"
python3 scripts/project.py reset-failed "$PROJECT" >/dev/null 2>&1

echo "==> 用$WHO（$CFG）以 $WORKERS 并发重启"
CLAUDE_CONFIG_DIR="$CFG" nohup python3 scripts/run_daemon.py run \
    --project "$PROJECT" --workers "$WORKERS" --channel "$CHANNEL" \
    >> workspace/daemon.out 2>&1 &
echo "    pid $!"

sleep 40
tail -5 workspace/daemon.out
python3 scripts/project.py status "$PROJECT" | head -3
