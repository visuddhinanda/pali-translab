# -*- coding: utf-8 -*-
"""wikipali CLI 的共用薄封装。只依赖标准库。

本项目所有数据读写都经 wikipali 插件的 `wikipali` 命令，不直连 HTTP、不读本地语料。
"""
import bisect
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time

# _System_Pali_VRI_ 的 uid 各服务器不同（本地开发机是 f4d07a00-…），读别的服务器时用环境变量换
PALI_UID = os.environ.get("WIKIPALI_PALI_UID") or "00b577c0-13b9-11ee-a05a-b7307efd9ee6"
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
    """跑一条 wikipali 命令并解析 JSON。读操作默认带重试。

    空输出是「确实没有」，返回 []；**解析不了就报错退出，不当空**——
    当空会让上层把读坏了误判成「没有译文」，记成 skip 永久跳过。
    """
    out = run(list(args), retries=retries).stdout
    try:
        return json.loads(out or "[]")
    except json.JSONDecodeError:
        sys.exit(f"wikipali {' '.join(args[:2])} 返回的不是 JSON：{out[:200]!r}")


GET_LIMIT = 1000   # `wikipali get` 一次最多返回几行（句 × channel）；CLI 默认只有 200


def toc_rows(book, para, depth=7):
    """`wikipali toc --json` 的目录项，统一成旧格式 `{book, paragraph, toc, level}`。

    0.29.0 起 CLI 改了输出：`paragraph`→`para`、`toc`→`title`，level 整体小 1；
    `--depth` 上限也收紧到 7（传 9 服务端回 422）。新旧两种都认，调用方只看旧字段。
    """
    out = []
    for t in jget("toc", f"{book}:{para}", "--json", "--depth", str(min(depth, 7))) or []:
        if "paragraph" in t:
            out.append(t)
        else:
            out.append({**t, "paragraph": t["para"], "toc": t.get("title") or "",
                        "level": int(t["level"]) + 1})
    return out


