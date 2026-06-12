---
description: "Annotate only: add footnotes from commentaries to existing translations without re-translating."
---

# annotate — 只加注，不翻译

组合工作流：仅 `pali-footnote`

## 执行顺序

1. **pali-footnote** `$ARGUMENTS`
   - 输入：现有 final.jsonl 或最新 v(n).jsonl
   - 输出：在 jsonl 中追加 `footnotes` 字段

## 前提条件

目标段落必须已有译文（至少 v1.jsonl）。如果未找到译文，报错退出。

## 输入格式

```
/annotate <book>/<para> [--method <name>]
```

## 输出

- 原文件追加 `footnotes` 字段（或输出 `_annotated` 后缀文件）
