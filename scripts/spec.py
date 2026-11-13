#!/usr/bin/env python3
"""List, validate, and match project Specs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from spec_core import (
    DEFAULT_INDEX,
    SpecValidationError,
    ensure_project_local_path,
    find_project_root,
    load_and_validate_index,
    match_specs,
    normalize_target_path,
)


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="准确的项目根目录；不传时从当前目录向上发现",
    )


def _public_spec(spec: dict) -> dict:
    return {key: value for key, value in spec.items() if not key.startswith("_")}


def _load(project: Path | None) -> dict:
    if project is None:
        root = find_project_root(Path.cwd())
    else:
        root = project.resolve()
        if not (root / DEFAULT_INDEX).is_file():
            raise SpecValidationError(
                f"显式项目根缺少 {DEFAULT_INDEX.as_posix()}: {root}"
            )
    return load_and_validate_index(root, root / DEFAULT_INDEX)


def cmd_validate(args: argparse.Namespace) -> int:
    index = _load(args.project)
    print(
        f"OK  {len(index['specs'])} 条 Spec，索引: "
        f"{index['index_path'].relative_to(index['project_root'])}"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    index = _load(args.project)
    if args.json:
        print(
            json.dumps(
                [_public_spec(item) for item in index["specs"]],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for spec in index["specs"]:
        print(f"{spec['id']}  {spec['source']}  {spec['description']}")
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    index = _load(args.project)
    target = normalize_target_path(index["project_root"], args.target)
    matches = match_specs(index, target)
    if args.json:
        print(
            json.dumps(
                {
                    "target": target,
                    "specs": [_public_spec(item) for item in matches],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"目标: {target}")
    if not matches:
        print("匹配 Spec: 无")
        return 0
    print("匹配 Spec:")
    for spec in matches:
        print(f"  - {spec['id']}: {spec['source']}（{spec['description']}）")
    return 0


PROJECT_SPEC_README = (
    Path(__file__).resolve().parents[1]
    / "context"
    / "templates"
    / "project-spec-readme.md"
)
HOOK_SOURCE = Path(__file__).resolve().parent / "hooks" / "spec-pre-tool-use.py"
CORE_SOURCE = Path(__file__).resolve().parent / "spec_core.py"
HOOK_NAME = "xman-spec-pre-tool-use.py"
CORE_NAME = "xman_spec_core.py"
MANAGED_MARKER = b"# Managed by xman spec install-hooks when copied into a project."
PLATFORM_HOOKS = {
    "claude": {
        "config": Path(".claude/settings.json"),
        "hook": Path(".claude/hooks") / HOOK_NAME,
        "core": Path(".claude/hooks") / CORE_NAME,
        "command": 'python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/xman-spec-pre-tool-use.py"',
        "events": {
            "PreToolUse": "Write|Edit|MultiEdit",
        },
    },
    "codex": {
        "config": Path(".codex/hooks.json"),
        "hook": Path(".codex/hooks") / HOOK_NAME,
        "core": Path(".codex/hooks") / CORE_NAME,
        "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/xman-spec-pre-tool-use.py"',
        "events": {
            "PreToolUse": "apply_patch|Edit|Write",
        },
    },
}


def _load_json_object(path: Path) -> dict:
    if path.is_symlink():
        raise SpecValidationError(f"Hook 配置是软链，拒绝替换: {path}")
    if not path.exists():
        return {}
    if not path.is_file():
        raise SpecValidationError(f"Hook 配置不是普通文件: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecValidationError(f"Hook 配置 JSON 非法: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SpecValidationError(f"Hook 配置必须是 JSON 对象: {path}")
    return payload


def _ensure_hook_groups(payload: dict, platform: str) -> bool:
    hooks = payload.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SpecValidationError("Hook 配置中的 hooks 必须是对象")
    changed = False
    definition = PLATFORM_HOOKS[platform]
    for event_name, matcher in definition["events"].items():
        groups = hooks.setdefault(event_name, [])
        if not isinstance(groups, list):
            raise SpecValidationError(f"Hook 配置中的 {event_name} 必须是数组")
        found = False
        drifted = False
        for group in groups:
            if not isinstance(group, dict):
                continue
            handlers = group.get("hooks", [])
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                if not isinstance(handler, dict):
                    continue
                command = str(handler.get("command", ""))
                if HOOK_NAME not in command:
                    continue
                if (
                    group.get("matcher") == matcher
                    and handler.get("type") == "command"
                    and command == definition["command"]
                ):
                    found = True
                else:
                    drifted = True
        if drifted:
            raise SpecValidationError(
                f"{platform} {event_name} Hook 定义漂移；"
                "请移除旧的 xman Spec Hook 后重新安装"
            )
        if found:
            continue
        groups.append(
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": definition["command"],
                    }
                ],
            }
        )
        changed = True
    return changed


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _validate_runtime_target(source: Path, target: Path) -> None:
    source = source.resolve()
    content = source.read_bytes()
    if target.is_symlink():
        if target.resolve() != source:
            raise SpecValidationError(f"Hook 路径已有其他软链，拒绝覆盖: {target}")
        return
    if target.exists():
        if not target.is_file():
            raise SpecValidationError(f"Hook 路径不是普通文件，拒绝覆盖: {target}")
        installed = target.read_bytes()
        if installed != content and MANAGED_MARKER not in installed.splitlines()[:3]:
            raise SpecValidationError(f"Hook 路径已有用户文件，拒绝覆盖: {target}")


def _install_runtime_file(source: Path, target: Path) -> bool:
    source = source.resolve()
    content = source.read_bytes()
    _validate_runtime_target(source, target)
    if target.is_symlink():
        target.unlink()
    if target.exists() and target.read_bytes() == content:
        return False
    _atomic_write_bytes(target, content)
    return True


def cmd_init(args: argparse.Namespace) -> int:
    root = (args.project or Path.cwd()).resolve()
    if not root.is_dir():
        raise SpecValidationError(f"项目根目录不存在或不是目录: {root}")
    index_path = root / DEFAULT_INDEX
    readme_path = index_path.parent / "README.md"
    ensure_project_local_path(root, index_path, "Spec 索引")
    ensure_project_local_path(root, readme_path, "Spec 说明")
    if index_path.exists() or index_path.is_symlink():
        raise SpecValidationError(f"Spec 索引已经存在，拒绝覆盖: {index_path}")
    if not PROJECT_SPEC_README.is_file():
        raise SpecValidationError(f"Spec 初始化模板不存在: {PROJECT_SPEC_README}")

    _atomic_write_json(index_path, {"version": 1, "specs": []})
    if not readme_path.exists():
        _atomic_write_bytes(readme_path, PROJECT_SPEC_README.read_bytes())
    print(f"已初始化项目 Spec: {index_path}")
    print("下一步：在 index.json 中登记现有规范事实源及其适用路径，然后运行 xman spec validate。")
    return 0


def _print_host_status(platform: str) -> None:
    executable = shutil.which(platform)
    if executable:
        try:
            result = subprocess.run(
                [executable, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = (result.stdout or result.stderr).strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError):
            version = "版本读取失败"
        print(
            f"宿主检查：检测到 {platform} CLI: {executable}（{version}）；"
            "存在可执行文件不证明 Hook 已生效，仍需真实写操作验证。"
        )
    else:
        print(f"宿主检查：未检测到 {platform} CLI；配置已写入，但当前机器无法验证 Hook 是否生效。")


def cmd_install_hooks(args: argparse.Namespace) -> int:
    index = _load(args.project)
    platform = args.platform
    definition = PLATFORM_HOOKS[platform]
    config_path = index["project_root"] / definition["config"]
    hook_path = index["project_root"] / definition["hook"]
    core_path = index["project_root"] / definition["core"]
    ensure_project_local_path(index["project_root"], config_path, "Hook 配置")
    if not (hook_path.is_symlink() and hook_path.resolve() == HOOK_SOURCE.resolve()):
        ensure_project_local_path(index["project_root"], hook_path, "Hook 脚本")
    ensure_project_local_path(index["project_root"], core_path, "Hook 运行库")
    payload = _load_json_object(config_path)
    changed = _ensure_hook_groups(payload, platform)

    if args.dry_run:
        print(f"将安装 {platform} Spec Hook:")
        print(f"  配置: {config_path}")
        print(f"  脚本副本: {hook_path}")
        print(f"  运行库副本: {core_path}")
        _print_host_status(platform)
        _print_hook_boundary()
        return 0

    _validate_runtime_target(HOOK_SOURCE, hook_path)
    _validate_runtime_target(CORE_SOURCE, core_path)
    runtime_changed = _install_runtime_file(HOOK_SOURCE, hook_path)
    runtime_changed = _install_runtime_file(CORE_SOURCE, core_path) or runtime_changed
    if changed or not config_path.exists():
        _atomic_write_json(config_path, payload)
    state = "已安装" if changed or runtime_changed else "已存在"
    print(f"{state} {platform} Spec Hook: {config_path}")
    _print_host_status(platform)
    _print_hook_boundary()
    if platform == "codex":
        print("下一步：在 Codex 中运行 /hooks，审核并信任新增 Hook；未信任前 Hook 不会执行。")
    return 0


def _print_hook_boundary() -> None:
    print("边界：MVP 仅覆盖结构化写工具；Bash、重定向、格式化器和脚本写入不在门禁内。")
    print("边界：会话缓存由同一 OS 用户写入，本机制用于防遗漏，不是安全或合规强制边界。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xman spec")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="初始化项目 Spec 索引和说明")
    init.add_argument(
        "--project",
        type=Path,
        default=None,
        help="准确的项目根目录；不传时使用当前目录",
    )
    init.set_defaults(handler=cmd_init)

    validate = subparsers.add_parser("validate", help="校验 Spec 索引")
    _add_project_argument(validate)
    validate.set_defaults(handler=cmd_validate)

    listing = subparsers.add_parser("list", help="列出 Spec")
    _add_project_argument(listing)
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(handler=cmd_list)

    match = subparsers.add_parser("match", help="匹配目标文件适用的 Spec")
    match.add_argument("target")
    match.add_argument("--json", action="store_true")
    _add_project_argument(match)
    match.set_defaults(handler=cmd_match)

    install = subparsers.add_parser(
        "install-hooks",
        help="安装 Claude 或 Codex 的项目级写前 Spec Hook",
    )
    install.add_argument("platform", choices=sorted(PLATFORM_HOOKS))
    install.add_argument("--dry-run", action="store_true")
    _add_project_argument(install)
    install.set_defaults(handler=cmd_install_hooks)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except SpecValidationError as exc:
        print(f"Spec 校验失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
