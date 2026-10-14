# -*- coding: utf-8 -*-
"""按层扫描的规划器（**schema 3**）：各层各自从上到下切块，统稿按 cs_para 跨层成组。

与 `plan_jobs.py`（schema 2，作业 = 一章 × 各层）的差别，也是重做它的理由：

  · **各层独立切块**。小经文多的书按章对齐就是一章一块：增支部六集 137 章里大半
    只有两三段，三层各切一块，每次调用要注入的 SKILL+method+knowledge（约 25KB）
    全摊在几百字符的正文上。各层自己扫下来、按真实体量合并，块数少一半以上。
  · **块以章为单位累加，不切断章**。单章自己超限才在章内按段切——**永远不拆段**，
    段是坐标的最小单位，拆了坐标就对不上。
  · **句数是真约束**。模型一次吐约 100 行 JSONL 就被输出上限截断，截断一次整块白跑。
    句数来自句子表的离线导出（`workspace/cache_sent_counts.csv`），字符数只是它的代理。
  · **统稿与块无关**：按 `cs_para` 把各层对应的段聚成单元（义注的黑体引自本文、
    复注的引自义注，对齐只能在 cs 这个跨书公共坐标上做）。相邻 cs 合并到上限为止。
  · **排班按阶段推进**：全部 `mula:translate` 跑完，再 `mula:review`，再 `mula:revise`，
    然后才是义注那三步。层间必须有屏障——注释层 translate 要注入父层**定稿**译文。
    阶段内的 task 同类、提示词前缀一样，连着跑吃得到 prompt 缓存。

规划期**只用本地数据**：段表与字符数来自 `wikipali paras` 的整本缓存，句数来自上面那份
CSV，层次与本集段范围来自 `wikipali books`。不调任何逐段接口。

用法：
    python3 scripts/plan_scan.py --book 89 --project an-chakkanipata \\
        --title "增支部 六集 三層翻譯" --channel <uid> \\
        --steps translate,review,revise,harmonize,export
"""
import argparse
import csv
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import (LAYER_CHAIN, LAYER_ORDER, SENT_CSV, book_chapters,  # noqa: E402
                 chunk_paras, cs_filled, have_sent_counts, layer_segments,
                 para_chars, para_sents, parent_layer)
import project as pj  # noqa: E402

LAYER_CN = {"mula": "本文 mūla", "atthakatha": "义注 aṭṭhakathā", "tika": "复注 ṭīkā",
            "mulatika": "根本复注 mūlaṭīkā", "anutika": "随复注 anuṭīkā"}
# 一个块上按顺序要做的步骤；harmonize / evaluate / export 不按块走，见 build_stages
CHUNK_STEPS = ("translate", "review", "revise")
ALL_STEPS = ("translate", "review", "revise", "harmonize", "evaluate", "export")


# ══════════════════ 一、各层切块 ══════════════════

def spans_of(paras_list):
    """段号列表 → 连续区间列表 [(lo, hi)]。统稿单元里某一层的段可能不连续。"""
    out = []
    for p in sorted(set(paras_list)):
        if out and out[-1][1] + 1 == p:
            out[-1][1] = p
        else:
            out.append([p, p])
    return [(lo, hi) for lo, hi in out]


