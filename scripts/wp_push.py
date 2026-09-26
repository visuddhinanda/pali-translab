# -*- coding: utf-8 -*-
"""把译文写进 wikipali channel——本项目唯一的译文落盘方式。

从 stdin 读 LLM 的原始输出（可能夹杂代码围栏与旁白），宽松抽出 JSONL，
校验坐标与条数，再交给 `wikipali write` 提交。**不写本地 jsonl。**

一次可提交多段（`--para 983-986`）：坐标按 `id` 里的段号分派，越界的丢弃。
每行至少要有 `zh`（或 `content`），坐标给 `id`（book-para-start-end）
或给 `book`/`paragraph`/`word_start`/`word_end` 四元组。

写入是覆盖式的：同一 (book, paragraph, word_start, word_end, channel) 的旧句子被替换，
没提交的坐标原样保留——所以 revise / harmonize 这类增量步骤**只提交改动过的句子**
（`--at-most N --allow-empty`），不必回传整个 chunk。translate 是整段新建，用 `--expect N`。

`--expect` 缺条时**先写已有的，再报缺的**（退出码 2），不整批拒收：一个 chunk 几十句，
模型漏一两句是常态，为此丢掉几十句已经译好的、再整块重译一遍，是白烧 token。
写入本来就按坐标覆盖，部分写入天然幂等；补译只要重跑缺失坐标所在的**段**即可
（缺失段号写在 `--missing-out` 指定的文件里，给上游重试用）。
**只丢坏数据，不丢好数据**：坐标造假、越界、重复、空译文的行逐条丢弃并列名，
其余照写。条数多于期望不算失败——模型多说几句不构成危害，为此拒收几十句好译文才是损失。
退出码：0 全齐；2 已写入但有缺失；1 真故障（上游吐空、写入失败、读回不符）。

用法：
    claude -p … | python3 scripts/wp_push.py --book 93 --para 983-986 --channel <uid> --expect 40
"""
import argparse
import json
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import jget, parse_paras, run  # noqa: E402

ID_RE = re.compile(r"^(\d+)-(\d+)-(\d+)-(\d+)$")


# 上传切块：一块 ≤ CHUNK_BYTES 字节且 ≤ CHUNK_SENTS 句，**谁先到按谁切**。
# 与规划期的 chunk 是两件事：那个管一次给模型多少内容，这个只管一次往服务端发多少。
# 服务端一次收太多就 500（2026-09-26 实测 19 句起必挂，且返回 500 而不是 4xx），
# 长句子还会先撞体积上限，所以两个条件都要卡。
CHUNK_BYTES, CHUNK_SENTS = 2560, 15


def split_for_upload(sentences, max_bytes=CHUNK_BYTES, max_count=CHUNK_SENTS):
    """按字节与句数切块。单句自己就超体积上限时单独成块——切不动，只能照发。"""
    out, cur, size = [], [], 0
    for s in sentences:
        n = len(json.dumps(s, ensure_ascii=False).encode())
        if cur and (size + n > max_bytes or len(cur) >= max_count):
            out.append(cur)
            cur, size = [], 0
        cur.append(s)
        size += n
    if cur:
        out.append(cur)
    return out


def extract_objects(raw):
    """从可能夹带围栏/旁白的文本里逐行抽出合法 JSON 对象。"""
    rows = []
    for line in raw.splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def to_sentence(obj, book, paras):
    """把一行译文规整成 wikipali 的句子结构；坐标不全或越界的丢弃并报告。"""
    content = obj.get("zh") or obj.get("content")
    if not content or not str(content).strip():
        return None, "译文为空"

    b = p = ws = we = None
    m = ID_RE.match(str(obj.get("id", "")))
    if m:
        b, p, ws, we = (int(x) for x in m.groups())
    if obj.get("word_start") is not None and obj.get("word_end") is not None:
        ws, we = int(obj["word_start"]), int(obj["word_end"])
        b = int(obj.get("book", b if b is not None else book))
        p = int(obj.get("paragraph", p if p is not None else -1))
    if None in (b, p, ws, we):
        return None, "坐标不全"
    if b != book or p not in paras:
        return None, f"坐标越界（{b}:{p} 不在本次范围内）"

    return {
        "book_id": b, "paragraph": p, "word_start": ws, "word_end": we,
        "content": str(content).strip(),
    }, None


