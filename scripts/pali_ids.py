# -*- coding: utf-8 -*-
"""从 wp_pull 的 JSONL 里挑出**真有巴利词**的本文句，写出 id 清单并报数。

为什么要挑：句子表会把孤立的标点切成独立「句子」——实测 `184-556-174-174`
与 `184-556-175-175` 的 pali 就是 `**.**`，一个加粗的句号，没有任何可译内容。
模型当然不会为它输出一行译文，于是 `wp_push --expect` 判「缺句」、整块重试到
用尽、task 记失败。**只要一块里有这种句子，这块必然失败**——这不是漏译。

判定只看一件事：pali 里有没有 Unicode 字母（category L*）。
`**.**`、`…`、`||` 这类没有，`Sīhasenāpatisuttādivaṇṇanā niṭṭhitā .` 有。
数字、变音符号、天城体转写一概照常算字母。

用法（两条执行路径共用）：
    N=$(printf '%s' "$SRC" | python3 scripts/pali_ids.py "$IDS_FILE")
写出的 id 清单给 `wp_push --expect-ids`，打印的计数给 `--expect` 与提示词里的「共 N 句」。
"""
import json
import sys
import unicodedata


def has_pali(text):
    """这句里有没有巴利词——有 Unicode 字母就算，纯标点/空白不算。"""
    return any(unicodedata.category(c).startswith("L") for c in text or "")


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else ""
    ids, skipped = [], []
    for line in sys.stdin:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("layer") != "mula" or not r.get("id"):
            continue
        (ids if has_pali(r.get("pali")) else skipped).append(r["id"])
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write("".join(i + "\n" for i in ids))
    if skipped:
        print(f"  （{len(skipped)} 句只有标点、没有巴利词，不计入漏译："
              f"{', '.join(skipped[:4])}{' …' if len(skipped) > 4 else ''}）",
              file=sys.stderr)
    print(len(ids))


if __name__ == "__main__":
    main()
