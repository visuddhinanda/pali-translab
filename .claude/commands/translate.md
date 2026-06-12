---
description: "Translate + term-check: produce v1 translation then check terminology consistency."
---

# translate — 翻译 + 术语检查

组合工作流：`pali-translate` → `pali-term-check`

## 执行顺序

1. **pali-translate** `$ARGUMENTS`
   - 输入：pali 原文（+ nissaya 如有）
   - 输出：`{para}_v1.jsonl`

2. **pali-term-check** `$ARGUMENTS --scope chunk`
   - 输入：刚产出的 v1.jsonl
   - 输出：`reviews/term_check_chunk.md`

## 输入格式

```
/translate <book>/<para> [--method <name>]
```

## 输出

- `workspace/tipitaka/{method}/jsonl/{book}/{para}/{para}_v1.jsonl`
- `workspace/tipitaka/{method}/jsonl/{book}/reviews/term_check_chunk.md`