def layer_chunks(book, lo, hi, layer, args):
    """一层的块序列：从上到下扫章，累加到上限就切。

    返回 [{start, end, paras, chars, sents, chapters:[{start,end,title}], split}]。
    `split=True` 表示这块是某个超限大章的一部分（章被切开了，不得已）。
    块的 start/end 取**章的边界**，不取非空段的边界——章标题段字符数为 0，
    按非空段取会把标题漏在两块之间，整本就不是无缝覆盖了。
    """
    chars, sents = para_chars(book), para_sents(book)
    chs = [(max(s, lo), min(e, hi), t)
           for s, e, t, _c, _n in book_chapters(book) if e >= lo and s <= hi]
    CH, SE, MP = args.chunk_chars, args.max_sents, args.max_paras

    def vol(s, e):
        ps = [p for p in range(s, e + 1) if chars.get(p, 0)]
        return (sum(chars.get(p, 0) for p in ps),
                sum(sents.get(p, 0) for p in ps), len(ps))

    out, cur = [], None

    def flush():
        nonlocal cur
        if cur:
            out.append(cur)
            cur = None

    for s, e, t in chs:
        c, sn, np = vol(s, e)
        over = c > CH or (SE > 0 and sn > SE) or (MP > 0 and np > MP)
        if over:                      # 单章就超限：独来独往，章内按段切
            flush()
            ps = [p for p in range(s, e + 1) if chars.get(p, 0)]
            parts = chunk_paras(book, ps, CH, MP, SE) or [ps]
            for i, part in enumerate(parts):
                a = s if i == 0 else part[0]              # 首块兜住章标题段
                b = e if i == len(parts) - 1 else part[-1]
                cc, cs_, _n = vol(a, b)
                out.append({"start": a, "end": b, "chars": cc, "sents": cs_,
                            "paras": len([p for p in range(a, b + 1) if chars.get(p, 0)]),
                            "chapters": [{"start": s, "end": e, "title": t}],
                            "split": True})
            continue
        if cur and (cur["chars"] + c > CH
                    or (SE > 0 and cur["sents"] + sn > SE)
                    or (MP > 0 and cur["paras"] + np > MP)):
            flush()
        if cur is None:
            cur = {"start": s, "end": e, "chars": 0, "sents": 0, "paras": 0,
                   "chapters": [], "split": False}
        cur["end"] = e
        cur["chars"] += c
        cur["sents"] += sn
        cur["paras"] += np
        cur["chapters"].append({"start": s, "end": e, "title": t})
    flush()
    return out


def chunk_title(ch):
    ts = [c["title"] for c in ch["chapters"]]
    if ch["split"]:
        return f'{ts[0]}（{ch["start"]}-{ch["end"]}）'
    return ts[0] if len(ts) == 1 else f"{ts[0]} … {ts[-1]}"


# ══════════════════ 二、父层对照范围 ══════════════════

def cs_index(book):
    """{cs: [段号…]}——cs_filled 的反向索引，用来由子层的 cs 找父层的段。"""
    idx = {}
    for p, cs in cs_filled(book).items():
        if cs is not None:
            idx.setdefault(cs, []).append(p)
    return idx


def parent_block(chunk, csf_child, pbook, pidx, plo, phi):
    """本块在父层里的对照段范围。

    translate 注释层时要把父层译文一起注进去（被解释词必须与父层逐字同译），
    范围就由 cs 决定：本块出现过的每个 cs，在父层对应哪些段。
    父层范围只在本集段界内取——注释书一本含好几集，越界就把别集拉进来了。
    """
    want = {csf_child.get(p) for p in range(chunk["start"], chunk["end"] + 1)}
    want.discard(None)
    ps = [p for cs in want for p in pidx.get(cs, []) if plo <= p <= phi]
    if not ps:
        return None
    return {"book": pbook, "spans": [{"start": lo, "end": hi} for lo, hi in spans_of(ps)]}


# ══════════════════ 三、统稿单元（按 cs_para 跨层成组）══════════════════

