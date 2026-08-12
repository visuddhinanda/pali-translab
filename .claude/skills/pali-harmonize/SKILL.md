---
name: pali-harmonize
description: "Atomic skill: read the mula / atthakatha / tika translations of a passage together, align bold lemmata word for word across layers, unify terminology and register, and fix what only a cross-layer reading reveals. Writes all three layers back to the channel."
---

# pali-harmonize

**统稿**：把同一段落的**本文 / 义注 / 复注三层译文放在一起**通读，对齐被解释词、统一术语语体，
**并修掉通读中发现的问题**，三层一起覆盖写回同一 channel。

三层分头翻译，天然会漂——义注的黑体被解释词跟本文的译法对不上，同一个巴利词在本文译
「责难」在复注译「举罪」，语体忽紧忽松。三层一起读还会看出单层视野里发现不了的错：
指代接不上、平行段落一处译错。**这是流水线里最后一个改译文的步骤。**

## 依赖

需要 **wikipali 插件**（`wikipali` CLI）。写入硬约束以插件 `wikipali:write` skill 的「铁律」为准。

## 调用方式

```
/pali-harmonize <book>:<para> [--channel <uid>] [--method <name>]
```

给本文的坐标即可——三层坐标由 `wikipali related` 逐层解析。

## 分派流程

1. 解析 `$ARGUMENTS`，用 `wikipali related` 解出本文 / 义注 / 复注三层的坐标
   （本项目封装为 `scripts/layers.py`）
2. 加载 method 配置与 knowledge（同 pali-translate）
3. 一次性读入三层：各层 `wikipali get <坐标…> --json --channel <ch>`，
   连同各自的巴利原文（判断某处不一致是原文本来就不同，还是译法漂了）
4. 通读三层，先列清单再动手（对齐项 + 统一项 + 问题项）
5. 三层一起覆盖写回：按 book 分次 `wikipali write - --channel <ch>`，写完独立读回核对

> 执行层封装：`scripts/pipeline_batch.sh --steps harmonize`（自动解析三层并分层提交）。

## 做两件事

### 一、统一

**最高优先：被解释词跨层逐字对齐。**

义注里的黑体 `**…**` 是从本文原样引出的被解释词，复注里的引自义注。抽出来逐个比对：

- 义注黑体的译法 ↔ **本文**同一处的译法，必须逐字相同
- 复注黑体的译法 ↔ **义注**同一处的译法，必须逐字相同
- 不一致就**改子层去迁就父层**；除非父层本身译错——那就把父层一并改对

这条可机械核查，是三层能不能当随文注读的前提。

其余统一项：

| 项 | 判据 |
|---|---|
| **术语** | 同一巴利词在**三层之内**译法唯一；命中 `knowledge/terms.md` 的以术语表为准 |
| **语体** | 三层同一层书面语，不能本文偏文、义注偏白 |
| **称谓与专名** | 人名、地名、经名、第二人称（您/你）三层统一 |
| **重复句式** | 巴利里原样重复的定型句，译文也要原样重复——同句不同译最刺眼 |
| **标点体例** | 引号层级（“” 外、‘’ 内）、破折号、省略号用法一致 |

**先核对巴利原文**：两处译得不同，可能原文本来就不同（不同的词、不同的格、不同的语境义）。
原文不同就不该强行统一——那是把区别抹掉，比不一致更糟。

### 二、修正

通读中发现的实际问题**就地改掉**，不要留给下一步：

- 误译、漏译、多译
- 指代错误或接不上（三层一起读才看得出「他」指谁）
- 汉语语病、句子读不通
- 文言 / 半文半白（对照 `knowledge/style.md` 第一节禁例表）
- 标点错误、引号配对断裂（长引语跨段时最常见）
- 平行段落里一处译对、另一处译错

## 改动的门槛（硬约束）

**每处改动都要有具体理由：一致性，或明确的错误。**

- **不要为「读起来更顺」而改。** 没有具体毛病、只是换个说法更漂亮——保持原样
- **不要重译。** 这一步是收口，不是再翻一遍
- 不要把原文本来就有的区别抹平
- 不要漏句：三层每一句都要提交（未改动的原样提交），覆盖写入是整段替换
- 不要编造坐标
- 不要在译文里留任何工作标记

## 输出

```
channel <ch>        # 三层统稿后的译文（按 book 分次覆盖写入）
```

改了哪些、依据是什么（统一 / 修正分开说），在本次运行的回复里说明；不额外落本地文件。

## 在流水线里的位置

```
translate → review → revise → harmonize → evaluate
                               ↑ 最后一个改译文的步骤   ↑ 只出报告
```

harmonize 之后就是 evaluate——评的是走完全部改动之后的定稿。

## 与其它 skill 的分工

- `pali-review` / `pali-revise`：**单层内按 chunk**，逐句精校，以义注与 nissaya 为标准
- `pali-term-check`：**只读**，出术语一致性报告，可跨章、跨书
- `pali-harmonize`：**跨三层动手改**，管被解释词对齐、术语、语体、称谓、句式、标点，
  以及只有三层同看才暴露的错
