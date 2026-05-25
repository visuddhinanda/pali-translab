---
name: translate
description: Pali Buddhist text translation pipeline. Subcommands: run/review/revise/evaluate/pipeline/learn. Reads source/nissaya/translations from wikipali API; method/style configurable per project.
---

# translate

巴利三藏翻译工作流伞形 skill。所有子命令共享 method 配置、resources、knowledge 上下文。

## 调用方式

```
/translate <subcommand> <book>/<para> [--method <name>]
```

`<book>/<para>` 为 wikipali 坐标（如 `94/3` = DN Mahāvaggapāḷi 第 3 段）。

### 子命令

| 子命令 | 输入 | 输出 |
|---|---|---|
| `run` | resources | `tipitaka/{method}/jsonl/{book}/{para}/{para}_v1.jsonl` |
| `review` | v(n).jsonl + resources | `tipitaka/{method}/jsonl/{book}/{para}/{para}_v(n).md`（审稿意见，不改译文） |
| `revise` | v(n).jsonl + v(n).md | `tipitaka/{method}/jsonl/{book}/{para}/{para}_v(n+1).jsonl` |
| `evaluate` | v3.jsonl + resources | `tipitaka/{method}/jsonl/{book}/{para}/{para}_final.jsonl` + `{para}_final.md` |
| `pipeline` | 同 run | 按 `method.md` 的 `steps:` 串联跑完 |
| `learn` | 自由文本 + 目标条目 | 追加到项目 `knowledge/` 对应文件 |
| `export` | jsonl src | `tipitaka/{method}/mdbook/`（mdbook 源码）+ `html/` + `epub/` |

## 分派流程

1. 解析 `$ARGUMENTS` 第一个 token 为子命令名
2. 解析 `<book>/<para>`
3. 加载 method 配置（**项目 `methods/<method>/<step>.md` 优先于 skill `methods/default/<step>.md`**，整文件覆盖）
4. 加载 knowledge：
   - skill `references/` 全部
   - 项目 `knowledge/style.md` / `terms.md` / `pitfalls.md`（如存在）
   - method frontmatter `knowledge:` 引用的项目 `knowledge/INDEX.md` 条目
5. 加载 resources（按 method frontmatter `resources:` 字段）：
   - `resources.toml` 解析资源名 → endpoint
   - 前缀 `skill:` 调本 skill 的脚本；`mcp:`（未来）调 MCP；普通路径读本地
6. 执行子命令对应的 step 文档（自然语言指南）
7. 写出输出文件

## 资源命名约定

method 步骤文档 frontmatter `resources:` 字段使用人类可读 channel name（如 `_System_Pali_VRI_`），skill 启动时调 `scripts/fetch_channels.py` 转 UUID。

特殊名：
- `prev_translation` → 自动解析为 v(n-1) jsonl
- `prev_review` → 自动解析为 v(n-1) md

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

## 译文存放（重要）

**Src（机器/回写）**：扁平 jsonl，便于程序处理和未来上传 wikipali

```
workspace/tipitaka/{method}/jsonl/{book_id}/
├── INDEX.md               # 按 TOC 组织的导航，每次 run/evaluate 自动重写
└── {para}/
    ├── {para}_v1.jsonl
    ├── {para}_v1.md       # review 输出
    ├── {para}_v2.jsonl
    ├── ...
    ├── {para}_final.jsonl
    └── {para}_final.md    # evaluate 总评
```

- `{method}` 命名建议：`pali-only` / `pali-nissaya` / `standard`
- INDEX.md 状态标记：✓ final / ⏳ v1/v2/v3 / ⚠️ 有疑问

**Dist（人读）**：按格式分目录

```
workspace/tipitaka/{method}/
├── jsonl/{book_id}/       # 源数据（上面的 Src）
├── mdbook/                # mdbook 源码（book.toml + src/）
├── html/                  # mdbook build 输出
└── epub/                  # epub 输出
```

由 `/translate export {book_id}` 子命令从 jsonl src 派生。展示是否含 pali 原文由项目 `knowledge/style.md` 的"显示巴利原文"决定。默认导出 `final` 版本，缺则跳过。

## 资源降级规则

当 method 声明的资源不可用时（如 `pali-nissaya` method 某段无 nissaya channel），**降级翻译但不换目录**：

- 输出仍写入当前 method 目录（如 `tipitaka/pali-nissaya/jsonl/93/14/`）
- jsonl 中标注实际使用的资源：`"actual_resources": ["pali"]`（缺少的资源不列出）
- 不因个别段落资源缺失而把译文分散到不同 method 目录

## 详细规范

- 工作流：参见 `references/workflow.md`
- API：参见 `references/wikipali_api.md`
- nissaya 结构：参见 `references/nissaya_format.md`
- 默认 method：参见 `methods/default/`
