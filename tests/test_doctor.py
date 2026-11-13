import os
from contextlib import contextmanager
import shutil
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path


DOCTOR = Path(__file__).resolve().parents[1] / "scripts" / "doctor.sh"


class DoctorTest(unittest.TestCase):
    @contextmanager
    def version_environment(self, verbose_command, *, missing_yaml=False, failed_command=""):
        """Version producers use many writes so early pipe closure is deterministic."""
        with tempfile.TemporaryDirectory() as temp_dir:
            shim = '''#!/bin/sh
tool="${0##*/}"
if [ "$1" = "--version" ]; then
  if [ "$tool" = "$XMAN_TEST_FAILED_COMMAND" ]; then
    echo "version command failed" >&2
    exit 7
  fi
  exec "$XMAN_TEST_PYTHON" -c '
import os, signal, sys
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
os.write(1, ("fixture " + sys.argv[1] + " version 1.0\\n").encode())
if sys.argv[1] == os.environ["XMAN_TEST_VERBOSE_COMMAND"]:
    for _ in range(256):
        os.write(1, b"unused version detail\\n" * 1024)
' "$tool"
fi
case "$tool" in
  python3)
    if [ "$XMAN_TEST_MISSING_YAML" = "1" ] && [ "$1" = "-c" ]; then
      case "$2" in
        *"import yaml"*) exec "$XMAN_TEST_PYTHON" -I -S "$@" ;;
      esac
    fi
    exec "$XMAN_TEST_PYTHON" "$@" ;;
  git) exec "$XMAN_TEST_GIT" "$@" ;;
esac
exit 1
'''
            for name in ("bash", "python3", "git", "rsync", "shasum"):
                executable = Path(temp_dir) / name
                executable.write_text(shim, encoding="utf-8")
                executable.chmod(0o755)
            yield {
                **os.environ,
                "PATH": f"{temp_dir}:{os.environ['PATH']}",
                "XMAN_TEST_PYTHON": sys.executable,
                "XMAN_TEST_GIT": shutil.which("git"),
                "XMAN_TEST_VERBOSE_COMMAND": verbose_command,
                "XMAN_TEST_MISSING_YAML": "1" if missing_yaml else "0",
                "XMAN_TEST_FAILED_COMMAND": failed_command,
            }

    def test_multiline_versions_do_not_interrupt_dependency_checks(self) -> None:
        for command in ("bash", "python3", "git", "rsync", "shasum"):
            with self.subTest(command=command), self.version_environment(command) as env:
                result = subprocess.run([str(DOCTOR)], capture_output=True, text=True, env=env)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn(f"fixture {command} version 1.0", result.stdout)
                self.assertNotIn("unused version detail", result.stdout)
                self.assertNotIn("已安装", result.stdout)
                self.assertIn("失败 0", result.stdout)
                self.assertIn("✅ 环境就绪", result.stdout)

    def test_multiline_versions_preserve_missing_dependency_failure(self) -> None:
        with self.version_environment("rsync", missing_yaml=True) as env:
            result = subprocess.run([str(DOCTOR)], capture_output=True, text=True, env=env)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("python3 -m pip install PyYAML", result.stdout)
        self.assertIn("失败 1", result.stdout)
        self.assertNotIn("✅ 环境就绪", result.stdout)

    def test_version_command_failure_is_not_hidden(self) -> None:
        with self.version_environment("", failed_command="rsync") as env:
            result = subprocess.run([str(DOCTOR)], capture_output=True, text=True, env=env)
        self.assertEqual(7, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("✅ 环境就绪", result.stdout)

    def test_missing_pyyaml_is_rejected_before_repository_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_python = Path(temp_dir) / "python3"
            fake_python.write_text(
                '#!/bin/sh\n'
                'case "$2" in\n'
                '  *"import yaml"*) exec "$XMAN_TEST_PYTHON" -I -S "$@" ;;\n'
                'esac\n'
                'exec "$XMAN_TEST_PYTHON" "$@"\n', encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = {**os.environ, "PATH": f"{temp_dir}:{os.environ['PATH']}",
                   "XMAN_TEST_PYTHON": sys.executable}
            result = subprocess.run([str(DOCTOR)], check=False, capture_output=True, text=True, env=env)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("PyYAML", result.stdout)
        self.assertIn("python3 -m pip install PyYAML", result.stdout)
        self.assertNotIn("✅ 环境就绪", result.stdout)

    def test_python_38_is_rejected_with_explicit_minimum_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_python = Path(temp_dir) / "python3"
            fake_python.write_text(
                """#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "Python 3.8.18"
  exit 0
fi
if [ "$1" = "-c" ]; then
  exit 1
fi
exit 1
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{temp_dir}:{env['PATH']}"

            result = subprocess.run(
                [str(DOCTOR)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("Python >= 3.9", result.stdout)


if __name__ == "__main__":
    unittest.main()
