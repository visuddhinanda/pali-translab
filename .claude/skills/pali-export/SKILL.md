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

## 定位整章在各层的完整起止（硬规程）

要翻译或导出**一整章（一部经）**时，先用 `wikipali paras` 拿到该书的段落清单，
再按下面的规程定各层范围。**不要用 `wikipali related` 的段号当章节范围**——
它是段级对应，一段注释常跨注好几段父层，边界必然错位：注释章的首段往往注的是
上一章的本文，其被解释词在本章里根本找不到。

### 一次调用拿全书结构

```bash
wikipali paras <book>:3 --body --json     # 每本书一次，约 2 秒
```

每段一行，关键字段：

| 字段 | 含义 |
|---|---|
| `level` | 标题层级；`< 100` 是标题行，`== 100` 是正文段 |
| `length` | 该段巴利字符数（分块用）。⚠ 0.8.7 之前拼作 `lenght`，两种都要认 |
| `chapter_len` | 该章段数 |
| `cs_para` | **Chaṭṭha Saṅgāyana 典藏段号——跨书通用，是跨层对应的钥匙** |
| `book_name` | 所属丛书（如 `dn1`），跨丛书时用来挡误配 |

由此可得：章节边界（相邻标题行之间）、本书真实末段、每段字符数——
这三样以前要上千次调用，现在一次拿全。

### 跨层对应：用 cs_para，不用 related

**同一个 `cs_para` 就是同一处内容**，本文与各层注释共用这套段号：

```
本文   93:984   cs_para=513
义注  103:1470  cs_para=513
复注  185:1345  cs_para=513
复注  189:1263  cs_para=513
```

所以「义注这一章归哪个本文章」直接按 cs_para 交集判定，**一次 related 都不用调**。

实测对比（DN Sīlakkhandhavagga，90 个有义注的本文章）：79 处两者一致，
11 处不一致——**逐个核过，全是 `related` 判错、`cs_para` 判对**。例如本文
`Ajitakesakambalavādo`，related 指到了下一章 `Pakudhakaccāyanavādavaṇṇanā`，
而 cs_para 正确指向 `Ajitakesakambalavādavaṇṇanā`。

### cs_para 不是全覆盖，孤儿兜底不能省

注释书里有大段**本来就没有本文对应**的内容（序论 `Ganthārambhakathā`、
结集史 `Paṭhamamahāsaṅgītikathā` 等），这些段没有 `cs_para`：

| book | 正文段 | 有 cs_para |
|---|---|---|
| 93 本文 | 927 | 927（100%）|
| 103 义注 | 1382 | 1189（86%）|
| 188 复注 | 1523 | 1073（70%）|

**整本翻译时这些段必须覆盖**，否则整本书是残的。做法：按**章名**跨层配对成独立作业
（复注开头正是注释义注开头的，章名就是义注章名加 `vaṇṇanā`），作业内部做
义注↔复注统稿，不牵扯本文。最后跑一遍覆盖率自检：**每本书从 level=1 到书末，
每一段都必须被某个作业覆盖**。

### 校验

注释章的章名通常是本文章名加 `vaṇṇanā`（本文 `Tayo codanārahā` →
义注/复注 `Tayo codanārahavaṇṇanā`）。对不上就回头核对，不要将就。

**实例**（本文 93:983-986 `Tayo codanārahā`）：

| 层 | book | 章名 | 目录给的真实范围 | related 段号（**错位**） |
|---|---|---|---|---|
| 本文 | 93 | Tayo codanārahā | 983-986 | 983-986 |
| 义注 | 103 | Tayo codanārahavaṇṇanā | **1469-1472** | 1468-1473 |
| 复注 | 185 | Tayocodanārahavaṇṇanā | **1344-1347** | 1345-1348 |
| 复注 | 189 | Tayocodanārahavaṇṇanā | **1262-1266** | 1261-1266 |

### related 还有什么用

只在**验证**某个具体对应关系、或 cs_para 缺失时兜底。它不再是规划的主力。

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
