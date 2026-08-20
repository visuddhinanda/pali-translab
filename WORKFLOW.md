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

要做**一整章（一部经）**时，用 `wikipali paras <book>:3 --body --json` 一次拿到
该书的章节边界与每段的 `cs_para`（Chaṭṭha Saṅgāyana 典藏段号，**跨书通用**），
**按 cs_para 判跨层归属**——不要拿 `wikipali related` 的段号当范围：related 是
段级对应，边界必然错位，实测有约一成的章会判到相邻章去。

没有 `cs_para` 的段（注释书独有的序论、结集史等）按章名跨层配对成独立作业，
并跑覆盖率自检确保一段不漏。

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

### harmonize 的规模分级：按 cs_para 预先规划

整章三层一次交给 LLM，小章没问题，大章必然撑爆上下文。实测本卷 133 个有效章，
三层合计巴利字符 **中位 9.8k、均值 23k、最大 379k**——差了近 40 倍：

| 三层合计巴利字符 | 章数 | 占比 |
|---|---|---|
| ≤ 5k | 34 | 26% |
| 5k–10k | 35 | 26% |
| 10k–20k | 30 | 23% |
| 20k–40k | 16 | 12% |
| 40k–80k | 9 | 7% |
| > 80k | 9 | 7% |

所以 **harmonize 之前先按 `cs_para` 算体量，再决定走哪条路**。体量在规划阶段就知道
（`wikipali paras` 的 `length` 字段直接给出巴利字符数），不必等失败了才降级。

**A. 小章（三层合计 ≤ 阈值）——整章三层一次做完**

现在的做法，不变。跨层对齐与全章统一在同一次调用里完成，效果最好。

**B. 大章——拆成横向 + 纵向两步**

```
第一步  横向（跨三层，按 cs_para 切）
        cs 6–7  { mūla 93:12-16 + 义注 103:210-240 + 复注 185:130-160 + 188:… }  → 一次调用
        cs 8–9  { mūla 93:17-22 + 义注 103:241-268 + 复注 185:161-190 + 188:… }  → 一次调用
        ⋯                     每个 chunk 自带三层，被解释词的对齐在这一步落实

第二步  纵向（每层各自通读，按章）
        a. 本章 mūla 整体 harmonize
        b. 本章义注整体 harmonize
        c. 本章复注整体 harmonize
        章本身还是太大就再按 cs_para 切成合适大小的 chunk
```

两步各管一件事，缺一不可：

- **横向**管**父子对齐**——义注的黑体被解释词必须与本文同一处逐字相同。这件事
  只有把三层放在一起才看得见，所以再大的章也不能省掉这一步，只能切小。
- **纵向**管**同层内的一致性**——同一术语在本章前后是否统一、语体是否一致、
  重复定型句是否同译。这件事需要的是**同层的长距离视野**，混进另外两层反而稀释。

顺序不能颠倒：先横向对齐，再纵向统一。反过来的话，纵向统一好的用词会被横向对齐
再改一遍，白做。

**为什么切分必须按 cs_para**

`cs_para` 是 Chaṭṭha Saṅgāyana 的典藏段号，**跨书通用**，是三层之间唯一的公共坐标。
本卷实测：注释层的 cs 值全部落在本文的 cs 集合里（103/185/188/189 独有的 cs 均为 0），
且 cs 随段号**单调不减**（四层各 0 次逆序）。所以「一个 cs 区间 → 该层的一段连续段号」
是精确可求的，横向 chunk 天然对齐，不会出现「本文切在这里、义注切在那里」。

相邻两章的 cs 区间总是重叠**恰好 1 个** cs（142 个接缝全是 1），按半开区间
`[cs_start, 下一章 cs_start)` 划分即可，共用的那个 cs 归前一章——与既有的
「归最早提到它的作业」规则一致。

没有 cs_para 的段落（注释层独有的序论、结集史、结语）**跟着前一个 cs 锚点走**，
归同一个 chunk；开头那一整块（如义注 103:3–201）没有前序锚点，自成作业，按章名配对。

**阈值（经验值，按失败率调）**

| 参数 | 初值 | 含义 |
|---|---|---|
| `--harmonize-direct-max` | 30,000 | 三层合计巴利字符 ≤ 此值 → 走 A（整章一次） |
| `--harmonize-cross-chars` | 12,000 | 走 B 时，每个横向 chunk 的三层合计上限 |
| `--harmonize-layer-chars` | 15,000 | 走 B 时，每个纵向（单层）chunk 的上限 |

按初值算，133 个有效章里 **111 章（83%）走 A，22 章走 B**；但那 22 章占了全书
巴利字符的 **65%**——章数上是少数，工作量上是大头，所以 B 这条路必须做对。
最大的 `Cūḷasīlaṃ`（379k）会切成约 32 个横向 chunk，外加三层各自的纵向 chunk。

这三个值**不要当常数**：`workspace/audit.log` 里记着每次 harmonize 的字符数与成败，
积累几轮之后统计「失败集中在多大体量」，把阈值下调到失败率可接受的位置。先用经验值
跑起来，再用数据收敛——不要凭空调参。

**怎么落地的**：`plan_jobs.py --project` 在规划阶段就把统稿单元排好写进 project 文件
（`harmonize.cross[]` 与 `harmonize.layer[]`，各带坐标与字符数），`pipeline_batch.sh`
阶段二读出来逐个跑，按 `audit.log` 断点续传。旧的「句数超过 `--harmonize-max 120`
就改为按层分批」只在**没有计划**时才走——那条路直接放弃跨层对齐、只做纵向，
而大章恰恰最需要对齐，是个静默的降级。

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
