# Dahlia 巴利文翻译 Pipeline 设计文档

> 本文档供 Claude Code 执行使用。所有开发工作在此 repo 中进行。

---

## 一、项目目标

将 VRI 巴利三藏逐句翻译为中文，输出 JSONL 格式，导入 WikiPali。支持多翻译方案实验、LLM 校对、方案评估。

---

## 二、目录结构

```
ROOT/
├── config.toml                  # 数据库连接等配置
├── corpus.json                  # 书目关系配置
├── corpus/                      # 原始语料（只读）
│   ├── pali/
│   │   └── dn/
│   │       └── 1.jsonl          # 巴利原文块
│   ├── nissaya/                 # 缅文逐词解析
│   │   └── dn/
│   │       └── 1.jsonl
│   ├── burmese/                 # 缅文译文（评估用）
│   └── thai/                    # 泰文译文（评估用）
│
├── cache/
│   └── lookup/
│       └── dn/
│           └── 1.jsonl          # Python 预处理结果（术语+字典）
│
├── translations/
│   ├── method_pali/
│   │   └── dn/
│   │       └── 1.jsonl
│   └── method_nissaya/
│       └── dn/
│           └── 1.jsonl
│
├── proofread/
│   ├── method_pali/
│   │   └── dn/
│   │       └── 1.html
│   └── method_nissaya/
│       └── dn/
│           └── 1.html
│
├── evaluation/
│   └── dn/
│       └── 1.json               # 方案横向对比评分
│
├── scripts/                     # Python 工具脚本
│   ├── chunk.py                 # 拆块
│   ├── lemmatize.py             # 词形→词头
│   ├── lookup.py                # 术语表+字典检索
│   └── merge.py                 # 合并分块译文
│
├── .claude/
│   └── commands/
│       ├── lookup.md            # Skill: 预处理
│       ├── translate.md         # Skill: 翻译
│       ├── proofread.md         # Skill: 校对
│       └── evaluate.md          # Skill: 评估
│
└── src/dahlia/
    ├── pali/
    │   └── __init__.py
    └── ...
```

---

## 三、corpus.json 结构

书目之间的注释对应关系。短码用于目录命名。

