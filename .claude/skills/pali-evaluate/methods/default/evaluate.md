---
resources:
  - pali
  - nissaya              # 缅文逐词注解，词级评估基准（如有）
  - prev_translation     # 最新 v(n).jsonl
knowledge: []
output:
  - tipitaka/{method}/jsonl/{book}/{para}/{para}_final.jsonl    # per-para
  - tipitaka/{method}/jsonl/{book}/reviews/{start}-{end}_final.md  # per-chunk
---

# Evaluate (最终评估)

## 目标
1. 读取 chunk 内所有最新版 v(n).jsonl，对译文中**有问题的最小片段**用 `<span>` 原地标注（见“标注方法”）
2. 按 para 输出 final.jsonl
3. 按 chunk 产出总评 md（总分 / 信心 / 问题清单）到 `reviews/{start}-{end}_final.md`

## 评估基准：缅文 nissaya
按 `(word_start, word_end)` 把 nissaya 单元对齐到每一句，**以 nissaya 为词级标准答案**评分（nissaya 缺失的段落降级为纯 pali 评估，并在理由中说明）。体例见 `references/nissaya_format.md`。

- **准确性打分**主要依据译文与 nissaya 的吻合度：词覆盖、格/句法角色（看缅文格助词）、歧义词的传统取义。
- 译文与 nissaya **冲突**且无更优依据时——降准确性分，并按“标注方法”给该片段套 span（多为 error 词义错误）。
- 译文偏离 nissaya 但**确有依据**（如别本、上下文）时——不扣分，但在理由中注明分歧。

## 标注方法

只对译文中**有问题的最小片段**，用如下 span 原地包裹（**不改动译文本身的文字与黑体等格式**，仅在外层套标签）：

```
<span class='evaluate-级别' title='级别emoji-问题类别：问题简述｜建议：修改建议'>有问题的译文片段</span>
```

**硬约束（违反会导致整行 JSON 解析失败、整句被丢弃）**：

- span 的属性**一律用单引号**：`class='...'`、`title='...'`。不要用双引号——因为 content 整体是 JSON 字符串、本身由双引号包裹，属性再用双引号极易因转义出错。
- title 等属性值内若要引用文字，使用中文全角引号「」或‘’。**严禁**出现 ASCII 双引号 `"` 或单引号 `'`。
- `class` = `evaluate-` + 级别英文名（如 `evaluate-error`）。
- `title` 格式固定：`级别emoji-问题类别：问题简述｜建议：修改建议`，分隔符为全角 `-`、`：`、`｜`。

译文中残留的 translate 阶段 `⚠️[候选?]` 标记须逐一处理：能定则采用并去标，仍存疑则转成对应级别的 span。final.jsonl 中**不应再出现** `⚠️[候选?]`。

**级别与 emoji**：

| 级别 | emoji | class |
|---|---|---|
| fatal | 🟥 | `evaluate-fatal` |
| error | 🟧 | `evaluate-error` |
| warning | 🟨 | `evaluate-warning` |
| suggestion | 🟦 | `evaluate-suggestion` |

**示例**：

```
礼敬彼<span class='evaluate-error' title='🟧-词义错误：「彼」指代不清且非现代汉语｜建议：删去或改为「那位」'>彼</span>世尊
```

## 问题分级

级别取自下表；`问题类别` 从对应级别的条目中择一填入 title。

**第一类 严重错误 fatal**（零容忍；增长普通读者邪见、降低普通读者对译文的评价）
1. 主谓（含非谓语动词）宾有一项判断错误
2. 句子意思违背基本教理原则

**第二类 错误 error**（专家有举必究；只要发现一定要改、只有巴利专家能发现）
1. 漏译（例：32**两**糖块的体积）
2. 错误多译
3. 错译（词义、修饰关系）
4. 导致误解的表达
5. 义理或用词与注释书不符
6. 代词指代错误

**第三类 待提升 warning**（出版社编辑视角）
1. 关键词语意不明确，或二意场合没有注释（稣息、转起）
2. 代词指代不明确
3. 不导致误解的汉语语病
4. 标点符号使用错误
5. 不该使用术语标记时使用了术语标记
6. 整句逻辑表达不规范

**第四类 可提升 suggestion**（有佛教背景的读者视角）
1. 语言表达不够流畅
2. 代词指代可能不够明确
3. 语言风格不统一
4. 该使用而没有使用术语标记
5. 不常用术语编写注释或者百科
6. 复杂的嵌套句整句语言逻辑理解困难（对读者不友好）

## final.jsonl 格式

与上一版相同，但 `zh` 中对有问题的片段套上 span 标注。例：

```json
{"id": "...", "pali": "Bhagavato ...", "zh": "礼敬彼<span class='evaluate-error' title='🟧-词义错误：「彼」非现代汉语｜建议：改为「那位」'>彼</span>世尊、阿罗汉、正等正觉者", "confidence": 95}
```

注意：例中 span 属性全用单引号，title 内引用一律用「」——保证整行是合法 JSON。

## final.md 格式

```markdown
# Evaluate — {book}/{start_para}-{end_para}

## 总分
- 准确性: X/100
- 风格符合度: X/100
- 一致性: X/100
- **综合**: X/100

## 信心指数
N / 100

## 理由
<分维度说明>

## 问题清单
按级别从高到低排列，与译文中的 span 一一对应。

### 🟥 fatal
- 句 <id>｜<问题类别>：<问题简述> → 建议：<修改建议>

### 🟧 error
- 句 <id>｜<问题类别>：<问题简述> → 建议：<修改建议>

### 🟨 warning
- ...

### 🟦 suggestion
- ...
```

无该级别问题时省略对应小节。

## 不要做

- 不要为了“看起来权威”虚标高分
- 不要套 span 时改动译文文字或黑体等内部格式——只在外层加标签
- span 属性不要用双引号，title 内不要出现 ASCII 引号 `"` `'`
- 问题清单必须与译文中的 span 一一对应（数量、级别相等）
