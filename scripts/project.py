# -*- coding: utf-8 -*-
"""project 文件：一个项目的**唯一状态载体**——结构、进度、命令都在这一个 json 里。

    workspace/projects/<name>.json     项目文件（层级：项目 → 作业 → 层 → 分块 / 统稿 / 导出）
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
AUDIT = os.path.join(WORK, "audit.log")
INDEX = os.path.join(PROJECTS, "index.json")

SCHEMA = 1
PENDING, RUNNING, DONE, FAILED, SKIPPED = "pending", "running", "done", "failed", "skipped"
STATE_CN = {PENDING: "未开始", RUNNING: "进行中", DONE: "已完成",
            FAILED: "失败", SKIPPED: "跳过"}
# harmonize 的规模阈值（三层合计巴利字符）。经验初值，见 WORKFLOW.md「harmonize 的规模分级」
THRESHOLDS = {"harmonize_direct_max": 30000,
              "harmonize_cross_chars": 12000,
              "harmonize_layer_chars": 15000}


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def path_of(name):
    return os.path.join(PROJECTS, f"{name}.json")


def load(name):
    p = path_of(name)
    if not os.path.exists(p):
        sys.exit(f"找不到项目 {name}（{p}）")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(proj):
    """原子落盘：写 tmp 再 rename，中途断电也不会留下半个文件。"""
    os.makedirs(PROJECTS, exist_ok=True)
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
    return sorted(f[:-5] for f in os.listdir(PROJECTS)
                  if f.endswith(".json") and f != "index.json")


# ── 节点遍历 ────────────────────────────────────────────────────────────
# 层级：job → layers[] → chunks[]，外加 job.harmonize.cross[] / .layer[] 与 job.export

def units(job):
    """一个作业下面全部**可执行单元**（带状态的叶子）。"""
    for lay in job.get("layers", []):
        for c in lay.get("chunks", []):
            yield c
    h = job.get("harmonize") or {}
    for c in h.get("cross", []) + h.get("layer", []):
        yield c
    if job.get("export"):
        yield job["export"]


def counts(nodes):
    c = {k: 0 for k in (PENDING, RUNNING, DONE, FAILED, SKIPPED)}
    for n in nodes:
        c[n.get("status", PENDING)] = c.get(n.get("status", PENDING), 0) + 1
    return c


def pct(nodes, key="chars"):
    tot = sum(n.get(key, 0) for n in nodes) or 1
    got = sum(n.get(key, 0) for n in nodes if n.get("status") == DONE)
    return 100.0 * got / tot


def chunks_of(proj):
    """全部翻译分块——进度按它们的字符数算。

    不能把 harmonize / export 的字符也加进来：统稿读的是同一批文字，
    加进去等于把同一段字符数了两遍，进度会凭空缩水。
    """
    return [c for j in proj["jobs"] for lay in j.get("layers", []) for c in lay.get("chunks", [])]


def progress(proj):
    """(翻译进度%, 统稿完成/总数, 导出完成/总数)——三件事各算各的。"""
    tr = pct(chunks_of(proj))
    hs = [c for j in proj["jobs"] for c in ((j.get("harmonize") or {}).get("cross", [])
                                            + (j.get("harmonize") or {}).get("layer", []))]
    ex = [j["export"] for j in proj["jobs"] if j.get("export")]
    return (tr,
            sum(1 for c in hs if c.get("status") == DONE), len(hs),
            sum(1 for c in ex if c.get("status") == DONE), len(ex))


# ── 从 audit.log 汇总进度 ───────────────────────────────────────────────

def audit_done(channel=None):
    """audit.log → {(step, book, para): status}，后写的覆盖先写的。"""
    seen = {}
    if not os.path.exists(AUDIT):
        return seen
    with open(AUDIT, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if channel and r.get("channel") not in (None, channel):
                continue
            key = (r.get("step"), r.get("book"), r.get("paragraph", r.get("para")))
            if None in key[:2]:
                continue
            seen[key] = r.get("status")
    return seen


def rollup(proj, steps=("translate", "review", "revise")):
    """按 audit.log 刷新分块与统稿状态。

    分块：每一段的每一步都 ok 才算 done。
    统稿：audit.log 里 harmonize 是按段记的，所以一个统稿单元覆盖的段全 ok 才算 done。
    导出：pipeline 不给 export 记账（它只在日志里打一行），所以导出节点由作业完成时
    顺带标记，不在这里推。
    """
    done = audit_done(proj.get("channel"))
    touched = 0
    for job in proj["jobs"]:
        for lay in job.get("layers", []):
            b = lay["book"]
            for ch in lay.get("chunks", []):
                ps = range(ch["start"], ch["end"] + 1)
                ok = all(done.get((s, b, p)) == "ok" for s in steps for p in ps)
                bad = any(done.get((s, b, p)) == "fail" for s in steps for p in ps)
                new = DONE if ok else (FAILED if bad else ch.get("status", PENDING))
                if new != ch.get("status"):
                    ch["status"] = new
                    touched += 1
        # 统稿单元：横向块跨多层，每层各自的段都要 ok
        h = job.get("harmonize") or {}
        for c in h.get("cross", []) + h.get("layer", []):
            spans = ([(int(b), r[0], r[1]) for b, r in (c.get("layers") or {}).items()]
                     or [(c.get("book"), c.get("start"), c.get("end"))])
            spans = [x for x in spans if None not in x]
            ok = bool(spans) and all(done.get(("harmonize", b, p)) == "ok"
                                     for b, lo, hi in spans for p in range(lo, hi + 1))
            if ok and c.get("status") != DONE:
                c["status"] = DONE
                touched += 1

        # 作业状态由它的单元推出来；跑着的那个由守护进程自己标 running
        us = list(units(job))
        c = counts(us)
        if c[DONE] == len(us) and us:
            job["status"] = DONE
        elif job.get("status") != RUNNING and c[FAILED]:
            job["status"] = FAILED
    return touched


# ── 索引 ────────────────────────────────────────────────────────────────

def build_index():
    rows = []
    for name in all_names():
        p = load(name)
        us = [u for j in p["jobs"] for u in units(j)]
        jc = counts(p["jobs"])
        rows.append({
            "name": name, "title": p.get("title", name), "state": p.get("state", "idle"),
            "book": p.get("book"), "channel": p.get("channel"),
            "jobs": len(p["jobs"]), "job_counts": jc,
            "units": len(us), "unit_counts": counts(us),
            "chars": sum(j.get("chars", 0) for j in p["jobs"]),
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
    out = os.path.join(PROJECTS, f"{proj['name']}.html")
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
    us = [u for j in p["jobs"] for u in units(j)]
    jc, uc = counts(p["jobs"]), counts(us)
    print(f"项目 {p['name']}｜{p.get('title','')}｜状态 {p.get('state','idle')}"
          f"｜channel {p.get('channel','')}")
    tr, hd, ht, ed, et = progress(p)
    print(f"作业 {len(p['jobs'])}：" + "  ".join(f"{STATE_CN[k]} {v}" for k, v in jc.items() if v))
    print(f"翻译 {tr:.1f}%（按巴利字符）｜统稿 {hd}/{ht}｜导出 {ed}/{et}")
    print(f"单元 {len(us)}：" + "  ".join(f"{STATE_CN[k]} {v}" for k, v in uc.items() if v))
    bad = [j for j in p["jobs"] if j.get("status") == FAILED]
    for j in bad[:20]:
        print(f"  ❌ {j['id']} {j.get('title','')}  尝试 {j.get('tries',0)}  {j.get('note','')}")


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
            print(f"{r['name']:<28} {r['state']:<8} 作业 {r['job_counts'][DONE]}/{r['jobs']:<5}"
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
        n = rollup(p)
        save(p)
        print(f"按 audit.log 重算，改动 {n} 个分块状态")
        cmd_status(args.name)
    elif args.cmd == "export":
        names = [args.name] if args.name else all_names()
        for nm in names:
            print("→", export_html(load(nm)))
        print("→", export_index(build_index()))


if __name__ == "__main__":
    main()
