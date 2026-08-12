---
name: pali-footnote
description: "Atomic skill: add inline commentary notes (from Atthakatha/Tika) to translations already in a WikiPali channel, following the wikipali inline-note convention."
---

# pali-footnote

从义注（Aṭṭhakathā）和复注（Ṭīkā）里取解释，为 channel 里的现有译文加**随文注**，
覆盖写回同一 channel。

## 依赖

需要 **wikipali 插件**（`wikipali` CLI）。注释格式、来源标注、被解释词一致性等硬约束
以插件 `references/conventions.md` 为准——本文件不重复。

## 调用方式

```
/pali-footnote <book>:<para> [--channel <uid>] [--method <name>]
```

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>:<para>` 与目标 channel
2. 读现有译文：`wikipali get <book>:<para> --json --channel <ch>`（没有译文则报错退出）
3. 找注释：`wikipali related <book>:<para> --json` 给出本文 ↔ 义注 ↔ 复注的段落对应，
   再 `wikipali get <义注坐标> --json` 取义注原文
4. **先把该段的义注读完再决定注什么**——不要只摘最短的一条
5. 把注释内联进译文，覆盖写回 channel，写后读回核对

## 注释格式（摘要，细则见插件 conventions.md）

紧跟被注释词、反引号包裹、**不能换行**、**必须标出来源**：

```
不乐于`**义注**：被欲贪的热恼所烧，但**并非希求还俗**`修习梵行。
```

- 注释内容只能取自 `wikipali related` 找到的义注复注，**不许自己发挥**
- 注释里的巴利词不再加 `[[ ]]`
- 该句没有可注的就不加，不要为了均匀硬凑

## 硬约束：被解释词逐字同译

义注里的**黑体**是从本文原样引出的被解释词，复注的引自义注。同一 channel 内，
被解释词的译法必须与所注文本逐字相同——不一致，读者就看不出这条注在注哪个词。
这条可以机械核查：抽出黑体词，到本文同一坐标比对字符串。

## 输出

覆盖写回同一 channel（加注是在译文里加，不是另存一份）。需要离线副本时用
`scripts/export_markdown.py` 导出 markdown。

## 待补充

- 脚注去重策略（同一术语在 chunk 内多次出现时）
