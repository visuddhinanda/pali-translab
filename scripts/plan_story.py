# -*- coding: utf-8 -*-
"""故事型规划器（**schema 3 · variant story**）：偈颂 + 因缘故事的书（法句经、长老偈、本生…）。

schema 3 的 plan_scan 是为「义注 = 名词解释」设计的：本文先译，义注按 cs 挂父层、
被解释词逐字对齐。故事型的书反过来——义注大半是故事，偈颂**连同上下文**整段引在
义注里，而且义注有缅文 nissaya。所以这里**义注先译、本文照抄**：

  规划期
    P1 两层巴利原文先拉进本地缓存（workspace/cache/text_<book>.jsonl，句级）
    P2/P3 本文每一偈与义注里同号偈的引文比对（去标点、数字、空格、异读括注、
          引号与句末 iti，只比巴利字母；末字的 iti 连音 ā/a、ī/i、ū/u、ṃ/n 视为相同）
          → **照抄组**（逐句对得上）/ **自译组**（义注没引，或文字不同）
    P4 自译组每偈：从义注同 cs 段里取带黑体的句子（被解释词的解释），本文 review 时注入
    P5 义注按故事（vatthu）切块，块不跨故事、不跨品

  执行阶段（--barrier 一阶段做完再进下一阶段）
    names → 义注 translate → review → revise → 本文 copy（照抄组）
          → 本文 translate → review → revise（自译组）→ export
    义注 translate/review/revise 注入「本块出现的人名地名」；review 带 nissaya。
    没有统稿。

调度结构与 schema 3 完全相同（tasks + needs + stages），守护进程、看门狗、进度页照用；
执行器按 `variant: story` 认出新步骤（names / vcopy）与两种注入。

`--reuse <旧计划 project.json>`：旧计划 audit 里本文已 translate ok 的段，新计划里
完全落在这些段内的本文 translate task 直接标 done（不重译）。

用法：
    python3 scripts/plan_story.py --project kn2 --mula 156:3:1392 --att 122:3:5229 \\
        --channel <uid> --title "…" --reuse workspace/projects/kn2/project.scan.json
"""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _wp import cs_filled, para_chars, para_sents, paras  # noqa: E402
import align_heading as ah  # noqa: E402
import plan_scan as ps  # noqa: E402
import project as pj  # noqa: E402

CACHE = "workspace/cache"
MARK = re.compile(r"^\s*(\d+)\s*\.\s*$")          # 偈号标题「21.」
ITI_END = re.compile(r"[’']\s*[’']\s*ti\s*[.,;:!?–\-]*\s*$")  # 句末引号 + iti，后面只剩标点
COLOPHON = re.compile(r"niṭṭhit[oā]\s*[.,]?\s*$")
TAIL = str.maketrans("āīūṃ", "aiun")


# ══════════ P1 原文缓存 ══════════

def text_path(book):
    return os.path.join(CACHE, f"text_{book}.jsonl")


def load_text(book):
    """{段: [句…]}（句按 word_start 排）。缓存不在就报错——规划必须先拉原文。"""
    p = text_path(book)
    if not os.path.exists(p):
        sys.exit(f"缺原文缓存 {p}：先跑 python3 scripts/wp_pull.py --book {book} "
                 f"--para <全书> > {p}")
    out = {}
    for line in open(p, encoding="utf-8"):
        if not line.startswith("{"):
            continue
        r = json.loads(line)
        if r.get("layer") != "mula":
            continue
        out.setdefault(int(r["paragraph"]), []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r["word_start"])
    return out


# ══════════ P2/P3 偈颂比对 ══════════

def norm(s, end=False):
    """只留巴利字母。end=True：这是一偈的最后一句，先剥句末 iti、末字连音归一。"""
    s = s.replace("**", "")                      # 黑体标记会把「’’ ti」拆开，先去掉
    if end:
        s = ITI_END.sub("", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)            # 异读括注 [ amataṃ padaṃ ( ka .)]
    s = re.sub(r"\([^)]*\)", " ", s)             # 出处括注 ( dha . pa .137-140)
    s = unicodedata.normalize("NFC", s.replace("**", "").lower())
    s = "".join(ch for ch in s if ch.isalpha())
    if end and s:
        s = s[:-1] + s[-1].translate(TAIL)
    return s


def has_pali(s):
    return bool(norm(s))


