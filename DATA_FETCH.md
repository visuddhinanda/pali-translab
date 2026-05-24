# 数据获取设计

> 列出 skill `scripts/` 在过渡期需要从 wikipali 获取的全部资源。
> 未来切 MCP 时，本文档定义的资源清单和 IO 契约保持不变。

## 待用户后续提供（按优先级）

- [ ] **资源 2** 缅文 nissaya channel UUID（一个或多个候选）
- [ ] **资源 3** 词典 / lemma / 词形分析 endpoint
- [ ] **资源 4** 术语表 `view` 取值、`lang` 列表、按词查询模式
- [ ] **资源 5/6** atthakatha / tika channel UUID + **正典 ↔ 注释 book 映射表**
- [ ] **资源 8** 其他译本 channel UUID 列表（按语种/译者）
- [ ] **资源 7c** `pcd_book_id` 含义、非 chapter 段调 palitext detail 的行为
- [ ] `status` 字段语义（10/30）

收齐前 translate skill 先以 pali + nissaya（资源 2 UUID 待填）为最小集开工。

---

## 一、基础配置

### Base URL

写入项目 `config.toml`，skill 默认值可放 SKILL.md frontmatter。

```toml
[wikipali]
base_url = "https://www.wikipali.cc"   # 项目可覆盖
# 已知备用: https://next.wikipali.org （示例 API 所在）
```

**TODO（用户填写）**：
- 正式生产 base 是 `www.wikipali.cc`(中国大陆) 和 `www.wikipali.org`(中国大陆以外地区) 两者提供服务相同
- API 路径前缀是 `/api/v2/` 固定

### 认证

**TODO**：
- 只读不需要 API key / token。 写入需要。以后会允许用户将生成的译文上传wikipali
- 若需要：放 env var 名（如 `WIKIPALI_TOKEN`），脚本通过 `Authorization` header 发送
- 没有速率限制

[wikipali]
url = 'https://www.wikipali.cc'
user = 'www'
token = 'change-me'

### 返回 envelope

已确认（来自术语表 API）：

```json
{ "ok": true, "data": { "rows": [ ... ] } }
```

**TODO**：所有 endpoint 都用这个 envelope。资源是列表有rows，是对象，data=<对象>

---

## 二、资源清单

### 通用 endpoint：`/api/v2/sentence`

**巴利原文、参考译文、nissaya、注释书** 全部走同一 endpoint，由 `channels` 参数区分资源类型。

**示例 URL**：
```
https://next.wikipali.org/api/v2/sentence
  ?view=paragraph
  &book=98
  &para=1524
  &channels=7ac4d13b-a43d-4409-91b5-5f2a82b916b3
  &format=text
```

**参数**：

| 参数 | 含义 | 示例 |
|---|---|---|
| `view` | 视图模式 | `paragraph`（按段返回） |
| `book` | 书 id（整数，单值） | `98` |
| `para` | 段号（整数，**逗号分隔可多值**） | `1524` 或 `1524,1525,1526` |
| `channels` | 资源通道 UUID（**逗号分隔可多值**） | `7ac4d13b-...,abcd-...` |
| `format` | 返回内容格式 | `text` / `markdown` / `html` |

**返回排序**：服务端按 `book_id` → `paragraph` → `word_start` 排序（客户端可直接消费，无需再排）。

**过滤条件**：仅返回 `ver > 1` 的句子（已通过初版的内容）。

**TODO（用户填写）**：
- [x] `view` 还有什么其他取值？（chapter, 但是翻译没用。一个章节太大，会超出上下文）
- [ ] `book` 整数 id 与人类可读的简称（dn / mn / ...）的对应表在哪？是否有 endpoint 可查（见资源 7）？

**返回 envelope**：

```json
{ "ok": true, "data": { "count": N, "rows": [...] }, "message": "..." }
```

**行字段**（已确认）：

