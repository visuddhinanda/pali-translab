---
name: pali-term-check
description: "Atomic skill: check terminology consistency of translations stored in a WikiPali channel. Compares against the term glossary and flags inconsistencies. Read-only."
---

# pali-term-check

术语一致性检查原子能力。扫描 channel 里某个范围的译文，对照术语表检查一致性。
**只读，不写 channel。**

## 依赖

需要 **wikipali 插件**（`wikipali` CLI）。

## 调用方式

```
/pali-term-check <book>:<start>-<end> [--channel <uid>] [--method <name>]
```

范围也可以给单段（`216:35`）或整章（配合 `wikipali chapter <book>:<para>` 找边界）。

## 分派流程

1. 解析 `$ARGUMENTS`，确定 book / 段落范围 / 目标 channel
2. 加载 `knowledge/terms.md` 与 `knowledge/term-glossary.jsonl`
3. 取译文：`wikipali get <book>:<p1> <book>:<p2> … --json --channel <ch>`（可一次给多个坐标）
4. 可选取权威译名对照：`wikipali terms <词> --json`
5. 逐句比对术语用法
6. 输出不一致报告

## 检查项

1. **术语表命中**：`terms.md` 中已定义的术语，译文是否采用了指定译法
2. **内部一致性**：同一巴利词在检查范围内是否使用了不同中文译法
3. **残留工作标记**：译文里出现候选、待定、问号、TODO 之类的标记——一条都不该有，发现即列出
4. **新术语发现**：出现频率 ≥ 3 但未登记在 `terms.md` 的巴利词

## 输出格式

> 表中「位置 / 首次出现」用句 id（`book-para-word_start-word_end`，如 `216-35-2-17`）定位。

```markdown
# Term Check Report — {book}:{start}-{end}（channel: {name}）

## 术语表违规
| 巴利词 | 规定译法 | 实际译法 | 位置(id) |
|---|---|---|---|

## 内部不一致
| 巴利词 | 译法 A (N次) | 译法 B (N次) | 首次出现(id) |
|---|---|---|---|

## 残留工作标记
| 位置(id) | 标记原文 | 所在译文片段 |
|---|---|---|

## 新术语建议
| 巴利词 | 推断译法 | 出现次数 | 建议登记 |
|---|---|---|---|
```

## 输出路径

```
workspace/reports/{book}/term_check_{start}-{end}.md
```
