"""guardrails：hook 的拦截判断与安装脚本的幂等、dry-run、卸载行为（脚本是 Node，与发行版同一份）。"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills/guardrails/scripts"
NODE = shutil.which("node")


def run_hook(command):
    return subprocess.run([NODE, str(SCRIPTS / "block-dangerous-git.mjs")],
                          input=json.dumps({"tool_input": {"command": command}}), capture_output=True, text=True)


def install(project, *args):
    return subprocess.run([NODE, str(SCRIPTS / "install.mjs"), "--scope", "project", "--project", str(project), *args],
                          capture_output=True, text=True)


@unittest.skipUnless(NODE, "需要 Node.js")
class GuardrailsTest(unittest.TestCase):
    def test_blocks_destructive_git(self):
        for command in ["git push", "git -C repo push", "git reset --hard HEAD~1", "git clean -fd",
                        "git branch -D feature", "git checkout -- .", "git restore ."]:
            r = run_hook(command)
            self.assertEqual(r.returncode, 2, command)
            self.assertIn("已拦截", r.stderr)

    def test_allows_daily_git(self):
        for command in ["git status", "git commit -m x", "git checkout -b feature", "git restore src/a.js", "git branch -d merged"]:
            self.assertEqual(run_hook(command).returncode, 0, command)

    def test_installer_idempotent_and_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            settings = project / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}), encoding="utf-8")
            dry = install(project, "--dry-run", "--json")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertFalse((project / ".claude/hooks").exists())
            self.assertEqual(install(project).returncode, 0)
            self.assertEqual(install(project).returncode, 0)
            saved = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["hooks"]["PreToolUse"]), 1)
            self.assertEqual(saved["permissions"], {"allow": ["Bash(ls)"]})
            self.assertEqual(install(project, "--uninstall").returncode, 0)
            after = json.loads(settings.read_text(encoding="utf-8"))
            self.assertNotIn("hooks", after)


if __name__ == "__main__":
    unittest.main()
