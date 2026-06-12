---
description: "Full pipeline: translate → review → revise → evaluate → term-check → footnote"
---

# full-pipeline — 完整流程

组合工作流：`pali-translate` → `pali-review` → `pali-revise` → `pali-evaluate` → `pali-term-check` → `pali-footnote`

## 执行顺序

1. **pali-translate** `$ARGUMENTS`
   - 输出：`{para}_v1.jsonl`

2. **pali-review** `$ARGUMENTS --version 1`
   - 输出：`reviews/{start}-{end}_v1.md`

3. **pali-revise** `$ARGUMENTS --version 1`
   - 输出：`{para}_v2.jsonl`

4. **pali-evaluate** `$ARGUMENTS`
   - 输入：v2.jsonl
   - 输出：`{para}_final.jsonl` + `reviews/{start}-{end}_final.md`

5. **pali-term-check** `$ARGUMENTS --scope chunk`
   - 输出：`reviews/term_check_chunk.md`

6. **pali-footnote** `$ARGUMENTS`
   - 输入：final.jsonl
   - 输出：final.jsonl 追加 `footnotes`

## 输入格式

```
/full-pipeline <book>/<para> [--method <name>]
```

## 输出

完整产物链：v1~v2.jsonl + final.jsonl（含脚注）+ reviews/*.md
