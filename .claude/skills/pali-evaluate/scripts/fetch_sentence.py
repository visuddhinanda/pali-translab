"""Fetch sentences from wikipali: /api/v2/sentence.

Usage:
  python fetch_sentence.py --book 98 --para 1524 --channels <uuid>[,<uuid>...] \\
                           [--format text|markdown|html] [--refresh]

Output: jsonl to stdout, one sentence per line.
"""
from __future__ import annotations
import argparse
import sys
from _client import get, emit_jsonl


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--book", type=int, required=True)
    p.add_argument("--para", required=True, help="comma-separated para numbers")
    p.add_argument("--channels", required=True, help="comma-separated channel UUIDs")
    p.add_argument("--format", default="text", choices=["text", "markdown", "html"])
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args(argv)

    data = get("/api/v2/sentence", {
        "view": "paragraph",
        "book": args.book,
        "para": args.para,
        "channels": args.channels,
        "format": args.format,
    }, refresh=args.refresh)

    rows = data.get("rows", [])
    emit_jsonl(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
