# -*- coding: utf-8 -*-
"""translate 只差一两句时（坐标对不上之类）流水线不重试，缺的句子记进
`workspace/projects/<name>/manual_fix.tsv`（task、句子坐标、时间），由人工补译文。

是否已补**以 channel 为准**：坐标上有译文就算补上，不另记账。

    python3 scripts/manual_fix.py list                     # 全部项目里还没补的句子，带巴利原文与上下句译文
    python3 scripts/manual_fix.py list --project x08-...
    python3 scripts/manual_fix.py check --project x08-...  # 有没补的就退出码 1（收尾脚本用）
    python3 scripts/manual_fix.py write --project x08-... --id 51-1990-2-8 --zh "译文"
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import get_rows, plain, run  # noqa: E402
import project as pj  # noqa: E402


def entries(name):
    path = os.path.join(pj.home(name), "manual_fix.tsv")
    if not os.path.exists(path):
        return []
    out, seen = [], set()
    for line in open(path, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2 and parts[1] not in seen:
            seen.add(parts[1])
            out.append((parts[0], parts[1]))
    return out


def parse(sid):
    b, p, a, e = (int(x) for x in sid.split("-"))
    return b, p, a, e


def key(r):
    return (int(r["paragraph"]), int(r["word_start"]), int(r["word_end"]))


def pending(name):
    """[(task, sid, 巴利, 前一句译文, 后一句译文)]——channel 上还没有译文的。"""
    proj = pj.load(name)
    ch = proj["channel"]
    out = []
    for task, sid in entries(name):
        b, p, a, e = parse(sid)
        paras = range(max(1, p - 1), p + 2)
        tr = {key(r): plain(r) for r in get_rows(b, paras, [ch])}
        if (p, a, e) in tr:
            continue
        src = sorted(get_rows(b, paras), key=key)
        ks = [key(r) for r in src]
        pali = next((plain(r) for r in src if key(r) == (p, a, e)), "")
        i = ks.index((p, a, e)) if (p, a, e) in ks else -1
        prev_zh = tr.get(ks[i - 1], "") if i > 0 else ""
        next_zh = tr.get(ks[i + 1], "") if 0 <= i < len(ks) - 1 else ""
        out.append((task, sid, pali, prev_zh, next_zh))
    return out


def names(arg):
    if arg:
        return [arg]
    return sorted(os.path.basename(os.path.dirname(f))
                  for f in glob.glob("workspace/projects/*/manual_fix.tsv"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "check", "write"])
    ap.add_argument("--project", default="")
    ap.add_argument("--id", default="")
    ap.add_argument("--zh", default="")
    args = ap.parse_args()

    if args.cmd == "write":
        if not (args.project and args.id and args.zh.strip()):
            sys.exit("write 需要 --project --id --zh")
        ch = pj.load(args.project)["channel"]
        b, p, a, e = parse(args.id)
        sent = {"book_id": b, "paragraph": p, "word_start": a, "word_end": e,
                "content": args.zh.strip(), "content_type": "markdown"}
        r = run(["write", "-", "--channel", ch, "--batch", "1", "-y"],
                stdin=json.dumps({"sentences": [sent]}, ensure_ascii=False), check=False)
        if getattr(r, "returncode", 0) != 0:
            sys.exit(f"写入失败：{(getattr(r, 'stderr', '') or '').strip()[-300:]}")
        got = {key(x): plain(x) for x in get_rows(b, [p], [ch])}
        if got.get((p, a, e)) != args.zh.strip():
            sys.exit(f"读回核对不符：{got.get((p, a, e))!r}")
        print(f"✓ {args.id} 已写入并读回核对")
        return

    total = 0
    for n in names(args.project):
        pend = pending(n)
        total += len(pend)
        if args.cmd == "list":
            for task, sid, pali, pz, nz in pend:
                print(f"{n}\t{task}\t{sid}\n  巴利：{pali}\n  上句：{pz}\n  下句：{nz}")
    if args.cmd == "list":
        print(f"待人工补 {total} 句")
    if args.cmd == "check" and total:
        print(f"{args.project} 还有 {total} 句待人工补")
        sys.exit(1)


if __name__ == "__main__":
    main()
