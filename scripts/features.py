#!/usr/bin/env python3
"""Feature Map —— 这个应用有哪些功能、从用户视角怎么到达、怎么用工具驱动它。

存在的理由：agent 每次要验证一个界面改动，都得先把应用重新摸一遍——哪个入口、
点哪里、有什么坑。摸一遍要烧掉一大块上下文，而且每次摸的结果还不一样。
把它写下来，就变成一份所有人共用的地图，查表代替探索。

地图不是脚本能写出来的：内容要靠 agent 读代码、驱动应用编目。脚本只管三件事——
建骨架、列清单、查结构完整。跟 `xman context init` 一样，填进去的东西标 ⟨待确认⟩，
人核对完再清掉。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FEATURES_DIR = Path(".ai-configs") / "features"
INDEX_NAME = "README.md"
CONFIRM_MARK = "⟨待确认⟩"

# 一条功能必须回答的五个问题。少一个，这条对 agent 就不完整。
REQUIRED_SECTIONS = ("子功能", "从用户视角怎么到达", "怎么用工具驱动它", "坑")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

ENTRY_TEMPLATE = """# {title}

{mark} 一句话说清这是什么。

## 子功能

- {mark} `<slug>`：一句话

## 从用户视角怎么到达

{mark} 点哪里、按什么键、走哪条路。写给没用过这个应用的人看。

## 怎么用工具驱动它

```bash
{mark} 能直接复制运行的命令
```

## 坑

- {mark} 已知会让人踩空的地方；没有就写「暂无」
"""

INDEX_TEMPLATE = """# Feature Map

这个应用有哪些功能、从用户视角怎么到达、怎么用工具驱动它。
验证界面改动前先查这里，别每次重新摸一遍应用。

每条功能一个文件，固定五段：是什么 / 子功能 / 怎么到达 / 怎么驱动 / 坑。
新增用 `xman features new <slug>`，写完用 `xman features check` 查结构。

内容会过期。改了功能就顺手改这里；`check` 只能查结构，查不出内容对不对。

## 功能清单

