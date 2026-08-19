# -*- coding: utf-8 -*-
"""长任务守护进程：按章切分整本书，多进程并行跑三层流水线，断点续传 + 失败重试。

一个**作业 = 本文的一章**。三层（本文/义注/复注）由 `pipeline_batch.sh --chapter`
在作业内部解析并处理，所以章与章之间互不相干，可以放心并行。

    python3 scripts/run_daemon.py --book 93 --channel <uid> --workers 4

守护行为：
  · 单实例锁（workspace/daemon.lock），重复启动会拒绝
  · 作业队列落盘（workspace/jobs.tsv），进程被杀掉重启后接着跑
  · 每个作业独立日志（workspace/logs/<book>-<start>-<end>.log）
  · 失败自动重试；**连不上或服务端 5xx 不算作业失败**，退回队列并整体退避
  · 启动前与每轮探活；API 挂了就停下等，不空烧 LLM 调用
  · 优雅停止：`touch workspace/STOP`（或 Ctrl-C / SIGTERM），跑完手头的作业才退出

子命令：
    run            跑（默认）
    status         打印进度
    stop           写 STOP 文件，让在跑的守护进程收尾退出
    reset-failed   把 failed 作业改回 pending，便于重跑
"""
import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import jget, run as wp_run  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "workspace")
LOGS = os.path.join(WORK, "logs")
JOBS = os.path.join(WORK, "task_alloc.csv")   # 任务分配表：作业/层/分块/统稿/导出
LOCK = os.path.join(WORK, "daemon.lock")
STOP = os.path.join(WORK, "STOP")
STATUS = os.path.join(WORK, "status.json")
AUDIT = os.path.join(WORK, "audit.log")
SNAP = os.path.join(WORK, ".snapshot")     # 流水线脚本的运行时快照

PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"
# 任务表用 emoji 标状态，一眼能扫出全书进度
EMOJI = {PENDING: "⬜ 未开始", RUNNING: "🔄 进行中", DONE: "✅ 已完成", FAILED: "❌ 失败"}
STATE = {v: k for k, v in EMOJI.items()}
# 分配表的列（task_table.py 产出）。守护进程只管「类型==作业」那些行的状态，
# 层/分块/统稿/导出等子行原样保留——它们由 audit.log 推导，见 sync_subrows()。
COLS = ["编号", "类型", "状态", "层次", "坐标", "名称", "归属",
        "段数", "字符数", "预计调用", "开始时间", "完成时间", "耗时", "备注"]
# 这些字样出现在日志里，说明是环境问题而非作业本身失败——退回队列，别耗重试次数
TRANSIENT = ("连接失败", "所有可用站点都连不上", "HTTP 500", "HTTP 502",
             "HTTP 503", "HTTP 504", "timed out", "Server Error")
# 撞订阅额度：多天任务里这必然发生。**不能算作业失败**，否则一批作业连环耗光重试次数。
RATE_LIMIT = ("rate limit", "rate_limit", "Rate limit", "usage limit", "Usage limit",
              "quota", "overloaded_error", "Too Many Requests", "429",
              "resets at", "limit reached", "5-hour limit", "weekly limit")


# ---------- 作业清单 ----------

def book_end(book, after):
    """本书最后一个有原文的段号：先倍增探到空，再二分收敛。

    没有这一步，末章的结束段会是 --end 的默认值（一个极大数），
    下游按段迭代就等于死循环。
    """
    def has(p):
        return bool(jget("get", f"{book}:{p}", "--json"))
    lo, step = after, 16
    while has(lo + step):
        lo += step
        step *= 2
    hi = lo + step
    while lo + 1 < hi:                 # (lo 有内容, hi 没有]
        mid = (lo + hi) // 2
        if has(mid):
            lo = mid
        else:
            hi = mid
    return lo


def chapters(book, lo, hi):
    """本书的叶子章节：某条目录项到下一条之前即一章，裁剪到 [lo, hi]。"""
    toc = sorted((t for t in jget("toc", f"{book}:{lo}", "--json", "--depth", "9")
                  if t.get("book") == book), key=lambda t: t["paragraph"])
    if not toc:
        return []
    if hi > toc[-1]["paragraph"] + 10000:      # --end 用的是默认极大值
        hi = book_end(book, toc[-1]["paragraph"])
    out = []
    for i, t in enumerate(toc):
        s = t["paragraph"]
        e = toc[i + 1]["paragraph"] - 1 if i + 1 < len(toc) else hi
        s, e = max(s, lo), min(e, hi)
        if s <= e:
            out.append((s, e, t["toc"]))
    return out


