# Pali-TransLab 架构

> 四层分离：**知识层** / **技能层** / **工作流层** / **执行层**
> 目标：skill 可独立发布复用，批量处理确定性可控，人工校对灵活组合。

---

## 一、四层架构总览

```
知识层 knowledge/
  style.md                 ← 翻译风格配置（skill 自动加载）
  terms.md                 ← 术语偏好（skill 自动加载）
  pitfalls.md              ← 已知坑（skill 自动加载）
  translation-rules.md     ← 从校对中蒸馏出的翻译规则，版本化管理
  term-glossary.jsonl      ← 术语表（结构化）
  known-issues.md          ← 已知难点和处理方案
  INDEX.md                 ← 自定义知识文件索引
  concepts/                ← 自定义概念笔记
  grammar/                 ← 自定义语法笔记

技能层 .claude/skills/
  pali-translate/          ← 原子能力：巴利原文 → 中译初稿
  pali-review/             ← 原子能力：译文审读，输出问题清单
  pali-revise/             ← 原子能力：根据审读意见修订译文
  pali-evaluate/           ← 原子能力：译文质量评分
  pali-footnote/           ← 原子能力：从义注查找并生成脚注
  pali-term-check/         ← 原子能力：术语一致性检查
  translate/               ← [旧] 伞形 skill，保留供参考

工作流层 .claude/commands/
  translate.md             ← 组合：translate → term-check
  translate-review.md      ← 组合：translate → review → revise (x2) → term-check
  annotate.md              ← 组合：footnote（只加注，不翻译）
  full-pipeline.md         ← 组合：完整流程
  extract-rules.md         ← 工具：从 audit.log 蒸馏规则 → 更新知识层

执行层 scripts/
  translate_batch.sh       ← 批量翻译，直接注入内容，支持断点续传
  audit.log                ← 结构化操作日志（JSONL）
```

---

## 二、各层职责

### 知识层 `knowledge/`

用户/团队的领域知识。进 repo，团队共享，注入每次翻译上下文。

- **固定文件**（`style.md` / `terms.md` / `pitfalls.md`）：skill 按约定路径自动读取
- **规则文件**（`translation-rules.md` / `term-glossary.jsonl` / `known-issues.md`）：从人工校对中蒸馏，版本化管理
- **自定义条目**（`concepts/` / `grammar/`）：须登记在 `INDEX.md`，由 method frontmatter 引用

### 技能层 `.claude/skills/`

通用、可发布、零项目依赖的原子能力。每个 skill 职责单一：

| Skill | 输入 | 输出 | 改译文？ |
|---|---|---|---|
| pali-translate | pali 原文 (+ nissaya) | v1.jsonl | — |
| pali-review | v(n).jsonl | review md | 否 |
| pali-revise | v(n).jsonl + review md | v(n+1).jsonl | 是 |
| pali-evaluate | v(n).jsonl | final.jsonl + final.md | 是（标注） |
| pali-footnote | final.jsonl + 义注 | jsonl + footnotes | 追加 |
| pali-term-check | jsonl 范围 | term report md | 否 |

每个 skill 内部结构：
```
.claude/skills/<name>/
├── SKILL.md                    # 触发条件 + 主流程
├── methods/default/            # 默认 method（项目可整文件覆盖）
├── references/                 # 业务强绑定知识（不可覆盖）
└── scripts/                    # 数据获取脚本（过渡期 HTTP，未来 MCP）
```

### 工作流层 `.claude/commands/`

组合多个 skill 的预定义流程。每个 command 明确写明调用哪些 skills、执行顺序、输入输出。

交互模式下用 `/command-name` 调用。

### 执行层 `scripts/`

批量自动化脚本。**不依赖 Skills 自动触发**，直接读取文件内容拼接提示词，用 `claude -p` 非交互模式执行。

---

## 三、两种使用模式

### 人工校对模式（交互）

