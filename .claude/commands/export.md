---
description: "Export translations from a WikiPali channel to local markdown — one file per chapter (sutta), with YAML frontmatter."
---

# export — 导出本地 markdown

组合工作流：仅 `pali-export`

**只在用户明确要本地文件时才跑。** 译文的正本在 wikipali，导出是单向快照。

## 执行顺序

1. **pali-export** `$ARGUMENTS`
   - 章节边界取自 `wikipali toc`，一章（经文）一个文件
   - 输出：`workspace/export/{章节路径}/{章节名}.md`
     （如 `workspace/export/(DN) Sīlakkhandhavaggapāḷi/12. Lohiccasuttaṃ/Tayo codanārahā.md`）

## 输入格式

```
/export <book>[:<para>] [--channel <uid>] [--from <p>] [--to <p>]
```

- 给 `<para>` → 只导出该段所属的那一章
- 给 `--from/--to` → 导出与该范围相交的所有章
- 都不给 → 整本

## 输出

每个文件带 YAML frontmatter（title / book / paragraph_start / paragraph_end / path /
channel / lang / generated_by / model / sentences / exported_at）。

正文**只有译文，不含巴利原文**：一句一行，同段落的句子之间不空行，段落之间空一行。

**机器生成的译文必须显式标注**——frontmatter 的 `generated_by: AI` 与正文开头的说明行
都不要删。

## 直接跑脚本

```bash
python3 scripts/export_markdown.py --book 93 --channel <uid> --para 983
```
