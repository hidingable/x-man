#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["wcwidth>=0.2"]
# ///
"""对齐工整的 ASCII 卡片图渲染器。

核心问题：中文/日文/韩文等全角字符在等宽字体下占 2 列，但 str 的 len() 按
字符数算。只按字符数补空格，中英混排时右边框必然错位。本模块用
wcwidth（若可用）或标准库 unicodedata 的等效实现计算每个字符的**显示列宽**，
保证每一行输出的显示宽度完全一致。

命令行：
    uv run render_card.py card.json            # 有 uv：自动装 wcwidth，不碰现有环境
    python3 render_card.py card.json           # 没 uv：走 unicodedata 降级实现
    python3 render_card.py card.yaml           # 需要 pyyaml
    cat card.json | python3 render_card.py -
    python3 render_card.py card.json --width 80 --check

顶部的 PEP 723 内联依赖声明只对 uv / pipx 之类的工具有意义；普通 python 把它当注释
忽略，因此同一个脚本两条路径都能跑。--check 会打印当前用的是哪个宽度引擎。

Python API：
    from render_card import Card, render, disp_width

    c = Card(width=72)
    c.text("入职红线提醒")
    c.divider()
    c.row("红线资料名称", buttons=["查看"])
    c.divider()
    c.buttons(["按建议终止入职", "继续入职"], align="between")
    print(c.render())
"""

from __future__ import annotations  # noqa: F407

import argparse
import json
import sys
import unicodedata

__all__ = ["Card", "render", "disp_width", "CardError", "BOX_STYLES"]


class CardError(ValueError):
    """卡片描述有问题（宽度不够、行类型未知等）。"""


# --------------------------------------------------------------------------
# 显示宽度
# --------------------------------------------------------------------------

try:  # 优先用 wcwidth，对 emoji / 组合字符更准
    from wcwidth import wcswidth as _wcswidth, wcwidth as _wcwidth

    HAVE_WCWIDTH = True
except ImportError:  # 降级到标准库等效实现
    _wcswidth = _wcwidth = None
    HAVE_WCWIDTH = False


def _char_width_fallback(ch: str) -> int:
    """unicodedata 版单字符显示宽度。"""
    if unicodedata.combining(ch):
        return 0
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf"):
        return 0
    if cat == "Cc":  # 宽度 API 按 0 处理；卡片渲染入口会拒绝控制字符
        return 0
    if unicodedata.east_asian_width(ch) in ("F", "W"):
        return 2
    return 1


def disp_width(text: str) -> int:
    """字符串在等宽终端下占用的列数。"""
    if HAVE_WCWIDTH:
        w = _wcswidth(text)
        if w >= 0:
            return w
        # wcswidth 遇到控制字符返回 -1，逐字符兜底
        total = 0
        for ch in text:
            cw = _wcwidth(ch)
            total += cw if cw and cw > 0 else 0
        return total
    return sum(_char_width_fallback(ch) for ch in text)


def _char_width(ch: str) -> int:
    if HAVE_WCWIDTH:
        cw = _wcwidth(ch)
        return cw if cw and cw > 0 else 0
    return _char_width_fallback(ch)


def _graphemes(text: str) -> list[str]:
    """按用户可见字符做轻量分组，避免截断 ZWJ/组合字符/旗帜。"""
    clusters: list[str] = []
    current = ""
    regional_count = 0
    for ch in text:
        code = ord(ch)
        is_variation = 0xFE00 <= code <= 0xFE0F
        is_modifier = 0x1F3FB <= code <= 0x1F3FF
        is_regional = 0x1F1E6 <= code <= 0x1F1FF
        joins_current = (
            bool(current)
            and (
                unicodedata.combining(ch)
                or is_variation
                or is_modifier
                or ch == "\u200d"
                or current.endswith("\u200d")
                or (is_regional and regional_count == 1)
            )
        )
        if current and not joins_current:
            clusters.append(current)
            current = ""
            regional_count = 0
        current += ch
        if is_regional:
            regional_count += 1
        elif ch != "\u200d":
            regional_count = 0
    if current:
        clusters.append(current)
    return clusters


def _pad(text: str, width: int, align: str = "left") -> str:
    """把 text 按显示宽度补到 width 列。"""
    fill = width - disp_width(text)
    if fill <= 0:
        return text
    if align == "right":
        return " " * fill + text
    if align == "center":
        left = fill // 2
        return " " * left + text + " " * (fill - left)
    return text + " " * fill


