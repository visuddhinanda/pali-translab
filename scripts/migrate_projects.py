# -*- coding: utf-8 -*-
"""一次性搬家：把散在 workspace 下的项目文件收进 `workspace/projects/<name>/`。

搬家前，一个项目的东西分布在四处公共目录里：

    workspace/projects/<name>.json / .html
    workspace/export/<书名>/…            ← **五个项目共用**，发信打包要从里面挑
    workspace/reports/<book>/…
    workspace/logs/<book>-<start>-<end>.log

挑错就会把别的书一起寄出去（实测整个 export 是 20 MB，本项目只有 3 MB）。
搬完之后一个项目一个目录，打包就是 `zip -r <name>.zip <name>/`。

**只搬文件，不改 project.json 的内部结构**（旧项目都已跑完，改结构没有收益，只有风险）。
export 目录归谁，按书目表的 toc 名字认领——那正是 export_markdown 建目录时用的名字。

    python3 scripts/migrate_projects.py            # 只报计划，不动文件
    python3 scripts/migrate_projects.py --write
    python3 scripts/migrate_projects.py --write --only mn-majjhimapannasa
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project as pj  # noqa: E402

WORK = pj.WORK
PROJECTS = pj.PROJECTS
UNSAFE_RE = re.compile(r"[/\\\x00-\x1f]+")


def safe_name(title):
    """与 export_markdown.safe_name 同规则——目录名就是这么建出来的。"""
    return UNSAFE_RE.sub("-", title).strip().strip(".")[:120] or "untitled"


def book_titles():
    """{book: {toc 名字}}，来自书目缓存。一个 book 号可能挂着好几部书。"""
    path = os.path.join(WORK, "cache_books.json")
    out = {}
    if os.path.exists(path):
        for r in json.load(open(path, encoding="utf-8")):
            if r.get("toc"):
                out.setdefault(r["book"], set()).add(safe_name(r["toc"]))
    return out


def books_of(proj):
    bs = set()
    for j in proj["jobs"]:
        if j.get("mula"):
            bs.add(j["mula"]["book"])
        for lay in j.get("layers", []):
            bs.add(lay["book"])
        for e in j.get("own", []) + j.get("ref", []):
            bs.add(e["book"])
    return sorted(bs)


def plan_for(name, titles):
    """[(源, 目标)]——这个项目该搬哪些东西。源不存在的条目不会出现在计划里。"""
    old_json = os.path.join(PROJECTS, f"{name}.json")
    src_json = old_json if os.path.exists(old_json) else pj.path_of(name)
    proj = json.load(open(src_json, encoding="utf-8"))
    dst = pj.home(name)
    moves = []
    if os.path.exists(old_json):
        moves.append((old_json, os.path.join(dst, "project.json")))
    old_html = os.path.join(PROJECTS, f"{name}.html")
    if os.path.exists(old_html):
        moves.append((old_html, os.path.join(dst, "project.html")))

    want = set()
    for b in books_of(proj):
        want |= titles.get(b, set())

    exp = os.path.join(WORK, "export")
    for t in sorted(want):
        d = os.path.join(exp, t)
        if os.path.isdir(d):
            moves.append((d, os.path.join(dst, "export", t)))
    # 书根直接出的散章：`[0003] <书名>.md` 就躺在 export 根下
    if os.path.isdir(exp):
        for f in sorted(os.listdir(exp)):
            if not f.endswith(".md"):
                continue
            stem = re.sub(r"^\[\d+\]\s*", "", f[:-3])
            if stem in want:
                moves.append((os.path.join(exp, f), os.path.join(dst, "export", f)))

    for b in books_of(proj):
        d = os.path.join(WORK, "reports", str(b))
        if os.path.isdir(d):
            moves.append((d, os.path.join(dst, "reports", str(b))))
    logs = os.path.join(WORK, "logs")
    if os.path.isdir(logs):
        bs = {str(b) for b in books_of(proj)}
        for f in sorted(os.listdir(logs)):
            if f.endswith(".log") and f.split("-")[0] in bs:
                moves.append((os.path.join(logs, f), os.path.join(dst, "logs", f)))
    return moves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="真的搬；不给就只报计划")
    ap.add_argument("--only", default="", help="只搬这一个项目")
    args = ap.parse_args()

    titles = book_titles()
    names = [d[:-5] for d in sorted(os.listdir(PROJECTS))
             if d.endswith(".json") and d != "index.json"]
    names += [d for d in sorted(os.listdir(PROJECTS))
              if os.path.isfile(os.path.join(PROJECTS, d, "project.json"))
              and d not in names]
    if args.only:
        names = [n for n in names if n == args.only]
    if not names:
        sys.exit("没有要搬的项目")

    total = 0
    for name in names:
        moves = plan_for(name, titles)
        print(f"\n== {name}：{len(moves)} 项")
        for src, dst in moves:
            kind = "目录" if os.path.isdir(src) else "文件"
            print(f"   {kind} {os.path.relpath(src, WORK)}  →  {os.path.relpath(dst, WORK)}")
        total += len(moves)
        if args.write:
            for src, dst in moves:
                if not os.path.exists(src):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    print(f"   ⚠ 目标已存在，跳过：{os.path.relpath(dst, WORK)}")
                    continue
                shutil.move(src, dst)
            print(f"   ✓ 已搬 {name}")
    print(f"\n合计 {total} 项" + ("" if args.write else "（--write 才真的动文件）"))


if __name__ == "__main__":
    main()