```json
{
  "dn": {
    "title": "Dīghanikāya",
    "vols": [
      "Sīlakkhandhavaggapāḷi",
      "Mahāvaggapāḷi",
      "Pāthikavaggapāḷi"
    ],
    "atthakatha": "dna",
    "tika": "dnt"
  },
  "dna": {
    "title": "Sumaṅgalavilāsinī",
    "vols": [
      "Sīlakkhandhavaggaṭṭhakathā",
      "Mahāvaggaṭṭhakathā",
      "Pāthikavaggaṭṭhakathā"
    ],
    "root": "dn",
    "tika": ["dnt", "dntt"]
  },
  "dnt": {
    "title": "Līnatthappakāsanā",
    "vols": [
      "Sīlakkhandhavaggaṭīkā",
      "Mahāvaggaṭīkā",
      "Pāthikavaggaṭīkā"
    ],
    "root": "dn",
    "atthakatha": "dna"
  },
  "dntt": {
    "title": "Sādhuvilāsinī",
    "vols": ["Sīlakkhandhavaggaabhinavaṭīkā"],
    "root": "dn",
    "atthakatha": "dna"
  },
  "mn": {
    "title": "Majjhimanikāya",
    "vols": [
      "Mūlapaṇṇāsapāḷi",
      "Majjhimapaṇṇāsapāḷi",
      "Uparipaṇṇāsapāḷi"
    ],
    "atthakatha": "mna",
    "tika": "mnt"
  },
  "mna": {
    "title": "Papañcasūdanī",
    "root": "mn",
    "tika": "mnt"
  },
  "mnt": {
    "title": "Līnatthappakāsanā (MN)",
    "root": "mn",
    "atthakatha": "mna"
  },
  "sn": {
    "title": "Saṃyuttanikāya",
    "vols": [
      "Sagāthāvaggo",
      "Nidānavaggo",
      "Khandhavaggo",
      "Saḷāyatanavaggo",
      "Mahāvaggo"
    ],
    "atthakatha": "sna",
    "tika": "snt"
  },
  "sna": {
    "title": "Sāratthappakāsinī",
    "root": "sn",
    "tika": "snt"
  },
  "snt": {
    "title": "Līnatthappakāsanā (SN)",
    "root": "sn",
    "atthakatha": "sna"
  },
  "an": {
    "title": "Aṅguttaranikāya",
    "vols": [
      "Ekakanipātapāḷi", "Dukanipātapāḷi", "Tikanipātapāḷi",
      "Catukkanipātapāḷi", "Pañcakanipātapāḷi", "Chakkanipātapāḷi",
      "Sattakanipātapāḷi", "Aṭṭhakanipātapāḷi", "Navakanipātapāḷi",
      "Dasakanipātapāḷi", "Ekādasakanipātapāḷi"
    ],
    "atthakatha": "ana",
    "tika": "ant"
  },
  "ana": {
    "title": "Manorathapūraṇī",
    "root": "an",
    "tika": "ant"
  },
  "ant": {
    "title": "Nipāta-ṭīkā",
    "root": "an",
    "atthakatha": "ana"
  },
  "vn": {
    "title": "Vinayapiṭaka",
    "vols": [
      "Pārājikapāḷi", "Pācittiyapāḷi",
      "Mahāvaggapāḷi", "Cūḷavaggapāḷi", "Parivārapāḷi"
    ],
    "atthakatha": "vna",
    "tika": ["vnt", "vnt2", "vnt3", "vnt4"]
  },
  "vna": {
    "title": "Samantapāsādikā",
    "root": "vn"
  },
  "vnt": {
    "title": "Sāratthadīpanī-ṭīkā",
    "root": "vn",
    "atthakatha": "vna"
  },
  "vnt2": {
    "title": "Vajirabuddhi-ṭīkā",
    "root": "vn",
    "atthakatha": "vna"
  },
  "vnt3": {
    "title": "Vimativinodanī-ṭīkā",
    "root": "vn",
    "atthakatha": "vna"
  },
  "vnt4": {
    "title": "Vinayālaṅkāra-ṭīkā",
    "root": "vn",
    "atthakatha": "vna"
  },
  "vnp": {
    "title": "Pātimokkha",
    "vols": ["Bhikkhupātimokkhapāḷi", "Bhikkhunīpātimokkhapāḷi"],
    "atthakatha": "vnpa"
  },
  "vnpa": {
    "title": "Kaṅkhāvitaraṇī-aṭṭhakathā",
    "root": "vnp",
    "tika": ["vnpt", "vnpt2"]
  },
  "vnpt": {
    "title": "Kaṅkhāvitaraṇīpurāṇa-ṭīkā",
    "root": "vnp",
    "atthakatha": "vnpa"
  },
  "vnpt2": {
    "title": "Kaṅkhāvitaraṇī-abhinavaṭīkā",
    "root": "vnp",
    "atthakatha": "vnpa"
  }
}
```

---

## 四、数据结构

### 4.1 巴利原文 JSONL

```jsonl
{"id": "94-1-1-6", "content": "Namo tassa bhagavato arahato sammāsambuddhassa"}
```

- `id`：段落编号，格式 `书-段-开始单词-结束单词`，跨文本对应关系靠此对齐
- `content`：巴利原文

### 4.2 缅文逐词解析 JSONL

```jsonl
{"id": "94-1-1-6", "content": "巴利词1=缅文释义1\n巴利词2=缅文释义2\n..."}
```

- `id` 与巴利原文一一对应
- `content`：Markdown 格式，每行 `巴利词=缅文`

### 4.3 lookup 预处理输出 JSONL

```jsonl
{"pali_id": "94-1-1-6", "entries": [
  {"lemma": "bhagavat", "source": "glossary", "zh": "世尊", "priority": 1},
  {"lemma": "arahant", "source": "glossary", "zh": "阿罗汉", "priority": 1},
  {"lemma": "sammāsambuddha", "source": "dict", "dict_id": "uuid-xxx", "mean": "...", "language": "my", "priority": 2}
]}
```

### 4.4 翻译输出 JSONL

```jsonl
{"id": "94-1-1-6", "pali": "Namo tassa...", "zh": "礼敬彼世尊...", "method": "method_pali"}
```

### 4.5 评估输出 JSON

```json
[
  {"method": "method_pali", "accuracy": 7, "fluency": 8, "terminology": 9, "completeness": 10, "comment": "..."},
  {"method": "method_nissaya", "accuracy": 9, "fluency": 7, "terminology": 9, "completeness": 10, "comment": "..."}
]
```

---

## 五、Python 脚本规格

### 5.1 config.toml

```toml
[postgresql]
host = '127.0.0.1'
port = 5432
user = 'www'
password = '123456'
db-name = 'wikipali'

[api]
term_vocabulary = "https://next.wikipali.org/api/v2/term-vocabulary?view=community&lang=zh-Hans"

[paths]
corpus = "corpus"
cache = "cache"
translations = "translations"
proofread = "proofread"
evaluation = "evaluation"
```

