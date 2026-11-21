# 人名词条评估（30 个 pending 条目）

> 证据来源：`wikipali search --lemma <name>`（全量 300 条 / 黑体 200 条）+ `dist` +
> 定向词形探针。判据是**语料里的章节名与黑体定释**，不是记忆。
> 评估脚本与原始 JSON 在会话 scratchpad 的 `assess/` 下。

## 判定汇总

| 名字 | 汉译 | 命中 | 判定 | 语料证据（章节名） |
|---|---|---|---|---|
| sāriputta | 舍利弗 | 229 | **单人** | Sāriputtasutta / -saṃyutta / -theraapadāna，均指同一上首弟子 |
| mahāmoggallāna | 大目犍连 | 190 | **单人** | Mahāmoggallānasutta / -theraapadāna / -sīhanādakathā |
| mahākassapa | 大迦叶 | 122 | **单人** | Mahākassapattheravatthu / -sutta / -theraapadāna |
| anāthapiṇḍika | 给孤独 | 77 | **单人** | Anāthapiṇḍikovādasutta / -vatthu / -vagga |
| vessavaṇa | 毗沙门 | 68 | **单人** | Janavasabha / Āṭānāṭiya；`kuvero`(21) 为同一神的别名 |
| bimbisāra | 频婆娑罗 | 65 | **单人** | Bimbisārasamāgamakathā / Bimbisārarājavatthu |
| cūḷapanthaka | 周利盘陀 | 62 | **单人** | Cūḷapanthakattheravatthu / -sutta / -theraapadāna |
| sāmāvatī | 沙摩婆提 | 53 | **单人** | Sāmāvatīvatthu / Khujjuttarā-sāmāvatīvatthu |
| padumuttara | 莲华上佛 | 50 | **单人** | Padumuttarabuddhavaṃsa；仅指该佛 |
| maṭṭhakuṇḍalī | 摩陀昆达利 | 45 | **单人** | Vimāna / Peta / Jātaka / Dhp 四处同一人 |
| rajjumālā | 拉朱马拉 | 44 | **单人** | Rajjumālāvimānavatthu |
| devadatta | 提婆达多 | 105 | **单人** | Devadattavatthu / -sutta / -pabbajjapañho，未见第二位 |
| vipassī | 毗婆尸佛 | 54 | **单人**（有同形词） | Vipassībuddhavaṃsa / Vipassīsutta；另有形容词 *vipassī*「具观者」，须在词条内分辨 |
| **gotama** | 乔达摩 | 285 | **多人 + 姓氏** | Gotamattheragāthāvaṇṇanā（长老）；绝大多数为婆罗门称佛「bho gotama」；`gotamagottena` 证其为姓 |
| **kālāma** | 迦罗摩 | 139 | **多人** | Pāsarāsi/Bodhirājakumāra/Saṅgārava 的 Āḷāra Kālāma；Kesamuttisutta 的迦罗摩族；Bharaṇḍukālāmasutta |
| **moggallāna** | 目犍连 | 139 | **多人** | Moggallānasaṃyutta（大目犍连）；`gaṇakamoggallāno`(7)；Moggallānabyākaraṇa / -pañcikā（文法家目犍连） |
| **kassapa** | 迦叶 | 132 | **多人（最复杂）** | Kassapabuddhavaṃsa / Mahākassapa- / Uruvelakassapa- / Nadīkassapa- / Gayākassapa / Kumārakassapa- / Acelakassapa- / Pūraṇakassapavādo / Lomasakassapajātaka；另 `kassapagotto`(9) 为姓 |
| **ānanda** | 阿难 | 127 | **多人** | Ānandattheravatthu 等（长老）；`ānandaseṭṭhi`(2) 悭吝长者；`ānandācariyena`(3) 复注作者阿阇梨 |
| **tissa** | 提舍 | 122 | **多人 + 同形词** | Tissabuddhavaṃsa / Tissattheragāthā / Tissātherīgāthā / Tissametteyya- / Tissabrahmāsutta / `moggaliputtatisso`；同形词 *tisso*「三」(阴性)污染严重 |
| **visākhā** | 毗舍佉 | 122 | **多人 + 同形词** | Visākhāvatthu(38, 鹿母) / Visākhātherīgāthā / Visākhasutta（男性 `visākho` 35）/ `pañcāliputto`；另 visākhā 为星宿名与月名 |
| **sirimā** | 希利摩 | 106 | **多人** | Sirimāvimāna- / Sirimāvatthu（王舍城名妓）；Sirimattheragāthā（男性长老） |
| **uttarā** | 郁多罗 | 91 | **多人 + 同形词严重** | Uttarānandamātāvatthu / Uttarāupāsikāvatthu / Uttarātherīgāthā / Uttarāvimāna / Uttaramāṇavavatthu / Uttarattheragāthā；同形词 *uttara*「上·北·胜」（anuttara / lokuttara / Uttaravinicchaya 书名）占比极高 |
| **nanda** | 难陀 | 84 | **多人 + 同形词** | Nandattheravatthu（佛异母弟）/ Sundarīnandātherī / Abhirūpanandātherī / Janapadakalyāṇī-rūpanandā / Nandamāṇavapucchā / Nandagopālakavatthu / Nandāpetivatthu / Nandopanandanāgadamana / Soṇanandajātaka；同形词 *nandati*「喜」 |
| **upāli** | 优波离 | 78 | **多人** | Upālittheravatthu（持律第一）/ Upālisutta（MN56 尼乾子居士 `upāligahapati`）/ Upālidārakavatthu |
| **anuruddha** | 阿那律 | 72 | **多人** | Anuruddhasaṃyutta 等（长老）；`anuruddharājā`(8)；`anuruddhācariyena`(5) 阿毗达摩论师 |
| **puṇṇa** | 富那 | 47 | **多人 + 同形词** | Puṇṇamantāṇiputta- / Puṇṇasutta（输那波兰陀）/ Puṇṇattheragāthā / Puṇṇātherīgāthā / Puṇṇadāsīvatthu；同形词 *puṇṇa*「满」（paripuṇṇa / puṇṇamā）占比高 |
| **subhaddā** | 须跋陀 | 47 | **多人（含男女同形）** | Subhaddaparibbājakavatthu（佛最后弟子，男）/ Subhaddādeviupasaṅkamana（大善见王后）/ Cūḷasubhaddāvatthu / `mahāsubhaddā`(7)；另有引发第一结集的老比丘须跋陀 |
| **mallikā** | 末利迦 | 45 | **多人 + 同形词** | Mallikādevīsutta / -vatthu（拘萨罗王后）/ Mallikāvimānavaṇṇanā；`bandhulassa`(3) 之妻末利迦；同形词 mallikā「茉莉」 |
| **aggivessana** | 阿耆毗舍那 | 44 | **姓氏，对应多人** | Mahā/Cūḷasaccakasutta 的 Saccaka(39)；Dīghanakhasutta 的 Dīghanakha(6)；Dantabhūmisutta 的 Aggivessana ＝ `aciravato`(4) |
| **dhanañcaya** | 达难阇耶 | 51 | **多人 + 文法例词** | Visākhāvatthu 的 `dhanañcayaseṭṭhi`(9)（毗舍佉之父）；Kurudhamma / Vidhurajātaka 的檀那阇耶·俱卢王；另在 Saddanīti / Moggallāna 文法书中作词形范例 |

