# Pali-TransLab 翻译工作流设计

> 本文档定义流水线与流程。**结构与契约（四层分离、加载规则、数据流）见 `ARCHITECTURE.md`。**

---

## 一、总体理念

- **配置文档驱动**：每个翻译方案（method）是一组 Markdown 说明书，声明每步用什么资源、怎么做。调整方案只改 md，不改 skill。
- **Skill 通用化**：skill 可发布到 skills 市场，跨项目复用。Skill 自带 `methods/default/` 默认方案与 `references/` 业务知识，项目层只放定制内容。
- **数据源与数据宿都是 wikipali**：读原文、写译文都经 wikipali 插件的 CLI。skill 不依赖项目本地语料文件，**也不产出本地译文文件**。
- **知识库分层**：业务流强绑定知识（如 nissaya 格式）放 skill `references/`；用户个性化知识（风格、术语偏好、pitfalls）放项目 `knowledge/`。
- **人在回路**：知识更新由 LLM 提议、人工审批后才落盘。

详细分层规则见 `ARCHITECTURE.md`。

---

## 二、翻译流水线

```
    ── 按 chunk ──            ── 按章 ──      ── 按 chunk ──
translate → review → revise → harmonize   →   evaluate
写 channel   出报告   覆盖 channel  覆盖 channel      出报告
                              ↑ 最后一个改译文的步骤   ↑ 验收，不改译文
```

固定一轮修正，整章统稿收口，最后评估验收。**每一步都从 channel 读回上一步的结果**——
channel 就是流水线的状态。**改译文的是 translate / revise / harmonize**；review 与
evaluate 非侵入，只出报告。

**evaluate 为什么在最后**：它给的是验收结论。放在 harmonize 之前，评的是还要再改一轮的
半成品，分数与问题清单都会失真——统稿改掉的问题会留在报告里，统稿新引入的问题反而没人评。

### 步骤定义

| 步骤 | 粒度 | 输入 | 输出 | 是否改译文 |
|---|---|---|---|---|
| translate | chunk | **只有 pali** | channel 译文 | 新写 |
| review | chunk | channel 译文 + pali + **义注** + **nissaya** | `reports/{book}/{start}-{end}_review.md` | 否（非侵入） |
| revise | chunk | channel 译文 + 义注/nissaya + review md | channel 译文（覆盖） | 是 |
| harmonize | **整章** | 整章 channel 译文 + pali | channel 译文（覆盖） | 是（统一 + 修正，不重译） |
| evaluate | chunk | channel 译文 + pali + 义注 + nissaya | `reports/{book}/{start}-{end}_final.md` | 否（非侵入，**最后一步**） |

### 整章范围要用目录求，不能用 related

要做**一整章（一部经）**时，各层的起止**用该层书自己的 `wikipali toc` 求**，
不要拿 `wikipali related` 的段号当范围——related 是段级对应，边界必然错位：
注释章的首段往往注的是上一章的本文，其被解释词在本章里根本找不到。

完整规程与实例见 `.claude/skills/pali-translate/SKILL.md`「定位整章在各层的完整起止」。

### 资源分工：义注与 nissaya 从 review 才介入

**translate 只看巴利原文**，独立译出一版。义注（aṭṭhakathā）与缅文 nissaya 留给
review / revise / evaluate 作对照标准：

- **义注定释义**——词句该作何解、术语指什么，以义注为准；译文与义注相悖就是错
- **nissaya 定词法**——格、数、主宾属关系、隐含成分，看缅文格助词
- 两者冲突**以义注为准**，并在报告里写明分歧

翻译时就照着它们译，等于被检查者与检查标准同源——译错的地方复核也发现不了，
复核就成了走过场。拿不准的地方由 translate 压低 `confidence`，等 review 来判。
缺哪个资源就用剩下的，在报告开头注明缺了什么；**不要拿相邻段落或别的译本凑**。

### 为什么按 chunk 提交

