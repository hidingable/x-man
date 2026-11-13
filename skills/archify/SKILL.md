---
name: archify
description: "把系统、调用链、流程、状态和数据关系做成可探索的离线 HTML 图。支持架构图、时序图、ERD、架构变更对照和节点路径追踪；适合画架构图、把 Mermaid 做成交互图、生成可分享的技术说明页。"
license: MIT
compatibility: "Node.js >=18；原生图的完整 finalize 检查还需要 Chrome、Chromium 或 Edge。"
metadata:
  category: design
  tags: [architecture, diagrams, visualization, html]
  dependencies: []
  requires_context: []
  requires_task: prompt
  outputs:
    type: analysis
  version: "3.2.0"
  source: "https://github.com/tt-a1i/archify"
---

# archify

把用户描述或查证后的代码关系转成结构化 JSON，再用随包渲染器生成可点击节点、追踪上下游和路径的单文件 HTML。需要找到架构问题时用 `improve-codebase-architecture`；需要理解既有调用链及历史时用 `code-archaeology`。本 skill 负责图与交互展示，不把画图结果当作运行期事实或重构许可。

## 选择图与输入

| 用户要看什么 | 类型 | 示例 |
|---|---|---|
| 组件、服务、依赖与边界 | `architecture` | `examples/web-app.architecture.json` |
| 步骤、分支、审批与工具调用 | `workflow` | `examples/agent-tool-call.workflow.json` |
| 请求、返回与异步交互 | `sequence` | `examples/cache-miss-request.sequence.json` |
| 数据流向、处理与消费者 | `dataflow` | `examples/product-analytics.dataflow.json` |
| 状态、等待、重试与终止 | `lifecycle` | `examples/deployment-release.lifecycle.json` |
| 数据表、字段、键与关系 | `erd` | `examples/orders.erd.json` |
| 类、接口与类型关系 | `class` | `examples/payments.class.json` |
| 单父层级与模块树 | `tree` | `examples/payment-platform.tree.json` |
| 事件发生时间 | `timeline` | `examples/payment-incident.timeline.json` |
| 一次请求各段耗时与重叠 | `waterfall` | `examples/checkout-request.waterfall.json` |

真实代码库先读 `references/repository-authoring.md`，根据源码、配置与测试标注关系和证据；描述型图按用户提供的事实作图。日期与耗时缺乏日志依据时标为示意。Mermaid 输入保留拓扑与含义，再编写本包 JSON。

编写前读 `references/authoring-defaults.md`、对应示例和 `schemas/<type>.schema.json`，需要公共字段定义时读 `schemas/common.schema.json`。布局与候选修复按 [上游流程](UPSTREAM.md) 的 Native diagram authoring、Type router 和 Delivery；其中以下本地约定优先。

## 保存与生成

按 `.ai-configs/conventions.md` 的 analysis 产物规则确定主名与目录，沿用当前需求身份；用户指定路径时使用该路径。HTML、JSON 源和校验回执放在同一目录，伴随文件沿用主名。这里的 HTML 由 Archify 从 JSON 渲染，不再交给 html-view 重写。

从当前 skill 目录解析 `bin/archify.mjs` 的绝对路径；输入输出参数从工作目录解析，不要求切换到 skill 目录。候选内的 `meta.output` 必须是工作目录内的 POSIX 相对 HTML 路径，且解析后与目标一致；目标在工作目录外时，从目标目录运行并使用输入、CLI 和代码仓的绝对路径。

```sh
ARCHIFY_UPDATE_CHECK_DISABLED=1 node "$ARCHIFY_CLI" finalize "$TYPE" "$SOURCE_JSON" "$OUTPUT_HTML" --quality showcase --json
```

`ARCHIFY_CLI` 是当前 skill 的 CLI 绝对路径，其余变量是本次选定的类型与文件。代码证据图追加 `--repo-root "$REPO_ROOT"`；用户需要密集全字段图时可按上游约定使用 `standard`。参数及 `meta.quality_profile` 保持一致。

`finalize` 依次运行模型校验、原子交付、产物检查和原生图浏览器检查。读取退出码与完整结果；失败按 `references/delivery-contract.md` 修复，不能把生成 HTML 或部分检查通过当作全部通过。复用已有输出路径时按该参考分离不同候选的浏览器证据。自动化通过与人工视觉检查分别说明。

不需要 npm install。需要诊断环境时运行 `node "$ARCHIFY_CLI" doctor`；缺浏览器时说明未完成的检查，不绕过失败去声明完成。

## 按需能力

- 架构 Before/Delta/After 对照，用 `node "$ARCHIFY_CLI" compare architecture "$BASE_JSON" "$HEAD_JSON" "$OUTPUT_HTML" --json`，保留两份源及对照回执。输入示例为 `examples/checkout-platform.base.architecture.json` 和 `examples/checkout-platform.head.architecture.json`；这只对照已编写的图，不推断运行期影响。
- 需要搜索、聚焦、上下游、路径卡片、导出或演示模式，读 `references/viewer-runtime.md`。
- 用户要求一页说明或可分享的解释页，读 `references/explainer-authoring.md`，使用 `finalize explainer`；普通文字问答不默认生成页面。
- 用户要求预览时，按 `references/delivery-contract.md` 的 Optional opening 使用一次打开或本地 preview。

上游的默认 `.archify` 目录与全局 explainer 模式提示不在本仓启用；不因生成页面修改全局 agent 规则。更新由 xman 外部来源 manifest 管理，默认使用上述环境变量关闭运行时更新联网检查；用户明确要求检查上游更新时读 `references/update-awareness.md`。

## 交付与来源

用用户语言给出 HTML 的绝对路径链接和必要结论，说明示意数据、缺失证据与未通过的检查。Schema、布局和浏览器检查只验证图的结构与显示，不证明真实系统行为、影响面或合并安全。

来源固定为 [tt-a1i/archify v3.2.0](https://github.com/tt-a1i/archify/tree/v3.2.0/archify)，原始入口保留于 [UPSTREAM.md](UPSTREAM.md)，运行文件保持上游实现。许可证与字体、图标等第三方声明见 [LICENSE](LICENSE) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