def _read_rows():
    if not os.path.exists(JOBS):
        return []
    with open(JOBS, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_jobs():
    """只取「类型==作业」的行——那才是派发单位。子行原样留在表里。"""
    jobs = []
    for r in _read_rows():
        if r.get("类型") != "作业":
            continue
        book, rng = r["坐标"].split(":")
        lo, hi = (rng.split("-") + [rng])[:2]
        jobs.append({
            "book": int(book), "start": int(lo), "end": int(hi),
            "status": STATE.get(r["状态"], PENDING),
            "tries": int(r.get("尝试") or 0),
            "title": r["名称"], "jid": r["编号"],
            "own": r.get("归属", ""),
            "began": r.get("开始时间", ""), "ended": r.get("完成时间", ""),
            "note": r.get("备注", ""),
        })
    return jobs


def _dur(a, b):
    if not (a and b):
        return ""
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        d = int(time.mktime(time.strptime(b, fmt)) - time.mktime(time.strptime(a, fmt)))
    except ValueError:
        return ""
    return f"{d // 3600:d}:{d % 3600 // 60:02d}:{d % 60:02d}"


def save_jobs(jobs):
    """就地更新作业行；子行（层/分块/统稿/导出）保持原样，不碰。"""
    rows = _read_rows()
    if not rows:
        return
    by_id = {str(j.get("jid")): j for j in jobs}
    for r in rows:
        if r.get("类型") != "作业":
            continue
        j = by_id.get(r["编号"])
        if not j:
            continue
        r["状态"] = EMOJI[j["status"]]
        r["开始时间"] = j.get("began", "")
        r["完成时间"] = j.get("ended", "")
        r["耗时"] = _dur(j.get("began", ""), j.get("ended", ""))
        r["尝试"] = j["tries"]
        if j.get("note"):
            r["备注"] = j["note"]
    fields = list(rows[0].keys())
    if "尝试" not in fields:
        fields.append("尝试")
    tmp = JOBS + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, JOBS)          # 原子替换，守护进程被杀也不会留半截任务表


def plan_chapters(plan_path, lo, hi):
    """从 plan_jobs.py 的计划里取作业骨架：(起, 止, 章名, 作业id, own 摘要)。"""
    plan = json.load(open(plan_path, encoding="utf-8"))
    out = []
    for j in plan["jobs"]:
        m = j["mula"] or j["own"][0]      # 前置作业没有本文层，用它第一个注释章定坐标
        if lo <= m["start"] and m["end"] <= hi:
            segs = sum(e["end"] - e["start"] + 1 for e in j["own"])
            own = f'本文{m["end"] - m["start"] + 1}段'
            if j["own"]:
                own += f' + 注释{len(j["own"])}章/{segs}段'
            out.append((m["start"], m["end"], m["title"], str(j["id"]), own))
    return out


def build_jobs(book, lo, hi, plan_path=""):
    """从分配表读作业行；上次被强杀留下的 running 复位为 pending。"""
    old = {(j["book"], j["start"], j["end"]): j for j in load_jobs()}
    # 分配表由 task_table.py 预先生成，这里只读不造
    jobs = [j for j in old.values() if lo <= j["start"] and j["end"] <= hi]
    jobs.sort(key=lambda j: int(j["jid"]))
    for j in jobs:
        if j["status"] == RUNNING:   # 上次被强杀留下的
            j["status"] = PENDING
    save_jobs(jobs)
    return jobs


# ---------- 探活 ----------

def api_alive(book, para):
    r = wp_run(["get", f"{book}:{para}", "--json"], check=False)
    return r.returncode == 0 and r.stdout.strip().startswith("[")


def wait_for_api(book, para, log):
    delay = 60
    while not os.path.exists(STOP):
        if api_alive(book, para):
            return True
        log(f"API 不可用，{delay}s 后重试")
        for _ in range(delay):
            if os.path.exists(STOP):
                return False
            time.sleep(1)
        delay = min(delay * 2, 900)
    return False


# ---------- 主循环 ----------

