# 已知难点和处理方案

> 翻译过程中发现的已知难点，及其推荐处理方式。
> 由 `/extract-rules` 命令从 `audit.log` 中提取，人工确认后写入。

---

## 一、术语争议

<!-- 待补充：从实际翻译中积累 -->

## 二、OCR / 原文问题

<!-- 待补充：记录 VRI 原文中发现的疑似讹误 -->

## 三、句法难点

<!-- 待补充：巴利语特殊句法的处理方案 -->

## 四、批处理脚本（工具链，非译文知识）

> 与翻译内容无关，记录 `scripts/pipeline_batch.sh` 调 `claude -p` 时踩过的坑。

1. **prompt 以 `---` 开头被 `claude -p` 当成选项**
   - 现象：拼接的提示词第一段是 SKILL.md 的 YAML frontmatter（`---` 开头），`claude -p --model sonnet "$PROMPT"` 报 `error: unknown option '---...'`，1 秒即失败。
   - 根因：CLI 参数解析按 argv 首字符 `-` 判定为选项，shell 引号不影响。
   - 处理：在 prompt 前加 `--` 终止选项解析：`claude -p --model sonnet -- "$PROMPT"`。

2. **`claude -p` stdout 裹旁白/代码围栏，污染 JSONL**
   - 现象：模型在 JSONL 前后加「已获取…现在翻译」旁白或 ```jsonl 围栏，整段管道进来就有非法行。
   - 处理：`scripts/wp_push.py` 逐行宽松解析，只留能 `json.loads` 成功的 dict 行；再按 `--expect` 核对条数，不符就拒绝写入（宁可整段重跑，也不要往 channel 里写残缺的一段）。
   - 纯 md 输出的步骤（review / evaluate）不受此影响：整个 stdout 就是报告，直接重定向到文件即可。

---

*最后更新*：2026-06-12