def harmonize_units(layers_meta, args):
    """按 cs_para 把各层对应的段聚成统稿单元，相邻 cs 合并到上限为止。

    单元是**跨层**的：一个 cs 在本文、义注、复注各自对应若干段，它们必须放在一起读，
    黑体被解释词才对得齐。与块的切分完全无关——块是为了翻译时的体量，
    单元是为了对齐时的对应关系。

    开头没有 cs 锚点的段（注释书的序论在本文里无对应）并进第一个单元，一段都不丢。
    """
    csf = {m["book"]: cs_filled(m["book"]) for m in layers_meta}
    chars = {m["book"]: para_chars(m["book"]) for m in layers_meta}
    sents = {m["book"]: para_sents(m["book"]) for m in layers_meta}

    # cs → {book: [段…]}；None 收在 head 里
    by_cs, head = {}, {}
    for m in layers_meta:
        b, lo, hi = m["book"], m["start"], m["end"]
        for p in range(lo, hi + 1):
            if not chars[b].get(p, 0):
                continue
            cs = csf[b].get(p)
            (head if cs is None else by_cs.setdefault(cs, {})).setdefault(b, []).append(p)

    def vol(group):
        c = sum(chars[b].get(p, 0) for b, ps in group.items() for p in ps)
        s = sum(sents[b].get(p, 0) for b, ps in group.items() for p in ps)
        return c, s

    def split_layerwise(g):
        """一个 cs 自己就超限（本集最大的那个有三百多句）：改**按层**拆。

        一个 cs 是跨层对应的最小单位，再往里切就没有公共锚点了，所以不能横向细分。
        退一步按层拆成纵向单元（层内还超就按段切），跨层对齐那部分交给 translate
        阶段的父层对照去保——那一步每块都注入了父层定稿译文。
        """
        parts = []
        for b in sorted(g, key=lambda x: LAYER_ORDER.get(
                next(m["layer"] for m in layers_meta if m["book"] == x), 9)):
            cur_ps, c, s2 = [], 0, 0
            for p in sorted(g[b]):
                pc, ps_ = chars[b].get(p, 0), sents[b].get(p, 0)
                if cur_ps and (c + pc > args.harm_chars
                               or (args.harm_sents > 0 and s2 + ps_ > args.harm_sents)):
                    parts.append({b: cur_ps}); cur_ps, c, s2 = [], 0, 0
                cur_ps.append(p); c += pc; s2 += ps_
            if cur_ps:
                parts.append({b: cur_ps})
        return parts

    units, cur, cur_cs = [], {}, []
    if head:
        cur, cur_cs = {b: list(ps) for b, ps in head.items()}, []

    def flush():
        nonlocal cur, cur_cs
        if not cur:
            return
        c, s = vol(cur)
        units.append({"cs": [cur_cs[0], cur_cs[-1]] if cur_cs else None,
                      "chars": c, "sents": s,
                      "spans": [{"book": b, "layer": next(m["layer"] for m in layers_meta
                                                          if m["book"] == b),
                                 "start": lo, "end": hi}
                                for b in sorted(cur, key=lambda x: LAYER_ORDER.get(
                                    next(m["layer"] for m in layers_meta if m["book"] == x), 9))
                                for lo, hi in spans_of(cur[b])]})
        cur, cur_cs = {}, []

    for cs in sorted(by_cs):
        g = by_cs[cs]
        c, s = vol(g)
        if cur:
            merged = {b: cur.get(b, []) + g.get(b, []) for b in set(cur) | set(g)}
            mc, ms = vol(merged)
            if mc <= args.harm_chars and (args.harm_sents <= 0 or ms <= args.harm_sents):
                cur, cur_cs = merged, cur_cs + [cs]
                continue
            flush()
        if c > args.harm_chars or (args.harm_sents > 0 and s > args.harm_sents):
            for part in split_layerwise(g):      # 这个 cs 自己就超限：按层拆
                cur, cur_cs = part, [cs]
                flush()
            continue
        cur, cur_cs = {b: list(ps) for b, ps in g.items()}, [cs]
    flush()
    return units


# ══════════════════ 四、阶段与任务 ══════════════════

def build_stages(layers_meta, steps):
    """阶段表，**即推进顺序**：各层的 translate→review→revise，然后统稿、评估、导出。

    层间是硬屏障：注释层 translate 要注入父层**定稿**译文，父层没走完 revise
    就开译子层，注进去的是半成品，被解释词白对一遍。
    """
    out = []
    for m in sorted(layers_meta, key=lambda m: LAYER_ORDER.get(m["layer"], 9)):
        for st in CHUNK_STEPS:
            if st in steps:
                out.append({"id": f'{m["layer"]}:{st}', "step": st, "layer": m["layer"]})
    for st in ("harmonize", "evaluate", "export"):
        if st in steps:
            out.append({"id": st, "step": st, "layer": ""})
    return out


def last_step(steps):
    """一个块上最后一个改译文的步骤——它了结了，这块才算定稿。"""
    for st in reversed(CHUNK_STEPS):
        if st in steps:
            return st
    return None


def hits(meta, book, lo, hi):
    """某层里与 [lo,hi] 相交的块。依赖是按**段区间相交**算的，不是按块号。"""
    return [ch for ch in meta["chunks"]
            if ch["book"] == book and not (ch["end"] < lo or ch["start"] > hi)]


