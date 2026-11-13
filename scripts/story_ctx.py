# -*- coding: utf-8 -*-
"""故事型计划（plan_story.py，variant story）的执行期辅助：注入块与照抄。

子命令：
  names-check  < 模型输出      校验 names 产物（JSONL：pali / forms / type / zh），合格的行写到 stdout
  names-block  --plan --task   本块出现的人名地名（全部 names 产物合并后按词形过滤）
  gloss-block  --plan --task --channel
                               本文自译块各偈在义注里的黑体解释（巴利 + 义注定稿译文）
  vcopy        --plan --task --channel [--dry-run]
                               本文照抄组：把义注引偈的定稿逐句抄到本文（经 wp_push 写入、读回核对）

人名地名表 = workspace/projects/<name>/names/*.jsonl 合并：同一 pali 原形取出现次数
最多的译名，平手取最先出现的（names task 按义注顺序编号）。合并结果落 names.json，
冲突落 names_conflicts.json 供人工过目。
"""
import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QUOTE_EDGE = "“”‘’「」『』\"'"


def load_plan(path):
    return json.load(open(path, encoding="utf-8"))


def find(plan, tid):
    t = next(x for x in plan["tasks"] if x["id"] == tid)
    ch = None
    for m in plan.get("layers", []):
        for c in m.get("chunks", []):
            if tid.startswith(c["id"] + ":"):
                ch = c
    return t, ch


def home(plan_path):
    return os.path.dirname(os.path.abspath(plan_path))


def pull(book, plist, channel=None, nissaya=False):
    cmd = [sys.executable, os.path.join(HERE, "wp_pull.py"), "--book", str(book),
           "--para", ",".join(str(p) for p in plist)]
    if channel:
        cmd += ["--channel", channel]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return [json.loads(x) for x in out.splitlines() if x.startswith("{")]


def cached_text(book, plist):
    """规划期缓存的原文（P1）；缓存不在就现拉。"""
    want = set(int(p) for p in plist)
    p = os.path.join(os.path.dirname(HERE), "workspace", "cache", f"text_{book}.jsonl")
    if os.path.exists(p):
        rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.startswith("{")]
        return [r for r in rows if int(r.get("paragraph", 0)) in want]
    return pull(book, sorted(want))


# ══════════ names ══════════

def cmd_names_check(_args):
    good, bad = 0, 0
    for line in sys.stdin:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if not (isinstance(r.get("pali"), str) and r["pali"].strip()
                and isinstance(r.get("zh"), str) and r["zh"].strip()
                and r.get("type") in ("人名", "地名")):
            bad += 1
            continue
        forms = r.get("forms") if isinstance(r.get("forms"), list) else []
        out = {"pali": r["pali"].strip(), "type": r["type"], "zh": r["zh"].strip(),
               "forms": sorted({f.strip() for f in forms + [r["pali"]] if isinstance(f, str) and f.strip()})}
        print(json.dumps(out, ensure_ascii=False))
        good += 1
    print(f"names：合格 {good} 行，丢弃 {bad} 行", file=sys.stderr)
    if good == 0:
        sys.exit(1)


