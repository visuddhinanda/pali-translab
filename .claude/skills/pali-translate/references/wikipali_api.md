# wikipali API 快速参考

> 详细字段表见项目 `DATA_FETCH.md`。本文件给 skill 内部使用。

## Base

- 国际：`https://www.wikipali.org`
- 国内：`https://www.wikipali.cc`（服务相同）
- API 前缀：`/api/v2`
- envelope 列表型：`{ok, data:{rows:[...], count:N}, message}`
- envelope 对象型：`{ok, data:{...}, message}`
- 只读无需认证。

## Endpoints

### 1. Sentence（句子，按段返回）
```
GET /api/v2/sentence?view=paragraph&book={book}&para={para,...}&channels={uuid,...}&format=text
```
- `para` / `channels` 逗号分隔可多值
- `format` ∈ `text` / `markdown` / `html`
- 服务端按 `book_id → paragraph → word_start` 排序，仅返 `ver > 1`
- 跨通道对齐 key：`(book, paragraph, word_start, word_end)`

### 2. Channel 目录
```
GET /api/v2/channel?view=system            # 系统通道全表
GET /api/v2/channel?view=community         # 社区通道全表
GET /api/v2/channel?view=paragraphs&book_id={book}&para={para}  # 指定段有哪些通道
```
- 字段：`uid, name, type, lang, status, is_system, ...`
- `type` ∈ `original` / `translation` / `commentary` / `wbw` / `nissaya`
- `lang` ∈ `pali` / `my` / `zh-Hans` / `zh-Hant` / `en`

### 3. 章节 TOC
```
GET /api/v2/palitext?view=book-toc&book={book}&para={start_para}
```
- `start_para` 从 `references/books.json` 取
- 返回 `[{book, paragraph, toc, level}, ...]`

### 4. 段落 / 章节元信息（path 参数）
```
GET /api/v2/palitext/{book}-{paragraph}
```
- 单对象返回，含 `chapter_len`（章节段数）、`next_chapter` / `prev_chapter` / `parent` / `path`

### 5. 术语表
```
GET /api/v2/term-vocabulary?view=community&lang=zh-Hans
```
- 字段：`guid, word, tag, meaning, other_meaning`

## 关键 channel UUID

| 资源 | name | UUID |
|---|---|---|
| Pali VRI 原文 | `_System_Pali_VRI_` | `00b577c0-13b9-11ee-a05a-b7307efd9ee6` |
| 缅文 nissaya | TODO | TODO |
| atthakatha 注释 | TODO | TODO |
| tika 复注 | TODO | TODO |
| 其他译本 | TODO | TODO |

未填项启动时调 `scripts/fetch_channels.py` 查 channel 目录获取。
