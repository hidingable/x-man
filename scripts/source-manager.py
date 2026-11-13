#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import filecmp
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_FILE = REPO_ROOT / "governance" / "skills-registry.csv"
SOURCES_ROOT = REPO_ROOT / "governance" / "sources"
DEFAULT_FIELDS = ["skill", "status", "source", "note", "source_type", "source_key"]
COMMON_SIMPLE_PARTS = [
    ("file", "SKILL.md", "SKILL.md"),
    ("dir", "assets", "assets"),
    ("dir", "references", "references"),
    ("dir", "scripts", "scripts"),
    ("dir", "data", "data"),
]
PRESERVED_SKILL_FRONTMATTER_FIELDS = ("disable-model-invocation",)


def err(message: str) -> None:
    print(message, file=sys.stderr)


def load_registry() -> tuple[list[str], list[dict[str, str]]]:
    if not REGISTRY_FILE.exists():
        raise SystemExit(f"缺少治理清单: {REGISTRY_FILE}")

    with REGISTRY_FILE.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        for field in DEFAULT_FIELDS:
            if field not in fieldnames:
                fieldnames.append(field)
        rows = []
        for row in reader:
            normalized = {field: (row.get(field, "") or "") for field in fieldnames}
            normalized["source_type"] = normalized["source_type"] or "local"
            rows.append(normalized)
        return fieldnames, rows


