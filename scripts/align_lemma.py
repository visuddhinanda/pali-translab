# -*- coding: utf-8 -*-
"""按**被解释词**自建跨层对照表：子层（注）每段 → 父层（被注）哪几段。

cs_para 与 `related` 在有些书上不可靠（Abhidhammatthasaṅgaha 一族：本论每品 cs 从 1
重编、Paramatthadīpanī 全书连续编号、两边对不上）。注释的唯一硬证据是它**逐字引用**
父层的词：黑体 `**…**` 与 `‘‘…’’ti` 引文。本脚本只用这个。

算法：
  1. 子层每段抽锚点（黑体连写合并、‘‘…’’ 引文），归一化（去变音、去空格、
     去词尾 ti 连音造成的长元音/鼻音）后在父层全文里找出现位置。
  2. 锚点按命中稀有度加权（只在一段出现的最有分量），得 (子段, 父段, 分数) 候选。
  3. 注释顺着父层讲 → 求**单调**最大权链（子段递增、父段不减），偶然命中被顺序滤掉。
  4. 链上的段：method=lemma，父段 = 链上前后锚点之间、本段锚点命中的全部父段。
     不在链上的段：继承前一个链上段（inherit）；第一个锚点之前的段：none（序论）。
     标题段跟后面第一段正文走。

用法（Abhidhammatthasaṅgaha 一族的实际命令）：
    python3 scripts/align_lemma.py fetch 178 23 24                       # 全文缓存
    A=workspace/projects/abhisangaha/align
    python3 scripts/align_lemma.py align --child 178:875- --parent 178:2-874 --number --out $A/178b__178a.jsonl
    python3 scripts/align_lemma.py align --child 23 --parent 178:2-874 --out $A/23__178a.jsonl
    python3 scripts/align_lemma.py align --child 24 --parent 23 --number --out $A/24__23.jsonl
    # 23 的「[N] Vibhāvaniyaṃ pana」驳议块 → Vibhāvinī（统稿对齐引文用；依赖上面两张表）
    python3 scripts/align_lemma.py align --child 23 --parent 178:875- --zone --exclude 178:2-874 \
        --via $A/23__178a.jsonl $A/178b__178a.jsonl --via-label '^\\s*\\[\\s*\\d+\\s*\\]\\s*Vibhāvaniy' \
        --out $A/23__178b.quote.jsonl
人工覆盖放在 <out 去掉 .jsonl>.overrides.jsonl，重跑时自动套用。
输出每行：{child, parent:[...], method, anchors:[命中的锚点], score}
另在同名 .report.md 写按品统计。
"""
import argparse
import bisect
import collections
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import jget, paras, plain  # noqa: E402

TEXT_CACHE = "workspace/cache_text_{}.jsonl"
END = 10 ** 9


def parse_work(spec):
    """'178:875-' / '178:2-874' / '23' → (book, lo, hi)。"""
    b, _, rng = spec.partition(":")
    if not rng:
        return int(b), 0, END
    lo, _, hi = rng.partition("-")
    return int(b), int(lo), int(hi) if hi else END


# ══════════════════ 全文缓存 ══════════════════

def load_text(book):
    """{段号: {para, level, toc, text}}；text 是该段各句 plain() 后以空格连起来。"""
    out = {}
    p = TEXT_CACHE.format(book)
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            out[r["para"]] = r
    return out


