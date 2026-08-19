# Pali-TransLab 架构

> 四层分离：**知识层** / **技能层** / **工作流层** / **执行层**
> 目标：skill 可独立发布复用，批量处理确定性可控，人工校对灵活组合。
>
> **译文的唯一去处是 wikipali channel。本地不存 json。**

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
  pali-translate/          ← 原子能力：巴利原文 → 中译初稿 → 写入 channel
  pali-review/             ← 原子能力：读回译文审读，输出问题清单（只读）
  pali-revise/             ← 原子能力：按审读意见修订，覆盖写回 channel
  pali-harmonize/          ← 原子能力：跨三层统稿，对齐被解释词 + 统一用词语体 + 修正问题
  pali-evaluate/           ← 原子能力：**流水线最后一步**，给定稿打分出报告（只读）
  pali-footnote/           ← 原子能力：从义注生成随文注，覆盖写回 channel
  pali-term-check/         ← 原子能力：术语一致性检查（只读）
  pali-export/             ← 原子能力：channel → 本地 markdown，一章一文件

工作流层 .claude/commands/
  translate.md             ← 组合：translate → term-check
  translate-review.md      ← 组合：translate → review → revise → term-check
  full-pipeline.md         ← 组合：完整流程
  harmonize.md             ← 组合：harmonize（整章统稿，流水线最后一步）
  annotate.md              ← 组合：footnote（只加注，不翻译）
  export.md                ← 组合：export（只在用户要本地文件时跑）
  extract-rules.md         ← 工具：从 audit.log + 报告蒸馏规则 → 更新知识层

执行层 scripts/
  _wp.py                   ← wikipali CLI 共用薄封装（黑体转 **…**，页码标记剔除）
  layers.py                ← 解析本文/义注/复注三层坐标与父层映射
  wp_pull.py               ← 取一批段落的原文 / nissaya / 义注 / 现有译文，对齐成逐句结构
  wp_push.py               ← 校验坐标与条数后写入 channel，写后读回核对
  export_markdown.py       ← channel → 本地 markdown（一章一文件，YAML frontmatter）
  pipeline_batch.sh        ← 批量流水线，注入式提示词，断点续传
```

---

## 二、数据流（这是本项目最重要的约束）

```
wikipali（pali / nissaya / 义注）
        ↓ 读
    translate → review → revise → harmonize → footnote →（最后）evaluate
        ↓ 写（覆盖式，同坐标替换）
wikipali channel  ←—— 译文的正本，唯一去处
        ↓ 可选，按用户要求
