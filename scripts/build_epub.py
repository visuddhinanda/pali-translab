# -*- coding: utf-8 -*-
"""把导出的 markdown 合成 epub —— 一本书一个 epub，章节按段落顺序排。

顺序取自每个文件 frontmatter 里的 `paragraph_start`，不靠文件名排序，所以
文件名有没有 `[0118]` 前缀都不影响结果。目录层级取自 frontmatter 的 `path`：
`path` 有几层，这一章的标题就是几级标题，epub 的目录树跟着分层。

**frontmatter 一个字段都不丢**：书级信息（书名、语言、channel、模型）写进
epub 元数据；每章原样的 frontmatter 以 HTML 注释嵌在该章开头，读者看不见，
`unzip -p x.epub '*.xhtml' | grep pali-meta` 能原样取回。可见的那行摘要
（段范围 / 句数 / 导出日期）由 --meta 控制。

用法：
    python3 scripts/build_epub.py                          # 导出目录下每本书各一个 epub
    python3 scripts/build_epub.py --book "(DN) Sīlakkhandhavaggapāḷi"
    python3 scripts/build_epub.py --meta none --out dist   # 不要可见的章节摘要行
    python3 scripts/build_epub.py --merge                   # 四本合成一个 epub
    python3 scripts/build_epub.py --merge "我的书名"
    python3 scripts/build_epub.py --keep-md                # 保留中间 markdown，便于排错

需要 pandoc（`pandoc --version`）。
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)
FIELD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")


def parse_front_matter(text):
    """够用的 frontmatter 解析：一层 key: value，值是 JSON 就按 JSON 读。"""
    m = FM.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        f = FIELD.match(line)
        if not f:
            continue
        k, raw = f.group(1), f.group(2).strip()
        try:
            meta[k] = json.loads(raw)
        except json.JSONDecodeError:
            meta[k] = raw
    return meta, text[m.end():]


def load_chapters(book_dir):
    """收集一本书的全部章节，先按 book 分组、组内按起始段号排。

    两件事容易漏：
    · 书目录旁边还有一个同名的 `<书名>.md`，那是这本书的扉页（`path` 为空），
      它不在目录里，`os.walk` 收不到。
    · 一个导出目录可能装着**两部书**（复注与新复注同名，如 book 188 与 189）。
      段号各编各的，只按段号排会把两部书交错在一起，所以排序键要带上 book。
    """
    book_dir = book_dir.rstrip("/")
    parent, name = os.path.split(book_dir)
    paths = []
    # 扉页文件名可能带 [0003] 前缀（见 rename_export_paras.py），按后缀认
    for f in sorted(os.listdir(parent or ".")):
        if f.endswith(".md") and re.sub(r"^\[\d+\]\s+", "", f) == name + ".md":
            paths.append(os.path.join(parent, f))
    for dirpath, _, names in os.walk(book_dir):
        paths += [os.path.join(dirpath, n) for n in names if n.endswith(".md")]

    chs = []
    for p in paths:
        meta, body = parse_front_matter(open(p, encoding="utf-8").read())
        if "paragraph_start" not in meta:
            print(f"  跳过（没有 paragraph_start）{p}", file=sys.stderr)
            continue
        chs.append({"path": p, "meta": meta, "body": body})
    chs.sort(key=lambda c: (int(c["meta"].get("book", 0)),
                            int(c["meta"]["paragraph_start"]),
                            int(c["meta"].get("paragraph_end", 0))))
    return chs


def yaml_block(meta):
    """把书级元数据写成 pandoc 认得的 YAML；标量一律走 JSON 引号，省得被冒号噎住。"""
    lines = []
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                first = True
                for ik, iv in item.items():
                    lines.append(("  - " if first else "    ")
                                 + f"{ik}: {json.dumps(iv, ensure_ascii=False)}")
                    first = False
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return lines


def split_leading_heading(body):
    """摘走正文自带的首个标题（连同那句离线副本提示），返回 (标题文字, 余下正文)。

    标题级别不固定：导出脚本按面包屑深度给中文章名定级，书名页是 `#`、经是
    `##`、章是 `###`。这里**不限级别**只认第一个 `#{1,6} `——早先写死认 `"# "`，
    改了导出规则后 `## 中文章名` 剥不掉，于是每章多出一条巴利目录项。
    """
    out, title = [], ""
    for line in body.splitlines():
        m = re.match(r"#{1,6} +(.*)", line) if not title else None
        if m:
            title = m.group(1).strip()
            continue
        if line.startswith("> 本文是") and line.rstrip().endswith("离线副本。"):
            continue
        out.append(line)
    return title, "\n".join(out).strip("\n")


def chapter_md(ch, meta_mode, shift=0):
    m = ch["meta"]
    level = max(1, len(m.get("path", [])) or 1) + shift
    # 章标题用正文里的**中文**章名；frontmatter 的 title 是巴利名，只作后备
    # （旧规则导出的文件正文标题就是巴利名，取到的仍是它）。级别一律由这里
    # 按 path 深度重排，正文那行原有的级别不带过来。
    heading, body = split_leading_heading(ch["body"])
    lines = ["#" * level + " " + (heading or str(m.get("title", "untitled"))), ""]

    # 原样保留整份 frontmatter：HTML 注释，读者看不见，机器取得回
    raw = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in m.items())
    lines += [f"<!-- pali-meta\n{raw}\n-->", ""]

    if meta_mode == "line":
        lines += [f"*§{m.get('paragraph_start')}–{m.get('paragraph_end')} · "
                  f"{m.get('sentences', '?')} 句 · 导出 {m.get('exported_at', '')}*", ""]
    lines.append(body)
    return "\n".join(lines).rstrip() + "\n"


def build(book_dir, out_dir, meta_mode, keep_md, dry):
    name = os.path.basename(book_dir.rstrip("/"))
    chs = load_chapters(book_dir)
    if not chs:
        print(f"  {name}：没有可用章节，跳过", file=sys.stderr)
        return None

    head = chs[0]["meta"]
    total = sum(int(c["meta"].get("sentences", 0)) for c in chs)
    today = datetime.date.today().isoformat()

    book_meta = {
        "title": name,
        "lang": head.get("lang", "zh-Hans"),
        "creator": [{"role": "author", "text": f"{head.get('model', 'AI')}（机器翻译）"},
                    {"role": "publisher", "text": "WikiPali"}],
        "date": today,
        "rights": "译文正本在 WikiPali，本 epub 是离线副本",
        "description": ("book " + "/".join(sorted({str(c["meta"].get("book")) for c in chs},
                                                   key=lambda x: int(x)))
                        + f" · {len(chs)} 章 · {total} 句 · "
                        f"channel {head.get('channel')} ({head.get('channel_uid')})"),
        "source": head.get("source", "wikipali"),
    }

    parts = ["---", *yaml_block(book_meta), "---", ""]
    parts += [chapter_md(c, meta_mode) for c in chs]
    md = "\n".join(parts)

    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{name}.md")
    epub_path = os.path.join(out_dir, f"{name}.epub")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    cmd = ["pandoc", md_path, "-o", epub_path,
           "--from", "markdown+raw_html+yaml_metadata_block",
           "--toc", "--toc-depth=3", "--split-level=2",
           "--metadata", f"lang={book_meta['lang']}"]
    print(f"  {name}：{len(chs)} 章 / {total} 句 → {epub_path}")
    if dry:
        print("   ", " ".join(cmd))
        return epub_path
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stderr.strip():
        print("   ", r.stderr.strip(), file=sys.stderr)
    if r.returncode != 0:
        sys.exit(f"pandoc 失败：{name}")
    if not keep_md:
        os.remove(md_path)
    return epub_path


# 三层的阅读顺序：本文 → 义注 → 复注 → 复注的复注。按 book 号排正好是这个次序。
# 层级排序用的 tag：`wikipali books` 的书目 tag（本地缓存，见 _wp.all_books）
LAYER_RANK = {"mūla": 0, "aṭṭhakathā": 1, "ṭīkā": 2, "abhinavaṭīkā": 3}


def layer_key(chs):
    """合并时的排序键：**先层次后书号**——本文 → 义注 → 复注。

    不能只按书号：长部碰巧是 93(本文) < 103(义注) < 185(复注)，中部却是
    131(义注) < 165(本文) < 193(复注)，纯按书号会把义注排到本文前面。
    """
    book = int(chs[0]["meta"].get("book", 10**9))
    return (book_layer_rank(book), book)


def book_layer_rank(book):
    """书号 → 层级序号；查不到（离线、书目缺 tag）就退回 9，排在最后但不报错。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _wp import all_books
        row = next((r for r in all_books() if r.get("book") == book), None)
        if row:
            for t in row.get("tags", []):
                if t in LAYER_RANK:
                    return LAYER_RANK[t]
    except Exception as e:                       # 排序拿不到就降级，别拖垮打包
        print(f"  取 book {book} 的层级失败（{e}），按书号排", file=sys.stderr)
    return 9


