import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "spec.py"
XMAN = Path(__file__).resolve().parents[1] / "xman"
HOOK = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "spec-pre-tool-use.py"


class SpecCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name).resolve()
        (self.project / ".ai-configs" / "specs").mkdir(parents=True)
        (self.project / "docs").mkdir()
        (self.project / "docs" / "contract.md").write_text(
            "# Contract\n",
            encoding="utf-8",
        )
        (self.project / ".ai-configs" / "specs" / "index.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "specs": [
                        {
                            "id": "contract",
                            "source": "docs/contract.md",
                            "description": "Contract",
                            "paths": ["src/**/*.py"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), *args, "--project", str(self.project)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_validate_reports_spec_count(self) -> None:
        result = self.run_cli("validate")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("1 条 Spec", result.stdout)

    def test_match_json_returns_applicable_spec_without_internal_fields(self) -> None:
        result = self.run_cli("match", "src/services/example.py", "--json")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("src/services/example.py", payload["target"])
        self.assertEqual(["contract"], [item["id"] for item in payload["specs"]])
        self.assertNotIn("_source_path", payload["specs"][0])

    def test_default_project_is_discovered_from_nested_directory(self) -> None:
        nested = self.project / "src" / "services"
        nested.mkdir(parents=True)

        result = subprocess.run(
            ["python3", str(SCRIPT), "match", "src/services/example.py", "--json"],
            check=False,
            capture_output=True,
            text=True,
            cwd=nested,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(["contract"], [item["id"] for item in payload["specs"]])

    def test_explicit_project_does_not_climb_to_parent_index(self) -> None:
        child = self.project / "nested-repo"
        (child / ".git").mkdir(parents=True)

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "install-hooks",
                "claude",
                "--project",
                str(child),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("显式项目根缺少", result.stderr)
        self.assertFalse((self.project / ".claude").exists())
        self.assertFalse((child / ".claude").exists())

    def test_automatic_discovery_stops_at_nested_git_boundary(self) -> None:
        child = self.project / "nested-repo"
        (child / ".git").mkdir(parents=True)

        result = subprocess.run(
            ["python3", str(SCRIPT), "validate"],
            check=False,
            capture_output=True,
            text=True,
            cwd=child,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("Git 仓库边界", result.stderr)

    def test_list_is_deterministic(self) -> None:
        result = self.run_cli("list")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("contract", result.stdout)
        self.assertIn("docs/contract.md", result.stdout)

    def test_xman_routes_spec_command(self) -> None:
        result = subprocess.run(
            [str(XMAN), "spec", "validate", "--project", str(self.project)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("1 条 Spec", result.stdout)

    def test_init_creates_project_spec_skeleton(self) -> None:
        project = self.project / "new-project"
        project.mkdir()

        result = subprocess.run(
            [str(XMAN), "spec", "init", "--project", str(project)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        index = json.loads(
            (project / ".ai-configs" / "specs" / "index.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual({"version": 1, "specs": []}, index)
        readme = (project / ".ai-configs" / "specs" / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("source", readme)
        self.assertIn("paths", readme)

    def test_init_refuses_to_replace_existing_spec_index(self) -> None:
        result = self.run_cli("init")

        self.assertEqual(1, result.returncode)
        self.assertIn("已经存在", result.stderr)

    def test_install_claude_hook_preserves_existing_settings(self) -> None:
        settings = self.project / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps(
                {
                    "permissions": {"allow": ["Read"]},
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {"type": "command", "command": "./existing-hook.sh"}
                                ],
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        result = self.run_cli("install-hooks", "claude")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("仅覆盖结构化写工具", result.stdout)
        self.assertIn("不是安全或合规强制边界", result.stdout)
        payload = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(["Read"], payload["permissions"]["allow"])
        hooks = payload["hooks"]["PreToolUse"]
        self.assertEqual(2, len(hooks))
        self.assertEqual("Bash", hooks[0]["matcher"])
        self.assertEqual("Write|Edit|MultiEdit", hooks[1]["matcher"])
        installed = self.project / ".claude" / "hooks" / "xman-spec-pre-tool-use.py"
        installed_core = self.project / ".claude" / "hooks" / "xman_spec_core.py"
        self.assertTrue(installed.is_file())
        self.assertFalse(installed.is_symlink())
        self.assertTrue(installed_core.is_file())

        hook_result = subprocess.run(
            ["python3", str(installed)],
            input=json.dumps(
                {
                    "session_id": "portable-install",
                    "cwd": str(self.project),
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Write",
                    "tool_input": {"file_path": "src/example.py"},
                }
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, hook_result.returncode, hook_result.stderr)
        self.assertEqual("block", json.loads(hook_result.stdout)["decision"])
        self.assertIn("宿主检查", result.stdout)

    def test_install_codex_hook_is_idempotent(self) -> None:
        first = self.run_cli("install-hooks", "codex")
        second = self.run_cli("install-hooks", "codex")

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertIn("/hooks", first.stdout)
        self.assertIn("信任", first.stdout)
        config = self.project / ".codex" / "hooks.json"
        payload = json.loads(config.read_text(encoding="utf-8"))
        hooks = payload["hooks"]["PreToolUse"]
        commands = [
            handler["command"]
            for group in hooks
            for handler in group.get("hooks", [])
        ]
        self.assertEqual(
            1,
            sum("xman-spec-pre-tool-use.py" in command for command in commands),
        )

    def test_install_reports_detected_host_version_without_claiming_activation(self) -> None:
        with tempfile.TemporaryDirectory() as bin_dir:
            fake_claude = Path(bin_dir) / "claude"
            fake_claude.write_text(
                "#!/bin/sh\necho 'claude-test 9.9.9'\n",
                encoding="utf-8",
            )
            fake_claude.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "install-hooks",
                    "claude",
                    "--project",
                    str(self.project),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("claude-test 9.9.9", result.stdout)
        self.assertIn("不证明 Hook 已生效", result.stdout)

    def test_install_hooks_reports_existing_matcher_drift(self) -> None:
        config = self.project / ".codex" / "hooks.json"
        config.parent.mkdir(parents=True)
        original = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 .codex/hooks/xman-spec-pre-tool-use.py",
                            }
                        ],
                    }
                ]
            }
        }
        config.write_text(json.dumps(original), encoding="utf-8")

        result = self.run_cli("install-hooks", "codex")

        self.assertEqual(1, result.returncode)
        self.assertIn("Hook 定义漂移", result.stderr)
        self.assertEqual(original, json.loads(config.read_text(encoding="utf-8")))

    def test_install_hooks_dry_run_does_not_write(self) -> None:
        result = self.run_cli("install-hooks", "claude", "--dry-run")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("将安装", result.stdout)
        self.assertFalse((self.project / ".claude").exists())

    def test_install_hooks_refuses_symlinked_config(self) -> None:
        external = self.project / "external-settings.json"
        original = {"permissions": {"allow": ["Read"]}}
        external.write_text(json.dumps(original), encoding="utf-8")
        config = self.project / ".claude" / "settings.json"
        config.parent.mkdir(parents=True)
        config.symlink_to(external)

        result = self.run_cli("install-hooks", "claude")

        self.assertEqual(1, result.returncode)
        self.assertIn("配置是软链", result.stderr)
        self.assertTrue(config.is_symlink())
        self.assertEqual(original, json.loads(external.read_text(encoding="utf-8")))

    def test_install_hooks_refuses_existing_real_hook_file(self) -> None:
        hook = self.project / ".codex" / "hooks" / "xman-spec-pre-tool-use.py"
        hook.parent.mkdir(parents=True)
        hook.write_text("user owned\n", encoding="utf-8")

        result = self.run_cli("install-hooks", "codex")

        self.assertEqual(1, result.returncode)
        self.assertIn("用户文件", result.stderr)
        self.assertEqual("user owned\n", hook.read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".codex" / "hooks.json").exists())

    def test_install_hooks_preflights_all_runtime_files_before_writing(self) -> None:
        hooks_dir = self.project / ".codex" / "hooks"
        hooks_dir.mkdir(parents=True)
        core = hooks_dir / "xman_spec_core.py"
        core.write_text("user owned core\n", encoding="utf-8")

        result = self.run_cli("install-hooks", "codex")

        self.assertEqual(1, result.returncode)
        self.assertIn("用户文件", result.stderr)
        self.assertFalse((hooks_dir / "xman-spec-pre-tool-use.py").exists())
        self.assertEqual("user owned core\n", core.read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".codex" / "hooks.json").exists())

    def test_install_hooks_migrates_legacy_source_symlink_to_portable_copy(self) -> None:
        hook = self.project / ".codex" / "hooks" / "xman-spec-pre-tool-use.py"
        hook.parent.mkdir(parents=True)
        hook.symlink_to(HOOK)

        result = self.run_cli("install-hooks", "codex")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(hook.is_file())
        self.assertFalse(hook.is_symlink())
        self.assertTrue((hook.parent / "xman_spec_core.py").is_file())

    def test_install_hooks_refuses_platform_directory_symlink_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as external_dir:
            external = Path(external_dir).resolve()
            (self.project / ".codex").symlink_to(external, target_is_directory=True)

            result = self.run_cli("install-hooks", "codex")

            self.assertEqual(1, result.returncode)
            self.assertIn("项目之外", result.stderr)
            self.assertEqual([], list(external.iterdir()))

    def test_repository_validate_runs_spec_contract_check(self) -> None:
        index = json.loads(
            (XMAN.parent / ".ai-configs" / "specs" / "index.json").read_text(
                encoding="utf-8"
            )
        )
        result = subprocess.run(
            [str(XMAN), "validate"],
            check=False,
            capture_output=True,
            text=True,
            cwd=XMAN.parent,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Spec 索引契约", result.stdout)
        self.assertIn(f"{len(index['specs'])} 条 Spec", result.stdout)

    def test_repository_setup_succeeds_for_fresh_user_path(self) -> None:
        result = subprocess.run(
            [str(XMAN), "setup"],
            check=False,
            capture_output=True,
            text=True,
            cwd=XMAN.parent,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("设置完成", result.stdout)


if __name__ == "__main__":
    unittest.main()