def cooldown(seconds, log):
    """撞额度后整体停一段时间——继续派发只会让所有作业一起失败。"""
    end = time.time() + seconds
    while time.time() < end:
        if os.path.exists(STOP):
            return False
        left = int(end - time.time())
        if left % 300 == 0:
            log(f"额度冷却中，还剩 {left // 60} 分钟")
        time.sleep(5)
    return True


def log_line(msg):
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


def write_status(jobs, running):
    counts = {}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump({"updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "counts": counts, "total": len(jobs),
                   "running": [f"{j['book']}:{j['start']}-{j['end']} {j['title']}" for j, _ in running]},
                  f, ensure_ascii=False, indent=2)


def snapshot_scripts():
    """把流水线脚本复制一份到 .snapshot 再跑。

    bash 是按**字节偏移**边读边执行的：源文件在作业运行期间被编辑，
    正在跑的 shell 会读到错位的内容，报出「XXX: unbound variable」这类
    莫名其妙的错——行号还对不上。跑快照就没这问题，改源码只在下次
    重启守护进程时生效。
    """
    import shutil
    os.makedirs(SNAP, exist_ok=True)
    for name in os.listdir(os.path.join(ROOT, "scripts")):
        if name.endswith((".sh", ".py")):
            shutil.copy2(os.path.join(ROOT, "scripts", name), os.path.join(SNAP, name))
    os.chmod(os.path.join(SNAP, "pipeline_batch.sh"), 0o755)
    return os.path.join(SNAP, "pipeline_batch.sh")


def spawn(job, args):
    os.makedirs(LOGS, exist_ok=True)
    path = os.path.join(LOGS, f"{job['book']}-{job['start']}-{job['end']}.log")
    cmd = [os.path.join(SNAP, "pipeline_batch.sh"),
           str(job["book"]), str(job["start"]), str(job["end"]),
           "--channel", args.channel]
    if args.plan:                       # 计划模式：翻译归属已定好，不再各自解析层次
        cmd += ["--plan", os.path.abspath(args.plan), "--job", str(job["jid"])]
    else:
        cmd.append("--chapter")
    if args.nissaya:
        cmd.append("--nissaya")
    if args.dry_run:
        cmd.append("--dry-run")
    cmd += args.extra
    f = open(path, "a", encoding="utf-8")
    f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 第 {job['tries'] + 1} 次 =====\n")
    f.flush()
    env = dict(os.environ, PROJECT_ROOT=ROOT)   # 快照脚本靠它找项目根
    p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT,
                         start_new_session=True, env=env)
    return p, f, path


def hit_in(path, needles, tail_bytes=20000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - tail_bytes))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    return any(t in tail for t in needles)


def transient_in(path):
    return hit_in(path, TRANSIENT)


def rate_limited_in(path):
    return hit_in(path, RATE_LIMIT)


