import argparse
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "source-manager.py"
SPEC = importlib.util.spec_from_file_location("source_manager", MODULE_PATH)
assert SPEC and SPEC.loader
source_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source_manager)


class SourceManagerPreservedFrontmatterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_dir.name) / "repo"
        self.checkout = Path(self.temp_dir.name) / "checkout"
        self.repo_root.mkdir()
        self.checkout.mkdir()
        self.repo_root = self.repo_root.resolve()
        self.checkout = self.checkout.resolve()
        self.original_repo_root = source_manager.REPO_ROOT
        source_manager.REPO_ROOT = self.repo_root

    def tearDown(self) -> None:
        source_manager.REPO_ROOT = self.original_repo_root
        self.temp_dir.cleanup()

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_file_mapping_preserves_disable_model_invocation(self) -> None:
        source = self.checkout / "skills" / "example" / "SKILL.md"
        destination = self.repo_root / "skills" / "example" / "SKILL.md"
        self.write(source, "---\nname: example\ndescription: upstream\n---\n\nNew body\n")
        self.write(
            destination,
            "---\nname: example\ndisable-model-invocation: true\ndescription: local\n---\n\nOld body\n",
        )
        mapping = {
            "type": "file",
            "from": "skills/example/SKILL.md",
            "to": "skills/example/SKILL.md",
        }

        source_manager.apply_mapping(self.checkout, mapping)

        content = destination.read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("description: upstream", content)
        self.assertIn("New body", content)
        self.assertEqual("unchanged", source_manager.mapping_status(self.checkout, mapping)[0])

    def test_directory_mapping_preserves_nested_skill_frontmatter(self) -> None:
        source = self.checkout / "bundle"
        destination = self.repo_root / "skills" / "example"
        self.write(source / "SKILL.md", "---\nname: example\ndescription: upstream\n---\n\nNew body\n")
        self.write(source / "references" / "guide.md", "upstream guide\n")
        self.write(
            destination / "SKILL.md",
            "---\nname: example\ndisable-model-invocation: true\ndescription: local\n---\n\nOld body\n",
        )
        mapping = {
            "type": "dir",
            "from": "bundle",
            "to": "skills/example",
        }

        source_manager.apply_mapping(self.checkout, mapping)

        content = (destination / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", content)
        self.assertEqual("upstream guide\n", (destination / "references" / "guide.md").read_text(encoding="utf-8"))
        self.assertEqual("unchanged", source_manager.mapping_status(self.checkout, mapping)[0])


class SourceManagerUpdatePolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        self.repo_root = self.root / "repo"
        self.checkout = self.root / "checkout"
        self.destination = self.repo_root / "skills" / "example" / "runtime.txt"
        self.destination.parent.mkdir(parents=True)
        self.destination.write_text("existing runtime 0.1.17", encoding="utf-8")
        self.checkout.mkdir()
        (self.checkout / "canonical.txt").write_text("new canonical source", encoding="utf-8")
        patcher = mock.patch.object(source_manager, "REPO_ROOT", self.repo_root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mapping = {"type": "file", "from": "canonical.txt", "to": "skills/example/runtime.txt"}

    def manifest(self, policy=None):
        result = {"repo": "https://github.com/example/upstream.git", "ref": "main", "mappings": [self.mapping]}
        if policy is not None:
            result["update_policy"] = policy
        return result

    def command(self, manifests):
        rows = [{"skill": key, "source_key": key, "source_type": "external"} for key in manifests]
        return (mock.patch.object(source_manager, "load_registry", return_value=([], rows)),
                mock.patch.object(source_manager, "load_manifest", side_effect=manifests.__getitem__),
                mock.patch.object(source_manager, "clone_checkout", return_value=self.checkout))

    def run_update(self, manifests, apply):
        registry, loader, clone = self.command(manifests)
        output = io.StringIO()
        with registry, loader, clone as clone_mock, contextlib.redirect_stdout(output):
            result = source_manager.cmd_update(argparse.Namespace(skills=[], apply=apply))
        return result, output.getvalue(), clone_mock

    def test_manual_release_apply_refuses_before_clone_or_write(self):
        registry, loader, clone = self.command({"security": self.manifest("manual-release")})
        with registry, loader, clone as clone_mock:
            with self.assertRaisesRegex(SystemExit, "manual-release") as caught:
                source_manager.cmd_update(argparse.Namespace(skills=[], apply=True))
        clone_mock.assert_not_called()
        self.assertIn("canonical", str(caught.exception))
        self.assertIn("发行包", str(caught.exception))
        self.assertEqual("existing runtime 0.1.17", self.destination.read_text(encoding="utf-8"))

    def test_mixed_batch_refuses_without_partial_write(self):
        manifests = {"a-mapped": self.manifest(), "z-manual": self.manifest("manual-release")}
        registry, loader, clone = self.command(manifests)
        with registry, loader as loader_mock, clone as clone_mock:
            with self.assertRaisesRegex(SystemExit, "manual-release"):
                source_manager.cmd_update(argparse.Namespace(skills=[], apply=True))
        self.assertEqual([mock.call("a-mapped"), mock.call("z-manual")], loader_mock.call_args_list)
        clone_mock.assert_not_called()
        self.assertEqual("existing runtime 0.1.17", self.destination.read_text(encoding="utf-8"))

    def test_manual_preview_compares_without_apply_advice(self):
        result, output, clone = self.run_update({"security": self.manifest("manual-release")}, False)
        self.assertEqual(0, result)
        clone.assert_called_once()
        self.assertIn("changed", output)
        self.assertIn("manual-release", output)
        self.assertIn("canonical", output)
        self.assertNotIn("追加 --apply", output)
        self.assertEqual("existing runtime 0.1.17", self.destination.read_text(encoding="utf-8"))

    def test_mixed_preview_compares_all_sources_without_writing(self):
        manifests = {"a-mapped": self.manifest(), "z-manual": self.manifest("manual-release")}
        result, output, clone = self.run_update(manifests, False)
        self.assertEqual(0, result)
        self.assertEqual(2, clone.call_count)
        self.assertIn("=== a-mapped ===", output)
        self.assertIn("=== z-manual ===", output)
        self.assertNotIn("追加 --apply", output)
        self.assertEqual("existing runtime 0.1.17", self.destination.read_text(encoding="utf-8"))

    def test_unknown_policy_rejected_before_clone_in_preview_and_apply(self):
        for apply in (False, True):
            for invalid in ("unknown", "", ["mapped"], False, None):
                with self.subTest(apply=apply, invalid=invalid):
                    invalid_manifest = self.manifest()
                    invalid_manifest["update_policy"] = invalid
                    manifests = {"a-mapped": self.manifest(), "z-invalid": invalid_manifest}
                    registry, loader, clone = self.command(manifests)
                    with registry, loader, clone as clone_mock:
                        with self.assertRaisesRegex(SystemExit, "update_policy"):
                            source_manager.cmd_update(argparse.Namespace(skills=[], apply=apply))
                    clone_mock.assert_not_called()
                    self.assertEqual("existing runtime 0.1.17", self.destination.read_text(encoding="utf-8"))

    def test_mapped_default_and_explicit_policy_keep_apply_behavior(self):
        for policy in (None, "mapped"):
            with self.subTest(policy=policy):
                result, output, clone = self.run_update({"example": self.manifest(policy)}, True)
                self.assertEqual(0, result)
                clone.assert_called_once()
                self.assertIn("已应用更新", output)
                self.assertEqual("new canonical source", self.destination.read_text(encoding="utf-8"))
                self.destination.write_text("existing runtime 0.1.17", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
