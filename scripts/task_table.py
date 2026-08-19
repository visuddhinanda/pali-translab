# -*- coding: utf-8 -*-
"""把作业计划展开成**实跑粒度**的任务分配表。

主任务表（tasks.csv）一行一个作业，看不出里面在干什么；一个作业跑两三小时，
中间毫无可见进展。这张表把作业摊开到实际会发生的每一次调用上：

    作业 3            本文一章 + 归它翻译的注释章
    └ 层 3.2          义注 Cūḷasīlavaṇṇanā（own）/ 或标 ref 只读不译
      └ 分块 3.2.1    103:323-334 —— 一次 translate + 一次 review + 一次 revise
      └ 分块 3.2.2    …
    └ 统稿 3.H        跨层，超过阈值则按层分批
    └ 导出 3.E        每层一个 md

行的粒度就是**一次 claude 调用**的粒度，所以「预计调用数」那列加起来
就是这次全书任务的总调用量。

用法：
    python3 scripts/task_table.py --plan workspace/plan_93.json --out workspace/task_alloc.csv
"""
import argparse
import csv
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _wp import chunk_paras, para_chars  # noqa: E402

COLS = ["编号", "类型", "状态", "层次", "坐标", "名称", "归属",
        "段数", "字符数", "预计调用", "开始时间", "完成时间", "耗时", "备注"]
LAYER_CN = {"mula": "本文", "atthakatha": "义注", "tika": "复注"}


def rows_for_job(job, budget, max_paras, harmonize_max):
    jid = job["id"]
    m = job["mula"]                      # 前置作业没有本文层，m 为 None
    groups = ([(m, 1)] if m else []) + [(e, 1) for e in job["own"]] + [(e, 0) for e in job["ref"]]

    own_paras = own_chars = own_calls = 0
    out = []
    sub = 0
    for e, own in groups:
        sub += 1
        plist = list(range(e["start"], e["end"] + 1))
        chars = para_chars(e["book"])
        gchars = sum(chars.get(p, 0) for p in plist)
        layer = LAYER_CN.get(e["layer"], e["layer"])
        tag = "own 翻译" if own else "ref 只读"

        if not own:
            # 参考层不翻译，只在 review/统稿时读；不产生调用
            out.append({"编号": f"{jid}.{sub}", "类型": "层", "状态": "⬜ 未开始",
                        "层次": layer, "坐标": f'{e["book"]}:{e["start"]}-{e["end"]}',
                        "名称": e.get("title", ""), "归属": tag,
                        "段数": len(plist), "字符数": gchars, "预计调用": 0,
                        "开始时间": "", "完成时间": "", "耗时": "", "备注": "只读参考，归别的作业翻译"})
            continue

        chunks = chunk_paras(e["book"], plist, budget, max_paras)
        calls = len(chunks) * 4          # translate + review + revise + evaluate
        own_paras += len(plist); own_chars += gchars; own_calls += calls
        out.append({"编号": f"{jid}.{sub}", "类型": "层", "状态": "⬜ 未开始",
                    "层次": layer, "坐标": f'{e["book"]}:{e["start"]}-{e["end"]}',
                    "名称": e.get("title", ""), "归属": tag,
                    "段数": len(plist), "字符数": gchars, "预计调用": calls,
                    "开始时间": "", "完成时间": "", "耗时": "",
                    "备注": f"{len(chunks)} 个分块"})
        for k, c in enumerate(chunks, 1):
            out.append({"编号": f"{jid}.{sub}.{k}", "类型": "分块", "状态": "⬜ 未开始",
                        "层次": layer, "坐标": f'{e["book"]}:{c[0]}-{c[-1]}',
                        "名称": "", "归属": tag, "段数": len(c),
                        "字符数": sum(chars.get(p, 0) for p in c), "预计调用": 4,
                        "开始时间": "", "完成时间": "", "耗时": "",
                        "备注": "translate/review/revise/evaluate 各一次"})

    # 统稿：小作业一次跨层；超阈值按层分批，每个注释层的每个分块各一次
    batched = own_paras > harmonize_max
    if batched:
        hcalls = sum(1 for e in job["own"] if e["layer"] != "mula"
                     for _ in chunk_paras(e["book"],
                                          list(range(e["start"], e["end"] + 1)),
                                          budget, max_paras))
        note = f"超过 {harmonize_max} 段，按层分批"
    else:
        hcalls, note = 1, "一次跨层统稿"
    anchor = m or job["own"][0]
    out.append({"编号": f"{jid}.H", "类型": "统稿", "状态": "⬜ 未开始",
                "层次": "跨层" if m else "义注↔复注",
                "坐标": f'{anchor["book"]}:{anchor["start"]}-{anchor["end"]}'
                        + (" +注释" if m else ""),
                "名称": anchor["title"], "归属": "own 翻译", "段数": own_paras,
                "字符数": own_chars, "预计调用": hcalls,
                "开始时间": "", "完成时间": "", "耗时": "", "备注": note})

    nexp = (1 if m else 0) + len(job["own"])
    out.append({"编号": f"{jid}.E", "类型": "导出", "状态": "⬜ 未开始", "层次": "各层",
                "坐标": "", "名称": anchor["title"], "归属": "own 翻译", "段数": own_paras,
                "字符数": "", "预计调用": 0, "开始时间": "", "完成时间": "", "耗时": "",
                "备注": f"{nexp} 个 md 文件"})

    head = {"编号": str(jid), "类型": "作业", "状态": "⬜ 未开始",
            "层次": "本文章" if m else "注释书开头",
            "坐标": f'{anchor["book"]}:{anchor["start"]}-{anchor["end"]}',
            "名称": anchor["title"],
            "归属": "own 翻译", "段数": own_paras, "字符数": own_chars,
            "预计调用": own_calls + hcalls, "开始时间": "", "完成时间": "", "耗时": "",
            "备注": job.get("note") or
                    f'{len(job["own"])} 个注释章 own，{len(job["ref"])} 个 ref'}
    return [head] + out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default="workspace/task_alloc.csv")
    ap.add_argument("--chunk-chars", type=int, default=5000)
    ap.add_argument("--max-paras", type=int, default=12)
    ap.add_argument("--harmonize-max", type=int, default=300)
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding="utf-8"))
    rows = []
    for job in plan["jobs"]:
        rows += rows_for_job(job, args.chunk_chars, args.max_paras, args.harmonize_max)

    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)

    kinds = {}
    for r in rows:
        kinds[r["类型"]] = kinds.get(r["类型"], 0) + 1
    calls = sum(r["预计调用"] for r in rows if r["类型"] in ("分块", "统稿"))
    print(f"→ {args.out}")
    print("  行数：" + "，".join(f"{k} {v}" for k, v in kinds.items()) + f"，合计 {len(rows)}")
    print(f"  预计 claude 调用总数：{calls}")


if __name__ == "__main__":
    main()
