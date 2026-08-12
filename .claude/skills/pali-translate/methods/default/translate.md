---
resources:
  - pali            # 本层的巴利原文。**不取 nissaya**——理由见下
  - parent_text     # 有父层时：父层的原文 + 已定稿译文（被解释词对照，非翻译拐杖）
knowledge: []        # 仅加载固定文件 + skill references
output: wikipali:{channel}          # 译文写进 channel，不落本地文件
---

# Translate (初稿)

## 目标
基于 pali 原文，按项目 `knowledge/style.md` 声明的风格，逐句产出初稿，写入目标 channel。

## 被解释词与父层逐字同译（硬约束）

翻义注或复注时会给一份**父层对照**（义注的父层是本文，复注的父层是义注）。

原文里的 `**词**` 是黑体，在注释层就是**被解释词**——它是从父层原样引出来的。
它的译法必须与父层译文里同一处**逐字相同**，一个字都不能改。不一致，读者就看不出
这条注在注哪个词，随文注唯一的线索就断了。译文里要保留 `**…**` 标记。

父层没提到的词，才由你自己定译法。父层对照只管被解释词与术语口径，
**不替你翻译本层**——义注解释什么、怎么解释，仍要从本层的巴利原文译出。

## 为什么不给 nissaya

nissaya 是 review / evaluate 阶段的**独立词级基准**。翻译时就照着它译，等于让被检查者
和检查标准同源——译错的地方 review 也发现不了，复核就成了走过场。

所以：**translate 只看巴利原文**，先独立译出一版；nissaya 留到 review 再拿出来逐词核对。
拿不准的地方压低 `confidence`，等 review 用 nissaya 来判。

## 工作方法

### 1. 组 Chunk

从起始 para 开始，逐段拉取巴利原文，累加字符数。当 buffer ≥ 5000 巴利字符时截断为一个 chunk。

```
for para in range(start_para, ...):
    text = wikipali get <book>:<para>
    buffer += text
    if len(buffer) >= 5000:
        → 翻译当前 chunk
        → 清空 buffer，开始下一个 chunk
```

### 2. 取资源

对 chunk 内每段，**只取巴利原文**：`wikipali get <book>:<para> --json`

不要去调 `wikipali versions` 找 nissaya，也不要读同坐标的其他译本——本步骤的输入就是
巴利原文本身。

### 3. 翻译整个 Chunk

将 chunk 内所有段落的巴利原文一次性提交翻译：
- 严格按 `knowledge/style.md` 中"语体 / 术语策略 / 原文显示"约定
- 术语命中 `knowledge/terms.md` → 直接采用；命中 wikipali 术语表 → 次优采用
- 拿不准时给出最好的一个译法并**调低该句 `confidence`**——存疑由 review / evaluate 的报告承担
- chunk 内术语保持一致

### 4. 写入

按段提交，每段的句数必须与该段原文句数相等：

```json
{"id": "<book>-<para>-<word_start>-<word_end>", "zh": "...", "confidence": 0-100}
```

- `id` 取自取回的原文，**不能编造坐标**
- 提交给 `wikipali write - --channel <ch>`（执行层封装：`scripts/wp_push.py`）
- 写完独立读回核对，条数不符要如实报告，不要说"已全部写入"

## 不要做

- **不要去取 nissaya 或别的译本**——translate 是独立翻译，不是照抄复核基准
- 不要补足省略的主语（除非歧义）
- **不要在译文里留任何工作标记**（`⚠️[候选?]`、问号、待定、TODO 之类）——
  写进 channel 的是给读者看的译文，不是草稿。不确定就压低 `confidence`，
  由 review / evaluate 的报告去说
- 不要留空、不要跳过——每句都要给出最好的一个译法
- 不要修改 pali 原文（即使发现疑似 OCR 错误，记入审稿意见而非改原文）
- 不要把译文写成本地 json 文件