def verse_groups(rows, text, lo, hi):
    """{偈号 N: [句…]}——偈号标题之后、下一个标题之前的正文句子（只要有巴利字母的）。"""
    out, cur = {}, None
    for x in rows:
        p = x["paragraph"]
        if not (lo <= p <= hi):
            continue
        if x.get("level", 100) < 100:
            m = MARK.match(x.get("toc") or "")
            cur = int(m.group(1)) if m else None
            continue
        if cur is not None:
            # 品末结语（Yamakavaggo paṭhamo niṭṭhito）不属于最后一偈
            out.setdefault(cur, []).extend(r for r in text.get(p, []) if has_pali(r["pali"])
                                           and not COLOPHON.search(r["pali"]))
    return out


def match_quote(msents, arows, atext, start_idx):
    """本文一偈 msents 与义注偈号标题之后的句子逐句对齐。

    返回 [(本文句 id, [义注句 id…])] 或 None。义注从标题后第一段起往后取句子，
    累加到与本文这一偈的字母串相同为止；每个本文句的边界必须落在义注句的边界上。
    """
    if not msents:
        return None
    mn = [norm(r["pali"], end=(i == len(msents) - 1)) for i, r in enumerate(msents)]
    target = "".join(mn)
    # 义注候选句：标题后连续的正文段，遇到下一个标题停；最多取本文句数 + 3 句
    cand = []
    for x in arows[start_idx + 1:]:
        if x.get("level", 100) < 100:
            break
        cand.extend(r for r in atext.get(x["paragraph"], []) if has_pali(r["pali"]))
        if len(cand) >= len(msents) + 3:
            break
    for k in range(1, len(cand) + 1):
        an = [norm(r["pali"], end=(i == k - 1)) for i, r in enumerate(cand[:k])]
        if "".join(an) != target:
            continue
        # 边界对齐：本文第 i 句 = 义注若干句之和
        pairs, j = [], 0
        for i, m in enumerate(mn):
            acc, ids = "", []
            while j < k and len(acc) < len(m):
                acc += an[j]
                ids.append(cand[j]["id"])
                j += 1
            if acc != m:
                return None
            pairs.append((msents[i]["id"], ids))
        return pairs if j == k else None
    return None


# ══════════ 主流程 ══════════

def bounds_of(rows, level):
    """{段: 界号}——遇到 level 及更高级的标题就换一界（故事 vatthu = 4，品 = 2）。"""
    out, b = {}, 0
    for x in rows:
        if x.get("level", 100) <= level:
            b += 1
        out[x["paragraph"]] = b
    return out


def chunks_of(book, lo, hi, layer, bounds, args, skip=()):
    ps.ALIGN = {"hard_keys": True, "bounds": {str(book): {str(p): v for p, v in bounds.items()}},
                "para_key": {}}
    try:
        return ps.layer_chunks(book, lo, hi, layer, args, skip=skip)
    finally:
        ps.ALIGN = None


