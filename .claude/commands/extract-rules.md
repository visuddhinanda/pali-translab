---
description: "Extract translation rules from audit.log into knowledge layer."
---

# extract-rules — 从审计日志蒸馏翻译规则

工具命令：读取 `scripts/audit.log`，分析人工校对记录，更新知识层。

## 执行顺序

1. **读取** `scripts/audit.log`（JSONL 格式）
2. **分析** 每条校对记录的 `op` 和 `reason` 字段
3. **聚类** 相似原因，提取可泛化的翻译规则
4. **输出建议**（不自动写入，需人工确认）：
   - 术语规则 → 建议追加到 `knowledge/term-glossary.jsonl`
   - 翻译规则 → 建议追加到 `knowledge/translation-rules.md`
   - 已知难点 → 建议追加到 `knowledge/known-issues.md`

## 输入格式

```
/extract-rules [--since <date>] [--min-count <n>]
```

- `--since`：只分析此日期之后的记录（默认：全部）
- `--min-count`：某类问题出现至少 N 次才提取为规则（默认：2）

## 输出

在 stdout 输出建议清单，格式：

```markdown
## 建议更新术语表
| 巴利词 | 建议译法 | 出处 | 出现次数 |
|---|---|---|---|

## 建议新增翻译规则
1. **规则描述** — 依据：N 条记录（列出 id）

## 建议记录已知难点
1. **难点描述** — 处理方案建议
```

**人工确认后**再用 `/translate learn` 写入知识层。