### 5.2 scripts/lemmatize.py

**功能**：提取 JSONL 中所有巴利词形，查 `user_dicts.parent` 还原词头。

**输入**：巴利原文 JSONL 路径

**输出**：`{"surface": "bhagavato", "lemma": "bhagavat"}` 每行一条

**数据库查询逻辑**：
```sql
-- 先查 word 精确匹配
SELECT word, parent FROM user_dicts
WHERE word = ANY(%(words)s)
  AND deleted_at IS NULL
  AND status = 10;

-- parent 非空则 lemma = parent，否则 lemma = word
```

### 5.3 scripts/lookup.py

**功能**：给定一个巴利原文 JSONL，输出该块所有句子的术语+字典检索结果。

**执行顺序**：
1. 读取巴利原文 JSONL，提取所有 `content` 中的词
2. 调用 `lemmatize.py` 逻辑还原词头
3. 查术语表 API（`term-vocabulary`），按 `word` 字段精确匹配，`priority=1`
4. 查 `user_dicts` 表，按 `word` 或 `parent` 匹配，`priority=2`
5. 合并去重，输出到 `cache/lookup/{corpus}/{chunk}.jsonl`

**术语表 API 响应结构**（需实际请求后确认字段）：
- 已知字段：`guid`, `word`, `meaning`, `other_meaning`, `tag`
- 术语表优先级最高，翻译时必须遵守

**缓存策略**：lookup 结果文件存在则跳过，加 `--force` 参数强制重新生成。

### 5.4 scripts/chunk.py

**功能**：将大 JSONL 按段落编号切分为小块（目标 50KB）。

**输入**：完整 JSONL 文件路径，目标大小（默认 50KB）

**输出**：`corpus/pali/{book}/` 目录下多个编号文件

**切分策略**：按 `id` 字段的段落编号边界切分，不在句子中间断开。

### 5.5 scripts/merge.py

**功能**：将分块译文合并为完整 JSONL。

**输入**：`translations/{method}/{book}/` 目录

**输出**：`translations/{method}/{book}.jsonl`

---

## 六、Claude Code Skill 规格

### 6.1 .claude/commands/lookup.md

```
给定语料块路径，运行预处理脚本生成 lookup 缓存。

执行：
python3 scripts/lookup.py $ARGUMENTS

$ARGUMENTS 格式：{corpus}/{chunk}
例如：dn/1

脚本会自动输出到 cache/lookup/{corpus}/{chunk}.jsonl
如果缓存已存在，跳过（除非加 --force）
```

### 6.2 .claude/commands/translate.md

```
你是巴利文汉译专家，精通巴利文、缅文佛典及汉传佛教术语。

翻译前，读取以下文件：
- 巴利原文：corpus/pali/$ARGUMENTS.jsonl
- lookup 缓存：cache/lookup/$ARGUMENTS.jsonl
- 翻译方案：$METHOD

如果 METHOD=method_nissaya，额外读取：
- 缅文逐词解析：corpus/nissaya/$ARGUMENTS.jsonl

如果对应义注存在（查 corpus.json），读取：
- 义注：corpus/{atthakatha_short}/$ARGUMENTS.jsonl（仅用于理解原文，不翻译义注）

翻译规则：
1. lookup 缓存中 source=glossary 的术语，翻译时必须严格遵守，不得自行更改
2. lookup 缓存中 source=dict 的词条，仅供参考
3. 缅文逐词解析提供词义线索，不得照搬缅文句式
4. 现代汉语，简洁自然
5. 术语锚点 [[词语]] 或 [[词语#pali]] 原样保留，不得修改
6. 每句独立翻译，id 严格对应

输出：每行一条 JSON
{"id": "<原id>", "pali": "<原文>", "zh": "<译文>", "method": "<METHOD>"}

输出到：translations/$METHOD/$ARGUMENTS.jsonl
输出前确保目录存在。
```

### 6.3 .claude/commands/proofread.md