def old_translated(path, book):
    """旧计划 audit 里 translate ok 的本文段。"""
    if not path:
        return set()
    old = json.load(open(path, encoding="utf-8"))
    tasks = {t["id"]: t for t in old.get("tasks") or []}
    aud = os.path.join(os.path.dirname(path), "audit.log")
    done = set()
    if not os.path.exists(aud):
        return done
    for line in open(aud, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        t = tasks.get(r.get("task"))
        if (r.get("status") == "ok" and t and t.get("step") == "translate"
                and int(t.get("book") or 0) == book):
            skip = set()
            for m in old.get("layers") or []:
                for ch in m.get("chunks") or []:
                    if r["task"].startswith(ch["id"] + ":"):
                        skip = set(ch.get("skip") or [])
            done.update(p for p in range(t["start"], t["end"] + 1) if p not in skip)
    return done


def task(tid, stage, step, layer, book, ch, needs, **kw):
    t = {"id": tid, "stage": stage, "step": step, "layer": layer, "book": book,
         "start": ch["start"] if ch else None, "end": ch["end"] if ch else None,
         "chars": ch.get("chars", 0) if (ch and step == "translate") else 0,
         "sents": ch.get("sents", 0) if ch else 0,
         "title": ch.get("title", "") if ch else "",
         "needs": sorted(set(needs)), "status": pj.PENDING, "tries": 0,
         "began": "", "ended": "", "note": "", "detail": ""}
    t.update(kw)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--mula", required=True, help="book:start:end")
    ap.add_argument("--att", required=True, help="book:start:end")
    ap.add_argument("--channel", required=True)
    ap.add_argument("--method", default="default")
    ap.add_argument("--chunk-chars", type=int, default=5000, dest="chunk_chars")
    ap.add_argument("--max-sents", type=int, default=80, dest="max_sents")
    ap.add_argument("--max-paras", type=int, default=0, dest="max_paras")
    ap.add_argument("--names-chars", type=int, default=30000, dest="names_chars",
                    help="一个 names task 读多少义注字符")
    ap.add_argument("--reuse", default="", help="旧计划 project.json：沿用其中已 translate 的本文段")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mb, mlo, mhi = map(int, args.mula.split(":"))
    ab, alo, ahi = map(int, args.att.split(":"))
    mrows = sorted((x for x in paras(mb) if mlo <= x["paragraph"] <= mhi), key=lambda x: x["paragraph"])
    arows = sorted((x for x in paras(ab) if alo <= x["paragraph"] <= ahi), key=lambda x: x["paragraph"])
    mhi, ahi = min(mhi, mrows[-1]["paragraph"]), min(ahi, arows[-1]["paragraph"])
    mtext, atext = load_text(mb), load_text(ab)

    # ── P2/P3：本文每偈 ↔ 义注同号偈引文 ──
    mverse = verse_groups(mrows, mtext, mlo, mhi)
    # 偈号 → 义注里该偈号标题在 arows 中的全部下标。同号可能出现多次（法句经义注序论
    # 自己的颂也编「1.」「2.」…），逐个试，取第一个对得上的
    amarks = {}
    for i, x in enumerate(arows):
        if x.get("level", 100) < 100:
            m = MARK.match(x.get("toc") or "")
            if m:
                amarks.setdefault(int(m.group(1)), []).append(i)
    copy_pairs, self_verses, why = {}, [], {}
    for n, ms in sorted(mverse.items()):
        if n not in amarks:
            self_verses.append(n); why[n] = "义注未引"
            continue
        pr = next((r for r in (match_quote(ms, arows, atext, i) for i in amarks[n]) if r), None)
        if pr:
            copy_pairs[n] = pr
        else:
            self_verses.append(n); why[n] = "文字不同"

    # 照抄段：整段句子都在照抄对里的本文段
    pair_of = {mid: aids for pr in copy_pairs.values() for mid, aids in pr}
    verse_last = {pr[-1][0] for pr in copy_pairs.values()}      # 每偈最后一句（偈尾改句号用）
    copy_paras = set()
    for p, rs in mtext.items():
        if mlo <= p <= mhi:
            real = [r for r in rs if has_pali(r["pali"])]
            if real and all(r["id"] in pair_of for r in real):
                copy_paras.add(p)

    # ── P4：自译组每偈的义注黑体解释（同 cs 段里带 ** 的句子，引文段除外）──
    csf = cs_filled(ab)
    akey = {int(p): csf[p] for p in range(alo, ahi + 1) if csf.get(p) is not None}
    akey.update({int(p): v for p, v in ah.backfill(arows, 4, csf,
                 {str(p): v for p, v in akey.items()}).items()})
    quote_ids = {a for pr in copy_pairs.values() for _m, aids in pr for a in aids}
    gloss = {}
    for p, rs in atext.items():
        n = akey.get(p)
        if n in self_verses:
            for r in rs:
                if "**" in r["pali"] and r["id"] not in quote_ids:
                    gloss.setdefault(n, []).append(r["id"])

    # ── P5：切块 ──
    A = {"id": "SA", "layer": "atthakatha", "book": ab, "start": alo, "end": ahi,
         "title": arows[0].get("toc") or f"book {ab}"}
    M = {"id": "SM", "layer": "mula", "book": mb, "start": mlo, "end": mhi,
         "title": mrows[0].get("toc") or f"book {mb}"}
    achs = chunks_of(ab, alo, ahi, "atthakatha", bounds_of(arows, 4), args)
    mchs = chunks_of(mb, mlo, mhi, "mula", bounds_of(mrows, 2), args, skip=copy_paras)
    for pre, chs, w in (("SA", achs, A), ("SM", mchs, M)):
        for i, ch in enumerate(chs, 1):
            ch["id"] = f"{pre}{i}"
            ch["book"] = w["book"]
            ch["layer"] = w["layer"]
            ch["title"] = ps.chunk_title(ch)
        w["chunks"] = chs
        w["chars"] = sum(c["chars"] for c in chs)
        w["sents"] = sum(c["sents"] for c in chs)
        w["paras"] = sum(c["paras"] for c in chs)
        w["layer_cn"] = ps.LAYER_CN.get(w["layer"], w["layer"])
        w["pfx"] = pre
        w["parent_id"] = None

    def a_chunk_of(sid):
        p = int(sid.split("-")[1])
        return next(c for c in achs if c["start"] <= p <= c["end"])

    verse_of_para = {}
    for n, ms in mverse.items():
        for r in ms:
            verse_of_para[int(r["paragraph"])] = n
    for ch in mchs:
        ps_ = range(ch["start"], ch["end"] + 1)
        ch["skip"] = sorted(p for p in ps_ if p in copy_paras)
        ch["vcopy"] = [[mid, pair_of[mid], mid in verse_last] for p in ch["skip"]
                       for r in mtext.get(p, []) if r["id"] in pair_of for mid in [r["id"]]]
        vs = sorted({verse_of_para[p] for p in ps_ if p not in copy_paras and p in verse_of_para})
        ch["gloss"] = [[n, sid] for n in vs for sid in gloss.get(n, [])]
        ch["todo"] = sum(1 for p in ps_ if p not in copy_paras
                         and any(has_pali(r["pali"]) for r in mtext.get(p, [])))

    # ── names：义注按 --names-chars 合并成若干段 ──
    names, cur = [], None
    for ch in achs:
        if cur and cur["chars"] + ch["chars"] > args.names_chars:
            names.append(cur); cur = None
        if cur is None:
            cur = {"start": ch["start"], "end": ch["end"], "chars": 0, "sents": 0,
                   "title": ch["title"]}
        cur["end"] = ch["end"]; cur["chars"] += ch["chars"]; cur["sents"] += ch["sents"]
    if cur:
        names.append(cur)
    for i, n in enumerate(names, 1):
        n["id"] = f"N{i}"

    # ── 沿用旧计划已译的本文段 ──
    reused = old_translated(args.reuse, mb)

    # ── tasks（队列顺序 = 阶段顺序）──
    T = []
    N_ids = [f'{n["id"]}:names' for n in names]
    for n in names:
        T.append(task(f'{n["id"]}:names', "names", "names", "atthakatha", ab, n, []))
    for st in ("translate", "review", "revise"):
        for ch in achs:
            dep = N_ids if st == "translate" else [f'{ch["id"]}:{"translate" if st == "review" else "review"}']
            T.append(task(f'{ch["id"]}:{st}', f"a{st}", st, "atthakatha", ab, ch, dep))
    for ch in mchs:
        if ch["vcopy"]:
            dep = {f'{a_chunk_of(a)["id"]}:revise' for _m, aids, _l in ch["vcopy"] for a in aids}
            T.append(task(f'{ch["id"]}:vcopy', "copy", "vcopy", "mula", mb, ch, dep,
                          sents=len(ch["vcopy"])))
    nreuse = 0
    for st in ("translate", "review", "revise"):
        for ch in mchs:
            if not ch["todo"]:
                continue
            if st == "translate":
                dep = []
            elif st == "review":
                dep = [f'{ch["id"]}:translate'] + [f'{a_chunk_of(s)["id"]}:revise'
                                                    for _n, s in ch["gloss"]]
            else:
                dep = [f'{ch["id"]}:review']
            t = task(f'{ch["id"]}:{st}', f"m{st}", st, "mula", mb, ch, dep)
            if st == "translate" and reused:
                own = [p for p in range(ch["start"], ch["end"] + 1)
                       if p not in copy_paras and para_chars(mb).get(p, 0)]
                if own and all(p in reused for p in own):
                    t.update(status=pj.DONE, note="沿用旧计划已译（scan 计划 M:translate）",
                             detail="reuse")
                    nreuse += 1
            T.append(t)
    exports = [{"id": "ESA", "book": ab, "layer": "atthakatha", "start": alo, "end": ahi,
                "title": A["title"]},
               {"id": "ESM", "book": mb, "layer": "mula", "start": mlo, "end": mhi,
                "title": M["title"]}]
    ids = {t["id"] for t in T}
    T.append(task("ESA:export", "export", "export", "atthakatha", ab,
                  exports[0], [f'{c["id"]}:revise' for c in achs]))
    T.append(task("ESM:export", "export", "export", "mula", mb, exports[1],
                  [x for c in mchs for x in (f'{c["id"]}:vcopy', f'{c["id"]}:revise') if x in ids]))

    stages = [{"id": i, "step": st, "layer": ""} for i, st in (
        ("names", "names"), ("atranslate", "translate"), ("areview", "review"),
        ("arevise", "revise"), ("copy", "vcopy"), ("mtranslate", "translate"),
        ("mreview", "review"), ("mrevise", "revise"), ("export", "export"))]
    stages = [s for s in stages if any(t["stage"] == s["id"] for t in T)]

    proj = {"schema": 3, "variant": "story", "name": args.project,
            "title": args.title or f"book {mb} 故事型两层翻译",
            "created": pj.now(), "updated": pj.now(), "book": mb,
            "channel": args.channel, "method": args.method, "state": "idle", "command": None,
            "steps": ["names", "translate", "review", "revise", "vcopy", "export"],
            "chunking": {"chunk_chars": args.chunk_chars, "max_sents": args.max_sents,
                         "max_paras": args.max_paras, "names_chars": args.names_chars,
                         "sent_counts": ps.have_sent_counts(), "scan": True},
            "story": {"copy_verses": sorted(copy_pairs), "self_verses": self_verses,
                      "self_reason": {str(k): v for k, v in why.items()},
                      "names": names, "text_cache": [text_path(mb), text_path(ab)],
                      "reuse": args.reuse or None},
            "books": {str(ab): {"layer": "atthakatha", "title": A["title"]},
                      str(mb): {"layer": "mula", "title": M["title"]}},
            "layers": [A, M], "harmonize": [], "exports": exports,
            "stages": stages, "tasks": T}

    # ── 自检 ──
    errs = []
    for w in (A, M):
        prev = w["start"] - 1
        for c in w["chunks"]:
            if c["start"] != prev + 1:
                errs.append(f'{w["id"]} 在 {prev}/{c["start"]} 有缝或重叠')
            prev = c["end"]
        if prev != w["end"]:
            errs.append(f'{w["id"]} 末段 {prev} ≠ {w["end"]}')
    byid = {t["id"]: t for t in T}
    if len(byid) != len(T):
        errs.append("task id 重复")
    for t in T:
        for d in t["needs"]:
            if d not in byid:
                errs.append(f'{t["id"]} 依赖不存在的 {d}')
    order = {t["id"]: i for i, t in enumerate(T)}
    for t in T:                                    # 队列顺序即拓扑序：依赖都在前面
        for d in t["needs"]:
            if d in order and order[d] > order[t["id"]]:
                errs.append(f'{t["id"]} 的依赖 {d} 排在后面')

    nv = len(mverse)
    print(f"本文 {mb}:{mlo}-{mhi}｜{nv} 偈：照抄 {len(copy_pairs)}，自译 {len(self_verses)}"
          f"（义注未引 {sum(1 for v in why.values() if v == '义注未引')}，"
          f"文字不同 {sum(1 for v in why.values() if v == '文字不同')}）", file=sys.stderr)
    print(f"  自译组有黑体解释的偈 {sum(1 for n in self_verses if gloss.get(n))}/{len(self_verses)}",
          file=sys.stderr)
    print(f"义注 {ab}:{alo}-{ahi}｜{len(achs)} 块（按故事切，{A['chars']:,} 字符 / {A['sents']:,} 句）"
          f"｜names {len(names)} 个", file=sys.stderr)
    print(f"本文 {len(mchs)} 块：照抄 task {sum(1 for c in mchs if c['vcopy'])}，"
          f"自译块 {sum(1 for c in mchs if c['todo'])}（沿用已译 {nreuse}）", file=sys.stderr)
    print("阶段：" + " → ".join(s["id"] for s in stages) + f"｜task {len(T)} 个", file=sys.stderr)
    if errs:
        for e in errs[:20]:
            print("  ✗ " + e, file=sys.stderr)
        sys.exit("自检失败，没有落盘")
    print("  ✓ 自检通过：两层无缝覆盖、task 唯一、依赖齐全且都在前面", file=sys.stderr)
    if args.dry_run:
        print("  （--dry-run：没有落盘）", file=sys.stderr)
        return proj
    pj.save(proj)
    print(f"→ {pj.path_of(args.project)}", file=sys.stderr)
    return proj


if __name__ == "__main__":
    main()
