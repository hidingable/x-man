#!/usr/bin/env python3
"""比对本仓与发行版里同名 skill 的正文，报告超出基线的漂移。

同名 skill 是同一个能力的两份文本。双装时用的是本仓这份，单装发行版的人用的是那份，
所以判据类改动必须两边都落；忘了一边，两拨人拿到的规则就不一样了。

有些差异是有意的：运行时命令名、编排器名字、发行版特有的约定兜底段落。这些归一化或
过滤掉；剩下的按章节记进基线，超出基线才报警。

只在本机同时有两个仓库时运行，发行版位置来自：
  1. 环境变量 XMAN_RELEASE_REPO
  2. governance/.release-repo（本机配置，不入库）
两者都没有就直接退出，不输出任何内容——本仓不假设另一个仓库存在。
"""

from __future__ import annotations

import difflib
import os
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_CONFIG = REPO_ROOT / "governance" / ".release-repo"
BASELINE = pathlib.Path(os.environ.get("XMAN_SKILL_DRIFT_BASELINE")
                        or REPO_ROOT / "governance" / "skill-drift-baseline.tsv")
OURS_SKILLS = REPO_ROOT / "skills"

# 发行版特有的约定兜底段落：本仓有 context/conventions.md 可引，发行版得自带找法。
FALLBACK_MARK = "第一行不是 `<!-- wf-conventions:"  # 发行版第 2 版约定起的兜底句式
# 宿主绑定的名字，归一化掉之后再比。
CLI_NAMES = ("xman", "release-dist")
FLOW_NAMES = ("xman-flow", "dev-flow")


def resolve_release_repo() -> pathlib.Path | None:
    raw = os.environ.get("XMAN_RELEASE_REPO", "").strip()
    if not raw and LOCAL_CONFIG.is_file():
        raw = LOCAL_CONFIG.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return pathlib.Path(raw).expanduser()


def normalize(text: str) -> list[str]:
    # front-matter 整段丢掉：metadata 两边本来就不是一套（release、status、hooks）
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + len("\n---\n"):]
    for name in FLOW_NAMES:
        text = re.sub(rf"\b{re.escape(name)}\b", "<FLOW>", text)
    for cli in CLI_NAMES:
        text = re.sub(rf"\b{re.escape(cli)}\b", "<CLI>", text)
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return [line for line in lines if FALLBACK_MARK not in line]


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "（正文开头）"
    sections[current] = []
    for line in lines:
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return sections


def load_baseline() -> dict[str, int]:
    """已人工裁决、决定保留的差异。格式每行 `skill::章节名<TAB>容许行数`。"""
    if not BASELINE.is_file():
        return {}
    out: dict[str, int] = {}
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, raw = line.partition("\t")
        if raw.strip().isdigit():
            out[name.strip()] = int(raw)
    return out


def diff_size(a: list[str], b: list[str]) -> int:
    return sum(
        1 for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes()
        if tag != "equal" for _ in range(max(i2 - i1, j2 - j1))
    )


def compare(name: str, ours: pathlib.Path, theirs: pathlib.Path) -> list[tuple[str, int]]:
    ours_sec = split_sections(normalize(ours.read_text(encoding="utf-8")))
    theirs_sec = split_sections(normalize(theirs.read_text(encoding="utf-8")))

    drifted: list[tuple[str, int]] = []
    for sec in ours_sec.keys() | theirs_sec.keys():
        a = ours_sec.get(sec)
        b = theirs_sec.get(sec)
        if a is None:
            drifted.append((f"{name}::{sec}（仅发行版有）", len(b)))
        elif b is None:
            drifted.append((f"{name}::{sec}（仅本仓有）", len(a)))
        elif a != b:
            drifted.append((f"{name}::{sec}", diff_size(a, b)))
    return drifted


def main() -> int:
    repo = resolve_release_repo()
    if repo is None:
        return 0                       # 未配置：静默退出，不提另一个仓库

    if not repo.is_dir():
        print(f"DRIFT\t配置的发行版仓库路径不存在: {repo}")
        return 1

    theirs_skills = repo / "skills"
    if not theirs_skills.is_dir():
        print(f"DRIFT\t{repo} 下没有 skills/ 目录")
        return 1

    pairs = []
    for d in sorted(OURS_SKILLS.iterdir()):
        ours = d / "SKILL.md"
        theirs = theirs_skills / d.name / "SKILL.md"
        if ours.is_file() and theirs.is_file():
            pairs.append((d.name, ours, theirs))

    if not pairs:
        print("DRIFT\t两侧没有同名 skill，安装选择集可能已经错开")
        return 1

    drifted: list[tuple[str, int]] = []
    for name, ours, theirs in pairs:
        drifted.extend(compare(name, ours, theirs))

    accepted = load_baseline()
    new_drift = [(k, d) for k, d in drifted if d > accepted.get(k, 0)]

    if not new_drift:
        extra = f"，{len(drifted)} 处已裁决差异在基线内" if drifted else ""
        print(f"OK\t同名 skill 无新增漂移（{len(pairs)} 个 skill{extra}）")
        return 0

    total = sum(d for _, d in new_drift)
    print(f"DRIFT\t同名 skill 新增漂移: {len(new_drift)} 处、约 {total} 行")
    for key, delta in sorted(new_drift, key=lambda x: -x[1]):
        print(f"    {key}（约 {delta} 行，基线 {accepted.get(key, 0)}）")
    print("    判据类差异要两边都改；确认是有意差异就记进")
    print(f"    {BASELINE.relative_to(REPO_ROOT)}。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
