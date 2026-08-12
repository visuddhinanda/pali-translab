---
description: "Translate + term-check: translate a paragraph into the target WikiPali channel, then check terminology consistency."
---

# translate — 翻译 + 术语检查

组合工作流：`pali-translate` → `pali-term-check`

## 执行顺序

1. **pali-translate** `$ARGUMENTS`
   - 输入：**只有 pali 原文**（nissaya 留给 review 作独立复核基准）
   - 输出：**写入目标 wikipali channel**（覆盖式）

2. **pali-term-check** `$ARGUMENTS`
   - 输入：刚写进 channel 的译文（读回）
   - 输出：`workspace/reports/{book}/term_check_{范围}.md`

## 输入格式

```
/translate <book>:<para> [--channel <uid>] [--method <name>]
```

`--channel` 缺省取 `config.toml` 的 `[wikipali].channel`。

## 输出

- 译文 → wikipali channel（**不写本地 json**）
- 术语报告 → `workspace/reports/{book}/term_check_{范围}.md`

需要本地 markdown 副本时另跑 `/export`。
