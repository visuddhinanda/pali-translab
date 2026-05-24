---
resources:
  - pali
  # - nissaya       # 取消注释以启用（需 resources.toml 中已定义 channel）
knowledge: []        # 仅加载固定文件 + skill references
output: translations/{method}/{book}/{para}_v1.jsonl
---

# Translate (v1)

## 目标
基于 pali 原文，按项目 `knowledge/style.md` 声明的风格，逐句产出初稿。

## 工作方法

1. **发现该段可用资源**：调 `scripts/fetch_channels.py --view paragraphs --book {B} --para {P}`
2. **取 pali 原文**：用 `_System_Pali_VRI_` 的 uid（或 `fetch_channels.py --resolve _System_Pali_VRI_` 动态查），调 `fetch_sentence.py`
3. **取 nissaya（如有）**：在步骤 1 的结果中筛 `type=nissaya, lang=my`
   - 一键：`fetch_channels.py --view paragraphs --book B --para P --type nissaya --lang my --uids-only`
   - 返回 0 个 → **降级为纯 pali 翻译**，不报错
   - 返回 1 个 → 直接使用
   - 返回 2 个（不同来源）→ 都取，作为对照参考；以第一个为主，第二个标 `nissaya2_*` 前缀
4. **句对齐**：按 `(word_start, word_end)` 把 nissaya 对齐到 pali 句
5. **逐句翻译**：
   - 严格按 `knowledge/style.md` 中"语体 / 术语策略 / 原文显示"约定
   - 术语命中 `knowledge/terms.md` → 直接采用；命中 wikipali 术语表 → 次优采用
   - 不确定的译法**不要**猜——标 `⚠️[候选?]`，evaluate 步会处理
4. 输出 jsonl，每行：
   ```json
   {"id": "<sentence uuid>", "book": N, "paragraph": N,
    "word_start": N, "word_end": N,
    "pali": "...", "zh": "...", "confidence": 0-100}
   ```

## 不要做

- 不要补足省略的主语（除非歧义）
- 不要把 `⚠️[候选?]` 留空——必须给出"最不坏"的候选词
- 不要修改 pali 原文（即使发现疑似 OCR 错误，记入审稿意见而非改原文）
