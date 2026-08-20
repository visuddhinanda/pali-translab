# -*- coding: utf-8 -*-
"""wikipali CLI 的共用薄封装。只依赖标准库。

本项目所有数据读写都经 wikipali 插件的 `wikipali` 命令，不直连 HTTP、不读本地语料。
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time

PALI_UID = "00b577c0-13b9-11ee-a05a-b7307efd9ee6"  # _System_Pali_VRI_
TAG_RE = re.compile(r"<[^>]+>")
# 黑体在义注/复注里是**被解释词**（引自上一层），必须保住——剥成纯文本就看不出注的是哪个词
BOLD_RE = re.compile(r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>", re.S | re.I)
# <code> 里是版本页码标记（M1.219 / V1.298），不是正文，去掉整段
CODE_RE = re.compile(r"<code\b[^>]*>.*?</code>", re.S | re.I)

# `paras` 是 0.8.6 才有的子命令。装好的插件可能还停在旧版，
# 这时回退到源码仓库里的可执行文件——只影响项目执行层，skill 仍只依赖已发布的 CLI。
_FALLBACK_BIN = "/mnt/visuddhinanda/workspace/wikipali-plugins/plugins/wikipali/bin/wikipali"
_BIN = None

_NOT_FOUND = (
    "找不到 wikipali 命令。请先安装 wikipali 插件（/plugin），"
    "或用 ${CLAUDE_PLUGIN_ROOT}/bin/wikipali；刚装好需重启会话让 PATH 生效。"
)


def _exe(need_paras=False):
    """选一个可用的 wikipali：优先 PATH 上的；要 `paras` 而它不支持就回退到源码版。"""
    global _BIN
    if _BIN is None:
        _BIN = os.environ.get("WIKIPALI_BIN") or shutil.which("wikipali")
    if not _BIN:
        sys.exit(_NOT_FOUND)
    if need_paras and not _supports(_BIN) and os.path.exists(_FALLBACK_BIN):
        return _FALLBACK_BIN
    return _BIN


_SUPPORTS = {}


def _supports(exe):
    if exe not in _SUPPORTS:
        r = subprocess.run([exe, "paras", "--help"], capture_output=True, text=True)
        _SUPPORTS[exe] = r.returncode == 0
    return _SUPPORTS[exe]


def run(args, stdin=None, check=True, retries=0, backoff=20):
    """跑一条 wikipali 命令。

    `retries` > 0 时对失败做指数退避重试——长任务（动辄上千次调用）里网络抖一下
    就整个前功尽弃是不可接受的。**写入不要自动重试**，交给上层流水线重跑，
    免得把「已写入但读回超时」误判成失败而重复提交。
    """
    exe = _exe(need_paras=bool(args) and args[0] == "paras")
    delay = backoff
    for attempt in range(retries + 1):
        r = subprocess.run([exe, *args], input=stdin, capture_output=True, text=True)
        if r.returncode == 0:
            return r
        if attempt < retries:
            print(f"  wikipali {' '.join(args[:2])} 失败，{delay}s 后重试"
                  f"（{attempt + 1}/{retries}）", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, 600)
    if check:
        sys.exit(f"wikipali {' '.join(args)} 失败：\n{r.stderr.strip()}")
    return r


def jget(*args, retries=5):
    """跑一条 wikipali 命令并解析 JSON；解析不了就当空。读操作默认带重试。"""
    try:
        return json.loads(run(list(args), retries=retries).stdout or "[]")
    except json.JSONDecodeError:
        return []


def plain(rec):
    """取句子文本。

    html 型：先摘掉版本页码 `<code>`，把黑体转成 `**…**`（被解释词的唯一线索），再去其余标签。
    markdown 型：原样返回（译文里的行内标记要保留）。
    """
    text = rec.get("content") or ""
    if (rec.get("content_type") or "").lower() in ("html", ""):
        text = CODE_RE.sub("", text)
        text = BOLD_RE.sub(lambda m: f"**{m.group(1).strip()}**", text)
        text = TAG_RE.sub("", text)
    return html.unescape(re.sub(r"[ \t]+", " ", text)).strip()


def parse_paras(spec):
    """段号区间：'984' / '983-986' / '983,985-987' → 有序去重列表。"""
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part.lstrip("-"):
            lo, hi = part.split("-", 1)
            lo, hi = int(lo), int(hi)
            if hi < lo:
                sys.exit(f"段号区间反了：{part}")
            out += range(lo, hi + 1)
        else:
            out.append(int(part))
    return sorted(dict.fromkeys(out))


def dump(obj):
    """紧凑 JSONL，键序即插入序——下游按 '^{\"layer\":\"mula\"' 之类前缀过滤。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


_PARAS_CACHE = {}


