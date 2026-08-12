# -*- coding: utf-8 -*-
"""解析一段本文对应的三层文献坐标：mūla → aṭṭhakathā → ṭīkā。

三层在**不同的书**里，段号也不同（本文 93:984 的义注在 103:1470，复注在 185:1345 与 189:1263）。
本脚本用 `wikipali related` 逐层向下问，产出坐标表与**父层映射**——
父层映射是「被解释词逐字同译」这条硬约束的执行依据：义注的父层是本文，复注的父层是义注。

输出 JSON：

    {"groups": [
      {"layer":"mula","book":93,"title":"dīghanikāyapāḷi","paras":[983,984,985,986],
       "parent_book":null,"map":{}},
      {"layer":"atthakatha","book":103,"title":"sumaṅgalavilāsinī","paras":[1468,…],
       "parent_book":93,"map":{"1468":[982,983],…}},
      {"layer":"tika","book":185,"title":"līnatthappakāsanā","paras":[1345,…],
       "parent_book":103,"map":{"1345":[1470],…}}
    ]}

用法：
    python3 scripts/layers.py --book 93 --para 983-986
"""
import argparse
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import jget, parse_paras  # noqa: E402

LAYER_TAGS = {"aṭṭhakathā": "atthakatha", "ṭīkā": "tika"}


def related(book, para, want):
    """<book>:<para> 向下一层的对应坐标：[(layer, book, title, [paras])]"""
    out = []
    for rel in jget("related", f"{book}:{para}", "--json"):
        names = {t.get("name") for t in rel.get("tags", [])}
        layer = next((LAYER_TAGS[n] for n in names if n in LAYER_TAGS), None)
        if layer in want and rel.get("book") != book:
            out.append((layer, rel["book"], rel.get("book_title_pali", ""), rel.get("para", [])))
    return out


def collect(parent_book, parent_paras, want):
    """把父层每一段的下层对应汇总成 {(layer, book): {"title":…, "map": {子段: [父段…]}}}"""
    groups = {}
    for pp in parent_paras:
        for layer, cbook, title, cparas in related(parent_book, pp, want):
            g = groups.setdefault((layer, cbook), {"title": title, "map": {}})
            for cp in cparas:
                g["map"].setdefault(cp, [])
                if pp not in g["map"][cp]:
                    g["map"][cp].append(pp)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True, help="本文（mūla）的 book")
    ap.add_argument("--para", required=True, help="本文段号：984 / 983-986")
    ap.add_argument("--no-tika", action="store_true", help="只到义注，不含复注")
    args = ap.parse_args()

    mula_paras = parse_paras(args.para)
    groups = [{
        "layer": "mula", "book": args.book, "title": "",
        "paras": mula_paras, "parent_book": None, "map": {},
    }]

    # 本文 → 义注
    att = collect(args.book, mula_paras, {"atthakatha"})
    for (layer, cbook), g in sorted(att.items(), key=lambda kv: kv[0][1]):
        groups.append({
            "layer": layer, "book": cbook, "title": g["title"],
            "paras": sorted(g["map"]), "parent_book": args.book,
            "map": {str(k): v for k, v in sorted(g["map"].items())},
        })

    # 义注 → 复注（复注的父层是义注，不是本文——被解释词引自义注）
    if not args.no_tika:
        for ag in [g for g in groups if g["layer"] == "atthakatha"]:
            tik = collect(ag["book"], ag["paras"], {"tika"})
            for (layer, cbook), g in sorted(tik.items(), key=lambda kv: kv[0][1]):
                groups.append({
                    "layer": layer, "book": cbook, "title": g["title"],
                    "paras": sorted(g["map"]), "parent_book": ag["book"],
                    "map": {str(k): v for k, v in sorted(g["map"].items())},
                })

    json.dump({"groups": groups}, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
