---
name: pali-translate
description: "Atomic skill: translate Pali source text (mula / atthakatha / tika) into Chinese and write it straight into a WikiPali channel. Commentary layers receive the parent layer translation so bold lemmata match word for word; nissaya is reserved for review. Never writes local jsonl."
---

# pali-translate

巴利原文 → 中译初稿的原子翻译能力。**译文直接写进 wikipali channel，不落本地 json。**

## 依赖

需要安装 **wikipali 插件**（提供 `wikipali` CLI）。若 `command -v wikipali` 为空，
改用 `${CLAUDE_PLUGIN_ROOT}/bin/wikipali`，并提醒用户重启会话让 PATH 生效。

写入相关的全部硬约束以插件 `wikipali:write` skill 的「铁律」为准——不索要密码、
写前确认、坐标不编造、写后读回、现代汉语。本文件不重复，只写翻译流程特有的部分。

## 调用方式

```
/pali-translate <book>:<para> [--channel <uid>] [--method <name>]
```

`<book>:<para>` 是 wikipali 坐标（如 `216:35`）。`--channel` 缺省取 `config.toml`
的 `[wikipali].channel`。

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>:<para>` 与目标 channel
2. 加载 method 配置（**项目 `methods/<method>/translate.md` 优先于 skill `methods/default/translate.md`**，整文件覆盖）
3. 加载 knowledge：
   - skill `references/` 全部
   - 项目 `knowledge/style.md` / `terms.md` / `pitfalls.md`（如存在）
   - method frontmatter `knowledge:` 引用的 `knowledge/INDEX.md` 条目
4. 取原文：`wikipali get <book>:<para> --json`。**不取 nissaya**、不读同坐标的其他译本。
   若本层有父层（义注/复注），另取父层的原文与译文作被解释词对照。
5. 按 method 文档逐句翻译
6. 写入：整理成 `{"sentences":[{book_id,paragraph,word_start,word_end,content,content_type}]}`，
   交给 `wikipali write - --channel <ch>`；写完用 `wikipali get --channel <ch>` 独立读回核对

> 本项目在执行层提供了封装：`scripts/wp_pull.py`（第 4 步）与 `scripts/wp_push.py`
> （第 6 步，含坐标校验、条数核对、写后读回）。跨项目使用本 skill 时直接用上面的 CLI 即可。

## 三层与父层对照

本文（mūla）、义注（aṭṭhakathā）、复注（ṭīkā）**分别翻译**，坐标在不同的书里，
由 `wikipali related` 逐层解析（本项目封装为 `scripts/layers.py`）。

| 层 | 父层 | 翻译时给什么 |
|---|---|---|
| 本文 mūla | 无 | **只有巴利原文** |
| 义注 aṭṭhakathā | 本文 | 自己的巴利原文 + **本文的已定稿译文** |
| 复注 ṭīkā | 义注 | 自己的巴利原文 + **义注的已定稿译文** |

**被解释词必须与父层逐字同译（硬约束）**：义注里的黑体是从本文原样引出的被解释词，
复注里的黑体引自义注。黑体词的译法必须与父层同一处**逐字相同**，一个字都不能改——
不一致读者就看不出这条注在注哪个词，随文注的对应关系就断了。这条可机械核查。

原文的黑体在取数时会转成 `**词**`，译文要保留这个标记。

## 定位整章在各层的完整起止（硬规程）

要翻译或导出**一整章（一部经）**时，**不要用 `wikipali related` 的段号当章节范围**。
`related` 是段级对应，一段注释常跨注好几段父层，边界处必然错位——注释章的首段往往
注的是上一章的本文，它的被解释词在本章里根本找不到。

正确做法是 **book-title + 该书目录**，两样都有现成的 CLI：

```bash
# 1) 本文本章的起止：某条目录项到下一条目录项之前
wikipali toc <mula_book>:<para> --json --depth 9