| 字段 | 类型 | 示例 | 用途 |
|---|---|---|---|
| `id` | string (UUID) | `9f7131cd-...` | 句子唯一 id |
| `content` | string | `"866.现在是所谓的狱卒论。"` | 句子内容（按 channel 而不同：pali / 译文 / nissaya） |
| `content_type` | string | `markdown` | 内容格式 |
| `html` | string | `<p>...</p>` | 渲染后 HTML（可忽略） |
| `book` | int | `98` | 书 id |
| `paragraph` | int | `1524` | 段号 |
| `word_start` | int | `2` | 段内词起始位置（**跨通道对齐 key**） |
| `word_end` | int | `10` | 段内词结束位置（**跨通道对齐 key**） |
| `editor` | object | `{id, nickName, userName, ...}` | 编辑者元信息（可忽略） |
| `fork_at` | null \| timestamp | `null` | 派生版本时间（可忽略） |
| `updated_at` | string (ISO 8601) | `2025-07-21T08:05:56Z` | 更新时间（缓存判断用） |
| `channel` | object | `{id, name, type, lang, ...}` | 通道元信息（资源类型说明） |
| `studio` | object | `{id, nickName, studioName, ...}` | 工作室元信息（可忽略） |

**跨通道对齐**（关键发现）：不同 channel 的句子通过 `(book, paragraph, word_start, word_end)` **四元组对齐**——即同一段巴利原文的某个 word 区间，对应译文/nissaya 的同一区间。这是 skill 内部做句对齐的依据。

---

### 通用：Channel 目录 endpoint

获取所有可用 channel 的清单（pali 原文、各语种译本、注释、nissaya 等）。

**示例 URL**：
- `https://next.wikipali.org/api/v2/channel?view=system` — 列出所有系统通道
- `https://next.wikipali.org/api/v2/channel?view=paragraphs&book_id=98&para=1524` — 列出**指定段**有内容的通道（按需查询）

**参数**：
- `view`：
  - `system` — 系统通道全表
  - `community` — 社区通道全表
  - `paragraphs` — 按段查询，需配合 `book_id` + `para`（**用于发现某段有哪些资源可用**，如查 nissaya 是否存在）
- `book_id` / `para`：仅 `view=paragraphs` 时使用

**返回 envelope**：`{ok, data:{rows:[...], count:N}, message}`

**行字段**：

| 字段 | 类型 | 示例 | 说明 |
|---|---|---|---|
| `uid` | string (UUID) | `00b577c0-...` | channel 唯一 id，传给 `/sentence` 的 `channels` 参数 |
| `name` | string | `_System_Pali_VRI_` | 通道名（`_System_*` 系统、`_community_*` 社区） |
| `summary` | string \| null | `null` | 描述 |
| `type` | enum | `original` / `translation` / `commentary` / `wbw` / `nissaya` | 资源类型（`wbw` = 逐词标注；`nissaya` = 缅文逐词释义） |
| `lang` | enum | `pali` / `my` / `zh-Hans` / `zh-Hant` / `en` | 语种 |
| `owner_uid` | string | `6e12f8ea-...` | 所有者 |
| `status` | int | `10` / `30` | 状态码（TODO 含义） |
| `is_system` | bool | `true` | 是否系统通道 |
| `created_at` / `updated_at` | ISO 8601 | — | 时间戳 |
| `studio` | object | `{...}` | 工作室元信息 |

**用法**：skill 启动时拉一次 channel 清单缓存到 `.cache/wikipali/channels.json`，按 `(type, lang)` 索引；用户在 `resources.toml` 中按 channel `name`（人类可读）声明资源，skill 内部转成 `uid`。

**TODO**：
- [ ] `status` 字段含义？10=启用、30=废弃？
- [ ] `view=community` 返回哪些？需要单独获取吗？

---

### 资源 1：巴利原文（pali）

- **endpoint**：`/api/v2/sentence`
- **type/lang 过滤**：`type=original`, `lang=pali`
- **默认 channel**：`_System_Pali_VRI_`
  - **UUID**：`00b577c0-13b9-11ee-a05a-b7307efd9ee6`
