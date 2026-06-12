---
name: pali-footnote
description: "Atomic skill: generate footnotes from Atthakatha/Tika commentaries for existing translations. Does not modify the main translation text."
---

# pali-footnote

从义注（Atthakathā）和复注（Ṭīkā）中查找相关解释，为现有译文生成脚注。

## 调用方式

```
/pali-footnote <book>/<para> [--method <name>]
```

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>/<para>`
2. 加载现有译文（final.jsonl 或最新 v(n).jsonl）
3. 通过 `resources.toml` 中的 `atthakatha` / `tika` 资源定位对应注释段
4. 为译文中的关键术语和难解句查找注释出处
5. 生成脚注，追加到 jsonl 的 `footnotes` 字段

## 输出格式

在现有 jsonl 基础上追加 `footnotes` 数组：

```json
{
  "id": "<book>-<para>-<word_start>-<word_end>", "book": N, "paragraph": N,
  "word_start": N, "word_end": N,
  "pali": "...", "zh": "...",
  "footnotes": [
    {
      "ref": "atthakatha",
      "source_book": N,
      "source_para": N,
      "pali_excerpt": "...",
      "note_zh": "..."
    }
  ]
}
```

## 输出路径

覆写原文件，或输出到带 `_annotated` 后缀的新文件（由调用方决定）。

## 资源需求

- `atthakatha`：义注 channel（需在 `resources.toml` 中配置）
- `tika`：复注 channel（可选）

## 待补充

- 义注/复注的 channel UUID 映射表（books.json 中已有义注书目，需确认 channel 对应关系）
- 脚注去重策略（同一术语在 chunk 内多次出现时）