在 Claude Code 中用自然语言或 slash commands 驱动：
- `/pali-translate 94/3` — 单步翻译
- `/translate-review 94/3` — 翻译 + 两轮审修
- `/full-pipeline 94/3` — 完整流程
- `/annotate 94/3` — 给现有译文加脚注

灵活组合，可中途人工介入修改。

### 批量处理模式（自动）

```bash
./scripts/translate_batch.sh 94 3 100 --method pali-only
```

确定性执行：
- 直接注入 SKILL.md + knowledge 内容到提示词
- 每次调用上下文完全相同
- 支持断点续传（跳过已有 v1.jsonl）
- 结构化审计日志（audit.log）

---

## 四、Method 覆盖规则

1. 项目 `methods/<method>/<step>.md` 存在 → 使用项目版本（**整文件覆盖**）
2. 不存在 → 回退到 `.claude/skills/<skill>/methods/default/<step>.md`

### Knowledge 加载

1. **skill `references/`**：业务强绑定，总是加载，不可覆盖
2. **项目固定文件**（`style.md` / `terms.md` / `pitfalls.md`）：自动加载
3. **项目自定义条目**：须登记在 `INDEX.md`，由 method frontmatter `knowledge:` 引用

追加而非覆盖。

---

## 五、如何新增 Skill

1. 在 `.claude/skills/<name>/` 创建目录
2. 写 `SKILL.md`（frontmatter 含 `name` 和 `description`）
3. 可选：`methods/default/` 放默认 method，`references/` 放业务知识，`scripts/` 放数据脚本
4. 在相关 command 文件中引用新 skill
5. 如需批量处理，在 `scripts/` 中创建对应的注入式脚本

---

## 六、知识蒸馏循环

```
人工校对 → audit.log 记录 → /extract-rules 分析 → 人工确认 → 更新 knowledge/
                                                                    ↓
                                                            下次翻译自动加载
```

1. 交互模式下人工校对时，操作记录追加到 `scripts/audit.log`
2. `/extract-rules` 命令分析日志，聚类提取可泛化规则
3. 人工确认后用 `/translate learn` 写入 `knowledge/`
4. 下次翻译（交互或批量）自动加载更新后的知识

---

## 七、配置文件

### `config.toml`（项目元信息）

```toml
[project]
name = "pali-translab"
target_lang = "zh-Hans"

[corpus]
books = ["dn", "mn"]

[wikipali]
endpoint = "https://wikipali.org/api"
```

### `resources.toml`（资源映射）

```toml
pali       = "skill:pali-translate/scripts/fetch_sentence.py --book {book} --para {para} --channels <uuid>"
nissaya    = "skill:pali-translate/scripts/fetch_channels.py --view paragraphs --book {book} --para {para}"
atthakatha = "skill:pali-footnote/scripts/fetch_sentence.py --book {book} --para {para} --channels <uuid>"
```

skill 按前缀分发：`skill:` 调脚本、`mcp:` 调 MCP tool、普通路径读本地文件。

---

## 八、输出目录结构

```
workspace/tipitaka/{method}/
├── jsonl/{book_id}/
│   ├── INDEX.md
│   ├── {para}/
│   │   ├── {para}_v1.jsonl
│   │   ├── {para}_v2.jsonl
│   │   ├── {para}_v3.jsonl
│   │   └── {para}_final.jsonl
│   └── reviews/
│       ├── {start}-{end}_v1.md
│       ├── {start}-{end}_v2.md
│       ├── {start}-{end}_final.md
│       └── term_check_chunk.md
├── mdbook/
├── html/
└── epub/
```

---

## 九、与旧架构的关系

旧架构将 translate/review/revise/evaluate 合并在 `.claude/skills/translate/` 一个伞形 skill 里。新架构拆分为独立原子 skill + command 组合层，原有 `translate/` 目录保留供参考，不再作为主工作流使用。

旧文档 `WORKFLOW.md` 中的流程定义仍然有效（translate→review→revise→evaluate 流水线），但实现方式从单一 skill 分派改为 command 组合多个独立 skill。