逐段孤立处理看不见跨段问题：同一个词前一段译 A 后一段译 B，语体忽紧忽松——
单段视野里都不算错。所以一次把连续若干段（累加到 ≥5000 巴利字符或 12 段截断）
交给同一次调用，review 专门有一项查跨段一致性。

chunk 仍解决不了跨 chunk 的漂移，所以有 **harmonize 按整章再统一一遍**——它同时负责
修掉整章视野才暴露的问题（指代接不上、长引语引号断裂、平行段落一处对一处错）。
统稿之后才轮到 evaluate 验收。

**没有版本号**。channel 里任一坐标只有当前一版；跑到哪一步由 `workspace/audit.log` 记录。
需要留档对照时，在改之前用 `/export` 导出 markdown 快照。

### 触发方式

- 手动单步：`/pali-translate`、`/pali-review`、`/pali-revise`、`/pali-evaluate`、`/harmonize`
- 组合流程：`/translate`、`/translate-review`、`/full-pipeline`
- 批量：`./scripts/pipeline_batch.sh <book> <start> <end> --channel <uid> --nissaya --atthakatha`
  （`--steps` 选步骤，`--chunk-chars` / `--max-paras` 调 chunk 大小）

### evaluate 输出规范

**流水线最后一步**，非侵入：不改译文、不写 channel、不在译文里插任何标记。唯一产物是
`workspace/reports/{book}/{start}-{end}_final.md`：

- 总分（分维度 + 总分）
- 信心指数（0–100）
- 理由（分项说明；nissaya 缺失、与 nissaya 的分歧都在这里交代）
- 问题清单：每条给出**句 id** + **原样摘出的问题片段**，按级别（🟥 fatal / 🟧 error /
  🟨 warning / 🟦 suggestion）从高到低排列

级别定义与问题分级表见 `.claude/skills/pali-evaluate/methods/default/evaluate.md`。
报告是验收结论——要照着改就回头跑 revise 或 harmonize，然后重新评；不要在 evaluate 里改。

---

## 三、目录结构

完整结构见 `ARCHITECTURE.md`。**项目层**关键目录：

```
methods/                           # 可选：覆盖 skill 默认 method（整文件覆盖）
└── my_method/
    ├── method.md
    └── translate.md ...

knowledge/                         # 用户知识库
├── INDEX.md                       # 自定义知识文件索引（必需）
├── style.md                       # 固定文件：语言风格、术语策略、原文显示
├── terms.md                       # 固定文件：术语偏好（可选）
├── pitfalls.md                    # 固定文件：个人积累的坑（可选）
├── concepts/                      # 自定义概念笔记（登记到 INDEX）
└── grammar/                       # 自定义语法笔记（登记到 INDEX）

workspace/                         # 全部 gitignore，只有过程记录与导出副本
├── audit.log
├── reports/{book}/{start}-{end}_review.md · {start}-{end}_final.md · term_check_*.md
└── export/{章节路径}/{章节名}.md
```

译文本身在 wikipali channel，不在这里。

业务流强绑定的通用知识（nissaya 格式 / review 标准等）位于 skill `references/`，**不在项目内**。

---

## 四、Method 配置文档结构

每个 method 含 `method.md` + 各步骤文档。

### method.md（方案总览）

```markdown
---
steps: [translate, review, revise, harmonize, evaluate]
---

# method_nissaya
基于巴利原文 + 缅文 nissaya 逐词解析的翻译方案。
```

`steps` 控制完整流程的执行序列。

### 步骤文档（translate.md / review.md / revise.md / evaluate.md）

```markdown
---
resources:
  - pali
  - nissaya
knowledge:
  # 固定文件由 skill 自动加载，无需在此列出
  # 此处只列 INDEX.md 中登记的自定义条目
  - concepts/nissaya
  - grammar/absolutive
output: wikipali:{channel}
---

# 翻译指南
（自然语言：工作方法、术语规则、风格要求……）
```