def build_merged(book_dirs, out_dir, meta_mode, keep_md, dry, title):
    """四本书合成一个 epub：每本书是一级标题，它的章节整体下沉一级。"""
    books = []
    for d in book_dirs:
        chs = load_chapters(d)
        if chs:
            books.append((os.path.basename(d.rstrip("/")), chs))
        else:
            print(f"  {d}：没有可用章节，跳过", file=sys.stderr)
    if not books:
        sys.exit("一本可用的书都没有")
    books.sort(key=lambda b: layer_key(b[1]))

    head = books[0][1][0]["meta"]
    total = sum(int(c["meta"].get("sentences", 0)) for _, chs in books for c in chs)
    n_ch = sum(len(chs) for _, chs in books)

    book_meta = {
        "title": title,
        "lang": head.get("lang", "zh-Hans"),
        "creator": [{"role": "author", "text": f"{head.get('model', 'AI')}（机器翻译）"},
                    {"role": "publisher", "text": "WikiPali"}],
        "date": datetime.date.today().isoformat(),
        "rights": "译文正本在 WikiPali，本 epub 是离线副本",
        "description": (f"{len(books)} 部 · {n_ch} 章 · {total} 句 · book "
                        # 一个目录可能含两部书（188/189），要全列出来
                        + "/".join(sorted({str(c["meta"].get("book"))
                                           for _, chs in books for c in chs},
                                          key=lambda x: int(x)))
                        + f" · channel {head.get('channel')} ({head.get('channel_uid')})"),
        "source": head.get("source", "wikipali"),
    }

    parts = ["---", *yaml_block(book_meta), "---", ""]
    for name, chs in books:
        b = chs[0]["meta"].get("book")
        parts.append(f"# {name}\n")
        parts.append(f"<!-- pali-book\nbook: {b}\nchapters: {len(chs)}\n"
                     f"sentences: {sum(int(c['meta'].get('sentences', 0)) for c in chs)}\n-->\n")
        parts += [chapter_md(c, meta_mode, shift=1) for c in chs]
        print(f"  + {name}（book {b}）{len(chs)} 章 / "
              f"{sum(int(c['meta'].get('sentences', 0)) for c in chs)} 句")

    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{title}.md")
    epub_path = os.path.join(out_dir, f"{title}.epub")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    cmd = ["pandoc", md_path, "-o", epub_path,
           "--from", "markdown+raw_html+yaml_metadata_block",
           "--toc", "--toc-depth=3", "--split-level=2",
           "--metadata", f"lang={book_meta['lang']}"]
    print(f"  合并 {len(books)} 本：{n_ch} 章 / {total} 句 → {epub_path}")
    if dry:
        print("   ", " ".join(cmd))
        return epub_path
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stderr.strip():
        print("   ", r.stderr.strip(), file=sys.stderr)
    if r.returncode != 0:
        sys.exit("pandoc 失败（合并）")
    if not keep_md:
        os.remove(md_path)
    return epub_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="workspace/export", help="导出根目录（项目的在 workspace/projects/<name>/export）")
    ap.add_argument("--out", default="workspace/epub", help="epub 输出目录")
    ap.add_argument("--book", action="append", default=[],
                    help="只做这本（目录名）；可重复，默认全做")
    ap.add_argument("--meta", choices=["line", "none"], default="line",
                    help="章节开头是否显示一行摘要；完整 frontmatter 两种模式都会保留")
    ap.add_argument("--keep-md", action="store_true", help="保留合并后的中间 markdown")
    ap.add_argument("--merge", nargs="?", const="Sīlakkhandhavagga 四层合集", default=None,
                    help="把选中的书合成**一个** epub（可带书名，默认「Sīlakkhandhavagga 四层合集」）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if subprocess.run(["which", "pandoc"], capture_output=True).returncode != 0:
        sys.exit("找不到 pandoc")

    books = [os.path.join(args.root, b) for b in args.book] or sorted(
        os.path.join(args.root, d) for d in os.listdir(args.root)
        if os.path.isdir(os.path.join(args.root, d)))
    if not books:
        sys.exit(f"{args.root} 下没有书目录")

    if args.merge:
        made = [build_merged(books, args.out, args.meta, args.keep_md, args.dry_run, args.merge)]
    else:
        made = [build(b, args.out, args.meta, args.keep_md, args.dry_run) for b in books]
    made = [m for m in made if m]
    print(f"{'（试跑）' if args.dry_run else ''}共生成 {len(made)} 个 epub → {args.out}/")


if __name__ == "__main__":
    main()
