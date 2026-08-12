---
resources:
  - pali
  - atthakatha           # 释义标准，用来落实 review 里基于义注的意见
  - nissaya              # 词级基准，用来落实 review 里基于 nissaya 的意见
  - current_translation  # 从目标 channel 读回的现有译文
  - review               # workspace/reports/{book}/{start}-{end}_review.md
knowledge: []
output: wikipali:{channel}          # 覆盖写回同一 channel
---

# Revise (按审稿意见修正)

## 目标
读取审稿意见与 channel 里的现有译文，按意见修正，**覆盖写回同一 channel**。

## 工作方法

1. 读 `workspace/reports/{book}/{start}-{end}_review.md` 获取整个 chunk 的审稿意见
2. `wikipali get <book>:<para> --json --channel <ch>` 读回现有译文
3. 逐条对应审稿意见到具体 sentence（通过 `§{para} 句 <id>` 定位，id = book-para-word_start-word_end）
4. 采纳意见时改译文；不采纳时在本次回复里说明理由（channel 只存译文，不存拒绝理由）
5. **坐标保持不变**：`book` / `paragraph` / `word_start` / `word_end` 与原文一致
6. 提交 `wikipali write - --channel <ch>`，写完独立读回核对

未被审稿意见提及的句子**原样提交**——覆盖写入是整段替换，漏提交就等于漏了那一句。

审稿意见里的「跨段一致性」一节要一并落实：那是逐段审查看不见、只有 chunk 视野才有的发现。

## 不要做

- 不要"顺便"修改未被 review 提及的句子
- 不要编造坐标，不要改动坐标
- 不要在 channel 里另开一份"修订版"——同坐标覆盖就是修订
- 不要把结果写成本地 json 文件
