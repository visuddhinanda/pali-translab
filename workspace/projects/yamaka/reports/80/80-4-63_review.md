# Review — 80:4-63（channel: 73c03e1a-f333-11f0-808a-438f0af4b9e9）

> 资源：pali ✅／nissaya ❌（未注入，本次无词级基准，格与句法只凭原文核对）／义注 ✅（98:1838-1852，Dhammayamaka-vaṇṇanā）
>
> 数据注记：注入的义注记录 `layer` 字段写成了 `mula`，内容实为义注（book 98，标题 Dhammayamaka-vaṇṇanā）。本报告按义注使用。请检查 `wp_pull.py` 的层次标记。
>
> 被解释词核对：本 chunk 是施设分总说（mūla §1–10）。义注对这一部分（98:1840，“1-16.”）只讲结构，**没有黑体被解释词**。义注的黑体词（如 **kusalā kusaladhammā**、**Avasesā dhammā na akusalā dhammā**）出自 98:1842，解释的是 mūla §17–32 的施设分详说，不在本 chunk。所以本 chunk 不需要做逐字对照。

## 跨段一致性
- 无。逐项核对过以下各点，全 chunk 一致：
  - kusalā／akusalā／abyākatā：善／不善／无记
  - na ～：非～
  - dhammā：法
  - Ka／Kha：（甲）／（乙）
  - anulomaṃ／paccanīkaṃ：顺／逆
  - vāra：分
  - 编号格式：“n.（甲）”
  - 问句：一律“……是……吗？”

## §4、§5、§6、§7、§22、§49 标题（跨章一致性提醒，非本 chunk 内部问题）
- **问题**：跨章对应。**义注**：“Tattha khandhayamake vuttanayeneva pāḷivavatthānaṃ veditabbaṃ. Yathā hi tattha paṇṇattivārādayo tayo mahāvārā…, tathā idhāpi.”（98:1840）义注明确说，法双论的结构和蕴双论相同。所以下面这些标题的译法应和蕴双论（及其他各双论）已有的译法完全一致：Paṇṇattivāro 施设分、uddeso 总说、Padasodhanavāro 词清净分、Padasodhanamūlacakkavāro 词清净根轮分、Suddhadhammavāro 纯法分、anulomaṃ 顺、paccanīkaṃ 逆。另外，义注 98:1840 列出的四分名称（padasodhanavāra、padasodhanamūlacakkavāra、suddhadhammavāra、suddhadhammamūlacakkavāra），义注层的译文也要和这里的标题同译。
- **建议**：harmonize 时拿本 channel 的蕴双论标题比对，有出入就统一。本 chunk 内部无误。

## §38、§40、§42、§44、§46、§48、§58–§63（“na dhammā” → “非法”）
- **问题**：存疑，可能有歧义。“na dhammā” 是对 dhammā 的否定（不是法的东西），译作“非法”在字面上没错。但“非法”在汉语佛典里通常对译 adhamma（与正法相对的“非法”），在现代汉语里又是“违法”的意思，一般读者可能会误读。
- **建议**：不强制改，因为双论的问句格式要求简洁对称，“非法”和“非善”“非无记”等在体例上一致。建议把这个译法登记进 `terms.md`（如“na dhammā：非法（指不属于法者，非 adhamma）”），并在全书首次出现处加一条段后小字注说明，避免读者误解。如果项目决定改译（如“非诸法”“不是法的”），必须全书统一替换。

## §49 句 80-49-2-3
- **问题**：OCR / 原文疑问。巴利原文作 “3 Suddhadhammavāro”，编号后缺 “.”，和 §7 “1. Padasodhanavāro”、§22 “2. Padasodhanamūlacakkavāro” 的格式不一致。译文补成“3. 纯法分”，处理得对。
- **建议**：译文不改。把这条原文缺点号的情况记入 `known-issues.md` 的“OCR / 原文问题”。
