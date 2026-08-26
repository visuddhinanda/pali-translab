# 工具链架构规划

> 2026-08-26 · 讨论纪要与重构建议
> 涉及三个仓：`pali-translab`、`wikipali-plugins`、`agent-poc/mcp`

## 0. 结论摘要

当前三个仓的能力边界是历史形成的，不是设计出来的：`wikipali-plugins` 把
**能力**（4.4k 行 Python CLI）、**方法**（2 个 skill）、**分发**（plugin 壳）焊在一起；
`pali-translab` 既是产品（9 个可发布 skill + 7 个 command）又是工作目录
（个人 knowledge / methods / workspace）；`agent-poc/mcp` 已经把能力层用 TS
重写出来（35 个 `wikipali_*` 工具，无状态 HTTP，写端拆 `_preview`/`_commit`）。

重构的枢纽就是 **MCP 层已经写好了**——把能力抽出去之后，其余归属自然落位。

目标形态：**三仓 · 两 MCP · 两 plugin**

| 仓 | 归谁 | 装什么 |
|---|---|---|
| `wikipali-mcp`（现 `agent-poc/mcp`） | 你 | TS core + MCP server + CLI 前端 |
| `pali-workbench`（新，可从 `wikipali-plugins` 演化） | 你 | 全部 skill + command + marketplace |
| `pali-translab` | 用户 fork | 个人 knowledge / methods / workspace + 批量调度脚本 |

---

## 1. 五类工具的边界

| | 它是什么 | 判据 |
|---|---|---|
| **MCP** | **能力**——做得到什么。跨宿主唯一可移植的接口层 | 需要网络 / 文件 / 计算，**不需要 LLM 判断** |
| **Skill** | **方法**——该怎么做。渐进披露的 markdown + 附件 | 需要 LLM 判断，且判断规则写得成文 |
| **Command** | **入口**——用户怎么发起。编排若干 skill 的宏 | 一句话触发一条流水线；宿主专有 |
| **本地脚本** | **调度器**——谁来反复调 agent。批量 / 断点 / 并发 / 报表 | 在 agent 之外，把 agent 当子进程用 |
| **Plugin** | **打包分发单元**。skills + commands + hooks + `mcpServers` 声明 | 只是壳，不产生新能力 |

一条判据解决绝大多数归属问题：

> **这一步如果换成一个确定性函数，结果会不会变差？**
> 不会 → MCP 或脚本；会 → skill。

推论：**脚本调 agent 的留在项目里，agent 调的上收 MCP。**

---

## 2. 归属表

### → MCP

**`wikipali-mcp`**（对 WikiPali 的全部访问）

- 现有 35 个 `wikipali_*` 工具全留，它就是唯一数据契约
- **从 `pali-translab` 上收**：`scripts/layers.py`（books + cs_para 算三层坐标）、
  `scripts/_wp.py`、`wp_pull.py`、`wp_push.py`。纯确定性计算与 IO，
  留在项目里等于让每个宿主重造一遍；`src/wikipali/books.ts`、`coords.ts` 已经在那儿了
- **新增**：`wikipali_layers`（给坐标返回三层对应）、`wikipali_export`（channel → markdown/YAML）。
  导出是纯变换，不该是 skill

**`translab-mcp`**（项目上下文，见 §5）

- `skill_get` / `context_get` / `context_list` / `audit_append`

### → Skill（零项目依赖，可发布）

- 原子 skill 全留：translate / review / revise / harmonize / evaluate / footnote / term-check
- `pali-export` **降级**：导出逻辑进 MCP，skill 只剩"章节切分与文件命名"的判断，
  可能薄到不值得单独存在——考虑并进 `/export` command
- `pali-encyclopedia` 与将来的 **paper / monograph** 共享同一骨架：
  取证 → 核对 → 引用 → 成文。抽 **`pali-cite`** 做底座（引用规范、`{{para}}` 模板、
  书名表、证据充分性判据），三个 authoring skill 各自只写"体裁"部分。
  **不要让 paper / monograph 各抄一份 `citation.md`**
- `wikipali-plugins/skills/{research,write}` 保留，但改为围绕 **MCP 工具名**书写，
  不再教 CLI 用法

### → Command

- 现有 7 个都合适（它们是编排，不是能力）
- 新增 `/paper`、`/monograph`、`/encyclopedia`
- **跨宿主化**：command 是 Claude Code 专有。要让 Desktop / online 也有一键入口，
  唯一途径是 **MCP Prompts 原语**——把 `full-pipeline`、`translate-review`
  同时实现成 MCP prompt

### → 本地脚本（留在 `pali-translab`）

