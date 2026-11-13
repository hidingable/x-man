"""治理登记表与实际可安装集合的一致性。

背景：`status` 决定 `xman install --status team-shared` 装哪些。编排器引用的 skill
如果标着 experimental，新机器按 CLAUDE.md 里那条默认命令装完，编排器会引用到一批
根本没装的 skill——流程走到一半发现工具不在。这个缺陷 2026-09-10 修过一次
（验证、复盘、收尾、记忆四类当时全是 experimental），这里把不变量钉住。
"""

import csv
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "governance" / "skills-registry.csv"
AGENTS_DIR = REPO_ROOT / "agents"
SKILLS_DIR = REPO_ROOT / "skills"


def registry_rows():
    return list(csv.DictReader(REGISTRY.open(newline="", encoding="utf-8")))


def agent_definitions() -> list[pathlib.Path]:
    """agent 定义是扁平的 agents/<name>.md，且带 YAML front-matter。
    README.md 这类说明文档首行不是 `---`，照 check-flow-drift.py 的判定方式排除。"""
    out = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        head = path.read_text(encoding="utf-8").split("\n", 1)[0]
        if head.strip() == "---":
            out.append(path)
    return out


def orchestrated_skills(agent_md: pathlib.Path) -> list[str]:
    text = agent_md.read_text(encoding="utf-8")
    m = re.search(r"^\s*orchestrates:\s*\[([^\]]*)\]", text, re.M)
    if not m:
        return []
    return [s.strip() for s in m.group(1).split(",") if s.strip()]


class GovernanceTest(unittest.TestCase):
    def test_编排器引用的_skill_必须在默认安装集里(self):
        rows = {r["skill"]: r for r in registry_rows()}
        for agent_md in agent_definitions():
            for skill in orchestrated_skills(agent_md):
                with self.subTest(agent=agent_md.name, skill=skill):
                    self.assertIn(skill, rows, f"{skill} 没登记进 registry")
                    self.assertEqual(
                        rows[skill]["status"], "team-shared",
                        f"{agent_md.name} 编排了 {skill}，但它是 "
                        f"{rows[skill]['status']}，"
                        f"`xman install --status team-shared` 装不到它")

    def test_编排器引用的_skill_目录必须存在(self):
        for agent_md in agent_definitions():
            for skill in orchestrated_skills(agent_md):
                with self.subTest(agent=agent_md.name, skill=skill):
                    self.assertTrue((SKILLS_DIR / skill / "SKILL.md").is_file(),
                                    f"{agent_md.name} 编排了不存在的 skill: {skill}")

    def test_每个_skill_目录都有登记(self):
        registered = {r["skill"] for r in registry_rows()}
        on_disk = {d.name for d in SKILLS_DIR.iterdir()
                   if d.is_dir() and not d.name.startswith(".")}
        self.assertEqual(on_disk - registered, set(), "这些 skill 没进 registry")

    def test_status_取值受限(self):
        """deprecated 是墓碑行专用（type 也必须是 deprecated），活着的条目只有三种。"""
        live = {"team-shared", "personal-only", "experimental"}
        bad = {}
        for r in registry_rows():
            if r["status"] == "deprecated":
                if r["type"] != "deprecated":
                    bad[r["skill"]] = "status=deprecated 但 type 不是 deprecated"
            elif r["status"] not in live:
                bad[r["skill"]] = r["status"]
        self.assertEqual(bad, {}, f"活着的条目 status 只允许 {live}；"
                                  "deprecated 仅用于已移除 skill 的墓碑行")

    def test_墓碑行不应该还有_skill_目录(self):
        for r in registry_rows():
            if r["type"] == "deprecated":
                with self.subTest(skill=r["skill"]):
                    self.assertFalse((SKILLS_DIR / r["skill"]).exists(),
                                     f"{r['skill']} 标着 deprecated，但目录还在")


if __name__ == "__main__":
    unittest.main()
