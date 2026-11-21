# Review — 81:7-8（channel: 73c03e1a-f333-11f0-808a-438f0af4b9e9）

> 资源：pali ✅／nissaya ❌（本 chunk 未取到 nissaya，词级核对缺位，格与句法一项无法执行）／义注 ✅（Paṭṭhāna-aṭṭhakathā, book 98 §1889–1955 *Paccayuddesavaṇṇanā*，覆盖本 chunk 全部内容）
>
> 本层为本文（mūla），无父层，故「被解释词与父层逐字同译」不适用。但反向约束成立：本 chunk 的 24 个缘名是义注（98-1917 起）各段黑体 **hetupaccayo** / **ārammaṇapaccayo** … **avigatapaccayo** 的被解释词来源，义注层翻译时必须逐字沿用此处译法。本 chunk 实为全书术语锚点，定稿前务必把 24 词写入 `knowledge/terms.md`。

## 跨段一致性

- 本 chunk 仅两段，且 §7 为标题、§8 为名目列举，无同词异译。
- 列举内部的构词对称性有两处不齐，但均属传统定译，不建议改动，只需登记固定：
  - `atthipaccaya` 译「有缘」／`natthipaccaya` 译「无有缘」（非「无缘」，避免与「没有缘」混读）。
  - `vigatapaccaya` 译「离去缘」／`avigatapaccaya` 译「不离去缘」。义注 98-1944「Atthipaccayadhammā eva avigatabhāvena upakārakattā **avigatapaccayo**」确认后者是前者的换词说法（「Desanāvilāsena pana … ayaṃ duko vutto」），两对译名保持「有/无有」「离去/不离去」的对称即可。

## §7 句 81-7-2-5

- **问题**：格式 — 译文「（一）**缘的列举**」给标题加了 `**…**`，但原文 `(1) Paccayuddeso` 无黑体。在 wikipali 体例中黑体专用于标注被解释词（参见义注 98-1894 `**anulomamhi**`、98-1916 `**hetupaccayo**`），本文层自行加粗会产生伪被解释词，破坏跨层机械核查。
- **建议**：去掉星号，写作「（一）缘的列举」。

- **问题**：术语取义 — `uddesa` 译「列举」偏松，丢了它与 `niddesa` 的成对关系。**义注**：「So uddesaniddesato duvidho. Tassa **hetupaccayo** … **avigatapaccayo**ti ayaṃ uddeso.」（98-1916-42/46）——义注明说本品分 uddesa 与 niddesa 两分，§8 这张名目表就是 uddesa。「列举」无法与后文 niddesa 构成对举。
- **建议**：改为「缘的总说」（或「缘的略说」），并预先约定 niddesa 译「广说」「别释」，两者在全书内成对固定。若保留「列举」，则 niddesa 没有自然的对位词。

- **问题**：编号体例 — 原文 `(1)` 为阿拉伯数字，译文改为「（一）」。单段看不出问题，但全书各分（二十四缘、各 paṭṭhāna）编号很密，体例一旦分叉后面无法收拢。
- **建议**：先定一条编号规则（建议随原文用「（1）」），写进 `knowledge/style.md`，本段据此回改。

## §8 句 81-8-2-52

- 24 个缘名逐一核对义注释义，**无误译、无漏译、无增译**，顺序与原文一致（hetu→avigata，24 项齐全）：因缘（98-1917「hetu ca so paccayo cā」）、所缘缘（98-1920）、增上缘（98-1921「Jeṭṭhakaṭṭhena」）、无间缘／等无间缘（98-1922–1923）、俱生缘（98-1924）、相互缘（98-1925「Aññamaññaṃ uppādanupatthambhanabhāvena」）、依止缘（98-1926）、亲依止缘（98-1927）、前生缘（98-1930）、后生缘（98-1931）、重复缘（98-1932「Āsevanaṭṭhena … paguṇabalavabhāvāya」）、业缘（98-1933）、异熟缘（98-1934）、食缘（98-1935）、根缘（98-1936）、禅缘（98-1937）、道缘（98-1938「niyyānaṭṭhena」）、相应缘（98-1939）、不相应缘（98-1940）、有缘（98-1941）、无有缘（98-1942）、离去缘（98-1943）、不离去缘（98-1944）。标点为全角、无 ASCII 引号，合规。

- **问题**：术语体例 — 依 `knowledge/style.md` 第二节「法相术语首次出现夹注巴利原词（圆括号），其后只用汉译」，这 24 词全部是全书首次出现，且此段正是纲目表，却一个巴利原词都没夹注。若不在此处夹注，后面 niddesa 各段首次出现时还要再夹一遍，体例必然混乱。
- **建议**：二选一并写死进 `style.md`：(a) 在本段逐词夹注，如「因缘（hetupaccaya）、所缘缘（ārammaṇapaccaya）、……」；(b) 本段作纯名目表不夹注，统一在 niddesa 首释处夹注。推荐 (a)——纲目表本身就是术语定义点，夹注集中一处最便于读者回查。无论选哪个，都要在 `terms.md` 登记这 24 条。

- **问题**（存疑，非必改）：`upanissayapaccaya` 译「亲依止缘」用的是传统定译，但与义注的构词解释不完全贴合。**义注**：「Yathā pana bhuso āyāso upāyāso, evaṃ bhuso nissayo upanissayo. Balavakāraṇassetaṃ adhivacanaṃ.」（98-1927-19/30）——`upa-` 在此取「强（bhuso）」义，是「强力原因」的别名，「亲」字传达不出这层意思（「强依止缘」更贴）。
- **建议**：仍采用「亲依止缘」（南传汉译通行、读者认知成本低），但在 `terms.md` 的 note 里记下义注的 `bhuso nissayo` 释义；义注层译到 98-1927 时须把这段构词解释完整译出，不能因汉译作「亲」而回避。

- **问题**（存疑，非必改）：`āsevanapaccaya` 译「重复缘」，与「修习缘」（元亨寺系）并行。**义注**：「Āsevanaṭṭhena anantarānaṃ paguṇabalavabhāvāya upakārako dhammo **āsevanapaccayo**, ganthādīsu purimāpurimābhiyogo viya.」（98-1932）——义注以「读书时前前的用功使后后纯熟有力」为喻，侧重「反复而致熟练」，两译皆有据，「重复缘」更中性。
- **建议**：维持「重复缘」，登记为 confirmed，全书不再摇摆。

## OCR / 原文疑问

- 无。§8 末尾 `avigatapaccayoti .` 的 `ti` 为列举收尾的引语标记，译文不译出，处理正确。
