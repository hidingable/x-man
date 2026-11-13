# Portable Prompts

这些提示词目标是：

- 同一套 Apple 风格视觉与交互原则
- 可直接复制到 Cursor / Claude Code / Gemini
- 不依赖特定工具语法

---

## 1. 通用版

```text
Refactor this UI to follow an Apple-inspired visual and interaction system.

Goals:
- Make it feel calm, premium, layered, and continuous.
- Prefer continuity over spectacle.
- Preserve the product structure, but upgrade the visual hierarchy and interaction quality.

Visual direction:
- Use a clean, minimalist light theme with translucent white surfaces, soft borders, generous whitespace, and large rounded corners.
- Prefer system fonts: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "PingFang SC", sans-serif.
- Keep text contrast strong: dark primary text, slate secondary text, muted tertiary text.
- Use one restrained accent color, usually cool blue.
- Use soft shadows and subtle glassmorphism; avoid noisy gradients and harsh contrasts.

Motion direction:
- Use only subtle motion that clarifies hierarchy or state change.
- Animate opacity and transform only.
- Route transitions: animate only the main content area with fade + small translateY.
- In-page selection changes, tabs, and query-param updates must use local pane transitions, not full-page transitions.
- Refresh should preserve existing content and show a local refreshing state instead of blanking the page.
- Save success should use a small inline confirmation, not a disruptive modal or large alert block.
- Avoid large zooms, heavy blur transitions, parallax, spins, or decorative motion.

Motion tokens:
- fast: 140ms
- normal: 220ms
- slow: 320ms
- easing: cubic-bezier(0.22, 1, 0.36, 1)

Accessibility:
- Respect prefers-reduced-motion.
- In reduced motion mode, replace movement-heavy transitions with dissolve, highlight fade, or color shift.
- Keep visible focus states and stable hover feedback.

Engineering constraints:
- Keep the implementation simple and reusable.
- Prefer shared tokens, shared classes, and shared interaction primitives over page-specific hacks.
- Do not introduce unnecessary animation libraries unless the project truly benefits from them.

Before coding:
- identify route-level transitions
- identify pane-level transitions
- identify refresh states
- identify save feedback states

Then implement the motion system consistently across the UI.
```

---

## 2. 后台 / 控制台版

```text
Refactor this dashboard/admin UI into an Apple-inspired control surface.

Requirements:
- Keep the information density practical, but remove the traditional “bootstrap admin panel” feel.
- Use light mode by default with layered translucent cards, soft borders, and large rounded surfaces.
- The sidebar must stay visually stable while the main content area transitions.
- Route transitions should only happen when the pathname changes.
- Query-string-only changes, master-detail switches, tab switches, and list selections must only animate the affected pane.
- Loading should not blank the whole page if previous data exists.
- Use local refresh indicators, subtle sheen, or inline progress states.
- Save feedback should appear as inline notice and auto-dismiss on success.
- Avoid flashy motion, blur transitions, large slides, or unnecessary stagger reveals.

Deliverables:
1. Explain the current causes of flicker or abrupt transitions.
2. Propose route-level, pane-level, and micro-interaction motion layers.
3. Implement shared motion tokens and reduced-motion support.
4. Apply the system consistently across navigation, cards, forms, and detail panes.
```

---

## 3. 阅读页 / 内容页版

```text
Refactor this content page to feel like a premium Apple-style reading surface.

Requirements:
- Use a calm light theme with translucent white cards, restrained borders, soft shadows, and generous whitespace.
- Typography should use a system font stack with strong hierarchy and excellent readability.
- Keep prose contrast high and line length controlled.
- The page should feel layered and refined, not flashy.
- Motion must be subtle: fade + small vertical movement only.
- Switching between content records should preserve context and avoid full-page flicker.
- Refreshing content should keep the previous content visible and use a local updating state.
- Respect prefers-reduced-motion.
```

---

## 4. Cursor 用法建议

把上面的任意 prompt 放进：

- Chat
- Composer
- `.cursor/rules` 中的风格规则

如果你在 Cursor 里做长期复用，推荐把“视觉规则 + motion 规则 + accessibility 规则”拆成单独 rule 文件。

---

## 5. Claude Code 用法建议

可直接在对话里引用这个 skill 的核心目标：

```text
Use an Apple-inspired visual and motion system for this refactor. Prioritize continuity over spectacle, local pane transitions over full-page motion, preserved data during refresh, and inline save feedback.
```

若 Claude Code 支持本地 skill/command 目录，也可直接复用本 skill 仓库内容。

---

## 6. Gemini 用法建议

Gemini 没有统一的 skill 目录标准时，直接复制“通用版”或“后台 / 控制台版” prompt。

建议在 Gemini 里额外补一句：

```text
Do not just describe the design. Update the implementation strategy and interaction model concretely.
```
