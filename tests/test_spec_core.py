import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "spec_core.py"
SPEC = importlib.util.spec_from_file_location("spec_core", MODULE_PATH)
assert SPEC and SPEC.loader
spec_core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(spec_core)


class SpecCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name).resolve()
        (self.project / "docs" / "specs").mkdir(parents=True)
        (self.project / "docs" / "SKILL-SPEC.md").write_text(
            "# Skill contract\n\nNames must match directories.\n",
            encoding="utf-8",
        )
        (self.project / "context").mkdir()
        (self.project / "context" / "platforms.md").write_text(
            "# Platform contract\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_index(self, specs: list[dict]) -> Path:
        path = self.project / "docs" / "specs" / "index.json"
        path.write_text(
            json.dumps({"version": 1, "specs": specs}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_validate_and_match_returns_all_applicable_specs(self) -> None:
        index = self.write_index(
            [
                {
                    "id": "skill-contract",
                    "source": "docs/SKILL-SPEC.md",
                    "description": "Skill contract",
                    "paths": ["skills/**/SKILL.md", "scripts/validate.sh"],
                },
                {
                    "id": "platform-contract",
                    "source": "context/platforms.md",
                    "description": "Platform contract",
                    "paths": ["scripts/sync-*.sh", "scripts/validate.sh"],
                },
            ]
        )

        loaded = spec_core.load_and_validate_index(self.project, index)

        skill_matches = spec_core.match_specs(
            loaded,
            "skills/review/SKILL.md",
        )
        shared_matches = spec_core.match_specs(loaded, "scripts/validate.sh")
        unrelated_matches = spec_core.match_specs(loaded, "README.md")

        self.assertEqual(["skill-contract"], [item["id"] for item in skill_matches])
        self.assertEqual(
            ["platform-contract", "skill-contract"],
            sorted(item["id"] for item in shared_matches),
        )
        self.assertEqual([], unrelated_matches)

    def test_validate_rejects_missing_source(self) -> None:
        index = self.write_index(
            [
                {
                    "id": "missing-source",
                    "source": "docs/missing.md",
                    "description": "Broken contract",
                    "paths": ["skills/**"],
                }
            ]
        )

        with self.assertRaisesRegex(spec_core.SpecValidationError, "事实源不存在"):
            spec_core.load_and_validate_index(self.project, index)

    def test_validate_rejects_non_utf8_source(self) -> None:
        source = self.project / "docs" / "binary.md"
        source.write_bytes(b"\xff\xfe")
        index = self.write_index(
            [
                {
                    "id": "binary-source",
                    "source": "docs/binary.md",
                    "description": "Broken encoding",
                    "paths": ["src/**"],
                }
            ]
        )

        with self.assertRaisesRegex(spec_core.SpecValidationError, "UTF-8"):
            spec_core.load_and_validate_index(self.project, index)

    def test_validate_rejects_non_utf8_index(self) -> None:
        index = self.project / "docs" / "specs" / "index.json"
        index.write_bytes(b"\xff\xfe")

        with self.assertRaisesRegex(spec_core.SpecValidationError, "UTF-8"):
            spec_core.load_and_validate_index(self.project, index)

    def test_validate_rejects_duplicate_ids_and_unsafe_paths(self) -> None:
        duplicate_index = self.write_index(
            [
                {
                    "id": "same",
                    "source": "docs/SKILL-SPEC.md",
                    "description": "One",
                    "paths": ["skills/**"],
                },
                {
                    "id": "same",
                    "source": "context/platforms.md",
                    "description": "Two",
                    "paths": ["scripts/**"],
                },
            ]
        )
        with self.assertRaisesRegex(spec_core.SpecValidationError, "重复"):
            spec_core.load_and_validate_index(self.project, duplicate_index)

        unsafe_index = self.write_index(
            [
                {
                    "id": "unsafe",
                    "source": "docs/SKILL-SPEC.md",
                    "description": "Unsafe",
                    "paths": ["../outside/**"],
                }
            ]
        )
        with self.assertRaisesRegex(spec_core.SpecValidationError, "越界"):
            spec_core.load_and_validate_index(self.project, unsafe_index)

    def test_validate_rejects_unsupported_glob_syntax(self) -> None:
        index = self.write_index(
            [
                {
                    "id": "unsupported-glob",
                    "source": "docs/SKILL-SPEC.md",
                    "description": "Unsupported character class",
                    "paths": ["src/[ab].py"],
                }
            ]
        )

        with self.assertRaisesRegex(spec_core.SpecValidationError, "暂不支持"):
            spec_core.load_and_validate_index(self.project, index)

    def test_normalize_target_rejects_files_outside_project(self) -> None:
        outside = self.project.parent / "outside.md"

        with self.assertRaisesRegex(spec_core.SpecValidationError, "项目之外"):
            spec_core.normalize_target_path(self.project, outside)


if __name__ == "__main__":
    unittest.main()
