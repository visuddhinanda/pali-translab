# -*- coding: utf-8 -*-
"""从 export_markdown 的输出里挑出**本项目**写到的书目录，复制进暂存目录。

workspace/export 是历次项目共用的（长部三卷、中部各本都在里面）。发信只该带这一个
项目的书，epub 也只该合并这一个项目的书——所以要先把本项目的目录挑出来。
目录名以导出自己打印的路径为准（`✓ workspace/export/<书>/<章>.md（…）`），不靠书名猜：
书名归一化规则在 export_markdown 里，两处各写一遍迟早对不上。

    python3 scripts/pick_export.py <导出输出日志> <export 根目录> <暂存目录>
"""
import os
import shutil
import sys


def top_dirs(outlog, exp):
    """导出日志 → export 根下的第一层名字集合（可能是目录，也可能是书根直接出的 md）。"""
    got, prefix = set(), exp.rstrip(os.sep) + os.sep
    for line in open(outlog, encoding="utf-8", errors="replace"):
        if not line.lstrip().startswith("✓"):
            continue
        i = line.find(prefix)
        if i < 0:
            continue
        rest = line[i + len(prefix):]
        # 行尾是「（165:4–4，1 句）」这样的中文括号注记，不属于路径
        name = rest.split("（")[0].strip().split(os.sep)[0]
        if name:
            got.add(name)
    return got


def main():
    outlog, exp, stage = sys.argv[1:4]
    names = top_dirs(outlog, exp)
    os.makedirs(stage, exist_ok=True)
    n = 0
    for name in sorted(names):
        src, dst = os.path.join(exp, name), os.path.join(stage, name)
        if not os.path.exists(src):
            print(f"  ⚠ 找不到 {src}", file=sys.stderr)
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        print(f"  收进附件：{name}")
        n += 1
    print(f"共 {n} 项 → {stage}")
    if not n:
        sys.exit("没挑到任何导出目录——附件会是空的，先看导出是否成功")


if __name__ == "__main__":
    main()
