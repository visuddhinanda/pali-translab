#!/usr/bin/env python3
"""从 claude -p 的原始 stdout 中抽取合法 JSONL 行，原地重写。

claude -p 常在 JSONL 前后裹旁白或 ```jsonl 代码围栏；模型也可能在 zh/pali 字段里
误用 ASCII 引号 " ' 导致整行 JSON 非法。本脚本：
  1. 只保留以 { 开头的候选行；
  2. 能直接 json.loads 成 dict 的直接收下；
  3. 否则尝试把「与 CJK 相邻的 ASCII 引号」全角化后重试（抢救常见的引号污染）；
  4. 仍失败的候选行丢弃，并把丢弃数报到 stderr。

用法：
  python3 _extract_jsonl.py <file>          # 原地清洗
  python3 _extract_jsonl.py <in> <out>      # 读 in 写 out

退出码：0=至少抽到一行；1=零行（视为失败）。
"""
from __future__ import annotations
import json
import sys

# CJK 及中文全角标点（判定 ASCII 引号是否为「内容引号」用）
def _is_cjk(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF      # CJK 统一表意
        or 0x3000 <= o <= 0x303F   # CJK 标点
        or 0xFF00 <= o <= 0xFFEF   # 全角 ASCII / 半宽
        or ch in "「」『』“”‘’，。、；：！？（）—…"
    )


def _prev_nonspace(s: str, i: int) -> str:
    j = i - 1
    while j >= 0 and s[j] == " ":
        j -= 1
    return s[j] if j >= 0 else ""


def _next_nonspace(s: str, i: int) -> str:
    j = i + 1
    while j < len(s) and s[j] == " ":
        j += 1
    return s[j] if j < len(s) else ""


def _fullwidthen_quotes(s: str) -> str:
    """把 zh/pali 值内部的 ASCII " 全角化（区分结构引号与内容引号）。

    结构引号紧邻 JSON 标点（前为 { [ , : 或后为 : , ] }）；其余 ASCII 双引号
    视为内容引号，按开/闭配对替换为全角 “”。单引号 ' 在 JSON 字符串内合法，不处理。
    """
    out = []
    for i, ch in enumerate(s):
        if ch == '"':
            p = _prev_nonspace(s, i)
            n = _next_nonspace(s, i)
            # 不含 [ ]：内容里的方括号（译者注）远比已损坏行里的 JSON 数组常见，
            # 把 ]/[ 旁的引号当内容引号全角化，能救回带方括号译注的句子。
            structural = p in "{,:" or n in ":,}"
            if not structural:
                # 内容引号：前接 CJK 视为闭引号，否则开引号
                out.append("”" if _is_cjk(p) else "“")
                continue
        out.append(ch)
    return "".join(out)


def extract(text: str):
    kept, dropped = [], 0
    for line in text.splitlines():
        s = line.strip()
        if not s or not s.startswith("{"):
            continue
        obj = None
        try:
            obj = json.loads(s)
        except Exception:
            try:
                obj = json.loads(_fullwidthen_quotes(s))
            except Exception:
                obj = None
        if isinstance(obj, dict):
            kept.append(json.dumps(obj, ensure_ascii=False))
        else:
            dropped += 1
    return kept, dropped


def main(argv):
    if not argv:
        print("用法: _extract_jsonl.py <file> [<out>]", file=sys.stderr)
        return 2
    src = argv[0]
    dst = argv[1] if len(argv) > 1 else argv[0]
    with open(src, encoding="utf-8") as f:
        kept, dropped = extract(f.read())
    with open(dst, "w", encoding="utf-8") as f:
        for l in kept:
            f.write(l + "\n")
    if dropped:
        print(f"[_extract_jsonl] 丢弃 {dropped} 个无法解析的候选行（{src}）", file=sys.stderr)
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
