---
resources:
  - pali
  - prev_translation     # v(n).jsonl
  - prev_review          # v(n).md
knowledge: []
output: tipitaka/{method}/jsonl/{book}/{para}/{para}_v{n+1}.jsonl
---

# Revise (按审稿意见修正)

## 目标
读取 chunk review md（`reviews/{start}-{end}_v{n}.md`）和 chunk 内所有 v(n).jsonl，按审稿意见修正，输出 per-para 的 v(n+1).jsonl。

## 工作方法

1. 读取 `reviews/{start}-{end}_v{n}.md` 获取整个 chunk 的审稿意见
2. 逐条对应审稿意见到具体 sentence（通过 `§{para} 句 <id>` 定位，id = book-para-word_start-word_end）
3. 采纳意见时修改 `zh` 字段；不采纳时在 jsonl 行追加 `"revise_skip_reason": "..."`
4. **保持 id / book / paragraph / word_start / word_end / pali 不变**
5. 按 para 拆分输出到各自目录的 v(n+1).jsonl

## 不要做

- 不要"顺便"修改未被 review 提及的句子
- 不要降低已有句子的 confidence 分数（除非引入新疑点）
