# -*- coding: utf-8 -*-
"""把一本书切成互不重叠的作业计划：一个作业 = 本文的一章 + 归它翻译的注释章。

**翻译归属与参考范围是两回事**，这是整个计划的核心：

  · 归属（own）——每个注释章只归**一个**作业翻译。本文多章对一章义注是常见现象，
    这时义注归**最早**提到它的那个本文章；后面的本文章不再翻译它。
  · 参考（ref）——后面的本文章在 review 与跨层统稿时**仍要读**那个义注，
    否则被解释词无从对齐、用词也统一不起来。ref 只读不写，可以重叠。

层次由 `wikipali books` 的 tag 一次问出，章节对应按 **cs_para**（跨书通用的典藏段号）
判定；章名匹配（本文 `Cūḷasīlaṃ` ↔ 义注 `Cūḷasīlavaṇṇanā`）用来在多个认领者之间定归属，
章名对不上再按 cs_para 取最早的认领者。
某个本文章没有义注是可能的，这时它的 own/ref 里就没有那一层。

用法：
    python3 scripts/plan_jobs.py --book 93                      # 整本
    python3 scripts/plan_jobs.py --book 93 --start 5 --end 52    # 只算这一段（试跑用）
"""
import argparse
import csv
import json
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import (LAYER_ORDER, SENT_CSV, book_chapters, chunk_paras,  # noqa: E402
                 cs_filled, cs_own, cs_set, have_sent_counts, layer_segments,
                 para_chars, para_sents, paras, plen)


def wp_sent_csv():
    return SENT_CSV
import project as pj  # noqa: E402

# 层序与层名统一由 _wp.LAYER_CHAIN 定；论藏是四层，见那里的说明
LAYER_CN = {"mula": "本文 mūla", "atthakatha": "义注 aṭṭhakathā", "tika": "复注 ṭīkā",
            "mulatika": "根本复注 mūlaṭīkā", "anutika": "随复注 anuṭīkā"}


def toc_chapters(book):
    """[(start, end, title)]——一次 `wikipali paras` 拿到，末段已确定，无需再探。

    锚点由 `_wp.book_roots` 从书目表取，这里不再有 anchor 参数（写死 3 是错的）。
    """
    return [(lo, hi, ti) for lo, hi, ti, _c, _n in book_chapters(book)]


def norm(title):
    """章名归一：去序号、只留巴利字母、削掉 vaṇṇanā 后缀、长短音与词尾归一。"""
    s = re.sub(r"^\s*\d+[.\s]*", "", title.lower())
    s = re.sub(r"[^a-zāīūṅñṭḍṇḷṃ]", "", s)
    for suf in ("vaṇṇanāya", "vaṇṇanā", "vaṇṇana"):
        if s.endswith(suf):
            s = s[:-len(suf)]
            break
    s = s.rstrip("ṃ").translate(str.maketrans("āīū", "aiu"))
    return s.rstrip("a")


# ══════════ project 文件：结构 + harmonize 规模分级 ══════════
# 一个作业的三层合计巴利字符决定 harmonize 怎么走（见 WORKFLOW.md「harmonize 的规模分级」）：
#   ≤ direct_max        → 整章三层一次做完
#   >  direct_max       → 先按 cs_para 切横向 chunk（保父子对齐），再按层做纵向（保同层一致）

def entries_of(job):
    """作业负责翻译的全部层次片段：本文 + own。"""
    out = []
    if job.get("mula"):
        m = dict(job["mula"]); m.setdefault("layer", "mula")
        out.append(m)
    return out + list(job["own"])


def cs_chars(entries, csm, chm):
    """{cs 值: 该作业内这个 cs 的三层合计字符}。

    没有 cs 的段跟着**前一个 cs 锚点**走——注释层独有的序论、结语夹在锚点之间，
    不能丢，也不该自成一块。开头就没有锚点的（如义注 103:3–201）落在 None 上。
    """
    acc, order = {}, []
    for e in entries:
        last = None
        for p in range(e["start"], e["end"] + 1):
            cs = csm[e["book"]].get(p) or last
            last = cs if cs is not None else last
            if cs not in acc:
                acc[cs] = 0
                order.append(cs)
            acc[cs] += chm[e["book"]].get(p, 0)
    return acc, [c for c in sorted(x for x in order if x is not None)], acc.get(None, 0)


def slice_by_cs(entry, csm, lo, hi):
    """某一层在 cs 区间 [lo, hi] 内的连续段号范围。cs 随段号单调不减，所以必是连续的。"""
    ps, last = [], None
    for p in range(entry["start"], entry["end"] + 1):
        cs = csm[entry["book"]].get(p)
        cs = cs if cs is not None else last
        if cs is not None:
            last = cs
        if cs is not None and lo <= cs <= hi:
            ps.append(p)
    return (ps[0], ps[-1]) if ps else None