def cmd_run(args):
    os.makedirs(WORK, exist_ok=True)
    if os.path.exists(LOCK):
        pid = open(LOCK).read().strip()
        try:
            os.kill(int(pid), 0)
            sys.exit(f"已有守护进程在跑（pid {pid}）。要停用：python3 scripts/run_daemon.py stop")
        except (ValueError, ProcessLookupError):
            pass                       # 陈旧锁
    open(LOCK, "w").write(str(os.getpid()))
    if os.path.exists(STOP):
        os.remove(STOP)

    stopping = {"v": False}
    def on_sig(*_):
        stopping["v"] = True
        log_line("收到停止信号，跑完手头的作业就退出")
    signal.signal(signal.SIGINT, on_sig)
    signal.signal(signal.SIGTERM, on_sig)

    running = []               # [(job, (proc, fh, path))]
    try:
        snapshot_scripts()
        log_line("已快照 scripts/ → workspace/.snapshot（跑快照，改源码不影响在跑的作业）")
        jobs = build_jobs(args.book, args.start, args.end, args.plan)
        todo = [j for j in jobs if j["status"] in (PENDING, FAILED) and j["tries"] < args.tries]
        log_line(f"共 {len(jobs)} 章，待处理 {len(todo)}，并发 {args.workers}")
        if not wait_for_api(args.book, args.start, log_line):
            return

        while True:
            if os.path.exists(STOP):
                stopping["v"] = True

            # 外部可能直接改任务表（例如把 ❌ 复位成 ⬜ 重排）。守护进程一直用
            # 内存里的 jobs 覆盖写回，那些改动就被静默吃掉了——必须重新读回来。
            # 只接受「非在跑作业」的状态：running 的以内存为准，否则会跟收割打架。
            running_keys = {id(j) for j, _ in running}
            live = {(j["book"], j["start"], j["end"]): j for j in jobs
                    if id(j) in running_keys}
            for disk in load_jobs():
                k = (disk["book"], disk["start"], disk["end"])
                if k in live:
                    continue
                for j in jobs:
                    if (j["book"], j["start"], j["end"]) == k and j["status"] != disk["status"]:
                        j.update(status=disk["status"], tries=disk["tries"],
                                 began=disk.get("began", ""), ended=disk.get("ended", ""),
                                 note=disk.get("note", ""))
                        break

            # 收割
            for item in list(running):
                job, (p, fh, path) = item
                if p.poll() is None:
                    continue
                running.remove(item)
                fh.close()
                job["tries"] += 1
                job["ended"] = time.strftime("%Y-%m-%d %H:%M:%S")
                if p.returncode == 0:
                    job["status"] = DONE
                    job["note"] = ""
                    log_line(f"✓ {job['book']}:{job['start']}-{job['end']} {job['title']}")
                elif rate_limited_in(path):
                    job["status"] = PENDING
                    job["tries"] -= 1          # 撞额度不算作业失败
                    job["note"] = "撞额度，已退回队列"
                    job["began"] = job["ended"] = ""
                    log_line(f"🚦 {job['start']}-{job['end']} 撞到额度限制，"
                             f"全局暂停 {args.cooldown // 60} 分钟等窗口刷新")
                    if not cooldown(args.cooldown, log_line):
                        stopping["v"] = True
                elif transient_in(path):
                    job["status"] = PENDING
                    job["tries"] -= 1          # 环境问题不算次数
                    job["note"] = "环境异常（网络/5xx），已退回队列"
                    job["began"] = job["ended"] = ""
                    log_line(f"⏸ {job['start']}-{job['end']} 环境异常，退回队列并等 API")
                    if not wait_for_api(args.book, args.start, log_line):
                        stopping["v"] = True
                else:
                    job["note"] = f"退出码 {p.returncode}，见 {os.path.basename(path)}"
                    job["status"] = FAILED if job["tries"] >= args.tries else PENDING
                    log_line(f"✗ {job['start']}-{job['end']} 退出码 {p.returncode}"
                             f"（第 {job['tries']}/{args.tries} 次，日志 {path}）")
                save_jobs(jobs)

            # 派发
            while not stopping["v"] and len(running) < args.workers:
                nxt = next((j for j in jobs
                            if j["status"] == PENDING and j["tries"] < args.tries), None)
                if not nxt:
                    break
                nxt["status"] = RUNNING
                nxt["began"] = time.strftime("%Y-%m-%d %H:%M:%S")
                nxt["ended"] = ""
                save_jobs(jobs)
                running.append((nxt, spawn(nxt, args)))
                log_line(f"▶ {nxt['book']}:{nxt['start']}-{nxt['end']} {nxt['title']}")
                time.sleep(args.stagger)       # 错峰，别同时打满 API

            write_status(jobs, running)
            sync_subrows()
            if not running and (stopping["v"] or not any(
                    j["status"] == PENDING and j["tries"] < args.tries for j in jobs)):
                break
            time.sleep(5)

        done = sum(1 for j in jobs if j["status"] == DONE)
        failed = [j for j in jobs if j["status"] == FAILED]
        log_line(f"结束：完成 {done}/{len(jobs)}，失败 {len(failed)}")
        for j in failed:
            log_line(f"   失败 {j['book']}:{j['start']}-{j['end']} {j['title']}")
    finally:
        for _job, (_p, fh, _path) in running:
            try:
                fh.close()
            except Exception:
                pass
        if os.path.exists(LOCK):
            os.remove(LOCK)