- `plan_jobs.py` / `project.py` / `run_daemon.py` / `watchdog.py` /
  `pipeline_batch.sh` / `task_table.py` / `html_report.py` —— 全留，它们是**外层调度器**
- `build_epub.py` 留（成品打包，与 WikiPali 无关）

### → Plugin

- **`wikipali`**：内容换成 `.mcp.json`（声明 MCP server）+ research/write 两个 skill + references。
  `lib/*.py` 那 4.4k 行退居二线
- **`pali-workbench`**（新）：9 个 `pali-*` skill + 7 个 command
- 两个 plugin 放**同一个 marketplace**（沿用 `wikipali-plugins/.claude-plugin/marketplace.json`），
  用户 `marketplace add` 一次，装两个

---

## 3. 平台能力矩阵

| 宿主 | Skills | Commands | Plugins | MCP | 本地脚本 |
|---|---|---|---|---|---|
| Claude Code (CLI) | ✅ | ✅ | ✅ | ✅ stdio + HTTP | ✅ |
| Claude Desktop | ✅ | ❌ | ❌（另一套 extension 打包） | ✅ stdio + 远程 | ❌ |
| claude.ai online chat | ✅ | ❌ | ❌ | ⚠️ **仅远程 HTTP，需公网 + 正规鉴权** | ❌ |
| Agent SDK | ✅ | ✅ | ✅ | ✅ | ✅ |
| LangGraph / 自建后端 | ❌ 无原生机制 | ❌ | ❌ | ✅ **唯一通路** | ✅（在自己代码里） |

> 宿主支持度会变，以各自当前文档为准。

三条结论：

1. **MCP 是唯一五处全通的东西。** 想在所有场景都可用的能力，必须在 MCP 里。
2. **Skill 在 4/5 处可用，LangGraph 没有原生 skill 机制。** → 决策 1。
3. **Command 只在 Claude Code / SDK 有。** 跨宿主靠 MCP Prompts 顶替。

---

## 4. 已定决策

### 决策 1 · skill 经 MCP 分发 ✅ 采纳

`translab-mcp` 提供 `skill_get(name)` / `skill_list()`，把 SKILL.md 正文当**数据**返回，
让 LangGraph 或任何自建 agent 自己拉进 prompt。

意义：方法层不再锁死在 Anthropic 系宿主里。同一套翻译规矩，Claude Code 里靠原生
skill 机制加载，LangGraph 里靠工具调用加载，**内容是同一份文件**。

注意事项：

- 返回的是**原文**，不做摘要——skill 的渐进披露靠 `references/` 分文件，
  所以 `skill_get` 要支持 `skill_get("pali-translate", "references/nissaya_format")`
- 非 Claude 宿主没有自动触发机制，得由调用方决定何时拉。
  建议 `skill_list()` 的返回带上 `description`（就是 frontmatter 里那句），
  让对方的 router 能判断
- **只读**。任何宿主都不能经 MCP 改 skill

### 决策 2 · 拆仓 ✅ 采纳

```
pali-workbench/          你维护，用户「安装」不「fork」
  .claude-plugin/
  skills/pali-*/         SKILL.md + methods/default/ + references/
  commands/*.md

pali-translab/           模板仓，用户 fork 一份当自己的工作台
  knowledge/             个人术语、规则、坑、概念笔记
  methods/<name>/        覆盖 skill 的 methods/default/
  scripts/               批量调度
  workspace/             reports / audit.log / export（gitignore）
  docs/
```

**关键：升级路径与个人数据完全不相交。** 用户改 `knowledge/terms.md`，
永远不会和你的 skill 更新冲突——因为那是两个分发渠道，不是一个 git 历史。

这条边界现在是靠 `CLAUDE.md` 里一句硬约束（"不要把项目特定内容写进 skill"）
**手工维持**的；拆仓之后由目录结构保证。

---

## 5. 决策 3 · 项目知识层要不要 MCP 化

### 先拆问题：知识层不是一种东西，是三种

| 类别 | 现在在哪 | 性质 | 该去哪 |
|---|---|---|---|
| **散文规则** `style.md` `pitfalls.md` `translation-rules.md` `methods/` | 项目 git | 低频改、要人读、要 review、有版本意义 | **留 git 文件** |
| **结构化术语表** `term-glossary.jsonl` | 项目 git | 高频增量、跨项目共享、有权威版本、**并发写** | **上 WikiPali 服务端** |
| **运行台账** `audit.log` `reports/` | 本地，gitignore | 只写不读、机器生成、体量大 | **留本地** |

把三者当一件事处理，是当前设计里唯一真正别扭的地方。