def get_rows(book, paras, channels=(), batch=20):
    """按段取句子（`wikipali get`），**返回行数顶到上限就对半拆了重取**。

    `wikipali get` 按 `--limit` 截断、不报错，默认 200 行。以前各处不传它：
    一批 20 段 × (巴利 + nissaya + 译文) 超过约 66 句，批尾的段就被静默丢掉——
    kn5 的 H7 统稿只看到 193 句里的 100 句，整本读回核对一轮丢 201 段。
    所有按段取句子的地方都走这里。
    """
    chan = [a for uid in channels for a in ("--channel", uid)]

    def get(ps):
        got = jget("get", *[f"{book}:{p}" for p in ps], "--json",
                   "--limit", str(GET_LIMIT), *chan) or []
        if len(got) < GET_LIMIT:
            return got
        if len(ps) == 1:
            sys.exit(f"wikipali get {book}:{ps[0]} 单段就有 ≥{GET_LIMIT} 行，可能被截断——调大 GET_LIMIT")
        mid = len(ps) // 2
        return get(ps[:mid]) + get(ps[mid:])

    paras = list(paras)
    rows = []
    for i in range(0, len(paras), batch):
        rows += get(paras[i:i + batch])
    return rows


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

    锚点必须取自书目表（见 book_roots），**不能写死 `<book>:3`**。
    """
    key = int(book)
    if refresh or key not in _PARAS_CACHE:
        cache = f"workspace/cache_paras_{key}.json"
        if not refresh and os.path.exists(cache):
            _PARAS_CACHE[key] = json.load(open(cache, encoding="utf-8"))
        else:
            rows, seen = [], set()
            for root in book_roots(key):
                for r in jget("paras", f"{key}:{root}", "--body", "--json"):
                    if r["paragraph"] not in seen:
                        seen.add(r["paragraph"])
                        rows.append(r)
            rows.sort(key=lambda r: r["paragraph"])
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


# 句子表（pali_sentences）的离线导出：book,paragraph,sentences。
# 真实句数是分块的**正主**——模型一次吐约 100 行 JSONL 就被输出上限截断，
# 截断一次整块白跑。字符数只是它的代理，相关但不精确（偈颂句短、长行注释句长）。
# 这份数据从数据库一次导出（见 README 的 SQL），放在这里跨项目共用；
# 没有它就退回「字符数 + 段数」的老办法。
SENT_CSV = "workspace/cache_sent_counts.csv"
_SENTS_CACHE = {}


def para_sents(book):
    """{段号: 句子数}——来自句子表的离线导出；没有那份 CSV 就返回 {}。"""
    key = int(book)
    if not _SENTS_CACHE:
        if not os.path.exists(SENT_CSV):
            _SENTS_CACHE["_missing"] = True
            return {}
        import csv as _csv
        with open(SENT_CSV, encoding="utf-8-sig", newline="") as f:
            for row in _csv.DictReader(f):
                b = int(row["book"])
                _SENTS_CACHE.setdefault(b, {})[int(row["paragraph"])] = int(row["sentences"])
    return _SENTS_CACHE.get(key, {})


def have_sent_counts():
    """句数数据在不在——规划期据此决定要不要再用段数兜底。"""
    para_sents(0)                     # 触发一次加载
    return not _SENTS_CACHE.get("_missing", False)


def chunk_paras(book, plist, budget=3500, max_paras=12, max_sents=0):
    """按巴利字符数、句数与段数切 chunk。**纯本地计算，不调任何接口。**

    三条上限，哪条先到按哪条切：
      · budget      本块的巴利字符数上限
      · max_sents   本块的句数上限（>0 且有句数数据时生效）。这是真约束——
                    模型一次约 100 行 JSONL 就被输出上限截断
      · max_paras   段数上限，<=0 为不限。**只在没有句数数据时**才需要它兜底：
                    那时句数无从约束，段数是唯一能防住「块里句子太多」的粗代理

    单段自己就超限（长偈颂整段上百句）时不拆段——段是坐标的最小单位，拆了
    坐标就对不上。那种段单独成块，执行器自己分几次调用写同一个 task。
    """
    plist = [int(p) for p in plist]
    chars = para_chars(book)
    sents = para_sents(book) if max_sents > 0 else {}
    chunks, cur, size, nsent = [], [], 0, 0
    for p in plist:
        n = chars.get(p, 0)
        if n == 0:
            continue
        sn = sents.get(p, 0)
        full = (size + n > budget
                or (max_paras > 0 and len(cur) >= max_paras)
                or (max_sents > 0 and sn and nsent + sn > max_sents))
        if cur and full:
            chunks.append(cur); cur, size, nsent = [], 0, 0
        cur.append(p); size += n; nsent += sn
    if cur:
        chunks.append(cur)
    return chunks


# ── 跨层书目与 cs 映射 ─────────────────────────────────────────────────
# `wikipali related` 是**段级**接口：一次一段、约 1.5 秒往返。用它做全书规划要
# 每章问一次（一卷 150 多次 ≈ 4 分钟），而它给的段级对应边界还会错位。
# 全书级的事情一律改用 `books`（一次拿到同一卷的各层书号）+ `cs_para`（跨书通用的
# 典藏段号）。related 只留给单段翻译时临时找对应。

# 注释层的链条：父层 = 链上前一个**在场**的层。
# 经藏走 mula → atthakatha → tika，论藏走 mula → atthakatha → mulatika → anutika，
# 两者都是这条链的子集，所以「父层」不必按藏别写死，沿链回退即可。
LAYER_CHAIN = ["mula", "atthakatha", "tika", "mulatika", "anutika"]
LAYER_ORDER = {n: i for i, n in enumerate(LAYER_CHAIN)}

# tag → 层次。**按这个顺序匹配，先中先得**：论藏的 mūlaṭīkā / anuṭīkā 两种书
# 都同时带着 `ṭīkā` 这个通用 tag，先看专名才分得开。
# purāṇaṭīkā / abhinavaṭīkā 是同一层的新旧两个注本（**并列**，不是上下层），都归 tika。
LAYER_TAG_RULES = [("mūla", "mula"), ("aṭṭhakathā", "atthakatha"),
                   ("mūlaṭīkā", "mulatika"), ("anuṭīkā", "anutika"),
                   ("purāṇaṭīkā", "tika"), ("abhinavaṭīkā", "tika"), ("ṭīkā", "tika")]
LAYER_BY_TAG = dict(LAYER_TAG_RULES)
# 这些 tag 说的是"哪一层"或"什么体裁"，不是"哪一卷"，配对时要排除。
# 漏一个层次 tag，它就会被当成卷名参与配对，同卷的其它层全被排除掉
#（实测 mūlaṭīkā 不在这里时，layer_books(172) 只能看到它自己）。
NON_VAGGA_TAGS = set(LAYER_BY_TAG) | {"pāḷi", "sutta", "vinaya", "abhidhamma", "añña"}


def _vagga_tags(tags):
    """一本书的**卷级** tag：去掉层次、体裁，以及 `…pāḷi` 这类**书名** tag。

    书名 tag 只挂在本文上（yamakapāḷi 挂在 78/79/80，注释书没有），当成卷名参与
    `vagga <= tags` 判定，同卷的注释书就全被排除——实测 yamaka 与 paṭṭhāna
    两部论因此完全找不到义注与复注。
    """
    return {t for t in tags
            if t not in NON_VAGGA_TAGS and not (t.endswith("pāḷi") and t != "pāḷi")}


# 专名 tag 是可靠的；只剩一个泛 `ṭīkā` 时它什么也没说明，这时看书名。
# 书目表里有五行就是这种残缺（207 的两部 pātimokkhapāḷi 与 Kaṅkhāvitaraṇī 义注、
# 180 的 Abhidhammamātikāpāḷi 与 Mohavicchedanī）：本文没挂 `mūla`、义注没挂
# `aṭṭhakathā`，全都只有 `ṭīkā`，照 tag 判会把一整卷五部作品统统当成复注，
# 于是没有本文也没有义注，父层链整条断掉。
SPECIFIC_LAYER_TAGS = {"mūla", "aṭṭhakathā", "mūlaṭīkā", "anuṭīkā",
                       "purāṇaṭīkā", "abhinavaṭīkā"}
# 书名里的层次线索，按顺序先中先得。`aṭṭhakathā` 要先于 `ṭīkā`：
# `Kaṅkhāvitaraṇī-aṭṭhakathā` 两个词都占，先看义注才不会判成复注。
LAYER_NAME_RULES = [("aṭṭhakathā", "atthakatha"), ("purāṇaṭīkā", "tika"),
                    ("abhinavaṭīkā", "tika"), ("ṭīkā", "tika"),
                    ("pāḷi", "mula"), ("pāṭha", "mula")]


def layer_by_name(*names):
    """按书名/toc 判层次。只在 tag 只剩泛 `ṭīkā` 时用，判不出就 None。"""
    s = " ".join(n for n in names if n).lower()
    return next((lay for key, lay in LAYER_NAME_RULES if key in s), None)


def layer_of(tags, name="", toc=""):
    """一组 tag 属于哪一层；不是任何注释层就给 None。

    专名 tag 优先。只有泛 `ṭīkā` 时改看书名（见 LAYER_NAME_RULES）——这一步只
    影响书目表 tag 残缺的那五行，其余 184 行都有专名 tag，判定与从前一字不差。
    """
    tags = set(tags)
    lay = next((lay for tag, lay in LAYER_TAG_RULES if tag in tags), None)
    if lay == "tika" and not (tags & SPECIFIC_LAYER_TAGS):
        return layer_by_name(name, toc) or lay
    return lay


def layer_of_row(row):
    """书目表一行属于哪一层——`layer_of` 的入口，连书名一起看。"""
    return layer_of(set(row.get("tags") or ()),
                    row.get("title") or "", row.get("toc") or "")


def parent_layer(layer, present):
    """`layer` 的父层：链上排在它前面、且在 `present` 里的最后一个层。没有就 None。"""
    if layer not in LAYER_ORDER:
        return None
    present = set(present)
    for name in reversed(LAYER_CHAIN[:LAYER_ORDER[layer]]):
        if name in present:
            return name
    return None
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


def book_roots(book):
    """该 book 号下每部书的**根段号**，来自书目表自带的 `paragraph`。

    两个理由不能写死 `<book>:3`：
    · 根段号本来就不都是 3（96 dhammasaṅgaṇī-aṭṭhakathā 是 4）。给正文段时
      `paras` 只回它自己一行，插件便向上找章节，服务端对它的父段回 -1，
      于是请求 `v2/palitext/96--1` → HTTP 500，整本书取不到段表。
    · 一个 book 号可能挂着好几部书（98 是五部论义注的合本，各部一条书目），
      整本的段表是这些根段各自那一章的并集。
    """
    ps = sorted({int(r["paragraph"]) for r in all_books()
                 if r.get("book") == int(book) and r.get("paragraph") is not None})
    return ps or [3]


def book_works(book):
    """一本书里的全部**作品**（work）：[(起段, 止段, 卷名, 族)]，按段号排序。

    书目表（`wikipali books`）的一行就是一个 work：book 209 的六行是六部作品
    （`209:3` 序论、`209:166` Pārājika 注、`209:992` Mahāvagga 注…），各属不同卷族。
    止段 = 同一本书里下一行的段号 - 1；最后一行到书末。
    **规划的单位是 work，不是 book** —— 按 book 规划会把别卷的注释一起拉进来。
    """
    rows = sorted((x for x in all_books()
                   if x.get("book") == int(book) and x.get("paragraph") is not None),
                  key=lambda x: int(x["paragraph"]))
    out = []
    for i, x in enumerate(rows):
        lo = int(x["paragraph"])
        hi = int(rows[i + 1]["paragraph"]) - 1 if i + 1 < len(rows) else 10 ** 9
        out.append((lo, hi, x.get("toc") or x.get("title") or "",
                    (x.get("related_name") or "").split("_")[0]))
    return out


def layer_works(book, para=None):
    """与某个 work 同族的各层作品：[{layer, book, start, end, title, fam}]，含它自己。

    族看书目表的 **related_name**（`vin1`、`an2`…），不看 tag：律藏的复注与本文
    **不共享卷级 tag**（204/205/210 的 tags 里没有 `pārājika`），按 tag 判同卷会把
    三部复注漏掉。related_name 是书目表给出的权威族标记。

    **同一层可以有多个 work**：律藏一卷常有并列的几部复注（vin1 有
    `Sāratthadīpanī` 两段 + `Vajirabuddhi` + `Vimativinodanī` 共四部五个 work），
    它们各自注同一部义注，彼此是并列关系、不该互相统一。
    经藏一层一个 work，退化成原来的样子。
    """
    rows = all_books()
    mine = [x for x in rows if x.get("book") == int(book)]
    if para is not None:
        mine = [x for x in mine if int(x.get("paragraph") or 0) <= int(para)] or mine
        mine = mine[-1:]
    fam = ((mine[0].get("related_name") if mine else "") or "").split("_")[0]
    out = []
    for r in rows:
        lay = layer_of_row(r)
        if not lay:
            continue
        f = (r.get("related_name") or "").split("_")[0]
        if fam and f != fam:
            continue
        lo = int(r.get("paragraph") or 0)
        hi = 10 ** 9
        for a, b, _t, _f in book_works(r["book"]):
            if a == lo:
                hi = b
                break
        out.append({"layer": lay, "book": r["book"], "start": lo, "end": hi,
                    "title": r.get("toc") or r.get("title") or "", "fam": f})
    out.sort(key=lambda x: (LAYER_ORDER.get(x["layer"], 99), x["book"], x["start"]))
    return out


def layer_segments(book):
    """与 `book` 同卷的各注释书，**连它在这一卷里的段范围**：
    {注释书号: (layer, title, 起段, 止段)}。

    增支部一本注释书含好几集（book 100 的三行书目分别是 an2/an3/an4），
    整本拉进来就会把别集的注释也当成本集的——相应部那种一集一本的书不会暴露这个问题。
    划界靠书目表的 `related_name`：取与本文同族的那一行（an2 ↔ an2_A），
    止段是同一本书里下一行的段号减一；只有一行就是整本。
    """
    rows = all_books()
    me = next((r for r in rows if r.get("book") == int(book)), None)
    fam = (me or {}).get("related_name") or ""
    fam = fam.split("_")[0]
    out = {}
    for r in layer_books(book):
        b = r["book"]
        if b == int(book):
            continue
        same = sorted((x for x in rows if x.get("book") == b
                       and x.get("paragraph") is not None),
                      key=lambda x: int(x["paragraph"]))
        mine = [i for i, x in enumerate(same)
                if ((x.get("related_name") or "").split("_")[0]) == fam]
        if not mine or len(same) == 1:
            out[b] = (r["layer"], r["title"], 0, 10 ** 9)
            continue
        i = mine[0]
        lo = int(same[i]["paragraph"])
        hi = int(same[i + 1]["paragraph"]) - 1 if i + 1 < len(same) else 10 ** 9
        out[b] = (r["layer"], r["title"], lo, hi)
    return out


def layer_books(book):
    """与 `book` 同卷的各层书：[{book, layer, title, toc}]，含它自己。

    判定方式：同卷 = 共享全部"卷级 tag"（如 dīghanikāya + sīlakkhandhavagga）；
    层次 = 该书的层级 tag（mūla / aṭṭhakathā / ṭīkā / abhinavaṭīkā）。
    一卷可能有两部新复注（如 188/189 各覆盖 cs 的前后半段），都会列出来。
    论藏是**四层**（mūla → aṭṭhakathā → mūlaṭīkā → anuṭīkā），见 LAYER_CHAIN。
    """
    rows = all_books()
    me = next((r for r in rows if r.get("book") == int(book)), None)
    if not me:
        return []
    vagga = _vagga_tags(me.get("tags", []))
    out = []
    for r in rows:
        tags = set(r.get("tags", []))
        if not vagga <= tags:
            continue
        layer = layer_of_row(r)
        if layer:
            out.append({"book": r["book"], "layer": layer,
                        "title": r.get("title", ""), "toc": r.get("toc", "")})
    out.sort(key=lambda x: (LAYER_ORDER.get(x["layer"], 99), x["book"]))
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

    # · **离群值当没有 cs**：前后锚点彼此有序、它却落在两者之外，就是录入坏了
    #   （经集义注 125:122 注第 10–13 偈，cs 却是 44117，会被并进全书最后一组统稿）。
    #   只在前 ≤ 后时判，cs 按品重计（如事品每品从 1 起）的回落不受影响。
    anchors = [p for p in sorted(body_cs) if body_cs[p] is not None]
    for i in range(1, len(anchors) - 1):
        a, v, b = (body_cs[anchors[j]] for j in (i - 1, i, i + 1))
        if a is not None and b is not None and a <= b and not a <= v <= b:
            body_cs[anchors[i]] = None

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


# ── 学处键：cs_para 当不成跨层坐标时的替代 ───────────────────────────
# 律藏 pātimokkha 一族（related_name=vin6，book 207 的两部本文与 Kaṅkhāvitaraṇī 义注、
# book 212 的新旧两部复注）的 cs_para 是坏的，三种坏法都占齐了：
#   · 本文的 cs 其实是**学处序号**，每个犍度从 1 重来（僧残 13 / 不定 2 / 舍堕 30 /
#     波逸提 92 / 悔过 4 / 众学 75），跨犍度不唯一；
#   · Kaṅkhāvitaraṇī 义注 1135 段的 cs **全是同一个值 75**，零信息；
#   · purāṇaṭīkā 整部 543 段一个 cs 都没有，abhinavaṭīkā 只有末尾附录那 61 段有。
# 于是按 cs 配层必然全空。可用的替代坐标是目录自己给出的
# **(比丘/比丘尼分, 犍度, 犍度内学处序号)**：
#   · 注释层逐学处立标题（`1. Sukkavissaṭṭhisikkhāpadavaṇṇanā`），三部注名字一字不差；
#   · 本文没有逐学处标题，但它的 cs 就是学处序号，犍度由 `Saṅghādisesuddeso` 这一级给出。
# 舍堕与波逸提下面还有品（vagga），序号在品内从 1 重来，要按品的大小累加成犍度内连续号——
# 品的大小不写死，从同族**注得最全**的那部注的目录里数出来（见 rule_sizes）。

# 犍度词干 → 代号。**顺序要紧**：`Nissaggiyapācittiyā` 两个词干都占，先看舍堕；
# `Suddhapācittiyā` 只含 `pācittiy`，所以泛的那条排在后面。
KANDA_STEMS = [("nissaggiy", "NIS"), ("suddhapācittiy", "PAC"), ("pārājik", "PAR"),
               ("saṅghādises", "SAN"), ("aniyat", "ANI"), ("pācittiy", "PAC"),
               ("pāṭidesanīy", "PAT"), ("sekhiy", "SEK"), ("adhikaraṇasamath", "ADH")]
RULE_NO_RE = re.compile(r"^\s*(\d+)")


def _kanda_of(toc):
    """这个标题是不是犍度标题。

    **带序号的一律不算**——`1. Paṭhamapārājikavaṇṇanā` 里也有 `pārājik`，
    不排掉它就会把一条学处当成一个犍度，整个犍度的段全判错。
    """
    if RULE_NO_RE.match(toc):
        return None
    s = toc.lower()
    return next((v for k, v in KANDA_STEMS if k in s), None)


def _is_vagga(toc):
    """带序号的品标题（`1. Cīvaravaggo`）；不带序号的品标题当普通小节。"""
    return bool(RULE_NO_RE.match(toc)) and "vagg" in toc.lower()


def _vibh_switch(toc):
    """这个标题把后文切到哪一分：比丘尼 / 比丘 / 不切。

    比丘尼在前判——`Bhikkhunīpātimokkhavaṇṇanā` 里也含 `bhikkhu`。
    注释层只在比丘尼分之前立一个 `Bhikkhupātimokkhavaṇṇanā`，有的注干脆不立，
    所以默认是比丘分，遇到比丘尼标题才翻过去。
    """
    s = toc.lower()
    if "pātimokkha" not in s and "vibhaṅga" not in s:
        return None
    if "bhikkhunī" in s or "bhikkhuni" in s:
        return "BI"
    return "BU" if "bhikkhu" in s else None


def toc_walk(book, lo, hi):
    """走一遍某 work 的目录，给每个**正文段**标上 `(vibh, kanda, vagga, 印刷序号)`。

    层级不看 `level` 的数值（各书不一致：同一类标题在 207 是 L4、在 212 是 L4/L5），
    只看标题文字的语义，四种标题各管一件事，见上面那三个判定函数。

    返回 `(marks, has_rule_headings)`。`has_rule_headings` 说明这个 work 自己
    有没有逐学处标题：有就按目录数序号（注释层），没有就得退回 cs（本文层）。
    """
    vibh, kanda, vagga, no, has = "BU", None, None, None, False
    marks = {}
    for r in sorted(paras(book), key=lambda x: x["paragraph"]):
        p = r["paragraph"]
        if not (lo <= p <= hi):
            continue
        if (r.get("level") or 100) >= 100:
            marks[p] = (vibh, kanda, vagga, no)
            continue
        toc = r.get("toc") or ""
        sw = _vibh_switch(toc)
        if sw:
            vibh, kanda, vagga, no = sw, None, None, None
            continue
        k = _kanda_of(toc)
        if k:
            kanda, vagga, no = k, None, None
            continue
        if _is_vagga(toc):
            vagga, no = int(RULE_NO_RE.match(toc).group(1)), None
            continue
        m = RULE_NO_RE.match(toc)
        # 光一个序号、后面没有名字的标题不是学处（abhinavaṭīkā 末尾的结颂附录就是
        # `1.` `2.` … `18.` 这样十八条）。把它们当学处会凭空给犍度加满一批序号，
        # 本文那边的学处就被配到附录上去了。
        if m and re.search(r"\w", toc[m.end():].strip(". 　")):
            no, has = int(m.group(1)), True
    return marks, has


def rule_sizes(spans):
    """同族各 work 合起来数出的品内学处数：`{(vibh, kanda, vagga): 学处数}`。

    一部注常只注其中一段：purāṇaṭīkā 的波逸提直接从第 4 品起头（前三品不注），
    所以品的大小取各 work 印刷序号的**最大值**——谁注得全就用谁的。
    没有品的犍度（波罗夷、僧残、不定、悔过、众学）不进这张表，序号本来就是犍度内连续的。
    """
    sizes = {}
    for book, lo, hi in spans:
        marks, has = toc_walk(book, lo, hi)
        if not has:
            continue
        for _p, (v, k, vg, no) in marks.items():
            if k is None or vg is None or no is None:
                continue
            key = (v, k, vg)
            sizes[key] = max(sizes.get(key, 0), no)
    return sizes


def rule_counts(spans, sizes):
    """`{(vibh, kanda): 该犍度的学处总数}`——各品之和，没有品的犍度取最大印刷序号。

    这张表有两个用处：把品内序号摊平成犍度内连续号，以及给本文的 cs **定上界**。
    上界是必需的：wikipali 的段里，一个犍度的结颂常排在下一个犍度的标题之后，
    那几段会带着上一个犍度的 cs（实测不定法头三段带着僧残的 cs 13，而不定只有 2 条）。
    超过上界就判成对不上，宁可少给父层对照，也不能把段配到别的学处上去。
    """
    counts = {}
    for (v, k, _vg), n in sizes.items():
        counts[(v, k)] = counts.get((v, k), 0) + n
    for book, lo, hi in spans:
        marks, has = toc_walk(book, lo, hi)
        if not has:
            continue
        for _p, (v, k, vg, no) in marks.items():
            if k is None or vg is not None or no is None:
                continue
            counts[(v, k)] = max(counts.get((v, k), 0), no)
    return counts


def flat_no(vibh, kanda, vagga, no, sizes):
    """品内序号 → 犍度内连续序号。品号是印刷出来的，所以**跳品也算得对**
    （purāṇaṭīkā 从第 4 品起头，基数照样是前三品之和）。"""
    if no is None:
        return None
    if vagga is None:
        return no
    base = sum(n for (v, k, vg), n in sizes.items()
               if v == vibh and k == kanda and vg < vagga)
    return base + no


# cs_para 是 CS 典藏的段号，实际从没超过四位数（Pārājikapāḷi 到 662、
# 它的义注到 660）。44053、22313 这种是脏值，判重启前先剔掉，不然一个脏值
# 就制造一次下跌，好书也会被判成重启。
CS_SANE_MAX = 10000


def cs_runs(vals):
    """cs 序列里有几段非递减——即「从头重编过几次」。脏值先剔掉。

    每段从头重编都意味着这串数不是跨书唯一的坐标。几次算重启，看实测：
    律藏 vin1 一族最多 3 段（Vimativinodanī 从比丘波罗夷注到波逸提，换了本文书，
    段号自然从 1 重来；Sāratthadīpanī 3 段同理），而 pātimokkha 本文是 **7 段**
    （七个犍度各自从 1 编号，因为那其实是学处序号不是段号）。
    """
    g = [v for v in vals if v < CS_SANE_MAX]
    return (1 if g else 0) + sum(1 for a, b in zip(g, g[1:]) if b < a)


def cs_usable(book, lo, hi):
    """这个 work 的 cs_para 能不能当跨层坐标。三条都要过：

      · 有 cs 的正文段 ≥ 20%——注释层本来就有大段没有 cs（义注 138 只有 75%、
        Sāratthadīpanī 只有 51%，照样够用），但整部一个都没有就没得谈
        （purāṇaṭīkā 与 Vajirabuddhi 序论都是 0%）；
      · 取值不止一个（Kaṅkhāvitaraṇī 义注 1135 段全是同一个值 75，零信息）；
      · 非递减段 ≤ 3，即没有反复从头重编（见 `cs_runs`）。

    判定是**族级**的，不是单 work 的（见 plan_scan.build_anchors）：坐标体系必须
    全族统一，父层用 cs、子层用学处键，一条也配不上。
    """
    rows = [r for r in paras(book)
            if lo <= r["paragraph"] <= hi and (r.get("level") or 100) >= 100]
    if not rows:
        return False
    vals = [r.get("cs_para") for r in sorted(rows, key=lambda x: x["paragraph"])]
    got = [v for v in vals if v is not None]
    if len(got) < 0.2 * len(vals) or len(set(got)) < 2:
        return False
    return cs_runs(got) <= 3


def work_anchors(book, lo, hi, sizes=None, counts=None, use_cs=True):
    """某 work 的跨层坐标：`{段号: key}`，key 可比较、可跨 work。

    `use_cs` 为真就是 `("cs", cs)`（标题跟后面的正文、缺 cs 的正文跟前面，
    同 `cs_filled`）；为假就改成 `("rule", 分, 犍度, 犍度内学处序号)`。
    对不上的段给 None。该用哪种由调用方按**族**决定，不在这里单 work 决定。
    """
    if use_cs:
        csf = cs_filled(book)
        return {p: (("cs", csf[p]) if csf.get(p) is not None else None)
                for p in csf if lo <= p <= hi}
    marks, has = toc_walk(book, lo, hi)
    sizes = sizes or {}
    counts = counts or {}
    own = cs_own(book) if not has else {}
    out = {}
    for p, (v, k, vg, no) in marks.items():
        n = flat_no(v, k, vg, no, sizes) if has else own.get(p)
        lim = counts.get((v, k))
        out[p] = ("rule", v, k, n) if (k and n and lim and n <= lim) else None
    return out
