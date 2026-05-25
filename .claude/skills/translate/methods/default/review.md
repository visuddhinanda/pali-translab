---
resources:
  - pali
  - prev_translation     # 自动解析为 v(n).jsonl
knowledge: []
output: tipitaka/{method}/jsonl/{book}/reviews/{start}-{end}_v{n}.md
---

# Review (审稿，不改译文)

## 目标
按 chunk 读取所有 v(n).jsonl，逐句审查，输出审稿意见 md。**不要直接改译文**——revise 步才改。

## 输入
读取 chunk 内所有 para 的 `{para}/{para}_v{n}.jsonl`，一次性审查整个 chunk。

## 检查清单

1. **准确性**：是否漏译、误译？术语是否符合 `knowledge/terms.md`？
2. **风格**：是否符合 `knowledge/style.md`？
3. **一致性**：同一术语在 chunk 内所有段落中是否一致？
4. **`⚠️[候选?]` 标记**：是否有该标而未标的？
5. **OCR / 原文疑问**：pali 原文是否有疑似讹误？（记下，不要改）

## 输出格式

输出到 `reviews/{start_para}-{end_para}_v{n}.md`：

```markdown
# Review v{n} — {book}/{start_para}-{end_para}

## §{para} 句 <sentence uuid>
- **问题**：<分类> — <说明>
- **建议**：<具体修改方向>

## §{para} 句 <sentence uuid>
- ...
```

无问题的句子不必列出。
