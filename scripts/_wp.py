# -*- coding: utf-8 -*-
"""wikipali CLI 的共用薄封装。只依赖标准库。

本项目所有数据读写都经 wikipali 插件的 `wikipali` 命令，不直连 HTTP、不读本地语料。
"""
import html
import json
import re
import shutil
import subprocess
import sys

PALI_UID = "00b577c0-13b9-11ee-a05a-b7307efd9ee6"  # _System_Pali_VRI_
TAG_RE = re.compile(r"<[^>]+>")
# 黑体在义注/复注里是**被解释词**（引自上一层），必须保住——剥成纯文本就看不出注的是哪个词
BOLD_RE = re.compile(r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>", re.S | re.I)
# <code> 里是版本页码标记（M1.219 / V1.298），不是正文，去掉整段
CODE_RE = re.compile(r"<code\b[^>]*>.*?</code>", re.S | re.I)

_NOT_FOUND = (
    "找不到 wikipali 命令。请先安装 wikipali 插件（/plugin），"
    "或用 ${CLAUDE_PLUGIN_ROOT}/bin/wikipali；刚装好需重启会话让 PATH 生效。"
)


def run(args, stdin=None, check=True):
    exe = shutil.which("wikipali")
    if not exe:
        sys.exit(_NOT_FOUND)
    r = subprocess.run([exe, *args], input=stdin, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"wikipali {' '.join(args)} 失败：\n{r.stderr.strip()}")
    return r


def jget(*args):
    """跑一条 wikipali 命令并解析 JSON；解析不了就当空。"""
    try:
        return json.loads(run(list(args)).stdout or "[]")
    except json.JSONDecodeError:
        return []


def plain(rec):
    """取句子文本。

    html 型：先摘掉版本页码 `<code>`，把黑体转成 `**…**`（被解释词的唯一线索），再去其余标签。
    markdown 型：原样返回（译文里的行内标记要保留）。
    """
    text = rec.get("content") or ""
    if (rec.get("content_type") or "").lower() in ("html", ""):
        text = CODE_RE.sub("", text)
        text = BOLD_RE.sub(lambda m: f"**{m.group(1).strip()}**", text)
        text = TAG_RE.sub("", text)
    return html.unescape(re.sub(r"[ \t]+", " ", text)).strip()


def parse_paras(spec):
    """段号区间：'984' / '983-986' / '983,985-987' → 有序去重列表。"""
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part.lstrip("-"):
            lo, hi = part.split("-", 1)
            lo, hi = int(lo), int(hi)
            if hi < lo:
                sys.exit(f"段号区间反了：{part}")
            out += range(lo, hi + 1)
        else:
            out.append(int(part))
    return sorted(dict.fromkeys(out))


def dump(obj):
    """紧凑 JSONL，键序即插入序——下游按 '^{\"layer\":\"mula\"' 之类前缀过滤。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
