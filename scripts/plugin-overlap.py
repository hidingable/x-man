#!/usr/bin/env python3
"""处理 Codex 里与本 plugin 重名的发行版 plugin。

本 plugin 发全量 skill。registry 的 release 列写着某个发行版名字的条目，那个发行版
也会发一份同名的；两个 plugin 同时启用时，模型会看到两个只差前缀的 skill。这里按
x-mansion 优先处理：把那个发行版 plugin 在 Codex 配置里停用，不卸载、不删缓存。

用法:
  plugin-overlap.py report    同时启用时提示一行；没有重名时零输出
  plugin-overlap.py takeover  停用重名的发行版 plugin
  plugin-overlap.py restore   把 takeover 停用的重新启用

Codex 配置位置取 CODEX_HOME，缺省 ~/.codex。registry 位置可用 XMAN_REGISTRY 覆盖。
"""

import csv
import os
import pathlib
import re
import sys
import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OWN_PLUGIN = "x-mansion"


def release_counts() -> dict[str, int]:
    registry = pathlib.Path(
        os.environ.get("XMAN_REGISTRY") or REPO_ROOT / "governance" / "skills-registry.csv"
    )
    counts: dict[str, int] = {}
    with registry.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("type") or "skill").strip() == "deprecated":
                continue
            name = (row.get("release") or "").strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


def config_path() -> pathlib.Path:
    home = os.environ.get("CODEX_HOME") or pathlib.Path.home() / ".codex"
    return pathlib.Path(home) / "config.toml"


def overlapping(enabled: bool) -> list[tuple[str, int]]:
    """返回 [(plugin 键, 重名 skill 数)]，只含启用状态等于 enabled 的发行版 plugin。"""
    path = config_path()
    if not path.is_file():
        return []
    try:
        plugins = tomllib.loads(path.read_text(encoding="utf-8")).get("plugins", {})
    except tomllib.TOMLDecodeError:
        return []
    own_enabled = any(
        key.split("@", 1)[0] == OWN_PLUGIN and value.get("enabled", True)
        for key, value in plugins.items()
        if isinstance(value, dict)
    )
    if not own_enabled:
        # 本 plugin 没启用就谈不上重名，也不该去动别人的 plugin
        return []
    counts = release_counts()
    return [
        (key, counts[key.split("@", 1)[0]])
        for key, value in plugins.items()
        if isinstance(value, dict)
        and key.split("@", 1)[0] in counts
        and bool(value.get("enabled", True)) is enabled
    ]


def set_enabled(key: str, enabled: bool) -> bool:
    """只改这一张表里的 enabled 一行，其余内容和注释原样保留。"""
    path = config_path()
    text = path.read_text(encoding="utf-8")
    header = re.search(rf'(?m)^\[plugins\."{re.escape(key)}"\][ \t]*$', text)
    if not header:
        return False
    rest = text[header.end():]
    next_table = re.search(r"(?m)^\[", rest)
    body = rest[: next_table.start()] if next_table else rest
    value = "true" if enabled else "false"
    new_body, changed = re.subn(
        r"(?m)^(enabled[ \t]*=[ \t]*)(true|false)", rf"\g<1>{value}", body, count=1
    )
    if not changed:
        new_body = f"\nenabled = {value}" + body
    path.write_text(
        text[: header.end()] + new_body + rest[len(body):], encoding="utf-8"
    )
    return True


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "report"
    if command == "report":
        for key, count in overlapping(enabled=True):
            print(f"⚠ Codex 里同时启用了 {key}，有 {count} 个 skill 与本 plugin 重名，模型会看到两份")
            print("  运行 ./xman plugin takeover 停用它，同名 skill 统一用 x-mansion 这份")
        return 0
    if command == "takeover":
        targets = overlapping(enabled=True)
        if not targets:
            print("Codex 里没有与本 plugin 重名的已启用 plugin，无需处理")
            return 0
        for key, count in targets:
            if set_enabled(key, False):
                print(f"已停用 {key}：{count} 个同名 skill 改由 x-mansion 提供（未卸载，缓存保留）")
        print(f"改动文件：{config_path()}，新会话生效；恢复用 ./xman plugin restore")
        return 0
    if command == "restore":
        targets = overlapping(enabled=False)
        if not targets:
            print("没有被停用的重名 plugin，无需恢复")
            return 0
        for key, _ in targets:
            if set_enabled(key, True):
                print(f"已重新启用 {key}")
        print(f"改动文件：{config_path()}，新会话生效")
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
