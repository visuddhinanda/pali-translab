# -*- coding: utf-8 -*-
"""按编号标题的**跨层对齐表**：代替 cs_para，给 `plan_scan.py --align` 用。

适用：cs_para 当不了跨书坐标、但各层同一级标题编号一一对应的书。
kn1（小诵）就是这样（2026-11-12 实测）：
  · 本文 154 与义注 116 的 cs 都是**经内偈号**，每部经从 1 重数——按 cs 值配对，
    九部经的同号偈会并进同一个单元；
  · 义注前四部经（116:5-459）一个 cs 都没有；后五部的 cs 比本文错一位
    （本文 cs 1 是缘起段，义注 cs 1 已是第 1 偈）。
而两层的二级标题都是「N. …」九部经，编号对得上。

键 = 所属那个编号标题的号 N（`1. Saraṇattayaṃ` ↔ `1. Saraṇattayavaṇṇanā`）。
第一个编号标题之前的段（书名段、义注序论 Ganthārambhakathā 等）键为空——
plan_scan 把它们当「无锚点」处理：块无父层对照，统稿自成一个单元。

表里写 `hard_keys: true`：块与统稿单元**不跨键**（一经一界），只在经内合并/切分。

`--backfill-level N`（配合 `--key cs`）：第 N 级标题（法句经义注的因缘故事 vatthu）
到它下面第一个编号小标题（偈号「21.」）之间的段，键改取那个偈号的 cs。法句经义注是
**先讲故事、后出偈**，原始数据里故事正文标的是**上一偈**的 cs（122:565-676 Sāmāvatī
故事标 cs 20，到 677 才出「21.」），不改的话几乎每个故事都挂到前一偈上。

`--key cs`：对齐键改用 cs_para（`cs_filled`），编号标题只当**切块边界**（写进 `bounds`）。
适用于 cs 本身干净、只想再加「不跨品」约束的书。kn2（法句经）就是这样：两层 cs
都是全书连续偈号 1-423，按偈对齐比按品精确；但义注序论（122:5-36）的颂带着
cs 1-10，与本文第 1-10 偈撞号——第一个编号标题之前的段一律不给键，序论自成一块。

用法：
    python3 scripts/align_heading.py --family kn1 --level 2 \\
        --work mula:154:3:276 --work atthakatha:116:3:1235 \\
        --out workspace/projects/kn1/align.json
    python3 scripts/align_heading.py --family kn17 --key name \\
        --work mula:151:3:2044 --work atthakatha:120:3:2526 \\
        --out workspace/projects/kn17/align.json
    python3 scripts/align_heading.py --family kn2 --level 2 --key cs \\
        --work mula:156:3:1392 --work atthakatha:122:3:5229 \\
        --out workspace/projects/kn2/align.json
"""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import cs_filled, paras  # noqa: E402

NUM = re.compile(r"^\s*(\d+)\s*\.")


def parse_work(spec):
    layer, book, lo, hi = spec.split(":")
    return {"layer": layer, "book": int(book), "start": int(lo), "end": int(hi)}


def backfill(rows, level, csf, d):
    """{段: cs}——第 level 级标题起、到其下第一个编号小标题止的段，改取该小标题的 cs。

    只改本来就有键的段（序论等无键段不碰）；遇到同级或更高级标题而没等到编号，放弃这一段。
    """
    out, pending, heads_only = {}, None, False
    for x in rows:
        p, lv = x["paragraph"], x.get("level", 100)
        if lv < level:
            pending, heads_only = [p], True       # 品标题：跟着它下面第一个故事走
            continue
        if lv == level:
            pending = pending if (pending and heads_only) else []
            heads_only = False
        elif pending is not None and lv < 100 and NUM.match(x.get("toc") or ""):
            cs = csf.get(p)
            if cs is not None:
                for q in pending:
                    if str(q) in d:
                        out[str(q)] = cs
            pending = None
            continue
        if pending is not None:
            pending.append(p)
            heads_only = False
    return out


JOINT = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*\.")


