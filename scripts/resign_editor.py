# -*- coding: utf-8 -*-
"""把 channel 里署名错的句子改回正确署名：原样读回、原样写回，内容一个字不动。

为什么需要它：句子的 editor 由**模型身份 token** 决定。别处跑过 `wikipali ensure-model`
把身份换成别的名字，之后写入的全部句子就都署了那个名字（2026-09-14 实测：三万句署成了
另一个模型）。译文本身没问题，只是署名错，所以修正手段就是**同内容覆盖写**——
写入按坐标覆盖，内容一致时除了 editor 与 updated_at 之外什么都不变。

这是**纯数据搬运，不经模型**：读回什么就写回什么，不做任何改写。

安全绳：
  · `--dry-run` 只报会改多少、哪些坐标，不发写请求
  · 每个区间写完重读、比对内容哈希，不一致立即停下（默认开，`--no-verify` 可关）
  · 进度写 `--state`，中断续跑跳过已完成区间
  · 切块规则与 wp_push 一致（≤2.5KB 且 ≤15 句，谁先到按谁切）——服务端一次收太多会 500

用法：
    # 先看会改什么，不写
    python3 scripts/resign_editor.py --channel <uid> --book 169 --from 3 --to 1467 --dry-run
    # 真改，按区间表、带进度
    python3 scripts/resign_editor.py --channel <uid> --tasks t.json --state s.json
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _wp import _exe, jget  # noqa: E402
from wp_push import CHUNK_BYTES, CHUNK_SENTS, split_for_upload  # noqa: E402


def digest(rows):
    """只对坐标与内容取哈希——editor / updated_at 本来就要变，不能进哈希。"""
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: (r["paragraph"], r["word_start"], r["word_end"])):
        h.update(f"{r['paragraph']}-{r['word_start']}-{r['word_end']}:{r['content']}\n".encode())
    return h.hexdigest()[:16]


def read_paras(book, paras, channel, read_batch):
    out = []
    for i in range(0, len(paras), read_batch):
        coords = [f"{book}:{p}" for p in paras[i:i + read_batch]]
        out += jget("get", *coords, "--json", "--channel", channel)
    return out


def write_blocks(rows, channel, max_bytes, max_count):
    """按块提交。中途失败不回滚：写入按坐标覆盖，重跑补齐即可。"""
    payload = [{"book_id": r["book"], "paragraph": r["paragraph"],
                "word_start": r["word_start"], "word_end": r["word_end"],
                "content": r["content"]} for r in rows]
    blocks = split_for_upload(payload, max_bytes, max_count)
    done = 0
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        for i, blk in enumerate(blocks, 1):
            json.dump(blk, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
            r = subprocess.run([_exe(), "write", tmp, "--channel", channel,
                                "--batch", str(len(blk)), "-y"],
                               capture_output=True, text=True)
            if r.returncode != 0 or "确认写入" not in r.stdout:
                last = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
                print(f"    ✗ 第 {i}/{len(blocks)} 块失败："
                      f"{last[-1][:120] if last else 'rc=%d' % r.returncode}")
                return done, len(blocks), False
            done += len(blk)
        return done, len(blocks), True
    finally:
        os.unlink(tmp)


def plan_of(rows, want, max_bytes, max_count):
    bad = [r for r in rows if r["editor"]["nickName"] != want]
    payload = [{"book_id": r["book"], "paragraph": r["paragraph"],
                "word_start": r["word_start"], "word_end": r["word_end"],
                "content": r["content"]} for r in bad]
    return bad, split_for_upload(payload, max_bytes, max_count) if payload else []


def handle(book, lo, hi, args, state, key):
    paras = list(range(lo, hi + 1))
    if args.only_paras:                      # 只读已知有问题的段，省掉大量请求
        paras = [p for p in paras if p in args.only_paras.get(str(book), set())]
        if not paras:
            state[key] = "done"
            return True, 0, 0
    rows = read_paras(book, paras, args.channel, args.read_batch)
    bad, blocks = plan_of(rows, args.want, args.chunk_bytes, args.batch)
    nicks = {}
    for r in bad:
        nicks[r["editor"]["nickName"]] = nicks.get(r["editor"]["nickName"], 0) + 1
    tag = f"{book}:{lo}-{hi}"
    if args.dry_run:
        print(f"  {tag}｜读 {len(rows)} 句，需改 {len(bad)} 句，"
              f"将分 {len(blocks)} 块写（≤{args.chunk_bytes}B/≤{args.batch}句）"
              f"｜现署名 {nicks or '—'}", flush=True)
        if bad[:3] and args.show_samples:
            for r in bad[:3]:
                print(f"      例 {r['book']}-{r['paragraph']}-{r['word_start']}-{r['word_end']}"
                      f"：{r['content'][:40]}")
        return True, len(bad), len(blocks)
    if not bad:
        print(f"  {tag}｜{len(rows)} 句全部署名正确，跳过", flush=True)
        state[key] = "done"
        return True, 0, 0
    before = digest(rows)
    n, nblk, ok = write_blocks(bad, args.channel, args.chunk_bytes, args.batch)
    if not ok:
        print(f"  {tag}｜写入中断（已写 {n}/{len(bad)} 句），进度不记，重跑可补", flush=True)
        return False, n, nblk
    if not args.no_verify:
        after = read_paras(book, paras, args.channel, args.read_batch)
        if digest(after) != before:
            print(f"  {tag}｜✗ 内容哈希不符（{before} → {digest(after)}），停下", flush=True)
            return False, n, nblk
        left = [r for r in after if r["editor"]["nickName"] != args.want]
        print(f"  {tag}｜✓ 改 {n} 句（{nblk} 块），内容一致，剩余署名错 {len(left)}", flush=True)
    else:
        print(f"  {tag}｜✓ 改 {n} 句（{nblk} 块），未校验", flush=True)
    state[key] = "done"
    return True, n, nblk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, help="目标 channel uid")
    ap.add_argument("--want", default="claude-opus-5", help="正确的署名（默认 claude-opus-5）")
    ap.add_argument("--book", type=int, help="单本书：与 --from/--to 一起用")
    ap.add_argument("--from", dest="start", type=int, help="起始段")
    ap.add_argument("--to", dest="end", type=int, help="结束段")
    ap.add_argument("--tasks", help="区间表 json：[[book, 起, 止], …]")
    ap.add_argument("--scan", help="只读扫描结果 json，用它跳过没有问题的段（省请求）")
    ap.add_argument("--state", default="", help="进度文件；不给则不记进度")
    ap.add_argument("--chunk-bytes", type=int, default=CHUNK_BYTES, dest="chunk_bytes",
                    help=f"一块最多字节（默认 {CHUNK_BYTES}）")
    ap.add_argument("--batch", type=int, default=CHUNK_SENTS,
                    help=f"一块最多句数（默认 {CHUNK_SENTS}）")
    ap.add_argument("--read-batch", type=int, default=20, dest="read_batch",
                    help="一次读几段（默认 20）")
    ap.add_argument("--dry-run", action="store_true", help="只报会改什么，不发写请求")
    ap.add_argument("--show-samples", action="store_true", help="dry-run 时每区间打几条样例")
    ap.add_argument("--no-verify", action="store_true", dest="no_verify",
                    help="跳过写后重读比对（不建议）")
    args = ap.parse_args()

    if args.tasks:
        tasks = [tuple(x) for x in json.load(open(args.tasks))]
    elif args.book and args.start and args.end:
        tasks = [(args.book, args.start, args.end)]
    else:
        sys.exit("要给 --tasks，或 --book 加 --from/--to")

    args.only_paras = {}
    if args.scan:
        sc = json.load(open(args.scan))
        args.only_paras = {b: set(v) for b, v in sc.get("bad_paras", {}).items()}

    state = {}
    if args.state and os.path.exists(args.state):
        state = json.load(open(args.state))

    t0 = time.time()
    tot_bad = tot_blk = 0
    for book, lo, hi in tasks:
        key = f"{book}:{lo}-{hi}"
        if state.get(key) == "done":
            continue
        ok, nbad, nblk = handle(book, lo, hi, args, state, key)
        tot_bad += nbad
        tot_blk += nblk
        if args.state and not args.dry_run:
            json.dump(state, open(args.state, "w"), ensure_ascii=False)
        if not ok:
            sys.exit(1)
    what = "将改" if args.dry_run else "已改"
    print(f"{what} {tot_bad} 句 / {tot_blk} 块，用时 {(time.time()-t0)/60:.1f} 分钟"
          + ("（dry-run，未写任何东西）" if args.dry_run else ""), flush=True)


if __name__ == "__main__":
    main()
