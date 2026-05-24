"""Export translated jsonl → mdbook source (and optionally build).

Reads:  workspace/translations/{method}/{book}/{para}_{version}.jsonl
Writes: workspace/translations/{method}/{book}/_mdbook/{book.toml, src/SUMMARY.md, src/*.md}

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
    for f in src_dir.glob(f"*_{version}.jsonl"):
        para = int(f.name.split("_")[0])
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
    src = root / "workspace" / "translations" / args.method / str(args.book)
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
    dist = src / "_mdbook"
    src_md = dist / "src"
    src_md.mkdir(parents=True, exist_ok=True)

    title = " / ".join(w["title"] for w in works)
    (dist / "book.toml").write_text(
        f'[book]\ntitle = "{title}"\nlanguage = "zh"\nsrc = "src"\n',
        "utf-8",
    )

    summary = ["# Summary", ""]
    written = 0
    for t in toc_entries:
        ch_paras = chapters[t["paragraph"]]
        if not ch_paras:
            continue
        level = max(1, t.get("level") or 1)
        indent = "  " * (level - 1)
        fname = f"{t['paragraph']:06d}-{slug(t['toc'])}.md"
        summary.append(f"{indent}- [{t['toc']}](./{fname})")

        md = [f"# {t['toc']}", ""]
        for para in ch_paras:
            md.append(f"## §{para}")
            md.append("")
            for sent in paras[para]:
                if style["show_pali"] and sent.get("pali"):
                    md.append(f"> {sent['pali']}")
                    md.append("")
                if sent.get("zh"):
                    md.append(str(sent["zh"]))
                    md.append("")
        (src_md / fname).write_text("\n".join(md), "utf-8")
        written += 1

    (src_md / "SUMMARY.md").write_text("\n".join(summary) + "\n", "utf-8")
    print(f"wrote {written} chapter files to {dist}")

    if shutil.which("mdbook"):
        print("mdbook found; building HTML...")
        subprocess.run(["mdbook", "build", str(dist)], check=False)
    else:
        print("mdbook not installed. To build HTML:")
        print("  cargo install mdbook   # or grab binary from github releases")
        print(f"  cd {dist} && mdbook build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