**统计：单人 13 个；同名多人 17 个。**

## 同形词干扰（影响工作集，须用 `--category 人名` 过滤并在末尾记账）

- `uttarā` — *uttara*「上·北·胜」；`anuttara` / `lokuttara` / 书名 *Uttaravinicchaya* 占抽样的多数
- `puṇṇa` — *puṇṇa*「满」；`paripuṇṇa` / `puṇṇamā`（满月）/ `māsapuṇṇatā`
- `tissa` — *tisso*「三」（阴性主格），如 *tisso vedanā* / *tisso sikkhā*
- `nanda` — *nandati*「喜」；`abhinandati` / `ānanda`（词形展开会互串）
- `mallikā` — 茉莉花
- `visākhā` — 星宿名 / 月名（Visākha 月）
- `vipassī` — 形容词「具观者」
- `dhanañcaya` — 文法书中的名词范例

## 需要产出的词条

多人组一律 **消歧页 + 每位分立词条**（skill 硬规则）。消歧页占用裸名
`<name>.md`，分立词条用语料里实际存在的巴利限定名。

| 组 | 消歧页 | 分立词条 |
|---|---|---|
| gotama | `gotama.md` | `gotamabuddha.md`（世尊）、`gotamatthera.md`；姓氏义在消歧页说明 |
| kālāma | `kālāma.md` | `āḷārakālāma.md`、`kesaputtakālāma.md`（族）、`bharaṇḍukālāma.md` |
| moggallāna | `moggallāna.md` | `gaṇakamoggallāna.md`；大目犍连见 `mahāmoggallāna.md`；文法家在消歧页说明 |
| kassapa | `kassapa.md` | `kassapabuddha.md`、`uruvelakassapa.md`、`nadīkassapa.md`、`gayākassapa.md`、`kumārakassapa.md`、`acelakassapa.md`、`pūraṇakassapa.md`；大迦叶见 `mahākassapa.md` |
| ānanda | `ānanda.md` | `ānandatthera.md`、`ānandaseṭṭhi.md`；阿阇梨在消歧页说明 |
| tissa | `tissa.md` | `tissabuddha.md`、`tissatthera.md`、`tissātherī.md`、`tissametteyya.md`、`tissabrahmā.md`、`moggaliputtatissa.md` |
| visākhā | `visākhā.md` | `visākhāmigāramātā.md`、`visākhātherī.md`、`visākhatthera.md` |
| sirimā | `sirimā.md` | `sirimāgaṇikā.md`、`sirimatthera.md` |
| uttarā | `uttarā.md` | `uttarānandamātā.md`、`uttarātherī.md`、`uttaramāṇava.md`、`uttaratthera.md` |
| nanda | `nanda.md` | `nandatthera.md`、`sundarīnandā.md`、`abhirūpanandā.md`、`nandamāṇava.md`、`nandagopālaka.md`、`nandopananda.md` |
| upāli | `upāli.md` | `upālitthera.md`、`upāligahapati.md`、`upālidāraka.md` |
| anuruddha | `anuruddha.md` | `anuruddhatthera.md`、`anuruddharājā.md`、`anuruddhācariya.md` |
| puṇṇa | `puṇṇa.md` | `puṇṇamantāṇiputta.md`、`puṇṇasunāparantaka.md`、`puṇṇātherī.md`、`puṇṇadāsī.md` |
| subhaddā | `subhaddā.md` | `subhaddaparibbājaka.md`、`subhaddavuḍḍhapabbajita.md`、`subhaddādevī.md`、`cūḷasubhaddā.md` |
| mallikā | `mallikā.md` | `mallikādevī.md`、`mallikābandhulabhariyā.md` |
| aggivessana | `aggivessana.md`（姓氏页） | `saccaka.md`、`dīghanakha.md`、`aciravata.md` |
| dhanañcaya | `dhanañcaya.md` | `dhanañcayaseṭṭhi.md`、`dhanañcayakorabya.md` |

**合计：单人 13 + 消歧页 17 + 分立词条约 55 ＝ 约 85 个词条。**

## 待生成时核实的存疑点

1. `uttarā` 的「难陀母」与「优婆夷（富那之女）」是否同一人——DPPN 分列，语料需按黑体定释核。
2. `visākhā` 男性 `visākho` 是否可分「毗舍佉·五盖罗子长老」与「法施比丘尼之夫毗舍佉优婆塞」两人。
3. `nanda` 的 Sundarīnandā / Rūpanandā / Janapadakalyāṇī 三名是否指同一位比丘尼。
4. `subhaddā` 男女同形：裸名列在人名表里作阴性，实际语料以男性 Subhadda 为主。
5. `puṇṇa` 的输那波兰陀富那与《长老偈》富那长老是否同一人。
6. `moggallāna` 文法家为后代著作署名，是否纳入正式词条。
