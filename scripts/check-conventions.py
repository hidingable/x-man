#!/usr/bin/env python3
"""产物约定一致性校验。

x-mansion 与发行版各自维护产物约定。默认只校验本仓，显式 --wf 时再检查
发行版自身契约及两侧共用路径，避免新类型尚未发行就阻断本仓。
本脚本把以下遗漏变成可检测的失败：

  路径断言：context/naming-contract.json 里的每条产物路径字面量，必须同时
            出现在同侧 conventions.md 里。防的是命名走散。
  章节断言：Skill、Agent 及其伴随文档里 `conventions.md`〈某节〉的引用，该标题必须
            在同侧的 conventions.md 里真实存在。防的是引用悬空。
  类型断言：metadata.outputs.type 必须已登记；需求链类型两种模式都有落点。

用法：
  scripts/check-conventions.py [--wf <release-dist 路径>]

任一断言失败退出码为 1。
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "context" / "naming-contract.json"
XMAN_CONVENTIONS = REPO_ROOT / "context" / "conventions.md"
XMAN_SKILLS = REPO_ROOT / "skills"

TASK_MAPPING_HINT = ".ai-configs/tasks/<task-id>/<artifact>.md"
SECTION_REF = re.compile(r"conventions\.md`\s*〈([^〉]+)〉")
HEADING = re.compile(r"^#{2,6}\s+(.+?)\s*$", re.M)
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.S)


def contract_entries(contract):
    yield "taskId", contract["taskId"]
    for name, value in contract["task"].items():
        yield f"task.{name}", value
    for name, value in contract["adHoc"].items():
        yield f"adHoc.{name}", value
    for name, value in contract.get("global", {}).items():
        yield f"global.{name}", value


def check_paths(contract, sides):
    """每条契约路径必须出现在同侧 conventions.md 中。"""
    failures = []
    for label, text in sides:
        for artifact, value in contract_entries(contract):
            if value in text:
                continue
            # Task 模式允许用「路径模板 + 文件名」的写法代替逐条列全路径
            if artifact.startswith("task."):
                filename = value.rsplit("/", 1)[-1]
                if TASK_MAPPING_HINT in text and f"`{filename}`" in text:
                    continue
            failures.append(f"PATH_DRIFT  {label}  {artifact}: 缺 {value}")
    return failures


def check_output_types(label, contract, skills_root):
    task_types = set(contract["task"])
    adhoc_types = set(contract["adHoc"])
    global_types = set(contract.get("global", {}))
    failures = []
    known_types = task_types | adhoc_types | global_types
    checked = 0
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        match = FRONTMATTER.match(skill_file.read_text(encoding="utf-8"))
        if not match:
            continue  # front-matter 存在性由仓库校验负责。
        rel = skill_file.relative_to(skills_root.parent)
        try:
            data = yaml.safe_load(match.group(1)) or {}
            metadata = data.get("metadata") or {}
            outputs = metadata.get("outputs") or {}
            if not outputs:
                continue
            output_type = outputs.get("type")
            checked += 1
            if not isinstance(output_type, str) or output_type not in known_types:
                failures.append(f"OUTPUT_UNDEFINED  {label}  {rel}: {output_type!r} 未登记产物落点")
            elif output_type not in global_types and output_type in task_types ^ adhoc_types:
                failures.append(f"MODE_MISSING  {label}  {rel}: {output_type} 的 Task 与 Ad-hoc 须同时定义")
        except (yaml.YAMLError, AttributeError) as error:
            failures.append(f"OUTPUT_INVALID  {label}  {rel}: 元数据不可解析 ({type(error).__name__})")
    return failures, checked


def check_sections(label, conventions_text, skills_root):
    """运行指令引用的章节标题必须在同侧 conventions.md 中存在。"""
    headings = {m.group(1) for m in HEADING.finditer(conventions_text)}
    failures = []
    checked = 0
    instructions = list(skills_root.glob("*/SKILL.md"))
    instructions += list(skills_root.glob("*/references/**/*.md"))
    instructions += list((skills_root.parent / "agents").rglob("*.md"))
    for skill_file in sorted(instructions):
        for match in SECTION_REF.finditer(skill_file.read_text(encoding="utf-8")):
            checked += 1
            section = match.group(1)
            if section not in headings:
                rel = skill_file.relative_to(skills_root.parent)
                failures.append(
                    f"SECTION_DANGLING  {label}  {rel} 引用〈{section}〉，conventions.md 无此标题"
                )
    return failures, checked


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--wf", type=Path, default=None)
    args = parser.parse_args()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    xman_text = XMAN_CONVENTIONS.read_text(encoding="utf-8")
    failures = check_paths(contract, [("x-mansion", xman_text)])
    type_failures, output_checked = check_output_types("x-mansion", contract, XMAN_SKILLS)
    failures += type_failures
    section_failures, xman_checked = check_sections("x-mansion", xman_text, XMAN_SKILLS)
    failures += section_failures
    wf_checked = 0
    if args.wf is not None:
        wf_conventions = args.wf / "conventions.md"
        wf_contract_path = args.wf / "naming-contract.json"
        if not wf_conventions.is_file() or not wf_contract_path.is_file():
            print(f"发行版缺少 conventions.md 或 naming-contract.json: {args.wf}", file=sys.stderr)
            return 1
        wf_text = wf_conventions.read_text(encoding="utf-8")
        wf_contract = json.loads(wf_contract_path.read_text(encoding="utf-8"))
        failures += check_paths(wf_contract, [("release-dist", wf_text)])
        local_paths, wf_paths = dict(contract_entries(contract)), dict(contract_entries(wf_contract))
        for artifact in sorted(local_paths.keys() & wf_paths.keys()):
            if local_paths[artifact] != wf_paths[artifact]:
                failures.append(f"PATH_DRIFT  两侧  {artifact}: {local_paths[artifact]} != {wf_paths[artifact]}")
        type_failures, wf_output_checked = check_output_types("release-dist", wf_contract, args.wf / "skills")
        failures += type_failures
        output_checked += wf_output_checked
        wf_section_failures, wf_checked = check_sections(
            "release-dist", wf_text, args.wf / "skills"
        )
        failures += wf_section_failures

    for failure in failures:
        print(failure)
    if failures:
        print(f"\n{len(failures)} 条漂移")
        return 1

    scope = "两侧" if args.wf is not None else "x-mansion"
    print(f"OK  {scope}路径契约一致，输出类型 {output_checked} 份、章节引用 {xman_checked + wf_checked} 处全部有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