def fetch(book, lo, hi, batch=20, limit=5000):
    have = load_text(book)
    rows = [r for r in paras(book) if lo <= r["paragraph"] <= hi]
    todo = [r for r in rows if r["paragraph"] not in have]
    meta = {r["paragraph"]: r for r in rows}
    print(f"book {book} [{lo}-{hi if hi < END else '末'}]：{len(rows)} 段，"
          f"已缓存 {len(rows) - len(todo)}，待取 {len(todo)}", file=sys.stderr)
    with open(TEXT_CACHE.format(book), "a", encoding="utf-8") as f:
        for i in range(0, len(todo), batch):
            ps = [r["paragraph"] for r in todo[i:i + batch]]
            # get 默认每次最多 200 句，大段会被**静默截断**（23/24 的长段实测缺句）
            recs = jget("get", *[f"{book}:{p}" for p in ps], "--json", "--limit", str(limit))
            if len(recs) >= limit:
                sys.exit(f"{book}:{ps[0]}-{ps[-1]} 达到 --limit {limit}，可能截断，调小 batch")
            by = collections.defaultdict(list)
            for x in recs:
                by[int(x["paragraph"])].append((int(x.get("word_start") or 0), plain(x)))
            for p in ps:
                m = meta[p]
                # sents：句子表里这段的句数（不含纯标点句，与 pali_ids 的口径一致）——
                # 规划切块的真约束，顺带记下，省得另找句子表导出
                f.write(json.dumps({"para": p, "level": m.get("level", 100),
                                    "toc": m.get("toc") or "",
                                    "sents": sum(1 for _, t in by.get(p, [])
                                                 if re.search(r"\w", t)),
                                    "text": " ".join(t for _, t in sorted(by.get(p, [])))},
                                   ensure_ascii=False) + "\n")
            f.flush()
            if (i // batch) % 10 == 0:
                print(f"  {book}: {i + len(ps)}/{len(todo)}", file=sys.stderr)


def write_sents(books, path="workspace/cache_sent_counts.csv"):
    """句数并进规划器读的那份 CSV（book,paragraph,sentences）。别的书的行原样保留。"""
    import csv
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                rows[(int(r["book"]), int(r["paragraph"]))] = int(r["sentences"])
    for b in books:
        got = load_text(b)
        want = {r["paragraph"] for r in paras(b)}
        if not got or want - set(got):
            sys.exit(f"book {b} 的全文缓存不全（{len(got)}/{len(want)} 段），先 fetch 完整再写句数")
        for p, r in got.items():
            if "sents" not in r:
                sys.exit(f"book {b} 的缓存没有句数，删掉 {TEXT_CACHE.format(b)} 重新 fetch")
            rows[(b, p)] = r["sents"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["book", "paragraph", "sentences"])
        for (b, p), n in sorted(rows.items()):
            w.writerow([b, p, n])
    print(f"→ {path}（{len(rows)} 段）", file=sys.stderr)


# ══════════════════ 锚点 ══════════════════

FOLD = str.maketrans({"ā": "a", "ī": "i", "ū": "u", "ṭ": "t", "ḍ": "d", "ḷ": "l",
                      "ṃ": "n", "ṁ": "n", "ṅ": "n", "ñ": "n", "ṇ": "n", "m": "n"})
NONLETTER = re.compile(r"[^a-z]+")


def norm(s):
    """去变音、鼻音全并成 n、去掉一切非字母（含空格）——巴利连写/分写都能对上。"""
    s = unicodedata.normalize("NFC", s.lower()).translate(FOLD)
    return NONLETTER.sub("", s)


def key(anchor):
    """锚点的匹配键：再去掉词尾因 ti 连音变出来的长元音/鼻音（abhivādiyā·ti、anupattan·ti）。"""
    k = norm(anchor)
    k = re.sub(r"(ti|iti)$", "", k) if len(k) > 8 and anchor.rstrip().endswith("ti") else k
    k = re.sub(r"n$", "", k)
    return k[:-1] if k and k[-1] in "aiueo" else k


BOLD_RUN = re.compile(r"(?:\*\*[^*]+\*\*[\s,;.]*)+")
QUOTE = re.compile(r"‘‘(.+?)’’")
JUNK = re.compile(r"^[\s\[\]\d.,;:‘’'\"()\-–—]*$")


def anchors(text):
    """一段里的锚点：相邻黑体合并为一个（** ceto ** ** yuttā ** → ceto yuttā），
    以及 ‘‘…’’ 引文（黑体里的引号先剥掉）。纯标点/编号的黑体丢掉。"""
    out = []
    for m in BOLD_RUN.finditer(text):
        s = re.sub(r"\*\*", " ", m.group(0))
        s = s.replace("‘", " ").replace("’", " ")
        if not JUNK.match(s):
            out.append(" ".join(s.split()))
    flat = text.replace("**", "")
    for m in QUOTE.finditer(flat):
        s = m.group(1)
        if not JUNK.match(s):
            out.append(" ".join(s.split()))
    # 长引文只取首尾两截：整句逐字一致的概率低（版本异文），首尾片段命中更稳
    res = []
    for a in out:
        w = a.split()
        if len(w) > 6:
            res += [" ".join(w[:4]), " ".join(w[-4:])]
        else:
            res.append(a)
    return res


# ══════════════════ 对齐 ══════════════════

class Corpus:
    """父层全文拼成一条串（段间放分隔符），子串查找后用 bisect 还原段号。"""

    def __init__(self, text_rows):
        self.ps, self.starts, buf, pos = [], [], [], 0
        for p in sorted(text_rows):
            k = norm(text_rows[p]["text"]) + "|"
            self.ps.append(p)
            self.starts.append(pos)
            buf.append(k)
            pos += len(k)
        self.s = "".join(buf)

    def hits(self, k, cap=50):
        out, i = set(), self.s.find(k)
        while i >= 0 and len(out) <= cap:
            out.add(self.ps[bisect.bisect_right(self.starts, i) - 1])
            i = self.s.find(k, i + 1)
        return out


NUM = re.compile(r"\s*(\d+)\s*\.")


def lead_num(text):
    m = NUM.match(text.replace("**", ""))
    return m.group(1) if m else None


ZONE_START = re.compile(r"^\s*\[\s*\d+\s*\]")


def zones_of(ctext):
    """驳议块：段首「[N]」起，到下一个段首编号「N.」/「[N]」或标题之前。{段号: 块起段}。
    Paramatthadīpanī 用这种块引别家注释（多为 Vibhāvinī）再驳，引文是逐字的。"""
    out, cur = {}, None
    for p in sorted(ctext):
        r = ctext[p]
        flat = r["text"].replace("**", "")
        if r["level"] < 100 or (NUM.match(flat) and not ZONE_START.match(flat)):
            cur = None
        if r["level"] >= 100 and ZONE_START.match(flat):
            cur = p
        if cur is not None:
            out[p] = cur
    return out


def shingles(text, n=4, min_len=18):
    """连续 n 词窗口（去掉黑体标记）。用于不加引号的直接引用（「…ti vuttaṃ」）。"""
    w = text.replace("**", "").replace("‘", " ").replace("’", " ").split()
    out = []
    for i in range(len(w) - n + 1):
        a = " ".join(w[i:i + n])
        if len(norm(a)) >= min_len:
            out.append(a)
    return out


def align(child, parent, min_key=5, number=False, num_w=2.0, zone=False, exclude=None):
    """number=True：子段段首编号 N 也当锚点，指向父层所有段首编号为 N 的段。
    只用于**编号体系相同**的一对（Vibhāvinī↔Saṅgaha、Anudīpanī↔Paramatthadīpanī）；
    父层每品重编时 N 会有多处，交给单调链挑——挑错品就破坏顺序。
    zone=True：只对齐驳议块（见 zones_of）里的段，块外一律 none，继承不跨块；
    锚点改用连续词串（shingles），exclude 给的那部书里也有的词串丢掉——
    Vibhāvinī 本身引着 Saṅgaha，Saṅgaha 的词在两边都命中，不算 Vibhāvinī 的证据。"""
    cb, clo, chi = child
    pb, plo, phi = parent
    ctext = {p: r for p, r in load_text(cb).items() if clo <= p <= chi}
    ptext = {p: r for p, r in load_text(pb).items() if plo <= p <= phi}
    if not ctext or not ptext:
        sys.exit("全文没缓存，先跑 fetch")
    corp = Corpus(ptext)
    excl = None
    if exclude:
        eb, elo, ehi = exclude
        excl = Corpus({p: r for p, r in load_text(eb).items() if elo <= p <= ehi})

    # 候选：(子段, 父段) → 分数、命中锚点
    cand = collections.defaultdict(lambda: collections.defaultdict(float))
    ev = collections.defaultdict(lambda: collections.defaultdict(list))
    n_anchor = {}
    zmap = zones_of(ctext) if zone else None
    for c in sorted(ctext):
        if ctext[c]["level"] < 100 or (zone and c not in zmap):
            continue
        an = shingles(ctext[c]["text"]) if zone else anchors(ctext[c]["text"])
        n_anchor[c] = len(an)
        for a in an:
            k = norm(a) if zone else key(a)
            if len(k) < min_key or (excl and excl.s.find(k) >= 0):
                continue
            hs = corp.hits(k)
            if not hs or len(hs) > 50:
                continue
            w = min(len(k), 30) / 10 / len(hs)       # 长而稀有的锚点分量大
            for p in hs:
                cand[c][p] += w
                ev[c][p].append(a)

    if number:
        pnum = collections.defaultdict(list)
        for p, r in ptext.items():
            n = lead_num(r["text"])
            if n and r["level"] >= 100:
                pnum[n].append(p)
        for c in sorted(ctext):
            n = lead_num(ctext[c]["text"]) if ctext[c]["level"] >= 100 else None
            for p in pnum.get(n, []):
                cand[c][p] += num_w
                ev[c][p].append(f"#{n}")

    # 单调最大权链：子段递增、父段不减。Fenwick 求前缀最大
    P = sorted(ptext)
    pidx = {p: i + 1 for i, p in enumerate(P)}
    tree = [(0.0, None)] * (len(P) + 2)

    def upd(i, v):
        while i < len(tree):
            if v[0] > tree[i][0]:
                tree[i] = v
            i += i & -i

    def qry(i):
        best = (0.0, None)
        while i > 0:
            if tree[i][0] > best[0]:
                best = tree[i]
            i -= i & -i
        return best

    back = {}
    for c in sorted(cand):
        pend = []
        for p, s in cand[c].items():
            prev = qry(pidx[p])
            pend.append((pidx[p], (prev[0] + s, (c, p)), prev[1]))
        for i, v, pr in pend:
            back[v[1]] = pr
            upd(i, v)
    node = qry(len(P))[1]
    chain = []
    while node:
        chain.append(node)
        node = back.get(node)
    chain.reverse()
    onchain = dict(chain)

    # 逐段定父段
    out, last = {}, None
    cs = [c for c, _ in chain]
    for c in sorted(ctext):
        if c in onchain:
            i = cs.index(c)
            lo = chain[i - 1][1] if i else P[0]
            hi = chain[i + 1][1] if i + 1 < len(chain) else P[-1]
            ps = sorted(p for p in cand[c] if lo <= p <= hi)
            # 以链上主父段为中心，**双向**收相邻（间隔 ≤3 段）的命中：子段 N 常一并注
            # 父层 N 与 N+1 两节，链只会挑分高的那个。远处的重复短语不收。
            keep = [onchain[c]]
            for p in ps:
                if p > keep[-1] and p - keep[-1] <= 3:
                    keep.append(p)
            for p in reversed(ps):
                if p < keep[0] and keep[0] - p <= 3:
                    keep.insert(0, p)
            anc = sorted({a for p in keep for a in ev[c][p]})
            only_num = all(a.startswith("#") for a in anc)
            out[c] = {"parent": keep, "method": "number" if only_num else "lemma",
                      "score": round(sum(cand[c][p] for p in keep), 2), "anchors": anc}
            last = keep[-1]
        elif ctext[c]["level"] < 100:
            out[c] = None                            # 标题，回填
        elif last is None:
            out[c] = {"parent": [], "method": "none", "score": 0, "anchors": []}
        else:
            out[c] = {"parent": [last], "method": "inherit", "score": 0, "anchors": []}
    nxt = None
    for c in sorted(ctext, reverse=True):             # 标题跟后面第一段正文走
        if out[c] is None:
            out[c] = dict(nxt or {"parent": [], "method": "none", "score": 0, "anchors": []},
                          method="heading", anchors=[], score=0)
        else:
            nxt = out[c]
    if zone:
        NONE = {"parent": [], "method": "none", "score": 0, "anchors": []}
        hit_z = {zmap[c] for c, r in out.items() if c in zmap and r["method"] == "lemma"}
        last = None
        for c in sorted(out):
            if c not in zmap or zmap[c] not in hit_z:
                out[c] = dict(NONE)
            elif out[c]["method"] == "lemma":
                last = (zmap[c], out[c]["parent"][-1])
            elif last and last[0] == zmap[c]:
                out[c] = {"parent": [last[1]], "method": "inherit", "score": 0, "anchors": []}
            else:
                out[c] = dict(NONE)
    return ctext, ptext, out, n_anchor


def load_table(path):
    """对照表 jsonl → {子段号: [父段号…]}（只取段号，book 由文件名约定）。"""
    out = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        out[int(r["child"].split(":")[1])] = [int(x.split(":")[1]) for x in r["parent"]]
    return out


def apply_via(out, ctext, via, label=None):
    """驳议块没有逐字证据时**经祖层中转**：本块 → 祖层段（子→祖表）→ 注同一祖层段的
    父层段（父→祖表的反查）。雷迪常转述而不直引 Vibhāvinī，文本上对不出来，
    但它驳的一定是 Vibhāvinī 注同一处本论的那几段。method=via，与逐字证据分开。
    label：块首段须匹配的正则（如 Vibhāvaniyaṃ）——「[N] Ṭīkāsu」驳的是僧伽罗古复注，
    不能中转到 Vibhāvinī。"""
    c2m, p2m = load_table(via[0]), load_table(via[1])
    inv = collections.defaultdict(set)
    for p, ms in p2m.items():
        for m in ms:
            inv[m].add(p)
    zmap = zones_of(ctext)
    blocks = collections.defaultdict(list)
    for c, z in zmap.items():
        blocks[z].append(c)
    n = 0
    for z, cs in blocks.items():
        if any(out[c]["method"] == "lemma" for c in cs):
            continue
        if label and not re.search(label, ctext[z]["text"].replace("**", "")):
            continue
        ms = sorted({m for c in cs for m in c2m.get(c, [])})
        ps = sorted({p for m in ms for p in inv.get(m, ())})
        for c in cs:
            out[c] = {"parent": ps, "method": "via" if ps else "none", "score": 0,
                      "anchors": [f"祖层 {ms[0]}-{ms[-1]}"] if ms else []}
        n += bool(ps)
    return n


def apply_overrides(out, path, pbook):
    """人工覆盖：jsonl，每行 {child:"178:1813-1838", parent:[...]|[], note:"…"}。
    child 可给区间；parent 给空表 = 独立段（跋、序）。覆盖后 method=manual。"""
    if not path or not os.path.exists(path):
        return 0
    n = 0
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        o = json.loads(line)
        _b, lo, hi = parse_work(o["child"])
        hi = lo if o["child"].count("-") == 0 else hi
        par = []
        for x in o.get("parent", []):            # 父段可写区间 "178:864-867"
            _pb, plo, phi = parse_work(x)
            par += list(range(plo, (phi if "-" in x else plo) + 1))
        for c in out:
            if lo <= c <= hi:
                out[c] = {"parent": par, "method": "manual", "score": 0,
                          "anchors": [o.get("note", "")]}
                n += 1
    return n


# ══════════════════ 报告 ══════════════════

def chapters(trows):
    """level==2 的标题作「品」：[(起段, 标题)]；没有 level 2 就退到最小 level。"""
    hs = [(p, r) for p, r in sorted(trows.items()) if r["level"] < 100]
    if not hs:
        return [(min(trows), "")]
    lv = 2 if any(r["level"] == 2 for _, r in hs) else min(r["level"] for _, r in hs)
    out = [(p, r["toc"]) for p, r in hs if r["level"] == lv]
    if not out or out[0][0] > min(trows):
        out.insert(0, (min(trows), "(开头)"))
    return out


def chap_of(chs, p):
    i = bisect.bisect_right([a for a, _ in chs], p) - 1
    return chs[max(i, 0)][1]


def report(child, parent, ctext, ptext, out, n_anchor):
    cch, pch = chapters(ctext), chapters(ptext)
    lines = [f"# 对照表报告：{child} → {parent}", "",
             "| 子层品 | 段 | lemma | number | via | inherit | none+manual | 父层品分布（lemma+number 段） |",
             "|---|---|---|---|---|---|---|---|"]
    agg = collections.OrderedDict()
    for c, r in sorted(out.items()):
        if ctext[c]["level"] < 100:
            continue
        g = agg.setdefault(chap_of(cch, c), collections.defaultdict(int, pc=collections.Counter()))
        g["n"] += 1
        g[r["method"]] += 1
        if r["method"] in ("lemma", "number"):
            g["pc"][chap_of(pch, r["parent"][0])] += 1
    for name, g in agg.items():
        dist = "；".join(f"{k} {v}" for k, v in g["pc"].most_common(3))
        lines.append(f'| {name} | {g["n"]} | {g["lemma"]} | {g["number"]} | {g["via"]} | {g["inherit"]} | {g["none"]}+{g["manual"]} | {dist} |')
    # 可疑：链上父段大跳（> 30 段）
    body = [(c, r) for c, r in sorted(out.items()) if r["method"] in ("lemma", "number")]
    jumps = [(a[0], a[1]["parent"][0], b[0], b[1]["parent"][0]) for a, b in zip(body, body[1:])
             if b[1]["parent"][0] - a[1]["parent"][-1] > 30]
    lines += ["", f"## 父段大跳（相邻 lemma 段之间父段前进 > 30）：{len(jumps)} 处", ""]
    lines += [f"- 子 {a}→父 {pa}，下一子 {b}→父 {pb}" for a, pa, b, pb in jumps[:40]]
    # 父层未被引用的长串
    used = {p for r in out.values() for p in r["parent"] if r["method"] in ("lemma", "number")}
    gaps, run = [], []
    for p in sorted(ptext):
        if ptext[p]["level"] >= 100 and p not in used:
            run.append(p)
        else:
            if len(run) >= 10:
                gaps.append((run[0], run[-1]))
            run = []
    if len(run) >= 10:
        gaps.append((run[0], run[-1]))
    lines += ["", f"## 父层连续 ≥10 段没被任何锚点命中：{len(gaps)} 处", ""]
    lines += [f"- {a}–{b}（{chap_of(pch, a)}）" for a, b in gaps]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("fetch")
    f.add_argument("works", nargs="+")
    sc = sp.add_parser("sents", help="把缓存里的句数并进 workspace/cache_sent_counts.csv")
    sc.add_argument("books", nargs="+", type=int)
    a = sp.add_parser("align")
    a.add_argument("--child", required=True)
    a.add_argument("--parent", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--number", action="store_true", help="段首编号也当锚点（两边编号体系相同时）")
    a.add_argument("--zone", action="store_true", help="只对齐「[N]」驳议块（引别家注再驳）")
    a.add_argument("--exclude", help="这部书里也有的锚点不算（zone 模式排除祖层用）")
    a.add_argument("--via", nargs=2, metavar=("CHILD2ANC", "PARENT2ANC"),
                   help="zone 模式：未命中的驳议块经祖层中转（两张已建好的对照表）")
    a.add_argument("--via-label", help="只中转块首匹配此正则的驳议块")
    a.add_argument("--overrides", help="人工覆盖 jsonl（默认 <out 去掉 .jsonl>.overrides.jsonl）")
    args = ap.parse_args()

    if args.cmd == "fetch":
        for w in args.works:
            fetch(*parse_work(w))
        return
    if args.cmd == "sents":
        write_sents(args.books)
        return
    child, parent = parse_work(args.child), parse_work(args.parent)
    ctext, ptext, out, n_anchor = align(child, parent, number=args.number, zone=args.zone,
                                        exclude=parse_work(args.exclude) if args.exclude else None)
    if args.via:
        print(f"经祖层中转补 {apply_via(out, ctext, args.via, args.via_label)} 个驳议块")
    ov = args.overrides or re.sub(r"\.jsonl$", "", args.out) + ".overrides.jsonl"
    n_ov = apply_overrides(out, ov, parent[0])
    if n_ov:
        print(f"人工覆盖 {n_ov} 段（{ov}）")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fo:
        for c in sorted(out):
            r = out[c]
            fo.write(json.dumps({"child": f"{child[0]}:{c}",
                                 "parent": [f"{parent[0]}:{p}" for p in r["parent"]],
                                 "method": r["method"], "score": r["score"],
                                 "anchors": r["anchors"]}, ensure_ascii=False) + "\n")
    rep = report(args.child, args.parent, ctext, ptext, out, n_anchor)
    open(re.sub(r"\.jsonl$", "", args.out) + ".report.md", "w", encoding="utf-8").write(rep)
    cnt = collections.Counter(r["method"] for r in out.values())
    print(f"{args.child} → {args.parent}：{dict(cnt)}；写入 {args.out}")


if __name__ == "__main__":
    main()