- **TODO**：是否还有其他巴利底本通道（如 PTS、缅版、泰版）？

### 资源 2：缅文 nissaya

- **endpoint**：`/api/v2/sentence`
- **type/lang 过滤**：`type=nissaya`（`lang` TODO，应为 `my`）
- **发现可用 channel**：调 `/channel?view=paragraphs&book_id={book}&para={para}`，筛 `type=nissaya` 的条目
- **channel UUID 选择策略**：
  - [ ] 同一段可能有多个 nissaya channel（不同来源/学派），选哪个？是否需在 `resources.toml` 中固定一个，还是用户每次指定？
  - [ ] 默认 channel：**TODO 给出推荐 UUID**
- **与巴利对齐**：通过 `(book, paragraph, word_start, word_end)` 四元组（见通用 endpoint）
- **结构标记保留情况**（`**词**` / `ဝါ=` / `(...)` / `[...]` / `` ``...`` ``）：TODO 用 `format=text` 取一段实际数据看 `content` 是否原样保留

**附注**：`wbw` 和 `nissaya` 类型的区别？wbw 是结构化的词级标注（json 字段化？），nissaya 是缅文释义段？请确认。

### 资源 3：词典查询（lookup / dict）

**用途**：translate 步骤的词形分析、词义参考。

**调用粒度**：两种可能模式——
- **A. 按词查询**：传一个词形 → 返回词根/词性/释义
- **B. 按段批量预处理**：传段 id → 返回该段所有词的分析结果（lookup 预处理缓存）

**我需要知道的**：
- [ ] **采用 A 还是 B？或两者都有**？
- [ ] **endpoint(s)**：
- [ ] **参数**：词形 / 段 id / 目标释义语种？
- [ ] **返回字段**：
  - 词形（surface form）
  - 词根 / lemma
  - 词性、变位信息
  - 释义（中文？多语种？）
  - 同义词 / 异读？
- [ ] **示例 URL + 返回 JSON**

### 资源 4：术语表（terms / vocabulary）

**已知**：`https://next.wikipali.org/api/v2/term-vocabulary?view=community&lang=zh-Hans`

返回 envelope：`{ok, data:{rows:[...]}}`

**行字段**（已确认）：

| 字段 | 类型 | 示例 | 说明 |
|---|---|---|---|
| `guid` | string (UUID) | `09e1c92c-05f1-47a6-8d18-a8e93e9f7de9` | 条目唯一 id |
| `word` | string | `manussajātika` | 巴利词形 |
| `tag` | string \| null | `null` / `vinaya` / `语法缩写` / `:quote:` | 分类标签 |
| `meaning` | string | `人类` | 主译义（按 `lang` 参数） |
| `other_meaning` | string \| null | `null` | 备选译义 |

**用途**：作为权威译名对照，注入 system prompt 或预查询。

**仍需确认**：
- [ ] `view` 取值范围？（community / official / personal / ...?）项目应该用哪个？
- [ ] `lang` 支持哪些？（zh-Hans / zh-Hant / en / ...?）
- [ ] 是否支持**按词查询**单条？（如 `?word=bhagavā`）还是只能拉全表？
- [ ] 全表多大？需要分页吗？（500+ 行还是更多？）
- [ ] 多久更新？缓存可放多久？

### 资源 5：注释书 atthakatha（可选，按 method 需要）

- **endpoint**：`/api/v2/sentence`（推测同通用 endpoint，靠 channel 区分）
- **channel UUID**：**TODO 用户填写**
- **与正典段的映射**：注释书的 `(book, para)` 与正典 `(book, para)` 如何对应？
  - [ ] 注释书有自己独立的 book id 吗？需要一张映射表（正典 book → 对应 atthakatha book）？
  - [ ] 还是同 book 不同 channel？

### 资源 6：复注 tika（可选）

