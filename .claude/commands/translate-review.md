---
description: "Full translate-review-revise cycle: translate → review → revise → term-check"
---

# translate-review — 翻译 + 单轮审修 + 术语检查

组合工作流：`pali-translate` → `pali-review` → `pali-revise` → `pali-term-check`

## 执行顺序

1. **pali-translate** `$ARGUMENTS`
   - 输出：`{para}_v1.jsonl`

2. **pali-review** `$ARGUMENTS --version 1`
   - 输入：v1.jsonl
   - 输出：`reviews/{start}-{end}_v1.md`

3. **pali-revise** `$ARGUMENTS --version 1`
   - 输入：v1.jsonl + v1 review
   - 输出：`{para}_v2.jsonl`

4. **pali-term-check** `$ARGUMENTS --scope chunk`
   - 输入：v2.jsonl
   - 输出：`reviews/term_check_chunk.md`

## 输入格式

```
/translate-review <book>/<para> [--method <name>]
```

## 输出

- `workspace/tipitaka/{method}/jsonl/{book}/{para}/{para}_v1~v2.jsonl`
- `workspace/tipitaka/{method}/jsonl/{book}/reviews/{start}-{end}_v1.md`
- `workspace/tipitaka/{method}/jsonl/{book}/reviews/term_check_chunk.md`
