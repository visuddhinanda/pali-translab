#!/usr/bin/env python3
"""把 jsonl 的 id 字段改为复合键 {book}-{paragraph}-{word_start}-{word_end}。

原 wikipali UUID 被覆盖（可由 (book,para,ws,we) 反查，不另存）。
id 置于每行首字段；其余字段顺序不变。

用法：
  python3 reformat_id.py <file|dir> ...
目录递归处理 *.jsonl。
"""
from __future__ import annotations
import json
import os
import sys


def make_id(d: dict) -> str:
    return f"{d['book']}-{d['paragraph']}-{d['word_start']}-{d['word_end']}"


def do_file(path: str) -> int:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            d = json.loads(s)
            new = {"id": make_id(d)}
            for k, v in d.items():
                if k != "id":
                    new[k] = v
            out.append(json.dumps(new, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        for l in out:
            f.write(l + "\n")
    return len(out)


def main(argv):
    if not argv:
        print("用法: reformat_id.py <file|dir> ...", file=sys.stderr)
        return 2
    n = 0
    for t in argv:
        if os.path.isdir(t):
            for root, _, files in os.walk(t):
                for fn in sorted(files):
                    if fn.endswith(".jsonl"):
                        p = os.path.join(root, fn)
                        c = do_file(p)
                        n += c
                        print(f"  {p} ({c} 行)")
        elif t.endswith(".jsonl"):
            c = do_file(t)
            n += c
            print(f"  {t} ({c} 行)")
    print(f"共 {n} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
