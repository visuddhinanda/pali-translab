# -*- coding: utf-8 -*-
"""看门狗：定期巡检守护进程与作业，出问题就地处理。

守护进程管作业，看门狗管守护进程——多天的任务里，守护进程本身也会死
（被 OOM、被误杀、卡在某个等待里），没人盯着就是整夜空转。

每轮巡检做四件事：

  1. **守护进程活着吗** —— 死了且还有未完成任务，就地拉起来
  2. **有卡住的作业吗** —— 日志超过 --stuck-min 分钟没动静，杀掉那个子进程；
     守护进程收割到非零退出码会自己退回队列重跑
  3. **是不是全在失败** —— 连续多轮没有新完成、失败却在涨，记一条显式告警
  4. **API 通不通** —— 不通只记录，不动作（守护进程自己会退避等待）

巡检结果写 workspace/watchdog.log，并在 workspace/health.json 留一份快照。

    python3 scripts/watchdog.py --interval 600 --channel <uid> --plan workspace/plan_93.json

停止：`touch workspace/STOP`（守护进程与看门狗共用这一个开关）。
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import run as wp_run  # noqa: E402
import run_daemon as rd  # noqa: E402

WATCH_LOG = os.path.join(rd.WORK, "watchdog.log")
HEALTH = os.path.join(rd.WORK, "health.json")
WD_LOCK = os.path.join(rd.WORK, "watchdog.lock")


def log(msg):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(WATCH_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def pids(pattern):
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split()] if r.returncode == 0 else []


def daemon_alive():
    if not os.path.exists(rd.LOCK):
        return False
    try:
        os.kill(int(open(rd.LOCK).read().strip()), 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def start_daemon(args):
    """拉起守护进程；它自己会把上次残留的 running 复位成 pending。"""
    if os.path.exists(rd.LOCK):
        os.remove(rd.LOCK)                     # 陈旧锁
    cmd = [sys.executable, os.path.join(rd.ROOT, "scripts", "run_daemon.py"), "run",
           "--book", str(args.book), "--channel", args.channel,
           "--workers", str(args.workers), "--nissaya"]
    if args.plan:
        cmd += ["--plan", args.plan]
    out = open(os.path.join(rd.WORK, "daemon.out"), "a", encoding="utf-8")
    out.write(f"\n===== watchdog 拉起 {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    out.flush()
    subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,
                     cwd=rd.ROOT, start_new_session=True)
    log("守护进程不在，已重新拉起")


# 这些行是「同一个原因反复失败」的信号。进程正常退出、状态正常落表，
# 但每个作业都栽在同一处——看门狗只盯进程是看不出来的，必须扫日志聚类。
ERR_PAT = [
    (r"Argument list too long", "提示词超出命令行长度上限"),
    (r"unbound variable", "shell 变量未定义"),
    (r"Traceback \(most recent", "python 异常"),
    (r"⚠ (\w+) 失败（输出不是报告）", "报告校验不通过"),
    (r"没有抽到任何 JSONL 行", "模型输出无法解析"),
    (r"条数不符", "句数与原文对不上"),
    (r"坐标不存在于原文", "坐标编造"),
    (r"HTTP 5\d\d", "服务端 5xx"),
    (r"连接失败|timed out", "网络异常"),
    (r"rate limit|usage limit|quota", "撞额度"),
]


def _tail(path, nbytes):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - nbytes))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def scan_failures(jobs, since_min=180, top=6):
    """扫最近失败作业的日志，把错误按模式聚类。

    返回 [(次数, 说明, 样例行)]。同一模式反复出现就是系统性 bug——
    那不是重试能解决的，得改代码。
    """
    import re
    now = time.time()
    hits = {}
    for j in jobs:
        path = os.path.join(rd.LOGS, f"{j['book']}-{j['start']}-{j['end']}.log")
        if not os.path.exists(path):
            continue
        if (now - os.path.getmtime(path)) / 60 > since_min:
            continue
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 200000))
                tail = f.read().decode("utf-8", "replace")
        except OSError:
            continue
        # 日志是追加的，早已修好的旧错误会被反复统计成「系统性问题」。
        # 只看最后一次运行（spawn 时写的 ===== 分隔符）之后的内容。
        cut = tail.rfind("=====")
        if cut > 0:
            tail = tail[cut:]
        for line in tail.splitlines():
            for pat, desc in ERR_PAT:
                if re.search(pat, line):
                    k = desc
                    c, sample = hits.get(k, (0, line.strip()[:110]))
                    hits[k] = (c + 1, sample)
                    break
    return sorted(((c, d, s) for d, (c, s) in hits.items()), reverse=True)[:top]


def stuck_jobs(jobs, stuck_min):
    """日志长时间没动静的在跑作业。一次 claude 调用最多十几分钟，超阈值就是真卡住。"""
    out = []
    now = time.time()
    for j in jobs:
        if j["status"] != rd.RUNNING:
            continue
        path = os.path.join(rd.LOGS, f"{j['book']}-{j['start']}-{j['end']}.log")
        if not os.path.exists(path):
            continue
        idle = (now - os.path.getmtime(path)) / 60
        if idle > stuck_min:
            out.append((j, path, idle))
    return out


def kill_job(j):
    """杀掉这个作业的流水线子进程；守护进程会收割并按失败退回队列。"""
    pat = f"pipeline_batch.sh {j['book']} {j['start']} {j['end']}"
    killed = 0
    for pid in pids(pat):
        try:
            os.kill(pid, 9)
            killed += 1
        except ProcessLookupError:
            pass
    return killed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=600, help="巡检间隔秒，默认 10 分钟")
    ap.add_argument("--stuck-min", type=int, default=45, help="日志静默多少分钟算卡住")
    ap.add_argument("--book", type=int, default=93)
    ap.add_argument("--channel", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--plan", default="")
    ap.add_argument("--err-threshold", type=int, default=5,
                    help="同一错误出现几次就当系统性问题告警")
    args = ap.parse_args()

    os.makedirs(rd.WORK, exist_ok=True)
    if os.path.exists(WD_LOCK):
        try:
            os.kill(int(open(WD_LOCK).read().strip()), 0)
            sys.exit("已有看门狗在跑")
        except (ValueError, ProcessLookupError):
            pass
    open(WD_LOCK, "w").write(str(os.getpid()))

    last_done, stagnant = -1, 0
    log(f"看门狗启动：每 {args.interval // 60} 分钟巡检一次，卡住阈值 {args.stuck_min} 分钟")
    try:
        while not os.path.exists(rd.STOP):
            jobs = rd.load_jobs()
            counts = {k: sum(1 for j in jobs if j["status"] == k)
                      for k in (rd.DONE, rd.RUNNING, rd.PENDING, rd.FAILED)}
            done, alive = counts[rd.DONE], daemon_alive()
            api = wp_run(["get", f"{args.book}:3", "--json"], check=False).returncode == 0

            # 1) 守护进程死了但还有活没干完
            if not alive and (counts[rd.PENDING] or counts[rd.RUNNING]):
                start_daemon(args)
                alive = True

            # 2) 卡住的作业
            for j, path, idle in stuck_jobs(jobs, args.stuck_min):
                n = kill_job(j)
                log(f"⚠ 卡住 {args.book}:{j['start']}-{j['end']}「{j['title']}」"
                    f"日志静默 {idle:.0f} 分钟，已杀 {n} 个进程，交给守护进程重排")

            # 3) 长时间零进展
            if done == last_done and counts[rd.RUNNING]:
                stagnant += 1
                if stagnant % 6 == 0:            # 约一小时没有新完成
                    log(f"⚠ 已连续 {stagnant} 轮（约 {stagnant * args.interval // 60} 分钟）"
                        f"没有新完成，在跑 {counts[rd.RUNNING]} 个，请留意")
            else:
                stagnant = 0
            last_done = done

            # 4) 失败模式聚类——反复出现同一个错误就是代码问题，显式告警
            errs = scan_failures(jobs)
            # 撞额度时 claude 返回空输出，流水线报「没有抽到 JSONL」——那是环境
            # 造成的空响应，不是代码 bug。守护进程正在冷却时，这一类一律不算系统性。
            cooling = any("撞到额度限制" in l for l in _tail(
                os.path.join(rd.WORK, "daemon.out"), 4000).splitlines()[-25:])
            ENV = ("5xx", "网络", "额度")
            systemic = [e for e in errs
                        if e[0] >= args.err_threshold
                        and not any(k in e[1] for k in ENV)
                        and not (cooling and "模型输出无法解析" in e[1])]
            if systemic:
                log("🚨 疑似系统性问题（同一原因反复出现，重试解决不了，需要改代码）：")
                for c, d, sample in systemic:
                    log(f"     {c:>4} 次  {d}  例：{sample}")
            elif errs:
                head = "｜".join(f"{d}×{c}" for c, d, _ in errs[:3])
                log(f"   近期错误：{head}")

            msg = (f"✅{counts[rd.DONE]} 🔄{counts[rd.RUNNING]} ⬜{counts[rd.PENDING]} "
                   f"❌{counts[rd.FAILED]} / {len(jobs)}"
                   f"｜守护 {'在' if alive else '停'}｜API {'通' if api else '断'}")
            log(msg)
            with open(HEALTH, "w", encoding="utf-8") as f:
                json.dump({"updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "counts": {k: counts[k] for k in counts},
                           "total": len(jobs), "daemon": alive, "api": api,
                           "stagnant_rounds": stagnant,
                           "errors": [{"count": c, "kind": d, "sample": s2}
                                      for c, d, s2 in errs],
                           "systemic": bool(systemic)}, f, ensure_ascii=False, indent=2)

            if not counts[rd.PENDING] and not counts[rd.RUNNING]:
                log(f"全部结束：完成 {counts[rd.DONE]}，失败 {counts[rd.FAILED]}")
                break

            for _ in range(args.interval):
                if os.path.exists(rd.STOP):
                    break
                time.sleep(1)
    finally:
        if os.path.exists(WD_LOCK):
            os.remove(WD_LOCK)
        log("看门狗退出")


if __name__ == "__main__":
    main()
