# -*- coding: utf-8 -*-
"""给已导出的 markdown 文件名加上起始段号前缀，让目录里的顺序等于段落顺序。

    Adhiccasamuppannavādo.md   →   [0118] Adhiccasamuppannavādo.md

段号取自文件自己的 frontmatter `paragraph_start`，不是猜的。**一次性工具**：
`export_markdown.py` 已经改成导出时就带前缀，这个脚本只用来修既有的那批文件。

为什么补零：文件管理器与 pandoc 都按字符串排序，`[1000]` 会排在 `[118]` 前面。
默认按全书最大段号的位数补零；真想要 `[118]` 这种写法就 `--pad 0`。

用法：
    python3 scripts/rename_export_paras.py --dry-run          # 先看要改什么
    python3 scripts/rename_export_paras.py
    python3 scripts/rename_export_paras.py --dirs             # 目录名也加前缀
    python3 scripts/rename_export_paras.py --strip            # 反悔了，去掉前缀
"""
import argparse
import os
import re
import sys

FM_START = re.compile(r"^paragraph_start:\s*(\d+)\s*$", re.M)
PREFIX = re.compile(r"^\[(\d+)\]\s+")


def start_para(path):
    """读 frontmatter 的 paragraph_start；没有就返回 None。"""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(2000)
    except OSError:
        return None
    m = FM_START.search(head)
    return int(m.group(1)) if m else None


def md_files(root):
    for dirpath, _, names in os.walk(root):
        for n in sorted(names):
            if n.endswith(".md"):
                yield os.path.join(dirpath, n)


def rename(old, new, dry):
    if old == new:
        return False
    if os.path.exists(new):
        print(f"  跳过（目标已存在）{new}", file=sys.stderr)
        return False
    print(f"  {os.path.basename(old)}  →  {os.path.basename(new)}")
    if not dry:
        os.rename(old, new)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="workspace/export", help="导出根目录")
    ap.add_argument("--pad", type=int, default=-1,
                    help="段号补零位数；-1=按全书最大段号自动，0=不补零")
    ap.add_argument("--dirs", action="store_true",
                    help="目录名也加前缀（取目录下最小的起始段号）")
    ap.add_argument("--strip", action="store_true", help="去掉前缀，恢复原名")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        sys.exit(f"找不到导出目录：{args.root}")

    files = list(md_files(args.root))
    if not files:
        sys.exit(f"{args.root} 下没有 .md 文件")

    if args.strip:
        n = 0
        for p in files:
            d, b = os.path.split(p)
            n += rename(p, os.path.join(d, PREFIX.sub("", b)), args.dry_run)
        print(f"{'（试跑）' if args.dry_run else ''}去掉前缀 {n} 个文件")
        return

    starts = {p: start_para(p) for p in files}
    missing = [p for p, s in starts.items() if s is None]
    for p in missing:
        print(f"  跳过（frontmatter 里没有 paragraph_start）{p}", file=sys.stderr)

    known = {p: s for p, s in starts.items() if s is not None}
    if not known:
        sys.exit("一个文件都读不到 paragraph_start，什么都没做")

    pad = args.pad if args.pad >= 0 else len(str(max(known.values())))
    n = 0
    for p, s in sorted(known.items(), key=lambda kv: kv[1]):
        d, b = os.path.split(p)
        n += rename(p, os.path.join(d, f"[{s:0{pad}d}] {PREFIX.sub('', b)}"), args.dry_run)

    if args.dirs:
        # 目录取「其下所有 md 的最小起始段号」，自底向上改，免得改完父目录路径就失效
        by_dir = {}
        for p, s in known.items():
            d = os.path.dirname(p)
            while len(d) > len(args.root):
                by_dir[d] = min(by_dir.get(d, s), s)
                d = os.path.dirname(d)
        for d in sorted(by_dir, key=lambda x: -x.count(os.sep)):
            parent, name = os.path.split(d)
            n += rename(d, os.path.join(parent, f"[{by_dir[d]:0{pad}d}] {PREFIX.sub('', name)}"),
                        args.dry_run)

    print(f"{'（试跑）' if args.dry_run else ''}共重命名 {n} 项"
          f"（补零 {pad} 位，跳过 {len(missing)} 个无段号文件）")


if __name__ == "__main__":
    main()
