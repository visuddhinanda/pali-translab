# -*- coding: utf-8 -*-
"""把一本书切成互不重叠的作业计划：一个作业 = 本文的一章 + 归它翻译的注释章。

**翻译归属与参考范围是两回事**，这是整个计划的核心：

  · 归属（own）——每个注释章只归**一个**作业翻译。本文多章对一章义注是常见现象，
    这时义注归**最早**提到它的那个本文章；后面的本文章不再翻译它。
  · 参考（ref）——后面的本文章在 review 与跨层统稿时**仍要读**那个义注，
    否则被解释词无从对齐、用词也统一不起来。ref 只读不写，可以重叠。

对应关系优先按**章名**判定（本文 `Cūḷasīlaṃ` ↔ 义注 `Cūḷasīlavaṇṇanā`），
章名对不上再退回 `wikipali related` 的段级对应取最早认领者。
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
from _wp import book_chapters, jget, paras  # noqa: E402

LAYER_TAGS = {"aṭṭhakathā": "atthakatha", "ṭīkā": "tika"}
LAYER_ORDER = {"mula": 0, "atthakatha": 1, "tika": 2}


def toc_chapters(book, anchor=3):
    """[(start, end, title)]——一次 `wikipali paras` 拿到，末段已确定，无需再探。"""
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


def chapter_of(chs, para):
    for i, (lo, hi, title) in enumerate(chs):
        if lo <= para and (hi is None or para <= hi):
            return i
    return None


def discover(book, paras):
    """本文这些段落向下关联到的 (layer, book, para)。"""
    hits = []
    for p in paras:
        for rel in jget("related", f"{book}:{p}", "--json", retries=2):
            names = {t.get("name") for t in rel.get("tags", [])}
            layer = next((LAYER_TAGS[n] for n in names if n in LAYER_TAGS), None)
            if layer and rel.get("book") != book:
                for cp in rel.get("para", []):
                    hits.append((layer, rel["book"], cp, rel.get("book_title_pali", "")))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=10**9)
    ap.add_argument("--out", default="", help="计划 json 落盘路径")
    ap.add_argument("--csv", default="",
                    help="任务表 csv 落盘路径；跑之前先出这张表，守护进程再逐条改状态")
    args = ap.parse_args()

    mula = toc_chapters(args.book)
    mula = [(lo, hi, t) for lo, hi, t in mula
            if lo >= args.start and lo <= args.end]
    if not mula:
        sys.exit("该范围内没有本文章节")
    # paras 已经给出真实末段，这里只需按 --end 裁剪
    mula = [(lo, min(hi, args.end), t) for lo, hi, t in mula if lo <= min(hi, args.end)]

    # 1) 逐章向下发现注释坐标
    #
    # **每章只查一段**：三层之间是章节对应，要么一对多要么多对一，不会混合，
    # 所以一段问出来的层归属对整章都成立。
    # **只查有正文的底层章节**：上层章节只是个标题，本身没有对应关系——
    # 用 paras 的 level 分辨（level==100 才是正文段）。
    # 这两条把 related 从「每段一次」压到「每个叶子章节一次」。
    body = {x["paragraph"] for x in paras(args.book) if x["level"] == 100}
    probes = [next((p for p in range(lo, hi + 1) if p in body), None)
              for lo, hi, _t in mula]
    print(f"{len(mula)} 个本文章，其中 {sum(1 for x in probes if x)} 个有正文——"
          f"只对这些各查一次 related", file=sys.stderr)

    per_chapter = []
    books_seen = {}
    for probe in probes:
        hits = discover(args.book, [probe]) if probe is not None else []
        for layer, b, _p, btitle in hits:
            books_seen.setdefault(b, (layer, btitle))
        per_chapter.append(hits)

    ctoc = {b: toc_chapters(b) for b in books_seen}

    # 2) 每个注释章的认领者集合（按本文章序号）
    claims = {}                       # (book, chapter_idx) -> set(本文章序号)
    for mi, hits in enumerate(per_chapter):
        for _layer, b, p, _t in hits:
            ci = chapter_of(ctoc[b], p)
            if ci is not None:
                claims.setdefault((b, ci), set()).add(mi)

    # 3) 定归属：章名匹配优先，否则给最早的认领者
    owner = {}
    for (b, ci), who in claims.items():
        key = norm(ctoc[b][ci][2])
        named = [mi for mi in who if norm(mula[mi][2]) == key]
        owner[(b, ci)] = min(named) if named else min(who)

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
                    note = ""
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

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text + "\n")
        print(f"→ {args.out}（{len(jobs)} 个作业）", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
