---
description: "Translate → review → revise → term-check, all against the target WikiPali channel."
---

# translate-review — 翻译 + 单轮审修 + 术语检查

组合工作流：`pali-translate` → `pali-review` → `pali-revise` → `pali-term-check`

每一步都把结果写回同一个 channel，下一步从 channel 读回——**没有中间 json 文件**，
任何一步中断后重跑都能接上。

## 执行顺序

1. **pali-translate** `$ARGUMENTS`
   - 输入：**只有 pali 原文**
   - 输出：初稿写入 channel

2. **pali-review** `$ARGUMENTS`
   - 输入：从 channel 读回的译文 + pali + **义注**（释义标准）+ **nissaya**（词级基准）——从这一步才介入
   - 输出：`workspace/reports/{book}/{start}-{end}_review.md`

3. **pali-revise** `$ARGUMENTS`
   - 输入：channel 译文 + 审稿意见
   - 输出：修订稿**覆盖写回** channel

4. **pali-term-check** `$ARGUMENTS`
   - 输出：`workspace/reports/{book}/term_check_{范围}.md`

## 输入格式

```
/translate-review <book>:<para> [--channel <uid>] [--method <name>]
```

## 输出

- 译文（已修订）→ wikipali channel
- 审稿意见 + 术语报告 → `workspace/reports/{book}/`
