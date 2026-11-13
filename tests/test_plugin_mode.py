import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
XMAN = REPO_ROOT / "xman"
BUILD_PLUGIN = REPO_ROOT / "scripts" / "build-plugin.sh"


def local_agent_resource_references(text, document, agent, resources, bundle):
    """只解析具体的本地资源路径；不替安装产物修正路径或回退到源码。"""
    external_skill_section = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.match(r"^#{1,6} ", line):
            external_skill_section = False
        # 如 PUA 探测段先定位 skills/pua/SKILL.md，随后裸 references/ 属于该 skill。
        if re.search(r"(?:^|/)skills/[A-Za-z0-9_-]+/SKILL\.md\b", line):
            external_skill_section = True
        for quoted, bare in re.findall(r"`([^`]+)`|([A-Za-z0-9_./:{}<>?*$~-]+)", line):
            raw = (quoted or bare).rstrip(".")
            if "://" in raw or ".ai-configs" in raw.split("/"):
                continue
            plugin_prefix = "${CLAUDE_PLUGIN_ROOT}/"
            concrete = raw.removeprefix(plugin_prefix)
            if re.search(r"[<>*?{}$]", concrete):
                continue
            parts = concrete.split("/")
            companion_relative = raw.startswith(("./", "../")) and document.resolve().is_relative_to(
                resources.resolve()
            ) and "." in parts[-1]
            conventions_reference = concrete == "context/conventions.md" or (
                (raw.startswith(plugin_prefix) or Path(raw).is_absolute())
                and Path(concrete).name == "conventions.md"
            )
            if "skills" in parts or not (conventions_reference or companion_relative or any(
                part in ("references", "hooks") and index < len(parts) - 1
                and parts[-1] and "." in parts[-1]
                for index, part in enumerate(parts)
            )):
                continue
            if raw.startswith(plugin_prefix):
                target = bundle / concrete
            elif Path(raw).is_absolute():
                target = Path(raw)
            elif raw == "context/conventions.md":
                target = document.resolve().parent.parent / raw
            elif raw.startswith(("references/", "hooks/")):
                if external_skill_section:
                    continue
                target = document.parent / raw
            elif raw.startswith("agents/"):
                target = bundle / raw
            elif raw.startswith((f"{agent}/", "./", "../")):
                target = document.parent / raw
            else:
                continue
            yield lineno, raw, target


