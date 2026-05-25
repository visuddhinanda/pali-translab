# Pali-TransLab 翻译工作流设计

> 本文档定义流水线与流程。**结构与契约（skill/MCP/项目三层分离、加载规则、固定文件）见 `ARCHITECTURE.md`。**
> 前期数据准备（chunk、lookup、术语表等）另见后续文档。

---

## 一、总体理念

- **配置文档驱动**：每个翻译方案（method）是一组 Markdown 说明书，声明每步用什么资源、怎么做。调整方案只改 md，不改 skill。
- **Skill 通用化**：skill 可发布到 skills 市场，跨项目复用。Skill 自带 `methods/default/` 默认方案与 `references/` 业务知识，项目层只放定制内容。
- **数据源外置**：巴利原文、nissaya、词典通过 skill 的 `scripts/` 调 wikipali API（过渡期），未来切 MCP。skill 不依赖项目本地语料文件。
- **知识库分层**：业务流强绑定知识（如 nissaya 格式）放 skill `references/`；用户个性化知识（风格、术语偏好、pitfalls）放项目 `knowledge/`。
- **人在回路**：知识更新由 LLM 提议、人工审批后才落盘。

详细分层规则见 `ARCHITECTURE.md`。

---

## 二、翻译流水线

```
translate → review → revise → review → revise → evaluate
   v1       v1.md     v2      v2.md     v3      final
```

固定两轮修正。

### 步骤定义

| 步骤 | 输入 | 输出 | 是否改译文 |
|---|---|---|---|
| translate | 资源（pali / nissaya / lookup / …） | `{para}_v1.jsonl` | — |
| review | v(n) jsonl + 资源 | `{para}_v{n}.md`（审稿意见） | 否（非侵入） |
| revise | v(n) jsonl + v(n).md | `{para}_v(n+1).jsonl` | 是 |
| evaluate | v3 jsonl + 资源 | `{para}_final.jsonl` + `{para}_final.md` | 是（内联标注疑问） |

### 触发方式

- 手动单步：`/translate`、`/review`、`/revise`、`/evaluate`
- 部分流程：指定起止步骤
- 自动全流程：`/pipeline {method} {book}/{para}`

### evaluate 输出规范

**译文内联疑问标记**：

```json
{"id": "94-1-1-6", "zh": "礼敬彼⚠️[世尊?]阿罗汉……","confidence":95}
```

`⚠️[候选词?]` 提示后续人工处理。

**总评 md**：

- 总分（分维度 + 总分）
- 信心指数（0–100）
- 理由（分项说明）
- 疑问清单（与译文中 ⚠️ 标记一一对应）

---

## 三、目录结构

完整三层结构（skill/项目）见 `ARCHITECTURE.md`。**项目层**关键目录：

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

tipitaka/{method}/
    ├── jsonl/{book}/
    │   ├── {para}_v1.jsonl
    │   ├── {para}_v1.md
    │   ├── ...
    │   ├── {para}_final.jsonl
    │   └── {para}_final.md
    ├── mdbook/                    # mdbook 源码
    ├── html/                      # mdbook build 输出
    └── epub/                      # epub 输出

gold/{book}/{para}.jsonl           # 人工校对定稿
lessons/{book}/{para}.md           # 反哺学习：原始差异分析
```

业务流强绑定的通用知识（pali_basics / nissaya 格式 / review 标准等）位于 skill `references/`，**不在项目内**。

---

## 四、Method 配置文档结构

每个 method 含 5 份文件：`method.md` + 4 个步骤文档。

### method.md（方案总览）

```markdown
---
steps: [translate, review, revise, review, revise, evaluate]
---

# method_nissaya
基于巴利原文 + 缅文 nissaya 逐词解析的翻译方案。
```

`steps` 控制 `/pipeline` 的执行序列与迭代次数。

### 步骤文档（translate.md / review.md / revise.md / evaluate.md）

```markdown
---
resources:
  - pali
  - nissaya
  - lookup
knowledge:
  # 固定文件由 skill 自动加载，无需在此列出
  # 此处只列 INDEX.md 中登记的自定义条目
  - concepts/nissaya       # 项目个性化补充
  - grammar/absolutive
output: tipitaka/{method}/jsonl/{book}/{para}_v{n}.jsonl
---

# 翻译指南
（自然语言：工作方法、术语规则、风格要求……）
```

**自动加载**（无需声明）：
- skill `references/` 全部内容
- 项目 `knowledge/style.md` / `terms.md` / `pitfalls.md`（如存在）

**特殊资源名**（由 skill 自动解析）：
- `prev_translation` → v(n-1) 的 jsonl（revise 用）
- `prev_review` → v(n-1) 的 md（revise 用）
- `atthakatha`、`tika` → 按 `corpus.json` 查映射

---

## 五、资源映射

`resources.toml`（项目专属，与 skill 解耦）。支持三种后端：

```toml
# 过渡期：skill 自带 python 脚本调 wikipali HTTP API
pali       = "skill:translate/scripts/fetch_pali.py --id {book}/{para}"
nissaya    = "skill:translate/scripts/fetch_nissaya.py --id {book}/{para}"
lookup     = "skill:translate/scripts/fetch_dict.py --id {book}/{para}"

