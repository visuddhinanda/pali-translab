# -*- coding: utf-8 -*-
"""vin6（双巴提木叉 / Kaṅkhāvitaraṇī 一族）的**跨层对齐表**：代替 cs_para。

这一族的 cs_para 不能当跨书坐标用（2026-10-28 实测）：
  · 本文 207:3-1214 的 cs 是**类内条号**，每个 uddesa 从 1 重数，两部巴提木叉各数一遍；
    uddesa 开头的引导段还带着上一类的末号（207:33-35 在僧残下却标 4）。
  · 义注 207:1215-2713 的 1135 个正文段**全部 cs=75**——从本文末尾往下填的，无意义。
  · 古复注 212:2-670 一个 cs 都没有；新复注只有书末 18 颂跋文带 cs 1-18。

所以按标题对齐。键 = (部, 类, 条号)：
  部   bhu（比丘）/ bhuni（比丘尼）——以 `…Bhikkhunīpātimokkha…` 标题切换
  类   par 波罗夷 / sg 僧残 / ani 不定 / nis 舍堕 / pac 波逸提 / pat 悔过 / sek 众学 /
       as 灭诤 / nid 序 / gan 造论缘起 / nig 结语；条号 0 = 类的引导段
  本文的条号取「uddesa 标题 + 类内 cs」，注释取「类标题 + 品 + 学处标题编号」。

注释按品编号（1-10 每品重数）时，品的起号**取义注实际各品条数累加**，不按每品 10 条算
（比丘波逸提的同法品有 12 条，比丘尼第 8、9 品各 13 条）。复注缺品（古复注波逸提
从第 4 品起、品内也常从第 2 条开注）或改用绝对编号（新复注比丘尼舍堕第 2 品从 11 起）
都靠这张品表兜住。

一个注释标题覆盖几条（`3-4.`、`7-8-9.`、`1…Pe…4.`）时，这几条在**所有层**并成一组
（并查集）——组是对齐的最小单位，组号按经文顺序排，可以直接当 cs 用。

比丘尼部与比丘部**巴利逐句相同**（句子切分与文字全同，含条号）的段，记进 `copy`：
这些段不译，等比丘部定稿后照搬（plan_scan 的 copy 步骤）。共学处的正文因为
bhikkhu → bhikkhunī 变格，绝大多数并不相同，照搬的主要是标题与定型句。

用法：
    python3 scripts/align_vin6.py --out workspace/projects/<name>/align.json
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import jget, paras  # noqa: E402

# 本文合成一个 work：两部巴提木叉同在 207、首尾相接，而义注一部书注两部——
# 拆成两个 work 的话义注只能挑一个父 work，另一部就没有对照了。
WORKS = [
    {"layer": "mula", "book": 207, "start": 3, "end": 1214,
     "title": "Dvemātikāpāḷi（Bhikkhu + Bhikkhunīpātimokkha）"},
    {"layer": "atthakatha", "book": 207, "start": 1215, "end": 2713,
     "title": "Kaṅkhāvitaraṇī-aṭṭhakathā"},
    {"layer": "tika", "book": 212, "start": 2, "end": 670,
     "title": "Kaṅkhāvitaraṇīpurāṇa-ṭīkā"},
    {"layer": "tika", "book": 212, "start": 671, "end": 2517,
     "title": "Kaṅkhāvitaraṇī-abhinavaṭīkā"},
]
BHU_END = 523          # 207:3-523 比丘巴提木叉，524-1214 比丘尼巴提木叉

KINDS = [("ganthārambh", "gan"), ("nidān", "nid"), ("pārājik", "par"),
         ("saṅghādises", "sg"), ("aniyat", "ani"), ("nissaggiy", "nis"),
         ("pācittiy", "pac"), ("pāṭidesanīy", "pat"), ("sekhiy", "sek"),
         ("adhikaraṇasamath", "as"), ("nigamana", "nig")]
KIND_ORDER = {k: i for i, (_, k) in enumerate([("", "pre")] + KINDS)}
PART_ORDER = {"bhu": 0, "bhuni": 1}

# 标题本身说不清、只能人工指定的几处（都是「同前」式的合注）
OVERRIDES = {
    (207, 2240): ("bhuni", "sg", 14, 17),    # 14. Saṅghabhedakādi = 14-17
    (207, 2668): ("bhuni", "pac", 97, 166),  # 10…Pe…16. musāvādādivaggo：共学处七品
    (207, 2682): ("bhuni", "pat", 2, 8),     # 2. Telaviññāpanādi = 2-8
    (207, 2688): ("bhuni", "sek", 1, 75),    # 比丘尼众学 + 灭诤：同比丘部
    (212, 2421): ("bhuni", "pat", 2, 8),
    (212, 2427): ("bhuni", "sek", 1, 75),    # 标在悔过类下，实为众学
}
NUM_RE = re.compile(r"^(\d+)(?:\s*(?:-|–|…Pe…|…pe…)\s*\d+)*\.")


def kind_of(t):
    t = t.lower()
    return next((k for kw, k in KINDS if kw in t), None)


def heading_nums(t):
    m = NUM_RE.match(t)
    return [int(x) for x in re.findall(r"\d+", m.group(0))] if m else []


def parse_work(w, vagga_tab):
    """{段号: (部, 类, 起条, 止条)}。标题段取它后面第一段正文的键。

    vagga_tab：{(部, 类, 品号): (起条, 止条)}，义注解析时填，复注解析时查。
    """
    rows = [r for r in paras(w["book"]) if w["start"] <= r["paragraph"] <= w["end"]]
    part, kd, key = "bhu", "pre", ("bhu", "pre", 0, 0)
    vg, voff = 0, 0
    out, pending = {}, []
    for r in rows:
        p, t = r["paragraph"], (r.get("toc") or "").strip()
        if (w["book"], p) in OVERRIDES:
            key = OVERRIDES[(w["book"], p)]
            part, kd = key[0], key[1]
            out[p] = key
            continue
        if w["layer"] == "mula":
            part = "bhu" if p <= BHU_END else "bhuni"
        if r["level"] < 100:
            low = t.lower()
            if "bhikkhunīpātimokkh" in low:
                part, kd, key = "bhuni", "pre", ("bhuni", "pre", 0, 0)
                pending.append(p)
                continue
            nums = heading_nums(t)
            if nums and "vagg" in low and "sikkhāpad" not in low:
                # 品标题：「4. Bhojanavaggo」或古复注的「4. Catutthavaggavaṇṇanā」
                vg = nums[0]
                rng = vagga_tab.get((part, kd, vg))
                if w["layer"] == "atthakatha" or not rng:
                    voff = sum(b - a + 1 for (pp, kk, v), (a, b) in vagga_tab.items()
                               if pp == part and kk == kd and v < vg)
                else:
                    voff = rng[0] - 1
                if w["layer"] != "atthakatha" and rng and "vaṇṇanā" in low:
                    key = (part, kd, rng[0], rng[1])   # 整品合注
                pending.append(p)
                continue
            if nums and kd not in ("pre", "gan", "nid", "nig", "as"):
                # 品内重新编号就加品的起号；编号超出本品条数（如新复注比丘尼舍堕
                # 第 2 品的「11.」）说明是绝对编号。复注常从品中间开注，不能看首号
                rng = vagga_tab.get((part, kd, vg))
                lo, hi = min(nums), max(nums)
                absolute = (not vg or kd not in ("nis", "pac")
                            or (w["layer"] != "atthakatha" and rng
                                and hi > rng[1] - rng[0] + 1))
                if not absolute:
                    lo, hi = lo + voff, hi + voff
                key = (part, kd, lo, hi)
                if w["layer"] == "atthakatha" and vg:
                    a, b = vagga_tab.get((part, kd, vg), (lo, hi))
                    vagga_tab[(part, kd, vg)] = (min(a, lo), max(b, hi))
                pending.append(p)
                continue
            k = kind_of(t)
            if k == "nig" and "nigamanakathā" not in low and kd not in ("pre", "gan", "nid", "nig"):
                k = kd    # 类末的「Nigamanavaṇṇanā」注本类结语；「Nigamanakathā」才是全书结语
            if k:
                kd, vg, voff = k, 0, 0
                key = (part, kd, 0, 0)
            pending.append(p)
            continue
        if w["layer"] == "mula" and kd not in ("pre", "nid", "as"):
            cs = r.get("cs_para")
            # uddesa 开头的引导段带着上一类的末号——第一条 cs=1 出现前都算引导段
            if key[2] == 0 and cs != 1:
                cs = None
            if cs is not None:
                key = (part, kd, cs, cs)
        for q in pending:
            out[q] = key
        pending = []
        out[p] = key
    for q in pending:
        out[q] = key
    return out


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def atoms(key):
    """(部,类,起,止) → 单条键列表；条号 0 是引导段，本身就是一条。"""
    part, kd, lo, hi = key
    return [(part, kd, n) for n in range(lo, hi + 1)] or [(part, kd, 0)]


def sort_atom(a):
    return (PART_ORDER[a[0]], KIND_ORDER.get(a[1], 99), a[2])


def mula_text(book, lo, hi):
    """{段号: ((ws,we,文字)…)}——判「巴利逐句相同」用。逐批 get，约三分钟。"""
    out = {}
    ps = list(range(lo, hi + 1))
    for i in range(0, len(ps), 40):
        for x in jget("get", *[f"{book}:{p}" for p in ps[i:i + 40]], "--json") or []:
            s = re.sub(r"<code>.*?</code>", "", x.get("content") or "")
            s = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()
            out.setdefault(x["paragraph"], {})[(x["word_start"], x["word_end"])] = s
        print(f"  取本文 {min(i + 40, len(ps))}/{len(ps)} 段", file=sys.stderr, end="\r")
    print(file=sys.stderr)
    return {p: tuple(sorted((a, b, s) for (a, b), s in v.items())) for p, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="对齐表落盘路径（项目目录下的 align.json）")
    ap.add_argument("--no-copy", action="store_true", help="不比对本文文字，不产出 copy 表")
    args = ap.parse_args()

    vagga_tab, keys = {}, {}
    for w in WORKS:                      # 顺序要紧：义注先于复注，复注查它的品表
        keys[(w["book"], w["start"])] = parse_work(w, vagga_tab)

    dsu = DSU()
    for km in keys.values():
        for k in set(km.values()):
            at = atoms(k)
            for a in at[1:]:
                dsu.union(at[0], a)
    roots = sorted({dsu.find(a) for km in keys.values() for k in km.values()
                    for a in atoms(k)}, key=sort_atom)
    members = {}
    for km in keys.values():
        for k in km.values():
            for a in atoms(k):
                members.setdefault(dsu.find(a), set()).add(a)
    gid = {r: i + 1 for i, r in enumerate(sorted(roots, key=lambda r: sort_atom(min(
        members[r], key=sort_atom))))}

    para_key = {}
    for w in WORKS:
        km = keys[(w["book"], w["start"])]
        d = para_key.setdefault(str(w["book"]), {})
        for p, k in km.items():
            d[str(p)] = gid[dsu.find(atoms(k)[0])]

    groups = []
    for r, g in sorted(gid.items(), key=lambda x: x[1]):
        ms = sorted(members[r], key=sort_atom)
        a, b = ms[0], ms[-1]
        groups.append({"id": g, "label": f"{a[0]}.{a[1]}.{a[2]}"
                       + (f"-{b[2]}" if len(ms) > 1 else "")})

    # 覆盖报告：每类每条在各层有没有注
    full = {("bhu", "par"): 4, ("bhu", "sg"): 13, ("bhu", "ani"): 2, ("bhu", "nis"): 30,
            ("bhu", "pac"): 92, ("bhu", "pat"): 4, ("bhu", "sek"): 75,
            ("bhuni", "par"): 8, ("bhuni", "sg"): 17, ("bhuni", "nis"): 30,
            ("bhuni", "pac"): 166, ("bhuni", "pat"): 8, ("bhuni", "sek"): 75}
    coverage = {}
    for w in WORKS:
        got = {}
        for k in keys[(w["book"], w["start"])].values():
            if k[2] > 0:
                got.setdefault((k[0], k[1]), set()).update(range(k[2], k[3] + 1))
        name = f'{w["book"]}:{w["start"]}'
        for (part, kd), n in full.items():
            s = got.get((part, kd), set())
            miss = sorted(set(range(1, n + 1)) - s)
            extra = sorted(s - set(range(1, n + 1)))
            coverage.setdefault(f"{part}.{kd}", {})[name] = {
                "covered": n - len(miss), "of": n, "missing": miss, "out_of_range": extra}

    copy = []
    if not args.no_copy:
        txt = mula_text(207, 3, 1214)
        first = {}
        for p in range(3, BHU_END + 1):
            if txt.get(p):
                first.setdefault(txt[p], p)
        copy = [[207, p, first[txt[p]]] for p in range(BHU_END + 1, 1215)
                if txt.get(p) and txt[p] in first]

    table = {"family": "vin6", "works": WORKS, "para_key": para_key,
             "groups": groups, "copy": copy, "coverage": coverage,
             "overrides": [f"{b}:{p}" for b, p in OVERRIDES]}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(table, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    c = Counter(len(m) for m in members.values())
    print(f"→ {args.out}：{len(groups)} 组（多条合组 {sum(v for k, v in c.items() if k > 1)} 个）"
          f"｜照搬 {len(copy)} 段", file=sys.stderr)
    for lab, per in coverage.items():
        cells = []
        for w in WORKS[1:]:
            v = per[f'{w["book"]}:{w["start"]}']
            cells.append(f'{w["title"][:18]} {v["covered"]}/{v["of"]}'
                         + (f' 越界{v["out_of_range"]}' if v["out_of_range"] else ""))
        print(f"  {lab:<10} " + "｜".join(cells), file=sys.stderr)


if __name__ == "__main__":
    main()