def paras(book, refresh=False):
    """整本书的段落清单：一次调用拿到每段字符数与章节层级（`wikipali paras`）。

    这一个接口顶掉了三样旧做法：逐段 related 求章节结构、倍增二分探书末、
    以及分块时逐段拉正文算字符数——那些加起来是全书任务最大的固定开销。

    返回 [{book, paragraph, toc, level, lenght, chapter_len}]，
    `level < 100` 是标题行，`== 100` 是正文段。
    ⚠ 字段名是 `lenght`（服务端如此拼写），不是 length。
    """
    key = int(book)
    if refresh or key not in _PARAS_CACHE:
        cache = f"workspace/cache_paras_{key}.json"
        if not refresh and os.path.exists(cache):
            _PARAS_CACHE[key] = json.load(open(cache, encoding="utf-8"))
        else:
            rows = jget("paras", f"{key}:3", "--body", "--json")
            if rows:
                os.makedirs("workspace", exist_ok=True)
                json.dump(rows, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
            _PARAS_CACHE[key] = rows
    return _PARAS_CACHE[key]


def book_chapters(book):
    """[(start, end, title, 字符数, 段数)]——章节边界与体量，全部来自一次 paras 调用。"""
    rows = paras(book)
    if not rows:
        return []
    heads = [x for x in rows if x["level"] < 100]
    last = rows[-1]["paragraph"]
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1]["paragraph"] - 1 if i + 1 < len(heads) else last
        seg = [x for x in rows if h["paragraph"] <= x["paragraph"] <= end]
        out.append((h["paragraph"], end, h["toc"],
                    sum(plen(x) for x in seg), len(seg)))
    return out


def plen(row):
    """段落字符数。服务端 0.8.7 之前拼作 `lenght`，之后改成 `length`——
    两种都认，否则旧缓存或旧插件会静默返回 0，分块直接失效。"""
    return row.get("length", row.get("lenght", 0))


def cs_map(book):
    """{段号: cs_para}——Chaṭṭha Saṅgāyana 典藏段号，**跨书通用**，是三层之间唯一的公共坐标。

    没有 cs_para 的段（注释层独有的序论、结语）值为 None。旧缓存里没有这个字段，
    遇到就刷新一次，否则三层映射会静默变成空的。
    """
    rows = paras(book)
    if rows and "cs_para" not in rows[0]:
        rows = paras(book, refresh=True)
    return {x["paragraph"]: x.get("cs_para") for x in rows}


def para_chars(book):
    """{段号: 字符数}——分块直接用它，不必再逐段拉正文。"""
    return {x["paragraph"]: plen(x) for x in paras(book)}


def sent_counts(book, plist, batch=30):
    """{段号: 句数}——一次批量取，用来给 chunk 加句数上限。"""
    out = {}
    plist = [int(p) for p in plist]
    for i in range(0, len(plist), batch):
        coords = [f"{book}:{p}" for p in plist[i:i + batch]]
        for r in jget("get", *coords, "--json"):
            out[r["paragraph"]] = out.get(r["paragraph"], 0) + 1
    return out


def chunk_paras(book, plist, budget=5000, max_paras=12, max_sents=60):
    """按巴利字符数切 chunk，并**限制句数**。

    只看字符数会翻车：短句密集的段落（复注常见）10 段就能有 170 多句，
    一次让模型吐 170 行 JSONL 会被输出上限截断，实测停在整 100 行，
    然后条数校验拒绝写入、三次重试全废。句数才是输出长度的真实约束。
    """
    plist = [int(p) for p in plist]
    chars = para_chars(book)
    sents = sent_counts(book, plist) if max_sents else {}
    chunks, cur, size, nsent = [], [], 0, 0
    for p in plist:
        n = chars.get(p, 0)
        if n == 0:
            continue
        k = sents.get(p, 0)
        if cur and (size + n > budget or len(cur) >= max_paras
                    or (max_sents and nsent + k > max_sents)):
            chunks.append(cur); cur, size, nsent = [], 0, 0
        cur.append(p); size += n; nsent += k
    if cur:
        chunks.append(cur)
    return chunks


# ── 跨层书目与 cs 映射 ─────────────────────────────────────────────────
# `wikipali related` 是**段级**接口：一次一段、约 1.5 秒往返。用它做全书规划要
# 每章问一次（一卷 150 多次 ≈ 4 分钟），而它给的段级对应边界还会错位。
# 全书级的事情一律改用 `books`（一次拿到同一卷的各层书号）+ `cs_para`（跨书通用的
# 典藏段号）。related 只留给单段翻译时临时找对应。

LAYER_BY_TAG = {"mūla": "mula", "aṭṭhakathā": "atthakatha",
                "ṭīkā": "tika", "abhinavaṭīkā": "tika"}
