---
name: ascii-card
disable-model-invocation: false
description: 生成中英文混排也能严格对齐的 ASCII/Unicode 卡片图和 UI 线框图。当用户要求“画个卡片示意图”“ASCII 线框图”“用文字画弹窗/抽屉/列表”“照截图画纯文本框图”，或要把界面草图写进 Markdown、PRD、代码注释、评审记录时使用。不要用于时序图、流程图、组件关系图（使用 PlantUML/Mermaid）。Use for CJK-aligned text UI wireframes, not semantic diagrams.
compatibility: Requires Python 3.9+. wcwidth and PyYAML are optional enhancements; JSON input works with the Python standard library.
metadata:
  category: docs
  tags: [ascii, wireframe, diagram, cjk, alignment]
  dependencies: []
---

# ASCII Card

把卡片、弹窗、抽屉、列表项画成纯文本框图，贴进 Markdown、PRD、代码注释、评审记录或聊天。

路由：时序、流程、组件关系等语义图用 PlantUML 或 Mermaid。

中文在等宽字体下占 2 列，`len()` 按字符数算，手敲空格的中英混排框图右边框必然错位。所以图一律由 `scripts/render_card.py` 按显示列宽生成，不手写、不手改空格。

`<skill-dir>` 指本 SKILL.md 所在目录，从已加载 skill 的真实路径解析。

## 步骤

1. 按用户描述在 scratchpad 目录写一个 JSON（格式见下）。
2. 运行 `python3 <skill-dir>/scripts/render_card.py <file> --check`。完成条件：`[check]` 行报告所有行等宽、退出码为 0。报错时按提示改 JSON 重跑。
3. 把输出包在 ``` 代码块里交给用户（不在代码块里、换成非等宽字体都会散），附上 `[check]` 那行作为对齐证据。
4. 用户要改文案或布局时改 JSON 重跑。

其他参数：`--width N` 覆盖总宽，`--style ascii|unicode|rounded|double` 覆盖边框，`--out FILE` 写文件，输入写 `-` 读 stdin。YAML 输入需要 PyYAML。

不用装依赖：没有 wcwidth 时脚本用标准库计算宽度，CJK 和 ASCII 的结果与 wcwidth 一致，`[check]` 行会写明用的哪个引擎。文案含 emoji 时宽度在各终端不一致，用 `uv run <skill-dir>/scripts/render_card.py …` 自动带上 wcwidth，并尽量少用 emoji。

## 输入格式

```json
{
  "width": 72,
  "rows": [
    { "type": "text", "text": "入职红线提醒" },
    { "type": "divider" },
    { "type": "row", "text": "红线资料名称", "buttons": ["查看"] },
    { "type": "buttons", "buttons": ["按建议终止入职", "继续入职"], "align": "between" }
  ]
}
```

`width` 是含左右边框的**总宽**（显示列数），默认 `"auto"` 按最宽行计算。

| type | 用途 | 字段 |
|---|---|---|
| `text` | 文本行 | `text`、`align`（left/center/right）、`wrap` |
| `row` | 左侧文本 + 右侧按钮 | `text`、`buttons`、`wrap` |
| `buttons` | 纯按钮行 | `buttons`、`align`（between/even/left/right/center） |
| `pre` | 原样保留空格和换行的多行文本 | `text` |
| `divider` | 分隔线 | 无 |
| `blank` | 空行 | 无 |

用到 `padding`、`gap`、`max_width`、自定义边框 `chars`、行类型别名、截断，或要查折行和报错规则、Python API 时，读 `references/format.md`。`examples/` 里有纯中文、中英混排、折行截断、Unicode 边框各一份，可以直接改。
