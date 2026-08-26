---
name: pali-encyclopedia
description: "Atomic skill: write a Chinese Wikipedia-style encyclopedia entry for a Pali term. Gathers its own evidence from the WikiPali corpus via `wikipali search` / `get`, and cites every claim with the Pali original plus a {{para}} reference template. Read-only against the corpus; writes markdown only."
---

# pali-encyclopedia

给一个巴利术语，检索 WikiPali 语料，产出**简体中文百科词条**（Markdown）。

**只读语料，不写 channel。** 当前只落地本地 markdown，缺省 `workspace/terms/<term>.md`。

> **TODO（等 WikiPali 百科 API 就绪）**
> 词条最终要写回 WikiPali 站点，本地 markdown 只是过渡形态。API 可用后补一步
> 发布：把成文 push 成词条，处理创建/更新（同名词条覆盖式更新）、
> `{{quality|…}}` 状态流转、以及 AI 模型身份署名（同 `wikipali:write` 的
> `ensure-model` / `grant` 那套）。届时 `--out` 降为调试用途，
> 并给这个 skill 加 `--publish` 开关。在那之前**不要**尝试用现有
> `wikipali write` 写词条——那个接口是写句子译文的，坐标语义完全不同。

## 依赖

需要 **wikipali 插件**（`wikipali` CLI）。`command -v wikipali` 为空时用
`${CLAUDE_PLUGIN_ROOT}/bin/wikipali`，并提醒用户重启会话。

## 调用方式

```
/pali-encyclopedia <term> [--category <类别>] [--limit N] [--tags <tags>] [--book <book>] [--out <file>] [--work <dir>]
```

- `<term>` — 巴利词根（走 `--lemma` 自动展开词形）或直接给词形；
  拼写变体一起给（`sāvatthī,sāvatthi`），合成一条词条
- `--category <类别>` — 限定义项与词条类型，如 `人名` / `地名` / `教理`。
  **给了就只写该义项**，其余义项的命中不进工作集。类型模板见
  `references/entry-types.md`
- `--limit N` — 工作集上限，默认 60 条命中
- `--tags` — 限定范围，如 `vinaya` 或 `vinaya,mūla;vinaya,aṭṭhakathā`
- `--book` — 限定单书（值取自 `wikipali dist`）
- `--out` — 输出文件路径，缺省 `workspace/terms/<term>.md`（相对当前工作目录，
  目录不存在就建；给 `-` 则直接打到对话里）
- `--work` — 中间产物目录，缺省 `${TMPDIR:-/tmp}/wikipali-encyclopedia/<term>/`

## 检索流程

**先建工作集，再动笔。** 不许凭记忆写任何一条论断。

1. **看分布** — `wikipali dist --lemma <term> --json --limit 30`
   知道该词集中在哪些书、三藏哪一部分。据此定 `--tags` / `--book`。

2. **取黑体命中（最高优先）** — `wikipali search --lemma <term> --bold --json --limit <N>`
   `--bold` 只要注释书标出的词条。这些就是义注/复注对该词的正式**定释**，
   是「词源与定义」段的主料。**黑体命中一条都不能丢。**

3. **取全量命中** — `wikipali search --lemma <term> --json --limit <N>`
   按 `rank` 降序取前 N 条，补充用例。

4. **取词典释义** — `wikipali word <term> --json --lang zh`
   仅供词源段参考，**不作为引用出处**（词典不是巴利文献）。

5. **取全句原文** — 搜索结果里 **没有** 完整正文，`highlight` 是被 `--width`
   截断的 HTML 片段，**禁止直接引用**。把工作集的坐标批量喂给：
   ```
   wikipali get <book>:<para> <book>:<para> … --json --limit 200
   ```
   一次可给多个坐标。取 `content` 字段，剥掉 `<span>` 标签后才是可引用的巴利原文。

   原文里混着两类**非正文标记**，引用时静默剔除、不加省略号：
   - 页码锚点，形如 `M0.402` / `V1.244` / `P0.24` / `T5.91`（紧贴词尾，易被误读进引文）
   - 版本夹注，形如 `( pārā.508-511)` / `( kaṅkhā. aṭṭha. paṭhamapārājikavaṇṇanā )`

   引号 `‘‘ … ’’` 与词间多余空格也一并规整。**但连声与长短音必须照抄**——
   `byākarotīti` 不能截成 `byākaroti`，`vītikkamasaṅkhātaṃ` 不能拆成两词。