# 这些 tag 说的是"哪一层"或"什么体裁"，不是"哪一卷"，配对时要排除
NON_VAGGA_TAGS = set(LAYER_BY_TAG) | {"pāḷi", "sutta", "vinaya", "abhidhamma", "añña"}
_BOOKS_CACHE = {}


def all_books(refresh=False):
    """全部书目（`wikipali books --json`），带 book 号与 tag。一次调用，本地缓存。"""
    if refresh or "rows" not in _BOOKS_CACHE:
        cache = "workspace/cache_books.json"
        if not refresh and os.path.exists(cache):
            _BOOKS_CACHE["rows"] = json.load(open(cache, encoding="utf-8"))
        else:
            rows = jget("books", "--json")
            if rows:
                os.makedirs("workspace", exist_ok=True)
                json.dump(rows, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
            _BOOKS_CACHE["rows"] = rows
    return _BOOKS_CACHE["rows"]


def layer_books(book):
    """与 `book` 同卷的各层书：[{book, layer, title, toc}]，含它自己。

    判定方式：同卷 = 共享全部"卷级 tag"（如 dīghanikāya + sīlakkhandhavagga）；
    层次 = 该书的层级 tag（mūla / aṭṭhakathā / ṭīkā / abhinavaṭīkā）。
    一卷可能有两部新复注（如 188/189 各覆盖 cs 的前后半段），都会列出来。
    """
    rows = all_books()
    me = next((r for r in rows if r.get("book") == int(book)), None)
    if not me:
        return []
    vagga = {t for t in me.get("tags", []) if t not in NON_VAGGA_TAGS}
    out = []
    for r in rows:
        tags = set(r.get("tags", []))
        if not vagga <= tags:
            continue
        layer = next((LAYER_BY_TAG[t] for t in tags if t in LAYER_BY_TAG), None)
        if layer:
            out.append({"book": r["book"], "layer": layer,
                        "title": r.get("title", ""), "toc": r.get("toc", "")})
    out.sort(key=lambda x: ({"mula": 0, "atthakatha": 1, "tika": 2}[x["layer"]], x["book"]))
    return out


def cs_filled(book):
    """{段号: cs}，把段号对齐到**它所属那一章**的 cs。

    两个坑，都是实测踩出来的：
    · **章标题段带的是上一章的 cs**（如义注 103:1469「Tayo codanārahavaṇṇanā」标着
      cs 510，而它这一章的正文是 513–515）。照抄就会把整章判到上一章去，
      所以标题一律改取**后面第一段正文**的 cs。
    · 正文里没有 cs 的段（注释独有的插话、结语）是接着前面讲的，向**前**继承。
    """
    rows = paras(book)
    if rows and "cs_para" not in rows[0]:
        rows = paras(book, refresh=True)
    rows = sorted(rows, key=lambda x: x["paragraph"])
    body_cs = {x["paragraph"]: x.get("cs_para") for x in rows if x.get("level", 100) >= 100}

    nxt, fwd = None, {}
    for x in reversed(rows):                      # 每段之后的第一个正文锚点
        p = x["paragraph"]
        if body_cs.get(p) is not None:
            nxt = body_cs[p]
        fwd[p] = nxt

    out, last = {}, None
    for x in rows:
        p = x["paragraph"]
        if x.get("level", 100) < 100:             # 标题：跟后面的正文走
            out[p] = fwd.get(p)
        elif body_cs.get(p) is not None:
            out[p] = last = body_cs[p]
        else:                                     # 正文缺 cs：跟前面走
            out[p] = last
    return out


def cs_own(book):
    """{段号: cs}，只认正文段自己的 cs；标题段一律 None。判章节归属用它。"""
    rows = paras(book)
    return {x["paragraph"]: (x.get("cs_para") if x.get("level", 100) >= 100 else None)
            for x in rows}


def cs_set(book, lo, hi, csm=None, carry=True):
    """某本书 [lo, hi] 段里出现的 cs 值集合。

    `carry=True`（默认）：没有 cs 的段跟着**前一个 cs 锚点**走——切 chunk 时用这个，
    注释层独有的序论、结语夹在锚点之间，属于同一段释义，不能丢。

    `carry=False`：只算这些段**自己**的 cs。判「这一章注的是哪一章」必须用它——
    章标题段常常没有 cs，一旦向前继承，标题就会把上一章的 cs 带进来，
    整章被判给上一章（实测把义注的 `8. Mahāsīhanādasuttavaṇṇanā` 判给了上一经的末章）。
    """
    csm = csm or (cs_filled(book) if carry else cs_own(book))
    return {csm.get(p) for p in range(int(lo), int(hi) + 1) if csm.get(p) is not None}
