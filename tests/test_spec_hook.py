import json
import subprocess
import tempfile
import unittest
from pathlib import Path


HOOK = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "spec-pre-tool-use.py"


class SpecPreToolUseHookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name).resolve()
        (self.project / ".ai-configs" / "specs").mkdir(parents=True)
        (self.project / "docs").mkdir()
        self.source = self.project / "docs" / "contract.md"
        self.source.write_text("# Contract\n\nRead this before writing.\n", encoding="utf-8")
        self.index = self.project / ".ai-configs" / "specs" / "index.json"
        self.index.write_text(
            json.dumps(
                {
                    "version": 1,
                    "specs": [
                        {
                            "id": "source-contract",
                            "source": "docs/contract.md",
                            "description": "Source contract",
                            "paths": ["src/**"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def invoke(self, payload: dict) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(HOOK)],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )

    def write_payload(self, path: str = "src/example.py") -> dict:
        return {
            "session_id": "session-1",
            "cwd": str(self.project),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": path},
        }

    def acknowledge(self, *spec_ids: str, session_id: str = "session-1") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(HOOK),
                "--spec-id",
                *spec_ids,
                "--session-id",
                session_id,
                "--project",
                str(self.project),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_write_remains_blocked_until_source_is_actually_read(self) -> None:
        first = self.invoke(self.write_payload())

        self.assertEqual(0, first.returncode, first.stderr)
        first_output = json.loads(first.stdout)
        self.assertEqual("block", first_output["decision"])
        self.assertIn("docs/contract.md", first_output["reason"])

        second = self.invoke(self.write_payload())

        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual("block", json.loads(second.stdout)["decision"])

        read_result = self.acknowledge("source-contract")
        self.assertEqual(0, read_result.returncode, read_result.stderr)
        self.assertIn("Read this before writing.", read_result.stdout)

        third = self.invoke(self.write_payload())
        self.assertEqual(0, third.returncode, third.stderr)
        self.assertEqual({}, json.loads(third.stdout))

    def test_source_change_requires_fresh_spec_delivery(self) -> None:
        self.invoke(self.write_payload())
        self.acknowledge("source-contract")
        allowed = self.invoke(self.write_payload())
        self.assertEqual({}, json.loads(allowed.stdout))
        self.source.write_text("# Contract\n\nUpdated rule.\n", encoding="utf-8")

        result = self.invoke(self.write_payload())

        output = json.loads(result.stdout)
        self.assertEqual("block", output["decision"])
        self.assertIn("docs/contract.md", output["reason"])

    def test_acknowledging_unregistered_source_fails(self) -> None:
        result = self.acknowledge("unregistered")

        self.assertEqual(1, result.returncode)
        self.assertIn("Spec id 未登记", result.stderr)

    def test_acknowledgement_refuses_runtime_directory_symlink_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as external_dir:
            external = Path(external_dir).resolve()
            (self.project / ".ai-configs" / "runtime").symlink_to(
                external,
                target_is_directory=True,
            )

            result = self.acknowledge("source-contract")

            self.assertEqual(1, result.returncode)
            self.assertIn("项目之外", result.stderr)
            self.assertEqual([], list(external.iterdir()))

    def test_unmatched_write_is_allowed(self) -> None:
        result = self.invoke(self.write_payload("README.md"))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({}, json.loads(result.stdout))

    def test_apply_patch_extracts_all_target_files(self) -> None:
        payload = {
            "session_id": "session-2",
            "cwd": str(self.project),
            "hook_event_name": "PreToolUse",
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Update File: src/a.py\n*** Add File: src/b.py\n*** End Patch"
            },
        }

        result = self.invoke(payload)

        output = json.loads(result.stdout)
        self.assertEqual("block", output["decision"])
        self.assertIn("src/a.py", output["reason"])
        self.assertIn("src/b.py", output["reason"])
        self.assertEqual(1, output["reason"].count("## source-contract"))

    def test_apply_patch_accepts_freeform_tool_input(self) -> None:
        payload = {
            "session_id": "session-3",
            "cwd": str(self.project),
            "hook_event_name": "PreToolUse",
            "tool_name": "apply_patch",
            "tool_input": "*** Begin Patch\n*** Update File: src/raw.py\n*** End Patch",
        }

        result = self.invoke(payload)

        output = json.loads(result.stdout)
        self.assertEqual("block", output["decision"])
        self.assertIn("src/raw.py", output["reason"])

    def test_relative_patch_paths_are_resolved_from_hook_cwd(self) -> None:
        nested = self.project / "src"
        nested.mkdir()
        payload = {
            "session_id": "session-4",
            "cwd": str(nested),
            "hook_event_name": "PreToolUse",
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Update File: nested.py\n*** End Patch"
            },
        }

        result = self.invoke(payload)

        output = json.loads(result.stdout)
        self.assertEqual("block", output["decision"])
        self.assertIn("src/nested.py", output["reason"])

    def test_block_reason_contains_executable_acknowledgement_command(self) -> None:
        result = self.invoke(self.write_payload())

        reason = json.loads(result.stdout)["reason"]
        self.assertIn("--spec-id source-contract", reason)
        self.assertIn("--session-id session-1", reason)
        self.assertIn("--project", reason)

    def test_duplicate_sources_are_acknowledged_by_spec_id(self) -> None:
        self.index.write_text(
            json.dumps(
                {
                    "version": 1,
                    "specs": [
                        {
                            "id": "a-contract",
                            "source": "docs/contract.md",
                            "description": "A",
                            "paths": ["src/a.py"],
                        },
                        {
                            "id": "b-contract",
                            "source": "docs/contract.md",
                            "description": "B",
                            "paths": ["src/b.py"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        a_payload = self.write_payload("src/a.py")
        b_payload = self.write_payload("src/b.py")

        first = self.invoke(a_payload)
        self.assertEqual("block", json.loads(first.stdout)["decision"])

        ack = self.acknowledge("a-contract")
        self.assertEqual(0, ack.returncode, ack.stderr)
        self.assertIn("# Contract", ack.stdout)

        a_retry = self.invoke(a_payload)
        b_write = self.invoke(b_payload)
        self.assertEqual({}, json.loads(a_retry.stdout))
        self.assertEqual("block", json.loads(b_write.stdout)["decision"])

    def test_broken_index_blocks_write_without_hiding_error(self) -> None:
        self.index.write_text("{broken", encoding="utf-8")

        result = self.invoke(self.write_payload())

        self.assertEqual(0, result.returncode, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual("block", output["decision"])
        self.assertIn("Spec 索引 JSON 非法", output["reason"])


if __name__ == "__main__":
    unittest.main()
