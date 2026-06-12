---
name: pali-translate
description: "Atomic skill: translate Pali source text into Chinese. Reads pali/nissaya via wikipali API, outputs v1.jsonl per paragraph."
---

# pali-translate

巴利原文 → 中译初稿的原子翻译能力。

## 调用方式

```
/pali-translate <book>/<para> [--method <name>]
```

`<book>/<para>` 为 wikipali 坐标（如 `94/3` = DN Mahāvaggapāḷi 第 3 段）。

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>/<para>`
2. 加载 method 配置（**项目 `methods/<method>/translate.md` 优先于 skill `methods/default/translate.md`**，整文件覆盖）
3. 加载 knowledge：
   - skill `references/` 全部
   - 项目 `knowledge/style.md` / `terms.md` / `pitfalls.md`（如存在）
   - method frontmatter `knowledge:` 引用的项目 `knowledge/INDEX.md` 条目
4. 加载 resources（按 method frontmatter `resources:` 字段）：
   - `resources.toml` 解析资源名 → endpoint
   - 前缀 `skill:` 调本 skill 的脚本；`mcp:`（未来）调 MCP；普通路径读本地
5. 执行 `methods/default/translate.md` 中的翻译指南
6. 写出输出文件

## 资源命名约定

method 步骤文档 frontmatter `resources:` 字段使用人类可读 channel name（如 `_System_Pali_VRI_`），skill 启动时调 `scripts/fetch_channels.py` 转 UUID。

## 配置来源优先级

1. 命令行参数
2. 项目 `config.toml [wikipali]`
3. SKILL.md 默认值：
   - `wikipali.url` = `https://www.wikipali.org`
   - `wikipali.api_prefix` = `/api/v2`
   - `cache_dir` = `.cache/wikipali/`

## 输出与对齐

- 句子型资源（pali/nissaya/译文/注释）通过 `(book, paragraph, word_start, word_end)` 四元组对齐
- 输出 jsonl 每行至少含：`id` / `book` / `paragraph` / `word_start` / `word_end` / `pali` / `<translation>`

## 译文存放

```
workspace/tipitaka/{method}/jsonl/{book_id}/
├── INDEX.md               # 按 TOC 组织的导航，每次 run 自动重写
├── {para}/
│   └── {para}_v1.jsonl
└── reviews/               # review/evaluate 按 chunk 存放（由其他 skill 写入）
```

- `{method}` 命名建议：`pali-only` / `pali-nissaya` / `standard`
- INDEX.md 状态标记：✓ final / ⏳ v1/v2/v3 / ⚠️ 有疑问

## 资源降级规则

当 method 声明的资源不可用时（如 `pali-nissaya` method 某段无 nissaya channel），**降级翻译但不换目录**：

- 输出仍写入当前 method 目录（如 `tipitaka/pali-nissaya/jsonl/93/14/`）
- jsonl 中标注实际使用的资源：`"actual_resources": ["pali"]`（缺少的资源不列出）
- 不因个别段落资源缺失而把译文分散到不同 method 目录

## Chunk 批处理

按 chunk 批处理，而非逐段处理。

**组 chunk 方法**：从起始 para 逐段拉取巴利原文，累加字符数，当 buffer ≥ 5000 巴利字符时截断为一个 chunk。余下段落进入下一个 chunk。

**输出分离**：jsonl 翻译结果仍按 para 拆分写入各自目录。

**好处**：上下文连贯，术语/风格一致性更好，减少 LLM 调用次数。

## 详细规范

- API：参见 `references/wikipali_api.md`
- nissaya 结构：参见 `references/nissaya_format.md`
- 默认 method：参见 `methods/default/translate.md`