def build_needs(layers, units, exports, steps):
    """每个 task 的前置 task（`needs`），**在规划期算死**。

    调度器因此不必靠「阶段屏障」那种粗办法等——队列里第一个前置都了结的 task
    随时可以派，三个 worker 不会因为最后几个 translate 没跑完就空等。
    屏障挡不住的事它也能挡住：某块 translate 失败后退回队列重跑时，
    它的 review 已经排在后面，只有依赖查表才知道「还不能做」。

    依赖只有四条：
      · 同一块里 translate → review → revise 顺序串起来；
      · 注释层某块的 translate，依赖**父层对照范围**覆盖到的那些父层块定稿；
      · 统稿单元依赖它 spans 覆盖的各层块定稿；
      · 导出依赖本层全部统稿单元（没有统稿就依赖本层全部块定稿）。
    """
    by_layer = {m["layer"]: m for m in layers}
    fin = last_step(steps)
    needs = {}

    def chunk_fin(ch):
        return f'{ch["id"]}:{fin}' if fin else None

    for m in layers:
        for ch in m["chunks"]:
            prev = None
            for st in CHUNK_STEPS:
                if st not in steps:
                    continue
                tid = f'{ch["id"]}:{st}'
                needs[tid] = [prev] if prev else []
                prev = tid
            # 注释层开译前，父层对照范围里的块必须已经定稿
            par = ch.get("parent")
            if par and "translate" in steps:
                pm = by_layer.get(par.get("layer"))
                if pm:
                    dep = [chunk_fin(x) for sp in par["spans"]
                           for x in hits(pm, par["book"], sp["start"], sp["end"])]
                    needs[f'{ch["id"]}:translate'] += [d for d in dep if d]

    for u in units:
        dep = []
        for sp in u["spans"]:
            m = by_layer.get(sp.get("layer"))
            if m:
                dep += [chunk_fin(x) for x in hits(m, sp["book"], sp["start"], sp["end"])]
        needs[f'{u["id"]}:harmonize'] = sorted({d for d in dep if d})

    # evaluate 评的必须是定稿：同块定稿 + 覆盖这块的统稿单元都做完
    if "evaluate" in steps:
        for m in layers:
            for ch in m["chunks"]:
                dep = [chunk_fin(ch)]
                dep += [f'{u["id"]}:harmonize' for u in units
                        if any(sp["book"] == ch["book"]
                               and not (sp["end"] < ch["start"] or sp["start"] > ch["end"])
                               for sp in u["spans"])]
                needs[f'{ch["id"]}:evaluate'] = sorted({d for d in dep if d})

    for e in exports:
        m = by_layer.get(e["layer"])
        dep = [f'{u["id"]}:harmonize' for u in units
               if any(sp["book"] == e["book"] for sp in u["spans"])]
        if not dep and m:
            dep = [chunk_fin(ch) for ch in m["chunks"]]
        needs[f'{e["id"]}:export'] = sorted({d for d in dep if d})
    return needs


