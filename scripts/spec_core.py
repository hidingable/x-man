#!/usr/bin/env python3
# Managed by xman spec install-hooks when copied into a project.
"""Shared validation and path matching for project Specs."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath


DEFAULT_INDEX = Path(".ai-configs/specs/index.json")
# 索引曾经放在 docs/specs/。这份文件会被 install-hooks 复制进项目，所以路径变更后
# 老项目里跑的是旧副本——找不到索引时它会阻断每一次结构化写入。保留旧位置作为
# 只读回退，读到就提示重装，让使用者知道该跑哪条命令，而不是对着报错猜。
LEGACY_INDEX = Path("docs/specs/index.json")
SPEC_ID = re.compile(r"^[a-z0-9-]+$")


class SpecValidationError(ValueError):
    """Raised when a Spec index or target path violates the contract."""


def find_project_root(start: Path | str) -> Path:
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / DEFAULT_INDEX).is_file():
            return candidate
        if (candidate / LEGACY_INDEX).is_file():
            raise SpecValidationError(
                f"Spec 索引仍在旧位置 {LEGACY_INDEX.as_posix()}（现在是 "
                f"{DEFAULT_INDEX.as_posix()}）。把它移到新位置，并重跑 "
                f"xman spec install-hooks <claude|codex> 更新项目里的 Hook 副本"
            )
        if (candidate / ".git").exists():
            raise SpecValidationError(
                f"到达 Git 仓库边界仍未找到 {DEFAULT_INDEX.as_posix()}: {candidate}"
            )
    raise SpecValidationError(
        f"未找到 {DEFAULT_INDEX.as_posix()}，起点: {current}"
    )


def _repo_relative(project_root: Path, raw: str, label: str) -> tuple[Path, str]:
    if not isinstance(raw, str) or not raw.strip():
        raise SpecValidationError(f"{label} 不能为空")
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (project_root / candidate).resolve()
    if resolved != project_root and project_root not in resolved.parents:
        raise SpecValidationError(f"{label} 越界: {raw}")
    return resolved, resolved.relative_to(project_root).as_posix()


def normalize_target_path(project_root: Path, target: Path | str) -> str:
    root = project_root.resolve()
    raw = Path(target)
    resolved = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if resolved != root and root not in resolved.parents:
        raise SpecValidationError(f"目标路径位于项目之外: {target}")
    return resolved.relative_to(root).as_posix()


def ensure_project_local_path(
    project_root: Path,
    target: Path,
    label: str,
) -> Path:
    root = project_root.resolve()
    resolved = target.resolve()
    if resolved != root and root not in resolved.parents:
        raise SpecValidationError(f"{label} 位于项目之外: {target} -> {resolved}")
    return target


def _validate_pattern(pattern: object, spec_id: str) -> str:
    if not isinstance(pattern, str) or not pattern.strip():
        raise SpecValidationError(f"{spec_id}: paths 中存在空模式")
    normalized = pattern.strip()
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or "\\" in normalized:
        raise SpecValidationError(f"{spec_id}: paths 越界或格式非法: {pattern}")
    unsupported = sorted(set(normalized) & set("[]{}"))
    if unsupported or "***" in normalized:
        detail = "".join(unsupported) or "***"
        raise SpecValidationError(
            f"{spec_id}: paths 暂不支持该 glob 语法 ({detail}): {pattern}；"
            "MVP 仅支持 *、**、?"
        )
    return normalized.removeprefix("./")


def load_and_validate_index(
    project_root: Path | str,
    index_path: Path | str | None = None,
) -> dict:
    root = Path(project_root).resolve()
    index = Path(index_path) if index_path is not None else root / DEFAULT_INDEX
    if not index.is_absolute():
        index = root / index
    try:
        payload = json.loads(index.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpecValidationError(f"Spec 索引不存在: {index}") from exc
    except UnicodeDecodeError as exc:
        raise SpecValidationError(f"Spec 索引不是有效 UTF-8 文本: {index}") from exc
    except json.JSONDecodeError as exc:
        raise SpecValidationError(f"Spec 索引 JSON 非法: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise SpecValidationError("Spec 索引 version 必须为 1")
    specs = payload.get("specs")
    if not isinstance(specs, list):
        raise SpecValidationError("Spec 索引 specs 必须是数组")

    normalized_specs = []
    seen_ids = set()
    for position, raw_spec in enumerate(specs, start=1):
        if not isinstance(raw_spec, dict):
            raise SpecValidationError(f"第 {position} 条 Spec 必须是对象")
        spec_id = raw_spec.get("id", "")
        if not isinstance(spec_id, str) or not SPEC_ID.fullmatch(spec_id):
            raise SpecValidationError(f"Spec id 非法: {spec_id!r}")
        if spec_id in seen_ids:
            raise SpecValidationError(f"Spec id 重复: {spec_id}")
        seen_ids.add(spec_id)

        description = raw_spec.get("description")
        if not isinstance(description, str) or not description.strip():
            raise SpecValidationError(f"{spec_id}: description 不能为空")
        source_path, source_rel = _repo_relative(
            root,
            raw_spec.get("source", ""),
            f"{spec_id}: source",
        )
        if not source_path.is_file():
            raise SpecValidationError(f"{spec_id}: 事实源不存在: {source_rel}")
        try:
            source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SpecValidationError(
                f"{spec_id}: 事实源不是有效 UTF-8 文本: {source_rel}"
            ) from exc

        raw_patterns = raw_spec.get("paths")
        if not isinstance(raw_patterns, list) or not raw_patterns:
            raise SpecValidationError(f"{spec_id}: paths 必须是非空数组")
        patterns = [_validate_pattern(item, spec_id) for item in raw_patterns]

        normalized_specs.append(
            {
                "id": spec_id,
                "source": source_rel,
                "description": description.strip(),
                "paths": patterns,
                "_source_path": source_path,
            }
        )

    return {
        "version": 1,
        "project_root": root,
        "index_path": index.resolve(),
        "specs": sorted(normalized_specs, key=lambda item: item["id"]),
    }


def _glob_regex(pattern: str) -> re.Pattern[str]:
    pieces = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    pieces.append("(?:.*/)?")
                    index += 1
                else:
                    pieces.append(".*")
                continue
            pieces.append("[^/]*")
        elif char == "?":
            pieces.append("[^/]")
        else:
            pieces.append(re.escape(char))
        index += 1
    pieces.append("$")
    return re.compile("".join(pieces))


def match_specs(index: dict, target: Path | str) -> list[dict]:
    target_path = normalize_target_path(index["project_root"], target)
    matches = []
    for spec in index["specs"]:
        if any(_glob_regex(pattern).fullmatch(target_path) for pattern in spec["paths"]):
            matches.append(spec)
    return matches