- **endpoint**：`/api/v2/sentence`
- **channel UUID**：**TODO 用户填写**
- **映射方式**：同资源 5

### 资源 7：目录 / 语料结构（corpus index）

**用途**：让 skill 知道有哪些书、每本书包含哪些 work（chunk 拆块、范围解析的依据）。

**结论**：列表很小且基本不变，**静态打包进 translate skill**：
- 位置：`.claude/skills/translate/references/books.json`（已落盘，217 books / 276 works）
- 格式：`[{"book": int, "start_para": int, "title": str}, ...]`
- 同一 book 可含多 work，按 `start_para` 切分（如 book 98 = 5 个 aṭṭhakathā，分别从 para 2/173/474/1623/1880 开始）
- 无需 API，无需 `--refresh`，新增书时手工追加并发新版 skill

### 资源 7b：章节目录 TOC（用于输出目录层级）

**endpoint**：`/api/v2/palitext?view=book-toc&book={book}&para={start_para}`

`para` 传 `books.json` 中该 work 的 `start_para`，返回该 work 内所有章节条目。

**返回 envelope**：`{ok, data:{rows:[...], count:N}, message}`

**行字段**：

| 字段 | 类型 | 示例 | 说明 |
|---|---|---|---|
| `book` | int | `210` | 书 id |
| `paragraph` | int | `210` / `1658` | 章节起始段号 |
| `toc` | string | `"1. Cīvaravaggo"` / `"Bhikkhunīvibhaṅgavaṇṇanā"` | 章节标题（巴利） |
| `level` | int (1–7) | `1` / `2` / `4` | 层级深度（1 = 顶层） |

**用法**：
- skill 输出译文时，按 TOC 生成 `translations/{method}/{book}/{toc-slug}/{para}_v1.jsonl` 的目录层级
- 用户可读性更好，避免一堆裸 para 号
- 缓存到本地（`.cache/wikipali/toc/{book}-{start_para}.json`）或干脆按需拉

**TODO**：
- [ ] `paragraph=0` 的特殊条目（如示例中 `level=1`）含义？整个 work 的根条目？
- [ ] `toc` 是否多语言？如需中文目录，是否有 `lang` 参数？

### 资源 7c：段落 / 章节元信息

**endpoint**：`/api/v2/palitext/{book}-{paragraph}`（path 参数，不是 query）

**返回 envelope**：`{ok, data: <object>, message}`（data 是单对象，**非** rows 数组）

**用途**：
1. **遍历章节内所有段落**：拿到章节起始段（来自 7b TOC），`chapter_len` 告知章节段数 → 循环取 `paragraph .. paragraph + chapter_len - 1`
2. **章节导航**：`next_chapter` / `prev_chapter` 跳转
3. **面包屑路径**：`path` 字段（祖先链）

**关键字段**：

| 字段 | 类型 | 示例 | 用途 |
|---|---|---|---|
| `book` / `paragraph` | int | `210` / `1659` | 自身坐标 |
| `level` | int | `3` | TOC 层级 |
| `class` | string | `chapter` | 元素类型（章/段/...） |
| `toc` / `title` | string | `"1. Pārājikakaṇḍaṃ"` | 标题 |
| `text` / `html` | string | — | 标题渲染 |
| `chapter_len` | int | `22` | **章节段数**（遍历用） |
| `chapter_strlen` | int | `4954` | 章节字符数（估算上下文用） |
| `next_chapter` / `prev_chapter` | int | `1660` / `1648` | 同级导航 |
| `parent` | int | `1658` | 父节点 para |
| `path` | array | `[{book, paragraph, title, level}, ...]` | 面包屑 |
| `uid` | UUID | `cab633af-...` | 段落唯一 id |
| `title_en` | string | `"1. parajikakandam"` | 英文转写标题 |
| `pcd_book_id` | int | `268` | TODO：与 `book` 的关系？另一套书号体系？ |

