# Review — 168:3（channel: 73c03e1a-f333-11f0-808a-438f0af4b9e9）

> 资源：pali ✅／nissaya ❌（本段未注入）／义注 ❌（本段未注入）／父层对照 ❌（本层即本文 mūla，无父层）
> 说明：本 chunk 仅一句一词（篇题），nissaya 与义注均未注入，被解释词逐字核对无从执行。以下结论仅基于巴利原文与 `knowledge/` 规则。

## 跨段一致性
无（本 chunk 只有段 3 一段、一句）。

## §3 句 168-3-1-2
- **问题**：无。`Nidānavaggo` 为 SN 第二篇篇题，`nidāna` 作「因缘」、`vagga` 作「篇」，与传统汉译（《相应部·因缘篇》）一致；现代书面汉语，无文言腔，无工作标记，无 ASCII 引号。
- **建议**：`nidāna`／`vagga` 目前不在 `knowledge/term-glossary.jsonl` 中。全书三层都会反复出现这两个词（`vagga` 在下级还会与 `saṃyutta`「相应」、`sutta`「经」构成层级标题），建议定案后补录，以免后续段落出现「因缘品／缘起篇」一类漂移：
  - `{"pali": "nidāna", "zh": "因缘", "status": "confirmed"}`
  - `{"pali": "vagga", "zh": "篇", "note": "SN 大分层用「篇」；小分层若需与之区别再议", "status": "pending"}`