# 未来：切到 MCP
# pali = "mcp:wikipali/get_pali"

# 也支持本地文件（如有离线语料）
# pali = "corpus/pali/{book}/{para}.jsonl"
```

skill 按前缀分发：`skill:` 调脚本、`mcp:` 调 MCP tool、普通路径读本地文件。

---

## 六、知识库

### 加载方式

三类知识合并注入 system prompt：

1. **skill `references/`**（业务流强绑定，总是加载，不可覆盖）
2. **项目固定文件**（`knowledge/style.md` / `terms.md` / `pitfalls.md`，如存在则自动加载）
3. **项目自定义条目**（须登记在 `knowledge/INDEX.md`，由 method 步骤文档 frontmatter `knowledge:` 字段按条目名引用）

### 与 memory 的区别

- `knowledge/`：项目领域知识，进 repo，团队共享，进每次翻译上下文
- `memory/`：用户/协作偏好，本地，影响 Claude 工作方式

### 即时记录

`/learn` skill：在使用中发现错误理解时即时追加知识。

```
/learn concepts/nissaya 缅文 nissaya 中的 "ti" 标记表示引文结束，不要译出
/learn --new pitfalls/sandhi 描述……
```

行为：找到对应文件追加（无则新建），带日期戳。

---

## 七、反哺学习工作流

人工校对几个月后，从 `gold/` 与 AI 终稿对比中提炼知识。

### 流水线

```
/distill → /consolidate → (人工审阅) → /apply
```

### /distill {book}/{para}

逐句 diff `tipitaka/{method}/jsonl/{book}/{para}_final.jsonl` 与 `gold/{book}/{para}.jsonl`，对每处差异分析：

- **类别**：术语 / 语法句型 / 固定搭配 / 省略还原 / 语体风格 / 名相歧义
- **原文片段**
- **AI 译法 → 人工译法**
- **原因推断**
- **建议归档去向**

输出 `lessons/{book}/{para}.md`（增量，已存在则跳过，`--force` 重跑）。

### /consolidate [--scope concepts|grammar|terminology|...]

批量读 `lessons/**/*.md`，跨案例聚类，产出修改建议清单：

```markdown
## 建议新增 knowledge/grammar/absolutive_ctva.md
依据：3 处案例（dn/1#94-1-1-6, dn/2#..., mn/5#...）
内容草稿：……

## 建议修改 knowledge/concepts/nissaya.md
依据：……
diff：……
```

输出到 `lessons/_proposals/{date}.md`。

### /apply {proposal-file}

经人工审阅确认后，按提案落盘到 `knowledge/` 或 `methods/`。

### 设计原则

- **不自动写知识库**：distill 取证，consolidate 起诉，apply 判决，人工是法官
- **可追溯**：每条知识更新带案例来源（书+段+id）
- **语法手册自然生长**：`knowledge/grammar/` 条目即事实上的语法书

---

## 八、Skill 分包

打包成**两个独立 skill 包**，各自可发布、可单独安装。

### 包 1：`translate`（翻译伞形 skill）

单一入口 `/translate <subcommand> [args]`，子命令在 SKILL.md 内分派：

| 子命令 | 职责 |
|---|---|
| `/translate run` | 执行翻译步骤（生成 v1） |
| `/translate review` | 执行审稿步骤（生成 v(n).md） |
| `/translate revise` | 执行修正步骤（生成 v(n+1)） |
| `/translate evaluate` | 执行最终评估（生成 final） |
| `/translate pipeline` | 按 method.md 的 steps 串联执行 |
| `/translate learn` | 即时追加知识条目（轻量，反哺前的零散记录） |

**理由**：review/revise/evaluate 不能脱离 translate 单独存在（共享 method 配置、resources、prompt 上下文），强行拆分会导致 references / scripts / methods 重复或跨目录引用——后者在 skills 市场发布时不可行。

### 包 2：`pali-learn`（反哺学习 skill，独立发布）

| 子命令 | 职责 |
|---|---|
| `/pali-learn distill` | 对比 gold 与 AI 终稿，提取差异 → `lessons/` |
| `/pali-learn consolidate` | 跨案例聚类，生成知识更新提案 |
| `/pali-learn apply` | 经人工审阅后落盘提案到 `knowledge/` 或 `methods/` |

**理由**：反哺工作流在时间上与翻译解耦（数月校对后才用），用户群也不同（高级研究者），独立发布更清晰。两包通过项目目录约定（`gold/` / `lessons/` / `knowledge/`）协作，无代码耦合。

### 共同约束

两个 skill 均仅依赖 `methods/` + `resources.toml` + `knowledge/` + 标准目录约定，可跨翻译项目复用，可发布到 skills 市场。

---

## 九、待办（前期数据准备另议）

- [ ] `resources.toml` 起草
- [ ] 知识分类法 `learning-taxonomy.md`（distill 用的类别清单）
- [ ] `gold/` 目录命名最终确认（gold / human / reviewed）
- [ ] 信心指数尺度（数值 0–100 vs 低/中/高，建议数值）确认