# 2) 找出各层是哪本书（related 的 book_title_pali + tags 标层次；books 可按书名检索）
wikipali related <mula_book>:<para> --json
wikipali books <书名关键词>

# 3) 用**该注释书自己的目录**求本章起止——这才是完整章节
wikipali toc <att_book>:<related 给的任一段> --json --depth 9
wikipali toc <tika_book>:<related 给的任一段> --json --depth 9
```

**校验**：注释章的章名通常是本文章名加 `vaṇṇanā`（本文 `Tayo codanārahā` →
义注/复注 `Tayo codanārahavaṇṇanā`）。对不上就说明第 3 步取错了段，回去核对，
不要将就。

**实例**（本文 93:983-986 `Tayo codanārahā`）：

| 层 | book | 章名 | 目录给的真实范围 | related 段号（**错位**） |
|---|---|---|---|---|
| 本文 | 93 | Tayo codanārahā | 983-986 | 983-986 |
| 义注 | 103 | Tayo codanārahavaṇṇanā | **1469-1472** | 1468-1473 |
| 复注 | 185 | Tayocodanārahavaṇṇanā | **1344-1347** | 1345-1348 |
| 复注 | 189 | Tayocodanārahavaṇṇanā | **1262-1266** | 1261-1267 |

按 related 的范围译，义注 1468 会被拉进来——它属于上一章、注的是本文 982，
其被解释词在本章本文里找不到，被解释词对齐就无从谈起。

## 独立翻译（硬约束）

**除父层对照外，本步骤的输入只有巴利原文。** 缅文 nissaya 是 review / evaluate 的
独立词级基准，翻译时照着它译，等于被检查者与检查标准同源——译错的地方复核也发现不了。

父层译文不同：它不是翻译的拐杖，是被解释词的对齐约束——义注解释什么、怎么解释，
仍要你自己从义注的巴利原文译出。

拿不准就压低该句 `confidence`，交给 review 用 nissaya 与义注来判。

## 数据流

```
wikipali（pali）→ 独立翻译 → wikipali channel（覆盖式写入）
                                    ↓
                        review / evaluate 再拿 nissaya 逐词复核
```

- **没有 v1/v2 本地文件**：同一坐标重写即覆盖，channel 里永远是最新一版
- 写入是覆盖式的：相同 `(book, paragraph, word_start, word_end, channel)` 的旧句子被替换
- 需要离线副本时用 `scripts/export_markdown.py` 导出 markdown（见 `/export`）

## 取不到原文时

某段 `wikipali get` 返回空 → **跳过该段**并如实报告，不要拿相邻段落凑，也不要凭标题臆造。

（nissaya 的降级问题不在本 skill——translate 本来就不用它，见 pali-review。）

## Chunk 批处理

按 chunk 组织上下文，而非逐段孤立翻译。

**组 chunk 方法**：从起始 para 逐段拉取巴利原文，累加字符数，buffer ≥ 5000 巴利字符
时截断为一个 chunk，余下段落进入下一个 chunk。

**写入仍按段**：一次提交一段，条数与该段原文句数必须相等。

**好处**：上下文连贯，术语/风格一致性更好，减少调用次数。

## 输出约定

逐句 JSONL（仅作为写入前的中间格式，不落盘）：

```json
{"id": "<book>-<para>-<word_start>-<word_end>", "zh": "译文", "confidence": 0-100}
```

- `id` 必须与取回的原文坐标完全一致——**坐标不能编造**
- `confidence` 只用于本次运行的报告，channel 里只存译文本身
- **译文里不留任何工作标记**：拿不准就压低 `confidence`，存疑交给 review / evaluate 的报告

## 详细规范

- nissaya 结构：`references/nissaya_format.md`
- 默认 method：`methods/default/translate.md`
- 写入规矩与坐标约定：wikipali 插件的 `references/conventions.md`、`references/api-write.md`
