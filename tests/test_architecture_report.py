import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "skills" / "improve-codebase-architecture"
SCRIPT = ROOT / "scripts" / "render_report.py"
SPEC = importlib.util.spec_from_file_location("architecture_report", SCRIPT)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class ReportHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attributes = []
        self.text = []
        self.styles = []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)
        self.in_style = tag == "style"

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False

    def handle_data(self, data):
        self.text.append(data)
        if self.in_style:
            self.styles.append(data)


class RenderReportTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "assets" / "example-report.json").read_text(encoding="utf-8"))

    def test_report_preserves_evidence_and_cannot_execute_input_markup(self):
        attack = '</pre><script src="https://example.test/run.js">run()</script><img src=x>'
        self.data["candidates"][0]["current"] = attack
        self.data["candidates"][0]["evidence"].append(attack)
        document = ReportHTML()
        document.feed(report.render(self.data))
        self.assertIn(attack, "".join(document.text))
        self.assertFalse({"script", "img", "link", "iframe"}.intersection(document.tags))
        self.assertNotRegex("".join(document.styles), r"@import|url\s*\(")
        for key, value in document.attributes:
            if key in ("src", "href"):
                self.assertTrue(value.startswith("#"), value)
        for key in ("impact", "rationale"):
            self.assertIn(self.data["candidates"][0][key], "".join(document.text))
        self.assertEqual(2, document.tags.count("pre"))

    def test_candidates_require_evidence_and_recommendation_must_exist(self):
        for mutation in ("no-evidence", "unknown-recommendation", "duplicate-name"):
            with self.subTest(mutation=mutation):
                data = copy.deepcopy(self.data)
                if mutation == "no-evidence":
                    data["candidates"][0]["evidence"] = []
                elif mutation == "unknown-recommendation":
                    data["recommended_candidate"] = "不在报告中的候选"
                else:
                    data["candidates"].append(copy.deepcopy(data["candidates"][0]))
                with self.assertRaises(ValueError):
                    report.render(data)

    def test_empty_findings_are_rendered_without_inventing_a_candidate(self):
        self.data["candidates"] = []
        self.data["recommended_candidate"] = None
        self.data["summary"] = "调用路径和已有测试没有支持结构调整的证据。"
        document = ReportHTML()
        document.feed(report.render(self.data))
        self.assertNotIn("article", document.tags)
        self.assertIn(self.data["summary"], "".join(document.text))

    def test_single_skill_publish_contains_every_required_report_resource(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            published = subprocess.run(
                [str(ROOT.parents[1] / "xman"), "publish", "personal", "--target", str(bundle),
                 "--skill", "improve-codebase-architecture"],
                capture_output=True, text=True,
            )
            self.assertEqual(0, published.returncode, published.stdout + published.stderr)
            installed = bundle / "skills" / "improve-codebase-architecture"
            self.assertTrue(installed.is_dir())
            self.assertFalse((bundle / "skills" / "architect").exists())
            # Explicit local resource links must work inside this independently published skill.
            import re
            for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", (installed / "SKILL.md").read_text()):
                if target.startswith(("https://", "http://")):
                    continue
                self.assertTrue((installed / target).is_file(), target)
            rendered = subprocess.run(
                [sys.executable, str(installed / "scripts" / "render_report.py"),
                 "--input", str(installed / "assets" / "example-report.json"),
                 "--output", str(bundle / "report.html")],
                cwd=bundle, capture_output=True, text=True,
            )
            self.assertEqual(0, rendered.returncode, rendered.stderr)
            self.assertTrue((bundle / "report.html").is_file())

    def test_cli_dry_run_and_write_are_explicit_and_invalid_input_preserves_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            output = root / "nested" / "report.html"
            source.write_text(json.dumps(self.data), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output)]
            dry_run = subprocess.run(command + ["--dry-run"], capture_output=True, text=True)
            self.assertEqual(0, dry_run.returncode, dry_run.stderr)
            self.assertFalse(json.loads(dry_run.stdout)["written"])
            self.assertFalse(output.parent.exists())
            written = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, written.returncode, written.stderr)
            self.assertTrue(json.loads(written.stdout)["written"])
            before = output.read_bytes()
            self.assertIn("<!doctype html>", before.decode("utf-8"))
            source.write_text('{"candidates": []}', encoding="utf-8")
            failed = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(0, failed.returncode)
            self.assertIn("error", json.loads(failed.stderr))
            self.assertEqual(before, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
