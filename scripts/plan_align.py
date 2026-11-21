# -*- coding: utf-8 -*-
"""按**自建对照表**规划（schema 3）：层次、父子关系、跨层对应都不看书目表与 cs_para。

plan_scan.py 的父层对照、义注参考、统稿配对全靠 cs_para 与书目表的 tag / related_name。
有的书族这些数据不可靠——Abhidhammatthasaṅgaha 一族：本论与 Vibhāvinī 都标 ṭīkā、
雷迪长老的两部标 añña；本论每品 cs 从 1 重编，Paramatthadīpanī 全书连续编号。
这时用 `align_lemma.py` 按被解释词建的对照表，本规划器只读那几张表。

产物与 plan_scan 同构（schema 3：layers[].chunks / harmonize / stages / tasks），
pipeline_batch.sh 与 run_daemon.py 不用改。不同处：

  · **作品与父子关系来自配置**（works.json），不推断。一层可有多部并列作品。
  · **每部作品可以只做部分步骤**（`steps`，如 Anudīpanī 只 translate 不 review）。
  · **屏障按配置的统稿批次排**：注释层开译要等父层**定稿**——父层若在某批统稿里
    被改写，就要等那批统稿；不再是 plan_scan 的「步骤优先、只等父层 translate」。
  · 统稿单元的只读对照可以跨作品：Paramatthadīpanī 的驳议块引 Vibhāvinī，
    单元的 read 同时带本论与 Vibhāvinī 的对应段。

配置（works.json，表路径相对它所在目录）：
    {"works": [{"id","layer","book","start","end","title",
                "parent","table","quote":{"work","table"},"steps":[...]}],
     "att_ref": {"本文 work": "注 work"},          # 本文 review/revise 的义注参考
     "harmonize_batches": [["A1","A2"], ["T"]]}    # 统稿分批，按子层 work 列

用法：
    python3 scripts/plan_align.py --config workspace/projects/abhisangaha/align/works.json \\
        --project abhisangaha --channel <uid> [--dry-run] [--csv 任务表.csv]
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import SENT_CSV, have_sent_counts, para_chars, para_sents  # noqa: E402
from plan_scan import (ALL_STEPS, CHUNK_STEPS, LAYER_CN, chunk_title,  # noqa: E402
                       layer_chunks, parse_steps, spans_of, write_csv)
import project as pj  # noqa: E402


# ══════════════════ 一、对照表 ══════════════════

def load_table(path, methods=None):
    """对照表 → {子段号: [父段号…]}。methods 给定时只收这些 method 的行。"""
    out = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if methods and r["method"] not in methods:
            continue
        ps = [int(x.split(":")[1]) for x in r["parent"]]
        if ps:
            out[int(r["child"].split(":")[1])] = ps
    return out


def mapped(table, paras_):
    """一串子段对应的父段（去重排序）。"""
    return sorted({p for c in paras_ for p in table.get(c, [])})


# ══════════════════ 二、统稿单元 ══════════════════

def harmonize_units(w, by_id, args):
    """一部子层作品的统稿单元：顺着子层累加到上限就切，read = 这些段在对照表里的父段。

    驳议块的引文对照（quote）也挂进 read：统稿时被引的 Vibhāvinī 原句要与它
    在 Vibhāvinī 里的译法一致，否则读者对不上雷迪驳的是哪句。
    """
    chars, sents = para_chars(w["book"]), para_sents(w["book"])
    par = by_id[w["parent"]]
    q = w.get("quote")
    qt = w.get("_qtable") or {}
    ps = [p for p in range(w["start"], w["end"] + 1) if chars.get(p, 0)]
    units, acc, ac, an = [], [], 0, 0

    def flush():
        nonlocal acc, ac, an
        if not acc:
            return
        read = [{"book": par["book"], "layer": par["layer"], "work": par["id"],
                 "start": lo, "end": hi}
                for lo, hi in spans_of([p for p in mapped(w["_table"], acc)
                                        if par["start"] <= p <= par["end"]])]
        if q:
            qw = by_id[q["work"]]
            read += [{"book": qw["book"], "layer": qw["layer"], "work": qw["id"],
                      "start": lo, "end": hi}
                     for lo, hi in spans_of([p for p in mapped(qt, acc)
                                             if qw["start"] <= p <= qw["end"]])]
        units.append({
            "pair": [par["id"], w["id"]] + ([q["work"]] if q and any(
                r["work"] == q["work"] for r in read) else []),
            "chars": ac, "sents": an,
            "ctx_chars": sum(para_chars(r["book"]).get(p, 0) for r in read
                             for p in range(r["start"], r["end"] + 1)),
            "write": [{"book": w["book"], "layer": w["layer"], "work": w["id"],
                       "start": lo, "end": hi} for lo, hi in spans_of(acc)],
            "read": read,
        })
        acc, ac, an = [], 0, 0

    for p in ps:
        pc, pn = chars.get(p, 0), sents.get(p, 0)
        if acc and (ac + pc > args.harm_chars
                    or (args.harm_sents > 0 and an + pn > args.harm_sents)):
            flush()
        acc.append(p)
        ac += pc
        an += pn
    flush()
    return units


# ══════════════════ 三、依赖与任务 ══════════════════

def hits(meta, lo, hi):
    return [ch for ch in meta["chunks"] if not (ch["end"] < lo or ch["start"] > hi)]


def wsteps(w, steps):
    """这部作品在块上要做的步骤（全局 steps 与作品自己的 steps 取交集）。"""
    own = w.get("steps") or CHUNK_STEPS
    return [s for s in CHUNK_STEPS if s in steps and s in own]


def build_needs(works, units, exports, steps):
    """每个 task 的前置，规划期算死。

      · 同块 translate → review → revise 串行；
      · 子层块 translate：父层对照范围里的父层块**定稿**，且若父层在某批统稿里
        被改写，覆盖到那些父段的统稿单元也要做完（Anudīpanī 等 Paramatthadīpanī
        第一批统稿之后的译文）；
      · 统稿单元：写的子层块定稿 + 读的各作品块定稿 + 读到的段若是别的单元写的，等那个单元；
      · evaluate：本块定稿 + 改写本块的统稿单元；export：本作品全部统稿单元 / 块定稿。
    """
    by_id = {w["id"]: w for w in works}
    fin = {w["id"]: (wsteps(w, steps) or [None])[-1] for w in works}
    needs = {}

    def chunk_fin(w, ch):
        return f'{ch["id"]}:{fin[w["id"]]}' if fin[w["id"]] else None

    def writers(work_id, lo, hi):
        return [u["id"] + ":harmonize" for u in units
                if any(s["work"] == work_id and not (s["end"] < lo or s["start"] > hi)
                       for s in u["write"])]

    for w in works:
        for ch in w["chunks"]:
            prev = None
            for st in wsteps(w, steps):
                tid = f'{ch["id"]}:{st}'
                needs[tid] = [prev] if prev else []
                prev = tid
            par = ch.get("parent")
            if par and "translate" in steps:
                pm = by_id[par["work"]]
                dep = []
                for sp in par["spans"]:
                    dep += [chunk_fin(pm, x) for x in hits(pm, sp["start"], sp["end"])]
                    if "harmonize" in steps:
                        dep += writers(pm["id"], sp["start"], sp["end"])
                needs[f'{ch["id"]}:translate'] += sorted({d for d in dep if d})

    for u in units:
        dep = []
        for sp in u["write"] + u["read"]:
            m = by_id[sp["work"]]
            dep += [chunk_fin(m, x) for x in hits(m, sp["start"], sp["end"])]
        for sp in u["read"]:
            dep += writers(sp["work"], sp["start"], sp["end"])
        needs[f'{u["id"]}:harmonize'] = sorted({d for d in dep if d} - {u["id"] + ":harmonize"})

    if "evaluate" in steps:
        for w in works:
            for ch in w["chunks"]:
                dep = [chunk_fin(w, ch)] + writers(w["id"], ch["start"], ch["end"])
                needs[f'{ch["id"]}:evaluate'] = sorted({d for d in dep if d})

    for e in exports:
        w = by_id[e["work"]]
        dep = writers(w["id"], w["start"], w["end"]) or [chunk_fin(w, ch) for ch in w["chunks"]]
        needs[f'{e["id"]}:export'] = sorted({d for d in dep if d})
    return needs


def task(tid, stage, step, **kw):
    t = {"id": tid, "stage": stage, "step": step, "layer": "", "book": None,
         "start": None, "end": None, "chars": 0, "sents": 0, "title": "", "needs": [],
         "status": pj.PENDING, "tries": 0, "began": "", "ended": "", "note": "", "detail": ""}
    t.update(kw)
    return t


def build_stages_tasks(works, units, exports, steps, batches):
    """阶段 = 推进顺序，也是队列顺序（同类连着跑吃 prompt 缓存）：

        根层 t/r/r → 第一批子层 t/r/r → 统稿第一批 → 第二批子层 t/r/r → 统稿第二批 …
        → evaluate → export

    子层归哪一批看它在 harmonize_batches 的位置；派发仍按 needs，阶段只定顺序与显示。
    """
    needs = build_needs(works, units, exports, steps)
    by_id = {w["id"]: w for w in works}
    batch_of = {wid: i for i, b in enumerate(batches) for wid in b}
    roots = [w for w in works if not w.get("parent")]
    stages, tasks = [], []

    def chunk_stage(ws, tag):
        for st in CHUNK_STEPS:
            if st not in steps:
                continue
            sid = f"{tag}:{st}"
            rows = []
            for w in ws:
                if st not in wsteps(w, steps):
                    continue
                for ch in w["chunks"]:
                    rows.append(task(f'{ch["id"]}:{st}', sid, st, layer=w["layer"],
                                     book=w["book"], start=ch["start"], end=ch["end"],
                                     chars=ch["chars"] if st == "translate" else 0,
                                     sents=ch["sents"], title=ch["title"],
                                     needs=needs.get(f'{ch["id"]}:{st}', [])))
            if rows:
                stages.append({"id": sid, "step": st,
                               "layer": "+".join(w["id"] for w in ws)})
                tasks.extend(rows)

    chunk_stage(roots, "+".join(w["id"] for w in roots))
    for i, b in enumerate(batches, 1):
        chunk_stage([by_id[x] for x in b], "+".join(b))
        if "harmonize" in steps:
            sid = f"harmonize-{i}"
            rows = [task(f'{u["id"]}:harmonize', sid, "harmonize", sents=u["sents"],
                         write=u["write"], read=u["read"], pair=u["pair"],
                         title=u["title"], needs=needs.get(f'{u["id"]}:harmonize', []))
                    for u in units if batch_of.get(u["write"][0]["work"]) == i - 1]
            if rows:
                stages.append({"id": sid, "step": "harmonize", "layer": "+".join(b)})
                tasks.extend(rows)
    if "evaluate" in steps:
        stages.append({"id": "evaluate", "step": "evaluate", "layer": ""})
        for w in works:
            for ch in w["chunks"]:
                tasks.append(task(f'{ch["id"]}:evaluate', "evaluate", "evaluate",
                                  layer=w["layer"], book=w["book"], start=ch["start"],
                                  end=ch["end"], sents=ch["sents"], title=ch["title"],
                                  needs=needs.get(f'{ch["id"]}:evaluate', [])))
    if "export" in steps:
        stages.append({"id": "export", "step": "export", "layer": ""})
        for e in exports:
            tasks.append(task(f'{e["id"]}:export', "export", "export", layer=e["layer"],
                              book=e["book"], start=e["start"], end=e["end"],
                              title=e["title"], needs=needs.get(f'{e["id"]}:export', [])))
    return stages, tasks


# ══════════════════ 四、自检 ══════════════════

def check(proj, steps, batches):
    bad, warn = [], []
    by_id = {w["id"]: w for w in proj["layers"]}
    for w in proj["layers"]:
        chars = para_chars(w["book"])
        cov, overlap = set(), 0
        for ch in w["chunks"]:
            rng = set(range(ch["start"], ch["end"] + 1))
            overlap += len(cov & rng)
            cov |= rng
        want = {p for p in range(w["start"], w["end"] + 1) if chars.get(p, 0)}
        if want - cov:
            bad.append(f'{w["id"]} 有 {len(want - cov)} 段没被块覆盖：{sorted(want - cov)[:10]}')
        if overlap:
            bad.append(f'{w["id"]} 的块之间重叠 {overlap} 段')
        if w.get("parent"):
            nop = [ch["id"] for ch in w["chunks"] if not ch.get("parent")]
            if nop:
                warn.append(f'{w["id"]} 有 {len(nop)}/{len(w["chunks"])} 块没有父层对照'
                            f'（序、跋等独立段）：{nop[:6]}')
            if "harmonize" in steps:
                hc = {p for u in proj["harmonize"] for s in u["write"] if s["work"] == w["id"]
                      for p in range(s["start"], s["end"] + 1)}
                if want - hc:
                    bad.append(f'统稿漏了 {w["id"]} 的 {len(want - hc)} 段：{sorted(want - hc)[:10]}')
    for wid in {x for b in batches for x in b}:
        if wid not in by_id or not by_id[wid].get("parent"):
            bad.append(f"harmonize_batches 里的 {wid} 不是有父层的作品")
    for w in proj["layers"]:
        if w.get("parent") and not any(w["id"] in b for b in batches) and "harmonize" in steps:
            bad.append(f'{w["id"]} 有父层但不在任何统稿批次里')

    # 统稿批次与父子顺序一致：子层的批次不能早于它父层被改写的批次
    bidx = {x: i for i, b in enumerate(batches) for x in b}
    for w in proj["layers"]:
        p = w.get("parent")
        if p in bidx and w["id"] in bidx and bidx[w["id"]] <= bidx[p]:
            bad.append(f'{w["id"]} 的统稿批次不晚于父层 {p}，父层定稿前就会对齐')

    ids = [t["id"] for t in proj["tasks"]]
    if len(set(ids)) != len(ids):
        bad.append("task id 有重复")
    ids = set(ids)
    dangling = sorted({d for t in proj["tasks"] for d in t["needs"]} - ids)
    if dangling:
        bad.append(f"这些前置 task 不存在：{dangling[:6]}")
    indeg = {t["id"]: len(t["needs"]) for t in proj["tasks"]}
    rev = collections.defaultdict(list)
    for t in proj["tasks"]:
        for d in t["needs"]:
            rev[d].append(t["id"])
    q = [i for i, n in indeg.items() if n == 0]
    seen = 0
    while q:
        cur = q.pop()
        seen += 1
        for nx in rev[cur]:
            indeg[nx] -= 1
            if indeg[nx] == 0:
                q.append(nx)
    if seen != len(ids):
        bad.append(f"依赖图有环：{len(ids) - seen} 个 task 永远等不到前置")
    # 队列顺序 = 拓扑序：前置一定排在前面，否则派发会在队首空转
    pos = {t["id"]: i for i, t in enumerate(proj["tasks"])}
    late = [t["id"] for t in proj["tasks"] if any(pos[d] > pos[t["id"]] for d in t["needs"] if d in pos)]
    if late:
        bad.append(f"有 {len(late)} 个 task 的前置排在它后面：{late[:5]}")
    sid = {s["id"] for s in proj["stages"]}
    if {t["stage"] for t in proj["tasks"]} - sid:
        bad.append("有 task 的 stage 不在阶段表里")

    for x in warn:
        print(f"  ⚠ {x}", file=sys.stderr)
    if bad:
        print("  ✗ 自检不过：", file=sys.stderr)
        for x in bad:
            print(f"     · {x}", file=sys.stderr)
    else:
        print("  ✓ 自检通过：各作品无缝覆盖不重叠、统稿覆盖子层每一段、批次顺序合父子关系、"
              "依赖图无环无悬空、队列顺序即拓扑序", file=sys.stderr)
    return bad


# ══════════════════ 五、组装 ══════════════════

def build(args):
    cfg = json.load(open(args.config, encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(args.config))
    steps = parse_steps(args.steps)
    works = [dict(w) for w in cfg["works"]]
    by_id = {w["id"]: w for w in works}
    batches = cfg.get("harmonize_batches") or [[w["id"] for w in works if w.get("parent")]]

    for w in works:
        if w.get("table"):
            w["_table"] = load_table(os.path.join(base, w["table"]))
        if w.get("quote"):
            # 引文对照只收有证据的行：逐字（lemma）、块内继承、经祖层中转（via）
            w["_qtable"] = load_table(os.path.join(base, w["quote"]["table"]),
                                      {"lemma", "inherit", "via"})
        w["pfx"] = w["id"] if len(w["id"]) == 1 else w["id"] + "-"
        w["parent_id"] = w.get("parent")
        w["layer_cn"] = LAYER_CN.get(w["layer"], w["layer"])

    print("作品：", file=sys.stderr)
    for w in works:
        chs = layer_chunks(w["book"], w["start"], w["end"], w["layer"], args)
        for i, ch in enumerate(chs, 1):
            ch["id"] = f'{w["pfx"]}{i}'
            ch["book"], ch["layer"] = w["book"], w["layer"]
            ch["title"] = chunk_title(ch)
        w["chunks"] = chs
        w["paras"] = sum(c["paras"] for c in chs)
        w["chars"] = sum(c["chars"] for c in chs)
        w["sents"] = sum(c["sents"] for c in chs)
        print(f'  {w["id"]:<3} {w["layer_cn"]:<14} {w["book"]}:{w["start"]}-{w["end"]} '
              f'{w["title"]}｜{len(chs)} 块｜{w["chars"]:,} 字符 / {w["sents"]:,} 句'
              f'｜父层 {w.get("parent") or "—"}｜步骤 {",".join(wsteps(w, steps))}',
              file=sys.stderr)

    # 父层对照：块内各段在对照表里的父段
    for w in works:
        if not w.get("parent"):
            continue
        pm = by_id[w["parent"]]
        for ch in w["chunks"]:
            ps = [p for p in mapped(w["_table"], range(ch["start"], ch["end"] + 1))
                  if pm["start"] <= p <= pm["end"]]
            ch["parent"] = ({"book": pm["book"], "layer": pm["layer"], "work": pm["id"],
                             "spans": [{"start": a, "end": b} for a, b in spans_of(ps)]}
                            if ps else None)

    # 本文复核的义注参考：反查注本的对照表，取注了本块各段的那些注释段
    for mid, aid in (cfg.get("att_ref") or {}).items():
        mw, aw = by_id[mid], by_id[aid]
        inv = collections.defaultdict(set)
        for c, ps in aw["_table"].items():
            for p in ps:
                inv[p].add(c)
        for ch in mw["chunks"]:
            cs = sorted({c for p in range(ch["start"], ch["end"] + 1) for c in inv.get(p, ())})
            ch["att_ref"] = ({"book": aw["book"], "layer": aw["layer"], "work": aw["id"],
                              "spans": [{"start": a, "end": b} for a, b in spans_of(cs)]}
                             if cs else None)

    units = []
    if "harmonize" in steps:
        for b in batches:
            for wid in b:
                units += harmonize_units(by_id[wid], by_id, args)
        for i, u in enumerate(units, 1):
            u["id"] = f"H{i}"
            u["kind"] = "pair"
            s = u["write"]
            u["title"] = f'{"+".join(u["pair"])} {s[0]["book"]}:{s[0]["start"]}-{s[-1]["end"]}'
        big = max(units, key=lambda u: u["ctx_chars"]) if units else None
        print(f'  统稿单元 {len(units)} 个（子层 ≤{args.harm_chars:,} 字符 / ≤{args.harm_sents} 句；'
              f'只读对照最大 {big["ctx_chars"]:,} 字符 @ {big["id"]}）', file=sys.stderr)
        for i, b in enumerate(batches, 1):
            n = sum(1 for u in units if u["write"][0]["work"] in b)
            print(f'    第 {i} 批 {"+".join(b)}：{n} 个', file=sys.stderr)

    exports = [{"id": f'E{w["id"]}', "work": w["id"], "book": w["book"], "layer": w["layer"],
                "start": w["start"], "end": w["end"], "title": w["title"]} for w in works]
    stages, tasks = build_stages_tasks(works, units, exports, steps, batches)

    for w in works:                      # 内部字段不落盘
        w.pop("_table", None)
        w.pop("_qtable", None)
    proj = {
        "schema": 3, "name": args.project,
        "title": args.title or cfg.get("title") or args.project,
        "created": pj.now(), "updated": pj.now(),
        "book": works[0]["book"], "channel": args.channel, "method": args.method,
        "state": "idle", "command": None, "steps": list(steps),
        "chunking": {"chunk_chars": args.chunk_chars, "max_sents": args.max_sents,
                     "max_paras": args.max_paras, "sent_counts": have_sent_counts(),
                     "harm_chars": args.harm_chars, "harm_sents": args.harm_sents,
                     "scan": True, "align": os.path.relpath(args.config)},
        "books": {str(w["book"]): {"layer": w["layer"], "title": w["title"]} for w in works},
        "layers": works, "harmonize": units, "exports": exports,
        "stages": stages, "tasks": tasks,
    }
    print(f'  阶段 {len(stages)} 个：' + " → ".join(s["id"] for s in stages), file=sys.stderr)
    print(f'  task {len(tasks)} 个', file=sys.stderr)
    return proj, steps, batches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="works.json（作品、父子、对照表、统稿批次）")
    ap.add_argument("--project", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--channel", default="")
    ap.add_argument("--method", default="default")
    ap.add_argument("--steps", default=",".join(ALL_STEPS))
    ap.add_argument("--chunk-chars", type=int, default=5000, dest="chunk_chars")
    ap.add_argument("--max-sents", type=int, default=80, dest="max_sents")
    ap.add_argument("--max-paras", type=int, default=0, dest="max_paras")
    ap.add_argument("--harm-chars", type=int, default=30000, dest="harm_chars")
    ap.add_argument("--harm-sents", type=int, default=200, dest="harm_sents")
    ap.add_argument("--csv", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not have_sent_counts():
        if args.max_paras <= 0:
            args.max_paras = 12
        print(f"  ⚠ 没有 {SENT_CSV}，句数上限不生效，改用 ≤{args.max_paras} 段兜底",
              file=sys.stderr)
    proj, steps, batches = build(args)
    if check(proj, steps, batches):
        sys.exit("计划不完整，没有落盘")
    if args.dry_run:
        print("  （--dry-run：没有落盘）", file=sys.stderr)
        return
    pj.save(proj)
    print(f"→ {pj.path_of(args.project)}", file=sys.stderr)
    if args.csv:
        write_csv(proj, args.csv)


if __name__ == "__main__":
    main()
