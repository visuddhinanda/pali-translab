"""Fetch palitext TOC or paragraph detail: /api/v2/palitext.

Modes:
  toc:    --book X --para START   → /api/v2/palitext?view=book-toc
  detail: --book X --para P       → /api/v2/palitext/X-P (path-style)

Usage:
  python fetch_palitext.py toc    --book 210 --para 1659
  python fetch_palitext.py detail --book 210 --para 1659    # has chapter_len etc.
"""
from __future__ import annotations
import argparse
import json
import sys
from _client import get, emit_jsonl


def cmd_toc(args) -> int:
    data = get("/api/v2/palitext", {
        "view": "book-toc",
        "book": args.book,
        "para": args.para,
    }, refresh=args.refresh)
    emit_jsonl(data.get("rows", []))
    return 0


def cmd_detail(args) -> int:
    data = get(f"/api/v2/palitext/{args.book}-{args.para}",
               refresh=args.refresh)
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)

    for name, fn in [("toc", cmd_toc), ("detail", cmd_detail)]:
        sp = sub.add_parser(name)
        sp.add_argument("--book", type=int, required=True)
        sp.add_argument("--para", type=int, required=True)
        sp.add_argument("--refresh", action="store_true")
        sp.set_defaults(func=fn)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
