---
description: "Full pipeline into WikiPali: translate → review → revise → harmonize → term-check → footnote → evaluate"
---

# full-pipeline — 完整流程

组合工作流：`pali-translate` → `pali-review` → `pali-revise` → `pali-harmonize` → `pali-term-check` → `pali-footnote` → `pali-evaluate`

改译文的步骤（translate / revise / harmonize / footnote）**覆盖写回同一个 channel**；
非侵入的步骤（review / term-check / evaluate）只输出本地 markdown 报告。
**全程不写本地 json。**

**evaluate 排在最后**：它评的是走完全部改动步骤之后的定稿，放在中间评的是半成品。

## 执行顺序

1. **pali-translate** `$ARGUMENTS` → 初稿写入 channel
2. **pali-review** `$ARGUMENTS` → `workspace/reports/{book}/{start}-{end}_review.md`
3. **pali-revise** `$ARGUMENTS` → 修订稿覆盖写回 channel
4. **pali-harmonize** `$ARGUMENTS` → 整章统稿：统一用词语体 + 修正通读发现的问题，覆盖写回 channel
5. **pali-term-check** `$ARGUMENTS` → `workspace/reports/{book}/term_check_{范围}.md`
6. **pali-footnote** `$ARGUMENTS` → 随文注内联进译文，覆盖写回 channel
7. **pali-evaluate** `$ARGUMENTS` → `workspace/reports/{book}/{start}-{end}_final.md`（**不改译文**）

## 输入格式

```
/full-pipeline <book>:<para> [--channel <uid>] [--method <name>]
```

## 输出

- channel 里是走完全流程的最终译文（已修订、已统稿、带随文注）
- `workspace/reports/{book}/` 下是审稿意见、术语报告、最终评估总评

## 注意

footnote 的随文注会进入 channel 正文。不希望它出现在正式发布的 channel 时，
把 `--channel` 指向草稿 channel，定稿后再写入正式 channel。

evaluate 的结论**只在报告里**，不进 channel。它是最后的验收：要按评估结果改译文，
再跑一轮 revise 或 harmonize。

批量跑整卷用执行层脚本：

```bash
./scripts/pipeline_batch.sh <book> <start> <end> --channel <uid> --nissaya
```
