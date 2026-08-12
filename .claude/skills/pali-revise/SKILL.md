---
name: pali-revise
description: "Atomic skill: revise translations based on review feedback. Reads the current translation from a WikiPali channel plus the review markdown, writes the revised text back to the same channel."
---

# pali-revise

根据审读意见修订译文的原子能力。**修订结果覆盖写回同一 channel**，不落本地 json。

## 依赖

需要 **wikipali 插件**（`wikipali` CLI）。写入的全部硬约束以插件 `wikipali:write` skill
的「铁律」为准——坐标不编造、写前确认、写后读回、现代汉语。

## 调用方式

```
/pali-revise <book>:<para> [--channel <uid>] [--method <name>]
```

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>:<para>` 与目标 channel
2. 加载 method 配置（项目 `methods/<method>/revise.md` 优先于 skill `methods/default/revise.md`，整文件覆盖）
3. 加载 knowledge（同 pali-translate）
4. 读取输入：
   - 现有译文：`wikipali get <book>:<para> --json --channel <ch>`
   - 巴利原文：`wikipali get <book>:<para> --json`
   - 审稿意见：`workspace/reports/{book}/{start}-{end}_review.md`
   - 义注与 nissaya：用来落实审稿意见里基于它们的判断
5. 逐条采纳/拒绝审稿意见，未被提及的句子**原样保留**
6. 覆盖写回：`wikipali write - --channel <ch>`，写完独立读回核对

> 执行层封装：读用 `scripts/wp_pull.py`，写用 `scripts/wp_push.py`（含坐标校验与读回）。

## 覆盖语义

相同 `(book, paragraph, word_start, word_end, channel)` 的旧句子被替换——
**channel 里没有历史版本**。需要保留修订前后的对照时，先用
`scripts/export_markdown.py` 导出一份 markdown 副本。

## 不要做

- 不要"顺便"修改未被 review 提及的句子
- 不要改动坐标：`book` / `paragraph` / `word_start` / `word_end` 必须与原文一致
- 不要在 channel 里另开一份"修订版"——同坐标覆盖就是修订

## 详细规范

参见 `methods/default/revise.md`
