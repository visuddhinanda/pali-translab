---
name: pali-evaluate
description: "Atomic skill: final evaluation of translations. Outputs final.jsonl with inline doubt markers and summary markdown with scores."
---

# pali-evaluate

译文最终评估原子能力。

## 调用方式

```
/pali-evaluate <book>/<para> [--method <name>]
```

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>/<para>`
2. 加载 method 配置（项目 `methods/<method>/evaluate.md` 优先于 skill `methods/default/evaluate.md`，整文件覆盖）
3. 加载 knowledge（同 pali-translate）
4. 读取 chunk 内所有最新版 v(n).jsonl
5. 加载 resources（按 method frontmatter `resources:` 字段）：
   - `pali`：取巴利原文
   - `nissaya`（如声明）：`scripts/fetch_channels.py --view paragraphs --book B --para P --type nissaya --lang my --uids-only` 发现 channel uid，再 `scripts/fetch_sentence.py --book B --para P --channels <uid>` 取句
   - 按 `(word_start, word_end)` 把 pali / nissaya 对齐到每条译文句
   - nissaya 返回 0 个 channel → 降级为纯 pali 评估（在理由中注明该段无 nissaya）
6. 评估并按“标注方法”用 span 原地标注问题片段（以 nissaya 为词级基准，见 method 文档）
7. 按 para 输出 final.jsonl + 按 chunk 产出总评 md

## 输出路径

```
workspace/tipitaka/{method}/jsonl/{book_id}/{para}/{para}_final.jsonl
workspace/tipitaka/{method}/jsonl/{book_id}/reviews/{start}-{end}_final.md
```

## 详细规范

参见 `methods/default/evaluate.md`
