"""共享公开 checkout 中允许缺省的本机 skill 判定。"""

import os
from pathlib import Path
import re
import subprocess


def optional_missing_skills(repo: Path, rows: list[dict[str, str]]) -> set[str]:
    """只接受根 .gitignore 明确排除、未跟踪且整个节点缺失的个人 skill。

    现存目录、残缺目录和断开的源软链均不豁免；无 .git 的源码包使用
    同一份根 .gitignore 声明，不读取用户全局 ignore 或 info/exclude。
    """
    ignore = repo / ".gitignore"
    declarations = set(ignore.read_text(encoding="utf-8").splitlines()) if ignore.is_file() else set()
    tracked = []
    if (repo / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "--", "skills"],
            check=True, capture_output=True,
        )
        tracked = [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]

    missing = set()
    for row in rows:
        name = row["skill"]
        if (row.get("type") or "skill").strip() != "skill" or row.get("status") != "personal-only":
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            continue
        relative = f"skills/{name}"
        if f"{relative}/" not in declarations and f"/{relative}/" not in declarations:
            continue
        if os.path.lexists(repo / relative):
            continue
        if any(path == relative or path.startswith(relative + "/") for path in tracked):
            continue
        missing.add(name)
    return missing


def optional_missing_link(repo: Path, link: Path, missing: set[str]) -> bool:
    """分类软链必须同名且准确指向允许缺省的 skill 目录。"""
    if not link.is_symlink() or link.name not in missing:
        return False
    try:
        return link.resolve() == (repo / "skills" / link.name).resolve()
    except (OSError, RuntimeError):
        return False
