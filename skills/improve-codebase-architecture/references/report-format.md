# 报告输入与检查

`scripts/render_report.py` 只把已完成的分析转成独立 HTML，不扫描仓库、不判断候选是否成立、不执行报告里的命令。先完成源码与约束核对，再准备 JSON；不要用示例里的虚构发现填实际报告。

## 报告必须回答什么

- **范围**：用户指定了什么，或用哪段 Git 历史选出了哪些路径；记录 revision 和未覆盖范围。
- **事实**：文件与行号、实际调用关系、提交或已运行命令说明了什么。证据摘录先脱敏。
- **现状与建议**：当前复杂度由谁承担，建议把哪条决策放到哪里；可以用多行调用草图，两栏必须描述同一条业务路径。
- **推荐依据**：真实调用方能少处理什么，维护者能把哪些修改与测试留在局部；同时说明迁移、兼容和验证成本。
- **验证与不确定性**：把已运行命令及结果、未运行检查、待补证据分别说清楚。纯静态扫描不得宣称运行结果正确。

推荐可用「优先验证」「值得探索」「证据不足」。前者表示有明确问题和可行的下一次验证，不授权开始实施；后者仍需至少一条真实观察，否则应放进范围说明而不是候选卡。

项目 ADR 或规范与建议冲突时，候选的 `uncertainties` 写出冲突双方与需要重议的原因。没有证据支持重议就移除候选。结论允许没有推荐，或没有任何候选。

## JSON 契约

顶层对象：

| 字段 | 内容 |
|---|---|
| `title` | 报告名称 |
| `scope` | 路径、revision、工作区状态与覆盖边界的简述 |
| `selection_basis` | 用户指定范围，或真实执行的历史查询及采用区间 |
| `summary` | 整体结论；零候选时说明检查结果与边界 |
| `recommended_candidate` | 首选候选的完整 `name`；无推荐时为 `null` |
| `recommendation_reason` | 选择或暂不选择候选的具体理由 |
| `candidates` | 候选对象数组，可为空 |

每个候选对象：

| 字段 | 内容 |
|---|---|
| `name` | 用实际改动含义命名；各候选名称不重复 |
| `recommendation` | `优先验证`、`值得探索` 或 `证据不足` |
| `rationale` | 为什么给这个推荐强度 |
| `current` / `proposed` | 现状与建议的文字或多行调用草图 |
| `impact` | 谁能得到什么改善；判断所依赖的前提 |
| `evidence` | 非空字符串数组，每条写位置和观察，不能只有异味名称 |
| `verification` | 非空字符串数组，写已运行结果或明确的未运行说明与验证办法 |
| `tradeoffs` | 非空字符串数组，说明迁移、兼容、维护或测试成本 |
| `uncertainties` | 字符串数组，可为空；未闭合问题与影响 |

所有内容按普通文本处理，HTML 标记不会执行。渲染器检查结构完整性，但不能替分析者证明证据真伪。

## 使用

从当前 skill 目录解析脚本位置。输入文件和输出 HTML 路径由当前项目 conventions 确定；示例文件只用于了解格式。

```sh
python3 scripts/render_report.py --input "$REPORT_JSON" --output "$REPORT_HTML" --dry-run
python3 scripts/render_report.py --input "$REPORT_JSON" --output "$REPORT_HTML"
```

stdout 固定输出 JSON，包含输出绝对路径、候选数与 `written`。`--dry-run` 只校验和渲染到内存，不创建文件或目录；无效输入以非零退出，已有报告不被覆盖。正常执行只写显式指定的报告文件及其父目录。

打开 HTML 后检查：离线可读；候选与首选对应；现状/建议未挤成不可读长行；证据、验证和不确定性没有漏项。报告用原生折叠区显示详细证据，不需要 JavaScript。

## 来源与本仓取舍

参考 [Matt Pocock 的架构扫描 skill](https://github.com/mattpocock/skills/blob/c55ee46073ed923f86ce59a5eb3b6d895095d1b7/skills/engineering/improve-codebase-architecture/SKILL.md) 和 [codebase-design](https://github.com/mattpocock/skills/blob/c55ee46073ed923f86ce59a5eb3b6d895095d1b7/skills/engineering/codebase-design/SKILL.md)，固定提交为 `c55ee46073ed923f86ce59a5eb3b6d895095d1b7`，上游采用 [MIT 许可](https://github.com/mattpocock/skills/blob/c55ee46073ed923f86ce59a5eb3b6d895095d1b7/LICENSE)。本实现重新编写：保留范围选择、热点线索和现状/建议对照；使用项目产物约定、内联 CSS 与文本转义；后续设计、领域模型和 ADR 修改由用户当前请求决定。
