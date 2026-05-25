---
resources:
  - pali
  - prev_translation     # v3.jsonl
knowledge: []
output:
  - tipitaka/{method}/jsonl/{book}/{para}_final.jsonl
  - tipitaka/{method}/jsonl/{book}/{para}_final.md
---

# Evaluate (最终评估)

## 目标
1. 在译文中**内联标注**所有疑点 `⚠️[候选?]`
2. 产出总评 md（总分 / 信心 / 疑问清单）

## final.jsonl 格式

与 v3 相同，但 `zh` 中保留 / 新增 `⚠️[候选?]` 标记。例：

```json
{"id": "...", "pali": "Bhagavato ...",
 "zh": "礼敬彼⚠️[世尊?]阿罗汉、正等正觉者",
 "confidence": 95}
```

## final.md 格式

```markdown
# Evaluate — {book}/{para}

## 总分
- 准确性: X/100
- 风格符合度: X/100
- 一致性: X/100
- **综合**: X/100

## 信心指数
N / 100

## 理由
<分维度说明>

## 疑问清单

### ⚠️ {候选词} （句 <id>）
- 上下文：<原文片段>
- 已采用：<译法>
- 候选：<其他译法>
- 不确定的原因：<说明>
```

## 不要做

- 不要为了"看起来权威"虚标高分
- 疑问清单必须与译文中的 `⚠️` 一一对应（数量相等）