<!-- xman features list 生成，手写的行会被保留 -->
"""


def features_dir(project: Path) -> Path:
    return project / FEATURES_DIR


def resolve_project(raw: Path | None) -> Path:
    """不传 --project 时从当前目录向上找 .ai-configs/，到 Git 边界为止。"""
    if raw is not None:
        return raw.resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".ai-configs").is_dir():
            return candidate
        if (candidate / ".git").exists():
            break
    fail(f"从 {current} 向上没找到 .ai-configs/。\n"
         f"先初始化项目上下文：xman context init")


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def entry_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.glob("*.md") if p.name != INDEX_NAME)


def parse_entry(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    headings = {line[3:].strip() for line in text.splitlines() if line.startswith("## ")}
    title_line = next((l for l in text.splitlines() if l.startswith("# ")), "")
    return {
        "slug": path.stem,
        "path": path.as_posix(),
        "title": title_line[2:].strip() or path.stem,
        "missing": [s for s in REQUIRED_SECTIONS if s not in headings],
        "todo": text.count(CONFIRM_MARK),
    }


def emit(as_json: bool, payload, human: str) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2) if as_json else human)


def cmd_init(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    root = features_dir(project)
    index = root / INDEX_NAME
    if index.is_file() and not args.force:
        emit(args.json, {"created": False, "path": index.as_posix()},
             f"已经有了：{index.relative_to(project)}\n要重建索引加 --force（会覆盖索引，不动功能条目）。")
        return 0
    if args.dry_run:
        emit(args.json, {"wouldCreate": [root.as_posix(), index.as_posix()]},
             f"--dry-run：会建 {root.relative_to(project)}/ 和它下面的 {INDEX_NAME}，不动别的。")
        return 0
    root.mkdir(parents=True, exist_ok=True)
    index.write_text(INDEX_TEMPLATE, encoding="utf-8")
    emit(args.json, {"created": True, "path": index.as_posix()},
         f"建好了：{index.relative_to(project)}\n"
         f"下一步加第一条功能：xman features new <slug>")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    root = features_dir(project)
    if not (root / INDEX_NAME).is_file():
        fail(f"还没建 Feature Map。先跑：xman features init")
    if not SLUG_RE.match(args.slug):
        fail(f"slug 只能用小写字母、数字和连字符，且不能以连字符开头：{args.slug}")
    path = root / f"{args.slug}.md"
    if path.exists():
        fail(f"已经有这条了：{path.relative_to(project)}\n"
             f"要改就直接编辑它；要看清单跑 xman features list")
    title = args.title or args.slug
    if args.dry_run:
        emit(args.json, {"wouldCreate": path.as_posix()},
             f"--dry-run：会建 {path.relative_to(project)}，用五段模板，各段标 {CONFIRM_MARK}。")
        return 0
    path.write_text(ENTRY_TEMPLATE.format(title=title, mark=CONFIRM_MARK), encoding="utf-8")
    emit(args.json, {"created": path.as_posix()},
         f"建好了：{path.relative_to(project)}\n"
         f"把五段填掉并清掉 {CONFIRM_MARK}，然后跑 xman features check")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    root = features_dir(project)
    entries = [parse_entry(p) for p in entry_files(root)]
    if not entries:
        emit(args.json, {"features": []},
             "还没有功能条目。" + ("" if (root / INDEX_NAME).is_file()
                                else "先跑 xman features init，再 ") + "用 xman features new <slug> 加。")
        return 0
    lines = []
    for e in entries:
        flags = []
        if e["missing"]:
            flags.append(f"缺 {len(e['missing'])} 段")
        if e["todo"]:
            flags.append(f"{e['todo']} 处待填")
        lines.append(f"  {e['slug']:<24} {e['title']}" + (f"   [{'，'.join(flags)}]" if flags else ""))
    emit(args.json, {"features": entries},
         f"{len(entries)} 条功能：\n" + "\n".join(lines))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    root = features_dir(project)
    if not (root / INDEX_NAME).is_file():
        fail(f"还没建 Feature Map。先跑：xman features init")
    entries = [parse_entry(p) for p in entry_files(root)]
    problems = []
    for e in entries:
        for section in e["missing"]:
            problems.append({"slug": e["slug"], "kind": "缺段", "detail": section})
        if e["todo"]:
            problems.append({"slug": e["slug"], "kind": "待填", "detail": f"{e['todo']} 处 {CONFIRM_MARK}"})
    payload = {"total": len(entries), "problems": problems}
    if not entries:
        emit(args.json, payload, "地图是空的：一条功能都没有。用 xman features new <slug> 加。")
        return 1
    if not problems:
        emit(args.json, payload, f"OK\t{len(entries)} 条功能，五段齐全，没有待填。")
        return 0
    human = f"{len(problems)} 处不完整（共 {len(entries)} 条功能）：\n" + "\n".join(
        f"  {p['slug']}：{p['kind']} — {p['detail']}" for p in problems)
    emit(args.json, payload, human + "\n\n结构不全的条目对 agent 是半张地图，"
                                     "尤其「怎么用工具驱动它」缺了就等于没写。")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xman features",
        description="Feature Map：应用有哪些功能、怎么到达、怎么驱动。",
        epilog="典型顺序：\n"
               "  xman features init\n"
               "  xman features new settings --title 偏好设置\n"
               "  # 让 agent 把五段填掉\n"
               "  xman features check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--project", type=Path, default=None,
                       help="项目根目录；不传时从当前目录向上找 .ai-configs/")
        p.add_argument("--json", action="store_true", help="机器可读输出")
        return p

    init = common(sub.add_parser("init", help="建 Feature Map 骨架",
                                 epilog="例子:\n  xman features init",
                                 formatter_class=argparse.RawDescriptionHelpFormatter))
    init.add_argument("--force", action="store_true", help="覆盖已有索引（不动功能条目）")
    init.add_argument("--dry-run", action="store_true", help="只说会建什么，不真建")
    init.set_defaults(handler=cmd_init)

    new = common(sub.add_parser("new", help="按五段模板加一条功能",
                                epilog="例子:\n  xman features new settings --title 偏好设置",
                                formatter_class=argparse.RawDescriptionHelpFormatter))
    new.add_argument("slug", help="小写字母、数字、连字符")
    new.add_argument("--title", default=None, help="显示名，默认用 slug")
    new.add_argument("--dry-run", action="store_true", help="只说会建什么，不真建")
    new.set_defaults(handler=cmd_new)

    listing = common(sub.add_parser("list", help="列出功能和完整度",
                                    epilog="例子:\n  xman features list --json",
                                    formatter_class=argparse.RawDescriptionHelpFormatter))
    listing.set_defaults(handler=cmd_list)

    check = common(sub.add_parser("check", help="查五段齐不齐、有没有待填",
                                  epilog="例子:\n  xman features check\n\n"
                                         "退出码: 0 完整 / 1 地图是空的 / 2 有条目不完整",
                                  formatter_class=argparse.RawDescriptionHelpFormatter))
    check.set_defaults(handler=cmd_check)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