# --------------------------------------------------------------------------
# 按显示宽度折行
# --------------------------------------------------------------------------

_LATIN = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "_-+.@#$%/'’:?#&=~"
)


def _tokenize(text: str) -> list[str]:
    """切成可断行的最小单元：连续的拉丁词/数字算一个整体，其余逐字符。"""
    tokens: list[str] = []
    buf = ""
    for cluster in _graphemes(text):
        if len(cluster) == 1 and cluster in _LATIN:
            buf += cluster
        else:
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(cluster)
    if buf:
        tokens.append(buf)
    return tokens


def _truncate(text: str, width: int, ellipsis: str = "…") -> str:
    if disp_width(text) <= width:
        return text
    ell_w = disp_width(ellipsis)
    budget = max(0, width - ell_w)
    out, used = "", 0
    for cluster in _graphemes(text):
        cw = disp_width(cluster)
        if used + cw > budget:
            break
        out += cluster
        used += cw
    return out + ellipsis


def _wrap(text: str, widths: list[int]) -> list[str]:
    """按显示宽度折行。widths[i] 是第 i 行可用列数，超出后沿用最后一个值。

    不会把一个汉字劈成两半；拉丁单词尽量整体保留，单词本身超长才硬切。
    """
    if not text:
        return [""]

    def width_at(i: int) -> int:
        return widths[i] if i < len(widths) else widths[-1]

    lines: list[str] = []
    cur, cur_w = "", 0
    limit = width_at(0)

    for token in _tokenize(text):
        tw = disp_width(token)
        if token == " " and not cur:
            continue  # 行首空格丢掉
        if cur_w + tw <= limit:
            cur += token
            cur_w += tw
            continue
        # 放不下：先收掉当前行
        if cur:
            lines.append(cur.rstrip())
            cur, cur_w = "", 0
            limit = width_at(len(lines))
            if token == " ":
                continue
        # 单个 token 本身就超宽 → 硬切
        while disp_width(token) > limit:
            part, part_w = "", 0
            for cluster in _graphemes(token):
                cw = disp_width(cluster)
                if part_w + cw > limit:
                    break
                part += cluster
                part_w += cw
            if not part:  # limit 小到放不下一个字符，防死循环
                raise CardError(f"卡片内宽 {limit} 列太窄，放不下字符 {token[0]!r}")
            lines.append(part)
            token = token[len(part):]
            limit = width_at(len(lines))
        cur, cur_w = token, disp_width(token)

    lines.append(cur.rstrip())
    return lines or [""]


def _widths_from(widths: list[int], line_index: int) -> list[int]:
    if line_index < len(widths):
        return widths[line_index:]
    return [widths[-1]]


def _wrap_multiline(text: str, widths: list[int]) -> list[str]:
    """保留显式换行，再对每个逻辑行折行。"""
    lines: list[str] = []
    for logical_line in text.split("\n"):
        lines.extend(_wrap(logical_line, _widths_from(widths, len(lines))))
    return lines


def _truncate_multiline(text: str, widths: list[int]) -> list[str]:
    lines: list[str] = []
    for logical_line in text.split("\n"):
        available = _widths_from(widths, len(lines))[0]
        lines.append(_truncate(logical_line, available))
    return lines


# --------------------------------------------------------------------------
# 行模型
# --------------------------------------------------------------------------

_ROW_ALIASES = {
    "text": "text", "title": "text", "line": "text",
    "pre": "pre", "raw": "pre", "preformatted": "pre",
    "row": "row", "item": "row", "text_button": "row",
    "buttons": "buttons", "actions": "buttons", "button": "buttons",
    "divider": "divider", "sep": "divider", "separator": "divider", "hr": "divider",
    "blank": "blank", "empty": "blank", "spacer": "blank",
}

_TEXT_ALIGNS = {"left", "right", "center"}
_BUTTON_ALIGNS = _TEXT_ALIGNS | {"between", "even"}
_CARD_FIELDS = {
    "width", "padding", "gap", "wrap", "align", "button_align",
    "max_width", "style", "chars", "rows",
}
_ROW_FIELDS = {
    "text": {"type", "text", "align", "wrap"},
    "pre": {"type", "text", "align"},
    "row": {"type", "text", "buttons", "button", "align", "wrap"},
    "buttons": {"type", "buttons", "button", "align"},
    "divider": {"type"},
    "blank": {"type"},
}

