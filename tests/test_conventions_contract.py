"""产物声明、路径正文和独立发行版的契约边界。"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/check-conventions.py"


class ConventionsContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="conventions-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "context").mkdir()
        (self.root / "skills/sample").mkdir(parents=True)
        shutil.copy2(CHECKER, self.root / "scripts/check-conventions.py")
        self.contract = {
            "version": 1, "taskId": "YYYY-MM-{slug}",
            "task": {"analysis": ".ai-configs/tasks/<task-id>/analysis.md"},
            "adHoc": {"analysis": ".ai-configs/analysis/YYYY/MM/{task-id}-{需求名称}-需求分析.md"},
        }
        self.write_side(self.root, self.contract, "analysis")

    def write_side(self, root, contract, output_type, *, omit_path=None):
        context = root / "context" if root == self.root else root
        context.mkdir(parents=True, exist_ok=True)
        (context / "naming-contract.json").write_text(json.dumps(contract), encoding="utf-8")
        paths = [contract["taskId"]]
        paths += [value for section in ("task", "adHoc", "global")
                  for value in contract.get(section, {}).values() if value != omit_path]
        (context / "conventions.md").write_text("\n".join(paths), encoding="utf-8")
        skill = root / "skills/sample/SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(
            "---\nname: sample\ndescription: fixture\nmetadata:\n"
            f"  outputs:\n    type: {output_type}\n---\n# Sample\n", encoding="utf-8",
        )

    def run_check(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(self.root / "scripts/check-conventions.py"), *args],
            capture_output=True, text=True, check=False, timeout=10,
        )

    def test_known_output_with_complete_local_paths_passes(self):
        result = self.run_check()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_unknown_declared_output_is_rejected(self):
        self.write_side(self.root, self.contract, "doc")
        result = self.run_check()
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("OUTPUT_UNDEFINED", result.stdout)
        self.assertIn("sample/SKILL.md", result.stdout)

    def test_local_paths_are_checked_without_a_distribution_checkout(self):
        self.write_side(self.root, self.contract, "analysis", omit_path=self.contract["task"]["analysis"])
        result = self.run_check()
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("PATH_DRIFT", result.stdout)

    def test_missing_mode_mapping_is_rejected(self):
        self.contract["task"]["doc"] = ".ai-configs/tasks/<task-id>/doc.md"
        self.write_side(self.root, self.contract, "doc")
        result = self.run_check()
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("MODE_MISSING", result.stdout)

    def test_global_output_does_not_require_a_task_mapping(self):
        self.contract["global"] = {"decisions": ".ai-configs/decisions/YYYY-MM-DD-{slug}.yaml"}
        self.write_side(self.root, self.contract, "decisions")
        result = self.run_check()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_runtime_entry_is_not_mistaken_for_a_declared_output_type(self):
        self.contract["task"]["stageState"] = ".ai-configs/tasks/<task-id>/.stage"
        self.write_side(self.root, self.contract, "analysis")
        result = self.run_check()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_default_check_does_not_depend_on_a_sibling_distribution(self):
        sibling = self.root.parent / "release-dist"
        sibling.mkdir()
        (sibling / "conventions.md").write_text("unrelated independently maintained version")
        result = self.run_check()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_agent_companion_cannot_reference_a_missing_conventions_section(self):
        companion = self.root / "agents/flow/references/prompt.md"
        companion.parent.mkdir(parents=True)
        companion.write_text("读取 `.ai-configs/conventions.md`〈不存在的规则〉。", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("SECTION_DANGLING", result.stdout)
        self.assertIn("agents/flow/references/prompt.md", result.stdout)

    def test_skill_reference_cannot_reference_a_missing_conventions_section(self):
        reference = self.root / "skills/sample/references/guide.md"
        reference.parent.mkdir()
        reference.write_text("读取 `.ai-configs/conventions.md`〈不存在的规则〉。", encoding="utf-8")
        result = self.run_check()
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("SECTION_DANGLING", result.stdout)
        self.assertIn("skills/sample/references/guide.md", result.stdout)

    def test_explicit_distribution_uses_its_own_types_and_checks_shared_paths(self):
        distribution = self.root.parent / "release-dist"
        wf_contract = json.loads(json.dumps(self.contract))
        self.write_side(distribution, wf_contract, "analysis")
        self.contract["task"]["doc"] = ".ai-configs/tasks/<task-id>/doc.md"
        self.contract["adHoc"]["doc"] = ".ai-configs/docs/YYYY/MM/{task-id}-{需求名称}-文档.md"
        self.write_side(self.root, self.contract, "doc")
        result = self.run_check("--wf", str(distribution))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        wf_contract["task"]["analysis"] = ".ai-configs/tasks/<task-id>/other-analysis.md"
        self.write_side(distribution, wf_contract, "analysis")
        result = self.run_check("--wf", str(distribution))
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("PATH_DRIFT", result.stdout)


if __name__ == "__main__":
    unittest.main()
