---
name: pali-review
description: "Atomic skill: review Pali-Chinese translations read back from a WikiPali channel against the Atthakatha commentary and the Burmese nissaya. Outputs an issue list as markdown; does NOT modify translations."
---

# pali-review

译文审读原子能力。从 wikipali channel 读回现有译文，**以义注（aṭṭhakathā）的解释为释义标准、
缅文 nissaya 为词级基准**逐句审查，输出审稿意见 md。**不改译文、不写 channel**——revise 步才改。

## 在流水线里的位置

translate 只看巴利原文独立译出，**义注与 nissaya 从本步骤才开始介入**——它们是独立的
对照标准。译者与标准同源就查不出错，所以复核的价值全在这一步。

## 两重标准的分工

| 标准 | 管什么 | 取法 |
|---|---|---|
| **义注 aṭṭhakathā** | **词句该作何解**——传统释义、术语所指、句子的意思归属 | `wikipali related` 找对应段 → `get` |
| **nissaya** | **词级形态与句法角色**——格、数、主宾属关系、隐含成分 | `wikipali versions` 找 `type=nissaya` → `get --channel` |

义注管「是什么意思」，nissaya 管「这个词在句子里是什么成分」。两者冲突时以义注为准，
并在审稿意见里写明分歧。

**义注是解释，不是本文。** 审稿意见引用义注时必须标明层次（`**义注**：…`），
把义注的说法当成经律本身的说法是学术错误，不是措辞问题。

## 依赖

需要 **wikipali 插件**（`wikipali` CLI）。找不到命令时用 `${CLAUDE_PLUGIN_ROOT}/bin/wikipali`
并提醒用户重启会话。

## 调用方式

```
/pali-review <book>:<para> [--channel <uid>] [--method <name>]
```

`--channel` 缺省取 `config.toml` 的 `[wikipali].channel`。**没有版本号参数**——
channel 里就是当前最新一版。

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>:<para>` 与目标 channel
2. 加载 method 配置（项目 `methods/<method>/review.md` 优先于 skill `methods/default/review.md`，整文件覆盖）
3. 加载 knowledge（同 pali-translate）
4. 取资源，按 `(word_start, word_end)` 对齐成逐句结构：
   - 巴利原文：`wikipali get <book>:<para> --json`
   - 现有译文：`wikipali get <book>:<para> --json --channel <ch>`
   - **义注（释义标准）**：`wikipali related <book>:<para> --json` → 取 tags 含 `aṭṭhakathā`
     的那一条的坐标，再 `wikipali get <义注坐标> --json`
   - **nissaya（词级基准）**：`wikipali versions <book>:<para> --json` 找 `type=nissaya`，再 `get --channel <uid>`
   - 缺哪个就降级用剩下的，**在审稿意见开头显著注明缺了什么**；不要拿相邻段落凑
5. 执行审查（义注定释义、nissaya 定词法，见 method 文档）
6. 写出 markdown 报告

> 本项目在执行层提供封装：
> `scripts/wp_pull.py --book B --para <起>-<止> --nissaya --atthakatha --channel <ch>`
> 一次取齐 pali / nissaya / 义注 / 现有译文。输出的 `layer` 字段区分本文与义注。

## Chunk 批处理（一次审多段）

**按 chunk 提交，不要逐段孤立审。** 一个 chunk 是连续的若干段（默认累加到 ≥ 5000 巴利字符
或 12 段截断），一次性交给同一次调用——只有这样才看得见跨段的术语漂移与语体不一致，
而那正是逐段审查永远发现不了的一类问题。

审稿意见按 chunk 出一份，文件名用段落区间。

## 输出路径

```
workspace/reports/{book}/{start}-{end}_review.md
```

审稿意见是**过程记录，不是译文**，所以留在本地；译文的正本始终在 wikipali。

## 详细规范

参见 `methods/default/review.md`
