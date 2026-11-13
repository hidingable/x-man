"""xman features（Feature Map）的行为测试。"""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "scripts" / "features.py"


class FeaturesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = pathlib.Path(self.tmp.name)
        (self.project / ".ai-configs").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True,
                              cwd=str(cwd or self.project), timeout=30)

    def test_init_建索引_重复跑不覆盖(self):
        r = self.run_cli("init", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["created"])
        index = self.project / ".ai-configs" / "features" / "README.md"
        index.write_text("我改过的索引", encoding="utf-8")
        again = self.run_cli("init", "--json")
        self.assertFalse(json.loads(again.stdout)["created"])
        self.assertEqual(index.read_text(encoding="utf-8"), "我改过的索引")

    def test_init_的_dry_run_不落文件(self):
        r = self.run_cli("init", "--dry-run", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.project / ".ai-configs" / "features").exists())

    def test_没_init_就_new_会指出下一步(self):
        r = self.run_cli("new", "settings")
        self.assertEqual(r.returncode, 1)
        self.assertIn("xman features init", r.stderr)

    def test_new_的条目带五段和待确认标记(self):
        self.run_cli("init")
        r = self.run_cli("new", "settings", "--title", "偏好设置", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.project / ".ai-configs" / "features" / "settings.md").read_text(encoding="utf-8")
        for section in ("子功能", "从用户视角怎么到达", "怎么用工具驱动它", "坑"):
            self.assertIn(f"## {section}", text)
        self.assertIn("偏好设置", text)
        self.assertIn("⟨待确认⟩", text)

    def test_slug_不合法时说清楚规则(self):
        self.run_cli("init")
        r = self.run_cli("new", "Settings_V2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("小写字母", r.stderr)

    def test_重复_new_不覆盖已有条目(self):
        self.run_cli("init")
        self.run_cli("new", "settings")
        path = self.project / ".ai-configs" / "features" / "settings.md"
        path.write_text("# 我写好的内容", encoding="utf-8")
        r = self.run_cli("new", "settings")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "# 我写好的内容")

    def test_check_区分空地图_不完整_和完整(self):
        self.run_cli("init")
        empty = self.run_cli("check", "--json")
        self.assertEqual(empty.returncode, 1)          # 空地图

        self.run_cli("new", "settings")
        partial = self.run_cli("check", "--json")
        self.assertEqual(partial.returncode, 2)        # 有待填
        self.assertTrue(json.loads(partial.stdout)["problems"])

        path = self.project / ".ai-configs" / "features" / "settings.md"
        path.write_text("# 偏好设置\n\n齿轮里的设置面板。\n\n"
                        "## 子功能\n\n- `theme`：换主题\n\n"
                        "## 从用户视角怎么到达\n\n点右上角齿轮。\n\n"
                        "## 怎么用工具驱动它\n\n```bash\ncurl .../click -d '.gear'\n```\n\n"
                        "## 坑\n\n- 关掉后焦点会丢\n", encoding="utf-8")
        full = self.run_cli("check", "--json")
        self.assertEqual(full.returncode, 0, full.stdout)
        self.assertEqual(json.loads(full.stdout)["problems"], [])

    def test_check_能指出缺了哪一段(self):
        self.run_cli("init")
        (self.project / ".ai-configs" / "features" / "x.md").write_text(
            "# X\n\n说明\n\n## 子功能\n\n- a\n", encoding="utf-8")
        r = self.run_cli("check", "--json")
        self.assertEqual(r.returncode, 2)
        missing = [p["detail"] for p in json.loads(r.stdout)["problems"] if p["kind"] == "缺段"]
        self.assertIn("怎么用工具驱动它", missing)

    def test_list_标出完整度(self):
        self.run_cli("init")
        self.run_cli("new", "settings")
        r = self.run_cli("list", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        item = json.loads(r.stdout)["features"][0]
        self.assertEqual(item["slug"], "settings")
        self.assertGreater(item["todo"], 0)

    def test_找不到_ai_configs_时指向_context_init(self):
        bare = pathlib.Path(self.tmp.name) / "bare"
        (bare / ".git").mkdir(parents=True)
        r = self.run_cli("list", cwd=bare)
        self.assertEqual(r.returncode, 1)
        self.assertIn("xman context init", r.stderr)

    def test_每个子命令都有独立_help_和例子(self):
        for cmd in ("init", "new", "list", "check"):
            r = self.run_cli(cmd, "--help")
            self.assertEqual(r.returncode, 0, cmd)
            self.assertIn("例子:", r.stdout, cmd)


if __name__ == "__main__":
    unittest.main()
