# 人名百科生成 · 进展与续做说明

> 更新：2026-08-26 · 人名条目全部完成
> 相关文件：`_assessment-persons.md`（评估结论）、`pali_terms.csv`（总台账）、`tools/`（可复用脚本与缓存）

---

## ⚠️ 换机前必读：这个目录不进 git

`.gitignore` 第 11 行 `/workspace/` 把整个 `workspace/` 排除在版本控制外
（`git check-ignore -v workspace/terms/sāriputta.md` 可复验）。
**`git push` 不会带走这里的任何东西。**换机时三选一：

1. 直接打包拷贝：`tar czf terms.tgz workspace/terms/` （含 `tools/`，约 14 MB）
2. 在新机重跑：只需 `tools/` 里的脚本 + `wikipali` CLI，词条可重新生成，
   但**已完稿的 88 篇会丢**，要重写
3. 若决定让词条进版本库：把 `workspace/terms/*.md` 与 `pali_terms.csv`
   从 gitignore 里豁免（如加 `!/workspace/terms/`），再提交

> 注：`tools/assess-raw/` 是 30 个人名的检索原始结果（约 14 MB）。
> 带上它，换机后**不必重跑 60 次 `wikipali search`**（原本约 8 分钟）。

---

## 任务状态：**已完成**

`pali_terms.csv` 中的人名条目已全部生成，共 **88 个词条**（消歧页 17 + 分立词条 55 + 单人条目 13 + 先前完成的 3）。
全部经 `tools/verify.py` 逐段核对巴利引文，**0 处不符**。CSV 中已无 pending 行。

用户在本轮开始时确认了上一轮遗留的三个验收点：
1. 消歧页形态（每位一个 `##` 小节：身份 + 一条引文 + `→ [[分立词条]]`，末尾附姓氏/同形词说明）；
2. 分立词条用巴利全名命名；
3. 语料篇幅不足以独立成条者，只在消歧页给一节。

---

## 完成清单

### 消歧页（17）

`kassapa` `dhanañcaya` `mallikā` `sirimā` `moggallāna` `aggivessana` `upāli`
`anuruddha` `ānanda` `gotama` `visākhā` `kālāma` `puṇṇa` `uttarā` `subhaddā`
`nanda` `tissa`

### 分立词条（55）

- **kassapa 组**：`kassapabuddha` `uruvelakassapa` `nadīkassapa` `gayākassapa` `kumārakassapa` `acelakassapa` `pūraṇakassapa`
- **dhanañcaya 组**：`dhanañcayaseṭṭhi` `dhanañcayakorabya`
- **mallikā 组**：`mallikādevī` `mallikābandhulabhariyā`
- **sirimā 组**：`sirimāgaṇikā` `sirimatthera`
- **moggallāna 组**：`gaṇakamoggallāna`
- **aggivessana 组**：`saccaka` `dīghanakha` `aciravata`
- **upāli 组**：`upālitthera` `upāligahapati` `upālidāraka`
- **anuruddha 组**：`anuruddhatthera` `anuruddharājā` `anuruddhācariya`
- **ānanda 组**：`ānandatthera` `ānandaseṭṭhi`
- **gotama 组**：`gotamabuddha` `gotamatthera`
- **visākhā 组**：`visākhāmigāramātā` `visākhātherī` `visākhatthera`
- **kālāma 组**：`āḷārakālāma` `bharaṇḍukālāma` `kesaputtakālāma`
- **puṇṇa 组**：`puṇṇamantāṇiputta` `puṇṇasunāparantaka` `puṇṇātherī` `puṇṇāsikkhamānā`
- **uttarā 组**：`uttarānandamātā` `uttarātherī` `uttaramāṇava` `uttaratthera`
- **subhaddā 组**：`subhaddaparibbājaka` `subhaddavuḍḍhapabbajita` `subhaddādevī` `cūḷasubhaddā`
- **nanda 组**：`nandatthera` `rūpanandā` `sundarīnandā` `abhirūpanandā` `nandamāṇava` `nandagopālaka` `nandopananda`
- **tissa 组**：`tissabuddha` `tissatthera` `tissātherī` `tissametteyya` `tissabrahmā` `moggaliputtatissa`