def build_tasks(layers, units, exports, steps):
    """全部 task，**按阶段顺序排好**（队列顺序 = 派发顺序，同类连着跑才吃得到缓存）。"""
    needs = build_needs(layers, units, exports, steps)
    out = []
    for m in sorted(layers, key=lambda m: LAYER_ORDER.get(m["layer"], 9)):
        for st in CHUNK_STEPS:
            if st not in steps:
                continue
            for ch in m["chunks"]:
                out.append({"id": f'{ch["id"]}:{st}', "stage": f'{m["layer"]}:{st}',
                            "step": st, "layer": m["layer"], "book": m["book"],
                            "start": ch["start"], "end": ch["end"],
                            "chars": ch["chars"] if st == "translate" else 0,
                            "sents": ch["sents"], "title": ch["title"],
                            "needs": needs.get(f'{ch["id"]}:{st}', []),
                            "status": pj.PENDING, "tries": 0,
                            "began": "", "ended": "", "note": "", "detail": ""})
    if "harmonize" in steps:
        for u in units:
            out.append({"id": f'{u["id"]}:harmonize', "stage": "harmonize",
                        "step": "harmonize", "layer": "", "book": None,
                        "start": None, "end": None, "chars": 0, "sents": u["sents"],
                        "spans": u["spans"], "title": u["title"],
                        "needs": needs.get(f'{u["id"]}:harmonize', []),
                        "status": pj.PENDING, "tries": 0,
                        "began": "", "ended": "", "note": "", "detail": ""})
    if "evaluate" in steps:
        for m in sorted(layers, key=lambda m: LAYER_ORDER.get(m["layer"], 9)):
            for ch in m["chunks"]:
                out.append({"id": f'{ch["id"]}:evaluate', "stage": "evaluate",
                            "step": "evaluate", "layer": m["layer"], "book": m["book"],
                            "start": ch["start"], "end": ch["end"], "chars": 0,
                            "sents": ch["sents"], "title": ch["title"],
                            "needs": needs.get(f'{ch["id"]}:evaluate', []),
                            "status": pj.PENDING, "tries": 0,
                            "began": "", "ended": "", "note": "", "detail": ""})
    if "export" in steps:
        for e in exports:
            out.append({"id": f'{e["id"]}:export', "stage": "export", "step": "export",
                        "layer": e["layer"], "book": e["book"],
                        "start": e["start"], "end": e["end"], "chars": 0, "sents": 0,
                        "title": e["title"], "needs": needs.get(f'{e["id"]}:export', []),
                        "status": pj.PENDING, "tries": 0,
                        "began": "", "ended": "", "note": "", "detail": ""})
    return out


# ══════════════════ 五、自检 ══════════════════

