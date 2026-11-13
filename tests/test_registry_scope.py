"""公开源码的个人项缺省边界，防止把误删或坏软链当作合法缺省。"""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("registry_scope", ROOT / "scripts/registry_scope.py")
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)


class RegistryScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "skills").mkdir()
        self.row = {"skill": "private", "status": "personal-only", "type": "skill"}
        (self.repo / ".gitignore").write_text("skills/private/\n")

    def missing(self, **overrides):
        return scope.optional_missing_skills(self.repo, [{**self.row, **overrides}])

    def test_only_explicit_missing_personal_directory_is_optional(self):
        self.assertEqual({"private"}, self.missing())
        for overrides in ({"status": "team-shared"}, {"status": "experimental"}, {"type": "agent"}):
            with self.subTest(overrides=overrides):
                self.assertEqual(set(), self.missing(**overrides))
        (self.repo / ".gitignore").write_text("skills/*/\n")
        self.assertEqual(set(), self.missing(), "宽泛 ignore 不能授权缺省")
        (self.repo / ".gitignore").write_text("/skills/private/\n")
        self.assertEqual({"private"}, self.missing())

    def test_deleted_tracked_private_skill_is_not_optional(self):
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        private = self.repo / "skills/private"
        private.mkdir()
        source = private / "SKILL.md"
        source.write_text("tracked source")
        subprocess.run(["git", "-C", str(self.repo), "add", "-f", "skills/private/SKILL.md"], check=True)
        source.unlink()
        private.rmdir()
        self.assertEqual(set(), self.missing())

    def test_info_exclude_does_not_authorize_missing_private_skill(self):
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / ".gitignore").unlink()
        (self.repo / ".git/info/exclude").write_text("skills/private/\n")
        self.assertEqual(set(), self.missing())

    def test_existing_incomplete_and_broken_source_nodes_are_not_optional(self):
        private = self.repo / "skills/private"
        private.mkdir()
        self.assertEqual(set(), self.missing())
        private.rmdir()
        private.symlink_to("missing")
        self.assertEqual(set(), self.missing())
        private.unlink()
        private.write_text("not a directory")
        self.assertEqual(set(), self.missing())

    def test_only_correct_same_named_category_link_is_optional(self):
        group = self.repo / "plugins/infra"
        group.mkdir(parents=True)
        link = group / "private"
        link.symlink_to("../../skills/private")
        self.assertTrue(scope.optional_missing_link(self.repo, link, self.missing()))
        link.unlink()
        link.symlink_to("../../skills/misspelled")
        self.assertFalse(scope.optional_missing_link(self.repo, link, self.missing()))
        alias = group / "alias"
        alias.symlink_to("../../skills/private")
        self.assertFalse(scope.optional_missing_link(self.repo, alias, self.missing()))
        self.assertFalse(scope.optional_missing_link(self.repo, link, set()))


if __name__ == "__main__":
    unittest.main()
