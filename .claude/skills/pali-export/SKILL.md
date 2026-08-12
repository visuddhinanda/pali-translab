---
name: pali-export
description: "Atomic skill: export translations from a WikiPali channel to local markdown files, one file per chapter (sutta), with YAML frontmatter. Read-only; only run when the user asks for local files."
---

# pali-export

把 wikipali channel 里的译文导出为本地 markdown——**一章（经文）一个文件**，带 YAML frontmatter。

**默认不导出。** 译文的正本在 wikipali；只有用户明确要一份本地文件时才跑这一步。

## 依赖

需要 **wikipali 插件**（`wikipali` CLI）。

## 调用方式

```
/pali-export <book>[:<para>] [--channel <uid>] [--from <p>] [--to <p>]
```

- 给 `<para>` → 只导出该段所属的那一章
- 给 `--from/--to` → 导出与该范围相交的所有章
- 都不给 → 整本

## 分派流程

1. 章节边界：`wikipali toc <book>:<para> --json --depth 9`
   —— 某条目录项到下一条目录项之前的所有段落即一章
2. 取译文：`wikipali get <book>:<p> … --json --channel <ch>`
3. 每章写一个文件

执行层已封装为：

```bash
python3 scripts/export_markdown.py --book 93 --channel <uid> --para 983
```

## 文件名与目录

**文件名就是章节名，目录就是章节路径**（取自 toc 的祖先面包屑）：

```
workspace/export/(DN) Sīlakkhandhavaggapāḷi/12. Lohiccasuttaṃ/Tayo codanārahā.md
```

章节名原样保留（空格、括号、变音符号都不动），只把路径分隔符换成 `-`。

## 文件格式

```markdown
---
title: "Tayo codanārahā"
book: 93
paragraph_start: 983
paragraph_end: 986
path: ["(DN) Sīlakkhandhavaggapāḷi", "12. Lohiccasuttaṃ"]
channel: "claude"
channel_uid: 73c03e1a-…
lang: "zh-Hans"
generated_by: AI
model: "claude-opus-5"
source: "wikipali"
sentences: 40
exported_at: 2026-08-12
---

# Tayo codanārahā

> 本文是**机器生成的译文**，正本在 WikiPali，本文件只是离线副本。

第一段第一句。
第一段第二句。

第二段第一句。
第二段第二句。
```

## 正文排版（硬约束）

- **不含巴利原文**——这是给人读的译文副本
- **一句一行**（按 `word_start` 排序）
- **同一段落的句子之间不空行**
- **段落之间空一行**

段落坐标不进正文，只在 frontmatter 里记 `paragraph_start` / `paragraph_end`。

## 硬约束

- **机器生成的译文必须显式标注**（frontmatter `generated_by: AI` + 正文开头的说明行）。
  这是插件 `references/conventions.md` 的要求，不是可选的礼貌用语。
- 导出是**单向快照**：改译文要改 channel，不要改导出的 md 再想同步回去。
