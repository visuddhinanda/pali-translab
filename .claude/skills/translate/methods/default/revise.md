---
resources:
  - pali
  - prev_translation     # v(n).jsonl
  - prev_review          # v(n).md
knowledge: []
output: translations/{method}/{book}/{para}_v{n+1}.jsonl
---

# Revise (按审稿意见修正)

## 目标
按 v(n).md 中的建议修正 v(n).jsonl，输出 v(n+1).jsonl。

## 工作方法

1. 逐条对应审稿意见到具体 sentence
2. 采纳意见时修改 `zh` 字段；不采纳时在 jsonl 行追加 `"revise_skip_reason": "..."`（仅本句保留，不写入后续版本）
3. **保持 id / book / paragraph / word_start / word_end / pali 不变**
4. 输出 jsonl 结构与 v(n) 相同

## 不要做

- 不要"顺便"修改未被 review 提及的句子
- 不要降低已有句子的 confidence 分数（除非引入新疑点）
