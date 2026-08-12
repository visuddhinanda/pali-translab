# -*- coding: utf-8 -*-
"""把 wikipali channel 里的译文导出为本地 markdown——**一章（经文）一个文件**，带 YAML frontmatter。

译文的正本在 wikipali；这里只是按用户要求生成一份可读、可归档的离线副本。
章节边界取自 `wikipali toc`：某条目录项到下一条目录项之前的所有段落即一章。

文件名用章节名，目录用章节路径（取自 toc 的祖先面包屑）：

    workspace/export/(DN) Sīlakkhandhavaggapāḷi/12. Lohiccasuttaṃ/Tayo codanārahā.md

正文只有译文（不含巴利原文）：**一句一行**，同段落的句子之间不空行，段落之间空一行。

用法：
    python3 scripts/export_markdown.py --book 216 --channel <uid>              # 整本
    python3 scripts/export_markdown.py --book 216 --channel <uid> --para 35    # 该段所属那一章
    python3 scripts/export_markdown.py --book 216 --channel <uid> --from 28 --to 120
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import jget, plain  # noqa: E402

# 文件名/目录名保留章节名原貌，只挡掉路径分隔符与控制字符
UNSAFE_RE = re.compile(r"[/\\\x00-\x1f]+")
PROBE = 200  # 末章没有下一条目录项时，向后探这么多段


def chapters(book, anchor_para):
    """目录项 → [{start, end, title, path}]，path 是祖先标题面包屑。"""
    toc = jget("toc", f"{book}:{anchor_para}", "--json", "--depth", "9")
    toc = [t for t in toc if t.get("book") == book]
    toc.sort(key=lambda t: t["paragraph"])

    out = []
    for i, t in enumerate(toc):
        nxt = toc[i + 1]["paragraph"] - 1 if i + 1 < len(toc) else t["paragraph"] + PROBE
        # 面包屑：每一层只保留最近的那个祖先
        seen = {}
        for a in toc[:i]:
            if a["level"] < t["level"]:
                seen[a["level"]] = a["toc"]
        out.append({"start": t["paragraph"], "end": nxt, "title": t["toc"],
                    "level": t["level"], "path": [seen[k] for k in sorted(seen)]})
    return out


def fetch_range(book, start, end, channels, batch=20):
    rows = []
    for lo in range(start, end + 1, batch):
        coords = [f"{book}:{p}" for p in range(lo, min(lo + batch, end + 1))]
        rows += jget("get", *coords, "--json",
                     *[a for uid in channels for a in ("--channel", uid)])
    return rows


def safe_name(title):
    """章节名直接当文件/目录名，只替掉路径分隔符，保留空格与变音符号。"""
    return UNSAFE_RE.sub("-", title).strip().strip(".")[:120] or "untitled"


def yaml_str(v):
    return json.dumps(v, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--channel", required=True, help="译文 channel uid")
    ap.add_argument("--para", type=int, help="只导出该段所属的那一章")
    ap.add_argument("--from", dest="start", type=int)
    ap.add_argument("--to", dest="end", type=int)
    ap.add_argument("--out", default="workspace/export")
    ap.add_argument("--model", default="", help="写进 frontmatter 的模型名")
    args = ap.parse_args()

    meta = next((c for c in jget("channels", "--json") if c["uid"] == args.channel), {})
    anchor = args.para or args.start or 1
    chs = chapters(args.book, anchor)
    if not chs:
        sys.exit(f"book {args.book} 取不到目录，无法按章导出")

    if args.para:
        chs = [c for c in chs if c["start"] <= args.para <= c["end"]] or chs[:1]
    else:
        lo = args.start if args.start is not None else -10**9
        hi = args.end if args.end is not None else 10**9
        chs = [c for c in chs if c["end"] >= lo and c["start"] <= hi]

    today = datetime.date.today().isoformat()
    written = 0

    for ch in chs:
        rows = fetch_range(args.book, ch["start"], ch["end"], [args.channel])

        by_para = {}
        for rec in rows:
            text = plain(rec)
            if text:
                by_para.setdefault(rec["paragraph"], []).append((rec["word_start"], text))

        paras = sorted(by_para)
        if not paras:
            continue

        n = sum(len(by_para[p]) for p in paras)
        fm = [
            "---",
            f"title: {yaml_str(ch['title'])}",
            f"book: {args.book}",
            f"paragraph_start: {paras[0]}",
            f"paragraph_end: {paras[-1]}",
            f"path: [{', '.join(yaml_str(x) for x in ch['path'])}]",
            f"channel: {yaml_str(meta.get('name', args.channel))}",
            f"channel_uid: {args.channel}",
            f"lang: {yaml_str(meta.get('lang', 'zh-Hans'))}",
            "generated_by: AI",
        ]
        if args.model:
            fm.append(f"model: {yaml_str(args.model)}")
        fm += [
            f"source: {yaml_str('wikipali')}",
            f"sentences: {n}",
            f"exported_at: {today}",
            "---",
            "",
            f"# {ch['title']}",
            "",
            "> 本文是**机器生成的译文**，正本在 WikiPali，本文件只是离线副本。",
            "",
        ]

        # 一句一行；同段落内不空行，段落之间空一行
        body = []
        for p in paras:
            body += [t for _, t in sorted(by_para[p])]
            body.append("")

        outdir = os.path.join(args.out, *[safe_name(x) for x in ch["path"]])
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"{safe_name(ch['title'])}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(fm + body).rstrip() + "\n")
        print(f"✓ {path}（{args.book}:{paras[0]}–{paras[-1]}，{n} 句）")
        written += 1

    print(f"共导出 {written} 章 → {args.out}/")


if __name__ == "__main__":
    main()