### 术语表：这一条最值得改

WikiPali **已经有术语表 API**（CLI 的 `terms` / `my_terms`，MCP 的 `wikipali_terms` /
`wikipali_term_add` / `wikipali_term_edit`）。项目里再维护一份 `term-glossary.jsonl`：

- 两个人同时翻译，各自新增术语 → jsonl 行级冲突，git merge 要人工处理
- 换个项目（写论文那个仓）就拿不到，除非复制一份 → 立刻开始漂移
- 术语表是**研究成果**，本来就该发布出去，而不是烂在某人的 fork 里

**建议**：`term-glossary.jsonl` 降级为**本地覆盖层**（只放"本项目临时不同意权威译名"的少数条目），
权威表走 WikiPali。`pali-term-check` 查两处，本地优先并**在报告里标出偏离**。

### 散文规则：不要"MCP 化"，要"MCP 可读"

**利**（全 MCP 化）：online chat 与 LangGraph 也能拿到项目知识；一处修改处处生效。

**弊**：

- 失去 git —— diff、blame、PR review、回滚。翻译规矩的演化史本身是有价值的研究记录
- 用户失去直接编辑能力。研究者改 `style.md` 是拿编辑器改文本，不是调 API
- 引入服务依赖：MCP server 挂了就翻译不了
- 出现"服务器那份和我本地那份不一样"的可能

**业内做法**是不二选一，而是 **配置即代码 + 运行时 loader**：真相源在 git，
一个只读适配器把它暴露成运行时可查的接口。LSP（配置文件在项目里，
language server 读它并提供查询）、GitOps、eslint/tsconfig 全是这个形状。

**建议**：`translab-mcp` 做成 **project-context server**，启动时 `--project <path>`
指向一个 translab 工作台，暴露：

```
context_list()              列出可用条目（读 knowledge/INDEX.md）
context_get(name)           返回某条知识的原文
skill_get(name, sub?)       决策 1，同一个 server 一起给
audit_append(record)        台账追加（唯一的写口）
```

三条硬性约束：

1. **文件是唯一真相源，server 无状态只读**
2. **除 `audit_append` 外不提供任何写回**——不能经 MCP 改 `style.md`，
   否则立刻出现两个真相源
3. 不给每类知识建一个工具（`terms_lookup` / `rules_list` / `pitfalls_get` …）。
   一个通用 `context_get` + `INDEX.md` 驱动，才不会每加一类知识就改 server

online chat 场景下，用户在自己服务器上跑一个指向其项目的 `translab-mcp` 即可。

---

## 6. 决策 4 · CLI 的归宿

### 四个选项

| | 方案 | 评价 |
|---|---|---|
| A | Python CLI 与 TS MCP **双实现并存**（现状） | ❌ 注定漂移 |
| B | CLI 改成 **MCP 协议客户端**（spawn server + JSON-RPC） | ⚠️ 单一真相源，但有握手开销 |
| C | **废弃 CLI**，只留 MCP | ❌ 不可行 |
| D | **MCP 是薄壳**，内部调 Python lib | ⚠️ 方向对，但 TS 已写完，回退成本高 |

**A 的代价**：两份读写逻辑。4.4k 行 Python + 一套 TS。WikiPali API 还在演进
（`www` 稳定 / `next` 最新），每次变更改两处，漏一处就是静默不一致。
单人维护的项目里，这是最容易崩的一种结构。

**C 不可行**：脚本层（`plan_jobs.py`、`pipeline_batch.sh`）需要一个能 subprocess
调、能进管道的东西；MCP 是有状态的 JSON-RPC 会话协议，不适合 shell。
而且人类在终端手工核对坐标时，需要 CLI。

**B 的问题**：每次 CLI 调用都要 spawn 进程 + `initialize` + `tools/list` 握手。
`plan_jobs.py` 里成千次调用，这个延迟不可忽略。而且 CLI 的人类友好输出
（表格、摘要、`--json`）是 MCP tool 的 text 返回不提供的，那部分格式化逻辑
无论如何要留在 CLI。

### 业内最佳实践：core library + multiple frontends

这个模式有名字。`docker` / `kubectl` / `gh` 全是一个 core，CLI 和 API server
是两个前端。GitHub 官方的 MCP server 独立于 `gh` CLI 用 Go 重写——但他们
**容忍双实现是因为有团队**。单人维护不该抄这一点。

### 建议：B 的变体——共享 core，但不走协议

```
wikipali-mcp/  (npm 包)
  src/wikipali/          ← 唯一真相源：client / api / coords / books / markup
  src/server.ts          ← 前端 1：MCP server（bin: wikipali-mcp）
  src/cli.ts             ← 前端 2：CLI，直接 import core（bin: wikipali）
```

