"""Fetch channel catalog: /api/v2/channel.

Usage:
  python fetch_channels.py --view system|community
  python fetch_channels.py --view paragraphs --book 98 --para 1524
  python fetch_channels.py --resolve <channel_name>      # name → uid (system view)

Output: jsonl rows, or single uid when --resolve.
"""
from __future__ import annotations
import argparse
import sys
from _client import get, emit_jsonl


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--view", default="system",
                   choices=["system", "community", "paragraphs"])
    p.add_argument("--book", type=int)
    p.add_argument("--para", type=int)
    p.add_argument("--resolve", help="channel name → uid lookup")
    p.add_argument("--type", help="filter by channel.type (e.g. nissaya/original/translation)")
    p.add_argument("--lang", help="filter by channel.lang (e.g. my/pali/zh)")
    p.add_argument("--uids-only", action="store_true",
                   help="print only matching uids, newline-separated (for shell composition)")
    p.add_argument("--refresh", action="store_true")
    args = p.parse_args(argv)

    params: dict = {"view": args.view}
    if args.view == "paragraphs":
        if args.book is None or args.para is None:
            p.error("--view paragraphs requires --book and --para")
        params["book_id"] = args.book
        params["para"] = args.para

    data = get("/api/v2/channel", params, refresh=args.refresh)
    rows = data.get("rows", [])

    if args.resolve:
        match = next((r for r in rows if r.get("name") == args.resolve), None)
        if not match:
            print(f"channel not found: {args.resolve}", file=sys.stderr)
            return 2
        print(match["uid"])
        return 0

    if args.type:
        rows = [r for r in rows if r.get("type") == args.type]
    if args.lang:
        rows = [r for r in rows if r.get("lang") == args.lang]

    if args.uids_only:
        for r in rows:
            print(r.get("uid") or r.get("id"))
        return 0

    emit_jsonl(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
