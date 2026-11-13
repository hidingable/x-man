#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path


SECTIONS = [
    "Problem",
    "Avoid",
    "Replace With",
    "Decision Rule",
    "Verification",
    "Related Incidents",
]


def slugify(value: str, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_length].rstrip("-") or "pattern"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update a long-lived evolution pattern.")
    parser.add_argument("--root", required=True, help="Repository root where .ai-configs lives")
    parser.add_argument("--pattern", required=True, help="Pattern name")
    parser.add_argument("--problem", required=True, help="Core repeated problem")
    parser.add_argument("--avoid", required=True, help="What to avoid by default")
    parser.add_argument("--replace-with", required=True, dest="replace_with", help="Better replacement")
    parser.add_argument("--decision-rule", required=True, dest="decision_rule", help="How to choose the replacement")
    parser.add_argument("--verification", required=True, help="How to validate the rule")
    parser.add_argument("--incident", action="append", default=[], help="Related incident path, repeatable")
    parser.add_argument("--tag", action="append", default=[], help="Tag keyword, repeatable")
    return parser.parse_args()


def split_sections(content: str) -> tuple[list[str], dict[str, list[str]]]:
    lines = content.splitlines()
    preamble: list[str] = []
    sections: dict[str, list[str]] = {name: [] for name in SECTIONS}
    current: str | None = None

    for line in lines:
        if line.startswith("## "):
            title = line[3:].strip()
            current = title if title in sections else None
            continue
        if current is None:
            preamble.append(line)
        else:
            sections[current].append(line)

    return preamble, sections


def append_unique(section_lines: list[str], value: str) -> list[str]:
    item = f"- {value.strip()}"
    normalized_existing = {line.strip() for line in section_lines if line.strip()}
    if item not in normalized_existing:
        if section_lines and section_lines[-1].strip():
            section_lines.append(item)
        else:
            section_lines.append(item)
    return section_lines


def render(preamble: list[str], sections: dict[str, list[str]]) -> str:
    blocks = [line for line in preamble if line != ""]
    output = "\n".join(blocks).rstrip() + "\n\n"
    for name in SECTIONS:
        output += f"## {name}\n\n"
        lines = [line for line in sections[name] if line.strip()]
        if lines:
            output += "\n".join(lines) + "\n\n"
        else:
            output += "-\n\n"
    return output.rstrip() + "\n"


def main() -> int:
    args = parse_args()

    root = Path(args.root).resolve()
    pattern_dir = root / ".ai-configs" / "evolution" / "patterns"
    pattern_dir.mkdir(parents=True, exist_ok=True)

    template_path = Path(__file__).resolve().parents[1] / "assets" / "pattern-template.md"
    template = template_path.read_text(encoding="utf-8")
    now = datetime.now().isoformat(timespec="seconds")
    pattern_path = pattern_dir / f"{slugify(args.pattern)}.md"

    if not pattern_path.exists():
        initial = template.format(
            pattern=args.pattern.strip(),
            updated_at=now,
            tags=", ".join(tag.strip() for tag in args.tag if tag.strip()) or "-",
            problem=f"- {args.problem.strip()}",
            avoid=f"- {args.avoid.strip()}",
            replace_with=f"- {args.replace_with.strip()}",
            decision_rule=f"- {args.decision_rule.strip()}",
            verification=f"- {args.verification.strip()}",
            related_incidents="\n".join(
                f"- {incident.strip()}" for incident in args.incident if incident.strip()
            )
            or "-",
        )
        pattern_path.write_text(initial, encoding="utf-8")
        print(pattern_path)
        return 0

    content = pattern_path.read_text(encoding="utf-8")
    preamble, sections = split_sections(content)

    updated_preamble = []
    last_updated_replaced = False
    tags_replaced = False
    tag_value = ", ".join(tag.strip() for tag in args.tag if tag.strip()) or "-"

    for line in preamble:
        if line.startswith("- Last Updated:"):
            updated_preamble.append(f"- Last Updated: {now}")
            last_updated_replaced = True
            continue
        if line.startswith("- Tags:") and tag_value != "-":
            existing = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
            merged = existing[:]
            for tag in [tag.strip() for tag in args.tag if tag.strip()]:
                if tag not in merged:
                    merged.append(tag)
            updated_preamble.append(f"- Tags: {', '.join(merged)}")
            tags_replaced = True
            continue
        updated_preamble.append(line)

    if not last_updated_replaced:
        updated_preamble.append(f"- Last Updated: {now}")
    if not tags_replaced and tag_value != "-":
        updated_preamble.append(f"- Tags: {tag_value}")

    append_unique(sections["Problem"], args.problem)
    append_unique(sections["Avoid"], args.avoid)
    append_unique(sections["Replace With"], args.replace_with)
    append_unique(sections["Decision Rule"], args.decision_rule)
    append_unique(sections["Verification"], args.verification)
    for incident in args.incident:
        if incident.strip():
            append_unique(sections["Related Incidents"], incident)

    pattern_path.write_text(render(updated_preamble, sections), encoding="utf-8")
    print(pattern_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