def check(proj, verbose=True):
    """内容完整性自检。任何一条不过都是计划有洞，不该拿去跑。

    查六件事：每层无缝覆盖本集段界、块之间不重叠、统稿单元覆盖每层每一段、
    task 与块/单元一一对应、阶段表与 task 的 stage 对得上、注释层都有父层对照。
    """
    bad = []
    chars_of = {}
    for m in proj["layers"]:
        b = m["book"]
        chars_of[b] = para_chars(b)
        # 1) 无缝覆盖 + 2) 不重叠
        cov, overlap = set(), 0
        for ch in m["chunks"]:
            rng = set(range(ch["start"], ch["end"] + 1))
            overlap += len(cov & rng)
            cov |= rng
        want = set(range(m["start"], m["end"] + 1))
        miss = want - cov
        extra = cov - want
        if miss:
            bad.append(f'层 {m["layer"]}(book {b}) 有 {len(miss)} 段没被任何块覆盖'
                       f'：{sorted(miss)[:10]}')
        if extra:
            bad.append(f'层 {m["layer"]}(book {b}) 有 {len(extra)} 段超出本集段界'
                       f'：{sorted(extra)[:10]}')
        if overlap:
            bad.append(f'层 {m["layer"]}(book {b}) 的块之间重叠 {overlap} 段')
        # 6) 注释层要有父层对照
        if m["layer"] != "mula":
            noparent = [ch["id"] for ch in m["chunks"] if not ch.get("parent")]
            if noparent:
                bad.append(f'层 {m["layer"]} 有 {len(noparent)} 块没有父层对照'
                           f'：{noparent[:5]}')

    # 3) 统稿单元覆盖每层每一段（只要有正文的段）
    if proj.get("harmonize"):
        hcov = {}
        for u in proj["harmonize"]:
            for sp in u["spans"]:
                hcov.setdefault(sp["book"], set()).update(
                    range(sp["start"], sp["end"] + 1))
        for m in proj["layers"]:
            b = m["book"]
            want = {p for p in range(m["start"], m["end"] + 1) if chars_of[b].get(p, 0)}
            miss = want - hcov.get(b, set())
            if miss:
                bad.append(f'统稿漏了 book {b} 的 {len(miss)} 段：{sorted(miss)[:10]}')

    # 3b) 统稿单元不超限（单段自己就超限的除外——段不拆）
    th = proj["chunking"]
    for u in proj.get("harmonize", []):
        if u["chars"] > th["harm_chars"] or (th["harm_sents"] > 0
                                             and u["sents"] > th["harm_sents"]):
            if len(u["spans"]) == 1 and u["spans"][0]["start"] == u["spans"][0]["end"]:
                continue                 # 一个段自己就超限，拆不动
            bad.append(f'统稿单元 {u["id"]} 超限：{u["chars"]:,} 字符 / {u["sents"]} 句'
                       f'（上限 {th["harm_chars"]:,} / {th["harm_sents"]}）')

    # 4) task 与块/单元一一对应
    steps = set(proj["steps"])
    nchunk = sum(len(m["chunks"]) for m in proj["layers"])
    want_n = (nchunk * len([s for s in CHUNK_STEPS if s in steps])
              + (len(proj.get("harmonize", [])) if "harmonize" in steps else 0)
              + (nchunk if "evaluate" in steps else 0)
              + (len(proj.get("exports", [])) if "export" in steps else 0))
    if len(proj["tasks"]) != want_n:
        bad.append(f'task 数不对：有 {len(proj["tasks"])} 个，按块与单元应是 {want_n} 个')
    ids = [t["id"] for t in proj["tasks"]]
    if len(set(ids)) != len(ids):
        bad.append("task id 有重复")

    # 4b) needs 指向的 task 必须存在，且拓扑可排（有环就永远派不出去）
    ids = {t["id"] for t in proj["tasks"]}
    dangling = sorted({d for t in proj["tasks"] for d in t.get("needs") or []} - ids)
    if dangling:
        bad.append(f'这些前置 task 不存在：{dangling[:6]}')
    indeg = {t["id"]: len([d for d in t.get("needs") or [] if d in ids])
             for t in proj["tasks"]}
    rev = {}
    for t in proj["tasks"]:
        for d in t.get("needs") or []:
            rev.setdefault(d, []).append(t["id"])
    q = [i for i, n in indeg.items() if n == 0]
    seen = 0
    while q:
        cur = q.pop()
        seen += 1
        for nxt in rev.get(cur, []):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    if seen != len(ids):
        bad.append(f'依赖图有环：{len(ids) - seen} 个 task 永远等不到前置')

    # 5) 阶段表与 task 的 stage 对得上
    sid = {s["id"] for s in proj["stages"]}
    orphan = sorted({t["stage"] for t in proj["tasks"]} - sid)
    if orphan:
        bad.append(f"这些 stage 不在阶段表里：{orphan}")
    empty = sorted(sid - {t["stage"] for t in proj["tasks"]})
    if empty:
        bad.append(f"这些阶段一个 task 都没有：{empty}")

    if verbose:
        if bad:
            print("  ✗ 自检不过：", file=sys.stderr)
            for x in bad:
                print(f"     · {x}", file=sys.stderr)
        else:
            print("  ✓ 自检通过：各层无缝覆盖且不重叠、统稿覆盖每一段、"
                  "task 与块/单元一一对应、依赖图无环且无悬空、阶段表自洽",
                  file=sys.stderr)
    return bad


# ══════════════════ 六、组装 ══════════════════