6. **取书目元数据** — `wikipali books --json`（有本地缓存）

   ⚠ **一个 `book` 号可能装多部书**（如 book 98 依次是界论义注 / 人施设论义注 /
   论事义注 / 双论义注 / 发趣论义注；book 207 前半是波罗提木叉、1215 段起是疑惑度脱）。
   `books` 的每条记录是「某书在该 book 内的起始段」，所以**必须按段号落位**：

   ```python
   cand = [e for e in books if e['book']==bk and e['paragraph']<=para]
   title, abbr = cand[-1]['title'], cand[-1]['related_name']   # 取起始段最大且不超过 para 的
   ```

   直接拿 book 号取第一条会张冠李戴——实测 113 条工作集里有 9 条会认错书。

7. **落 manifest** — 把工作集写成 `<work>/manifest.json`，每项：
   ```json
   {"book":165,"paragraph":145,"bold":false,"rank":464158,
    "doc":"majjhimanikāyapāḷi","abbr":"MN","chapter":"6. Upālisuttaṃ",
    "path":["majjhimanikāyapāḷi","(MN)Majjhimapaṇṇāsapāḷi","1. Gahapativaggo","6. Upālisuttaṃ"],
    "pali":"…全句…",
    "link":"{{para|id=165-145|title=majjhimanikāyapāḷi 145|style=reference}}"}
   ```
   写完词条后**逐条核对 manifest**：每一项的 `link` 都必须在正文里出现过。

## 字段映射（务必照此，别照搬旧提示词）

`wikipali search --json` 返回 `{"count":N,"rows":[…]}`，每行字段：

| 需要的东西 | 来源 |
|---|---|
| 文献名 | `path[0].title` |
| 章节名 | `paliTitle`（＝ `path` 最末项的 `title`） |
| 章节路径 | `path[]` 各项 `title` 顺序拼接 |
| 巴利原文 | **不在 search 里**——用 `wikipali get <book>:<para>` 的 `content` |
| 引用链接 | 由 `book`/`paragraph` 拼 `{{para|id=<book>-<paragraph>|title=<path[0].title> <paragraph>|style=reference}}`——`title` 是站点显示文本，用**巴利书名 + 段号** |
| 参考文献缩写 | `wikipali books --json` 里同 `book` 的 `related_name` |

**链接模板原样输出**，不加 markdown 链接、不改大小写、不换字段顺序、不加空格。

## 中文名处理

语料只给巴利书名/章节名，没有中文名。规则：

- 有公认汉译名的用汉译名（如 `majjhimanikāyapāḷi` →《中部》，
  `visuddhimagga` →《清净道论》），见 `references/book-names.md`
- 表里没有的，**自行意译**，并在**首次出现**时括注罗马转写：
  《疑惑度脱新注（Vimativinodanī-ṭīkā）》
- 章节名同理，首次出现时括注巴利原名
- 拿不准就保留巴利原名，**不要编造汉名**

## 词条类型

见 `references/entry-types.md`。**动笔前先定类型**：

| 类型 | 触发 | 结构重点 |
|---|---|---|
| 义项分析型 | 默认 | 按义项分节，不按文献顺序 |
| 人名 | `--category 人名` | 必须有「相关经文」节：**每经一个 `###` 小标题（中译经名）+ 简介 + 引用模板，不用表格**；**同名多人要拆成「消歧页 + 每位一个分立词条」**，不是合成一篇 |
| 地名 | `--category 地名` | 必须有「与佛陀及僧团的关系」一节，且要有实质内容 |

