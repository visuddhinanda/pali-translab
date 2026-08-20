# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目状态

**当前处于设计阶段，无实现代码。** `src/dahlia/` 仅有空 `__init__.py`。不要"完善"或"补全"源码，除非用户明确要求开始实现。

## 权威设计文档

按以下顺序阅读以建立全局认知（修改任何架构相关内容前必读）：

1. `@ARCHITECTURE.md` — 四层架构契约、**数据流硬约束**、加载与覆盖规则
2. `@WORKFLOW.md` — 翻译流水线（translate→review→revise→evaluate）、method 文档规范、反哺学习
3. `@DESIGN.md` — ⚠️ 历史文档，多数已作废，只看项目目标与术语

**冲突时以 ARCHITECTURE.md 为准**（结构契约优先于流程描述）。

## 硬约束

- **译文只写 wikipali channel，不写本地 json。** 没有 v1/v2/final 文件。用户明确要本地副本时，用 `/export` 导出 markdown（一章一文件，带 YAML frontmatter）。
- **坐标不能编造。** 写前用 `wikipali get` 取真实坐标比对，写后独立读回核对；条数不符要如实报告，不要说"已全部写入"。
- **不要擅自创建目录或文件。** 仅在用户明确批准的范围内落盘。
- **不要把项目特定的内容写进 skill。** Skill 必须零项目依赖（除 wikipali 插件这一外部 CLI），可发布到 skills 市场。
- **不要把"业务流强绑定"的通用知识写进项目 `knowledge/`。** 那些属于 skill `references/`。

## 架构要点（不读架构文档时也要遵守）

- **四层**：知识层（`knowledge/`）/ 技能层（`.claude/skills/pali-*`，原子能力）/ 工作流层（`.claude/commands/`，组合 skill）/ 执行层（`scripts/`，批量自动化）
- **原子 Skills**：pali-translate / pali-review / pali-revise / **pali-harmonize** / pali-evaluate / pali-footnote / pali-term-check / pali-export，各自独立
- **数据流**：wikipali 读 → 处理 → wikipali channel 写（**覆盖式**，同坐标替换）。channel 就是流水线状态，每步从 channel 读回上一步结果，所以中断能接上
- **资源分工**：translate **只看巴利原文**；**义注定释义、nissaya 定词法**，两者从 review 才介入（译者与标准同源就查不出错），冲突以义注为准。改译文的是 translate / revise / harmonize / footnote，review 与 evaluate 非侵入只出报告。**evaluate 排在流水线最后**——评的必须是定稿
- **三层都译**：本文 / 义注 / 复注分别翻译（坐标由 `wikipali books` + `cs_para` 本地算出，见 `scripts/layers.py`；**全书级不用 `related`**——它是段级接口、一次约 1.5 秒，只留给单段临时查对应）。**被解释词与父层逐字同译**是硬约束——义注黑体引自本文、复注黑体引自义注
- **按 chunk 提交**：一次连续若干段交同一次调用（默认 ≤5000 巴利字符 / ≤12 段），跨段漂移才看得见；再 **harmonize 跨三层统稿**（对齐被解释词 + 统一术语/语体/称谓 + 修正问题，但不重译、不为「更顺」而改），最后 evaluate 验收
- **数据访问**：全部经 **wikipali 插件**的 `wikipali` CLI（`get` / `versions` / `related` / `toc` / `channels` / `write`）。skill 内不再有 `scripts/`，不直连 HTTP，不读本地语料
- **写入规矩**以插件的 `wikipali:write` skill 与 `references/conventions.md` 为准，本项目不重复定义
- **本地只留过程记录**：`workspace/reports/`（审稿意见、总评、术语报告）、`workspace/audit.log`（断点续传台账）、`workspace/export/`（按需导出的 markdown）。全部 gitignore
- **批量处理**：`scripts/pipeline_batch.sh` 直接注入 SKILL.md + method + knowledge 到提示词，不依赖 Skills 自动触发
- **Method 覆盖**：项目 `methods/<name>/<step>.md` 整文件覆盖 skill `methods/default/<step>.md`，不做字段合并
- **Knowledge 分层**：
  - skill `references/`（业务强绑定，不可覆盖）
  - 项目 `knowledge/` 固定文件 `style.md` / `terms.md` / `pitfalls.md`（skill 自动加载）
  - 项目 `knowledge/` 规则文件 `translation-rules.md` / `term-glossary.jsonl` / `known-issues.md`
  - 项目 `knowledge/INDEX.md` 登记的自定义条目（method frontmatter 按条目名引用）

## 技术栈

- Python 3.14，包名 `dahlia`（见 `pyproject.toml`）
- 依赖含 SQLAlchemy / psycopg / langchain / minio / pika（**尚未在代码中使用**）
- `scripts/*.py` 只用标准库，通过 subprocess 调 `wikipali` CLI
- 配置模板：`config.orig.toml`（实际配置 `config.toml` 已 gitignore；不存 token，凭据在 `~/.wikipali/credentials.json`）
- 外部依赖：**wikipali 插件**（`/mnt/visuddhinanda/workspace/wikipali-plugins`）。`command -v wikipali` 为空时用 `${CLAUDE_PLUGIN_ROOT}/bin/wikipali` 并提醒重启会话

## 沟通风格

- 用户使用中文沟通，偏好**简短直接**的回复。避免末尾总结、不必要的客套。
- 设计讨论时先给出方案要点，让用户判断方向，再细化。不要一次性堆大段方案。
- 涉及架构调整时，先核对 `ARCHITECTURE.md` 是否需要同步更新。
