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
    """收集一本书的全部章节，按起始段号排序。"""
    chs = []
    for dirpath, _, names in os.walk(book_dir):
        for n in names:
            if not n.endswith(".md"):
                continue
            p = os.path.join(dirpath, n)
            meta, body = parse_front_matter(open(p, encoding="utf-8").read())
            if "paragraph_start" not in meta:
                print(f"  跳过（没有 paragraph_start）{p}", file=sys.stderr)
                continue
            chs.append({"path": p, "meta": meta, "body": body})
    chs.sort(key=lambda c: (int(c["meta"]["paragraph_start"]),
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


def strip_leading_heading(body, title):
    """去掉正文自带的 `# 标题` 与那句离线副本提示——标题由本脚本按层级重排。"""
    out, dropped_h1 = [], False
    for line in body.splitlines():
        if not dropped_h1 and line.startswith("# "):
            dropped_h1 = True
            continue
        if line.startswith("> 本文是") and line.rstrip().endswith("离线副本。"):
            continue
        out.append(line)
    return "\n".join(out).strip("\n")


def chapter_md(ch, meta_mode):
    m = ch["meta"]
    level = max(1, len(m.get("path", [])) or 1)
    lines = ["#" * level + " " + str(m.get("title", "untitled")), ""]

    # 原样保留整份 frontmatter：HTML 注释，读者看不见，机器取得回
    raw = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in m.items())
    lines += [f"<!-- pali-meta\n{raw}\n-->", ""]

    if meta_mode == "line":
        lines += [f"*§{m.get('paragraph_start')}–{m.get('paragraph_end')} · "
                  f"{m.get('sentences', '?')} 句 · 导出 {m.get('exported_at', '')}*", ""]
    lines.append(strip_leading_heading(ch["body"], m.get("title", "")))
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
        "description": (f"book {head.get('book')} · {len(chs)} 章 · {total} 句 · "
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="workspace/export", help="导出根目录")
    ap.add_argument("--out", default="workspace/epub", help="epub 输出目录")
    ap.add_argument("--book", action="append", default=[],
                    help="只做这本（目录名）；可重复，默认全做")
    ap.add_argument("--meta", choices=["line", "none"], default="line",
                    help="章节开头是否显示一行摘要；完整 frontmatter 两种模式都会保留")
    ap.add_argument("--keep-md", action="store_true", help="保留合并后的中间 markdown")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if subprocess.run(["which", "pandoc"], capture_output=True).returncode != 0:
        sys.exit("找不到 pandoc")

    books = [os.path.join(args.root, b) for b in args.book] or sorted(
        os.path.join(args.root, d) for d in os.listdir(args.root)
        if os.path.isdir(os.path.join(args.root, d)))
    if not books:
        sys.exit(f"{args.root} 下没有书目录")

    made = [build(b, args.out, args.meta, args.keep_md, args.dry_run) for b in books]
    made = [m for m in made if m]
    print(f"{'（试跑）' if args.dry_run else ''}共生成 {len(made)} 个 epub → {args.out}/")


if __name__ == "__main__":
    main()
