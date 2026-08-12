# -*- coding: utf-8 -*-
"""把译文写进 wikipali channel——本项目唯一的译文落盘方式。

从 stdin 读 LLM 的原始输出（可能夹杂代码围栏与旁白），宽松抽出 JSONL，
校验坐标与条数，再交给 `wikipali write` 提交。**不写本地 jsonl。**

一次可提交多段（`--para 983-986`）：坐标按 `id` 里的段号分派，越界的丢弃。
每行至少要有 `zh`（或 `content`），坐标给 `id`（book-para-start-end）
或给 `book`/`paragraph`/`word_start`/`word_end` 四元组。

写入是覆盖式的：同一 (book, paragraph, word_start, word_end, channel) 的旧句子被替换。

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, required=True)
    ap.add_argument("--para", required=True, help="段号：984 / 983-986 / 983,985-987")
    ap.add_argument("--channel", required=True, help="目标 channel（uid / 序号 / 名字片段）")
    ap.add_argument("--expect", type=int, default=0, help="期望条数，不符则拒绝写入")
    ap.add_argument("--content-type", default="markdown")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-verify", action="store_true", help="跳过写后读回核对")
    ap.add_argument("--ignore-foreign", action="store_true",
                    help="静默跳过不属于本次 book/para 范围的行（跨层统稿时一份输出要分多次提交）")
    args = ap.parse_args()

    paras = set(parse_paras(args.para))
    ordered = sorted(paras)
    scope = f"{args.book}:{ordered[0]}-{ordered[-1]}"

    rows = extract_objects(sys.stdin.read())
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

    if args.expect and len(sentences) != args.expect:
        sys.exit(f"条数不符：期望 {args.expect}，可写 {len(sentences)}——拒绝写入 {scope}")
    if not sentences:
        sys.exit(f"没有可写的句子：{scope}")

    for s in sentences:
        s["content_type"] = args.content_type
    payload = json.dumps({"sentences": sentences}, ensure_ascii=False)

    cmd = ["write", "-", "--channel", args.channel, "--batch", str(args.batch), "-y"]
    if args.dry_run:
        cmd.append("--dry-run")
    r = run(cmd, stdin=payload, check=False)
    sys.stderr.write(r.stderr)
    print(r.stdout, end="")
    if r.returncode != 0:
        sys.exit(f"写入失败：{scope}")
    if args.dry_run:
        return

    if not args.no_verify:
        got = real_coords(args.book, ordered, channel=args.channel)
        missing = [s for s in sentences
                   if (s["paragraph"], s["word_start"], s["word_end"]) not in got]
        if missing:
            ids = ", ".join(f"{s['paragraph']}-{s['word_start']}-{s['word_end']}" for s in missing)
            sys.exit(f"读回核对：{len(missing)} 句没写进去（{ids}）")

    print(f"✓ {scope} 已写入 {len(sentences)} 句 → channel {args.channel}", file=sys.stderr)


if __name__ == "__main__":
    main()