def build(args):
    segs = layer_segments(args.book)
    chm = para_chars(args.book)
    mula_paras = sorted(p for p in chm)
    layers_meta = [{"layer": "mula", "book": args.book,
                    "start": min(mula_paras), "end": max(mula_paras), "title": ""}]
    for b, (lay, title, lo, hi) in sorted(segs.items(), key=lambda kv: LAYER_ORDER.get(kv[1][0], 9)):
        ps = sorted(para_chars(b))
        layers_meta.append({"layer": lay, "book": b, "title": title,
                            "start": max(lo, min(ps)), "end": min(hi, max(ps))})
    present = {m["layer"] for m in layers_meta}
    steps = parse_steps(args.steps)

    print(f'层次：' + "、".join(f'{m["layer"]}(book {m["book"]} {m["start"]}-{m["end"]})'
                               for m in layers_meta), file=sys.stderr)

    # 切块
    for m in layers_meta:
        chs = layer_chunks(m["book"], m["start"], m["end"], m["layer"], args)
        pfx = {"mula": "M", "atthakatha": "A", "tika": "T",
               "mulatika": "MT", "anutika": "AT"}.get(m["layer"], m["layer"][:2].upper())
        for i, ch in enumerate(chs, 1):
            ch["id"] = f"{pfx}{i}"
            ch["book"] = m["book"]
            ch["layer"] = m["layer"]
            ch["title"] = chunk_title(ch)
        m["chunks"] = chs
        m["paras"] = sum(c["paras"] for c in chs)
        m["chars"] = sum(c["chars"] for c in chs)
        m["sents"] = sum(c["sents"] for c in chs)
        m["layer_cn"] = LAYER_CN.get(m["layer"], m["layer"])
        nsplit = sum(1 for c in chs if c["split"])
        # 大章被切成几块时每块都挂一份章条目，按 (start,end) 去重才是真实章数
        nchap = len({(c["start"], c["end"]) for ch in chs for c in ch["chapters"]})
        print(f'  {m["layer_cn"]:<16} book {m["book"]:>3}｜本集 {nchap} 章 → {len(chs)} 块'
              f'（{nsplit} 块来自超限大章）｜'
              f'{m["chars"]:,} 字符 / {m["sents"]:,} 句', file=sys.stderr)

    # 父层对照
    by_layer = {m["layer"]: m for m in layers_meta}
    for m in layers_meta:
        pl = parent_layer(m["layer"], present)
        if not pl:
            continue
        pm = by_layer[pl]
        csf = cs_filled(m["book"])
        pidx = cs_index(pm["book"])
        for ch in m["chunks"]:
            ch["parent"] = parent_block(ch, csf, pm["book"], pidx, pm["start"], pm["end"])
            if ch["parent"]:
                ch["parent"]["layer"] = pl

    # 本文的复核要义注参考：**义注定释义**，译者与标准同源就查不出错。
    # translate 永远不给（那会让复核失去独立基准），所以只挂在块上供 review/revise 取。
    att = by_layer.get("atthakatha")
    mu = by_layer.get("mula")
    if att and mu:
        csf = cs_filled(mu["book"])
        aidx = cs_index(att["book"])
        for ch in mu["chunks"]:
            ch["att_ref"] = parent_block(ch, csf, att["book"], aidx,
                                         att["start"], att["end"])
            if ch["att_ref"]:
                ch["att_ref"]["layer"] = "atthakatha"

    # 统稿单元
    units = []
    if "harmonize" in steps:
        units = harmonize_units(layers_meta, args)
        for i, u in enumerate(units, 1):
            u["id"] = f"H{i}"
            u["kind"] = "cross" if len({sp["book"] for sp in u["spans"]}) > 1 else "layer"
            first = u["spans"][0]
            u["title"] = (f'cs {u["cs"][0]}-{u["cs"][1]}' if u["cs"]
                          else f'{first["book"]}:{first["start"]}（无 cs 锚点）')
        ncross = sum(1 for u in units if u["kind"] == "cross")
        print(f'  统稿单元 {len(units)} 个（跨层 {ncross}、单层 {len(units) - ncross}）'
              f'｜上限 ≤{args.harm_chars:,} 字符'
              + (f' / ≤{args.harm_sents} 句' if args.harm_sents > 0 else ""),
              file=sys.stderr)

    exports = [{"id": f'E{m["book"]}', "book": m["book"], "layer": m["layer"],
                "start": m["start"], "end": m["end"],
                "title": m["title"] or f'book {m["book"]}'} for m in layers_meta]

    stages = build_stages(layers_meta, steps)
    tasks = build_tasks(layers_meta, units, exports, steps)

    proj = {
        "schema": 3, "name": args.project,
        "title": args.title or f"book {args.book} 各层翻译",
        "created": pj.now(), "updated": pj.now(),
        "book": args.book, "channel": args.channel, "method": args.method,
        "state": "idle", "command": None,
        "steps": list(steps),
        "chunking": {"chunk_chars": args.chunk_chars, "max_sents": args.max_sents,
                     "max_paras": args.max_paras, "sent_counts": have_sent_counts(),
                     "harm_chars": args.harm_chars, "harm_sents": args.harm_sents,
                     "scan": True},
        "books": {str(m["book"]): {"layer": m["layer"], "title": m["title"]}
                  for m in layers_meta},
        "layers": layers_meta,
        "harmonize": units,
        "exports": exports,
        "stages": stages,
        "tasks": tasks,
    }
    print(f'  阶段 {len(stages)} 个：' + " → ".join(s["id"] for s in stages),
          file=sys.stderr)
    print(f'  task {len(tasks)} 个', file=sys.stderr)
    return proj