class PluginModeTest(unittest.TestCase):
    def assert_installed_agent_resources(self, definition, resources, bundle, *, copied=False):
        agent = definition.stem
        if definition.suffix == ".toml":
            text = tomllib.loads(definition.read_text(encoding="utf-8"))["developer_instructions"]
        else:
            text = definition.read_text(encoding="utf-8")
        pending = [(definition, text)]
        visited = set()
        references = []
        while pending:
            document, text = pending.pop()
            if document.resolve() in visited:
                continue
            visited.add(document.resolve())
            for lineno, raw, target in local_agent_resource_references(
                text, document, agent, resources, bundle
            ):
                if copied:
                    self.assertTrue(
                        target.resolve().is_relative_to(bundle.resolve()),
                        f"安装后资源越出副本：{document}:{lineno}: {raw} -> {target}",
                    )
                self.assertTrue(
                    target.is_file(),
                    f"安装后资源缺失：{document}:{lineno}: {raw} -> {target}",
                )
                references.append((document, raw, target))
                if target.suffix == ".md":
                    pending.append((target, target.read_text(encoding="utf-8")))
        return references

    def test_codex_install_generates_toml_agent_and_keeps_resources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xman project with spaces ") as temp_dir:
            project = Path(temp_dir)

            result = subprocess.run(
                [
                    str(XMAN),
                    "install",
                    "codex",
                    "--project",
                    str(project),
                    "--agent",
                    "xman-flow",
                    "--clean",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            target = project / ".codex" / "agents"
            agent_file = target / "xman-flow.toml"
            self.assertTrue(agent_file.is_file())
            payload = tomllib.loads(agent_file.read_text(encoding="utf-8"))
            self.assertEqual("xman-flow", payload["name"])
            self.assertTrue(payload["description"])
            self.assertTrue(payload["developer_instructions"])
            resources = project / ".codex" / "agent-resources" / "xman-flow"
            self.assertTrue(resources.is_symlink())
            self.assertTrue(resources.is_dir())
            self.assertFalse((target / "xman-flow.md").exists())
            self.assertFalse((target / "xman-flow").exists())
            references = self.assert_installed_agent_resources(agent_file, resources, project)
            self.assertTrue(references)
            self.assertTrue(any(document.parent.name == "references" for document, _, _ in references))

            original = agent_file.read_text(encoding="utf-8")
            agent_file.write_text(
                original.replace(str(REPO_ROOT), "/old/location/x-mansion", 1),
                encoding="utf-8",
            )
            rerun = subprocess.run(
                [
                    str(XMAN),
                    "install",
                    "codex",
                    "--project",
                    str(project),
                    "--agent",
                    "xman-flow",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            self.assertEqual(0, rerun.returncode, rerun.stderr)
            self.assertEqual(original, agent_file.read_text(encoding="utf-8"))

    def test_claude_install_resolves_agent_and_companion_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            result = subprocess.run(
                [str(XMAN), "install", "claude", "--project", str(project),
                 "--agent", "xman-flow"],
                check=False, capture_output=True, text=True, cwd=REPO_ROOT,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            agents = project / ".claude" / "agents"
            references = self.assert_installed_agent_resources(
                agents / "xman-flow.md", agents / "xman-flow", project
            )
            self.assertTrue(references, "安装后的 agent 必须实际解析到资源引用")
            self.assertTrue(any(document.parent.name == "references" for document, _, _ in references))

    def test_direct_install_keeps_released_skills_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    str(XMAN),
                    "install",
                    "cursor",
                    "--target",
                    str(Path(temp_dir) / "skills"),
                    "--dry-run",
                    "--no-agents",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            output = result.stdout + result.stderr
            self.assertEqual(0, result.returncode, output)
            self.assertNotIn("跳过 22 个已进入发行版", output)
            self.assertIn("  - review", output)

    def test_build_check_fails_when_generated_plugin_is_missing(self) -> None:
        fixture = self.make_plugin_fixture()

        result = subprocess.run(
            [str(fixture / "scripts" / "build-plugin.sh"), "--check"],
            check=False,
            capture_output=True,
            text=True,
            cwd=fixture,
        )

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("FAIL", result.stdout)

    def test_build_generates_cross_host_manifests_and_agents(self) -> None:
        fixture = self.make_plugin_fixture()

        result = subprocess.run(
            [str(fixture / "scripts" / "build-plugin.sh")],
            check=False,
            capture_output=True,
            text=True,
            cwd=fixture,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        plugin = fixture / "dist" / "plugin" / "x-mansion"
        self.assertTrue((plugin / "skills" / "alpha" / "SKILL.md").is_file())
        bundled_skill = (plugin / "skills" / "alpha" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("disable-model-invocation: false", bundled_skill)
        self.assertNotIn("disable-model-invocation: true", bundled_skill)
        # plugin 单装要完整：发行版里也有的同名 skill 照样发
        self.assertTrue((plugin / "skills" / "released" / "SKILL.md").is_file())
        self.assertTrue((plugin / "agents" / "flow.md").is_file())
        self.assertFalse((plugin / "agents" / "flow").exists())
        self.assertTrue(
            (plugin / "agent-resources" / "flow" / "references" / "guide.md").is_file()
        )
        bundled_agent = (plugin / "agents" / "flow.md").read_text(encoding="utf-8")
        self.assertIn(
            "${CLAUDE_PLUGIN_ROOT}/agent-resources/flow/references/guide.md",
            bundled_agent,
        )
        references = self.assert_installed_agent_resources(
            plugin / "agents" / "flow.md", plugin / "agent-resources" / "flow", plugin,
            copied=True,
        )
        self.assertTrue(references)
        self.assertTrue(any(document.parent.name == "references" for document, _, _ in references))

        codex_manifest = json.loads(
            (plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        claude_manifest = json.loads(
            (plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("./skills/", codex_manifest["skills"])
        self.assertNotIn("agents", claude_manifest)
        self.assertEqual(codex_manifest["version"], claude_manifest["version"])
        self.assertRegex(
            codex_manifest["version"],
            r"^1\.0\.0\+codex\.local-[0-9]{8}-[0-9]{6}$",
        )

        check_result = subprocess.run(
            [str(fixture / "scripts" / "build-plugin.sh"), "--check"],
            check=False,
            capture_output=True,
            text=True,
            cwd=fixture,
        )
        self.assertEqual(0, check_result.returncode, check_result.stdout + check_result.stderr)

    def test_nested_codex_security_launcher_resolves_from_plugin_root(self) -> None:
        fixture = self.make_plugin_fixture()
        bundle = fixture / "skills" / "codex-security"
        launcher = bundle / "scripts" / "launch_codex_security_mcp"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        launcher.chmod(0o755)
        (bundle / "SKILL.md").write_text(
            "---\nname: codex-security\ndescription: Defensive review\n---\n", encoding="utf-8"
        )
        (bundle / ".mcp.json").write_text(json.dumps({"mcpServers": {"codex-security": {
            "command": "./scripts/launch_codex_security_mcp", "cwd": ".", "args": ["--stdio"],
        }}}), encoding="utf-8")
        with (fixture / "governance" / "skills-registry.csv").open("a", newline="") as file:
            csv.writer(file).writerow(
                ["codex-security", "experimental", "local", "", "local", "", "skill", ""]
            )

        result = self.run_fixture_build(fixture)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        plugin = fixture / "dist" / "plugin" / "x-mansion"
        manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
        config_path = plugin / manifest["mcpServers"]
        server = json.loads(config_path.read_text())["mcpServers"]["codex-security"]
        self.assertEqual(".", server["cwd"])
        installed_launcher = plugin / server["cwd"] / server["command"]
        self.assertEqual(["--stdio"], server["args"])
        self.assertTrue(os.access(installed_launcher, os.X_OK))

    def test_plugin_copies_resolve_real_agent_companion_references(self) -> None:
        fixture = self.make_plugin_fixture()
        (fixture / "context").mkdir()
        shutil.copy2(REPO_ROOT / "context" / "conventions.md", fixture / "context" / "conventions.md")
        names = []
        with (fixture / "governance" / "skills-registry.csv").open("a", newline="") as handle:
            writer = csv.writer(handle)
            for source in sorted((REPO_ROOT / "agents").glob("*.md")):
                text = source.read_text(encoding="utf-8")
                if not text.startswith("---\n") or not re.search(r"^name:", text.split("---", 2)[1], re.M):
                    continue
                names.append(source.stem)
                shutil.copy2(source, fixture / "agents" / source.name)
                companion = source.with_suffix("")
                if companion.is_dir():
                    shutil.copytree(companion, fixture / "agents" / source.stem)
                writer.writerow([source.stem, "experimental", "local", "", "local", "", "agent", ""])
        result = self.run_fixture_build(fixture)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        plugin = fixture / "dist" / "plugin" / "x-mansion"
        references = []
        for name in names:
            references.extend(self.assert_installed_agent_resources(
                plugin / "agents" / f"{name}.md", plugin / "agent-resources" / name, plugin,
                copied=True,
            ))
        self.assertTrue(references, "不能靠空引用集合通过真实 agent 副本检查")
        self.assertTrue(any(document.parent.name == "references" for document, _, _ in references))

    def add_conventions_fixture(self, fixture: Path) -> Path:
        conventions = fixture / "context" / "conventions.md"
        conventions.parent.mkdir(exist_ok=True)
        conventions.write_text(
            "<!-- xman-conventions: 3 -->\n# Fixture conventions\n",
            encoding="utf-8",
        )
        agent = fixture / "agents" / "flow.md"
        agent.write_text(
            agent.read_text(encoding="utf-8").replace(
                "Read flow/references/guide.md", "Read `flow/references/guide.md`"
            ) + "Read `context/conventions.md`.\n",
            encoding="utf-8",
        )
        return conventions

    def test_plugin_bundles_conventions_and_rejects_missing_or_changed_copy(self) -> None:
        for corruption in ("missing", "changed"):
            with self.subTest(corruption=corruption):
                fixture = self.make_plugin_fixture()
                source = self.add_conventions_fixture(fixture)
                result = self.run_fixture_build(fixture)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                plugin = fixture / "dist" / "plugin" / "x-mansion"
                bundled = plugin / "conventions.md"
                self.assertEqual(source.read_bytes(), bundled.read_bytes())
                definition = plugin / "agents" / "flow.md"
                self.assertIn(
                    "`${CLAUDE_PLUGIN_ROOT}/conventions.md`",
                    definition.read_text(encoding="utf-8"),
                )
                resources = plugin / "agent-resources" / "flow"
                references = self.assert_installed_agent_resources(
                    definition, resources, plugin, copied=True,
                )
                self.assertTrue(any(target == bundled for _, _, target in references))
                if corruption == "missing":
                    bundled.unlink()
                else:
                    bundled.write_text("tampered conventions\n", encoding="utf-8")
                self.assertTrue(source.is_file(), "源文件存在不能掩盖副本丢失或被改动")
                check = self.run_fixture_build(fixture, "--check")
                self.assertEqual(1, check.returncode, check.stdout + check.stderr)
                self.assertIn("plugin agent 定义已漂移", check.stdout)

    def test_codex_conventions_use_real_source_path_with_spaces(self) -> None:
        fixture = self.make_plugin_fixture()
        source = self.add_conventions_fixture(fixture)
        with tempfile.TemporaryDirectory(prefix="xman source with spaces ") as temp_dir:
            checkout = Path(temp_dir) / "checkout with spaces"
            shutil.copytree(fixture, checkout)
            project = Path(temp_dir) / "installed project"
            agent_source = checkout / "agents" / "flow.md"
            target = project / ".codex" / "agents" / "flow.toml"
            resources = checkout / "agents" / "flow"
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "sync-codex-agent.py"),
                 "--source", str(agent_source), "--target", str(target),
                 "--name", "flow", "--resources", str(resources)],
                capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            instructions = tomllib.loads(target.read_text(encoding="utf-8"))["developer_instructions"]
            expected = (checkout / "context" / "conventions.md").resolve()
            self.assertIn(f"`{expected.as_posix()}`", instructions)
            self.assertEqual(source.read_bytes(), expected.read_bytes())
            references = self.assert_installed_agent_resources(target, resources, project)
            self.assertTrue(any(path == expected for _, _, path in references))

    def test_codex_rejects_missing_conventions_without_replacing_existing_agent(self) -> None:
        fixture = self.make_plugin_fixture()
        self.add_conventions_fixture(fixture).unlink()
        target = fixture / "installed" / "flow.toml"
        target.parent.mkdir()
        target.write_text("existing agent\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "sync-codex-agent.py"),
             "--source", str(fixture / "agents" / "flow.md"), "--target", str(target),
             "--name", "flow", "--resources", str(fixture / "agents" / "flow")],
            capture_output=True, text=True,
        )
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("conventions", result.stderr)
        self.assertEqual("existing agent\n", target.read_text(encoding="utf-8"))

    def test_agent_exports_preserve_non_companion_paths(self) -> None:
        fixture = self.make_plugin_fixture()
        agent_source = fixture / "agents" / "flow.md"
        preserved = (
            ".ai-configs/flow/YYYY/MM/report.md",
            "/tmp/flow/report.md",
            "workflow/references/guide.md",
            "https://example.com/flow/report.md",
        )
        with agent_source.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(f"Keep `{path}`." for path in preserved) + "\n")

        target = fixture / "installed" / "flow.toml"
        resources = fixture / "agents" / "flow"
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "sync-codex-agent.py"),
             "--source", str(agent_source), "--target", str(target),
             "--name", "flow", "--resources", str(resources)],
            capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        instructions = tomllib.loads(target.read_text(encoding="utf-8"))["developer_instructions"]
        self.assertIn(f"{resources.resolve().as_posix()}/references/guide.md", instructions)
        for path in preserved:
            self.assertIn(f"`{path}`", instructions)

        build = self.run_fixture_build(fixture)
        self.assertEqual(0, build.returncode, build.stdout + build.stderr)
        plugin = fixture / "dist" / "plugin" / "x-mansion"
        installed = (plugin / "agents" / "flow.md").read_text(encoding="utf-8")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/agent-resources/flow/references/guide.md", installed)
        for path in preserved:
            self.assertIn(f"`{path}`", installed)
        check = self.run_fixture_build(fixture, "--check")
        self.assertEqual(0, check.returncode, check.stdout + check.stderr)

    def test_codex_repository_references_resolve_outside_source_checkout(self) -> None:
        fixture = self.make_plugin_fixture()
        conventions = self.add_conventions_fixture(fixture)
        platforms = fixture / "context" / "platforms.md"
        platforms.write_text("# Fixture platforms\n", encoding="utf-8")
        skill = fixture / "skills" / "alpha" / "SKILL.md"
        agent_source = fixture / "agents" / "flow.md"
        with agent_source.open("a", encoding="utf-8") as handle:
            handle.write("Read `skills/alpha/SKILL.md` and `context/platforms.md`.\n")
        with tempfile.TemporaryDirectory(prefix="unrelated-project-") as project:
            target = Path(project) / ".codex" / "agents" / "flow.toml"
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "sync-codex-agent.py"),
                 "--source", str(agent_source), "--target", str(target),
                 "--name", "flow", "--resources", str(fixture / "agents" / "flow")],
                capture_output=True, text=True, cwd=project,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            instructions = tomllib.loads(target.read_text(encoding="utf-8"))["developer_instructions"]
            for path in (skill, platforms, conventions):
                self.assertTrue(path.is_file())
                self.assertIn(f"`{path.resolve().as_posix()}`", instructions)

    def test_installed_reference_check_detects_missing_copy_and_wrong_level(self) -> None:
        for corruption in ("missing-copy", "wrong-level", "source-fallback"):
            with self.subTest(corruption=corruption):
                fixture = self.make_plugin_fixture()
                result = self.run_fixture_build(fixture)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                plugin = fixture / "dist" / "plugin" / "x-mansion"
                definition = plugin / "agents" / "flow.md"
                resources = plugin / "agent-resources" / "flow"
                references = self.assert_installed_agent_resources(definition, resources, plugin, copied=True)
                self.assertTrue(references)
                document, raw, target = next(
                    ref for ref in references if ref[0].parent.name == "references"
                    and ref[2].suffix == ".md"
                )
                source = fixture / "agents" / "flow" / target.relative_to(resources)
                self.assertTrue(source.is_file(), "负例必须保留源资源，以排除源码兜底假绿")
                if corruption == "missing-copy":
                    target.unlink()
                else:
                    broken = str(source) if corruption == "source-fallback" else f"references/{raw}"
                    document.write_text(
                        document.read_text(encoding="utf-8").replace(raw, broken),
                        encoding="utf-8",
                    )
                with self.assertRaisesRegex(AssertionError, "安装后资源"):
                    self.assert_installed_agent_resources(definition, resources, plugin, copied=True)

    def test_reference_parser_uses_document_paths_and_excludes_external_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir)
            resources = bundle / "agent-resources" / "flow"
            document = resources / "references" / "guide.md"
            text = (
                "Read `./missing.md` and `../hooks/pre.sh`.\n"
                "Project `.ai-configs/references/project.md`.\n"
                "URL https://example.test/references/remote.md\n"
                "Examples `references/{name}.md`, `references/<name>.md`, `**/references/any.md`.\n"
                "External `skills/review/references/evidence.md`.\n"
                "## External skill\nGlob `**/skills/pua/SKILL.md`.\n"
                "Read its `references/external-only.md`.\n"
                "## Local again\nRead `references/missing.md`.\n"
            )
            found = list(local_agent_resource_references(text, document, "flow", resources, bundle))
            self.assertEqual(
                {
                    "./missing.md": document.parent / "missing.md",
                    "../hooks/pre.sh": document.parent / "../hooks/pre.sh",
                    "references/missing.md": document.parent / "references/missing.md",
                },
                {raw: target for _, raw, target in found},
            )

    def test_flat_agent_definition_matches_skill_agent_spec(self) -> None:
        result = subprocess.run(
            [
                str(XMAN),
                "spec",
                "match",
                "agents/xman-flow.md",
                "--json",
                "--project",
                str(REPO_ROOT),
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("skill-agent-contract", [item["id"] for item in payload["specs"]])

    def test_agent_frontmatter_is_valid_yaml_when_parser_is_available(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")

        text = (REPO_ROOT / "agents" / "xman-flow.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        payload = yaml.safe_load(frontmatter)
        self.assertEqual("xman-flow", payload["name"])

    def test_agent_companion_references_exist(self) -> None:
        missing = []
        for agent_file in sorted((REPO_ROOT / "agents").glob("*.md")):
            text = agent_file.read_text(encoding="utf-8")
            references = set(
                re.findall(
                    r"(?:^|[^A-Za-z0-9_-])([A-Za-z0-9_-]+/(?:references|hooks)/[A-Za-z0-9._-]+)",
                    text,
                )
            )
            for reference in references:
                if not (REPO_ROOT / "agents" / reference).is_file():
                    missing.append(f"{agent_file.name}: {reference}")

        self.assertEqual([], missing)

    def test_xman_help_describes_conventions_landing_rules(self) -> None:
        """约定怎么落地是使用者必须知道的：默认不覆盖已有的那份，覆盖要显式要求，
        软链只在本机调试时用。帮助文本不写清楚，这些规则就只能靠读源码发现。"""
        result = subprocess.run(
            [str(XMAN), "help"],
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--link", result.stdout)
        self.assertIn("--refresh-conventions", result.stdout)
        self.assertIn("已存在则保持不变", result.stdout)

    def test_xman_routes_plugin_check(self) -> None:
        result = subprocess.run(
            [str(XMAN), "plugin", "check"],
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

        self.assertNotIn("未知命令", result.stderr)
        self.assertIn("plugin", result.stdout + result.stderr)

    def make_plugin_fixture(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        (temp_dir / "scripts").mkdir()
        (temp_dir / "governance").mkdir()
        (temp_dir / "skills" / "alpha").mkdir(parents=True)
        (temp_dir / "skills" / "released").mkdir(parents=True)
        (temp_dir / "agents" / "flow" / "references").mkdir(parents=True)

        shutil.copy2(BUILD_PLUGIN, temp_dir / "scripts" / "build-plugin.sh")
        shutil.copy2(
            REPO_ROOT / "scripts" / "registry_scope.py",
            temp_dir / "scripts" / "registry_scope.py",
        )
        (temp_dir / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Alpha\ndisable-model-invocation: true\n---\n",
            encoding="utf-8",
        )
        (temp_dir / "skills" / "released" / "SKILL.md").write_text(
            "---\nname: released\ndescription: Released\n---\n",
            encoding="utf-8",
        )
        (temp_dir / "agents" / "flow.md").write_text(
            "---\nname: flow\ndescription: Flow\n---\nRead flow/references/guide.md\n",
            encoding="utf-8",
        )
        (temp_dir / "agents" / "flow" / "references" / "guide.md").write_text(
            "# Guide\nRead `./nested/details.md` and `../hooks/after.sh`.\n"
            "Project `.ai-configs/references/project.md`; URL https://example.test/references/remote.md\n"
            "Examples: `references/{name}.md`, `references/<name>.md`, `**/references/any.md`.\n"
            "## External skill\nGlob `**/skills/pua/SKILL.md`.\n"
            "Read its `references/external-only.md`.\n",
            encoding="utf-8",
        )
        nested = temp_dir / "agents" / "flow" / "references" / "nested"
        nested.mkdir()
        (nested / "details.md").write_text("# Details\n", encoding="utf-8")
        hooks = temp_dir / "agents" / "flow" / "hooks"
        hooks.mkdir()
        (hooks / "after.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        with (temp_dir / "governance" / "skills-registry.csv").open(
            "w", encoding="utf-8", newline=""
        ) as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "skill",
                    "status",
                    "source",
                    "note",
                    "source_type",
                    "source_key",
                    "type",
                    "release",
                ]
            )
            writer.writerow(["alpha", "experimental", "local", "", "local", "", "skill", ""])
            writer.writerow(
                ["flow", "experimental", "local", "", "local", "", "agent", ""]
            )
            writer.writerow(
                [
                    "released",
                    "team-shared",
                    "local",
                    "",
                    "local",
                    "",
                    "skill",
                    "release-dist",
                ]
            )

        return temp_dir

    def add_private_fixture(self, fixture: Path, status="personal-only", ignored=True):
        with (fixture / "governance" / "skills-registry.csv").open("a", newline="") as handle:
            csv.writer(handle).writerow(["private", status, "local", "", "local", "", "skill", ""])
        if ignored:
            (fixture / ".gitignore").write_text("skills/private/\n", encoding="utf-8")

    def run_fixture_build(self, fixture: Path, *args):
        return subprocess.run(
            [str(fixture / "scripts" / "build-plugin.sh"), *args],
            cwd=fixture, capture_output=True, text=True,
        )

    def test_optional_private_skill_is_absent_in_public_build_and_present_locally(self):
        fixture = self.make_plugin_fixture()
        self.add_private_fixture(fixture)
        result = self.run_fixture_build(fixture)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse((fixture / "dist/plugin/x-mansion/skills/private").exists())
        self.assertEqual(0, self.run_fixture_build(fixture, "--check").returncode)

        private = fixture / "skills/private"
        private.mkdir()
        (private / "SKILL.md").write_text("---\nname: private\ndescription: Personal\n---\n")
        self.assertNotEqual(0, self.run_fixture_build(fixture, "--check").returncode)
        result = self.run_fixture_build(fixture)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue((fixture / "dist/plugin/x-mansion/skills/private/SKILL.md").is_file())
        self.assertEqual(0, self.run_fixture_build(fixture, "--check").returncode)

    def test_missing_nonoptional_skills_still_fail_build(self):
        for status, ignored in (("personal-only", False), ("experimental", True), ("team-shared", True)):
            with self.subTest(status=status, ignored=ignored):
                fixture = self.make_plugin_fixture()
                self.add_private_fixture(fixture, status=status, ignored=ignored)
                result = self.run_fixture_build(fixture)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertIn("缺少 skill 源文件: skills/private/SKILL.md", result.stderr)

    def test_incomplete_or_broken_private_source_still_fails_build(self):
        for state in ("directory", "broken-link", "file"):
            with self.subTest(state=state):
                fixture = self.make_plugin_fixture()
                self.add_private_fixture(fixture)
                private = fixture / "skills/private"
                if state == "directory":
                    private.mkdir()
                elif state == "broken-link":
                    private.symlink_to("missing-source")
                else:
                    private.write_text("not a skill directory")
                result = self.run_fixture_build(fixture)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertIn("缺少 skill 源文件: skills/private/SKILL.md", result.stderr)

    def test_release_marked_agent_stays_in_plugin(self) -> None:
        """plugin 单装必须完整：release 列只标出发行版也有同名一份，不再过滤。
        用夹具 registry 给 xman-flow 标上 release，产物里有它才算一致。"""
        registry = REPO_ROOT / "governance" / "skills-registry.csv"
        rows = registry.read_text(encoding="utf-8").splitlines(keepends=True)
        marked = []
        for line in rows:
            if line.startswith("xman-flow,"):
                marked.append(line.rstrip("\n").rstrip(",") + ",release-dist\n")
            else:
                marked.append(line)
        self.assertNotEqual(rows, marked, "夹具没生效，registry 格式可能变了")

        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "skills-registry.csv"
            fixture.write_text("".join(marked), encoding="utf-8")

            result = subprocess.run(
                [str(BUILD_PLUGIN), "--check"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env={**os.environ, "XMAN_REGISTRY": str(fixture)},
            )

            self.assertEqual(0, result.returncode, result.stdout)

    def run_overlap(self, codex_home: Path, command: str):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "plugin-overlap.py"), command],
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "CODEX_HOME": str(codex_home)},
        )

    def write_codex_config(self, codex_home: Path, release_enabled: bool | None) -> Path:
        config = codex_home / "config.toml"
        text = 'model = "x"  # 注释要保留\n\n[plugins."x-mansion@x-mansion-lab"]\nenabled = true\n'
        if release_enabled is not None:
            text += (
                '\n[plugins."release-dist@release-dist"]\n'
                f'enabled = {"true" if release_enabled else "false"}\n'
            )
        text += '\n[plugins."pdf@openai-primary-runtime"]\nenabled = true\n'
        config.write_text(text, encoding="utf-8")
        return config

    def test_overlap_is_silent_without_release_plugin(self) -> None:
        """单装时任何输出都不提发行版，连「未检测到」这类反向暗示也不行。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            self.assertEqual("", self.run_overlap(home, "report").stdout)
            self.write_codex_config(home, release_enabled=None)
            result = self.run_overlap(home, "report")
            self.assertEqual("", result.stdout + result.stderr)
            takeover = self.run_overlap(home, "takeover")
            self.assertNotIn("wf", takeover.stdout)

    def test_takeover_disables_only_the_release_plugin_and_restore_undoes_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            config = self.write_codex_config(home, release_enabled=True)
            before = config.read_text(encoding="utf-8")

            report = self.run_overlap(home, "report")
            self.assertIn("release-dist@release-dist", report.stdout)
            self.assertEqual(before, config.read_text(encoding="utf-8"), "report 不该改配置")

            result = self.run_overlap(home, "takeover")
            self.assertEqual(0, result.returncode, result.stderr)
            data = tomllib.loads(config.read_text(encoding="utf-8"))["plugins"]
            self.assertFalse(data["release-dist@release-dist"]["enabled"])
            self.assertTrue(data["x-mansion@x-mansion-lab"]["enabled"])
            # 本仓也有 pdf skill，但它不在 release 列里，别人的 plugin 不能碰
            self.assertTrue(data["pdf@openai-primary-runtime"]["enabled"])
            self.assertIn("# 注释要保留", config.read_text(encoding="utf-8"))
            self.assertEqual("", self.run_overlap(home, "report").stdout)

            self.run_overlap(home, "restore")
            self.assertEqual(before, config.read_text(encoding="utf-8"))

    def test_takeover_leaves_release_plugin_alone_when_own_plugin_is_off(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            config = self.write_codex_config(home, release_enabled=True)
            config.write_text(
                config.read_text(encoding="utf-8").replace(
                    '[plugins."x-mansion@x-mansion-lab"]\nenabled = true',
                    '[plugins."x-mansion@x-mansion-lab"]\nenabled = false',
                ),
                encoding="utf-8",
            )
            before = config.read_text(encoding="utf-8")
            self.run_overlap(home, "takeover")
            self.assertEqual(before, config.read_text(encoding="utf-8"))

    def test_plugin_agents_match_registry_agent_rows(self) -> None:
        with (REPO_ROOT / "governance" / "skills-registry.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            expected = sorted(
                row["skill"] for row in csv.DictReader(handle)
                if (row.get("type") or "").strip() == "agent"
            )
        actual = sorted(
            path.stem for path in
            (REPO_ROOT / "dist" / "plugin" / "x-mansion" / "agents").glob("*.md")
        )
        self.assertEqual(expected, actual)


    def test_rename_leaves_no_orphan_links_and_spares_foreign_ones(self) -> None:
        """母仓 agent 改名后，平台目录里指向旧名字的软链会断在那里：装新名字不会
        碰它们，用户也看不出那是垃圾。清理判据必须窄到只认我们自己造的断链。"""
        agents_root = REPO_ROOT / "agents"
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            target = project / ".claude" / "agents"
            target.mkdir(parents=True)

            (target / "gone.md").symlink_to(agents_root / "gone.md")       # 我们的，已断
            (target / "gone").symlink_to(agents_root / "gone")             # 我们的，已断
            (target / "foreign.md").symlink_to("/nonexistent/foreign.md")  # 别人的断链
            (target / "kept.md").symlink_to(agents_root / "README.md")  # 还能解析

            result = subprocess.run(
                [str(XMAN), "install", "claude", "--project", str(project),
                 "--agent", "xman-flow"],
                check=False, capture_output=True, text=True, cwd=REPO_ROOT,
            )
            self.assertEqual(0, result.returncode, result.stderr)

            self.assertFalse((target / "gone.md").is_symlink(), "指向母仓的断链该清掉")
            self.assertFalse((target / "gone").is_symlink(), "指向母仓的断链该清掉")
            self.assertTrue((target / "foreign.md").is_symlink(), "别人的断链不该动")
            self.assertTrue((target / "kept.md").is_symlink(), "还能解析的不该动")
            self.assertTrue((target / "xman-flow.md").is_symlink())

    def test_stale_codex_agent_is_pruned_but_handwritten_one_survives(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            target = project / ".codex" / "agents"
            target.mkdir(parents=True)

            # toml 是生成物不是软链，改名后它仍能解析，只是记录的 source 已经不在
            (target / "gone.toml").write_text(
                f"# Generated by x-mansion — source: {REPO_ROOT}/agents/gone.md\n"
                'name = "gone"\n',
                encoding="utf-8",
            )
            (target / "mine.toml").write_text(
                '# 我自己写的\nname = "mine"\n', encoding="utf-8",
            )

            result = subprocess.run(
                [str(XMAN), "install", "codex", "--project", str(project),
                 "--agent", "xman-flow"],
                check=False, capture_output=True, text=True, cwd=REPO_ROOT,
            )
            self.assertEqual(0, result.returncode, result.stderr)

            self.assertFalse((target / "gone.toml").exists(), "源已不存在的生成物该清掉")
            self.assertTrue((target / "mine.toml").exists(), "没有生成标记的是用户文件")
            self.assertTrue((target / "xman-flow.toml").exists())


    def _fake_release_layer(self, project: Path, names: list[str]) -> Path:
        """造出发行版那种形态：真身在项目的 .agents/ 锁定层，平台目录放相对软链。"""
        canonical = project / ".agents" / "skills"
        platform = project / ".claude" / "skills"
        canonical.mkdir(parents=True)
        platform.mkdir(parents=True)
        for name in names:
            (canonical / name).mkdir()
            (canonical / name / "SKILL.md").write_text("# 发行版那份\n", encoding="utf-8")
            (platform / name).symlink_to(Path("..") / ".." / ".agents" / "skills" / name)
        return platform

    def test_release_link_is_taken_over_and_foreign_link_is_left_alone(self) -> None:
        """平台目录里的软链原先只分两态：指向母仓的保留，其余一律当「错误软链」删掉重建。
        这会把别人手工建的、或另一个工具装的链接无声顶掉。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            platform = self._fake_release_layer(project, ["review"])

            foreign_src = project / "other-tool" / "create-plan"
            foreign_src.mkdir(parents=True)
            (foreign_src / "SKILL.md").write_text("# 别的工具装的\n", encoding="utf-8")
            (platform / "create-plan").symlink_to(foreign_src)

            result = subprocess.run(
                [str(XMAN), "install", "claude", "--project", str(project),
                 "--skill", "review", "--skill", "create-plan"],
                check=False, capture_output=True, text=True, cwd=REPO_ROOT,
            )
            self.assertEqual(0, result.returncode, result.stderr)

            # x-mansion 优先：发行版那份被接管
            taken = (platform / "review").resolve()
            self.assertEqual((REPO_ROOT / "skills" / "review").resolve(), taken)
            self.assertIn("接管发行版提供的同名条目", result.stdout)

            # 来源不明的原样保留，只报告
            self.assertEqual(
                foreign_src.resolve(), (platform / "create-plan").resolve(),
                "来源不明的软链不该被顶掉",
            )
            self.assertIn("来源不明", result.stdout + result.stderr)

    def test_already_correct_link_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            for _ in range(2):
                result = subprocess.run(
                    [str(XMAN), "install", "claude", "--project", str(project),
                     "--skill", "review"],
                    check=False, capture_output=True, text=True, cwd=REPO_ROOT,
                )
                self.assertEqual(0, result.returncode, result.stderr)
            # 第二次应认出是自己装的，既不接管也不报来源不明
            self.assertIn("已存在正确软链", result.stdout)
            self.assertNotIn("接管发行版", result.stdout)
            self.assertNotIn("来源不明", result.stdout + result.stderr)


    def test_existing_conventions_survive_init_unless_refresh_is_asked(self) -> None:
        """约定是 skill 的运行时事实源。项目里已经有一份就以它为准——它可能由别的
        工具落地，也可能被本项目改过，无条件覆盖会把这些静默冲掉。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            ai_configs = project / ".ai-configs"
            ai_configs.mkdir()
            mine = "# 本项目自己的约定\n\n## 产物路径\n\n随便写点什么\n"
            (ai_configs / "conventions.md").write_text(mine, encoding="utf-8")

            def run(*extra: str) -> subprocess.CompletedProcess:
                return subprocess.run(
                    [str(XMAN), "context", "init", str(project), "--auto", *extra],
                    check=False, capture_output=True, text=True, cwd=REPO_ROOT,
                )

            result = run()
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                mine, (ai_configs / "conventions.md").read_text(encoding="utf-8"),
                "默认不该覆盖项目里已有的约定",
            )
            self.assertIn("保持不变", result.stdout)
            self.assertIn("与母仓版本的差异", result.stdout)

            result = run("--refresh-conventions")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotEqual(
                mine, (ai_configs / "conventions.md").read_text(encoding="utf-8"),
                "显式要求刷新时应当覆盖",
            )
            self.assertIn("将被丢弃的差异", result.stdout)

    def test_fresh_project_still_gets_conventions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            result = subprocess.run(
                [str(XMAN), "context", "init", str(project), "--auto"],
                check=False, capture_output=True, text=True, cwd=REPO_ROOT,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            landed = project / ".ai-configs" / "conventions.md"
            self.assertTrue(landed.is_file())
            self.assertFalse(landed.is_symlink(), "软链是本机路径，同事 clone 下来会断")

    def test_spec_index_lives_under_ai_configs_and_is_not_gitignored(self) -> None:
        """索引搬进 .ai-configs/ 时，最容易漏的是 .gitignore：整个目录被忽略的话
        索引会静默失去版本控制，同事和 CI 读不到就等于没有 Spec。"""
        index = REPO_ROOT / ".ai-configs" / "specs" / "index.json"
        self.assertTrue(index.is_file(), "索引应在 .ai-configs/specs/ 下")

        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(index)],
            check=False, capture_output=True, cwd=REPO_ROOT,
        )
        self.assertNotEqual(0, ignored.returncode, "Spec 索引不能被 gitignore 掉")

        result = subprocess.run(
            [str(XMAN), "spec", "validate"],
            check=False, capture_output=True, text=True, cwd=REPO_ROOT,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(".ai-configs/specs/index.json", result.stdout)


    def _run_drift(self, env_extra: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "check-flow-drift.py")],
            check=False, capture_output=True, text=True, cwd=REPO_ROOT,
            env={**os.environ, **env_extra},
        )

    def test_drift_check_is_silent_when_no_release_repo_configured(self) -> None:
        """本仓不假设另一个仓库存在：没配置时连一个字都不该输出，
        「未检测到发行版」这类反向暗示同样不行。"""
        self.assertFalse(
            (REPO_ROOT / "governance" / ".release-repo").exists(),
            "本机配置文件不该入库，它的存在会让这条用例失去意义",
        )
        result = self._run_drift({"XMAN_RELEASE_REPO": ""})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())
        self.assertEqual("", result.stderr.strip())

    def test_drift_check_reports_when_configured_path_is_bogus(self) -> None:
        result = self._run_drift({"XMAN_RELEASE_REPO": "/nonexistent/release-repo"})
        self.assertNotEqual(0, result.returncode)
        self.assertIn("路径不存在", result.stdout)

    def test_drift_check_whitelists_host_bound_differences(self) -> None:
        """宿主绑定差异必须放行：把本仓编排器原样复制成另一个名字、改掉运行时命令
        与 env 变量之后，比对结果应当没有漂移而不是满屏差异。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            fake = Path(temp_dir)
            (fake / "agents").mkdir(parents=True)
            text = (REPO_ROOT / "agents" / "xman-flow.md").read_text(encoding="utf-8")
            twin = (text.replace("xman-flow", "twin-flow")
                        .replace("XMAN_TASK", "WF_TASK")
                        .replace("xman ", "release-dist "))
            (fake / "agents" / "twin-flow.md").write_text(twin, encoding="utf-8")

            result = self._run_drift({"XMAN_RELEASE_REPO": str(fake)})
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("无新增漂移", result.stdout)

    def test_drift_check_catches_a_real_section_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake = Path(temp_dir)
            (fake / "agents").mkdir(parents=True)
            text = (REPO_ROOT / "agents" / "xman-flow.md").read_text(encoding="utf-8")
            twin = text.replace("xman-flow", "twin-flow").replace(
                "## 第三步：逐个阶段执行", "## 第三步：逐个阶段执行\n\n这一段是凭空加的，白名单不该放行它。\n", 1,
            )
            (fake / "agents" / "twin-flow.md").write_text(twin, encoding="utf-8")

            result = self._run_drift({"XMAN_RELEASE_REPO": str(fake)})
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("第三步：逐个阶段执行", result.stdout)


    def test_drift_baseline_absorbs_reviewed_differences_but_not_new_ones(self) -> None:
        """已裁决的差异不记基线的话会被永远报下去，很快没人看；但基线不能顺带
        把新出现的漂移也吞掉。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            fake = Path(temp_dir)
            (fake / "agents").mkdir(parents=True)
            text = (REPO_ROOT / "agents" / "xman-flow.md").read_text(encoding="utf-8")
            twin = text.replace("xman-flow", "twin-flow").replace(
                "## 第三步：逐个阶段执行", "## 第三步：逐个阶段执行\n\n凭空加的一行。\n", 1,
            )
            (fake / "agents" / "twin-flow.md").write_text(twin, encoding="utf-8")

            baseline = fake / "baseline.tsv"
            baseline.write_text("第三步：逐个阶段执行\t5\n", encoding="utf-8")
            env = {"XMAN_RELEASE_REPO": str(fake)}

            # 差异在基线内 → 放行
            result = self._run_drift({**env, "XMAN_DRIFT_BASELINE": str(baseline)})
            self.assertEqual(0, result.returncode, result.stdout)

            # 基线收紧到 0 → 同一处差异应当被报出来
            baseline.write_text("第三步：逐个阶段执行\t0\n", encoding="utf-8")
            result = self._run_drift({**env, "XMAN_DRIFT_BASELINE": str(baseline)})
            self.assertNotEqual(0, result.returncode)
            self.assertIn("第三步：逐个阶段执行", result.stdout)


if __name__ == "__main__":
    unittest.main()
