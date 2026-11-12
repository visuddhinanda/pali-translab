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

用法：
    python3 scripts/align_heading.py --family kn1 --level 2 \\
        --work mula:154:3:276 --work atthakatha:116:3:1235 \\
        --out workspace/projects/kn1/align.json
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import paras  # noqa: E402

NUM = re.compile(r"^\s*(\d+)\s*\.")


def parse_work(spec):
    layer, book, lo, hi = spec.split(":")
    return {"layer": layer, "book": int(book), "start": int(lo), "end": int(hi)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--level", type=int, default=2, help="按哪一级标题对齐")
    ap.add_argument("--work", action="append", required=True,
                    help="layer:book:start:end，可重复；层序按给出的顺序")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    works, para_key, heads = [], {}, {}
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
        para_key[str(w["book"])] = d
        heads[w["book"]] = hs

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

    table = {"family": args.family, "by": f"heading level {args.level}", "hard_keys": True,
             "works": works, "para_key": para_key,
             "groups": [{"id": n, "label": t} for n, _p, t in heads[works[0]["book"]]],
             "copy": []}
    if args.dry_run:
        print("  （--dry-run：没有落盘）", file=sys.stderr)
        return
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(table, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"→ {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
