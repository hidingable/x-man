#!/usr/bin/env python3
"""把探测结果写回 project-context.md。

用法：
  CONTEXT_FILE=... NA_FIELDS=... MARK=... apply-context-fields.py <tsv>

只替换仍是 [待填写] 的字段——已经有人填过的值不覆盖。
MARK 非空时给自动填入的值追加标记（等待人工确认）；--auto 模式传空。
NA_FIELDS 是逗号分隔的字段名，标为 [不适用]（项目形态决定，如后端项目不填主色调）。
"""

import os
import re
import sys

CONTEXT_FILE = os.environ["CONTEXT_FILE"]
NA_FIELDS = [f.strip() for f in os.environ.get("NA_FIELDS", "").split(",") if f.strip()]
MARK = os.environ.get("MARK", "")

tsv_path = sys.argv[1]

fields = {}
modules = []
structure = None

with open(tsv_path, encoding="utf-8") as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        key = parts[0]
        if key == "__module__" and len(parts) >= 4:
            modules.append((parts[1], parts[2], parts[3]))
        elif key == "__structure__" and len(parts) >= 2:
            structure = parts[1].replace("\\n", "\n")
        elif key == "__archetype__":
            continue
        elif len(parts) >= 2:
            fields[key] = parts[1]

with open(CONTEXT_FILE, encoding="utf-8") as fh:
    text = fh.read()

filled = []
skipped = []


def replace_field(label, value, marker):
    """替换 `- **label**：[待填写]`，保留行尾注释。"""
    global text
    pattern = re.compile(
        r"(^-\s+\*\*" + re.escape(label) + r"\*\*：)\[待填写\](.*)$",
        re.M,
    )
    replacement_value = value + (" " + marker if marker else "")
    new_text, n = pattern.subn(
        lambda m: m.group(1) + replacement_value + m.group(2), text, count=1
    )
    if n:
        text = new_text
    return n


# 1. 不适用字段（形态决定）
# 只在探测器没给出值时才标 [不适用]——形态判断是启发式，探测到的是事实，
# 事实优先。否则 library 形态会把真实存在的 Tailwind/Zustand 抹成"不适用"，
# 而 [不适用] 又计入已完成，check 永远不会暴露这个错误。
for label in NA_FIELDS:
    if fields.get(label):
        continue
    if replace_field(label, "[不适用]", ""):
        skipped.append(label)

# 2. 探测到的字段
for label, value in fields.items():
    if replace_field(label, value, MARK):
        filled.append((label, value))

# 3. 项目结构代码块
# 不加 ⟨待确认⟩ 标记——代码块里没有注释语法，塞标记会污染目录树本身。
# 目录列表是直接读文件系统得来的，也没什么可确认的。
if structure:
    block = re.compile(r"(## 项目结构\n\n```\n)\[待填写\]", re.M)
    new_text, n = block.subn(lambda m: m.group(1) + structure, text, count=1)
    if n:
        text = new_text
        filled.append(("项目结构", structure.splitlines()[0] + " ..."))

# 4. 子工程清单（monorepo）
if modules:
    rows = ["| 路径 | 形态 | 技术栈 |", "|---|---|---|"]
    for rel, arche, stack in modules:
        rows.append(f"| `{rel}` | {arche} | {stack} |")
    table = "\n".join(rows)
    sec = re.compile(r"(## 子工程\n\n)\[待填写\][^\n]*", re.M)
    new_text, n = sec.subn(lambda m: m.group(1) + table, text, count=1)
    if n:
        text = new_text
        filled.append(("子工程", f"{len(modules)} 个"))
else:
    sec = re.compile(r"(## 子工程\n\n)\[待填写\][^\n]*", re.M)
    new_text, n = sec.subn(lambda m: m.group(1) + "[不适用]（单工程仓库）", text, count=1)
    if n:
        text = new_text
        skipped.append("子工程")

with open(CONTEXT_FILE, "w", encoding="utf-8") as fh:
    fh.write(text)

# ─── 回显 ───
if filled:
    print(f"  ✓ 自动填入 {len(filled)} 项：")
    for label, value in filled:
        shown = value if len(value) <= 60 else value[:57] + "..."
        print(f"      {label}: {shown}")

if skipped:
    print(f"  ⊘ 标为不适用 {len(skipped)} 项：{', '.join(skipped)}")

# 排除说明性文本：> 开头的引言块，以及 <!-- --> 注释块（可能跨行）。
# 两处都会字面写出这些标记做说明，算进去就虚报。
# 与 context-init.sh 的 count_mark 保持同一口径。
_counted = re.sub(r"<!--.*?-->", "", text, flags=re.S)
remaining = sum(
    line.count("[待填写]")
    for line in _counted.split("\n")
    if not line.startswith(">")
)
if remaining:
    print(f"  ○ 仍需人工填写 {remaining} 项（语义类字段，脚本判定不了）")
