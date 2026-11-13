---
name: improve-codebase-architecture
disable-model-invocation: true
description: "只读扫描模块或变更热点，找出有证据的架构改善候选，生成 HTML 报告。"

metadata:
  category: engineering
  tags: [architecture, analysis, review, maintenance]
  dependencies: []
  requires_context: [project]
  requires_task: prompt
  outputs:
    type: analysis
---

# 架构改善候选扫描

在当前请求的范围内调查结构摩擦，交付一份有依据的离线 HTML 报告。读取源码、调用方、历史和项目决策；只写本次报告所需的产物，不修改业务代码、依赖、领域词表或 ADR，不自动启动重构或后续设计流程。

## 确定扫描范围

用户指定的模块、路径或痛点优先。未指定时，用 Git 历史选择近期反复修改的区域：先看 `git log --oneline` 和 `git log --name-only`，在报告中写清采用的提交区间及路径，不自行把短期热点推成全仓结论。生成代码、锁文件和批量格式化造成的频繁变更不代表架构问题。

没有 Git 历史或没有明显热点时，先依据入口、测试和模块依赖缩小范围；仍有多个会改变结论的方向时再确认。记录当前 revision、工作区状态和本次未覆盖的部分。读取命中的项目规范与相关架构决策，既有决策是约束；需要重议时给出新证据。

读取项目上下文中与扫描范围有关的业务规则、领域词义及已裁定歧义，将它们与源码、测试一起列为输入依据。上下文目录可能被默认文件搜索忽略，按项目实际入口读取；未读到材料与材料没有规定某项规则要分开记录，不能把已提供的约定重新当成未知问题。

## 找候选并尝试推翻它

先看调用者为用对一个模块必须知道多少内部步骤、错误处理和状态。做删除实验时，说明取消该模块后哪些复杂性会消失、哪些会重新散到调用方；不能凭接口短或代码少就断定结构好坏。保留项目已有清楚含义的术语。

术语和 deletion test 的步骤按 skill 安装目录里的 `create-plan/references/module-design.md`；只读这份参考，不启动计划流程。未安装 create-plan 时，按本节的证据与删除实验继续，不猜测相邻目录或自动安装依赖。

- 从真实调用或变更任务追踪：同一规则在哪几处重复决定，理解一个概念需要跳转哪里，调用方承担了哪些内部步骤，测试为什么难以覆盖实际行为。
- 对每个候选写明源码位置、调用关系或提交证据，再做 deletion test。区分已观察到的事实、由事实推出的收益与尚未验证的假设。
- 检查反例：兼容层、权限边界、协议适配和已批准的迁移是否解释了现状。不能解释的不确定性留在报告里，不当作确定缺陷。
- 在授权且不会影响外部状态的条件下运行最小相关验证。未运行时写清原因与建议命令，不把静态阅读写成运行期证据。
- 建议停在职责、复杂度归属和验证面的变化。明确收益、迁移代价和要补的证据；不替用户决定新接口、字段、兼容策略或项目命名。

## 交付离线 HTML

按 `.ai-configs/conventions.md` 的 analysis 产物规则确定目录与文件主名，HTML 使用同一主名和 `.html` 扩展名。沿用当前需求身份；目录约定仍由项目决定。

先读 [`references/report-format.md`](references/report-format.md)，整理候选与证据。用当前 skill 目录下的 `scripts/render_report.py` 渲染；输入示例在 `assets/example-report.json`。解析出的输入和输出路径由调用者传入，脚本不猜项目目录。

```sh
python3 scripts/render_report.py --input "$REPORT_JSON" --output "$REPORT_HTML"
```

报告包含扫描范围、选择依据、推荐理由、各候选的现状与建议、验证结果、代价及不确定性。零候选也要报告检查了什么、证据边界是什么，不能为了填卡片发明问题。推荐强度表达证据与收益的把握，不等于批准实施。

渲染器仅使用标准库和内联 CSS，无 CDN、远端字体或浏览器请求。打开生成的文件检查可读性、对照与证据是否齐全，再向用户给出绝对路径链接及最值得关注的结论。用户当前只要扫描时，到报告为止；用户明确选择继续设计或实施时，再按该请求衔接。

## 来源

流程思想参考 [Matt Pocock 的 improve-codebase-architecture](https://github.com/mattpocock/skills/blob/c55ee46073ed923f86ce59a5eb3b6d895095d1b7/skills/engineering/improve-codebase-architecture/SKILL.md)，本仓重新编写。具体取舍见 [`references/report-format.md`](references/report-format.md) 的来源说明。
