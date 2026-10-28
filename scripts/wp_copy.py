# -*- coding: utf-8 -*-
"""照搬译文：把源段在 channel 上的定稿逐句复制到巴利逐句相同的目标段。

对齐表（如 align_vin6.py）的 `copy` 列出这些段——比丘尼巴提木叉里与比丘部
**巴利逐句相同**的标题与定型句。它们不送去译，等源段定稿后由这一步照搬，
两处译文因此一字不差。

照搬前**逐句核对**：目标段与源段的句子坐标（word_start/word_end）与巴利文字
必须全同，否则整批不写——对齐表是规划期算的，原文若被改过，这里要拦住。
源段有句子还没有译文也整批不写（退出码 1，等下次重试）。写入走 wp_push，
与其它步骤同一套坐标校验与读回核对。

用法：
    python3 scripts/wp_copy.py --book 207 --pairs 545:24,547:26 --channel <uid>
"""
import argparse
import json
import subprocess
import sys

HERE = __file__.rsplit("/", 1)[0]


def pull(book, ps, channel=None):
    cmd = [sys.executable, f"{HERE}/wp_pull.py", "--book", str(book),
           "--para", ",".join(str(p) for p in ps)]
    if channel:
        cmd += ["--channel", channel]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    rows = [json.loads(x) for x in out.splitlines() if x.startswith("{")]
    by = {}
    for r in rows:
        if r.get("layer") == "mula":
            by.setdefault(r["paragraph"], []).append(r)
    return {p: sorted(v, key=lambda r: r["word_start"]) for p, v in by.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--pairs", required=True, help="目标段:源段，逗号分隔")
    ap.add_argument("--channel", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pairs = [tuple(int(x) for x in s.split(":")) for s in args.pairs.split(",") if s]
    src = pull(args.book, [s for _d, s in pairs], args.channel)
    dst = pull(args.book, [d for d, _s in pairs])

    lines, bad, untranslated = [], [], []
    for d, s in pairs:
        a, b = dst.get(d, []), src.get(s, [])
        ka = [(r["word_start"], r["word_end"], r["pali"]) for r in a]
        kb = [(r["word_start"], r["word_end"], r["pali"]) for r in b]
        if ka != kb:
            bad.append(f"{d}←{s}")
            continue
        for ra, rb in zip(a, b):
            if not (rb.get("zh") or "").strip():
                untranslated.append(rb["id"])
                continue
            lines.append({"id": ra["id"], "zh": rb["zh"]})
    if bad:
        sys.exit(f"巴利不再逐句相同，整批不写：{bad[:8]}（对齐表要重新生成）")
    if untranslated:
        sys.exit(f"源段还有 {len(untranslated)} 句没有译文，整批不写：{untranslated[:5]}")
    if not lines:
        print("没有要照搬的句子", file=sys.stderr)
        return

    cmd = [sys.executable, f"{HERE}/wp_push.py", "--book", str(args.book),
           "--para", ",".join(str(d) for d, _s in pairs), "--channel", args.channel,
           "--expect", str(len(lines))]
    if args.dry_run:
        cmd.append("--dry-run")
    rc = subprocess.run(cmd, input="\n".join(json.dumps(x, ensure_ascii=False) for x in lines),
                        text=True).returncode
    if rc == 0:
        print(f"✓ 照搬 {len(pairs)} 段 / {len(lines)} 句", file=sys.stderr)
    sys.exit(rc)


if __name__ == "__main__":
    main()