def joint(rows, level, d, book):
    """合注：第 level 级标题写作「N-M.」的，一段义注解释了相邻 M-N+1 部经。

    kn4 如是语义注 124:267「9-10.」、124:272「1-3.」（本文第 11-13 经）、
    124:953「7-8.」。前两处原始 cs 是乱码（44084、44148），第三处是 56。
    一律改为：合注下的段（连同紧挨在它前面、cs 与它相同的段，如品标题 124:271）
    键取「上一经的 cs + 1」= k；返回 {被并掉的经号: k}，交给其他层把对应的经并进同一组。
    """
    out, remap, last, i = dict(d), {}, None, 0
    seq = [x for x in rows if str(x["paragraph"]) in d]
    while i < len(seq):
        x = seq[i]
        p, toc = x["paragraph"], x.get("toc") or ""
        if x.get("level") == level:
            m = JOINT.match(toc)
            if m and last is not None:
                span, k, raw = int(m.group(2)) - int(m.group(1)) + 1, last + 1, d[str(p)]
                j = i - 1
                while j >= 0 and d[str(seq[j]["paragraph"])] == raw and str(seq[j]["paragraph"]) != "":
                    out[str(seq[j]["paragraph"])] = k
                    j -= 1
                j = i
                while j < len(seq) and (j == i or seq[j].get("level") != level):
                    out[str(seq[j]["paragraph"])] = k
                    j += 1
                for c in range(k + 1, k + span):
                    remap[c] = k
                print(f"  book {book}：合注 {p}「{toc[:30]}」→ 经号 {k}"
                      + (f"（并入 {k + 1}-{k + span - 1}）" if span > 1 else "")
                      + (f"，原始 cs {raw}" if raw != k else ""), file=sys.stderr)
                last, i = k + span - 1, j
                continue
            last = d[str(p)]
        i += 1
    return out, remap


def monotonic(d, book):
    """cs 倒退的段归回所在经：键取到此为止的最大 cs。

    kn3 自说义注 123:990-1062 是第 38 经义注里引的 12 首宿业偈（Pubbakammapiloti），
    原始数据给它另编了 cs 1-12，跟本文第 1-12 经撞号，第 1 经的义注参考里会混进这段。
    """
    out, top, moved = {}, None, []
    for p in sorted(d, key=int):
        k = d[p]
        if top is not None and k < top:
            moved.append(int(p))
            k = top
        top = k if top is None else max(top, k)
        out[p] = k
    if moved:
        print(f"  book {book}：cs 倒退 {len(moved)} 段（{moved[0]}-{moved[-1]}）归回所在经",
              file=sys.stderr)
    return out


LEAD_NUM = re.compile(r"^\s*[\(\[]?\s*\d+(?:\s*-\s*\d+)?\s*[\)\]\.]?\s*")
VANNANA = re.compile(r"vaṇṇanā\s*$")


def stem(toc):
    """标题 → 比对用的词干：去编号（1. / (1) / 2-4.）、去 vaṇṇanā、只留字母、去词尾格变化。

    `1. Sutamayañāṇaniddeso` 与 `1. Sutamayañāṇaniddesavaṇṇanā` 都成 sutamayañāṇaniddes；
    纯编号标题（偈号「62.」）成空串，不参与比对。
    """
    s = unicodedata.normalize("NFC", LEAD_NUM.sub("", toc or "").lower())
    s = "".join(ch for ch in s if ch.isalpha())
    s = VANNANA.sub("", s)
    return re.sub(r"[aāoeiīuūṃ]+$", "", s)


