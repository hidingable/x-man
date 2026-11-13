# 输入格式参考

需要卡片级字段、按钮分布、自定义边框或折行细节时读本文件。完整示例见 `examples/`。

## 卡片级字段

| 字段 | 默认 | 说明 |
|---|---|---|
| `width` | `"auto"` | 卡片**总宽**（显示列数，含左右边框）。`"auto"` 按最宽行自动算 |
| `max_width` | `100` | 仅 `width: "auto"` 时生效，自动宽度的上限，超过则折行 |
| `padding` | `1` | 边框与内容之间的左右内边距（列） |
| `gap` | `2` | 内容与按钮之间、按钮与按钮之间的最小间隔（列） |
| `wrap` | `true` | 内容超宽时折行；`false` 则截断并补 `…`。可在单行上覆盖 |
| `align` | `"left"` | `text` 行的默认对齐：`left` / `center` / `right` |
| `button_align` | `"between"` | `buttons` 行的默认分布 |
| `style` | `"ascii"` | 边框预设：`ascii` / `unicode` / `rounded` / `double` |
| `chars` | 无 | 自定义边框，每个字形的显示宽度必须为 1 |

`chars` 字段：`top_left`、`top_right`、`bottom_left`、`bottom_right`、`horizontal`、`vertical`、`left_junction`、`right_junction`。旧字段 `corner`、`h`、`v` 仍可用，但会让顶角、底角和分隔连接符混用，新配置写完整字段。

## 行类型别名

| type | 别名 |
|---|---|
| `text` | `title` `line` |
| `pre` | `raw` `preformatted` |
| `row` | `item` `text_button` |
| `buttons` | `actions` `button` |
| `divider` | `sep` `hr` |
| `blank` | `empty` |

`buttons` 传字符串数组或单个字符串；文案自动包 `[]`，已带方括号的不重复包。

## 按钮行的 `align`

| 值 | 效果 |
|---|---|
| `between` | 首尾贴两端，中间空隙均分（默认） |
| `even` | 含左右外边距在内均匀分布 |
| `left` / `right` / `center` | 按钮块整体靠左 / 靠右 / 居中，按钮间隔 `gap` 列 |

## 折行与报错

- 按显示宽度折行，汉字不会被劈开；拉丁单词尽量整体保留，单词本身超宽才硬切。
- `text` / `row` 里的显式换行先作为硬换行保留再折行；`pre` 原样保留空格，不折行，超宽直接报错。
- `row` 折行时按钮固定在首行右侧，续行占满内容区。
- 按钮放不下内容区时退出码为 2，并提示所需列数。
- Tab、ANSI 转义、其他控制字符，以及未知字段、非法对齐值、负数间距、无效宽度、多列宽边框字符，都在渲染前报错并指出字段位置。

## Python API

```python
import sys
sys.path.insert(0, "<skill-dir>/scripts")
from render_card import Card, render

print(render({"width": 72, "rows": [...]}))
print(Card(width="auto")
      .text("待办 Todo · 3 项", align="center")
      .divider()
      .row("社保补缴 2026-08", buttons=["处理"])
      .buttons(["全部忽略", "批量处理"], align="between")
      .render())
```