def save_registry(fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    rows = sorted(rows, key=lambda item: item["skill"])
    with REGISTRY_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def rows_by_skill(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["skill"]: row for row in rows}


def manifest_path(source_key: str) -> Path:
    return SOURCES_ROOT / f"{source_key}.json"


def load_manifest(source_key: str) -> dict:
    path = manifest_path(source_key)
    if not path.exists():
        raise FileNotFoundError(f"缺少 source manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_repo_relative(path_str: str) -> Path:
    resolved = (REPO_ROOT / path_str).resolve()
    if REPO_ROOT not in resolved.parents and resolved != REPO_ROOT:
        raise SystemExit(f"目标路径越界: {path_str}")
    return resolved


def clone_checkout(repo: str, ref: str, workdir: Path) -> Path:
    checkout = workdir / "checkout"
    cmd = ["git", "clone", "--depth", "1", "--branch", ref, repo, str(checkout)]
    subprocess.run(cmd, check=True)
    return checkout


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha_state(root: Path, excludes: list[str] | None = None) -> dict[str, str]:
    excludes = excludes or []
    state: dict[str, str] = {}
    if not root.exists():
        return state
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if should_exclude(rel, excludes):
            continue
        state[rel] = file_hash(path)
    return state


def should_exclude(rel_path: str, excludes: list[str]) -> bool:
    path = Path(rel_path)
    for pattern in excludes:
        if path.match(pattern):
            return True
        if rel_path == pattern or rel_path.startswith(f"{pattern.rstrip('/')}/"):
            return True
    return False


def preserved_skill_frontmatter(src: Path, dst: Path) -> bytes:
    content = src.read_bytes()
    if src.name != "SKILL.md" or dst.name != "SKILL.md" or not dst.exists():
        return content

    try:
        src_text = content.decode("utf-8")
        dst_text = dst.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return content

    src_lines = src_text.splitlines(keepends=True)
    dst_lines = dst_text.splitlines(keepends=True)
    if not src_lines or src_lines[0].strip() != "---":
        return content
    if not dst_lines or dst_lines[0].strip() != "---":
        return content

    def closing_index(lines: list[str]) -> int | None:
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return index
        return None

    src_end = closing_index(src_lines)
    dst_end = closing_index(dst_lines)
    if src_end is None or dst_end is None:
        return content

    preserved: dict[str, str] = {}
    for line in dst_lines[1:dst_end]:
        key, separator, value = line.partition(":")
        key = key.strip()
        if separator and key in PRESERVED_SKILL_FRONTMATTER_FIELDS:
            preserved[key] = value.strip()

    if not preserved:
        return content

    newline = "\r\n" if "\r\n" in src_text else "\n"
    for key, value in preserved.items():
        replacement = f"{key}: {value}{newline}"
        existing_index = next(
            (
                index
                for index, line in enumerate(src_lines[1:src_end], start=1)
                if line.partition(":")[0].strip() == key
            ),
            None,
        )
        if existing_index is not None:
            src_lines[existing_index] = replacement
            continue

        name_index = next(
            (
                index
                for index, line in enumerate(src_lines[1:src_end], start=1)
                if line.partition(":")[0].strip() == "name"
            ),
            0,
        )
        src_lines.insert(name_index + 1, replacement)
        src_end += 1

    return "".join(src_lines).encode("utf-8")


def compare_file(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return False
    if src.name == "SKILL.md" and dst.name == "SKILL.md":
        return preserved_skill_frontmatter(src, dst) == dst.read_bytes()
    return filecmp.cmp(src, dst, shallow=False)


def compare_dir(src: Path, dst: Path, excludes: list[str]) -> bool:
    src_state = sha_state(src, excludes)
    dst_state = sha_state(dst, excludes)
    if src_state.keys() != dst_state.keys():
        return False
    return all(compare_file(src / rel, dst / rel) for rel in src_state)


def sync_file(src: Path, dst: Path) -> None:
    content = preserved_skill_frontmatter(src, dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if content != src.read_bytes():
        dst.write_bytes(content)


def sync_dir(src: Path, dst: Path, excludes: list[str]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    src_state = sha_state(src, excludes)
    dst_state = sha_state(dst, excludes)

    for rel in sorted(dst_state):
        if rel not in src_state:
            (dst / rel).unlink()

    for rel in sorted(src_state):
        src_file = src / rel
        dst_file = dst / rel
        sync_file(src_file, dst_file)

    # remove empty directories bottom-up
    for directory in sorted((p for p in dst.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if any(directory.iterdir()):
            continue
        directory.rmdir()


def mapping_status(checkout: Path, mapping: dict) -> tuple[str, Path, Path]:
    src = (checkout / mapping["from"]).resolve()
    dst = ensure_repo_relative(mapping["to"])
    optional = bool(mapping.get("optional"))
    mapping_type = mapping["type"]
    excludes = list(mapping.get("exclude", []))

    if not src.exists():
        if optional:
            return "optional-missing", src, dst
        raise SystemExit(f"上游路径不存在: {mapping['from']}")

    if mapping_type == "file":
        return ("unchanged" if compare_file(src, dst) else "changed"), src, dst

    if mapping_type == "dir":
        return ("unchanged" if compare_dir(src, dst, excludes) else "changed"), src, dst

    raise SystemExit(f"不支持的 mapping.type: {mapping_type}")


def apply_mapping(checkout: Path, mapping: dict) -> None:
    src = (checkout / mapping["from"]).resolve()
    dst = ensure_repo_relative(mapping["to"])
    optional = bool(mapping.get("optional"))
    excludes = list(mapping.get("exclude", []))
    if not src.exists():
        if optional:
            return
        raise SystemExit(f"上游路径不存在: {mapping['from']}")

    if mapping["type"] == "file":
        sync_file(src, dst)
        return

    if mapping["type"] == "dir":
        sync_dir(src, dst, excludes)
        return

    raise SystemExit(f"不支持的 mapping.type: {mapping['type']}")


def cmd_list(args: argparse.Namespace) -> int:
    _, rows = load_registry()
    if args.source_type:
        rows = [row for row in rows if row["source_type"] == args.source_type]

    if args.compact:
        for row in rows:
            print(row["skill"])
        return 0

    local_rows = [row for row in rows if row["source_type"] == "local"]
    external_rows = [row for row in rows if row["source_type"] == "external"]

    print(f"=== external ({len(external_rows)}) ===")
    for row in external_rows:
        key = row["source_key"] or "-"
        repo = "-"
        ref = "-"
        if row["source_key"]:
            manifest = load_manifest(row["source_key"])
            repo = manifest.get("repo", "-")
            ref = manifest.get("ref", "-")
        print(f"  {row['skill']:<24} [{row['status']:<13}] key={key:<18} ref={ref:<10} {repo}")

    print()
    print(f"=== local ({len(local_rows)}) ===")
    for row in local_rows:
        print(f"  {row['skill']:<24} [{row['status']:<13}] {row['source']}")

    print()
    print(f"合计: {len(rows)} 个 skill")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    fieldnames, rows = load_registry()
    by_skill = rows_by_skill(rows)
    row = by_skill.get(args.skill)
    if row is None:
        raise SystemExit(f"未找到 skill: {args.skill}")

    row["source"] = args.source_label or row["source"]
    row["source_type"] = args.source_type

    if args.source_type == "local":
        row["source_key"] = ""
        save_registry(fieldnames, rows)
        print(f"已标记为本地 skill: {args.skill}")
        return 0

    source_key = args.source_key or args.skill
    row["source_key"] = source_key

    if args.repo:
        if not args.path:
            raise SystemExit("外部 source 在创建 manifest 时必须提供 --path")
        SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
        upstream_root = "" if args.path in {".", "./"} else args.path.strip("/")
        mappings = []
        for mapping_type, from_part, to_part in COMMON_SIMPLE_PARTS:
            prefix = f"{upstream_root}/" if upstream_root else ""
            mappings.append(
                {
                    "type": mapping_type,
                    "from": f"{prefix}{from_part}",
                    "to": f"skills/{args.skill}/{to_part}",
                    "optional": mapping_type == "dir",
                }
            )
        manifest = {
            "key": source_key,
            "kind": "git",
            "repo": args.repo,
            "ref": args.ref,
            "mappings": mappings,
        }
        manifest_path(source_key).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save_registry(fieldnames, rows)
    print(f"已标记为外部 skill: {args.skill} -> {source_key}")
    return 0


def selected_external_rows(rows: list[dict[str, str]], skills: list[str]) -> list[dict[str, str]]:
    rows = [row for row in rows if row["source_type"] == "external"]
    if skills:
        selected = set(skills)
        rows = [row for row in rows if row["skill"] in selected]
    return rows


def cmd_update(args: argparse.Namespace) -> int:
    _, rows = load_registry()
    targets = selected_external_rows(rows, args.skills)
    if not targets:
        raise SystemExit("没有匹配到可更新的外部 skill")

    source_keys = sorted({row["source_key"] for row in targets if row["source_key"]})
    manifests = {}
    for key in source_keys:
        manifests[key] = load_manifest(key)

    # Validate the whole batch before cloning or writing any mapped target.
    manual_sources = []
    for key, manifest in manifests.items():
        policy = manifest.get("update_policy", "mapped")
        if policy not in ("mapped", "manual-release"):
            raise SystemExit(f"不支持的 update_policy: {key} -> {policy!r}")
        if policy == "manual-release":
            manual_sources.append(key)
    if args.apply and manual_sources:
        raise SystemExit(
            f"拒绝 --apply：update_policy=manual-release 来源：{', '.join(manual_sources)}。"
            "Git 中是 canonical 源码，运行包需从已构建发行包迁移；本批次不会 clone 或写入任何映射目标。"
        )

    with tempfile.TemporaryDirectory(prefix="xman-update-") as tmp:
        tmp_root = Path(tmp)
        checkouts: dict[str, Path] = {}

        for key in source_keys:
            manifest = manifests[key]
            repo = manifest["repo"]
            ref = manifest.get("ref", "main")
            print(f"=== {key} ===")
            print(f"repo: {repo}")
            print(f"ref : {ref}")
            if key in manual_sources:
                print("policy: manual-release（仅比对 Git 中 canonical 源码；运行包需从已构建发行包迁移，不能通过 --apply 升级）")
            checkout = clone_checkout(repo, ref, tmp_root / key)
            checkouts[key] = checkout

            target_skills = [row for row in targets if row["source_key"] == key]
            for row in target_skills:
                print(f"  skill: {row['skill']}")
                for mapping in manifest.get("mappings", []):
                    status, src, dst = mapping_status(checkout, mapping)
                    if status == "optional-missing":
                        print(f"    - skip optional: {mapping['from']}")
                        continue
                    print(f"    - {status:<10} {mapping['from']} -> {Path(mapping['to']).as_posix()}")
                    if args.apply and status == "changed":
                        apply_mapping(checkout, mapping)

        if args.apply:
            print()
            print("已应用更新。")
        else:
            print()
            if manual_sources:
                print("仅预览，未写入本地。manual-release 来源不能通过 --apply 升级；运行包需从已构建发行包人工迁移。")
            else:
                print("仅预览，未写入本地。追加 --apply 才会真正覆盖。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理外部来源 skill")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    list_parser = subparsers.add_parser("list", help="列出本地/外部来源标记")
    list_parser.add_argument("--source-type", choices=["local", "external"])
    list_parser.add_argument("--compact", action="store_true")
    list_parser.set_defaults(func=cmd_list)

    set_parser = subparsers.add_parser("set", help="标记 skill 来源")
    set_parser.add_argument("skill")
    set_parser.add_argument("--source-type", choices=["local", "external"], required=True)
    set_parser.add_argument("--source-label", help="覆盖 registry 的 source 列")
    set_parser.add_argument("--source-key", help="manifest key，默认等于 skill 名")
    set_parser.add_argument("--repo", help="git 仓库地址；提供时自动生成简单 manifest")
    set_parser.add_argument("--ref", default="main", help="跟踪分支或 tag，默认 main")
    set_parser.add_argument("--path", help="上游 skill 在仓库中的相对路径，例如 skills/docx")
    set_parser.set_defaults(func=cmd_set)

    update_parser = subparsers.add_parser("update", help="预览或应用外部 skill 更新")
    update_parser.add_argument("--skill", dest="skills", action="append", default=[], help="只更新指定 skill，可重复")
    update_parser.add_argument("--apply", action="store_true", help="真正写入本地；默认只预览")
    update_parser.set_defaults(func=cmd_update)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