**CLI 与 MCP server 共享 core，但互不调用。** 这样：

- 单一真相源 —— API 变更只改 `src/wikipali/`
- 没有 JSON-RPC 握手开销 —— CLI 就是个普通 node 程序
- 人类友好输出留在 `cli.ts`，不污染 MCP tool 的返回

**代价**：脚本层需要 node。你已经有了（MCP 就是 TS）。`scripts/*.py` 现在用
标准库 subprocess 调 `wikipali`，换成调 node bin **完全无感**。

**迁移策略**：Python CLI 不要立刻删。设一个过渡期，用 `release-check.sh`
做**双实现一致性测试**——同样输入喂两边，diff 输出。等 TS CLI 覆盖全部子命令
且 diff 干净，再 archive Python 版。

---

## 7. 凭据与多租户（跨场景的真正卡点）

当前设计——客户端持 `userToken` + `modelToken`，经 HTTP 头传入，server 不落盘——
对**单用户本机**（Claude Code / Desktop，token 在 `~/.wikipali/credentials.json`）
是完美的。换到**多用户服务端**就断了：

- LangGraph 后端服务 N 个终端用户，浏览器里的 chat 没有 `~/.wikipali/credentials.json`
- 必须由后端**代持每个用户的 userToken**，按会话查表注入 header。
  这引入了现在明确回避的东西：token store、加密、轮换、撤销
- `ensure_model` 签发的 modelToken 决定 `editor_uid`。多租户下是
  "每人一个模型身份"还是"平台一个模型身份 + 另记 human operator"？
  **这是产品决策，不是技术决策**，直接影响 WikiPali 侧的审计语义。
  建议 API 增 `on_behalf_of` 字段，比给每个人建模型干净

**claude.ai online chat 直连 MCP** 是另一条路，卡点不同：custom connector 走 OAuth，
不是自定义 header。要让它写入，`wikipali-mcp` 大概率得实现 OAuth 授权码流
（用 WikiPali 账号登录并授权）。工作量不小，但做完之后
Desktop / online / 任意第三方宿主全部打通，且比让用户手工粘贴 token 安全得多。
**排进路线图，但不是第一优先。**

**另一个多租户才暴露的问题**：`_preview`/`_commit` 拆分依赖**人在回路里确认**。
无人值守的 agent 会直接连着调两个。要么 MCP 侧对 `_commit` 加配额 / 白名单 channel，
要么由 WikiPali API 侧管——**不能只靠工具拆分**。

---

## 8. 迁移分期

按依赖排序，不按工作量：

**第一期 · 立住单一真相源**（其余全部依赖它）

1. `agent-poc/mcp` 独立成 `wikipali-mcp` 仓
2. 加 `src/cli.ts` 前端，与 MCP server 共享 core
3. `release-check.sh` 改成双实现 diff 测试
4. Python CLI 进入冻结（只修 bug，不加功能）

**第二期 · 能力上收**

5. `layers.py` / `_wp.py` / `wp_pull` / `wp_push` 的逻辑迁进 core，
   新增 `wikipali_layers`、`wikipali_export`
6. `pali-export` skill 降级；skill 与 command 里的 CLI 调用改写成 MCP 工具名

**第三期 · 拆仓**

7. 建 `pali-workbench`，迁 9 skill + 7 command，进现有 marketplace
8. `pali-translab` 瘦身成模板仓，写 fork + install 的上手文档

**第四期 · 跨宿主**

9. `translab-mcp`（`skill_get` / `context_get` / `audit_append`）
10. MCP Prompts 暴露 `full-pipeline` 等编排
11. 术语表迁往 WikiPali 服务端，本地表降级为覆盖层

**第五期 · 多租户**（仅当真要做 online chat / 公共服务时）

12. OAuth 授权码流
13. `on_behalf_of` 审计语义
14. `_commit` 的配额与白名单

**第六期 · 新体裁**

15. 抽 `pali-cite` 底座，重构 `pali-encyclopedia`
16. 新增 paper / monograph skill + command

---

## 9. 明确不做的事

- **不做**"CLI 调 MCP server"的协议桥接 —— 握手开销换不来任何东西，共享 core 更直接
- **不做**知识层的全 MCP 化 —— git 文件仍是真相源，MCP 只是只读适配器
- **不给**每类知识建专用工具 —— 一个 `context_get` + `INDEX.md` 驱动
- **不删** Python CLI，直到双实现 diff 测试干净
- **不让**任何宿主经 MCP 写回 skill 或知识文件（`audit_append` 除外）
