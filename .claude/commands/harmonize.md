---
description: "Harmonize a whole sutta/chapter: unify terminology, register, names and punctuation, and fix the problems a whole-chapter reading reveals. Last step that changes the translation."
---

# harmonize — 整章统稿

组合工作流：仅 `pali-harmonize`

## 执行顺序

1. **pali-harmonize** `$ARGUMENTS`
   - 章边界由 `wikipali toc` 自动上溯确定（给章内任一段即可）
   - 输入：整章译文（从 channel 读回）+ 巴利原文
   - 输出：统一后的整章译文**覆盖写回 channel**

## 输入格式

```
/harmonize <book>:<para> [--channel <uid>] [--method <name>]
```

## 前提条件

整章必须已有译文。跑在 translate / review / revise 之后——**这是最后一个改译文的步骤**，
之后只剩 evaluate 出报告。

## 它做什么、不做什么

**做两件事**：

1. **统一**——同一巴利词译法、语体、称谓与专名、重复句式、标点体例，前后一律
2. **修正**——通读中发现的实际问题就地改掉：误译、漏译、指代接不上、汉语语病、
   文言腔、引号配对断裂、平行段落一处对一处错

**不做**：整章重译；为「读起来更顺」而改。每处改动都要能说出理由——一致性，或明确的错误。

## 批量

```bash
./scripts/pipeline_batch.sh <book> <start> <end> --channel <uid> --steps harmonize
```

按 `wikipali toc` 自动切章，一章一次调用。