BOX_STYLES = {
    "ascii": {
        "top_left": "+", "top_right": "+",
        "bottom_left": "+", "bottom_right": "+",
        "horizontal": "-", "vertical": "|",
        "left_junction": "+", "right_junction": "+",
    },
    "unicode": {
        "top_left": "┌", "top_right": "┐",
        "bottom_left": "└", "bottom_right": "┘",
        "horizontal": "─", "vertical": "│",
        "left_junction": "├", "right_junction": "┤",
    },
    "rounded": {
        "top_left": "╭", "top_right": "╮",
        "bottom_left": "╰", "bottom_right": "╯",
        "horizontal": "─", "vertical": "│",
        "left_junction": "├", "right_junction": "┤",
    },
    "double": {
        "top_left": "╔", "top_right": "╗",
        "bottom_left": "╚", "bottom_right": "╝",
        "horizontal": "═", "vertical": "║",
        "left_junction": "╠", "right_junction": "╣",
    },
}
_BOX_KEYS = set(BOX_STYLES["ascii"])
_LEGACY_BOX_KEYS = {"corner", "h", "v"}


def _clean_text(value, path: str, allow_newline: bool = True) -> str:
    if not isinstance(value, str):
        raise CardError(f"{path} 必须是字符串")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    for ch in value:
        if ch == "\n" and allow_newline:
            continue
        if unicodedata.category(ch) in {"Cc", "Zl", "Zp"}:
            raise CardError(
                f"{path} 含不支持的控制字符 U+{ord(ch):04X}；"
                "只允许普通文本和显式换行"
            )
        if ch == "\n":
            raise CardError(f"{path} 不允许换行")
    return value


