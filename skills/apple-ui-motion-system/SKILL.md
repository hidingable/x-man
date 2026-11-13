---
name: apple-ui-motion-system
disable-model-invocation: false
description: "Apple 风格视觉与交互系统 skill。用于将 Web UI 重构为克制、连续、分层、低噪音的 Apple 风格体验，特别适合页面改版、控制台/后台、阅读页、表单、导航、加载态、刷新态、转场与 motion polish。也适用于为 Cursor / Claude Code / Gemini 生成可复用提示词。"
metadata:
  category: design
  tags: [design, animation, motion, apple]
  dependencies: []
---

# Apple UI Motion System

## 适用场景

当用户提出以下需求时使用：

- 做成 Apple 风格 / iOS 风格 / HIG 风格
- 页面切换太硬、太闪、太“后台味”
- 需要统一视觉和交互节奏
- 需要优化导航、卡片、表单、阅读页、加载态、刷新态、保存反馈
- 需要一套可迁移到 Cursor / Claude Code / Gemini 的稳定提示词

## 核心目标

不是“模仿苹果截图”。

而是让界面具备这些特征：

- **克制**：少而准，不炫技
- **连续**：切换有上下文，不突兀
- **分层**：页面层、面板层、控件层边界清晰
- **稳定**：避免闪烁、跳变、整块重绘感
- **精致**：圆角、阴影、边框、文字层级都统一

## 强制原则

### 1. 先稳数据，再做动画

如果页面切换会先清空内容再加载，优先改成：

- 保留旧数据刷新
- 局部 loading
- skeleton 或 local refresh indicator

不要直接用动画掩盖闪烁。

### 2. 先区分三种过渡层级

开始改动前，必须把交互拆成三层：

1. **路由级**
   - 只在 `pathname` 变化时触发
   - 只动画主内容区，不动画整个 App shell
2. **面板级**
   - 用于 tabs、list-detail、drawer、query 参数切换
   - 同一路径内只做局部 pane 动画
3. **微交互级**
   - hover、press、focus、save success、badge state

### 3. query 参数切换禁止触发整页转场

像这些：

- `/runs?batchId=...`
- `/items?itemId=...`
- tab / filter / local pane selection

都应该走**局部 detail pane 动画**，不应走整页 route transition。

### 4. 支持 reduced motion

必须支持 `prefers-reduced-motion`。

降级规则：

- 去掉纵向移动和缩放强调
- 去掉持续性装饰动画
- 保留轻微 dissolve / highlight fade / color shift
- 不要因为 reduced motion 就完全失去层级反馈

## 视觉规则

- 默认优先浅色界面，除非项目已明确深色体系
- 字体优先系统栈：
  - `-apple-system`
  - `BlinkMacSystemFont`
  - `"SF Pro Text"`
  - `"SF Pro Display"`
  - `"PingFang SC"`
  - `sans-serif`
- 表面用半透明白底、轻边框、软阴影
- 圆角统一到 3 档：`24 / 28 / 32`
- 主文案深色，正文不要发灰发飘
- 控制台页面也要大留白，不要做成紧凑传统后台
- 使用单一克制强调色，优先冷静蓝

## Motion 规则

- 只优先动画 `opacity` / `transform` / 少量 `background-color`、`border-color`
- 不要用 `width` / `height` / `top` / `left` 做主动画
- 不要做大 slide、强 zoom、spin、blur-in/out、parallax
- route transition 要轻：fade + 小幅 `translateY`
- detail pane replace 要局部：fade + 轻微位移
- refresh 态要保留旧内容：局部 sheen 或 pulse
- save success 用 inline notice，不要大块 alert 或 modal

## 推荐 motion token

默认值：

```text
--motion-fast: 140ms
--motion-normal: 220ms
--motion-slow: 320ms
--ease-apple: cubic-bezier(0.22, 1, 0.36, 1)
--ease-fade: cubic-bezier(0.2, 0.8, 0.2, 1)
```

推荐模式：

- hover: `scale(1.01)` 到 `scale(1.02)` 上限
- press: `scale(0.96)` 到 `scale(0.98)`
- route enter: `opacity 0 -> 1`, `translateY(8px) -> 0`
- route exit: `opacity 1 -> 0`, `translateY(0) -> -4px`
- pane switch: `opacity + translateY(6px)`，只作用于 pane
- refresh: pulse 或 sheen，不能靠整块 spinner 替代

## 输出要求

当你用这个 skill 产出方案或直接改代码时，输出必须覆盖：

1. 当前闪烁 / 生硬切换的根因
2. 路由级、面板级、微交互级的拆分
3. loading / refreshing / saving 三种状态策略
4. reduced motion 支持
5. 共享 token / 共享类 / 共享组件建议

## 执行顺序

1. 读当前项目的路由和页面结构
2. 找出整页切换、局部切换、刷新态、保存态
3. 先修数据流闪烁
4. 再加 route transition
5. 再加 pane transition
6. 再加 inline notice / refresh indicator / local sheen
7. 最后校验 reduced motion 和 focus states

## 禁止事项

- 不要为了“更像 Apple”而全站堆动画
- 不要在同一路径 query 参数切换时动画整页
- 不要把所有列表项都 stagger reveal
- 不要用大块 loading 页面替换已有内容
- 不要为了一次动画引入重型动画库，除非项目复杂度真的需要

## 何时读取附加参考

- 需要跨模型复用提示词时：读 [references/portable-prompts.md](references/portable-prompts.md)
- 需要统一 token 或对照实现时：读 [references/motion-tokens.md](references/motion-tokens.md)

## 推荐结论

- **一次性需求**：直接使用 `portable-prompts.md` 里的提示词
- **跨项目长期复用**：直接调用本 skill，并按当前项目结构落地
