# -*- coding: utf-8 -*-
"""单层作品的规划器：**只有本文、只做 translate**，一部作品一个 project。

藏外（añña）诸书没有义注、复注，也没有 nissaya，review/revise/harmonize 都无从谈起，
流水线就只剩 translate。切块、task、stage 全部复用 `plan_scan.py`（schema 3），
这里只做两件它做不了的事：

  · **按作品取范围，不按族**。这些书的 `related_name` 是空的，`layer_works` 拿空族名
    过滤等于不过滤，会把全库 281 部作品都当成同族。这里直接从书目表那一行
    （book + 起段）定出 work，止段是同书下一行的段号 - 1。
  · **一本书多部作品就拆成多个 project**：book 2 有 Mahāpaṇāmapāṭha / Tigumbacetiya
    thomanā / Vāsamālinīkya 三部，book 32 有 Suttantanīti / Vasalasutta 两部。

作品清单写在下面的 WORKS 里，顺序就是执行顺序（编号前缀 = 顺序）。标题按书目表的
toc 匹配（忽略大小写、空白与末尾句点），对不上的直接报错，不猜。

用法：
    python3 scripts/plan_solo.py --list               # 只列清单与匹配结果
    python3 scripts/plan_solo.py --dry-run            # 全部算一遍，不落盘
    python3 scripts/plan_solo.py                      # 落盘全部 project
    python3 scripts/plan_solo.py --only 3,5           # 只规划清单里第 3、5 部
    python3 scripts/plan_solo.py --force              # 已有 project.json 也覆盖
"""
import argparse
import os
import re
import sys
import unicodedata

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import plan_scan as ps  # noqa: E402
import project as pj  # noqa: E402
from _wp import all_books, book_works, have_sent_counts  # noqa: E402

CHANNEL = "73c03e1a-f333-11f0-808a-438f0af4b9e9"

# 执行顺序 = 列表顺序
WORKS = [
    "Cūḷaganthavaṃsapāḷi",
    "Sāsanavaṃsappadīpikā",
    "Mahāvaṃsapāḷi",
    "Padamañjarī",
    "Padasādhanaṃ",
    "Saddabindu pakaraṇaṃ",
    "Kaccāyana dhātu mañjūsā",
    "Samantakūṭavaṇṇanā",
    "Moggallāna vuttivivaraṇapañcikā",
    "Thupavaṃso",
    "Dāṭhāvaṃso",
    "Dhātupāṭha vilāsiniyā",
    "Dhātuvaṃso",
    "Hatthavanagallavihāra vaṃso",
    "Jinacaritaya",
    "Jinavaṃsadīpaṃ",
    "Telakaṭāhagāthā",
    "(saṅgayana-puccha vissajjanā) Dīghanikāye",
    "(saṅgayana-puccha vissajjanā) Majjhimanikāya",
    "(saṅgayana-puccha vissajjanā) Saṃyuttanikāye",
    "(saṅgayana-puccha vissajjanā) Aṅguttaranikāye",
    "(saṅgayana-puccha vissajjanā) Vinayapiṭaka",
    "(saṅgayana-puccha vissajjanā) Abhidhammapiṭaka",
    "(saṅgayana-puccha vissajjanā) Aṭṭhakathā",
    "Rasavāhinī",
    "Sīmavisodhanī",
    "Vessantarāgīti",
    "Caturārakkhadīpanī",
    "Kavidappaṇanīti",
    "Nītimañjarī",
    "Dhammanīti",
    "Mahārahanīti",
    "Lokanīti",
    "Suttantanīti",
    "Vasalasutta",
    "Sūrassatīnīti",
    "Cāṇakyanītipāḷi",
    "Naradakkhadīpanī",
    "Mahāpaṇāmapāṭha",
    "Tigumbacetiya thomanā",
    "Vāsamālinīkya",
    "Lakkhaṇāto",
    "Suttavandanā",
    "Jinālaṅkāra",
    "Kamalāñjali",
    "Pajjamadhu",
    "Buddhaguṇagāthāvalī",
    "Niruttidīpanīpāṭha",
    "Peṭakopadesapāḷi",
    # 文法书（byākaraṇa ganthasaṅgaha）。Kaccāyanabyākaraṇaṃ、Abhidhānappadīpikāṭīkā 有 nissaya，另做
    "Subodhālaṅkāro",        # 50、51 是本文 + 复注一族，不是单层作品：占位保序号，见 SKIP
    "Subodhālaṅkāraṭīkā",
    "Bālāvatāra",
    "Moggallānasuttapāṭho",
    "Moggallānabyākaraṇaṃ",
    "Mahākaccāyanasaddāpāṭha",
    "Saddanītippakaraṇaṃ (padamālā)",
    "Saddanītippakaraṇaṃ (dhātumālā)",
    "Padarūpasiddhi",
    "Moggallāna pañcikā ṭīkā",
    "Payogasiddhipāḷi",
    "Vuttodayaṃ",
    "Abhidhānappadīpikā",
]

