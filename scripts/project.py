# -*- coding: utf-8 -*-
"""project 文件：一个项目的**唯一状态载体**——结构、进度、命令都在这一个 json 里。

    workspace/projects/<name>/project.json  项目文件（层级：项目 → 流水线 → 任务）
    workspace/projects/index.json      项目索引
    workspace/projects/<name>.html     给人看的折叠视图（单文件，json 内嵌）
    workspace/projects/index.html      索引页，点进去看单个项目

## 写者只有一个

守护进程是**唯一**能改 project.json 的进程。worker 只往 `workspace/audit.log`
追加记录（append-only，崩溃安全），守护进程定期把它汇总进 project.json 并原子落盘
（写 tmp 再 rename）。人工操作不直接改状态，而是写 `command` 字段（pause / resume /
reset-failed），守护进程下一轮读到就执行并清空。

这么定是有教训的：状态曾经同时存在 CSV 与守护进程内存里，`reset-failed` 改好的表
被退出中的守护进程用旧内存覆盖了回去。

## project.json 只是视图，audit.log 才是事实

`rollup()` 能从 audit.log 完全重建分块级进度，所以 project.json 损坏或落后都不致命
（`project.py rebuild <name>`）。断电重来也就是重新汇总一遍。

用法：
    python3 scripts/project.py list                      # 列出全部项目
    python3 scripts/project.py status <name>             # 打印进度
    python3 scripts/project.py pause <name>              # 请求暂停（守护进程收尾后停）
    python3 scripts/project.py resume <name>
    python3 scripts/project.py reset-failed <name>
    python3 scripts/project.py rebuild <name>            # 用 audit.log 重算进度
    python3 scripts/project.py export [<name>]           # 导出 html（不给名字＝全部＋索引）
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "workspace")
PROJECTS = os.path.join(WORK, "projects")
INDEX = os.path.join(PROJECTS, "index.json")
# 全局旧账：迁到「一项目一目录」之前，五个项目的账混在这一本里。只读，不再写。
LEGACY_AUDIT = os.path.join(WORK, "audit.log")

SCHEMA = 2
PENDING, RUNNING, DONE, FAILED, SKIPPED = "pending", "running", "done", "failed", "skipped"
STATE_CN = {PENDING: "未开始", RUNNING: "进行中", DONE: "已完成",
            FAILED: "失败", SKIPPED: "跳过"}
# harmonize 的规模阈值（三层合计巴利字符）。经验初值，见 WORKFLOW.md「harmonize 的规模分级」
THRESHOLDS = {"harmonize_direct_max": 30000,
              "harmonize_cross_chars": 12000,
              "harmonize_layer_chars": 15000}


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 一项目一目录 ────────────────────────────────────────────────────────
# workspace/projects/<name>/ 里放这个项目的**全部**东西：project.json、audit.log、
# export/、reports/、logs/、epub/。历史上它们散在 workspace 下的公共目录里
#（export 尤其是共用的），发信打包时要从一堆文件里挑属于本项目的那些，容易挑错。

def home(name):
    return os.path.join(PROJECTS, name)


def path_of(name):
    return os.path.join(home(name), "project.json")


def audit_path(name):
    return os.path.join(home(name), "audit.log")


def sub(name, *parts):
    """项目目录下的子路径（export / reports / logs / epub …）。"""
    return os.path.join(home(name), *parts)


def load(name):
    p = path_of(name)
    if not os.path.exists(p):
        sys.exit(f"找不到项目 {name}（{p}）")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(proj):
    """原子落盘：写 tmp 再 rename，中途断电也不会留下半个文件。"""
    os.makedirs(home(proj["name"]), exist_ok=True)
    proj["updated"] = now()
    p = path_of(proj["name"])
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, p)
    return p


def all_names():
    if not os.path.isdir(PROJECTS):
        return []
    return sorted(d for d in os.listdir(PROJECTS)
                  if os.path.isfile(os.path.join(PROJECTS, d, "project.json")))


# ── 模型：project → pipelines[] → tasks[] ───────────────────────────────
# **task = (chunk, step)**，是唯一带状态的单位。pipeline（一章 × 各层）内部严格
# 单线按 tasks 顺序跑，pipeline 之间可以并行——并行在这里只压缩墙钟，不省 token。
#
# 状态只有一个来源：task 自己。执行器把 task_id 写进项目的 audit.log，守护进程
# **查表**落状态。此前是记 (step, book, para) 再由 rollup() 反推 chunk 与作业的
# 状态，推错过两次（跳过的步骤没有账 → chunk 永远升不到 done → 作业被反复打回
# FAILED）。反推没了，这类 bug 也就没了。

def is_archive(proj):
    """旧格式（schema 1）只当存档看：能读能显示，不再跑。"""
    return proj.get("schema") != SCHEMA or "pipelines" not in proj


def pipelines(proj):
    return proj.get("pipelines") or []


def units(pipe):
    """一条流水线下面全部 task。"""
    return list(pipe.get("tasks") or [])


def all_tasks(proj):
    for pipe in pipelines(proj):
        for t in units(pipe):
            yield pipe, t


def by_step(proj, *steps):
    return [t for _p, t in all_tasks(proj) if t.get("step") in steps]


def counts(nodes):
    c = {k: 0 for k in (PENDING, RUNNING, DONE, FAILED, SKIPPED)}
    for n in nodes:
        c[n.get("status", PENDING)] = c.get(n.get("status", PENDING), 0) + 1
    return c


def settled(node):
    """done 与 skipped 都是终态：skipped 是「按规矩不该做」，同样满足后继依赖。"""
    return node.get("status") in (DONE, SKIPPED)


def pct(nodes, key="chars"):
    tot = sum(n.get(key, 0) for n in nodes) or 1
    got = sum(n.get(key, 0) for n in nodes if settled(n))
    return 100.0 * got / tot


def chars(nodes, key="chars"):
    """(已了结字符, 总字符)——pct 的分子分母，报进度时连绝对量一起给。"""
    return (sum(n.get(key, 0) for n in nodes if settled(n)),
            sum(n.get(key, 0) for n in nodes))


def progress(proj):
    """(翻译进度%, 统稿完成/总数, 导出完成/总数)——三件事各算各的。

    翻译进度只看 translate：review / revise / evaluate 读的是同一批文字，
    算进去等于把同一段字符数好几遍。
    """
    tr = by_step(proj, "translate")
    hs = by_step(proj, "harmonize")
    ex = by_step(proj, "export")
    return (pct(tr),
            sum(1 for t in hs if settled(t)), len(hs),
            sum(1 for t in ex if settled(t)), len(ex))


# ── audit.log → task 状态（查表，不是推断）───────────────────────────────

AUDIT_STATUS = {"ok": DONE, "fail": FAILED, "skip": SKIPPED, "start": RUNNING}


def audit_tasks(name):
    """项目 audit.log → {task_id: 状态}，后写的覆盖先写的。"""
    seen = {}
    path = audit_path(name)
    if not os.path.exists(path):
        return seen
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid, st = r.get("task"), AUDIT_STATUS.get(r.get("status"))
            if tid and st:
                seen[tid] = st
    return seen


def apply_audit(proj):
    """把 audit.log 里的 task 结果落到项目文件上，并按 task 推出流水线状态。"""
    seen = audit_tasks(proj["name"])
    touched = 0
    for pipe in pipelines(proj):
        ts = units(pipe)
        for t in ts:
            st = seen.get(t["id"])
            if st and st != t.get("status"):
                t["status"] = st
                touched += 1
        c = counts(ts)
        if ts and c[DONE] + c[SKIPPED] == len(ts):
            new = DONE
        elif c[FAILED]:
            new = FAILED
        elif c[RUNNING]:
            new = RUNNING
        else:
            new = pipe.get("status", PENDING)
        # PENDING 是「已排队等重跑」（reset-failed 刚退回的），别让旧账把它顶回 FAILED
        if pipe.get("status") == PENDING and new == FAILED:
            new = PENDING
        if new != pipe.get("status"):
            pipe["status"] = new
            touched += 1
    return touched



# ── 索引 ────────────────────────────────────────────────────────────────

def build_index():
    rows = []
    for name in all_names():
        p = load(name)
        if is_archive(p):                     # 旧格式：原样列出，不去解释它的内部结构
            rows.append({"name": name, "title": p.get("title", name), "state": "archive",
                         "book": p.get("book"), "channel": p.get("channel"),
                         "jobs": len(p.get("jobs") or []), "job_counts": {},
                         "units": 0, "unit_counts": {}, "chars": 0, "pct": 100.0,
                         "archive": True,
                         "updated": p.get("updated", ""), "created": p.get("created", "")})
            continue
        us = [t for _pipe, t in all_tasks(p)]
        jc = counts(pipelines(p))
        rows.append({
            "name": name, "title": p.get("title", name), "state": p.get("state", "idle"),
            "book": p.get("book"), "channel": p.get("channel"),
            "jobs": len(pipelines(p)), "job_counts": jc,
            "units": len(us), "unit_counts": counts(us),
            "chars": sum(t.get("chars", 0) for t in us),
            "pct": round(progress(p)[0], 1),
            "updated": p.get("updated", ""), "created": p.get("created", ""),
        })
    rows.sort(key=lambda r: r["updated"], reverse=True)
    os.makedirs(PROJECTS, exist_ok=True)
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump({"schema": SCHEMA, "updated": now(), "projects": rows},
                  f, ensure_ascii=False, indent=1)
    return rows


# ── HTML 导出（单文件：模板 + 内嵌 json，折叠树用原生 details） ─────────

def export_html(proj):
    from html_report import render_project  # noqa: E402
    out = os.path.join(home(proj["name"]), "project.html")
    open(out, "w", encoding="utf-8").write(render_project(proj))
    return out


def export_index(rows):
    from html_report import render_index  # noqa: E402
    out = os.path.join(PROJECTS, "index.html")
    open(out, "w", encoding="utf-8").write(render_index(rows))
    return out


# ── 命令：人工写字段，守护进程执行 ──────────────────────────────────────

def put_command(name, cmd):
    proj = load(name)
    proj["command"] = {"cmd": cmd, "at": now()}
    save(proj)
    print(f"已给项目 {name} 写下命令 {cmd}——守护进程下一轮读到就执行")


def take_command(proj):
    """守护进程调用：取出待执行命令并清空（取走即消费）。"""
    cmd = (proj.get("command") or {}).get("cmd")
    if cmd:
        proj["command"] = None
    return cmd


def cmd_status(name):
    p = load(name)
    print(f"项目 {p['name']}｜{p.get('title','')}｜状态 {p.get('state','idle')}"
          f"｜channel {p.get('channel','')}")
    if is_archive(p):
        print("旧格式（schema 1），只作存档：能看不能跑。")
        return
    us = [t for _pipe, t in all_tasks(p)]
    jc, uc = counts(pipelines(p)), counts(us)
    tr, hd, ht, ed, et = progress(p)
    cdone, ctot = chars(by_step(p, "translate"))
    print(f"流水线 {len(pipelines(p))}：" + "  ".join(f"{STATE_CN[k]} {v}" for k, v in jc.items() if v))
    print(f"翻译 {tr:.1f}%（巴利字符 {cdone:,}/{ctot:,}）｜统稿 {hd}/{ht}｜导出 {ed}/{et}")
    print(f"任务 {len(us)}：" + "  ".join(f"{STATE_CN[k]} {v}" for k, v in uc.items() if v))
    for pipe in pipelines(p):
        if pipe.get("status") != FAILED:
            continue
        bad = [t["id"] for t in units(pipe) if t.get("status") == FAILED]
        print(f"  ❌ {pipe['id']} {pipe.get('title','')}  尝试 {pipe.get('tries',0)}"
              f"  失败任务 {', '.join(bad[:6])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "status", "pause", "resume",
                                    "reset-failed", "rebuild", "export"])
    ap.add_argument("name", nargs="?", default="")
    args = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    if args.cmd == "list":
        rows = build_index()
        if not rows:
            sys.exit("还没有项目（workspace/projects/ 是空的）")
        for r in rows:
            print(f"{r['name']:<28} {r['state']:<8} 流水线 "
                  f"{r['job_counts'].get(DONE, 0)}/{r['jobs']:<5}"
                  f" {r['pct']:>5.1f}%  更新 {r['updated']}")
        return

    if args.cmd != "export" and not args.name:
        sys.exit("要给项目名")

    if args.cmd == "status":
        cmd_status(args.name)
    elif args.cmd in ("pause", "resume", "reset-failed"):
        put_command(args.name, args.cmd)
    elif args.cmd == "rebuild":
        p = load(args.name)
        if is_archive(p):
            sys.exit("旧格式项目只作存档，不重算")
        n = apply_audit(p)
        save(p)
        print(f"按 audit.log 落状态，改动 {n} 个节点")
        cmd_status(args.name)
    elif args.cmd == "export":
        names = [args.name] if args.name else all_names()
        for nm in names:
            print("→", export_html(load(nm)))
        print("→", export_index(build_index()))


if __name__ == "__main__":
    main()
