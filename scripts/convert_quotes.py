#!/usr/bin/env python3
"""把全角直角引号「」『』转换为全角弯引号 “” ‘’。

- .jsonl：逐行 json.loads，仅在字符串值内替换后再 dump（不碰 JSON 结构）。
- 其他（.md 等）：整文件文本替换。

用法：
  python3 convert_quotes.py <file|dir> [<file|dir> ...]
目录会递归处理 *.jsonl 与 *.md。
"""
from __future__ import annotations
import json
import os
import sys

MAP = {"「": "“", "」": "”", "『": "‘", "』": "’"}


def _conv(s: str) -> str:
    for a, b in MAP.items():
        s = s.replace(a, b)
    return s


def _walk(obj):
    if isinstance(obj, str):
        return _conv(obj)
    if isinstance(obj, list):
        return [_walk(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _walk(v) for k, v in obj.items()}
    return obj


def do_jsonl(path: str) -> int:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            out.append(json.dumps(_walk(json.loads(s)), ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        for l in out:
            f.write(l + "\n")
    return len(out)


def do_text(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        t = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(_conv(t))
    return 1


def handle(path: str):
    if path.endswith(".jsonl"):
        n = do_jsonl(path)
        print(f"  jsonl {path} ({n} 行)")
    elif path.endswith(".md"):
        do_text(path)
        print(f"  md    {path}")


def main(argv):
    if not argv:
        print("用法: convert_quotes.py <file|dir> ...", file=sys.stderr)
        return 2
    for target in argv:
        if os.path.isdir(target):
            for root, _, files in os.walk(target):
                for fn in sorted(files):
                    if fn.endswith((".jsonl", ".md")):
                        handle(os.path.join(root, fn))
        else:
            handle(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
