"""只读命令的 --json 输出。

规范写在 context/conventions.md〈给 agent 用的工具〉：给 agent 的输出要机器可读。
这里盯的主要是转义——title、note 这类字段是人随手写的，制表符、引号、反斜杠都可能有，
拼 JSON 拼坏了 agent 拿到的就是烂数据。
"""

import json
import os
import pathlib
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TASK_SH = REPO_ROOT / "scripts" / "task.sh"
LIST_SH = REPO_ROOT / "scripts" / "list.sh"

NASTY_TITLE = '登录"改造"\t流程 C:\\new'      # 引号 + 制表符 + 反斜杠


class TaskJsonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = pathlib.Path(self.tmp.name)
        (self.project / ".ai-configs" / "tasks").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def task(self, *args):
        return subprocess.run(["bash", str(TASK_SH), *args], capture_output=True,
                              text=True, cwd=str(self.project), timeout=30,
                              env={**os.environ})

    def test_没有_task_时给空数组而不是报错文本(self):
        (self.project / ".ai-configs" / "tasks").rmdir()
        r = self.task("list", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"tasks": []})

    def test_title_里的制表符不会把字段冲串(self):
        self.task("new", "login-revamp", "--title", NASTY_TITLE)
        r = self.task("list", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        task = json.loads(r.stdout)["tasks"][0]
        self.assertEqual(task["stage"], "in_progress")        # 没被挤走
        self.assertIn("C:\\new", task["title"])               # 反斜杠原样保留
        self.assertIn('"改造"', task["title"])                 # 引号正确转义
        self.assertNotIn("\t", task["title"])                 # 制表符已换成空格

    def test_current_是布尔不是字符串(self):
        self.task("new", "a")
        self.task("new", "b")
        ids = [t["id"] for t in json.loads(self.task("list", "--json").stdout)["tasks"]]
        self.task("use", ids[0])
        tasks = json.loads(self.task("list", "--json").stdout)["tasks"]
        flags = {t["id"]: t["current"] for t in tasks}
        self.assertIs(flags[ids[0]], True)
        self.assertIs(flags[ids[1]], False)

    def test_current_子命令的_json(self):
        self.task("new", "a")
        the_id = json.loads(self.task("list", "--json").stdout)["tasks"][0]["id"]
        self.assertEqual(json.loads(self.task("current", "--json").stdout), {"task": ""})
        self.task("use", the_id)
        self.assertEqual(json.loads(self.task("current", "--json").stdout), {"task": the_id})

    def test_find_的_json_带产物列表(self):
        self.task("new", "login-revamp", "--title", NASTY_TITLE)
        r = self.task("find", "login", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["keyword"], "login")
        self.assertEqual(len(out["tasks"]), 1)
        self.assertIsInstance(out["tasks"][0]["artifacts"], list)

    def test_人读输出没被破坏(self):
        self.task("new", "a", "--title", "普通标题")
        r = self.task("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("=== Task 列表 ===", r.stdout)
        self.assertIn("普通标题", r.stdout)


class ListJsonTest(unittest.TestCase):
    def run_list(self, *args):
        return subprocess.run(["bash", str(LIST_SH), *args], capture_output=True,
                              text=True, cwd=str(REPO_ROOT), timeout=60)

    def test_每个_skill_都有非空_description(self):
        r = self.run_list("--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        skills = json.loads(r.stdout)["skills"]
        self.assertGreater(len(skills), 20)
        empty = [s["name"] for s in skills if not s["description"]]
        self.assertEqual(empty, [], f"这些 skill 的 description 没解析出来: {empty}")

    def test_description_不截断(self):
        skills = json.loads(self.run_list("--json").stdout)["skills"]
        human = self.run_list("--plugin", "engineering").stdout
        self.assertNotIn("...", max((s["description"] for s in skills), key=len)[-10:])
        self.assertIn("...", human)          # 人读版才截断

    def test_plugin_过滤同时作用于两种输出(self):
        j = json.loads(self.run_list("--json", "--plugin", "engineering").stdout)["skills"]
        compact = self.run_list("--compact", "--plugin", "engineering").stdout.split()
        self.assertEqual(sorted(s["name"] for s in j), sorted(compact))


if __name__ == "__main__":
    unittest.main()