def layers_in(entries, csm, lo, hi):
    """{book: [起, 止]}——**同一本书可能有好几个片段**（一个作业认领了该层的多章），
    键相同会互相覆盖，所以按 book 取并集的首尾，不能直接赋值。"""
    out = {}
    for e in entries:
        sl = slice_by_cs(e, csm, lo, hi)
        if not sl:
            continue
        k = str(e["book"])
        if k in out:
            out[k] = [min(out[k][0], sl[0]), max(out[k][1], sl[1])]
        else:
            out[k] = list(sl)
    return out


def split_range(book, lo_p, hi_p, chm, parts):
    """把一段段落按字符权重切成 parts 份，返回 [[起, 止], …]。"""
    if parts <= 1:
        return [[lo_p, hi_p]]
    total = sum(chm[book].get(p, 0) for p in range(lo_p, hi_p + 1)) or 1
    step, out, got, start = total / parts, [], 0, lo_p
    for p in range(lo_p, hi_p + 1):
        got += chm[book].get(p, 0)
        if (got >= step * (len(out) + 1) and len(out) < parts - 1) or p == hi_p:
            out.append([start, p])
            start = p + 1
    return out


def harmonize_plan(job, entries, csm, chm, th):
    """按体量给这个作业排 harmonize：direct 一次，或 横向 + 纵向 两步。"""
    total = sum(chm[e["book"]].get(p, 0)
                for e in entries for p in range(e["start"], e["end"] + 1))
    jid = job["id"]
    if total <= th["harmonize_direct_max"]:
        return total, {"mode": "direct", "cross": [
            {"id": f"{jid}.H", "kind": "direct", "chars": total,
             "layers": {str(e["book"]): [e["start"], e["end"]] for e in entries}}],
                "layer": []}

    acc, cs_list, headless = cs_chars(entries, csm, chm)
    budget = th["harmonize_cross_chars"]
    cross, i, n = [], 0, 0
    while i < len(cs_list):                       # 贪心攒 cs，直到超过横向上限
        lo = cs_list[i]
        if acc[lo] > budget:
            # 单个 cs 就超限：注释层在这一个典藏段上写了成百段（序论、长篇释义）。
            # cs 内部没有更细的公共坐标，但**各层可以按字符权重同步切成 K 份**——
            # 每一份仍然三层俱全，位置大致对应；本文片段短，整份带进每一子块当锚点。
            # 千万不能每层各切各的：那就退化成纵向，跨层对齐这一步等于没做。
            mula_e = [e for e in entries if e["layer"] == "mula"]
            anchors = layers_in(mula_e, csm, lo, lo)
            anchor_chars = sum(chm[int(b)].get(p, 0)
                               for b, r in anchors.items() for p in range(r[0], r[1] + 1))
            heavy = layers_in([e for e in entries if e["layer"] != "mula"], csm, lo, lo)
            # 本文片段通常只有几段，整份带进每一子块当锚点最省事。但整章同属一个 cs 时
            # （如波梨品的 Tikaṃ，本文 63 段 6.3k 字符、注释 10 万字符），锚点会被重复
            # 十几遍，占掉每块一半的额度——这时把本文也按同样的权重切开。
            if anchor_chars > budget // 3:
                heavy = {**heavy, **anchors}
                anchors, anchor_chars = {}, 0
            body = acc[lo] - anchor_chars
            k = max(1, -(-body // max(1, budget - anchor_chars)))
            cut = {b: split_range(int(b), r[0], r[1], chm, k) for b, r in heavy.items()}
            for t in range(k):
                part = {b: v[t] for b, v in cut.items() if t < len(v)}
                if not part:
                    continue
                n += 1
                cross.append({
                    "id": f"{jid}.H{n}", "kind": "cross", "cs": [lo, lo],
                    "part": [t + 1, k], "split_within_cs": True,
                    "chars": anchor_chars + sum(chm[int(b)].get(p, 0)
                                                for b, r in part.items()
                                                for p in range(r[0], r[1] + 1)),
                    "layers": {**anchors, **part},
                    "note": "" if anchors else "本文层在这个 cs 上没有段落，父层对照取义注",
                    "status": pj.PENDING})
            i += 1
            continue

        got, j = 0, i
        while j < len(cs_list) and (got == 0 or got + acc[cs_list[j]] <= budget):
            got += acc[cs_list[j]]
            j += 1
        hi = cs_list[j - 1]
        layers = layers_in(entries, csm, lo, hi)
        if len(layers) >= 2:          # 只剩一层就没有"跨层"可言，交给纵向那一步即可
            n += 1
            cross.append({"id": f"{jid}.H{n}", "kind": "cross", "cs": [lo, hi],
                          "chars": got, "layers": layers})
        i = j

    layer_chunks = []
    seq = {}                                       # 编号按 book 连续，不能按 entry 重置——
    for e in entries:                              # 一个作业可能认领同一层的好几段，会撞 id
        got, start = 0, e["start"]
        for p in range(e["start"], e["end"] + 1):
            got += chm[e["book"]].get(p, 0)
            last = p == e["end"]
            if got >= th["harmonize_layer_chars"] or last:
                k = seq[e["book"]] = seq.get(e["book"], 0) + 1
                layer_chunks.append({
                    "id": f'{jid}.HL{e["book"]}.{k}', "kind": "layer",
                    "layer": e["layer"], "layer_cn": LAYER_CN.get(e["layer"], e["layer"]),
                    "book": e["book"], "start": start, "end": p, "chars": got})
                got, start = 0, p + 1
    # 一个 cs 锚点都没有（注释书开头的序论、结集史）——那些段在父层里没有对应，
    # 横向对齐本来就无从做起，只做纵向，并把原因写进文件。
    mode = "cross+layer" if cross else "layer-only"
    return total, {"mode": mode, "cross": cross, "layer": layer_chunks,
                   "headless_chars": headless,
                   "note": "" if cross else "本作业全部段落没有 cs_para 对应，只做纵向统稿"}


# 一个 chunk 上按顺序要做的步骤。evaluate 排在 harmonize 之后（评的必须是定稿），
# 所以它不与 translate/review/revise 同批，见 tasks_of_pipeline。
CHUNK_STEPS = ("translate", "review", "revise")
# 流水线的全部步骤，按执行顺序。--steps 只能从这里挑子集：**计划里没有的步骤
# 执行器也不会跑**（steps 写进 project 文件，守护进程派发时透传给 pipeline_batch），
# 否则跑了却没有对应 task，白花一次模型调用，rollup 也等不到它。
ALL_STEPS = ("translate", "review", "revise", "harmonize", "evaluate", "export")


def layer_node(jid, k, e, chm, args):
    """一层的计划：段范围 + 体量 + **权威切好的分块**。

    边界在这里定死，执行期照单执行、不再重切——重切一遍就会与计划错位一两段，
    task 编号也就对不上了。**切分只用本地数据**（字符数来自整本 paras 缓存），
    规划期不调任何逐段接口。句数上限归执行期：执行器取回原文后本地数，
    一个 chunk 太长就分几次调用，仍算同一个 task。
    """
    plist = list(range(e["start"], e["end"] + 1))
    chunks = []
    for n, ps in enumerate(chunk_paras(e["book"], plist, args.chunk_chars,
                                       args.max_paras, args.max_sents), 1):
        snm = para_sents(e["book"])
        chunks.append({"id": f'{jid}.{k}.{n}', "kind": "chunk", "book": e["book"],
                       "layer": e["layer"],
                       "start": ps[0], "end": ps[-1], "paras": len(ps),
                       "chars": sum(chm[e["book"]].get(p, 0) for p in ps),
                       "sents": sum(snm.get(p, 0) for p in ps)})
    return {"layer": e["layer"], "layer_cn": LAYER_CN.get(e["layer"], e["layer"]),
            "book": e["book"], "start": e["start"], "end": e["end"],
            "title": e.get("title", ""), "paras": len(plist),
            "chars": sum(chm[e["book"]].get(p, 0) for p in plist),
            "chunks": chunks}


def tasks_of_pipeline(jid, layers, harm, steps=ALL_STEPS):
    """一条流水线的 task 列表，**按执行顺序**排好。

    顺序即依赖：前一个了结（done 或 skipped）才轮到下一个。分四段——
    逐层逐 chunk 的 translate→review→revise、跨层统稿、逐 chunk 评估、逐层导出。
    evaluate 必须在 harmonize 之后：评的得是定稿。
    """
    out = []
    for lay in layers:
        for ch in lay["chunks"]:
            for step in CHUNK_STEPS:
                if step not in steps:
                    continue
                out.append({"id": f'{ch["id"]}:{step}', "step": step,
                            "layer": lay["layer"], "book": ch["book"],
                            "start": ch["start"], "end": ch["end"],
                            "chars": ch["chars"] if step == "translate" else 0,
                            "status": pj.PENDING, "detail": ""})
    for c in (harm["cross"] + harm["layer"] if "harmonize" in steps else []):
        out.append({"id": c["id"], "step": "harmonize", "kind": c["kind"],
                    "layer": c.get("layer", ""), "book": c.get("book"),
                    "start": c.get("start"), "end": c.get("end"),
                    "layers": c.get("layers"), "chars": 0,
                    "status": pj.PENDING, "detail": ""})
    for lay in (layers if "evaluate" in steps else []):
        for ch in lay["chunks"]:
            out.append({"id": f'{ch["id"]}:evaluate', "step": "evaluate",
                        "layer": lay["layer"], "book": ch["book"],
                        "start": ch["start"], "end": ch["end"], "chars": 0,
                        "status": pj.PENDING, "detail": ""})
    for lay in (layers if "export" in steps else []):
        out.append({"id": f'{jid}.{lay["book"]}:export', "step": "export",
                    "layer": lay["layer"], "book": lay["book"],
                    "start": lay["start"], "end": lay["end"], "chars": 0,
                    "status": pj.PENDING, "detail": ""})
    return out

def chapter_levels(book):
    """{章首段号: 目录层级}——与 book_chapters 同源（同一份 paras 缓存），不另调接口。"""
    return {x["paragraph"]: x["level"] for x in paras(book) if x["level"] < 100}


def span_title(titles):
    return titles[0] if len(titles) == 1 else f"{titles[0]} … {titles[-1]}"


def coalesce(entries):
    """同层同书、段号首尾相接的片段接成一段——接上了，chunk_paras 才能跨过小章边界凑块。
    接不上的（中间隔着归别的作业翻译的章）保持分开，照样各自切块，只是少凑一点。"""
    out = []
    for e in sorted(entries, key=lambda e: (LAYER_ORDER.get(e["layer"], 9), e["book"], e["start"])):
        last = out[-1] if out else None
        if last and last["book"] == e["book"] and last["end"] + 1 == e["start"]:
            last["end"] = e["end"]
            last["_titles"].append(e["title"])
        else:
            out.append({**e, "_titles": [e["title"]]})
    for e in out:
        e["title"] = span_title(e.pop("_titles"))
    return out


def merge_small(jobs, mula, levels, chm, budget, max_paras, max_sents=0):
    """同一父章节下相邻的小章节并成一个作业，省掉逐章逐 chunk 的固定开销。

    chunk 出不了作业（它在作业的层片段内部切），所以合并只能做在作业这一级。
    规则——宁可少并，不许并出界：
      · 只并「子章节全是叶子」的父章节范围内的章（含父章节自己的标题章），
        不跨父章节，品与品、相應与相應的边界原样保留；
      · 并进来之后，每本书的合计仍须守住分块的那几条上限（字符、句数、段数）——
        即合并后每层恰好还是一个 chunk，不会因合并而多切或超上限。
        **三条上限要与 chunk_paras 用的完全一致**，否则合出来的作业一跑就被重新切成
        两块，task 编号与计划错位；
      · 单章就超限的大章永远独来独往，所以长部这类大章节书的计划与合并前逐字相同。
    """
    n = len(mula)
    lv = [levels.get(lo, 99) for lo, _hi, _t in mula]
    parent, kids = [None] * n, [[] for _ in range(n)]
    stack = []
    for i in range(n):
        while stack and lv[stack[-1]] >= lv[i]:
            stack.pop()
        if stack:
            parent[i] = stack[-1]
            kids[stack[-1]].append(i)
        stack.append(i)
    leafy = [bool(kids[i]) and all(not kids[k] for k in kids[i]) for i in range(n)]

    def key(i):
        if leafy[i]:
            return i
        p = parent[i]
        return p if p is not None and leafy[p] else None

    def size(job):
        acc = {}
        for e in entries_of(job):
            got = acc.setdefault(e["book"], [0, 0, 0])
            snm = para_sents(e["book"])
            for p in range(e["start"], e["end"] + 1):
                c = chm[e["book"]].get(p, 0)
                if c:
                    got[0] += c
                    got[1] += 1
                    got[2] += snm.get(p, 0)
        return acc

    def fits(acc):
        return all(c <= budget
                   and (max_paras <= 0 or k <= max_paras)
                   and (max_sents <= 0 or not sn or sn <= max_sents)
                   for c, k, sn in acc.values())

    groups, cur, cur_key, cur_size = [], [], None, {}
    for i, job in enumerate(jobs):             # jobs 与 mula 一一对应、同序
        k, sz = key(i), size(job)
        if cur and k is not None and k == cur_key:
            merged = dict(cur_size)
            for b, (c, m, sn) in sz.items():
                c0, m0, s0 = merged.get(b, (0, 0, 0))
                merged[b] = (c0 + c, m0 + m, s0 + sn)
            if fits(merged):
                cur.append(job); cur_size = merged
                continue
        if cur:
            groups.append(cur)
        cur, cur_key, cur_size = [job], k, {b: tuple(v) for b, v in sz.items()}
        if not fits(cur_size):              # 自己就超限：不给后面的章并进来
            cur_key = None
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        if len(g) == 1:
            out.append(g[0])
            continue
        own = coalesce([e for j in g for e in j["own"]])
        mine = {(e["book"], e["start"], e["end"]) for j in g for e in j["own"]}
        seen, ref = set(), []
        for j in g:
            for e in j["ref"]:
                t = (e["book"], e["start"], e["end"])
                if t in mine or t in seen:
                    continue
                seen.add(t)
                ref.append(e)
        m0, m1 = g[0]["mula"], g[-1]["mula"]
        out.append({
            "id": g[0]["id"],
            "mula": {**m0, "end": m1["end"],
                     "title": span_title([j["mula"]["title"] for j in g])},
            "own": own,
            "ref": sorted(ref, key=lambda e: (LAYER_ORDER.get(e["layer"], 9), e["book"], e["start"])),
            "chapters": [{"start": j["mula"]["start"], "end": j["mula"]["end"],
                          "title": j["mula"]["title"]} for j in g],
            "note": f"合并 {len(g)} 个小章",
        })
    return out


def limits_text(args):
    """分块上限的人话版——规划日志与任务表都用它，免得说一套做一套。"""
    return (f"≤{args.chunk_chars:,} 字符"
            + (f" / ≤{args.max_sents} 句" if args.max_sents > 0 and have_sent_counts() else "")
            + (f" / ≤{args.max_paras} 段" if args.max_paras > 0 else ""))


def parse_steps(raw):
    """--steps 的值 → 按 ALL_STEPS 的执行顺序排好的子集。顺序由这里定，不由用户的书写顺序定。"""
    want = {x.strip() for x in raw.split(",") if x.strip()}
    bad = want - set(ALL_STEPS)
    if bad:
        sys.exit(f"--steps 里有认不出的步骤：{', '.join(sorted(bad))}"
                 f"（可选：{', '.join(ALL_STEPS)}）")
    if not want:
        sys.exit("--steps 不能为空")
    return tuple(s for s in ALL_STEPS if s in want)


def build_project(args, jobs, books_seen, channel):
    """把作业计划物化成 project 文件——结构、体量、harmonize 计划、状态全在里面。"""
    steps = parse_steps(args.steps)
    bl = {e["book"] for j in jobs for e in entries_of(j)}
    csm = {b: cs_filled(b) for b in bl}
    chm = {b: para_chars(b) for b in bl}
    th = dict(pj.THRESHOLDS)

    th_chunk = limits_text(args)
    out_jobs, modes = [], {"direct": 0, "cross+layer": 0, "layer-only": 0}
    for j in jobs:
        ents = entries_of(j)
        total, harm = harmonize_plan(j, ents, csm, chm, th)
        modes[harm["mode"]] += 1
        cs_all = sorted({c for e in ents for p in range(e["start"], e["end"] + 1)
                         if (c := csm[e["book"]].get(p)) is not None})
        layers = [layer_node(j["id"], k, e, chm, args) for k, e in enumerate(ents, 1)]
        out_jobs.append({
            "id": j["id"],
            "title": (j["mula"] or j["own"][0])["title"],
            "cs": [cs_all[0], cs_all[-1]] if cs_all else None,
            "chars": total,
            "status": pj.PENDING, "tries": 0, "began": "", "ended": "",
            "note": j.get("note", ""),
            "mula": j["mula"],
            "chapters": j.get("chapters", []),   # 合并作业的成员章；单章作业为空
            "ref": j.get("ref", []),
            "layers": layers,          # 结构（层 → 分块边界），执行器照它取原文
            "harmonize": harm,
            "tasks": tasks_of_pipeline(j["id"], layers, harm, steps),   # 状态只在这里
        })

    proj = {
        "schema": pj.SCHEMA, "name": args.project,
        "title": args.title or f"book {args.book} 三层翻译",
        "created": pj.now(), "updated": pj.now(),
        "book": args.book, "channel": channel, "method": "default",
        "state": "idle", "command": None,
        # 这条流水线做哪些步骤。守护进程派发时透传成 pipeline_batch 的 --steps，
        # 执行器与计划因此永远一致。
        "steps": list(steps),
        "thresholds": th,
        "chunking": {"chunk_chars": args.chunk_chars, "max_sents": args.max_sents,
                     "max_paras": args.max_paras, "merge_small": not args.no_merge,
                     "sent_counts": have_sent_counts()},
        "books": {str(b): {"layer": l, "title": t} for b, (l, t) in books_seen.items()},
        "pipelines": out_jobs,
    }
    nch = sum(len(l["chunks"]) for j in out_jobs for l in j["layers"])
    nt = sum(len(j["tasks"]) for j in out_jobs)
    print(f"  切分块 {nch} 个（{th_chunk}）→ 任务 {nt} 个", file=sys.stderr)
    print(f"  harmonize 分级：整章直做 {modes['direct']} 个，"
          f"横向+纵向 {modes['cross+layer']} 个，只纵向 {modes['layer-only']} 个"
          f"（阈值 {th['harmonize_direct_max']:,} / {th['harmonize_cross_chars']:,}"
          f" / {th['harmonize_layer_chars']:,}）", file=sys.stderr)
    return proj

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=10**9)
    ap.add_argument("--out", default="", help="计划 json 落盘路径（旧格式）")
    ap.add_argument("--project", default="",
                    help="项目名：产出 workspace/projects/<name>/project.json（含任务与 harmonize 计划）")
    ap.add_argument("--title", default="", help="项目标题，给人看的")
    ap.add_argument("--chunk-chars", type=int, default=5000, dest="chunk_chars",
                    help="分块的巴利字符上限")
    ap.add_argument("--max-sents", type=int, default=80, dest="max_sents",
                    help="分块的句数上限（真约束：模型一次约 100 行 JSONL 就被截断）。"
                         "要 workspace/cache_sent_counts.csv（句子表的离线导出）；"
                         "没有那份数据时这项不生效，改用段数兜底")
    ap.add_argument("--max-paras", type=int, default=0, dest="max_paras",
                    help="分块的段数上限，0 为不限。只在**没有句数数据**时需要它兜底"
                         "（缺数据且未显式给值时自动按 12）")
    ap.add_argument("--no-merge", action="store_true", dest="no_merge",
                    help="不合并小章节（一章一作业，旧行为；对照用）")
    ap.add_argument("--channel", default="", help="写进项目文件的目标 channel uid")
    ap.add_argument("--steps", default=",".join(ALL_STEPS),
                    help="这个项目做哪些步骤（逗号分隔，顺序不论）。"
                         "计划里没有的步骤执行器也不会跑，例如不要总评："
                         "--steps translate,review,revise,harmonize,export")
    ap.add_argument("--csv", default="",
                    help="任务表 csv 落盘路径；跑之前先出这张表，守护进程再逐条改状态")
    args = ap.parse_args()
    # 句数是分块的真约束；没有那份离线数据时，退回用段数兜底（旧行为），
    # 并说明清楚——不然会拿 5,000 字符不限段地切，块里句子可能上百、必被截断。
    if not have_sent_counts():
        if args.max_paras <= 0:
            args.max_paras = 12
        print(f"  ⚠ 没有 {wp_sent_csv()}（句子表的离线导出），"
              f"句数上限不生效，改用 ≤{args.max_paras} 段兜底", file=sys.stderr)

    mula = toc_chapters(args.book)
    mula = [(lo, hi, t) for lo, hi, t in mula
            if lo >= args.start and lo <= args.end]
    if not mula:
        sys.exit("该范围内没有本文章节")
    # paras 已经给出真实末段，这里只需按 --end 裁剪
    mula = [(lo, min(hi, args.end), t) for lo, hi, t in mula if lo <= min(hi, args.end)]

    # 1) 找同卷各层的书 —— 一次 `wikipali books`，不是每章一次 related
    #
    # related 是**段级**接口（一次约 1.5 秒），全书规划要每章问一次：一卷 150 多次、
    # 四分钟，而且它给的段级对应边界还会错位（实测约一成的章判到相邻章）。
    # 层次归属改由 books 的 tag 判定，章节对应改由 cs_para 判定，两者都是本地计算。
    # 注释书不一定整本只对一本本文：增支部一本义注含好几集（book 100 = an2+an3+an4），
    # 所以要连**本集在那本书里的段范围**一起拿，否则会把别集的注释也拉进本项目。
    segs = layer_segments(args.book)
    books_seen = {b: (l, t) for b, (l, t, _lo, _hi) in segs.items()}
    if not books_seen:
        print(f"  ⚠ 没找到与 book {args.book} 同卷的注释书——只排本文", file=sys.stderr)
    print(f"{len(mula)} 个本文章｜同卷注释书 "
          + "、".join(f"{b}({l})" for b, (l, _t) in sorted(books_seen.items())),
          file=sys.stderr)

    ctoc = {}
    for b, (_l, _t, lo, hi) in segs.items():        # 只留落在本集段范围内的注释章
        chs = [(max(clo, lo), min(chi, hi), ti) for clo, chi, ti in toc_chapters(b)
               if chi >= lo and clo <= hi]
        ctoc[b] = chs
        if lo > 0 or hi < 10 ** 9:
            print(f"  book {b} 限定在本集范围 {lo}-{min(hi, chs[-1][1]) if chs else hi}"
                  f"（{len(chs)} 章）", file=sys.stderr)
    csm = {b: cs_own(b) for b in [args.book] + list(books_seen)}   # 判归属只认正文段自己的 cs

    # 2) 每章的 cs 集合 → 注释章的认领者
    #
    # cs_para 是 Chaṭṭha Saṅgāyana 典藏段号，跨书通用，是三层唯一的公共坐标。
    # 注释章与本文章共享哪怕一个 cs，就说明它注的是这一章。
    # 判归属只看各章**自己**的 cs（carry=False）：章标题段往往没有 cs，
    # 一旦向前继承就会把上一章的 cs 带进来，整章被判给上一章。
    mula_cs = [cs_set(args.book, lo, hi, csm[args.book], carry=False) for lo, hi, _t in mula]
    # 章名在本文里**唯一**时才敢拿它认亲：Cūḷasīlaṃ、Dvepabbajitavatthu 这类
    # 小节名在好几部经里重复出现（本卷有 6 个），重名的只能靠 cs 判。
    name_count = {}
    for _lo, _hi, t in mula:
        name_count[norm(t)] = name_count.get(norm(t), 0) + 1
    by_name = {}
    for mi, (_lo, _hi, t) in enumerate(mula):
        if name_count[norm(t)] == 1:
            by_name.setdefault(norm(t), mi)

    claims = {}                       # (book, chapter_idx) -> set(本文章序号)
    for b, chs in ctoc.items():
        for ci, (clo, chi, ctitle) in enumerate(chs):
            S = cs_set(b, clo, chi, csm[b], carry=False)
            hit = {mi for mi, M in enumerate(mula_cs) if S & M}
            # 标题章自己没有 cs（如义注的「2. Sāmaññaphalasuttavaṇṇanā」只有一行标题），
            # 靠章名认亲：它显然属于同名的那一经，而不该自成一个前置作业。
            if not hit and norm(ctitle) in by_name:
                hit = {by_name[norm(ctitle)]}
            if hit:
                claims[(b, ci)] = hit

    # 3) 定归属：章名匹配优先，其次 cs 重叠最多的那一章，再平手取最早
    owner = {}
    for (b, ci), who in claims.items():
        clo, chi, ctitle = ctoc[b][ci]
        key = norm(ctitle)
        named = [mi for mi in who if norm(mula[mi][2]) == key]
        if named:
            owner[(b, ci)] = min(named)
            continue
        # 经题章（义注的「8. Mahāsīhanādasuttavaṇṇanā」只有一行标题）跟本文经题章
        # 未必共享 cs，所以认领者里找不到同名的；章名唯一时直接认，别退回 cs 重叠——
        # 退回去会把经题判给上一经的末章。
        if key in by_name:
            owner[(b, ci)] = by_name[key]
            claims[(b, ci)] = who | {by_name[key]}
            continue
        S = cs_set(b, clo, chi, csm[b], carry=False)
        owner[(b, ci)] = max(who, key=lambda mi: (len(S & mula_cs[mi]), -mi))

    # 4) 组装作业
    jobs = []
    for mi, (lo, hi, title) in enumerate(mula):
        own, ref = [], []
        for (b, ci), who in claims.items():
            if mi not in who:
                continue
            clo, chi, ctitle = ctoc[b][ci]
            layer, btitle = books_seen[b]
            entry = {"layer": layer, "book": b, "start": clo, "end": chi,
                     "title": ctitle, "book_title": btitle}
            (own if owner[(b, ci)] == mi else ref).append(entry)
        key = lambda e: (LAYER_ORDER.get(e["layer"], 9), e["book"], e["start"])
        jobs.append({
            "id": mi,
            "mula": {"layer": "mula", "book": args.book, "start": lo, "end": hi,
                     "title": title, "book_title": ""},
            "own": sorted(own, key=key),
            "ref": sorted(ref, key=key),
        })

    # 4b) 小章合并：同一父章节下相邻的小章并成一个作业（见 merge_small）
    if not args.no_merge:
        before = len(jobs)
        chm_all = {b: para_chars(b) for b in [args.book] + list(books_seen)}
        jobs = merge_small(jobs, mula, chapter_levels(args.book), chm_all,
                           args.chunk_chars, args.max_paras, args.max_sents)
        print(f"  小章合并：{before} 章 → {len(jobs)} 个作业"
              f"（每层合计 {limits_text(args)}，不跨父章节）", file=sys.stderr)

    # ── 5) 前置作业：注释书里与本文无对应的开头部分 ──────────────────────
    # 注释书从 level=1 起就是本书的一部分（序论 Ganthārambhakathā、Nidānakathā、
    # 结集史 Paṭhamamahāsaṅgītikathā 等），只是与本文对不上。整本翻译时必须覆盖，
    # 否则整本书是残的。这些章按**章名**跨层配对成作业（复注开头正是注释义注开头的，
    # 章名就是义注章名加 vaṇṇanā），作业内部做义注↔复注统稿，不牵扯本文。
    claimed = {(b, ci) for (b, ci) in claims}
    orphan = {}                      # norm(章名) -> [(book, ci)]
    for b, chs in ctoc.items():
        last_key = None
        for ci, (clo, chi, ctitle) in enumerate(chs):
            if (b, ci) in claimed:
                last_key = None
                continue
            key = norm(ctitle)
            if not key or key == "empty":        # 无题小节挂到本书上一节
                key = last_key or f"__{b}_{ci}"
            orphan.setdefault(key, []).append((b, ci))
            last_key = key

    nid = len(jobs)
    for key, items in sorted(orphan.items(), key=lambda kv: (kv[1][0][0], kv[1][0][1])):
        own = []
        for b, ci in sorted(items, key=lambda x: (LAYER_ORDER.get(books_seen[x[0]][0], 9), x[0], x[1])):
            clo, chi, ctitle = ctoc[b][ci]
            layer, btitle = books_seen[b]
            own.append({"layer": layer, "book": b, "start": clo, "end": chi,
                        "title": ctitle, "book_title": btitle})
        jobs.append({"id": nid, "mula": None, "own": own, "ref": [],
                     "note": "注释书开头，与本文无对应；本作业内部统稿"})
        nid += 1

    # 覆盖率自检：每本注释书从 level=1 到书末都必须被某个作业覆盖，一段都不能漏
    for b, chs in ctoc.items():
        want = set()
        for clo, chi, _t in chs:
            want |= set(range(clo, chi + 1))
        got = set()
        for j in jobs:
            for e in j["own"]:
                if e["book"] == b:
                    got |= set(range(e["start"], e["end"] + 1))
        miss = sorted(want - got)
        dup = len([1 for j in jobs for e in j["own"] if e["book"] == b])
        print(f"  book {b}: 覆盖 {len(got)}/{len(want)} 段"
              + (f"，**漏 {len(miss)} 段** 例 {miss[:5]}" if miss else "，无遗漏")
              + f"｜{dup} 个章归属", file=sys.stderr)

    # ── 6) 排序：前置作业排到最前面 ────────────────────────────────────
    # 注释书的开头（序论、结集史）就是这几本书的起点，先把它们译出来，
    # 后面各章的术语与语体才有统一的起点可依。
    pre = [j for j in jobs if j["mula"] is None]
    main = [j for j in jobs if j["mula"] is not None]
    pre.sort(key=lambda j: (j["own"][0]["book"], j["own"][0]["start"]))
    jobs = pre + main
    for i, j in enumerate(jobs):          # 重新编号，派发顺序即表里的顺序
        j["id"] = i

    out = {"book": args.book, "jobs": jobs,
           "books": {str(b): {"layer": l, "title": t} for b, (l, t) in books_seen.items()}}
    if args.csv:
        # 与 run_daemon.py 的任务表同格式：跑之前全部 ⬜ 未开始，跑起来由守护进程改
        cols = ["序号", "状态", "本文坐标", "章节名", "本作业翻译",
                "开始时间", "完成时间", "耗时", "尝试", "备注"]
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for j in jobs:
                m, segs = j["mula"], sum(e["end"] - e["start"] + 1 for e in j["own"])
                if m:
                    coord = f'{m["book"]}:{m["start"]}-{m["end"]}'
                    title = m["title"]
                    own = f'本文{m["end"] - m["start"] + 1}段'
                    if j["own"]:
                        own += f' + 注释{len(j["own"])}章/{segs}段'
                    note = j.get("note", "")
                else:                       # 前置作业：注释书开头，无本文
                    e0 = j["own"][0]
                    coord = f'{e0["book"]}:{e0["start"]}-{e0["end"]}'
                    title = e0["title"]
                    own = f'注释{len(j["own"])}章/{segs}段（无本文）'
                    note = j.get("note", "")
                w.writerow({"序号": j["id"], "状态": "⬜ 未开始", "本文坐标": coord,
                            "章节名": title, "本作业翻译": own,
                            "开始时间": "", "完成时间": "", "耗时": "", "尝试": 0,
                            "备注": note})
        print(f"→ {args.csv}（{len(jobs)} 条任务，全部 ⬜ 未开始）", file=sys.stderr)

    if args.project:
        proj = build_project(args, jobs, books_seen, args.channel)
        p = pj.save(proj)
        pj.build_index()
        print(f"→ {p}（{len(jobs)} 个作业）", file=sys.stderr)
        print(f"→ {pj.export_html(proj)}", file=sys.stderr)
        print(f"→ {pj.export_index(pj.build_index())}", file=sys.stderr)
        return

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text + "\n")
        print(f"→ {args.out}（{len(jobs)} 个作业）", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
