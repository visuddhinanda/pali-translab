---
resources:
  - pali
  - nissaya              # 缅文逐词注解，词级评估基准（如有）
  - prev_translation     # 最新 v(n).jsonl
knowledge: []
output:
  - tipitaka/{method}/jsonl/{book}/{para}/{para}_final.jsonl    # per-para
  - tipitaka/{method}/jsonl/{book}/reviews/{start}-{end}_final.md  # per-chunk
---

# Evaluate (最终评估)

## 目标
1. 读取 chunk 内所有最新版 v(n).jsonl，在译文中**内联标注**所有疑点 `⚠️[候选?]`
2. 按 para 输出 final.jsonl
3. 按 chunk 产出总评 md（总分 / 信心 / 疑问清单）到 `reviews/{start}-{end}_final.md`

## 评估基准：缅文 nissaya
按 `(word_start, word_end)` 把 nissaya 单元对齐到每一句，**以 nissaya 为词级标准答案**评分（nissaya 缺失的段落降级为纯 pali 评估，并在理由中说明）。体例见 `references/nissaya_format.md`。

- **准确性打分**主要依据译文与 nissaya 的吻合度：词覆盖、格/句法角色（看缅文格助词）、歧义词的传统取义。
- 译文与 nissaya **冲突**且无更优依据时——降准确性分，并在该词加 `⚠️[候选?]`，候选取 nissaya 义。
- 译文偏离 nissaya 但**确有依据**（如别本、上下文）时——不扣分，但在理由中注明分歧。

## final.jsonl 格式

与上一版相同，但 `zh` 中保留 / 新增 `⚠️[候选?]` 标记。例：

```json
{"id": "...", "pali": "Bhagavato ...",
 "zh": "礼敬彼⚠️[世尊?]阿罗汉、正等正觉者",
 "confidence": 95}
```

## final.md 格式

```markdown
# Evaluate — {book}/{start_para}-{end_para}

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
