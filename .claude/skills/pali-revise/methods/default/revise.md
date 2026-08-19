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
6. **只提交改动过的句子**，写完独立读回核对

写入是**按坐标覆盖**的：同坐标替换，没提交的坐标原样保留。
所以未改动的句子**不要回传**——回传整个 chunk 只是把原文重写一遍，白费 token，
还多一次改坏的机会。一句都没改就什么都不提交。

审稿意见里的「跨段一致性」一节要一并落实：那是逐段审查看不见、只有 chunk 视野才有的发现。

## 被解释词的黑体必须保留（硬约束）

原文里的黑体是**被解释词**——义注的引自本文，复注的引自义注。译文里这些词
**必须照样用 `**…**` 包起来**：不要改成引号、不要去掉。

两个理由，都不是风格问题：

1. 它是读者辨认「这条注在注哪个词」的**唯一线索**；换成引号，与原文的黑体对不上
2. 它是「被解释词与父层逐字同译」的**机械核查依据**——抽出全部 `**…**` 到父层比对字符串

`revise` 与 `harmonize` 尤其容易把它顺手改成 ‘…’，那是回归，不是改进。

## 不要做

- 不要"顺便"修改未被 review 提及的句子
- 不要编造坐标，不要改动坐标
- 不要在 channel 里另开一份"修订版"——同坐标覆盖就是修订
- 不要回传未改动的句子
- 不要把结果写成本地 json 文件