def _validate_int(name: str, value, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CardError(f"{name} 必须是整数")
    if value < minimum:
        raise CardError(f"{name} 不能小于 {minimum}")
    return value


def _resolve_chars(style: str, chars: dict | None) -> dict[str, str]:
    if style not in BOX_STYLES:
        raise CardError(f"style 必须是：{' / '.join(BOX_STYLES)}")
    if chars is not None and not isinstance(chars, dict):
        raise CardError("chars 必须是对象")

    resolved = dict(BOX_STYLES[style])
    custom = dict(chars or {})
    unknown = set(custom) - _BOX_KEYS - _LEGACY_BOX_KEYS
    if unknown:
        raise CardError(f"chars 含未知字段：{', '.join(sorted(unknown))}")

    if "corner" in custom:
        for key in (
            "top_left", "top_right", "bottom_left", "bottom_right",
            "left_junction", "right_junction",
        ):
            resolved[key] = custom["corner"]
    if "h" in custom:
        resolved["horizontal"] = custom["h"]
    if "v" in custom:
        resolved["vertical"] = custom["v"]
    for key in _BOX_KEYS:
        if key in custom:
            resolved[key] = custom[key]

    for key, glyph in resolved.items():
        glyph = _clean_text(glyph, f"chars.{key}", allow_newline=False)
        if disp_width(glyph) != 1:
            raise CardError(
                f"chars.{key} 的显示宽度必须为 1，当前为 {disp_width(glyph)}"
            )
        resolved[key] = glyph
    return resolved


def _validated_buttons(row: dict, path: str) -> list[str]:
    if "buttons" in row and "button" in row:
        raise CardError(f"{path} 不能同时提供 button 和 buttons")
    raw = row.get("buttons", row.get("button"))
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise CardError(f"{path}.buttons 必须是字符串或字符串数组")
    return [
        _clean_text(label, f"{path}.buttons[{index}]", allow_newline=False)
        for index, label in enumerate(raw)
    ]


def _btn(label: str) -> str:
    label = str(label)
    if label.startswith("[") and label.endswith("]"):
        return label
    return f"[{label}]"


def _btns(row: dict) -> list[str]:
    raw = row.get("buttons")
    if raw is None:
        raw = row.get("button")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    return [_btn(b) for b in raw]


def _join_buttons(buttons: list[str], area: int, align: str, gap: int) -> str:
    """把一组按钮排进 area 列。"""
    if not buttons:
        return ""
    total = sum(disp_width(b) for b in buttons)
    n = len(buttons)

    if n == 1:
        if align in ("between", "even"):
            align = "left" if align == "between" else "center"
        return _pad(buttons[0], area, align)

    min_needed = total + gap * (n - 1)
    if min_needed > area:
        raise CardError(
            f"按钮行放不下：需要至少 {min_needed} 列，当前内容区只有 {area} 列。"
            f"请调大 width 或缩短按钮文案 {[b for b in buttons]}"
        )

    if align == "between":
        free = area - total
        slots = n - 1
        base, extra = divmod(free, slots)
        parts = [buttons[0]]
        for i, b in enumerate(buttons[1:]):
            parts.append(" " * (base + (1 if i < extra else 0)))
            parts.append(b)
        return "".join(parts)

    if align == "even":
        free = area - total
        slots = n + 1
        base, extra = divmod(free, slots)
        parts = []
        for i, b in enumerate(buttons):
            parts.append(" " * (base + (1 if i < extra else 0)))
            parts.append(b)
        parts.append(" " * (base + (1 if n < extra else 0)))
        return _pad("".join(parts), area, "left")

    block = (" " * gap).join(buttons)
    return _pad(block, area, align if align in ("left", "right", "center") else "left")


# --------------------------------------------------------------------------
# 卡片
# --------------------------------------------------------------------------

DEFAULTS = {
    "width": "auto",
    "padding": 1,
    "gap": 2,
    "wrap": True,
    "align": "left",
    "button_align": "between",
    "max_width": 100,
    "style": "ascii",
}


class Card:
    def __init__(
        self,
        width="auto",
        padding: int = 1,
        gap: int = 2,
        wrap: bool = True,
        align: str = "left",
        button_align: str = "between",
        max_width: int = DEFAULTS["max_width"],
        style: str = DEFAULTS["style"],
        chars: dict | None = None,
        rows: list | None = None,
    ):
        self.width = width
        self.padding = padding
        self.gap = gap
        self.wrap = wrap
        self.align = align
        self.button_align = button_align
        self.max_width = max_width
        self.style = style
        self.chars = chars
        self.rows: list[dict] = list(rows or [])

    # -- 链式 API ---------------------------------------------------------
    def text(self, text: str, align: str | None = None, **kw) -> "Card":
        self.rows.append({"type": "text", "text": text, "align": align, **kw})
        return self

    def row(self, text: str, buttons=None, **kw) -> "Card":
        self.rows.append({"type": "row", "text": text, "buttons": buttons, **kw})
        return self

    def buttons(self, buttons, align: str | None = None, **kw) -> "Card":
        self.rows.append({"type": "buttons", "buttons": buttons, "align": align, **kw})
        return self

    def pre(self, text: str, align: str | None = None, **kw) -> "Card":
        self.rows.append({"type": "pre", "text": text, "align": align, **kw})
        return self

    def divider(self) -> "Card":
        self.rows.append({"type": "divider"})
        return self

    def blank(self) -> "Card":
        self.rows.append({"type": "blank"})
        return self

    # -- 渲染 -------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "Card":
        if not isinstance(data, dict):
            raise CardError("卡片描述必须是一个对象（dict）")
        unknown = set(data) - _CARD_FIELDS
        if unknown:
            raise CardError(f"卡片描述含未知字段：{', '.join(sorted(unknown))}")
        rows = data.get("rows")
        if rows is None:
            raise CardError("卡片描述缺少 rows 字段")
        if not isinstance(rows, list):
            raise CardError("rows 必须是数组")
        kwargs = {k: data[k] for k in DEFAULTS if k in data}
        return cls(chars=data.get("chars"), rows=rows, **kwargs)

    def _validate(self) -> None:
        if not (
            self.width == "auto"
            or (
                isinstance(self.width, int)
                and not isinstance(self.width, bool)
            )
        ):
            raise CardError('width 必须是正整数或 "auto"')
        self.padding = _validate_int("padding", self.padding, 0)
        self.gap = _validate_int("gap", self.gap, 0)
        self.max_width = _validate_int("max_width", self.max_width, 1)
        if not isinstance(self.wrap, bool):
            raise CardError("wrap 必须是布尔值")
        if self.align not in _TEXT_ALIGNS:
            raise CardError("align 必须是 left / center / right")
        if self.button_align not in _BUTTON_ALIGNS:
            raise CardError("button_align 必须是 left / center / right / between / even")
        if not isinstance(self.style, str):
            raise CardError("style 必须是字符串")
        self.chars = _resolve_chars(self.style, self.chars)
        self.rows = self._validated_rows()

        min_total = 2 + 2 * self.padding + 1
        if isinstance(self.width, int) and self.width < min_total:
            raise CardError(f"width={self.width} 太小，至少需要 {min_total}")
        if self.width == "auto" and self.max_width < min_total:
            raise CardError(f"max_width={self.max_width} 太小，至少需要 {min_total}")

    def _validated_rows(self) -> list[dict]:
        if not isinstance(self.rows, list):
            raise CardError("rows 必须是数组")
        validated: list[dict] = []
        for index, original in enumerate(self.rows):
            path = f"rows[{index}]"
            if not isinstance(original, dict):
                raise CardError(f"{path} 必须是对象")
            row = dict(original)
            raw_type = row.get("type", "text")
            if not isinstance(raw_type, str):
                raise CardError(f"{path}.type 必须是字符串")
            row_type = self._row_type(row)
            unknown = set(row) - _ROW_FIELDS[row_type]
            if unknown:
                raise CardError(
                    f"{path} 含未知字段：{', '.join(sorted(unknown))}"
                )
            row["type"] = row_type

            if row_type in {"text", "pre", "row"}:
                row["text"] = _clean_text(row.get("text", ""), f"{path}.text")
            if row_type in {"row", "buttons"}:
                row["buttons"] = _validated_buttons(row, path)
                row.pop("button", None)
            if "wrap" in row and not isinstance(row["wrap"], bool):
                raise CardError(f"{path}.wrap 必须是布尔值")
            if "align" in row and row["align"] is not None:
                allowed = _BUTTON_ALIGNS if row_type == "buttons" else _TEXT_ALIGNS
                if row["align"] not in allowed:
                    choices = " / ".join(sorted(allowed))
                    raise CardError(f"{path}.align 必须是 {choices}")
            validated.append(row)
        return validated

    def _row_type(self, row: dict) -> str:
        t = str(row.get("type", "text")).lower()
        if t not in _ROW_ALIASES:
            raise CardError(
                f"未知的行类型 {t!r}，可用：text / pre / row / buttons / divider / blank"
            )
        return _ROW_ALIASES[t]

    def _natural_width(self, row: dict) -> int:
        """该行不折行时需要的内容区列数。"""
        t = self._row_type(row)
        if t in ("divider", "blank"):
            return 0
        if t in ("text", "pre"):
            return max(disp_width(line) for line in row.get("text", "").split("\n"))
        if t == "row":
            btns = _btns(row)
            logical_lines = row.get("text", "").split("\n")
            w = disp_width(logical_lines[0])
            if btns:
                w += self.gap + sum(disp_width(b) for b in btns) + self.gap * (len(btns) - 1)
            return max([w] + [disp_width(line) for line in logical_lines[1:]])
        btns = _btns(row)
        if not btns:
            return 0
        return sum(disp_width(b) for b in btns) + self.gap * (len(btns) - 1)

    def _resolve_width(self) -> int:
        """返回卡片总宽（含左右边框）。"""
        if isinstance(self.width, int):
            return self.width
        natural = max([self._natural_width(r) for r in self.rows] or [0])
        total = natural + 2 * self.padding + 2
        min_total = 2 + 2 * self.padding + 1
        return min(max(total, min_total), self.max_width)

    def render(self) -> str:
        self._validate()
        total = self._resolve_width()
        area = total - 2 - 2 * self.padding  # 内容区列数
        v = self.chars["vertical"]
        h = self.chars["horizontal"]
        pad = " " * self.padding
        top = self.chars["top_left"] + h * (total - 2) + self.chars["top_right"]
        divider = self.chars["left_junction"] + h * (total - 2) + self.chars["right_junction"]
        bottom = self.chars["bottom_left"] + h * (total - 2) + self.chars["bottom_right"]

        out: list[str] = [top]
        for row in self.rows:
            t = self._row_type(row)
            if t == "divider":
                out.append(divider)
                continue
            if t == "blank":
                out.append(v + pad + " " * area + pad + v)
                continue
            for line, align in self._render_row(row, t, area):
                out.append(v + pad + _pad(line, area, align) + pad + v)
        out.append(bottom)
        return "\n".join(out)

    def _render_row(self, row: dict, t: str, area: int) -> list[tuple[str, str]]:
        wrap = row.get("wrap", self.wrap)

        if t == "buttons":
            btns = _btns(row)
            align = row.get("align") or self.button_align
            return [(_join_buttons(btns, area, align, self.gap), "left")]

        text = row.get("text", "")
        align = row.get("align") or (self.align if t in ("text", "pre") else "left")

        if t == "pre":
            lines = text.split("\n")
            for index, line in enumerate(lines, 1):
                if disp_width(line) > area:
                    raise CardError(
                        f"pre 第 {index} 行放不下：需要 {disp_width(line)} 列，"
                        f"内容区只有 {area} 列"
                    )
            return [(line, align) for line in lines]

        if t == "text":
            widths = [area]
        else:  # row：按钮固定在首行右侧，首行内容区收窄
            btns = _btns(row)
            if not btns:
                widths = [area]
            else:
                btn_block = (" " * self.gap).join(btns)
                btn_w = disp_width(btn_block)
                first = area - btn_w - self.gap
                if first < 1:
                    raise CardError(
                        f"这一行放不下：按钮 {btn_block} 占 {btn_w} 列，"
                        f"内容区只有 {area} 列。请调大 width"
                    )
                widths = [first, area]

        if wrap:
            lines = _wrap_multiline(text, widths)
        else:
            lines = _truncate_multiline(text, widths)

        if t == "row" and _btns(row):
            btn_block = (" " * self.gap).join(_btns(row))
            head = _pad(lines[0], widths[0], align) + " " * self.gap + btn_block
            return [(head, "left")] + [(ln, align) for ln in lines[1:]]
        return [(ln, align) for ln in lines]


def render(data: dict) -> str:
    """从字典渲染卡片，返回多行字符串。"""
    return Card.from_dict(data).render()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _load(path: str) -> dict:
    try:
        raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    except OSError as exc:
        raise CardError(f"无法读取输入文件：{exc}") from exc
    if path != "-" and path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError:
            raise CardError("读取 YAML 需要 pyyaml：pip install pyyaml（或改用 JSON）")
        try:
            return yaml.safe_load(raw)
        except Exception as exc:
            raise CardError(f"无法解析 YAML：{exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as json_exc:
        if path != "-" and path.lower().endswith(".json"):
            raise CardError(f"无法解析 JSON：{json_exc}") from json_exc
        try:
            import yaml
        except ImportError:
            raise CardError(f"无法解析 JSON：{json_exc}") from json_exc
        try:
            return yaml.safe_load(raw)
        except Exception as yaml_exc:
            raise CardError(
                f"无法解析 JSON 或 YAML：JSON {json_exc}; YAML {yaml_exc}"
            ) from yaml_exc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="渲染对齐的 ASCII 卡片图")
    p.add_argument("input", help="卡片描述文件（.json / .yaml），- 表示 stdin")
    p.add_argument("--width", type=int, help="覆盖卡片总宽（显示列数，含边框）")
    p.add_argument("--style", choices=BOX_STYLES, help="覆盖边框样式")
    p.add_argument("--out", help="写入文件而不是 stdout")
    p.add_argument("--check", action="store_true", help="校验每行显示宽度是否一致")
    args = p.parse_args(argv)

    try:
        data = _load(args.input)
        if not isinstance(data, dict):
            raise CardError("卡片描述必须是一个对象（dict）")
        if args.width is not None:
            data["width"] = args.width
        if args.style is not None:
            data["style"] = args.style
        text = render(data)
    except CardError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as exc:
            print(f"错误：无法写入输出文件：{exc}", file=sys.stderr)
            return 2
    else:
        print(text)

    if args.check:
        widths = {disp_width(ln) for ln in text.splitlines()}
        engine = "wcwidth" if HAVE_WCWIDTH else "unicodedata(fallback)"
        if len(widths) == 1:
            print(f"[check] OK 全部 {len(text.splitlines())} 行显示宽度均为 "
                  f"{widths.pop()} 列（引擎：{engine}）", file=sys.stderr)
        else:
            print(f"[check] FAIL 出现多种宽度：{sorted(widths)}（引擎：{engine}）",
                  file=sys.stderr)
            for i, ln in enumerate(text.splitlines(), 1):
                print(f"  line {i:>2}: {disp_width(ln):>3} | {ln}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
