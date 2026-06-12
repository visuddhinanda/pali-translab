---
resources:
  - pali
  # - nissaya       # 取消注释以启用（需 resources.toml 中已定义 channel）
knowledge: []        # 仅加载固定文件 + skill references
output: tipitaka/{method}/jsonl/{book}/{para}/{para}_v1.jsonl
---

# Translate (v1)

## 目标
基于 pali 原文，按项目 `knowledge/style.md` 声明的风格，逐句产出初稿。

## 工作方法

### 1. 组 Chunk

从起始 para 开始，逐段拉取巴利原文，累加字符数。当 buffer ≥ 5000 巴利字符时截断为一个 chunk。

```
for para in range(start_para, ...):
    text = fetch_sentence(book, para, pali_channel)
    buffer += text
    if len(buffer) >= 5000:
        → 翻译当前 chunk
        → 清空 buffer，开始下一个 chunk
```

### 2. 取资源

对 chunk 内每段：
- **取 pali 原文**：用 `_System_Pali_VRI_` uid，调 `fetch_sentence.py`
- **取 nissaya（如有）**：`fetch_channels.py --view paragraphs --book B --para P --type nissaya --lang my --uids-only`
  - 返回 0 个 → **降级为纯 pali 翻译**，输出目录不变，jsonl 中标注 `"actual_resources": ["pali"]`
  - 返回 1 个 → 直接使用
  - 返回 2 个 → 都取，以第一个为主
- **句对齐**：按 `(word_start, word_end)` 把 nissaya 对齐到 pali 句

### 3. 翻译整个 Chunk

将 chunk 内所有段落的巴利原文（+ nissaya）一次性提交翻译：
- 严格按 `knowledge/style.md` 中"语体 / 术语策略 / 原文显示"约定
- 术语命中 `knowledge/terms.md` → 直接采用；命中 wikipali 术语表 → 次优采用
- 不确定的译法**不要**猜——标 `⚠️[候选?]`，evaluate 步会处理
- chunk 内术语保持一致

### 4. 输出

按 para 拆分写入各自目录，每行 jsonl：
```json
{"id": "<book>-<para>-<word_start>-<word_end>", "book": N, "paragraph": N,
 "word_start": N, "word_end": N,
 "pali": "...", "zh": "...", "confidence": 0-100}
```

## 不要做

- 不要补足省略的主语（除非歧义）
- 不要把 `⚠️[候选?]` 留空——必须给出"最不坏"的候选词
- 不要修改 pali 原文（即使发现疑似 OCR 错误，记入审稿意见而非改原文）
