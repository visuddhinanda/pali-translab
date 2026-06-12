---
resources:
  - pali
  - nissaya              # 缅文逐词注解，词级审校基准（如有）
  - prev_translation     # 自动解析为 v(n).jsonl
knowledge: []
output: tipitaka/{method}/jsonl/{book}/reviews/{start}-{end}_v{n}.md
---

# Review (审稿，不改译文)

## 目标
按 chunk 读取所有 v(n).jsonl，逐句审查，输出审稿意见 md。**不要直接改译文**——revise 步才改。

## 输入
读取 chunk 内所有 para 的 `{para}/{para}_v{n}.jsonl`，一次性审查整个 chunk。
同时按 `(word_start, word_end)` 把 nissaya 单元对齐到每一句，作为词级核对基准。
nissaya 体例见 `references/nissaya_format.md`。

## 检查清单

**优先以缅文 nissaya 为准核对每一句**（nissaya 缺失的段落降级为纯 pali 审查）：

1. **nissaya 词级核对**：
   - **覆盖**：原文每个实词在 nissaya 都有释义；译文若漏了某词，nissaya 会暴露。
   - **格与句法**：以 nissaya 的格助词（`သည်`主格 / `၏`属格 / `ကို`宾格 / `၌`处格 / `ဖြင့်`具格等）判定主/宾/属关系，纠正译文语法误读。
   - **歧义取义**：原文一词多义时以 nissaya 的传统取义为准；译文取别义需说明依据。
   - **补出成分**：nissaya 补出的隐含主语/连接词，提示译文该不该补、补什么。
2. **准确性**：是否漏译、误译？术语是否符合 `knowledge/terms.md`？
3. **风格**：是否符合 `knowledge/style.md`？**重点查文言 / 半文半白**——逐句扫描文言虚词（之/其/乃/便/即/谓/於/遂）、文言句式（…者…也／于…之际／经…后／答以…）、单音节文言词（食用/用膳/端坐/盛装/年方）。发现即作为**必改项**列出，给出现代汉语改法（对照 `style.md` 第一节禁例表）。这是高频问题，务必逐处揪出。
4. **一致性**：同一术语在 chunk 内所有段落中是否一致？
5. **`⚠️[候选?]` 标记**：是否有该标而未标的？
6. **OCR / 原文疑问**：pali 原文是否有疑似讹误？（记下，不要改）

审稿意见涉及 nissaya 依据时，在"说明"中引用对应的 `巴利词= 缅文释义`。

## 输出格式

输出到 `reviews/{start_para}-{end_para}_v{n}.md`：

```markdown
# Review v{n} — {book}/{start_para}-{end_para}

## §{para} 句 <id>（id = book-para-word_start-word_end）
- **问题**：<分类> — <说明>
- **建议**：<具体修改方向>

## §{para} 句 <id>（id = book-para-word_start-word_end）
- ...
```

无问题的句子不必列出。
