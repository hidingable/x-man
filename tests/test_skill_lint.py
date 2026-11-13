"""skill 正文的静态检查：字数上限、代号写法、调用方式声明。

只检查本仓维护的 skill（registry 里 source_type=local），外部同步来的不管：改了也会被下次同步覆盖。
conventions 小节引用的有效性由 scripts/check-conventions.py 负责，这里不重复。
行为层面的效果由 scripts/eval-run.py 衡量。
"""

import csv
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "governance/skills-registry.csv"


def local_skills():
    with REGISTRY.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return sorted(
        r["skill"] for r in rows
        if r["type"] == "skill" and r["source_type"] == "local" and (ROOT / f"skills/{r['skill']}/SKILL.md").exists()
    )


def prose(text):
    """代码块、行内反引号和引号里的内容是对规则的引用或示例，不算正文。"""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    return re.sub(r"“[^”\n]*”|「[^」\n]*」", "", text)


SKILLS = local_skills()
DOCUMENTS = [f"skills/{name}/SKILL.md" for name in SKILLS] + ["agents/xman-flow.md", "context/conventions.md"]

# 判据与 conventions〈表达与命名〉一致：读者需要翻回去查对照表才懂的标识
CODE_NAMES = [
    re.compile(r"\b(Phase|Layer)\s*\d+"),
    re.compile(r"方案\s*[A-F](?![A-Za-z])"),
    re.compile(r"步骤\s*\d+\.\d+"),
]


class SkillLintTest(unittest.TestCase):
    def test_budgets_registered_and_respected(self):
        limits = json.loads((ROOT / "evals/budgets.json").read_text(encoding="utf-8"))["limits"]
        missing = [d for d in DOCUMENTS if d not in limits]
        self.assertEqual(missing, [], f"evals/budgets.json 缺少上限：{', '.join(missing)}")
        over = [
            f"{d}：{len((ROOT / d).read_text(encoding='utf-8'))} > {limits[d]}"
            for d in DOCUMENTS if len((ROOT / d).read_text(encoding="utf-8")) > limits[d]
        ]
        self.assertEqual(over, [], "超出字数上限，先删减正文；确有必要再调高 evals/budgets.json：\n" + "\n".join(over))

    def test_no_code_names_in_prose(self):
        offenders = []
        for d in DOCUMENTS:
            for i, line in enumerate(prose((ROOT / d).read_text(encoding="utf-8")).split("\n"), 1):
                if any(p.search(line) for p in CODE_NAMES):
                    offenders.append(f"{d}:{i}  {line.strip()}")
        self.assertEqual(offenders, [], "改成实际名称：\n" + "\n".join(offenders))

    def test_prohibition_count_report(self):
        """只报告，不失败。"""
        counts = sorted(
            ((d, len(re.findall(r"不得|不要|不能", prose((ROOT / d).read_text(encoding="utf-8"))))) for d in DOCUMENTS),
            key=lambda x: -x[1],
        )
        total = sum(n for _, n in counts)
        top = "，".join(f"{d} {n}" for d, n in counts[:5])
        print(f"\n「不得 / 不要 / 不能」共 {total} 处；最多的：{top}")

    def test_invocation_declared(self):
        # 只能人触发写 true，模型可调用写 false；显式写出来，新增 skill 时就不会漏掉这个决定
        undeclared = [
            name for name in SKILLS
            if not re.search(r"^disable-model-invocation:\s*(true|false)\s*$",
                             (ROOT / f"skills/{name}/SKILL.md").read_text(encoding="utf-8"), re.M)
        ]
        self.assertEqual(undeclared, [], f"frontmatter 缺少 disable-model-invocation：{', '.join(undeclared)}")

    def test_codex_policy_matches_frontmatter(self):
        # Codex 用 agents/openai.yaml 的 policy 控制隐式调用；一个 skill 要么两个宿主都只能人触发，要么都不是
        mismatched = []
        for name in SKILLS:
            user_only = re.search(r"^disable-model-invocation:\s*true\s*$",
                                  (ROOT / f"skills/{name}/SKILL.md").read_text(encoding="utf-8"), re.M) is not None
            yaml = ROOT / f"skills/{name}/agents/openai.yaml"
            codex_off = yaml.exists() and re.search(r"^\s+allow_implicit_invocation:\s*false\s*$",
                                                    yaml.read_text(encoding="utf-8"), re.M) is not None
            if user_only != codex_off:
                mismatched.append(name)
        self.assertEqual(mismatched, [], f"SKILL.md 与 agents/openai.yaml 的调用方式不一致：{', '.join(mismatched)}")

    def test_cross_skill_references_exist(self):
        # 跨 skill 引用写成「skill 安装目录里的 `<skill>/references/x.md`」，各种装法里 skill 都是同级目录
        missing = []
        docs = list(ROOT.glob("skills/*/SKILL.md")) + list(ROOT.glob("agents/**/*.md")) + [ROOT / "context/conventions.md"]
        for doc in docs:
            for skill, ref in re.findall(r"skill 安装目录里的 `([a-z][a-z0-9-]*)/(references/[^`]+)`", doc.read_text(encoding="utf-8")):
                if not (ROOT / "skills" / skill / ref).exists():
                    missing.append(f"{doc.relative_to(ROOT)}：skills/{skill}/{ref}")
        self.assertEqual(missing, [], "引用的文件不存在：\n" + "\n".join(missing))

    def test_router_covers_user_invoked_skills(self):
        # 路由要覆盖每个人触发的 skill：新增、改名、删除 skill 时忘了更新 ask-xman，路由就会指错路
        router = (ROOT / "skills/ask-xman/SKILL.md").read_text(encoding="utf-8")
        missing = [
            name for name in SKILLS
            if name != "ask-xman"
            and re.search(r"^disable-model-invocation:\s*true\s*$", (ROOT / f"skills/{name}/SKILL.md").read_text(encoding="utf-8"), re.M)
            and f"/{name}" not in router
        ]
        self.assertEqual(missing, [], f"ask-xman 没有提到：{', '.join(missing)}")


if __name__ == "__main__":
    unittest.main()
