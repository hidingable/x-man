#!/usr/bin/env python3
"""比对本仓编排器与发行版编排器的流程骨架，报告超出白名单的漂移。

两份编排器是有意的两个实现：它们绑定不同的运行时，内容本来就该不同。但阶段列表、
仲裁规则、失败判定这些是同一套方法论，漂移了就变成两套流程。

只在本机同时有两个仓库时运行。发行版仓库位置来自：
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
# 基线位置可用 XMAN_DRIFT_BASELINE 覆盖，回归测试要能构造自己的基线
BASELINE = pathlib.Path(os.environ.get("XMAN_DRIFT_BASELINE")
                        or REPO_ROOT / "governance" / "flow-drift-baseline.tsv")
OURS = REPO_ROOT / "agents" / "xman-flow.md"

# 宿主绑定差异：这四类必须不同，改成一致反而会坏。归一化掉之后再比。
STAGE_FILE = ".dev-flow-stage"          # 产物路径，两侧同名，先保护起来
STAGE_TOKEN = "\x00STAGE\x00"
FALLBACK_MARK = "第一行不是 `<!-- wf-conventions:"  # 发行版特有的约定兜底段落（第 2 版约定起的句式）
# 阶段状态文件的落点：本仓引 conventions 不写死路径字面量，发行版直接列出路径。
# 两种表述语义等价，取舍取决于各自是否有可引用的约定事实源，属于宿主绑定。
STAGE_LOCATION_MARK = "**位置**"
CLI_NAMES = ("xman", "release-dist")


def resolve_release_repo() -> pathlib.Path | None:
    raw = os.environ.get("XMAN_RELEASE_REPO", "").strip()
    if not raw and LOCAL_CONFIG.is_file():
        raw = LOCAL_CONFIG.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return pathlib.Path(raw).expanduser()


def find_counterpart(repo: pathlib.Path) -> pathlib.Path | None:
    """发行版侧的编排器名字由它自己决定，不写死：取 agents/ 下带 name 的扁平定义，
    排除与本仓同名的那个（那是本仓装过去的，不是对照物）。"""
    agents_dir = repo / "agents"
    if not agents_dir.is_dir():
        return None
    for path in sorted(agents_dir.glob("*.md")):
        if path.stem == OURS.stem:
            continue
        head = path.read_text(encoding="utf-8").split("\n", 1)[0]
        if head.strip() == "---":
            return path
    return None


def normalize(text: str, agent_name: str) -> list[str]:
    text = text.replace(STAGE_FILE, STAGE_TOKEN)
    # front-matter 整段丢掉：orchestrates 的 skill 集合两边本来就不是同一批
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + len("\n---\n"):]
    text = text.replace(f"./{agent_name}/", "<AGENT>/")
    text = text.replace(f"{agent_name}/", "<AGENT>/")
    text = text.replace(agent_name, "<AGENT>")
    # env 变量名跟着 CLI 走（XMAN_TASK / WF_TASK），属于同一类宿主绑定
    text = re.sub(r"\b(XMAN|WF)_TASK\b", "<CLI>_TASK", text)
    for cli in CLI_NAMES:
        text = re.sub(rf"\b{re.escape(cli)}\b", "<CLI>", text)
    text = text.replace(STAGE_TOKEN, STAGE_FILE)
    return [line.rstrip() for line in text.splitlines() if line.strip()]


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
    """已人工裁决、决定保留的差异。没有它，那些差异会被永远报下去。
    格式每行 `章节名<TAB>容许行数`，# 开头为注释。"""
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


def main() -> int:
    repo = resolve_release_repo()
    if repo is None:
        return 0                       # 未配置：静默退出，不提另一个仓库

    if not repo.is_dir():
        print(f"DRIFT\t配置的发行版仓库路径不存在: {repo}")
        return 1

    theirs = find_counterpart(repo)
    if theirs is None:
        print(f"DRIFT\t{repo} 下没有找到可对照的编排器定义")
        return 1
    if not OURS.is_file():
        print(f"DRIFT\t本仓编排器不存在: {OURS.relative_to(REPO_ROOT)}")
        return 1

    ours_lines = normalize(OURS.read_text(encoding="utf-8"), OURS.stem)
    def keep(line: str) -> bool:
        return FALLBACK_MARK not in line and STAGE_LOCATION_MARK not in line

    ours_lines = [line for line in ours_lines if keep(line)]
    theirs_lines = [
        line for line in normalize(theirs.read_text(encoding="utf-8"), theirs.stem)
        if keep(line)
    ]

    ours_sec = split_sections(ours_lines)
    theirs_sec = split_sections(theirs_lines)

    only_ours = [k for k in ours_sec if k not in theirs_sec]
    only_theirs = [k for k in theirs_sec if k not in ours_sec]
    if only_ours or only_theirs:
        print("DRIFT\t流程骨架的章节对不上，两侧已经是两套流程")
        for name in only_ours:
            print(f"    仅本仓有: {name}")
        for name in only_theirs:
            print(f"    仅发行版有: {name}")
        return 1

    drifted = []
    for name, ours_body in ours_sec.items():
        theirs_body = theirs_sec[name]
        if ours_body == theirs_body:
            continue
        delta = sum(
            1 for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, ours_body, theirs_body).get_opcodes()
            if tag != "equal" for _ in range(max(i2 - i1, j2 - j1))
        )
        drifted.append((name, delta))

    accepted = load_baseline()
    new_drift = [(name, delta) for name, delta in drifted
                 if delta > accepted.get(name, 0)]

    if not new_drift:
        extra = f"，{len(drifted)} 处已裁决差异在基线内" if drifted else ""
        print(f"OK\t流程骨架无新增漂移（{len(ours_sec)} 个章节{extra}）")
        return 0

    total = sum(d for _, d in new_drift)
    print(f"DRIFT\t流程骨架新增漂移: {len(new_drift)} 个章节、约 {total} 行")
    for name, delta in sorted(new_drift, key=lambda x: -x[1]):
        was = accepted.get(name, 0)
        print(f"    {name}（约 {delta} 行，基线 {was}）")
    print("    白名单只放行：orchestrates 集合、约定兜底段落、references 的 ./ 前缀、")
    print("    阶段状态位置的表述方式、运行时命令名与编排器自身名字。")
    print("    其余差异需要人工判断哪边该跟进。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
