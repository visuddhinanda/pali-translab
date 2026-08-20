# -*- coding: utf-8 -*-
"""从 wikipali 取一批段落的原文与对齐资源，输出精简 JSONL 供提示词注入。

一次可取多段（`--para 983-986`）——让 LLM 看到上下文，术语与语体才连得起来。

输出分两层，`layer` 字段区分，mūla 在前、注释在后：

    {"layer":"mula","id":"93-984-2-19","book":93,"paragraph":984,
     "word_start":2,"word_end":19,"pali":"…","nissaya":"…","zh":"…"}
    {"layer":"atthakatha","for":984,"id":"103-1470-2-9","pali":"…"}

用法：
    python3 scripts/wp_pull.py --book 93 --para 983-986                    # 只要 pali
    python3 scripts/wp_pull.py --book 93 --para 983-986 --nissaya          # 附缅文 nissaya
    python3 scripts/wp_pull.py --book 93 --para 983-986 --atthakatha       # 附义注（含复注用 --tika）
    python3 scripts/wp_pull.py --book 93 --para 983-986 --channel <uid>    # 附该 channel 的现有译文
"""
import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import PALI_UID, dump, jget, parse_paras, plain  # noqa: E402

# related 的 tags 里标文献层次
LAYER_TAGS = {"aṭṭhakathā": "atthakatha", "ṭīkā": "tika"}


def fetch(book, paras, channels, batch=20):
    rows = []
    for i in range(0, len(paras), batch):
        coords = [f"{book}:{p}" for p in paras[i:i + batch]]
        rows += jget("get", *coords, "--json",
                     *[a for uid in channels for a in ("--channel", uid)])
    return rows


def find_nissaya(book, para):
    """该段有没有缅文 nissaya channel——没有就降级，不要拿别段的凑。"""
    return [r["uid"] for r in jget("versions", f"{book}:{para}", "--json")
            if r.get("type") == "nissaya"]


def find_commentary(book, para, want):
    """某一段的义注 / 复注对应段——**这里保留 `wikipali related`**，理由如下。

    全书级的事情（排计划、定章节归属、切统稿单元）一律用 `cs_para`，因为它是本地
    计算、跨书通用。但 cs 是**粗粒度**的：一个典藏段号常覆盖注释层几十上百段
    （实测本文 93:12 一段的 cs 对应义注 96 段、复注 164 段），拿它给单段找对照
    就是把整章塞进去。related 给的是逐段的精确对应，正是单段翻译需要的。

    换句话说：**related 只用在单段场景，且一次只问一段**——这一层的调用量是可控的。
    """
    hits = []
    for rel in jget("related", f"{book}:{para}", "--json"):
        names = {t.get("name") for t in rel.get("tags", [])}
        layer = next((LAYER_TAGS[n] for n in names if n in LAYER_TAGS), None)
        if layer in want:
            for p in rel.get("para", []):
                hits.append((layer, rel["book"], p))
    return hits


def merge(rows, pali_uid, nissaya_uids):
    """按 (paragraph, word_start, word_end) 把多个 channel 的句子并成一行。"""
    merged, order = {}, []
    for rec in rows:
        key = (rec["paragraph"], rec["word_start"], rec["word_end"])
        uid = (rec.get("channel") or {}).get("id")
        if key not in merged:
            merged[key] = {
                "id": f"{rec['book']}-{rec['paragraph']}-{key[1]}-{key[2]}",
                "book": rec["book"], "paragraph": rec["paragraph"],
                "word_start": key[1], "word_end": key[2],
            }
            order.append(key)
        slot = "pali" if uid == pali_uid else "nissaya" if uid in nissaya_uids else "zh"
        text = plain(rec)
        if text:
            merged[key][slot] = text
    return [merged[k] for k in sorted(order)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--para", required=True, help="段号：984 / 983-986 / 983,985-987")
    ap.add_argument("--channel", action="append", default=[],
                    help="译文 channel uid，取到的内容放进 zh 字段")
    ap.add_argument("--nissaya", action="store_true", help="附缅文 nissaya（该段没有则静默跳过）")
    ap.add_argument("--atthakatha", action="store_true", help="附义注原文")
    ap.add_argument("--tika", action="store_true", help="附复注原文")
    args = ap.parse_args()

    paras = parse_paras(args.para)

    nissaya_uids = []
    if args.nissaya:
        for p in paras:
            nissaya_uids += find_nissaya(args.book, p)
        nissaya_uids = list(dict.fromkeys(nissaya_uids))

    rows = fetch(args.book, paras, [PALI_UID, *nissaya_uids, *args.channel])
    for row in merge(rows, PALI_UID, nissaya_uids):
        if row.get("pali"):          # 没有巴利原文的坐标不是可翻译单位
            print(dump({"layer": "mula", **row}))

    want = {l for l, on in (("atthakatha", args.atthakatha), ("tika", args.tika)) if on}
    if not want:
        return

    seen = set()
    for p in paras:
        for layer, cbook, cpara in find_commentary(args.book, p, want):
            if (cbook, cpara) in seen:
                continue
            seen.add((cbook, cpara))
            for rec in fetch(cbook, [cpara], [PALI_UID]):
                text = plain(rec)
                if text:
                    print(dump({
                        "layer": layer, "for": p,
                        "id": f"{rec['book']}-{rec['paragraph']}-{rec['word_start']}-{rec['word_end']}",
                        "pali": text,
                    }))


if __name__ == "__main__":
    main()
