# Pali-TransLab

巴利三藏中译流水线：**读写都经 [wikipali 插件](https://github.com/iapt-platform/wikipali-plugins)，
译文直接写进 WikiPali channel，本地不存 json。**

## 前置

1. 安装 wikipali 插件（提供 `wikipali` CLI），并在**真正的终端**里登录一次：

   ```bash
   wikipali-login
   wikipali ensure-model --name claude-opus-5   # 建立 AI 模型署名身份
   wikipali channels                            # 查目标 channel uid
   ```

2. 复制配置模板，填上默认写入的 channel：

   ```bash
   cp config.orig.toml config.toml
   ```

## 用法

交互模式（Claude Code 里）：

```
/translate 216:35              # 翻译 + 术语检查
/translate-review 216:35       # 翻译 + 一轮审修
/full-pipeline 216:35          # translate → review → revise → harmonize → term-check → footnote → evaluate
/harmonize 216:35              # 整章统稿：统一用词语体 + 修正通读发现的问题
/annotate 216:35               # 只给现有译文加随文注
/export 93:983                 # 导出本地 markdown（一章一文件，带 YAML frontmatter）
```

批量：

```bash
./scripts/pipeline_batch.sh 93 983 986 --channel <uid> --nissaya
```

给的是**本文**的坐标；义注与复注的坐标由 `wikipali related` 自动解析，三层都会翻译。

按 chunk 提交——连续若干段一次交给同一次调用（默认累加到 5000 巴利字符或 12 段截断，
用 `--chunk-chars` / `--max-paras` 调），LLM 看得到上下文，术语与语体才连得起来。
三阶段：先逐层（本文→义注→复注）逐 chunk 做 translate/review/revise，再**跨三层** harmonize
统稿，最后逐层做 evaluate 验收——**评的一定是定稿**。

断点续传靠 `workspace/audit.log`（按段记账），重跑同一命令即可继续（`--force` 强制重做）。

`--nissaya` **只作用于复核步骤**（review / revise / evaluate）。translate 只看本层巴利原文——
译者与检查标准同源，复核就查不出错。唯一的例外是**父层译文**：翻义注要看本文译文、
翻复注要看义注译文，那不是拐杖，是「被解释词逐字同译」这条硬约束的对照。

## 产物去向

| 内容 | 去处 |
|---|---|
| 译文 | WikiPali channel（覆盖式写入，无本地 json） |
| 审稿意见 / 总评 / 术语报告 | `workspace/reports/{book}/`（gitignore） |
| 本地 markdown 副本 | `workspace/export/{章节路径}/{章节名}.md`（仅在用户要求时生成） |

## 文档

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — 四层架构与数据流硬约束（**冲突时以此为准**）
- [`WORKFLOW.md`](WORKFLOW.md) — 流水线、method 规范、反哺学习
- [`DESIGN.md`](DESIGN.md) — ⚠️ 历史文档，多数已作废