def parse_steps(raw):
    want = {x.strip() for x in raw.split(",") if x.strip()}
    bad = want - set(ALL_STEPS)
    if bad:
        sys.exit(f"--steps 里有认不出的步骤：{', '.join(sorted(bad))}"
                 f"（可选：{', '.join(ALL_STEPS)}）")
    if not want:
        sys.exit("--steps 不能为空")
    return tuple(s for s in ALL_STEPS if s in want)


def write_csv(proj, path):
    """任务表：一行一个 task，emoji 标状态，跑之前先出这张表。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["阶段", "task", "步骤", "层", "坐标", "标题",
                    "字符", "句", "状态", "开始时间", "完成时间", "尝试", "备注"])
        for t in proj["tasks"]:
            coord = (f'{t["book"]}:{t["start"]}-{t["end"]}' if t.get("book")
                     else "、".join(f'{sp["book"]}:{sp["start"]}-{sp["end"]}'
                                   for sp in t.get("spans", [])[:3]))
            w.writerow([t["stage"], t["id"], t["step"], t.get("layer", ""), coord,
                        t.get("title", ""), t.get("chars") or "", t.get("sents") or "",
                        "⬜ 未开始", "", "", 0, ""])
    print(f"→ {path}（{len(proj['tasks'])} 条 task，全部 ⬜ 未开始）", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True, help="本文的 book")
    ap.add_argument("--project", required=True, help="项目名 → workspace/projects/<name>/")
    ap.add_argument("--title", default="", help="项目标题，给人看的")
    ap.add_argument("--channel", default="", help="目标 channel uid")
    ap.add_argument("--method", default="default")
    ap.add_argument("--steps", default=",".join(ALL_STEPS),
                    help="做哪些步骤（逗号分隔）。计划里没有的步骤执行器也不会跑")
    ap.add_argument("--chunk-chars", type=int, default=5000, dest="chunk_chars",
                    help="一块的巴利字符上限")
    ap.add_argument("--max-sents", type=int, default=80, dest="max_sents",
                    help="一块的句数上限（真约束：模型一次约 100 行 JSONL 就被截断）")
    ap.add_argument("--max-paras", type=int, default=0, dest="max_paras",
                    help="一块的段数上限，0 为不限（只在没有句数数据时需要它兜底）")
    # 统稿的上限比翻译宽得多，因为它**只回传改动过的句子**（至多百来行），
    # 输入大小只受上下文限制。30,000 字符是 an2–an5 实跑验证过的值（全部成功）；
    # 卡到翻译那样的 80 句会把绝大多数 cs 判成超限、被迫按层拆成纵向，
    # 跨层对齐就做不成了——那才是统稿最要紧的事。
    ap.add_argument("--harm-chars", type=int, default=30000, dest="harm_chars",
                    help="一个统稿单元的各层合计字符上限")
    ap.add_argument("--harm-sents", type=int, default=200, dest="harm_sents",
                    help="一个统稿单元的各层合计句数上限（0 为不限）")
    ap.add_argument("--csv", default="", help="任务表 csv 落盘路径")
    ap.add_argument("--dry-run", action="store_true", help="只算不落盘")
    args = ap.parse_args()

    if not have_sent_counts():
        if args.max_paras <= 0:
            args.max_paras = 12
        print(f"  ⚠ 没有 {SENT_CSV}（句子表的离线导出），句数上限不生效，"
              f"改用 ≤{args.max_paras} 段兜底", file=sys.stderr)

    proj = build(args)
    bad = check(proj)
    if bad:
        sys.exit("计划不完整，没有落盘——先修上面这些问题")
    if args.dry_run:
        print("  （--dry-run：没有落盘）", file=sys.stderr)
        return
    pj.save(proj)
    print(f"→ {pj.path_of(args.project)}", file=sys.stderr)
    if args.csv:
        write_csv(proj, args.csv)


if __name__ == "__main__":
    main()