# 留在清单里只为不让后面的序号（= project 名前缀）错位，不规划
SKIP = {"Subodhālaṅkāro", "Subodhālaṅkāraṭīkā"}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().rstrip(".").strip()).lower()


def slug(s):
    """project 名：去掉变音符、括号与空白，只留 ascii 小写与连字符。"""
    a = unicodedata.normalize("NFKD", s)
    a = "".join(c for c in a if not unicodedata.combining(c)).lower()
    a = re.sub(r"\(sangayana-puccha vissajjana\)", "spv", a)
    return re.sub(r"[^a-z0-9]+", "-", a).strip("-")


def resolve():
    """WORKS → [{seq, name, book, start, end, title}]；匹配不上或重名就退出。"""
    rows = all_books()
    idx = {}
    for r in rows:
        idx.setdefault(norm(r.get("toc") or r.get("title")), []).append(r)
    out, bad = [], []
    for i, t in enumerate(WORKS, 1):
        if t in SKIP:
            continue
        hit = idx.get(norm(t), [])
        if len(hit) != 1:
            bad.append(f"  {i:>2} {t}：书目表命中 {len(hit)} 行")
            continue
        r = hit[0]
        lo = int(r["paragraph"])
        hi = next((b for a, b, _t, _f in book_works(r["book"]) if a == lo), 10 ** 9)
        out.append({"seq": i, "name": f"x{i:02d}-{slug(t)}", "book": int(r["book"]),
                    "start": lo, "end": hi, "title": (r.get("toc") or t).strip()})
    if bad:
        sys.exit("作品清单有对不上书目表的：\n" + "\n".join(bad))
    return out


def plan_one(w, args):
    # 只给 plan_scan 一个本文 work：不经族匹配，也就没有注释层可配
    ps.layer_works = lambda book, para=None: [{
        "layer": "mula", "book": w["book"], "start": w["start"], "end": w["end"],
        "title": w["title"], "fam": w["name"]}]
    a = argparse.Namespace(
        book=w["book"], project=w["name"], title=f'{w["title"]} 汉译（藏外·仅本文）',
        channel=args.channel, method=args.method, steps="translate",
        chunk_chars=args.chunk_chars, max_sents=args.max_sents, max_paras=args.max_paras,
        harm_chars=30000, harm_sents=200, harm_ctx=60000, ref_chars=0,
        csv="", dry_run=args.dry_run, align="")
    proj = ps.build(a)
    proj["seq"] = w["seq"]            # 执行顺序，给批量跑的脚本排队用
    if ps.check(proj):
        return None
    return proj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=CHANNEL)
    ap.add_argument("--method", default="default")
    ap.add_argument("--chunk-chars", type=int, default=5000, dest="chunk_chars")
    ap.add_argument("--max-sents", type=int, default=80, dest="max_sents")
    ap.add_argument("--max-paras", type=int, default=0, dest="max_paras")
    ap.add_argument("--only", default="", help="只规划这些序号（逗号分隔，1 起）")
    ap.add_argument("--list", action="store_true", help="只列清单，不规划")
    ap.add_argument("--dry-run", action="store_true", help="只算不落盘")
    ap.add_argument("--force", action="store_true", help="覆盖已有的 project.json")
    args = ap.parse_args()
    if not have_sent_counts() and args.max_paras <= 0:
        args.max_paras = 12

    works = resolve()
    if args.only:
        keep = {int(x) for x in args.only.split(",") if x.strip()}
        works = [w for w in works if w["seq"] in keep]

    if args.list:
        for w in works:
            end = "末" if w["end"] >= 10 ** 9 else w["end"]
            print(f'{w["seq"]:>2}  {w["name"]:<44} book {w["book"]:>3} '
                  f'{w["start"]}-{end}  {w["title"]}')
        return

    fail, rows = [], []
    for w in works:
        print(f'\n══ {w["seq"]:>2} {w["name"]} ══', file=sys.stderr)
        if os.path.exists(pj.path_of(w["name"])) and not args.force and not args.dry_run:
            print("  已有 project.json，跳过（--force 覆盖）", file=sys.stderr)
            continue
        proj = plan_one(w, args)
        if proj is None:
            fail.append(w["name"])
            continue
        L = proj["layers"][0]
        rows.append((w["seq"], w["name"], len(proj["tasks"]), L["paras"], L["chars"], L["sents"]))
        if not args.dry_run:
            pj.save(proj)
            print(f"  → {pj.path_of(w['name'])}", file=sys.stderr)

    print("\n序  project                                      task   段     字符      句")
    for r in rows:
        print(f"{r[0]:>2}  {r[1]:<44} {r[2]:>4} {r[3]:>5} {r[4]:>9,} {r[5]:>7,}")
    if rows:
        print(f"合计 {len(rows)} 部  task {sum(r[2] for r in rows)}  "
              f"字符 {sum(r[4] for r in rows):,}  句 {sum(r[5] for r in rows):,}")
    if fail:
        sys.exit(f"规划失败（未落盘）：{', '.join(fail)}")


if __name__ == "__main__":
    main()