### 单人条目（13）

`sāriputta` `mahākassapa` `mahāmoggallāna` `anāthapiṇḍika` `vessavaṇa` `bimbisāra`
`cūḷapanthaka` `sāmāvatī` `padumuttara` `maṭṭhakuṇḍalī` `rajjumālā` `devadatta` `vipassī`

---

## 本轮解决的存疑点

评估阶段留下的六个存疑点，写作时按语料黑体定释逐一核实：

1. **`uttarā` 的「难陀母」与「优婆夷」**——语料只支持一位「郁多罗·难陀母」（王舍城富那长者之女，禅修第一），另有《长老尼偈》的郁多罗长老尼（七集）与一集的同名者，已在 `uttarātherī` 末节说明。
2. **`visākhā` 的男性 `visākho`**——确为两人：毗舍佉·般遮罗子长老（`visākhatthera`）与法施比丘尼之夫毗舍佉优婆塞（篇幅不足，列于消歧页）。
3. **`nanda` 的三名女性**——`Sundarīnandā`（律藏四姊妹之一）与 `Abhirūpanandā`（差摩迦之女）是两人；`Rūpanandā` ＝ `Janapadakalyāṇī` ＝ 禅修第一的难陀长老尼，是同一位（an1_A 99:1119「Rūpanandātipi vuccati」）。
4. **`subhaddā` 男女同形**——裸名在表中作阴性，实际命中以男性为主，已在消歧页「检索提示」说明。
5. **`puṇṇa` 的两位**——《长老偈》富那长老与输那波兰陀富那是**同一人**（kn8 128:1793 明记其求教诫后赴输那波兰陀）；另发现《长老尼偈》的富那长老尼即给孤独家的婢女富那（kn9 106:3132），与学法女富那（106:53）是两人。
6. **`moggallāna` 文法家**——为后代著作署名，不立人物词条，在消歧页说明。

此外发现两处可并的同名：《大史》的**帝须梵天**即后来的**目犍连子帝须**（下生目犍连婆罗门家）；`vipassī` / `devadatta` / `dhanañcaya` 的文法词例与形容词义，均已在相应词条内记账。

---

## 每条词条的标准作业流程

上一台机器摸索出来的、能过校验的流程。**不要改用 rank 排序直接取工作集**——
试过，取回来的全是注疏序偈与零碎语法注释，不是传记骨架。

1. **定向检索传记锚点**，而不是泛取高分命中：
   ```
   tools/hunt.sh "<有辨识度的词形>" 3
   ```
   人名条目的锚点通常是：`etadagga` 称号词（如 `dhutavādānaṃ`）、
   俗名/别名、出家因缘章名、证悟场景、般涅槃地名、专属经名。
   注意**要用变格后的词形**（`uruvelakassapo` 而非 `uruvelakassapa`），
   裸词干搜索经常返回 0，那是词形不匹配，不代表语料里没有。
   `hunt.sh` 只做**单词精确匹配**，多词短语一律返回 0，不要用整句去搜。

2. **取全文**（search 的 `highlight` 是截断 HTML，禁止直接引用）：
   ```
   python3 tools/getx.py <标签> 108:3743 165:805 …
   ```
   会自动剥页码锚点（`M0.307`）、版本夹注、异读方括号（`[ghaṭīkāro (sī. pī.)]`），
   并按段号正确落位书名（一个 book 号可能装多部书，必须按段号取，
   直接拿 book 号取第一条会张冠李戴）。