def lcs_pairs(a, b):
    """两串词干的最长公共子序列 → [(i, j)]（a 的下标, b 的下标），顺序单调。"""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    out, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] == b[j]:
            out.append((i, j)); i += 1; j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def name_align(works, rows_of, args):
    """`--key name`：按标题名对齐，不看层级与编号。

    适用：各层标题名一一对应，但编号每品重数、层级各层不同、写法不一的书。
    kn17（无碍解道）就是这样（2026-11-23 实测）：两层都是 3 品 × 10 论，论号每品从 1
    重数；义注品标题写作「(1) Mahāvaggo」；义注第二品的论标题在 level 4，其余在 level 3。
    做法：每层全部标题（level < 100）取词干，**以第一层为基准**与其余各层求最长公共
    子序列；配上的基准标题各开一组，组号 = 它在基准层的序号（顺序即经文顺序）。
    某层的段归它前面最近一个配上的标题；第一个配上的标题之前的段无键（序论）。
    """
    heads = {}
    for w in works:
        heads[w["book"]] = [(x["paragraph"], x.get("toc") or "", stem(x.get("toc")))
                            for x in rows_of[w["book"]] if x.get("level", 100) < 100]
    base = works[0]["book"]
    bstems = [s for _p, _t, s in heads[base]]
    starts = {w["book"]: {} for w in works}      # 段 → 组号（该段是配上的标题）
    matched_base = set()
    for w in works[1:]:
        cs = [s for _p, _t, s in heads[w["book"]]]
        bi = [i for i, s in enumerate(bstems) if s]
        ci = [j for j, s in enumerate(cs) if s]
        for i, j in lcs_pairs([bstems[k] for k in bi], [cs[k] for k in ci]):
            gi = bi[i]
            matched_base.add(gi)
            starts[w["book"]][heads[w["book"]][ci[j]][0]] = gi
    for gi in matched_base:
        starts[base][heads[base][gi][0]] = gi
    # 交叉：同名标题在两层的先后不同（kn17 本文 Mātikā 在 Ñāṇakathā 标题之前，义注
    # Mātikāvaṇṇanā 在其之后），单调的 LCS 只能配上一个。两个没配上的同名标题落在
    # 不同组 → 把这两组之间的组并成一组（取小号），否则一方的内容挂到对方的标题段上。
    def group_at(book, p):
        g = None
        for q, k in sorted(starts[book].items()):
            if q > p:
                break
            g = k
        return g
    merge = {}
    for w in works[1:]:
        cb = w["book"]
        bmiss = [(p, s) for p, _t, s in heads[base] if s and p not in starts[base]]
        cmiss = [(p, s) for p, _t, s in heads[cb] if s and p not in starts[cb]]
        for bp, bs in bmiss:
            for cp, cs_ in cmiss:
                if bs != cs_:
                    continue
                g1, g2 = group_at(base, bp), group_at(cb, cp)
                if g1 is None or g2 is None or g1 == g2:
                    continue
                lo, hi = min(g1, g2), max(g1, g2)
                if sum(1 for g in matched_base if lo < g <= hi) > 2:
                    continue                      # 隔得远的同名标题（常见小标题）不算交叉
                for g in matched_base:
                    if lo < g <= hi:
                        merge[g] = lo
                print(f"  交叉：book {base}:{bp} ↔ book {cb}:{cp}「{bs}」→ 组 {lo}-{hi} 并成 {lo}",
                      file=sys.stderr)
    if merge:
        for b in starts:
            starts[b] = {p: merge.get(g, g) for p, g in starts[b].items()}
        matched_base = {merge.get(g, g) for g in matched_base}
    para_key, groups = {}, {}
    for w in works:
        d, cur = {}, None
        for x in rows_of[w["book"]]:
            p = x["paragraph"]
            if p in starts[w["book"]]:
                cur = starts[w["book"]][p]
            if cur is not None:
                d[str(p)] = cur
        para_key[str(w["book"])] = d
        hs = heads[w["book"]]
        miss = [t for p, t, s in hs if s and p not in starts[w["book"]]]
        free = [p for p in range(w["start"], w["end"] + 1) if str(p) not in d]
        print(f'  {w["layer"]:<11} book {w["book"]} {w["start"]}-{w["end"]}：'
              f'标题 {len(hs)}，配上 {len(starts[w["book"]])}，没配上 {len(miss)}'
              f'｜无键段 {len(free)}' + (f'（{free[0]}-{free[-1]}）' if free else ""),
              file=sys.stderr)
        if miss:
            print("    没配上：" + " / ".join(m[:30] for m in miss[:12])
                  + (" …" if len(miss) > 12 else ""), file=sys.stderr)
    for gi in sorted(matched_base):
        groups[gi] = heads[base][gi][1]
    # 自检：各层键随段号单调不减
    ok = True
    for b, d in para_key.items():
        ks = [d[p] for p in sorted(d, key=int)]
        if any(x > y for x, y in zip(ks, ks[1:])):
            print(f"  ✗ book {b} 组号不单调", file=sys.stderr)
            ok = False
    print(f"  共 {len(groups)} 组", file=sys.stderr)
    return para_key, [{"id": g, "label": t} for g, t in sorted(groups.items())], ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--level", type=int, default=2, help="按哪一级标题对齐")
    ap.add_argument("--work", action="append", required=True,
                    help="layer:book:start:end，可重复；层序按给出的顺序")
    ap.add_argument("--key", choices=("heading", "cs", "name"), default="heading",
                    help="对齐键：heading = 标题号（默认）；cs = cs_para，标题号只作切块边界；"
                         "name = 按标题名对齐（不看层级与编号，见 name_align）")
    ap.add_argument("--backfill-level", type=int, default=0, dest="backfill",
                    help="--key cs 时：该级标题到其下第一个编号小标题之间的段，取那个编号段的 cs")
    ap.add_argument("--monotonic", action="store_true",
                    help="--key cs 时：cs 比前面小的段（书内另起编号的引偈等）键取前面的最大 cs")
    ap.add_argument("--joint", type=int, default=0,
                    help="--key cs 时：该级标题写作「N-M.」的是合注，键取上一经 cs+1，别层对应各经并组")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    works, para_key, heads, bounds, remap = [], {}, {}, {}, {}
    if args.key == "name":
        rows_of = {}
        for spec in args.work:
            w = parse_work(spec)
            rows = sorted((x for x in paras(w["book"]) if w["start"] <= x["paragraph"] <= w["end"]),
                          key=lambda x: x["paragraph"])
            w["title"] = rows[0].get("toc") or f'book {w["book"]}'
            works.append(w)
            rows_of[w["book"]] = rows
        para_key, groups, ok = name_align(works, rows_of, args)
        if not ok:
            sys.exit("对齐表自检失败，没有落盘")
        table = {"family": args.family, "by": "heading name (LCS)", "hard_keys": True,
                 "works": works, "para_key": para_key, "groups": groups, "copy": []}
        if args.dry_run:
            print("  （--dry-run：没有落盘）", file=sys.stderr)
            return
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        json.dump(table, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"→ {args.out}", file=sys.stderr)
        return
    for spec in args.work:
        w = parse_work(spec)
        rows = sorted((x for x in paras(w["book"]) if w["start"] <= x["paragraph"] <= w["end"]),
                      key=lambda x: x["paragraph"])
        w["title"] = rows[0].get("toc") or f'book {w["book"]}'
        works.append(w)
        d, cur, hs = {}, None, []
        for x in rows:
            if x.get("level", 100) <= args.level:
                m = NUM.match(x.get("toc") or "")
                # 同级及更高级的无号标题（书名、序论）打断归属：后面的段不再属于上一经
                cur = int(m.group(1)) if m else None
                if m:
                    hs.append((cur, x["paragraph"], x["toc"]))
            if cur is not None:
                d[str(x["paragraph"])] = cur
        heads[w["book"]] = hs
        if args.key == "cs":
            # 标题号退为边界；键取 cs，但第一个编号标题之前（序论、书名）不给键
            bounds[str(w["book"])] = d
            csf = cs_filled(w["book"])
            d = {p: csf[int(p)] for p in d if csf.get(int(p)) is not None}
            if args.backfill:
                d.update(backfill(rows, args.backfill, csf, d))
            if args.joint:
                d, rm = joint(rows, args.joint, d, w["book"])
                remap.update(rm)
            if args.monotonic:
                d = monotonic(d, w["book"])
        para_key[str(w["book"])] = d

    # 合注：别的层里被并掉的经号改成合注的键，两边同组
    if remap:
        for b, d in para_key.items():
            n = sum(1 for p in d if d[p] in remap)
            for p in d:
                d[p] = remap.get(d[p], d[p])
            if n:
                print(f"  book {b}：{n} 段按合注并组", file=sys.stderr)

    # 自检：各层编号集合一致、单调不重复
    sets = {b: [n for n, _p, _t in hs] for b, hs in heads.items()}
    ok = True
    for b, ns in sets.items():
        if ns != sorted(set(ns)):
            print(f"  ✗ book {b} 标题编号不单调或重复：{ns}", file=sys.stderr)
            ok = False
    base = next(iter(sets.values()))
    for b, ns in sets.items():
        if ns != base:
            print(f"  ✗ book {b} 编号 {ns} ≠ {base}", file=sys.stderr)
            ok = False

    for w in works:
        d = para_key[str(w["book"])]
        free = [p for p in range(w["start"], w["end"] + 1) if str(p) not in d]
        print(f'  {w["layer"]:<11} book {w["book"]} {w["start"]}-{w["end"]}：'
              f'{len(heads[w["book"]])} 组｜无键段 {len(free)}'
              + (f'（{free[0]}-{free[-1]}）' if free else ""), file=sys.stderr)
    by = list(zip(*[heads[w["book"]] for w in works]))
    for row in by:
        print("    " + " ↔ ".join(f"{p}:{t}" for _n, p, t in row), file=sys.stderr)
    if not ok:
        sys.exit("对齐表自检失败，没有落盘")

    table = {"family": args.family, "by": f"{args.key} / heading level {args.level}",
             "hard_keys": True, "works": works, "para_key": para_key,
             "groups": [{"id": n, "label": t} for n, _p, t in heads[works[0]["book"]]],
             "copy": []}
    if bounds:
        table["bounds"] = bounds
    if args.dry_run:
        print("  （--dry-run：没有落盘）", file=sys.stderr)
        return
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(table, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