**典型使用**：
```
# 翻译一整个 work
work = books.json 中 (book=98, start_para=1623, title="Yamakappakaraṇa-aṭṭhakathā")
toc  = GET /palitext?view=book-toc&book=98&para=1623   # 该 work 的章节列表
for chapter in toc:
    meta = GET /palitext/98-{chapter.paragraph}        # 取 chapter_len
    for p in range(chapter.paragraph, chapter.paragraph + meta.chapter_len):
        sentences = GET /sentence?book=98&para=p&channels=...
```

**TODO**：
- [ ] `pcd_book_id` 字段的含义？示例 `268` 与 `book=210` 不一致，是 PCD（缅版？）另一套编号？
- [ ] `chapter_len` 是否在所有 level 的段落上都有意义？还是只在 `class=chapter` 的段落上？非章节段（如普通正文段）调此 endpoint 时返回什么？

### 资源 8：其他译本（可选）

DESIGN.md 提到 burmese / thai / 中文已有译本作为参考。

- **endpoint**：`/api/v2/sentence`（同通用 endpoint）
- **不同语种 / 译本 = 不同 channel UUID**
- **channel UUID 列表**：**TODO 用户填写**（建议给出一张 "语种/译本 → channel UUID" 对照表）
- [ ] wikipali 上有哪些语种译本？（burmese / thai / 中文元亨寺 / 中文庄春江 / 英译 / ...？）

---

## 三、脚本设计（一旦上面填完）

### 文件位置

```
.claude/skills/<skill>/scripts/
├── _client.py          # 共享: HTTP 客户端、缓存、错误处理
├── fetch_pali.py
├── fetch_nissaya.py
├── fetch_dict.py
├── fetch_terms.py
└── fetch_corpus_index.py
```

`_client.py` 统一处理：base_url、auth header、envelope 解包、本地缓存、重试。

### 通用 CLI 约定

```
python fetch_pali.py --book dn --para 1 [--no-cache] [--lang zh-Hans]
```

- 成功：stdout 输出 jsonl，每行一个对象，退出码 0
- 失败：stderr 输出错误信息，非零退出码
- `--no-cache` / `--refresh` 强制重新拉取

### 输出契约（建议）

每行 jsonl：
```json
{
  "id": "<resource-specific id>",
  "...": "<resource-specific fields>",
  "_source": "wikipali",
  "_fetched_at": "2026-05-24T12:34:56Z"
}
```

下划线前缀字段为元信息，便于追溯与缓存失效判断。

### 缓存策略（建议）

- 位置：项目 `.cache/wikipali/<endpoint-path>/<param-hash>.json`
- key：endpoint + sorted(params) 的 sha1
- 失效：默认永久缓存（API 数据相对稳定），靠 `--refresh` 手动失效
- **TODO 用户决定**：是否对术语表设较短 TTL（社区更新频繁）？

### 配置读取顺序

1. 命令行参数（最高优先级）
2. 项目 `config.toml [wikipali]` 节
3. skill `SKILL.md` 默认值（最低）

---

## 四、待你填写后我会做的事

1. 根据填写结果，定稿每个脚本的 CLI 参数与输出字段
2. 写 `_client.py`（HTTP + 缓存 + envelope 解包）
3. 写各 `fetch_*.py`（薄壳，调 `_client`）
4. 在第一个 skill（建议 translate）的 `SKILL.md` 中演示如何调用这些脚本
5. 更新 `ARCHITECTURE.md` / `WORKFLOW.md` 的 `resources.toml` 示例为真实参数

---

## 五、开放问题（你来决定方向）

- [ ] **范围**：第一版只做 DN 经藏 + nissaya，还是覆盖全部 pitaka？
- [ ] **离线模式**：是否支持完全离线（先 dump 整本书到 `.cache/`，之后无网络也能跑）？
- [ ] **多语种 fallback**：术语表 zh-Hans 查不到时，是否 fallback 到 en 再到原词？
- [ ] **错误处理基调**：网络失败时 skill 是中断流程，还是降级（如缺 nissaya 就跑纯 pali method）？
