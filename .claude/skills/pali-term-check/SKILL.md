---
name: pali-term-check
description: "Atomic skill: check terminology consistency across translations. Compares against term glossary and flags inconsistencies."
---

# pali-term-check

术语一致性检查原子能力。扫描译文 jsonl，对照术语表检查一致性。

## 调用方式

```
/pali-term-check <book>/<para> [--scope chunk|book|all] [--method <name>]
```

## 分派流程

1. 解析 `$ARGUMENTS`，确定检查范围
2. 加载 `knowledge/terms.md`（项目术语表）
3. 可选加载 wikipali 社区术语表（`/api/v2/term-vocabulary?view=community&lang=zh-Hans`）
4. 扫描指定范围内的所有 jsonl 文件
5. 逐句比对术语用法
6. 输出不一致报告

## 检查项

1. **术语表命中**：`terms.md` 中已定义的术语，译文是否采用了指定译法
2. **内部一致性**：同一巴利词在检查范围内是否使用了不同中文译法
3. **`⚠️[候选?]` 统计**：列出所有未决术语
4. **新术语发现**：出现频率 ≥ 3 但未登记在 `terms.md` 的巴利词

## 输出格式

> 表中「位置 / 首次出现」用句 id（`book-para-word_start-word_end`，如 `132-32-2-3`）定位。

```markdown
# Term Check Report — {book}/{scope}

## 术语表违规
| 巴利词 | 规定译法 | 实际译法 | 位置(id) |
|---|---|---|---|

## 内部不一致
| 巴利词 | 译法 A (N次) | 译法 B (N次) | 首次出现(id) |
|---|---|---|---|

## 未决术语
| 巴利词 | 当前候选 | 出现次数 |
|---|---|---|

## 新术语建议
| 巴利词 | 推断译法 | 出现次数 | 建议登记 |
|---|---|---|---|
```

## 输出路径

```
workspace/tipitaka/{method}/jsonl/{book_id}/reviews/term_check_{scope}.md
```
