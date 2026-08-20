# -*- coding: utf-8 -*-
"""解析一段本文对应的三层文献坐标：mūla → aṭṭhakathā → ṭīkā。

三层在**不同的书**里，段号也不同（本文 93:984 的义注在 103:1470，复注在 185:1345 与 189:1263）。
本脚本用 `wikipali books` + `cs_para` 逐层向下算，产出坐标表与**父层映射**——
父层映射是「被解释词逐字同译」这条硬约束的执行依据：义注的父层是本文，复注的父层是义注。

`--chapter` 把每一层扩成**该层书自己目录里的完整一章**——这是处理整章时的正确做法。
cs_para 是跨书通用的典藏段号；旧做法用的 `related` 是段级对应、一次一段一秒半，
一段注释常跨注好几段父层，直接拿它的段号当章节范围必然错位：
注释章的首段往往注的是上一章的本文，其被解释词在本章里根本找不到。

输出 JSON：

    {"groups": [
      {"layer":"mula","book":93,"title":"dīghanikāyapāḷi","paras":[983,984,985,986],
       "parent_book":null,"map":{},"chapter":"Tayo codanārahā"},
      {"layer":"atthakatha","book":103,"title":"sumaṅgalavilāsinī","paras":[1468,…],
       "parent_book":93,"map":{"1468":[982,983],…}},
      {"layer":"tika","book":185,"title":"līnatthappakāsanā","paras":[1345,…],
       "parent_book":103,"map":{"1345":[1470],…}}
    ]}

用法：
    python3 scripts/layers.py --book 93 --para 983-986
    python3 scripts/layers.py --book 93 --para 983 --chapter    # 各层扩成完整章节
"""
import argparse
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import cs_filled, jget, layer_books, parse_paras  # noqa: E402

LAYER_TAGS = {"aṭṭhakathā": "atthakatha", "ṭīkā": "tika"}
PROBE = 500   # 末章没有下一条目录项时，向后按这个跨度收尾


def chapters(book, anchor):
    """该书的章节表：[(start, end, title)]，某条目录项到下一条之前即一章。"""
    toc = sorted((t for t in jget("toc", f"{book}:{anchor}", "--json", "--depth", "9")
                  if t.get("book") == book), key=lambda t: t["paragraph"])
    out = []
    for i, t in enumerate(toc):
        end = toc[i + 1]["paragraph"] - 1 if i + 1 < len(toc) else t["paragraph"] + PROBE
        out.append((t["paragraph"], end, t["toc"]))
    return out


def to_chapter(book, paras):
    """把一组段号扩成完整一章：取**包含该组段落最多**的那一章。

    一组段号常跨三章（上一章末段 + 本章 + 下一章首段），多数决能稳稳落在本章上。
    """
    chs = chapters(book, paras[0])
    if not chs:
        return paras, ""
    best = max(chs, key=lambda c: sum(1 for p in paras if c[0] <= p <= c[1]))
    if not any(best[0] <= p <= best[1] for p in paras):
        return paras, ""
    return list(range(best[0], best[1] + 1)), best[2]


def by_cs(parent_book, parent_paras, want, books):
    """父层这些段 → 下一层的对应段，全靠 cs_para，本地计算，**不调 related**。

    related 是段级接口（一次约 1.5 秒往返），整章解析要几十上百次；而它给的是段级
    对应，边界还会错位。cs_para 是跨书通用的典藏段号：父段与子段落在同一个 cs 上，
    就是对应关系。子层里没有 cs 的段（注释独有的插话）跟着前一个锚点走。

    返回 {(layer, book): {"title":…, "map": {子段: [父段…]}}}
    """
    pcs = cs_filled(parent_book)
    want_cs = {}
    for pp in parent_paras:
        c = pcs.get(pp)
        if c is not None:
            want_cs.setdefault(c, []).append(pp)
    groups = {}
    for r in books:
        if r["layer"] not in want or r["book"] == parent_book:
            continue
        ccs = cs_filled(r["book"])       # 空缺已补好：标题往后跟、正文往前跟
        g = {"title": r["title"], "map": {}}
        for cp, c in sorted(ccs.items()):
            if c in want_cs:
                g["map"].setdefault(cp, [])
                for pp in want_cs[c]:
                    if pp not in g["map"][cp]:
                        g["map"][cp].append(pp)
        if g["map"]:
            groups[(r["layer"], r["book"])] = g
    return groups


def collect(parent_book, parent_paras, want, books):
    return by_cs(parent_book, parent_paras, want, books)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True, help="本文（mūla）的 book")
    ap.add_argument("--para", required=True, help="本文段号：984 / 983-986")
    ap.add_argument("--no-tika", action="store_true", help="只到义注，不含复注")
    ap.add_argument("--chapter", action="store_true",
                    help="各层扩成该层书目录里的完整一章（处理整章时应当加）")
    args = ap.parse_args()

    mula_paras = parse_paras(args.para)
    books = layer_books(args.book)      # 一次 books 调用，拿到同卷各层的书号
    groups = [{
        "layer": "mula", "book": args.book, "title": "",
        "paras": mula_paras, "parent_book": None, "map": {},
    }]

    # 本文 → 义注
    att = collect(args.book, mula_paras, {"atthakatha"}, books)
    for (layer, cbook), g in sorted(att.items(), key=lambda kv: kv[0][1]):
        groups.append({
            "layer": layer, "book": cbook, "title": g["title"],
            "paras": sorted(g["map"]), "parent_book": args.book,
            "map": {str(k): v for k, v in sorted(g["map"].items())},
        })

    # 义注 → 复注（复注的父层是义注，不是本文——被解释词引自义注）
    if not args.no_tika:
        for ag in [g for g in groups if g["layer"] == "atthakatha"]:
            tik = collect(ag["book"], ag["paras"], {"tika"}, books)
            for (layer, cbook), g in sorted(tik.items(), key=lambda kv: kv[0][1]):
                groups.append({
                    "layer": layer, "book": cbook, "title": g["title"],
                    "paras": sorted(g["map"]), "parent_book": ag["book"],
                    "map": {str(k): v for k, v in sorted(g["map"].items())},
                })

    if args.chapter:
        for g in groups:
            if not g["paras"]:
                continue
            full, title = to_chapter(g["book"], g["paras"])
            # map 里只有 related 问到的那些段；扩章后新增的段没有父层映射，
            # 留空即可——父层对照按整章给，不靠逐段映射
            g["paras"], g["chapter"] = full, title

    json.dump({"groups": groups}, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