```
你是巴利文汉译校对专家。

读取以下文件：
- 巴利原文：corpus/pali/$ARGUMENTS.jsonl
- 待校对译文：translations/$METHOD/$ARGUMENTS.jsonl
- lookup 缓存：cache/lookup/$ARGUMENTS.jsonl

如果 METHOD=method_nissaya，额外读取缅文逐词解析作为参考：
- corpus/nissaya/$ARGUMENTS.jsonl

校对维度：
1. 术语一致性：lookup 中 source=glossary 的术语是否严格使用
2. 意思准确性：译文是否忠实原文
3. 完整性：是否有句子遗漏或 id 不连续
4. 术语锚点：[[...]] 是否完整保留

错误等级：
- 🔴 严重：意思错误、术语误译、句子遗漏、锚点丢失
- 🟡 警告：措辞不准、术语未遵守术语表
- 🔵 建议：可优化但不影响准确性

输出：HTML 文件，每句显示：
- 巴利原文
- 中文译文
- 错误标注（按等级着色）

输出到：proofread/$METHOD/$ARGUMENTS.html
输出前确保目录存在。
```

### 6.4 .claude/commands/evaluate.md

```
你是翻译质量评估专家。

读取以下文件：
- 巴利原文：corpus/pali/$ARGUMENTS.jsonl
- 所有方案译文：translations/*/$ARGUMENTS.jsonl（自动读取所有存在的方案）
- 缅文译文（如存在）：corpus/burmese/$ARGUMENTS.txt（评估参考，不参与翻译）
- 泰文译文（如存在）：corpus/thai/$ARGUMENTS.txt（评估参考，不参与翻译）

评估维度（1-10分）：
- accuracy：译文是否忠实巴利原文
- fluency：汉语是否自然流畅
- terminology：术语是否一致准确
- completeness：是否有遗漏

对每个方案输出一条评估记录，并给出简短说明。

输出到：evaluation/$ARGUMENTS.json
格式：
[
  {"method": "method_pali", "accuracy": 0, "fluency": 0, "terminology": 0, "completeness": 0, "comment": ""},
  {"method": "method_nissaya", "accuracy": 0, "fluency": 0, "terminology": 0, "completeness": 0, "comment": ""}
]
```

---

## 七、Shell 脚本

### lookup.sh

```bash
#!/bin/bash
# 预处理：生成 lookup 缓存
# 用法：bash lookup.sh dn mn sn
for BOOK in "$@"; do
    for f in corpus/pali/$BOOK/*.jsonl; do
        name=$(basename $f .jsonl)
        claude --print "/lookup $BOOK/$name"
    done
done
```

### translate.sh

```bash
#!/bin/bash
# 翻译
# 用法：bash translate.sh method_pali dn mn
METHOD=$1
shift
for BOOK in "$@"; do
    for f in corpus/pali/$BOOK/*.jsonl; do
        name=$(basename $f .jsonl)
        claude --print "/translate $BOOK/$name" --env METHOD=$METHOD
    done
done
```

### proofread.sh

```bash
#!/bin/bash
# 校对
# 用法：bash proofread.sh method_pali dn mn
METHOD=$1
shift
for BOOK in "$@"; do
    for f in translations/$METHOD/$BOOK/*.jsonl; do
        name=$(basename $f .jsonl)
        claude --print "/proofread $BOOK/$name" --env METHOD=$METHOD
    done
done
```

### evaluate.sh

```bash
#!/bin/bash
# 方案评估
# 用法：bash evaluate.sh dn mn
for BOOK in "$@"; do
    for f in corpus/pali/$BOOK/*.jsonl; do
        name=$(basename $f .jsonl)
        claude --print "/evaluate $BOOK/$name"
    done
done
```

---

## 八、执行顺序

```bash
# 1. 拆块（首次）
python3 scripts/chunk.py corpus/pali/dn.jsonl

# 2. 生成 lookup 缓存（各方案共用）
bash lookup.sh dn

# 3. 翻译（可并行跑多方案）
bash translate.sh method_pali dn
bash translate.sh method_nissaya dn

# 4. 校对
bash proofread.sh method_pali dn
bash proofread.sh method_nissaya dn

# 5. 评估对比
bash evaluate.sh dn

# 6. 合并（导入 WikiPali 前）
python3 scripts/merge.py method_pali dn
```

---

## 九、待确认事项（Claude Code 执行前需补充）

| 项目 | 状态 |
|------|------|
| config.toml 数据库连接参数 | ⬜ 待填写 |
| user_dicts 的 dict_id 与字典名对照 | ⬜ 待提供 |
| 术语表 API 实际响应字段结构 | ⬜ 待确认 |
| corpus.json Abhidhamma / Khuddaka 部分 | ⬜ 待补充 |
| 缅文逐词解析文件是否与巴利原文 id 完全对齐 | ⬜ 待确认 |
| Pro 订阅额度限制下的批量节奏 | ⬜ 建议先跑单本 dn 验证质量 |