3. **写词条**，结构照 `.claude/skills/pali-encyclopedia/references/entry-types.md`：
   - 人名：定义段 → 目录 → 生平各节 → **相关经文（每经一个 `###`，不用表格）**
     → 参考文献 → 相关条目 → 分类标签
   - 消歧页：定义段 → 每位一个 `##`（身份 + 一条引文 + `→ [[链接]]`）→ 姓氏/同形词说明
   - `{{quality|pending}}` 后**紧跟内容，不留空行**
   - 分类标签只能取自 `references/taxonomy.md`

4. **校验**（这一步不能省）：
   ```
   python3 tools/verify.py workspace/terms/<name>.md
   ```
   按段落把每条 `"*巴利*"` 与该段所有 `{{para}}` 所指原文做归一化子串比对。
   **必须校验到 0 problems 再收工。**

5. **登记台账**：
   ```
   python3 tools/csvup.py "D|<已有词>|<file>.md|<备注>" "A|<新词>|0|人名|<汉译>|<file>.md|从 X 拆出"
   ```

---

## 校验时踩到的坑（本轮新增，写下一批时照办）

- **原文中的夹注引用会打断引文**。义注里常有 `( dha . pa .223)` `( a . ni .1.209,217)`
  这类出处夹注，`clean()` 不会剥掉；跨过它的长引文必然 MISMATCH。
  解决：在夹注处用 `…` 断开，写成两段引文。
- **verify 的 pool 用 `set(ids)`，段序不定**。因此**一条引文不能跨两个段号**
  （偈颂尤其常见，每个 pāda 是独立段）。解决：一句一引，或给该段落补上所有相关 `{{para}}`。
- **长元音的尾字要照抄**。如 `na kathetī` 不可写成 `na katheti`；
  MISMATCH 只差一个 `ī` 时，先查这一类。
- **verify 首次跑一个新书号会很慢**（要逐段拉取并写 `paracache.json`），
  遇到 2 分钟超时属正常，用 `timeout 600` 重跑即可，第二次走缓存。
- 顺带修好了 `kiriyā.md` 中一处同类问题（`( paci .84)` 夹注），现全库 0 problems。

---

## `tools/` 内容说明

| 文件 | 用途 |
|---|---|
| `hunt.sh <词形> [N]` | 定向检索，打印命中的坐标 + 章名 + 片段（单词精确匹配） |
| `getx.py <标签> <book:para>…` | 按坐标取全文并清洗，存 `mf/<标签>.extra.json` |
| `mkmanifest.py` | 清洗与书名落位函数，被其他脚本 import |
| `verify.py <md 文件>` | **引文校验**，输出不符的引文；缓存在 `paracache.json` |
| `digest.py` `csvup.py` `books.json` | 摘要、台账、书名缓存 |
| `assess-raw/` | 30 个人名的 search 原始结果，重做评估时才需要 |

脚本假定工作目录是仓库根 `pali-translab/`。

**外部依赖**：`wikipali` CLI。`command -v wikipali` 为空时用
`${CLAUDE_PLUGIN_ROOT}/bin/wikipali`，并重启会话。

---

## 已知坑（检索阶段）

- **词干搜索返回 0 不等于语料里没有**。`wikipali search` 不带 `--lemma` 时按精确词形匹配，
  必须给变格形式。带 `--lemma` 会展开词形，但会引入同形词污染。
- **同形词污染严重的 8 个名字**：`uttarā`（*uttara* 上/北/胜）、`puṇṇa`（「满」）、
  `tissa`（*tisso*「三」阴性）、`nanda`（*nandati*「喜」）、`mallikā`（茉莉）、
  `visākhā`（星宿/月名）、`vipassī`（「具观者」）、`dhanañcaya`（文法词例）。
  这些已在各自消歧页末尾记账说明。
- **一个 book 号可能装多部书**，书名必须按段号落位（`mkmanifest.bookinfo` 已处理）。
- `wikipali get` 返回的是**逐句** row，同一 `paragraph` 会有多行，引用时按句取，坐标仍记段号。
