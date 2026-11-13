import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISH = REPO_ROOT / "scripts" / "publish-team.sh"
BOOTSTRAP = REPO_ROOT / "scripts" / "bootstrap-repo.sh"


class PublishedSkillBundleTest(unittest.TestCase):
    def test_bootstrap_copies_publish_readme_template_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "skeleton"

            result = subprocess.run(
                [str(BOOTSTRAP), str(target)],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(
                (
                    target
                    / "context"
                    / "templates"
                    / "published-skill-bundle-readme.md"
                ).is_file()
            )

    def test_publish_uses_skill_bundle_readme_without_xman_runtime_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "bundle"

            result = subprocess.run(
                [str(PUBLISH), "--target", str(target), "--skill", "brainstorm"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            readme = (target / "README.md").read_text(encoding="utf-8")
            self.assertIn("Skill Bundle", readme)
            self.assertIn("不包含 `xman`", readme)
            self.assertNotIn("xman spec", readme)
            self.assertTrue((target / "skills" / "brainstorm" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