def merge_names(plan, plan_path):
    """合并全部 names 产物 → names.json（按需重建：有更新的产物就重做）。"""
    h = home(plan_path)
    want = [n["id"] for n in plan.get("story", {}).get("names", [])]
    files = {i: os.path.join(h, "names", f"{i}.jsonl") for i in want}
    missing = [i for i, f in files.items() if not os.path.exists(f)]
    if missing:
        sys.exit(f"人名地名表还不全：缺 {', '.join(missing[:8])}{' …' if len(missing) > 8 else ''}")
    out = os.path.join(h, "names.json")
    newest = max(os.path.getmtime(f) for f in files.values())
    if os.path.exists(out) and os.path.getmtime(out) >= newest:
        return json.load(open(out, encoding="utf-8"))
    votes, forms, kind, first = {}, {}, {}, {}
    order = 0
    for i in want:
        for line in open(files[i], encoding="utf-8"):
            if not line.startswith("{"):
                continue
            r = json.loads(line)
            k = r["pali"].lower()
            votes.setdefault(k, collections.Counter())[r["zh"]] += 1
            forms.setdefault(k, set()).update(r.get("forms") or [])
            kind.setdefault(k, r["type"])
            first.setdefault((k, r["zh"]), order)
            order += 1
    table, conflicts = [], []
    for k, c in votes.items():
        best = sorted(c.items(), key=lambda kv: (-kv[1], first[(k, kv[0])]))
        table.append({"pali": k, "type": kind[k], "zh": best[0][0], "forms": sorted(forms[k])})
        if len(best) > 1:
            conflicts.append({"pali": k, "chosen": best[0][0], "votes": dict(c)})
    table.sort(key=lambda r: r["pali"])
    tmp = out + ".tmp"
    json.dump(table, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    os.replace(tmp, out)
    cf = os.path.join(h, "names_conflicts.json")
    json.dump(conflicts, open(cf + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(cf + ".tmp", cf)
    return table


def words_of(text):
    t = text.replace("**", "").lower()
    return set(re.findall(r"[a-zāīūṅñṭḍṇḷṃ]+", t))


def stem(w):
    w = w.lower()
    return w[:-1] if len(w) > 4 else w


def cmd_names_block(args):
    plan = load_plan(args.plan)
    table = merge_names(plan, args.plan)
    t, ch = find(plan, args.task)
    skip = set((ch or {}).get("skip") or [])
    plist = [p for p in range(t["start"], t["end"] + 1) if p not in skip]
    ws = set()
    for r in cached_text(t["book"], plist):
        ws |= words_of(r.get("pali", ""))
    hit = []
    for r in table:
        fs = {f.lower() for f in r["forms"]}
        if fs & ws or any(w.startswith(stem(r["pali"])) for w in ws):
            hit.append(r)
    if not hit:
        return
    print("\n---人名地名表（本块出现的专名；译名必须照此统一，不得另译）---")
    for r in hit:
        print(json.dumps({"pali": r["pali"], "type": r["type"], "zh": r["zh"]}, ensure_ascii=False))


# ══════════ gloss ══════════

def cmd_gloss_block(args):
    plan = load_plan(args.plan)
    _t, ch = find(plan, args.task)
    gl = (ch or {}).get("gloss") or []
    if not gl:
        return
    ab = next(m["book"] for m in plan["layers"] if m["layer"] == "atthakatha")
    verse = {sid: n for n, sid in gl}
    plist = sorted({int(sid.split("-")[1]) for sid in verse})
    rows = [r for r in pull(ab, plist, args.channel) if r.get("id") in verse]
    if not rows:
        return
    print(f"\n---义注对本块偈颂的解释（book={ab}；黑体为被解释词，zh 为义注定稿译文。"
          "**义注定释义**：本文偈颂的理解与用词要与之相符）---")
    for r in rows:
        print(json.dumps({"verse": verse[r["id"]], "id": r["id"], "pali": r["pali"],
                          "zh": r.get("zh", "")}, ensure_ascii=False))


# ══════════ vcopy ══════════

def clean(zh, last):
    """引文的引号是义注的，抄进本文要去掉；偈尾的逗号改句号。"""
    s = zh.replace("**", "").strip().strip(QUOTE_EDGE).strip()   # 引偈在义注里常整句加黑
    if last:
        s = s.rstrip("，、；：,;:").rstrip(QUOTE_EDGE)
        if s and s[-1] not in "。！？…":
            s += "。"
    return s


def cmd_vcopy(args):
    plan = load_plan(args.plan)
    t, ch = find(plan, args.task)
    pairs = ch.get("vcopy") or []
    ab = next(m["book"] for m in plan["layers"] if m["layer"] == "atthakatha")
    aps = sorted({int(a.split("-")[1]) for _m, aids, _l in pairs for a in aids})
    zh = {r["id"]: r.get("zh", "") for r in pull(ab, aps, args.channel)}
    miss = [a for _m, aids, _l in pairs for a in aids if not zh.get(a)]
    if miss:
        sys.exit(f"义注引偈还没有译文：{miss[:5]}（共 {len(miss)} 句）")
    lines, mids = [], []
    for mid, aids, last in pairs:
        text = "".join(clean(zh[a], last and j == len(aids) - 1) for j, a in enumerate(aids))
        lines.append(json.dumps({"id": mid, "zh": text}, ensure_ascii=False))
        mids.append(mid)
    mps = sorted({int(m.split("-")[1]) for m in mids})
    cmd = [sys.executable, os.path.join(HERE, "wp_push.py"), "--book", str(t["book"]),
           "--para", ",".join(map(str, mps)), "--channel", args.channel,
           "--expect", str(len(lines))]
    if args.dry_run:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, input="\n".join(lines) + "\n", text=True)
    sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("names-check")
    for name in ("names-block", "gloss-block", "vcopy"):
        p = sub.add_parser(name)
        p.add_argument("--plan", required=True)
        p.add_argument("--task", required=True)
        if name != "names-block":
            p.add_argument("--channel", required=True)
        if name == "vcopy":
            p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    {"names-check": cmd_names_check, "names-block": cmd_names_block,
     "gloss-block": cmd_gloss_block, "vcopy": cmd_vcopy}[a.cmd](a)


if __name__ == "__main__":
    main()
