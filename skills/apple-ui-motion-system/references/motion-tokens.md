# Motion Tokens

这份参考用于把 Apple 风格的视觉与交互规则落成工程可复用的 token、状态语义和实现边界。

目标不是做“动画库规范”，而是保证：

- 视觉节奏统一
- 路由切换与局部切换不混用
- 刷新和保存反馈可复用
- Cursor / Claude Code / Gemini 都能读懂并执行

---

## 1. 推荐 token

```text
--motion-fast: 140ms
--motion-normal: 220ms
--motion-slow: 320ms

--ease-apple: cubic-bezier(0.22, 1, 0.36, 1)
--ease-fade: cubic-bezier(0.2, 0.8, 0.2, 1)

--radius-control: 16px
--radius-card: 24px
--radius-panel: 28px
--radius-hero: 32px

--shadow-soft: 0 10px 30px rgba(15, 23, 42, 0.08)
--shadow-float: 0 20px 50px rgba(15, 23, 42, 0.12)

--surface-glass: rgba(255, 255, 255, 0.72)
--surface-card: rgba(255, 255, 255, 0.84)
--border-subtle: rgba(148, 163, 184, 0.18)
--text-primary: #0f172a
--text-secondary: #475569
--text-tertiary: #64748b
--accent: #2563eb
```

---

## 2. 过渡层级

### 路由级

只在 `pathname` 变化时触发。

适用：

- 左侧导航切页
- 顶部主导航切页
- 真正进入新页面

推荐：

- enter: `opacity 0 -> 1`, `translateY(8px) -> 0`
- exit: `opacity 1 -> 0`, `translateY(0) -> -4px`
- 时长：`220ms / 160ms`

禁止：

- `search` / `hash` / tab / filter 变化触发整页转场
- 整个 app shell 一起 fade

### 面板级

用于同一路径内的 detail replace。

适用：

- `/runs?batchId=...`
- master-detail 切换
- tab 内容切换
- drawer / side pane / inspector 替换

推荐：

- `opacity + translateY(6px)`
- 只作用于被替换的 pane
- 保持容器最小高度，避免布局跳变

### 微交互级

适用：

- 按钮 hover / press
- list item selected
- inline notice
- badge state
- refresh sheen

推荐：

- hover: `scale(1.01)` 到 `scale(1.02)`
- press: `scale(0.96)` 到 `scale(0.98)`
- focus: 明确 outline 或 ring，不靠阴影代替

---

## 3. 数据状态策略

### loading

- 首次进入时才用 skeleton 或空态 loading
- 不要反复用整块 loading 覆盖已有内容

### refreshing

- 保留旧数据
- 用局部 `refresh-indicator`、sheen、弱 pulse
- 区分 `isLoading` 和 `isRefreshing`

### saving

- 表单提交中：按钮 loading 或局部禁用
- 成功：inline notice，自动消隐
- 失败：就近提示，避免整页红块警报

---

## 4. reduced motion

检测：

- `prefers-reduced-motion: reduce`

降级规则：

- 保留淡入淡出
- 去掉明显位移、缩放、持续装饰动画
- 不做 blur、zoom、parallax
- 仍保留 focus、selected、success 的状态反馈

---

## 5. 工程实现建议

### React / SPA

- 路由级：在主内容区外包一层 transition shell
- 页面内：keyed pane + 轻量 class 切换
- 数据：支持 `keepPreviousData` / `isRefreshing`

### CSS

- 只动画 `opacity`、`transform`、少量颜色属性
- 避免 `width`、`height`、`top`、`left`
- 把 token 放到全局 theme 层，不要散落页面内联样式

### 组件建议

- `PageTransitionShell`
- `SwitchPane`
- `InlineNotice`
- `RefreshIndicator`
- `PanelSkeleton`
- `usePrefersReducedMotion`

---

## 6. 跨工具复用建议

### Cursor

- 这份文件可拆成 `.cursor/rules` 中的视觉规则和 motion 规则

### Claude Code

- 这份文件适合作为 skill 附加参考
- 优先让模型先分析“闪烁根因”，再要求动手实现

### Gemini

- 直接复制 token 和层级规则最稳定
- 额外强调“不要只描述设计，要输出实现策略和状态策略”
