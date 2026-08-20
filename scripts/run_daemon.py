# -*- coding: utf-8 -*-
"""长任务守护进程：按章切分整本书，多进程并行跑三层流水线，断点续传 + 失败重试。

一个**作业 = 本文的一章**。三层（本文/义注/复注）由 `pipeline_batch.sh --chapter`
在作业内部解析并处理，所以章与章之间互不相干，可以放心并行。

    python3 scripts/run_daemon.py run --project dn-silakkhandhavagga --channel <uid> --workers 4

作业与状态都在 **project 文件**里（`workspace/projects/<name>.json`，由
`plan_jobs.py --project` 产出）。**本进程是它唯一的写者**：worker 只往 audit.log
追加，人工操作写 `command` 字段（`project.py pause/resume/reset-failed`）由这里消费。

守护行为：
  · 单实例锁（workspace/daemon.lock），重复启动会拒绝
  · 状态每轮汇总进项目文件并原子落盘，进程被杀掉重启后接着跑
  · 每个作业独立日志（workspace/logs/<book>-<start>-<end>.log）
  · 失败自动重试；**连不上或服务端 5xx 不算作业失败**，退回队列并整体退避
  · 启动前与每轮探活；API 挂了就停下等，不空烧 LLM 调用
  · 优雅停止：`touch workspace/STOP`（或 Ctrl-C / SIGTERM），跑完手头的作业才退出

子命令：
    run            跑（默认）
    status         打印进度
    stop           写 STOP 文件，让在跑的守护进程收尾退出
    pause/resume   给项目写命令，守护进程下一轮消费
    reset-failed   把 failed 作业改回 pending（守护进程在跑时走命令通道）
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import jget, run as wp_run  # noqa: E402
import project as pj  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "workspace")
LOGS = os.path.join(WORK, "logs")
# 状态载体是 project 文件（workspace/projects/<name>.json）。**守护进程是唯一写者**：
# worker 只往 audit.log 追加，人工操作写 command 字段由这里消费。见 ARCHITECTURE.md。
# 旧的 task_alloc.csv 已废弃——状态曾同时存在 CSV 与内存两处，手工 reset-failed
# 被退出中的守护进程用旧内存覆盖了回去。
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
              "resets at", "limit reached", "5-hour limit", "weekly limit",
              # claude -p 撞额度时原样吐这一句到 stdout 并 rc=1：
              #   You've hit your session limit · resets 1:40pm (UTC)
              # 没有 "at"，前面的 "resets at" 匹配不到，于是被当成作业失败白耗重试次数。
              "session limit", "hit your", "resets ")


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


def _dur(a, b):
    if not (a and b):
        return ""
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        d = int(time.mktime(time.strptime(b, fmt)) - time.mktime(time.strptime(a, fmt)))
    except ValueError:
        return ""
    return f"{d // 3600:d}:{d % 3600 // 60:02d}:{d % 60:02d}"


PROJ = {"name": None, "data": None}      # 内存里这一份就是权威，落盘走 pj.save


def proj_load(name):
    PROJ["name"], PROJ["data"] = name, pj.load(name)
    return PROJ["data"]


def job_coord(pjob):
    """作业的派发坐标：有本文用本文，前置作业（注释书开头）用它的第一层。"""
    m = pjob.get("mula") or (pjob["layers"][0] if pjob.get("layers") else None)
    return int(m["book"]), int(m["start"]), int(m["end"])


def load_jobs():
    """project 的作业 → 调度用的扁平结构（字段名沿用旧的，主循环不用改）。"""
    out = []
    for j in PROJ["data"]["jobs"]:
        b, lo, hi = job_coord(j)
        out.append({"book": b, "start": lo, "end": hi,
                    "status": j.get("status", PENDING), "tries": j.get("tries", 0),
                    "title": j.get("title", ""), "jid": j["id"],
                    "began": j.get("started") or "", "ended": j.get("finished") or "",
                    "note": j.get("note", "")})
    return out


def save_jobs(jobs):
    """把调度状态写回 project 并原子落盘。"""
    by = {str(j["jid"]): j for j in jobs}
    for pjob in PROJ["data"]["jobs"]:
        j = by.get(str(pjob["id"]))
        if not j:
            continue
        pjob["status"] = j["status"]
        pjob["tries"] = j["tries"]
        pjob["started"] = j.get("began") or None
        pjob["finished"] = j.get("ended") or None
        pjob["note"] = j.get("note", "")
    pj.save(PROJ["data"])


def build_jobs(book, lo, hi, project):
    """读项目里的作业；上次被强杀留下的 running 复位为 pending。"""
    proj_load(project)
    jobs = [j for j in load_jobs() if lo <= j["start"] and j["end"] <= hi]
    jobs.sort(key=lambda j: int(j["jid"]))
    for j in jobs:
        if j["status"] == RUNNING:      # 上次被强杀留下的
            j["status"] = PENDING
            j["began"] = ""
    save_jobs(jobs)
    return jobs


def take_command(jobs, args, log):
    """消费人工命令（project.py pause/resume/reset-failed 写进来的）。

    人工不直接改状态——单写者是这条流水线最贵的一课，见模块头。
    返回 True 表示要停机。
    """
    cmd = pj.take_command(PROJ["data"])
    if not cmd:
        return PROJ["data"].get("state") == "paused"
    if cmd == "pause":
        PROJ["data"]["state"] = "paused"
        log("收到 pause：跑完手头的作业就停")
    elif cmd == "resume":
        PROJ["data"]["state"] = "running"
        log("收到 resume：继续派发")
    elif cmd == "reset-failed":
        n = 0
        for j in jobs:
            if j["status"] == FAILED:
                j.update(status=PENDING, tries=0, note="", began="", ended="")
                n += 1
        log(f"收到 reset-failed：{n} 个失败作业已退回队列")
    save_jobs(jobs)
    return PROJ["data"].get("state") == "paused"


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
    if args.project:                    # 计划模式：翻译归属已定好，不再各自解析层次
        cmd += ["--plan", pj.path_of(args.project), "--job", str(job["jid"])]
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


def hit_since_last_run(path, needles):
    """只在**本次运行**那一段日志里找。

    额度提示往往出现在作业早期，后面还有几十 KB 的导出与评估输出，按固定尾部
    字节数去找必然漏掉——今天 4 个作业就是这样被误判成失败、耗光重试次数的。
    按 `===== <时间> 第 N 次 =====` 分段，只看最后一段，也就不会翻到上一轮的旧提示。
    """
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    i = text.rfind("\n===== ")
    if i >= 0:
        text = text[i:]
    return any(t in text for t in needles)


def transient_in(path):
    return hit_in(path, TRANSIENT) or hit_since_last_run(path, TRANSIENT)


def rate_limited_in(path):
    return hit_since_last_run(path, RATE_LIMIT)


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
        jobs = build_jobs(args.book, args.start, args.end, args.project)
        PROJ["data"]["state"] = "running"
        todo = [j for j in jobs if j["status"] in (PENDING, FAILED) and j["tries"] < args.tries]
        log_line(f"共 {len(jobs)} 章，待处理 {len(todo)}，并发 {args.workers}")
        if not wait_for_api(args.book, args.start, log_line):
            return

        while True:
            if os.path.exists(STOP):
                stopping["v"] = True
            if take_command(jobs, args, log_line):
                stopping["v"] = True

            # 人工可能在守护进程跑着的时候改了项目文件（虽然不推荐）。只接受
            # **非在跑作业**的状态：running 的以内存为准，否则会跟收割打架。
            running_keys = {str(j["jid"]) for j, _ in running}
            disk = pj.load(PROJ["name"])
            by_disk = {str(d["id"]): d for d in disk["jobs"]}
            for j in jobs:
                d = by_disk.get(str(j["jid"]))
                if not d or str(j["jid"]) in running_keys:
                    continue
                if d.get("status", PENDING) != j["status"]:
                    j.update(status=d.get("status", PENDING), tries=d.get("tries", 0),
                             note=d.get("note", ""))
            PROJ["data"]["command"] = disk.get("command")   # 命令只从盘上来

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
                    # 导出这一步 pipeline 不记 audit（只在日志里打一行），
                    # 作业整体跑完就等于它的导出也做了，在这里顺手标掉。
                    pjob = next((x for x in PROJ["data"]["jobs"]
                                 if str(x["id"]) == str(job["jid"])), None)
                    if pjob and pjob.get("export"):
                        pjob["export"]["status"] = DONE
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
        # 这一轮可能只跑了 --start/--end 圈定的一段，项目整体完没完要看全表
        whole = PROJ["data"]["jobs"]
        all_done = all(j.get("status") == DONE for j in whole)
        PROJ["data"]["state"] = ("done" if all_done else
                                 "paused" if stopping["v"] else "idle")
        save_jobs(jobs)
        sync_subrows(force=True)
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


_LAST_EXPORT = {"t": 0}


def sync_subrows(force=False):
    """按 audit.log 刷新分块进度，并（节流地）重导 html。

    作业一跑两三小时，没有分块级进度用户就只能干等。分块状态是 audit.log 推出来的，
    作业状态由守护进程自己记——两者的写入都在这个进程里，不会打架。
    """
    n = pj.rollup(PROJ["data"])
    pj.save(PROJ["data"])
    if n or force or time.time() - _LAST_EXPORT["t"] > 60:
        _LAST_EXPORT["t"] = time.time()
        try:
            pj.export_html(PROJ["data"])
            pj.export_index(pj.build_index())
        except Exception as e:                    # 导出失败不该拖垮跑批
            log_line(f"⚠ 导出 html 失败：{e}")
    return n


def cmd_status(args):
    proj_load(args.project)
    jobs = load_jobs()
    p = PROJ["data"]
    tr, hd, ht, ed, et = pj.progress(p)
    counts = {}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    print(f"项目 {p['name']}｜{p.get('title', '')}｜状态 {p.get('state', 'idle')}")
    print(f"共 {len(jobs)} 个作业：" +
          "  ".join(f"{EMOJI[k]} {counts.get(k, 0)}" for k in (DONE, RUNNING, PENDING, FAILED)))
    print(f"翻译 {tr:.1f}%（按巴利字符）｜统稿 {hd}/{ht}｜导出 {ed}/{et}")
    for j in jobs:
        if j["status"] in (RUNNING, FAILED):
            print(f"  {EMOJI[j['status']]}  {j['book']}:{j['start']}-{j['end']}  {j['title']}"
                  f"  起 {j.get('began', '') or '-'}  尝试 {j['tries']}  {j.get('note', '')}")
    dones = [j for j in jobs if j["status"] == DONE and j.get("began") and j.get("ended")]
    secs = []
    for j in dones:
        d = _dur(j["began"], j["ended"])
        if d:
            h, m, s2 = (int(x) for x in d.split(":"))
            secs.append(h * 3600 + m * 60 + s2)
    if secs:
        avg = sum(secs) // len(secs)
        left = sum(1 for j in jobs if j["status"] != DONE)
        print(f"\n已完成 {len(secs)} 个，平均耗时 {avg // 60} 分 {avg % 60} 秒；剩 {left} 个")
    print(f"\n详细进度：workspace/projects/{p['name']}.html")


def cmd_stop(_args):
    os.makedirs(WORK, exist_ok=True)
    open(STOP, "w").write("stop\n")
    print(f"已写 {STOP}——守护进程会跑完手头的作业再退出（可能要几十分钟）")
    print("看门狗不受这个开关影响，会继续巡检但不拉起守护进程；"
          "删掉 STOP 它就把守护进程拉回来。要连看门狗一起停：touch workspace/WATCHDOG_STOP")


def cmd_reset(args):
    """不直接改状态——写命令，由守护进程消费。守护进程没跑时就地执行。"""
    proj_load(args.project)
    if os.path.exists(LOCK):
        pj.put_command(args.project, "reset-failed")
        return
    jobs = load_jobs()
    n = 0
    for j in jobs:
        if j["status"] == FAILED:
            j.update(status=PENDING, tries=0, note="", began="", ended="")
            n += 1
    save_jobs(jobs)
    print(f"守护进程没在跑，已就地把 {n} 个失败作业改回 pending")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="run",
                    choices=["run", "status", "stop", "reset-failed", "pause", "resume"])
    ap.add_argument("--book", type=int, default=93, help="本文的 book")
    ap.add_argument("--start", type=int, default=1, help="起始段（含）")
    ap.add_argument("--end", type=int, default=10**9, help="结束段（含）")
    ap.add_argument("--channel", default="", help="目标 channel uid")
    ap.add_argument("--workers", type=int, default=3, help="并行作业数")
    ap.add_argument("--tries", type=int, default=2, help="每章最多跑几次")
    ap.add_argument("--stagger", type=float, default=10, help="派发间隔秒，错峰用")
    ap.add_argument("--cooldown", type=int, default=1800,
                    help="撞到额度限制后全局冷却秒数（默认 30 分钟）")
    ap.add_argument("--project", default="", help="项目名（workspace/projects/<name>.json）")
    ap.add_argument("--nissaya", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args, extra = ap.parse_known_args()   # 认不出的参数原样透传给 pipeline_batch.sh
    args.extra = extra

    if not args.project:
        names = pj.all_names()
        if len(names) == 1:
            args.project = names[0]           # 只有一个项目就不用每次敲名字
        else:
            sys.exit("要给 --project <name>（可选的有：" + ", ".join(names) + "）")
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd in ("pause", "resume"):
        return pj.put_command(args.project, args.cmd)
    if args.cmd == "stop":
        return cmd_stop(args)
    if args.cmd == "reset-failed":
        return cmd_reset(args)
    if not args.channel:
        sys.exit("run 需要 --channel <uid>")
    cmd_run(args)


if __name__ == "__main__":
    main()