def real_coords(book, paras, channel=None, batch=20):
    """真实存在的坐标集合——写之前用它挡掉编造的坐标，写之后用它读回核对。"""
    ch = ["--channel", channel] if channel else []
    got = set()
    for i in range(0, len(paras), batch):
        coords = [f"{book}:{p}" for p in paras[i:i + batch]]
        for x in jget("get", *coords, "--json", *ch):
            got.add((x["paragraph"], x["word_start"], x["word_end"]))
    return got


def report_missing(book, scope, miss, missing_out):
    """缺条报告：列出缺的句子坐标，并把它们所在的**段号**写给上游，只补这些段。"""
    ids = ", ".join(f"{book}-{p}-{a}-{b}" for p, a, b in miss)
    print(f"⚠ {scope} 缺 {len(miss)} 句未提交：{ids}", file=sys.stderr)
    mparas = sorted({p for p, _a, _b in miss})
    if missing_out:
        with open(missing_out, "w", encoding="utf-8") as f:
            f.write(",".join(str(p) for p in mparas) + "\n")
    print(f"  缺失落在段 {','.join(str(p) for p in mparas)}——只需重跑这些段", file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--para", required=True, help="段号：984 / 983-986 / 983,985-987")
    ap.add_argument("--channel", required=True, help="目标 channel（uid / 序号 / 名字片段）")
    ap.add_argument("--expect", type=int, default=0, help="期望条数，不符则拒绝写入（整段重写用，如 translate）")
    ap.add_argument("--at-most", type=int, default=0, dest="at_most",
                    help="上限条数（增量写入用，如 revise / harmonize：只提交改动过的句子）")
    ap.add_argument("--allow-empty", action="store_true",
                    help='允许上游用 {"no_change": true} 声明「一句都不用改」（增量写入的正常结果）；'
                         "空输出仍算失败")
    ap.add_argument("--content-type", default="markdown")
    ap.add_argument("--batch", type=int, default=CHUNK_SENTS, dest="batch",
                    help=f"一块最多几句（默认 {CHUNK_SENTS}）")
    ap.add_argument("--chunk-bytes", type=int, default=CHUNK_BYTES, dest="chunk_bytes",
                    help=f"一块最多多少字节（默认 {CHUNK_BYTES}）；与句数上限谁先到按谁切")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-verify", action="store_true", help="跳过写后读回核对")
    ap.add_argument("--expect-ids", default="", dest="expect_ids",
                    help="期望坐标清单文件（每行一个 book-para-ws-we）。缺条时用它算缺的是哪几句；"
                         "不给则退回用原文全部坐标，那会把「没有巴利原文、本就不该译」的坐标算成缺失")
    ap.add_argument("--missing-out", default="", dest="missing_out",
                    help="把缺失坐标所在的**段号**写进这个文件（逗号分隔），给上游只补这些段")
    ap.add_argument("--ignore-foreign", action="store_true",
                    help="静默跳过不属于本次 book/para 范围的行（跨层统稿时一份输出要分多次提交）")
    args = ap.parse_args()

    paras = set(parse_paras(args.para))
    ordered = sorted(paras)
    scope = f"{args.book}:{ordered[0]}-{ordered[-1]}"

    rows = extract_objects(sys.stdin.read())
    # 「一句都不用改」必须由上游显式声明 {"no_change": true}——空输出一律当上游失败。
    # 历史上 claude -p 撞额度时就是干净地吐空，把空当成「无需改动」会把故障洗成成功。
    if args.allow_empty and any(r.get("no_change") for r in rows):
        print(f"✓ {scope} 上游声明无需改动，未写入", file=sys.stderr)
        return
    rows = [r for r in rows if not r.get("no_change")]
    if not rows:
        sys.exit("没有抽到任何 JSONL 行——上游可能失败了")

    sentences, dropped = [], []
    for obj in rows:
        s, why = to_sentence(obj, args.book, paras)
        if s is None:
            if args.ignore_foreign and "越界" in why:
                continue
            dropped.append(f"{obj.get('id')}：{why}")
        else:
            sentences.append(s)

    # 同一坐标重复：留第一条，其余丢弃。**丢的是坏数据，不牵连好数据。**
    seen, uniq = set(), []
    for s in sentences:
        k = (s["paragraph"], s["word_start"], s["word_end"])
        if k in seen:
            dropped.append(f"{s['book_id']}-{k[0]}-{k[1]}-{k[2]}：同一坐标重复提交")
        else:
            seen.add(k)
            uniq.append(s)
    sentences = uniq

    valid = real_coords(args.book, ordered)
    if valid:
        keep = []
        for s in sentences:
            if (s["paragraph"], s["word_start"], s["word_end"]) in valid:
                keep.append(s)
            else:
                dropped.append(f"{s['book_id']}-{s['paragraph']}-{s['word_start']}-{s['word_end']}：坐标不存在于原文")
        sentences = keep

    for d in dropped:
        print(f"  丢弃 {d}", file=sys.stderr)

    # 条数对不上**不是拒收的理由**。坏数据（坐标造假、越界、重复、空译文）在上面
    # 逐条丢干净了，剩下的每一条都验过真、都能写。多出来只说明模型多说了几句，
    # 那不构成危害；为此丢掉几十句好译文才是真损失。只记一行提醒。
    if args.expect and len(sentences) > args.expect:
        print(f"  提醒：{scope} 期望 {args.expect} 句，实收 {len(sentences)} 句（多出的已验真，照写）",
              file=sys.stderr)
    if args.at_most and len(sentences) > args.at_most:
        print(f"  提醒：{scope} 增量步骤至多 {args.at_most} 句，实收 {len(sentences)} 句"
              f"（上游可能回传了未改动的句子；已验真，照写）", file=sys.stderr)
    if not sentences:
        # 跨层统稿是一份输出分多次提交：本层一句都没改是正常的（别层改了）。
        # 上游整个吐空已在前面拦掉，这里只可能是「本层无改动」。
        if args.allow_empty:
            print(f"✓ {scope} 本层无改动，未写入", file=sys.stderr)
            return
        sys.exit(f"没有可写的句子：{scope}")

    # 缺条：先算，写完再报。整批拒收会连带丢掉已经译好的几十句，而写入是按坐标覆盖的，
    # 补译时重写一遍毫无副作用。缺失坐标 = 期望坐标 − 本次提交的坐标；期望坐标优先用
    # --expect-ids（上游 wp_pull 实际给出的可译句），退回原文全部坐标只是兜底。
    want = valid
    if args.expect_ids:
        want = set()
        for line in open(args.expect_ids, encoding="utf-8"):
            m = ID_RE.match(line.strip())
            if m:
                b, p, ws, we = (int(x) for x in m.groups())
                if b == args.book:
                    want.add((p, ws, we))
    miss = []
    if args.expect and want:
        sent = {(x["paragraph"], x["word_start"], x["word_end"]) for x in sentences}
        miss = sorted(want - sent)

    for s in sentences:
        s["content_type"] = args.content_type
    blocks = split_for_upload(sentences, args.chunk_bytes, args.batch)
    if len(blocks) > 1:
        print(f"分 {len(blocks)} 块上传（每块 ≤{args.chunk_bytes} 字节 / ≤{args.batch} 句）",
              file=sys.stderr)
    sent_n = 0
    for i, blk in enumerate(blocks, 1):
        payload = json.dumps({"sentences": blk}, ensure_ascii=False)
        # 块已经切好，CLI 不必再分：--batch 给本块的实际条数
        cmd = ["write", "-", "--channel", args.channel, "--batch", str(len(blk)), "-y"]
        if args.dry_run:
            cmd.append("--dry-run")
        r = run(cmd, stdin=payload, check=False)
        sys.stderr.write(r.stderr)
        print(r.stdout, end="")
        if r.returncode != 0:
            # 写入按坐标覆盖，前面的块已经落地不必回滚；报清楚写到哪里，重跑即可补齐
            sys.exit(f"写入失败：{scope} 第 {i}/{len(blocks)} 块"
                     f"（已写 {sent_n}/{len(sentences)} 句）")
        sent_n += len(blk)
    if args.dry_run:
        if miss:
            report_missing(args.book, scope, miss, args.missing_out)
        return

    if not args.no_verify:
        got = real_coords(args.book, ordered, channel=args.channel)
        missing = [s for s in sentences
                   if (s["paragraph"], s["word_start"], s["word_end"]) not in got]
        if missing:
            ids = ", ".join(f"{s['paragraph']}-{s['word_start']}-{s['word_end']}" for s in missing)
            sys.exit(f"读回核对：{len(missing)} 句没写进去（{ids}）")

    print(f"✓ {scope} 已写入 {len(sentences)} 句 → channel {args.channel}", file=sys.stderr)

    if miss:
        report_missing(args.book, scope, miss, args.missing_out)


if __name__ == "__main__":
    main()
