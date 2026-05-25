---
resources:
  - pali
  - prev_translation     # 自动解析为 v(n).jsonl
knowledge: []
output: tipitaka/{method}/jsonl/{book}/{para}_v{n}.md
---

# Review (审稿，不改译文)

## 目标
对 v(n).jsonl 逐句审查，输出审稿意见 md。**不要直接改译文**——revise 步才改。

## 检查清单

1. **准确性**：是否漏译、误译？术语是否符合 `knowledge/terms.md`？
2. **风格**：是否符合 `knowledge/style.md`？
3. **一致性**：同一术语在本段内是否一致？
4. **`⚠️[候选?]` 标记**：是否有该标而未标的？
5. **OCR / 原文疑问**：pali 原文是否有疑似讹误？（记下，不要改）

## 输出格式

```markdown
# Review v{n} — {book}/{para}

## 句 <sentence uuid>
- **问题**：<分类> — <说明>
- **建议**：<具体修改方向>

## 句 <sentence uuid>
- ...
```

无问题的句子不必列出。
