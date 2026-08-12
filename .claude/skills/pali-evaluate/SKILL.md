---
name: pali-evaluate
description: "Atomic skill: evaluate translations stored in a WikiPali channel and output a scored markdown report. Read-only — never modifies the translation."
---

# pali-evaluate

译文最终评估原子能力。读回 channel 里的译文，打分并列出问题清单，
**只输出 markdown 报告——不改译文、不写 channel。**

## 在流水线里的位置

```
translate → review → revise → harmonize → evaluate
                              最后一个改译文的步骤   ← 这里
```

**排在全部改动步骤之后**：评的必须是定稿，中途评的是半成品，分数与问题清单都会失真。
报告是验收结论——要照着改，回头再跑 revise 或 harmonize，然后重新评。

## 依赖

需要 **wikipali 插件**（`wikipali` CLI）。只用读端命令，不涉及写入。

## 调用方式

```
/pali-evaluate <book>:<para> [--channel <uid>] [--method <name>]
```

## 分派流程

1. 解析 `$ARGUMENTS` 为 `<book>:<para>` 与目标 channel
2. 加载 method 配置（项目 `methods/<method>/evaluate.md` 优先于 skill `methods/default/evaluate.md`，整文件覆盖）
3. 加载 knowledge（同 pali-translate）
4. 取资源并按 `(word_start, word_end)` 对齐：
   - 现有译文：`wikipali get <book>:<para> --json --channel <ch>`
   - 巴利原文：`wikipali get <book>:<para> --json`
   - **义注（释义标准）**：`wikipali related <book>:<para> --json` → 取 `aṭṭhakathā` 那条坐标 → `get`
   - **nissaya（词级基准）**：`wikipali versions` 找 `type=nissaya` → `get --channel <uid>`
   - 缺哪个就降级用剩下的，并在理由中说明
5. 评估：以义注定释义、nissaya 定词法逐句核对，按分级表定级（见 method 文档）
6. 写出 markdown 报告 `workspace/reports/{book}/{start}-{end}_final.md`

> 执行层封装：`scripts/wp_pull.py --book B --para <起>-<止> --nissaya --atthakatha --channel <ch>` 一次取齐。

## 非侵入（硬约束）

- **不写 channel**：评估结论只进报告，不碰译文一个字
- **不在译文里插标注**：问题片段在报告的问题清单里引用，不套 span、不加标记
- 要改译文是 revise / harmonize 的事——把评估报告当作下一轮的输入即可

## 输出路径

```
workspace/reports/{book}/{start}-{end}_final.md   # 总分 / 信心 / 理由 / 问题清单
```

## 详细规范

参见 `methods/default/evaluate.md`
