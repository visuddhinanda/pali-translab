---
description: "Annotate only: add inline commentary notes to translations already in the WikiPali channel, without re-translating."
---

# annotate — 只加注，不翻译

组合工作流：仅 `pali-footnote`

## 执行顺序

1. **pali-footnote** `$ARGUMENTS`
   - 输入：channel 里的现有译文 + `wikipali related` 找到的义注/复注
   - 输出：随文注内联进译文，**覆盖写回同一 channel**

## 前提条件

目标 channel 在该坐标必须已有译文。`wikipali get <book>:<para> --channel <ch>` 取不到
内容就报错退出——**不要顺手先翻一遍**。

## 输入格式

```
/annotate <book>:<para> [--channel <uid>] [--method <name>]
```

## 输出

- 带随文注的译文 → wikipali channel（覆盖式）

注释格式、来源标注、被解释词逐字同译等硬约束见 wikipali 插件的 `references/conventions.md`。
