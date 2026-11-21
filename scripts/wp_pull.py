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
    python3 scripts/wp_pull.py --book 93 --para 983-986 --local-dir DIR    # zh 取本地待补传的 JSONL
"""
import argparse
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import PALI_UID, dump, get_rows, jget, layer_of, parse_paras, plain  # noqa: E402


def fetch(book, paras, channels, batch=20):
    """见 _wp.get_rows：拆批重取，防 `wikipali get` 的静默截断。"""
    return get_rows(book, paras, channels, batch)


def find_nissaya(book, para):
    """该段有没有缅文 nissaya channel——没有就降级，不要拿别段的凑。"""
    # 只认缅文原始 nissaya（lang == "my"）——同名 type 下还有 AI 生成的汉译 nissaya
    # （lang zh-Hans），它是机器产物，不能拿来当词级基准。
    return [r["uid"] for r in jget("versions", f"{book}:{para}", "--json")
            if r.get("type") == "nissaya" and r.get("lang") == "my"]


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
        layer = layer_of(names)   # related 的 tags 里标文献层次，判定同 _wp.LAYER_TAG_RULES
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


def local_zh(out_dir, book, paras):
    """从待补传目录里读该书这些段的译文：`{(段,起,止): 译文}`。

    服务端写不进去时译文只存在本地（见 `wp_push.py --out-dir`），而注释层开译要
    注入父层译文——被解释词必须与父层逐字同译。没有这个回退，本地模式下
    父层译文就成了空的，注释层只能自己定译法，统稿再也补不回来。

    文件是 `<book>-<起段>-<止段>.jsonl`，一行一句；按 book 与段号过滤，
    文件名只用来缩小扫描范围，真正认的是行里的坐标。
    """
    out = {}
    if not out_dir or not os.path.isdir(out_dir):
        return out
    want = set(paras)
    for name in sorted(os.listdir(out_dir)):
        if not name.endswith(".jsonl") or not name.startswith(f"{book}-"):
            continue
        with open(os.path.join(out_dir, name), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if int(r.get("book_id") or r.get("book") or 0) != book:
                    continue
                if r.get("paragraph") not in want:
                    continue
                out[(r["paragraph"], r["word_start"], r["word_end"])] = \
                    r.get("content") or ""
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--para", required=True, help="段号：984 / 983-986 / 983,985-987")
    ap.add_argument("--channel", action="append", default=[],
                    help="译文 channel uid，取到的内容放进 zh 字段")
    ap.add_argument("--nissaya", action="store_true", help="附缅文 nissaya（该段没有则静默跳过）")
    ap.add_argument("--atthakatha", action="store_true", help="附义注原文")
    ap.add_argument("--tika", action="store_true", help="附复注原文")
    ap.add_argument("--local-dir", default="", dest="local_dir",
                    help="待补传目录（wp_push --out-dir 的产物）；channel 里没有的译文从这里取")
    args = ap.parse_args()

    paras = parse_paras(args.para)

    # 先取巴利原文，**只对真有原文的段**查 nissaya、取译文。
    # 段号区间里会有不存在的编号（kn15 的 149:2446，`get` 返回 []）：对它调
    # `versions` 服务端回 500，守护进程认作环境异常无限退回队列，整个阶段卡死。
    # 查询失败照样中止——这里只排除「确实没有」，不吞「读不到」。
    rows = fetch(args.book, paras, [PALI_UID])
    present = sorted({r["paragraph"] for r in rows})

    nissaya_uids = []
    if args.nissaya:
        for p in present:
            nissaya_uids += find_nissaya(args.book, p)
        nissaya_uids = list(dict.fromkeys(nissaya_uids))

    extra = [*nissaya_uids, *args.channel]
    if extra and present:
        rows += fetch(args.book, present, extra)
    # channel 里已有的译文优先；本地待补传的只补 channel 没有的那些坐标
    local = local_zh(args.local_dir, args.book, present)
    for row in merge(rows, PALI_UID, nissaya_uids):
        if not row.get("pali"):      # 没有巴利原文的坐标不是可翻译单位
            continue
        if not row.get("zh"):
            zh = local.get((row["paragraph"], row["word_start"], row["word_end"]))
            if zh:
                row["zh"] = zh
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
