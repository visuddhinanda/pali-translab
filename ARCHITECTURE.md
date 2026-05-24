# Pali-TransLab 架构

> 三层分离：**Skill 层**（通用引擎）/ **MCP 层**（数据源，过渡期为 Python 脚本）/ **项目层**（用户定制）。
> 目标：skill 可发布到 skills 市场，被任意佛教研究者复用，项目层只承载个人/团队的定制。

---

## 一、三层职责

### 1. Skill 层 `.claude/skills/<name>/`

通用、可发布、零项目依赖。

```
.claude/skills/translate/
├── SKILL.md                    # 触发条件 + 主流程
├── methods/
│   └── default/                # 自带默认 method（项目可整文件覆盖）
│       ├── method.md
│       ├── translate.md
│       ├── review.md
│       ├── revise.md
│       └── evaluate.md
├── references/                 # 业务流强绑定的知识（不可被项目覆盖）
│   ├── nissaya_format.md       # 缅文 nissaya 6 类结构
│   ├── pali_basics.md
│   └── review_criteria.md
└── scripts/                    # 过渡期：HTTP 调 wikipali；未来由 MCP 替换
    ├── fetch_pali.py
    ├── fetch_nissaya.py
    └── fetch_dict.py
```

**原则**：skill 内一切都是"通用知识 + 通用流程"。任何与具体语料、具体研究者偏好相关的内容都不进 skill。

### 2. MCP 层（未来）

替换 skill 中的 `scripts/*.py`。接口对 skill 透明——SKILL.md 中调用方式从
`python scripts/fetch_pali.py --id X` 改为 MCP tool 调用，其他不变。

**过渡期**：scripts 直接走 HTTP 调 wikipali API。

### 3. 项目层（本仓库）

用户/团队的个性化数据与配置。

```
pali-translab/
├── config.toml                 # 项目元信息（语料范围、目标译语、wikipali endpoint…）
├── resources.toml              # 资源名 → 路径/接口 映射
├── methods/                    # 覆盖 skill 默认 method（可选）
│   └── my_method/
│       ├── method.md
│       └── translate.md        # 整文件覆盖 skill 同名默认文件
├── knowledge/                  # 用户知识库
│   ├── INDEX.md                # 知识文件索引（必需）
│   ├── style.md                # 语言风格（固定文件，skill 自动读取）
│   ├── terms.md                # 术语偏好（固定文件）
│   ├── pitfalls.md             # 用户积累的坑（固定文件）
│   ├── concepts/               # 自定义概念笔记（按 INDEX 加载）
│   └── grammar/                # 自定义语法笔记
├── translations/{method}/{book}/{para}_v{n}.jsonl
├── gold/{book}/{para}.jsonl
└── lessons/{book}/{para}.md
```

---

## 二、加载与覆盖规则

### Method 加载

1. skill 启动时，先看项目 `methods/<name>/<step>.md` 是否存在
2. 存在 → 使用项目版本（**整文件覆盖**，不做字段合并）
3. 不存在 → 回退到 `.claude/skills/<skill>/methods/default/<step>.md`

**项目模板**：每个项目 `methods/` 下提供一份完整模板（拷贝自 skill default），用户按需编辑。

### Knowledge 加载

1. **skill `references/`**：业务流强绑定，**总是加载**，项目不可覆盖
2. **项目 `knowledge/` 固定文件**：skill 按约定路径自动读取
   - `style.md` — 语言风格、术语策略、是否显示巴利原文等
   - `terms.md` — 术语偏好对照表
   - `pitfalls.md` — 个人积累的坑
3. **项目 `knowledge/INDEX.md`**：列出额外可加载的知识文件，method 步骤文档的 `knowledge:` frontmatter 按 INDEX 中的条目名引用

**追加而非覆盖**：项目 knowledge 追加到 skill references 之后，不替换。

### 资源加载

skill 中所有"取数据"的动作（取巴利原文、取 nissaya、查词典）：

- 通过 `resources.toml` 的资源名解析
- 解析结果可以是本地路径、HTTP endpoint、或未来的 MCP tool 名
- skill 不关心后端形态

---

## 三、固定文件契约

项目 `knowledge/` 下，以下文件名为**保留约定**，skill 会自动读取（如存在）：

| 文件 | 用途 | 是否必需 |
|---|---|---|
| `INDEX.md` | 列出所有可被 method 引用的知识文件 | 必需 |
| `style.md` | 语言风格、术语处理、是否显示原文 | 推荐 |
| `terms.md` | 术语偏好对照 | 可选 |
| `pitfalls.md` | 用户积累的坑 | 可选 |

其余文件（如 `concepts/<topic>.md`、`grammar/<topic>.md`）由用户自定，必须在 INDEX.md 中登记才能被 method 引用。

---

## 四、配置文件

### `config.toml`（项目元信息）

```toml
[project]
name = "pali-translab"
target_lang = "zh-Hans"

[corpus]
books = ["dn", "mn"]

[wikipali]
endpoint = "https://wikipali.org/api"
# 未来切 MCP 后此节作废
```

### `resources.toml`（资源映射）

```toml
# 过渡期：scripts 调 wikipali HTTP
pali       = "skill:translate/scripts/fetch_pali.py --id {book}/{para}"
nissaya    = "skill:translate/scripts/fetch_nissaya.py --id {book}/{para}"
lookup     = "skill:translate/scripts/fetch_dict.py --id {book}/{para}"

# 未来：切换到 MCP
# pali = "mcp:wikipali/get_pali"
```

skill 解析 `skill:` 前缀 → 调脚本；`mcp:` 前缀 → 调 MCP tool；普通路径 → 读本地文件。

---

## 五、迁移路径

1. **现在**：写第一个 skill（建议 translate），含 default method + scripts/fetch_*.py
2. **跑通端到端**：用 wikipali HTTP 取数据，产出 v1.jsonl
3. **沉淀 references/**：把 nissaya.md 等业务强绑定知识从项目 knowledge/ 搬进 skill references/
4. **开发 wikipali MCP**：scripts 接口冻结后照样迁移
5. **发布 skill**：项目层只剩 config + resources + knowledge + 产出物

---

## 六、与 WORKFLOW.md 的关系

- 本文档定义**结构与契约**（哪里放什么、如何加载）
- `WORKFLOW.md` 定义**流程**（translate→review→revise→evaluate 怎么跑）
- 两者互不重复，有冲突以本文档为准