人名与地名条目要额外做**按经文聚合**：把 search 命中按 `(book, paliTitle)`
分组统计，据此列相关经文；`path[]` 提供「丛书 › 部 › 品 › 经」的层级。

**「相关经文」一律用小标题铺开，不要压成表格**——表格里塞不下经文内容，
读者看到的只有经名和一句标签。

## 写作与校验的省力做法

正文里先写**简写** `{{p|<book>-<paragraph>}}`，成文后用脚本按 manifest
统一展开成完整模板。`title` 由 manifest 生成，不可能写错；顺带能拦住
**指向工作集之外的坐标**——那种坐标常来自章节聚合表，没取过全文，
描述多半是猜的。

## 引用规范

见 `references/citation.md`。核心：

**任何论断句都必须带巴利原文引用，只有中文转述的一律不合格。**

标准格式：

```
《文献中文名》在《章节中文名》中指出："*巴利文原文*"（中文翻译及必要说明）。{{para|id=<book>-<para>|title=<巴利书名> <para>|style=reference}}
```

- 巴利原文用引号 + *斜体*
- 引用动词可用：指出、解释、说明、定义、描述、强调、阐述、论述
- 同一观点多处出处，链接模板连排：`…。{{para|id=A|…}}{{para|id=B|…}}`

## 词条结构

```
{{quality|pending}}
<紧接正文，中间不留空行>

<简短定义段落，无标题>

## 目录

## 词源与定义

## <按文献实际内容分出的主题小节，可多个>

## 参考文献

## 相关条目

# 分类标签
```

- 开头 `{{quality|pending}}` 后**直接跟内容，不留空行**
- 关键术语首次出现给「中文（pali）」对照
- 巴利文一律罗马转写
- 直接输出正文，不加词条大标题

参考文献格式：`[序号] 文献缩写, 具体章节, 标题, 段落编号`

## 分类标签

见 `references/taxonomy.md`。从该分类体系中选，**不得自创**。
通常不超过 3 个标签，格式：

```
{{category|一级分类}} {{category|二级分类}} {{category|标签}}
```

一、二级分类去掉编号（写「人物」不写「七、人物」）。只输出标签，不作解释。

## 输出前自检

逐条过，任一不过就改完再输出：

1. 每个论断句是否都是 `[中文陈述] + "*巴利文*" + （译文） + {{para|…}}`？
2. 正文里有没有残留 `link`、`引用链接`、`[1]` 之类占位符？**必须全部替换成真实模板。**
3. manifest 里每一条的 `link` 是否都在正文出现过？漏的补进合适章节；
   实在放不进去的，在报告末尾列出**未采用条目及原因**，不要装作全用了。
4. 引用的巴利原文是否来自 `wikipali get`，而不是 `highlight` 片段？
   **用程序核对，别靠眼睛**：把每条引文和它所指段落都归一化
   （剔页码标记与版本夹注、转小写、非字母折成空格），逐段（按省略号切）
   检查引文是否为原文子串。实测一次就抓出 6 处长短音/连声/复合词切分错误。
5. `{{quality|pending}}` 后面是否紧跟内容、无空行？
6. 分类标签是否全部出自 `references/taxonomy.md`？
7. 给了 `--category` 时，有没有混进其他义项？被剔除的命中是否在末尾记了账？
8. 人名条目：「相关经文」小节在不在，每节有没有引用模板？
   同名多人是不是拆成了消歧页 + 分立词条（而不是挤在一篇里）？工作集分完了没？
9. 地名条目：「与佛陀及僧团的关系」一节是不是有实质内容，而不只是地理沿革？

## 输出落地

- 缺省写 `workspace/terms/<term>.md`，`<term>` 用罗马转写、小写、变音符号保留
- 同名文件已存在时**覆盖**，覆盖前先看一眼旧文件内容
- 写完报告文件路径与词条条数统计（引用了多少条 / 工作集共多少条）

## 诚实性

- 工作集因 `--limit` 截断时，在输出末尾注明「本词条基于前 N / 共 M 条命中撰写」
- 检索为零命中时如实说明，不要编词条
- 保持学术中立客观，不作教派判定
