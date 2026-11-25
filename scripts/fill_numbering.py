# -*- coding: utf-8 -*-
"""把「没有巴利词」的句子（纯编号、纯标点，如 `1.`、`(ka)`）照抄原文写进 channel。

translate 按约定不输出这类句子（不算漏译，见 pipeline_batch.sh），于是 channel 里
它们是空的：导出的 markdown 缺了偈颂编号，句数也和原文对不上。这里补齐：

  · 范围取 project.json 的各层 work（book + 起止段），只补**channel 里还没有**的句子，
    已有译文一律不碰
  · 「没有巴利词」与 pali_ids.has_pali 同一判定（无 Unicode 字母）
  · 写入走 `wikipali write`（覆盖式、按坐标），写后从 channel 读回逐条核对

用法：
    python3 scripts/fill_numbering.py --project x06-saddabindu-pakaranam
    python3 scripts/fill_numbering.py --project x06-saddabindu-pakaranam --dry-run
"""
import argparse
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import get_rows, plain, run  # noqa: E402
from pali_ids import has_pali  # noqa: E402
import project as pj  # noqa: E402

BATCH = 50


def key(r):
    return (int(r["paragraph"]), int(r["word_start"]), int(r["word_end"]))


def todo_for(book, lo, hi, channel):
    paras = range(lo, hi + 1)
    have = {key(r) for r in get_rows(book, paras, [channel])}
    out = []
    for r in get_rows(book, paras):
        text = plain(r)
        if not text or has_pali(text) or key(r) in have:
            continue
        p, ws, we = key(r)
        out.append({"book_id": int(book), "paragraph": p, "word_start": ws,
                    "word_end": we, "content": text, "content_type": "markdown"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    proj = pj.load(args.project)
    ch = proj["channel"]

    total = bad = 0
    for L in proj["layers"]:
        b, lo, hi = int(L["book"]), int(L["start"]), int(L["end"])
        todo = todo_for(b, lo, hi, ch)
        print(f"book {b} {lo}-{hi}：待补 {len(todo)} 句"
              + (f"（如 {todo[0]['paragraph']}: {todo[0]['content']}）" if todo else ""))
        if not todo or args.dry_run:
            total += len(todo)
            continue
        for i in range(0, len(todo), BATCH):
            blk = todo[i:i + BATCH]
            r = run(["write", "-", "--channel", ch, "--batch", str(len(blk)), "-y"],
                    stdin=json.dumps({"sentences": blk}, ensure_ascii=False), check=False)
            if getattr(r, "returncode", 0) != 0:
                sys.stderr.write(getattr(r, "stderr", "") or "")
                sys.exit(f"book {b} 写入失败（第 {i // BATCH + 1} 批）")
        # 读回核对：每一句都得在 channel 里，内容一致
        got = {key(r): plain(r) for r in get_rows(b, range(lo, hi + 1), [ch])}
        miss = [s for s in todo
                if got.get((s["paragraph"], s["word_start"], s["word_end"])) != s["content"]]
        total += len(todo)
        bad += len(miss)
        print(f"  写入 {len(todo)}，读回核对不符 {len(miss)}"
              + (f"：{[(s['paragraph'], s['word_start']) for s in miss[:10]]}" if miss else ""))
    print(f"合计 {'待补' if args.dry_run else '补写'} {total} 句" + (f"，不符 {bad}" if bad else ""))
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
