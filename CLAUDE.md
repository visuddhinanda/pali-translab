# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目状态

**当前处于设计阶段，无实现代码。** `src/dahlia/` 仅有空 `__init__.py`。不要"完善"或"补全"源码，除非用户明确要求开始实现。

## 权威设计文档

按以下顺序阅读以建立全局认知（修改任何架构相关内容前必读）：

1. `@DESIGN.md` — 原始设计、术语、整体目标
2. `@ARCHITECTURE.md` — 三层架构契约（Skill / MCP / 项目层），加载与覆盖规则，固定文件清单
3. `@WORKFLOW.md` — 翻译流水线（translate→review→revise→evaluate）、method 文档规范、反哺学习

**冲突时以 ARCHITECTURE.md 为准**（结构契约优先于流程描述）。

## 硬约束

- **不要擅自创建目录或文件。** 用户明确说过"先不要建立任何目录和文件"。仅在用户明确批准的范围内落盘。
- **不要把项目特定的内容写进 skill。** Skill 必须零项目依赖，可发布到 skills 市场。
- **不要把"业务流强绑定"的通用知识写进项目 `knowledge/`。** 那些属于 skill `references/`（项目目前作为占位临时存放，未来要迁出）。

## 架构要点（不读架构文档时也要遵守）

- **四层**：知识层（`knowledge/`）/ 技能层（`.claude/skills/pali-*`，原子能力）/ 工作流层（`.claude/commands/`，组合 skill）/ 执行层（`scripts/`，批量自动化）
- **原子 Skills**：pali-translate / pali-review / pali-revise / pali-evaluate / pali-footnote / pali-term-check，各自独立
- **批量处理**：`scripts/translate_batch.sh` 直接注入 SKILL.md + knowledge 内容到提示词，不依赖 Skills 自动触发
- **数据源**：过渡期 skill 内 `scripts/*.py` 调 wikipali HTTP API；未来切 MCP。**不依赖项目本地语料文件。**
- **Method 覆盖**：项目 `methods/<name>/<step>.md` 整文件覆盖 skill `methods/default/<step>.md`，不做字段合并
- **Knowledge 分层**：
  - skill `references/`（业务强绑定，不可覆盖）
  - 项目 `knowledge/` 固定文件 `style.md` / `terms.md` / `pitfalls.md`（skill 自动加载）
  - 项目 `knowledge/` 规则文件 `translation-rules.md` / `term-glossary.jsonl` / `known-issues.md`
  - 项目 `knowledge/INDEX.md` 登记的自定义条目（method frontmatter 按条目名引用）
- **资源映射**：`resources.toml` 用前缀分发——`skill:` 调脚本、`mcp:` 调 MCP tool、普通路径读本地文件

## 技术栈

- Python 3.14，包名 `dahlia`（见 `pyproject.toml`）
- 依赖含 SQLAlchemy / psycopg / langchain / minio / pika（**尚未在代码中使用**）
- 数据库配置模板：`config.orig.toml`（实际配置 `config.toml` 应 gitignore）

## 沟通风格

- 用户使用中文沟通，偏好**简短直接**的回复。避免末尾总结、不必要的客套。
- 设计讨论时先给出方案要点，让用户判断方向，再细化。不要一次性堆大段方案。
- 涉及架构调整时，先核对 `ARCHITECTURE.md` 是否需要同步更新。