workspace/export/{章节路径}/{章节名}.md   ← 一章（经文）一个文件，带 YAML frontmatter
```

**硬约束**：

- **译文不写本地 json。** 没有 v1/v2/final 文件，channel 里就是最新一版
- **写入是覆盖式的**：相同 `(book, paragraph, word_start, word_end, channel)` 的旧句子被替换；
  没提交的坐标原样保留，所以 **revise / harmonize 只提交改动过的句子**，不回传整个 chunk
  （translate 是整段新建，全部提交）
- **只有 translate / revise / harmonize / footnote 改译文**；review 与 evaluate 是**非侵入**的，只出报告
- **evaluate 排在最后**：评的必须是走完全部改动步骤的定稿，中途评的是半成品
- **translate 只看巴利原文**，不给义注、不给 nissaya；这两样是 review / revise / evaluate 的
  独立对照标准（**义注定释义，nissaya 定词法**）。译者与标准同源，复核就查不出错——
  这条不是效率取舍，是复核有没有意义的前提
- **三层都译**：本文 mūla / 义注 aṭṭhakathā / 复注 ṭīkā 分别翻译，坐标由 `wikipali related`
  逐层解析（三层在不同的书里）。**被解释词必须与父层逐字同译**——义注的黑体引自本文、
  复注的黑体引自义注，不一致读者就看不出这条注在注哪个词
- **按 chunk 提交，不逐段孤立处理**：一次把连续若干段交给同一次调用，跨段的术语漂移与
  语体不一致才看得见。最后再由 harmonize 跨三层统一收口
- **坐标不能编造**：写前用 `wikipali get` 取真实坐标做集合比对，写后独立读回
- **本地只留过程记录**：审稿意见、总评、术语报告、audit.log —— 这些不是译文
- 需要修订前后的对照时，先 `/export` 导出快照，再改 channel

## 三、外部依赖：wikipali 插件

数据的读写全部经 **wikipali 插件**的 `wikipali` CLI（`/mnt/visuddhinanda/workspace/wikipali-plugins`），
不直连 HTTP，不读本地语料。

| 用途 | 命令 |
|---|---|
| 取原文 / 译文 | `wikipali get <book>:<para> --json [--channel <uid>]` |
| 查该坐标有哪些 channel | `wikipali versions <book>:<para> --json` |
| 找义注 / 复注对应 | `wikipali related <book>:<para> --json` |
| 章节边界 | `wikipali toc <book>:<para> --json` |
| **整书结构 + 跨层对应** | `wikipali paras <book>:3 --body --json`（含 `cs_para`，**规划首选**） |
| 可写 channel 列表 | `wikipali channels --json` |
| 写入 | `wikipali write - --channel <uid>` |

写入的全部硬约束（不索要密码、写前确认、坐标不编造、写后读回、现代汉语、
注释与术语标记格式）以插件的 `wikipali:write` skill 与 `references/conventions.md`
为准，本项目不重复定义。

---

## 四、各层职责

### 知识层 `knowledge/`

用户/团队的领域知识。进 repo，团队共享，注入每次翻译上下文。

- **固定文件**（`style.md` / `terms.md` / `pitfalls.md`）：skill 按约定路径自动读取
- **规则文件**（`translation-rules.md` / `term-glossary.jsonl` / `known-issues.md`）：从人工校对中蒸馏，版本化管理
- **自定义条目**（`concepts/` / `grammar/`）：须登记在 `INDEX.md`，由 method frontmatter 引用

### 技能层 `.claude/skills/`

通用、可发布、零项目依赖的原子能力（只依赖 wikipali 插件这一外部 CLI）。每个 skill 职责单一：

| Skill | 输入 | 输出 | 改 channel？ |
|---|---|---|---|
| pali-translate | 本层 pali（+ 父层译文作被解释词对照） | channel 译文 | 是（新写） |
| pali-review | channel 译文 + pali/义注/nissaya | review md | 否 |
| pali-revise | channel 译文 + review md + 义注/nissaya | channel 译文 | 是（覆盖） |
| pali-harmonize | 三层 channel 译文 + pali | 对齐并统一后的三层译文 | 是（覆盖） |
| pali-evaluate | channel 译文 + pali/义注/nissaya（**最后一步**） | final md（评分 + 问题清单） | 否 |
| pali-footnote | channel 译文 + 义注 | channel 译文 | 是（覆盖，加随文注） |
| pali-term-check | channel 译文范围 | term report md | 否 |
| pali-export | channel 译文 + toc | 本地 markdown | 否 |

每个 skill 内部结构：
```
.claude/skills/<name>/
├── SKILL.md                    # 触发条件 + 主流程
├── methods/default/            # 默认 method（项目可整文件覆盖）
└── references/                 # 业务强绑定知识（不可覆盖）
```

skill 内不再有 `scripts/`——数据访问统一走 wikipali CLI。

### 工作流层 `.claude/commands/`

组合多个 skill 的预定义流程。每个 command 明确写明调用哪些 skills、执行顺序、输入输出。

交互模式下用 `/command-name` 调用。

### 执行层 `scripts/`

批量自动化。**不依赖 Skills 自动触发**，直接读 SKILL.md + method + knowledge 拼提示词，
用 `claude -p` 非交互模式执行，结果经 `wp_push.py` 写入 channel。

---

## 五、两种使用模式

### 人工校对模式（交互）

```
/translate 216:35              # 翻译 + 术语检查
/translate-review 216:35       # 翻译 + 一轮审修
/full-pipeline 216:35          # 完整流程
/harmonize 216:35              # 整章统稿（流水线最后一步）
/annotate 216:35               # 给现有译文加随文注
/export 93:983                 # 导出本地 markdown
```

灵活组合，可中途人工介入修改。

### 批量处理模式（自动）

```bash
./scripts/pipeline_batch.sh 216 28 41 --channel <uid> --nissaya --atthakatha
```

确定性执行：

- 直接注入 SKILL.md + method + knowledge 内容到提示词
- 每次调用上下文完全相同
- **按 chunk 提交**：累加到 `--chunk-chars`（默认 5000 巴利字符）或 `--max-paras`（默认 12 段）就切一刀
- **断点续传靠 `workspace/audit.log`**：按段记账，整个 chunk 都做过才跳过——改 chunk 大小重跑也不会重做
- 每一步都从 channel 读回上一步结果，所以中断后能接上
- **三阶段**：先所有 chunk 做 translate/review/revise，再按 `wikipali toc` 切章 harmonize，最后所有 chunk 做 evaluate

---

## 六、Method 覆盖规则

1. 项目 `methods/<method>/<step>.md` 存在 → 使用项目版本（**整文件覆盖**）
2. 不存在 → 回退到 `.claude/skills/<skill>/methods/default/<step>.md`

### Knowledge 加载

1. **skill `references/`**：业务强绑定，总是加载，不可覆盖
2. **项目固定文件**（`style.md` / `terms.md` / `pitfalls.md`）：自动加载
3. **项目自定义条目**：须登记在 `INDEX.md`，由 method frontmatter `knowledge:` 引用

追加而非覆盖。

---

## 七、如何新增 Skill

1. 在 `.claude/skills/<name>/` 创建目录
2. 写 `SKILL.md`（frontmatter 含 `name` 和 `description`）
3. 可选：`methods/default/` 放默认 method，`references/` 放业务知识
4. 数据访问一律用 wikipali CLI，不要在 skill 里塞 HTTP 客户端
5. 在相关 command 文件中引用新 skill

---

## 八、知识蒸馏循环

```
批量/人工校对 → audit.log + reports/ → /extract-rules 分析 → 人工确认 → 更新 knowledge/
                                                                            ↓
                                                                    下次翻译自动加载
```

---

## 九、配置

### `config.toml`（项目元信息，gitignore）

```toml
[project]
name = "pali-translab"
target_lang = "zh-Hans"

[wikipali]
# 端点与凭据由 wikipali 插件管理（~/.wikipali/credentials.json），此处不存 token
channel = "73c03e1a-f333-11f0-808a-438f0af4b9e9"   # 默认写入目标 channel
```

模板见 `config.orig.toml`。

---

## 十、本地产物目录

```
workspace/                        # 全部 gitignore
├── audit.log                     # 批处理台账（断点续传依据）
├── reports/{book}/
│   ├── {start}-{end}_review.md   # 审稿意见（按 chunk）
│   ├── {start}-{end}_final.md    # 总评（分数 / 信心 / 问题清单）
│   └── term_check_{范围}.md      # 术语报告
└── export/{章节路径}/
    └── {章节名}.md               # 按用户要求导出的译文副本
```

这里**没有 jsonl**——译文在 wikipali。