def sync_subrows():
    """按 audit.log 刷新子行（层/分块）状态——作业跑两三小时，
    没有子行进度用户就只能干等。作业行不动，那是守护进程的账。"""
    import re
    rows = _read_rows()
    if not rows:
        return 0
    ok = {}
    if os.path.exists(AUDIT):
        for line in open(AUDIT, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("status") == "ok":
                ok.setdefault((r["book"], r["para"]), set()).add(r["step"])
    STEPS4 = {"translate", "review", "revise", "evaluate"}
    n = 0
    for r in rows:
        if r.get("类型") not in ("层", "分块") or r.get("归属", "").startswith("ref"):
            continue
        m = re.match(r"^(\d+):(\d+)-(\d+)$", r.get("坐标", ""))
        if not m:
            continue
        b, lo, hi = (int(x) for x in m.groups())
        paras = range(lo, hi + 1)
        done = sum(1 for p in paras if STEPS4 <= ok.get((b, p), set()))
        part = sum(1 for p in paras if ok.get((b, p)))
        total = len(list(paras))
        new = (EMOJI[DONE] if done == total else
               EMOJI[RUNNING] if part else EMOJI[PENDING])
        if r["状态"] != new:
            r["状态"] = new
            n += 1
        if part and done < total:
            r["备注"] = f"{done}/{total} 段走完四步"
    if n:
        tmp = JOBS + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        os.replace(tmp, JOBS)
    return n


def cmd_status(_args):
    jobs = load_jobs()
    if not jobs:
        sys.exit(f"还没有任务表（先跑 plan_jobs.py --csv {JOBS}，或直接 run）")
    counts = {}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    done = counts.get(DONE, 0)
    print(f"任务表 {JOBS}")
    print(f"共 {len(jobs)} 条：" +
          "  ".join(f"{EMOJI[k]} {counts.get(k, 0)}" for k in (DONE, RUNNING, PENDING, FAILED)) +
          f"   进度 {done * 100 // max(len(jobs), 1)}%")
    for j in jobs:
        if j["status"] in (RUNNING, FAILED):
            print(f"  {EMOJI[j['status']]}  {j['book']}:{j['start']}-{j['end']}  {j['title']}"
                  f"  起 {j.get('began', '') or '-'}  尝试 {j['tries']}  {j.get('note', '')}")
    dones = [j for j in jobs if j["status"] == DONE and j.get("began") and j.get("ended")]
    if dones:
        secs = []
        for j in dones:
            d = _dur(j["began"], j["ended"])
            if d:
                h, m, s2 = (int(x) for x in d.split(":"))
                secs.append(h * 3600 + m * 60 + s2)
        if secs:
            avg = sum(secs) // len(secs)
            left = len(jobs) - done
            print(f"\n已完成 {len(secs)} 条，平均耗时 {avg // 60} 分 {avg % 60} 秒"
                  f"；剩 {left} 条")
    if os.path.exists(STATUS):
        print(f"\n{STATUS}:")
        print(open(STATUS, encoding="utf-8").read())


def cmd_stop(_args):
    os.makedirs(WORK, exist_ok=True)
    open(STOP, "w").write("stop\n")
    print(f"已写 {STOP}——守护进程会跑完手头的作业再退出（可能要几十分钟）")


def cmd_reset(_args):
    jobs = load_jobs()
    n = 0
    for j in jobs:
        if j["status"] == FAILED:
            j["status"], j["tries"], n = PENDING, 0, n + 1
    save_jobs(jobs)
    print(f"已把 {n} 个失败作业改回 pending")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="run",
                    choices=["run", "status", "stop", "reset-failed"])
    ap.add_argument("--book", type=int, default=93, help="本文的 book")
    ap.add_argument("--start", type=int, default=1, help="起始段（含）")
    ap.add_argument("--end", type=int, default=10**9, help="结束段（含）")
    ap.add_argument("--channel", default="", help="目标 channel uid")
    ap.add_argument("--workers", type=int, default=3, help="并行作业数")
    ap.add_argument("--tries", type=int, default=2, help="每章最多跑几次")
    ap.add_argument("--stagger", type=float, default=10, help="派发间隔秒，错峰用")
    ap.add_argument("--cooldown", type=int, default=1800,
                    help="撞到额度限制后全局冷却秒数（默认 30 分钟）")
    ap.add_argument("--plan", default="", help="作业计划 json（plan_jobs.py 产出）")
    ap.add_argument("--nissaya", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args, extra = ap.parse_known_args()   # 认不出的参数原样透传给 pipeline_batch.sh
    args.extra = extra

    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "stop":
        return cmd_stop(args)
    if args.cmd == "reset-failed":
        return cmd_reset(args)
    if not args.channel:
        sys.exit("run 需要 --channel <uid>")
    cmd_run(args)


if __name__ == "__main__":
    main()
