---
name: pali-revise
description: "Atomic skill: revise translations based on review feedback. Reads review markdown + v(n).jsonl, outputs v(n+1).jsonl."
---

# pali-revise

根据审读意见修订译文的原子能力。

## 调用方式

```
/pali-revise <book>/<para> [--version <n>] [--method <name>]
```

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>/<para>`，`--version` 默认为最新版本号
2. 加载 method 配置（项目 `methods/<method>/revise.md` 优先于 skill `methods/default/revise.md`，整文件覆盖）
3. 加载 knowledge（同 pali-translate）
4. 读取 chunk review md（`reviews/{start}-{end}_v{n}.md`）和 chunk 内所有 v(n).jsonl
5. 逐条采纳/拒绝审稿意见
6. 按 para 拆分输出 v(n+1).jsonl

## 输出路径

```
workspace/tipitaka/{method}/jsonl/{book_id}/{para}/{para}_v{n+1}.jsonl
```

## 详细规范

参见 `methods/default/revise.md`
