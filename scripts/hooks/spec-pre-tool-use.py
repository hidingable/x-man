#!/usr/bin/env python3
# Managed by xman spec install-hooks when copied into a project.
"""Block the first write until all path-matched project Specs are delivered."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
import tempfile
from pathlib import Path


HOOK_DIR = Path(__file__).resolve().parent
INSTALLED_CORE = HOOK_DIR / "xman_spec_core.py"
if INSTALLED_CORE.is_file():
    MODULE_DIR = HOOK_DIR
    CORE_MODULE = "xman_spec_core"
else:
    MODULE_DIR = HOOK_DIR.parent
    CORE_MODULE = "spec_core"
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

if CORE_MODULE == "xman_spec_core":
    from xman_spec_core import (  # noqa: E402
        SpecValidationError,
        ensure_project_local_path,
        find_project_root,
        load_and_validate_index,
        match_specs,
        normalize_target_path,
    )
else:
    from spec_core import (  # noqa: E402
        SpecValidationError,
        ensure_project_local_path,
        find_project_root,
        load_and_validate_index,
        match_specs,
        normalize_target_path,
    )


PATCH_PATH = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$",
    re.M,
)


def _json_output(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _block(reason: str) -> None:
    _json_output({"decision": "block", "reason": reason})


def _collect_named_paths(value: object) -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"file_path", "path"} and isinstance(child, str):
                found.append(child)
            else:
                found.extend(_collect_named_paths(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_collect_named_paths(child))
    return found


def extract_target_paths(tool_input: object) -> list[str]:
    paths = _collect_named_paths(tool_input)
    patch_values = [tool_input] if isinstance(tool_input, str) else []
    if isinstance(tool_input, dict):
        for field in ("patch", "input", "text", "command"):
            value = tool_input.get(field)
            if isinstance(value, str):
                patch_values.append(value)
    for patch in patch_values:
        for match in PATCH_PATH.finditer(patch):
            paths.append(match.group(1) or match.group(2))
    return list(dict.fromkeys(paths))


def _source_snapshot(spec: dict) -> tuple[str, str]:
    content = spec["_source_path"].read_bytes()
    text = content.decode("utf-8")
    digest = hashlib.sha256()
    digest.update(spec["id"].encode("utf-8"))
    digest.update(b"\0")
    digest.update(content)
    return text, digest.hexdigest()


def _cache_dir(project_root: Path, session_id: str) -> Path:
    safe_session = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    path = project_root / ".ai-configs" / "runtime" / "spec-cache" / safe_session
    return ensure_project_local_path(project_root, path, "Spec 运行态目录")


def _read_delivered_hash(cache_dir: Path, spec_id: str) -> str:
    try:
        return (cache_dir / f"{spec_id}.sha256").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _write_delivered_hash(cache_dir: Path, spec_id: str, source_hash: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{spec_id}.sha256"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=cache_dir,
        delete=False,
    ) as handle:
        handle.write(f"{source_hash}\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _delivery_reason(
    targets: list[str],
    specs: list[dict],
    session_id: str,
    project_root: Path,
) -> str:
    read_command = shlex.join(
        [
            "python3",
            str(Path(sys.argv[0]).absolute()),
            "--spec-id",
            *(spec["id"] for spec in specs),
            "--session-id",
            session_id,
            "--project",
            str(project_root),
        ]
    )
    sections = [
        "当前写入已阻断：以下路径命中了尚未加载或已经变化的项目 Spec。",
        "",
        "目标文件：",
        *(f"- {target}" for target in targets),
        "",
        "先执行以下命令读取并确认规范，再重新提交原写入操作：",
        "",
        read_command,
    ]
    for spec in specs:
        sections.extend(
            [
                "",
                f"## {spec['id']}",
                f"来源：{spec['source']}",
                f"适用原因：{spec['description']}",
            ]
        )
    return "\n".join(sections).rstrip()


def acknowledge_specs(project: Path, session_id: str, spec_ids: list[str]) -> int:
    project_root = find_project_root(project)
    index = load_and_validate_index(project_root)
    by_id = {spec["id"]: spec for spec in index["specs"]}
    requested = []
    for spec_id in spec_ids:
        spec = by_id.get(spec_id)
        if spec is None:
            raise SpecValidationError(f"Spec id 未登记: {spec_id}")
        if spec not in requested:
            requested.append(spec)

    cache_dir = _cache_dir(project_root, session_id)
    for spec in requested:
        source_text, source_hash = _source_snapshot(spec)
        print(f"## {spec['id']} ({spec['source']})")
        print()
        print(source_text)
        _write_delivered_hash(cache_dir, spec["id"], source_hash)
    return 0


def run_acknowledgement_cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-id", nargs="+", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    try:
        return acknowledge_specs(args.project, args.session_id, args.spec_id)
    except Exception as exc:  # Hook CLI must fail visibly instead of hiding partial setup.
        print(f"Spec 阅读确认失败: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise SpecValidationError("Hook 输入必须是 JSON 对象")
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise SpecValidationError("Hook 输入缺少 session_id")
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            raise SpecValidationError("Hook 输入缺少 cwd")
        project_root = find_project_root(cwd)
        index = load_and_validate_index(project_root)
        raw_targets = extract_target_paths(payload.get("tool_input", {}))
        hook_cwd = Path(cwd).resolve()
        targets = [
            normalize_target_path(
                project_root,
                Path(target) if Path(target).is_absolute() else hook_cwd / target,
            )
            for target in raw_targets
        ]
        targets = list(dict.fromkeys(targets))
        if not targets:
            _json_output({})
            return 0

        matched_by_id = {}
        for target in targets:
            for spec in match_specs(index, target):
                matched_by_id[spec["id"]] = spec
        matched = [matched_by_id[key] for key in sorted(matched_by_id)]
        if not matched:
            _json_output({})
            return 0

        cache_dir = _cache_dir(project_root, session_id)
        missing = []
        for spec in matched:
            _, current_hash = _source_snapshot(spec)
            if _read_delivered_hash(cache_dir, spec["id"]) == current_hash:
                continue
            missing.append(spec)

        if not missing:
            _json_output({})
            return 0

        _block(_delivery_reason(targets, missing, session_id, project_root))
        return 0
    except Exception as exc:  # Policy hooks must fail closed on unexpected input or code defects.
        _block(f"Spec 检查失败，写入未执行：{exc}")
        return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(run_acknowledgement_cli())
    sys.exit(main())
