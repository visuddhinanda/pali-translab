---
name: pali-review
description: "Atomic skill: review Pali-Chinese translations, output issue list as markdown. Does NOT modify translations."
---

# pali-review

译文审读原子能力。按 chunk 读取 v(n).jsonl，逐句审查，输出审稿意见 md。**不直接改译文**。

## 调用方式

```
/pali-review <book>/<para> [--version <n>] [--method <name>]
```

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>/<para>`，`--version` 默认为最新版本号
2. 加载 method 配置（项目 `methods/<method>/review.md` 优先于 skill `methods/default/review.md`，整文件覆盖）
3. 加载 knowledge（同 pali-translate）
4. 读取 chunk 内所有 para 的 `{para}/{para}_v{n}.jsonl`
5. 加载 resources（按 method frontmatter `resources:` 字段）：
   - `pali`：取巴利原文
   - `nissaya`（如声明）：`scripts/fetch_channels.py --view paragraphs --book B --para P --type nissaya --lang my --uids-only` 发现 channel uid，再 `scripts/fetch_sentence.py --book B --para P --channels <uid>` 取句
   - 按 `(word_start, word_end)` 把 pali / nissaya 对齐到每条 v(n) 译文句
   - nissaya 返回 0 个 channel → 降级为纯 pali 审查（在审稿意见中注明该段无 nissaya）
6. 执行审查（以 nissaya 为词级核对基准，见 method 文档）
7. 写出 `reviews/{start_para}-{end_para}_v{n}.md`

## Chunk 批处理

与 pali-translate 相同的 chunk 组织方式（≥ 5000 巴利字符）。一次性审查整个 chunk。

## 输出路径

```
workspace/tipitaka/{method}/jsonl/{book_id}/reviews/{start}-{end}_v{n}.md
```

## 详细规范

参见 `methods/default/review.md`
