"""Export translated jsonl → mdbook source (and optionally build).

Reads:  workspace/tipitaka/{method}/jsonl/{book}/{para}_{version}.jsonl
Writes: workspace/tipitaka/{method}/mdbook/{book.toml, src/SUMMARY.md, src/*.md}
Build:  workspace/tipitaka/{method}/html/

Layout: chapters grouped by TOC (from /api/v2/palitext?view=book-toc).
Display: per project knowledge/style.md "显示巴利原文" flag.

Usage:
  python export_mdbook.py --book 98 [--method default] [--version final] [--project-root .]
"""
from __future__ import annotations
import argparse
import bisect
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from _client import get


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "untitled"


def read_style(project_root: Path) -> dict:
    """Heuristic parse of knowledge/style.md."""
    p = project_root / "knowledge" / "style.md"
    if not p.exists():
        return {"show_pali": False}
    text = p.read_text("utf-8")
    # checkbox or plain "是/否" after the 显示巴利原文 field
    show = bool(re.search(r"显示巴利原文.*?(?:\[x\]|：\s*是|:\s*是|是)", text))
    return {"show_pali": show}


def load_paras(src_dir: Path, version: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for d in src_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            para = int(d.name)
        except ValueError:
            continue
        f = d / f"{para}_{version}.jsonl"
        if f.exists():
            out[para] = [json.loads(l) for l in f.read_text("utf-8").splitlines() if l.strip()]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--method", default="default")
    ap.add_argument("--version", default="final")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.project_root).resolve()
    method_dir = root / "workspace" / "tipitaka" / args.method
    src = method_dir / "jsonl" / str(args.book)
    if not src.exists():
        print(f"no source dir: {src}", file=sys.stderr)
        return 2

    paras = load_paras(src, args.version)
    if not paras:
        print(f"no _{args.version}.jsonl files in {src}", file=sys.stderr)
        return 2

    style = read_style(root)

    skill_root = Path(__file__).resolve().parent.parent
    books_json = json.loads((skill_root / "references" / "books.json").read_text("utf-8"))
    works = [b for b in books_json if b["book"] == args.book]
    if not works:
        print(f"book {args.book} not in books.json", file=sys.stderr)
        return 2

    # Aggregate TOC entries across all works in this book.
    # Some works may return "no data"; skip them.
    toc_entries: list[dict] = []
    for w in works:
        try:
            data = get("/api/v2/palitext", {
                "view": "book-toc", "book": args.book, "para": w["start_para"],
            }, refresh=args.refresh)
        except RuntimeError as e:
            print(f"  skip work para={w['start_para']} ({w['title']}): {e}", file=sys.stderr)
            continue
        toc_entries.extend(data.get("rows", []))
    if not toc_entries:
        # No TOC at all → synthesize a single chapter per translated para
        toc_entries = [{"paragraph": p, "toc": f"§{p}", "level": 1}
                       for p in sorted(paras)]
    toc_entries.sort(key=lambda x: x["paragraph"])

    # Bucket translated paragraphs under the nearest preceding TOC entry
    toc_paras = [t["paragraph"] for t in toc_entries]
    chapters: dict[int, list[int]] = {t["paragraph"]: [] for t in toc_entries}
    for para in sorted(paras):
        idx = bisect.bisect_right(toc_paras, para) - 1
        if idx >= 0:
            chapters[toc_paras[idx]].append(para)

    # Write mdbook
    dist = method_dir / "mdbook"
    src_md = dist / "src"
    src_md.mkdir(parents=True, exist_ok=True)

    title = " / ".join(w["title"] for w in works)
    (dist / "book.toml").write_text(
        f'[book]\ntitle = "{title}"\nlanguage = "zh"\nsrc = "src"\n\n'
        '[output.html]\nadditional-css = ["theme/evaluate.css"]\n',
        "utf-8",
    )
    # 评估标注配色（final 版 zh 中的 <span class="evaluate-*">）
    theme = dist / "theme"
    theme.mkdir(parents=True, exist_ok=True)
    (theme / "evaluate.css").write_text(
        ".evaluate-fatal      { background:#ffd6d6; border-bottom:2px solid #d00; cursor:help; }\n"
        ".evaluate-error      { background:#ffe2c2; border-bottom:2px solid #e67e00; cursor:help; }\n"
        ".evaluate-warning    { background:#fff3c4; border-bottom:2px dotted #c8a200; cursor:help; }\n"
        ".evaluate-suggestion { background:#d9ecff; border-bottom:1px dotted #3b82c4; cursor:help; }\n"
        '[class^="evaluate-"]:hover { filter:brightness(0.95); }\n',
        "utf-8",
    )

    # 以实际有章节的条目中的最小 level 作为顶层（0 缩进），
    # 否则首条即缩进、mdbook 识别不到任何章节。
    base_level = min(
        (max(1, t.get("level") or 1) for t in toc_entries if chapters[t["paragraph"]]),
        default=1,
    )

    summary = ["# Summary", ""]
    written = 0
    for t in toc_entries:
        ch_paras = chapters[t["paragraph"]]
        if not ch_paras:
            continue
        level = max(1, t.get("level") or 1)
        indent = "  " * (level - base_level)
        fname = f"{t['paragraph']:06d}-{slug(t['toc'])}.md"
        summary.append(f"{indent}- [{t['toc']}](./{fname})")

        md = [f"# {t['toc']}", ""]
        for para in ch_paras:
            md.append(f"## §{para}")
            md.append("")
            para_lines: list[str] = []
            for sent in paras[para]:
                if style["show_pali"] and sent.get("pali"):
                    md.append(f"> {sent['pali']}")
                    md.append("")
                if sent.get("zh"):
                    para_lines.append(str(sent["zh"]))
            if para_lines:
                md.append("\n".join(para_lines))
                md.append("")
        (src_md / fname).write_text("\n".join(md), "utf-8")
        written += 1

    (src_md / "SUMMARY.md").write_text("\n".join(summary) + "\n", "utf-8")
    print(f"wrote {written} chapter files to {dist}")

    html_dir = method_dir / "html"
    if shutil.which("mdbook"):
        print("mdbook found; building HTML...")
        html_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["mdbook", "build", str(dist), "--dest-dir", str(html_dir)], check=False)
    else:
        print("mdbook not installed. To build HTML:")
        print("  cargo install mdbook   # or grab binary from github releases")
        print(f"  cd {dist} && mdbook build --dest-dir {html_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