**自动加载**（无需声明）：
- skill `references/` 全部内容
- 项目 `knowledge/style.md` / `terms.md` / `pitfalls.md`（如存在）

**资源名**（由 skill 解析为 wikipali CLI 调用）：

| 资源名 | 取法 |
|---|---|
| `pali` | `wikipali get <book>:<para> --json` |
| `nissaya` | `wikipali versions` 里 `type=nissaya` 的 channel → `get --channel <uid>`（**translate 不声明此资源**） |
| `atthakatha` / `tika` | `wikipali related <book>:<para> --json` 按 tags 找层次 → `get <义注坐标>`（**translate 不声明**） |
| `current_translation` | `wikipali get <book>:<para> --json --channel <目标 channel>` |
| `review` | 本地 `workspace/reports/{book}/{start}-{end}_review.md` |

`output` 写 `wikipali:{channel}` 表示写回 channel；写路径表示落本地文件（仅报告与导出）。

---

## 五、资源缺失时的降级

某段没有声明的资源（最常见是 nissaya）时：

- **降级执行**，channel 不变
- 在本次回复 / 报告里注明实际用了哪些资源
- **不要拿相邻段落或别的译本凑**——如实报告「无」

---

## 六、知识库

### 加载方式

三类知识合并注入提示词：

1. **skill `references/`**（业务流强绑定，总是加载，不可覆盖）
2. **项目固定文件**（`knowledge/style.md` / `terms.md` / `pitfalls.md`，如存在则自动加载）
3. **项目自定义条目**（须登记在 `knowledge/INDEX.md`，由 method 步骤文档 frontmatter `knowledge:` 字段按条目名引用）

### 与 memory 的区别

- `knowledge/`：项目领域知识，进 repo，团队共享，进每次翻译上下文
- `memory/`：用户/协作偏好，本地，影响 Claude 工作方式

---

## 七、反哺学习工作流

人工校对一段时间后，从人工定稿与 AI 译文的差异中提炼知识。

### 数据来源

人工校对直接在 wikipali 上改，或改在另一个 channel。所以「对比」是**两个 channel 的同坐标对比**：

```bash
wikipali get <book>:<para> --json --channel <AI channel>
wikipali get <book>:<para> --json --channel <人工定稿 channel>
```

### 流水线

```
/distill → /consolidate → (人工审阅) → /apply
```

### /distill <book>:<para>

逐句 diff AI channel 与人工定稿 channel，对每处差异分析：

- **类别**：术语 / 语法句型 / 固定搭配 / 省略还原 / 语体风格 / 名相歧义
- **原文片段**
- **AI 译法 → 人工译法**
- **原因推断**
- **建议归档去向**

输出 `workspace/lessons/{book}/{para}.md`（增量，已存在则跳过，`--force` 重跑）。

### /consolidate [--scope concepts|grammar|terminology|...]

批量读 `workspace/lessons/**/*.md`，跨案例聚类，产出修改建议清单：

```markdown
## 建议新增 knowledge/grammar/absolutive_ctva.md
依据：3 处案例（216:35, 216:41, 217:3）
内容草稿：……

## 建议修改 knowledge/concepts/nissaya.md
依据：……
diff：……
```

输出到 `workspace/lessons/_proposals/{date}.md`。

### /apply {proposal-file}

经人工审阅确认后，按提案落盘到 `knowledge/` 或 `methods/`。

### 设计原则

- **不自动写知识库**：distill 取证，consolidate 起诉，apply 判决，人工是法官
- **可追溯**：每条知识更新带案例来源（`book:para` + 句 id）
- **语法手册自然生长**：`knowledge/grammar/` 条目即事实上的语法书

> 这三个命令**尚未实现**，此处是设计。

---

## 八、待办

- [ ] `/distill` `/consolidate` `/apply` 实现
- [ ] 知识分类法 `learning-taxonomy.md`（distill 用的类别清单）
- [ ] 人工定稿 channel 的命名约定
