#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path


def slugify(value: str, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_length].rstrip("-") or "incident"


def bulletize(items: list[str], empty: str = "- (none)") -> str:
    cleaned = [item.strip() for item in items if item.strip()]
    if not cleaned:
        return empty
    return "\n".join(f"- {item}" for item in cleaned)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a structured evolution incident entry.")
    parser.add_argument("--root", required=True, help="Repository root where .ai-configs lives")
    parser.add_argument("--summary", required=True, help="One-line summary of the mistake")
    parser.add_argument("--trigger", required=True, help="Signal that caused the entry to be recorded")
    parser.add_argument("--category", required=True, help="Classification such as wrong-method")
    parser.add_argument("--symptom", required=True, help="Observed symptom")
    parser.add_argument("--wrong", required=True, help="Wrong action, assumption, or decision")
    parser.add_argument("--better", required=True, help="Better replacement method or technology")
    parser.add_argument("--guardrail", required=True, help="Default prevention rule for future work")
    parser.add_argument("--impact", default="-", help="Impact of the mistake")
    parser.add_argument("--evidence", action="append", default=[], help="Evidence item, repeatable")
    parser.add_argument("--file", action="append", default=[], help="Related file, repeatable")
    parser.add_argument("--tag", action="append", default=[], help="Tag keyword, repeatable")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    root = Path(args.root).resolve()
    now = datetime.now()
    incident_dir = root / ".ai-configs" / "evolution" / now.strftime("%Y") / now.strftime("%m")
    incident_dir.mkdir(parents=True, exist_ok=True)

    template_path = Path(__file__).resolve().parents[1] / "assets" / "incident-template.md"
    template = template_path.read_text(encoding="utf-8")

    filename = f"{now.strftime('%Y%m%d-%H%M%S')}-{slugify(args.summary)}.md"
    output_path = incident_dir / filename

    content = template.format(
        summary=args.summary.strip(),
        created_at=now.isoformat(timespec="seconds"),
        trigger=args.trigger.strip(),
        category=args.category.strip(),
        tags=", ".join(tag.strip() for tag in args.tag if tag.strip()) or "-",
        symptom=args.symptom.strip(),
        wrong=args.wrong.strip(),
        better=args.better.strip(),
        guardrail=args.guardrail.strip(),
        impact=args.impact.strip() or "-",
        evidence=bulletize(args.evidence),
        related_files=bulletize(args.file),
    )

    output_path.write_text(content, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
