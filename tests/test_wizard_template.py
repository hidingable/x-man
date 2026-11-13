import os
import pty
import select
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "skills/wizard/assets/wizard-template.sh"
BASH = "/bin/bash"


class WizardTemplateTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wizard-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.environment = os.environ.copy()
        self.environment.update({
            "WIZARD_TEMPLATE": str(TEMPLATE),
            "CASE_ROOT": str(self.root),
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
        })

    def run_script(self, body, *, input_text="", extra_env=None, trace=False):
        script = self.root / "case.sh"
        script.write_text('source "$WIZARD_TEMPLATE"\n' + body, encoding="utf-8")
        environment = self.environment.copy()
        environment.update(extra_env or {})
        return subprocess.run(
            [BASH, *(["-x"] if trace else []), str(script)],
            cwd=self.root, env=environment, input=input_text,
            text=True, capture_output=True, timeout=8,
        )

    def fake(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
        path.chmod(0o700)
        return path

    def assert_ok(self, result):
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_template_syntax_and_unconfigured_execution_refuses(self):
        syntax = subprocess.run([BASH, "-n", str(TEMPLATE)], capture_output=True, text=True)
        self.assert_ok(syntax)
        for args in ([], ["--dry-run"]):
            result = subprocess.run([BASH, str(TEMPLATE), *args], capture_output=True, text=True)
            self.assertEqual(64, result.returncode)
            self.assertIn("no steps configured", result.stderr)

    def test_dry_run_invokes_no_callbacks_opener_python_or_input(self):
        self.fake("open", 'touch "$CASE_ROOT/opened"\n')
        self.fake("python3", 'touch "$CASE_ROOT/python-used"\nexit 9\n')
        result = self.run_script(r'''
wizard_init --dry-run
probe() { touch "$CASE_ROOT/probed"; return 1; }
action() { ask_secret token 'Token'; touch "$CASE_ROOT/acted"; }
verify() { touch "$CASE_ROOT/verified"; }
run_stage 'Configure account' probe action verify
ask answer 'Name'
ask_secret token 'Token'
write_env "$CASE_ROOT/.env" TOKEN UNSET_VALUE
open_url 'https://example.com/settings'
IFS= read -r untouched
[ "$untouched" = 'not-consumed' ]
''', input_text="not-consumed\n")
        self.assert_ok(result)
        for name in ("opened", "python-used", "probed", "acted", "verified", ".env"):
            self.assertFalse((self.root / name).exists(), name)

    def test_confirmation_defaults_to_no_and_eof_cannot_authorize(self):
        for text in ("", "\n", "no\n", "yes", "unexpected\n"):
            with self.subTest(text=text):
                result = self.run_script("wizard_init\nconfirm 'Apply'\n", input_text=text)
                self.assertEqual(1, result.returncode)
        result = self.run_script("wizard_init\nconfirm 'Apply'\n", input_text="yes\n")
        self.assert_ok(result)

    def test_ask_preserves_spaces_and_secret_does_not_leak_with_xtrace(self):
        secret = "test-secret-'$` ; whitespace"
        result = self.run_script(r'''
wizard_init
ask answer 'Name'
[ "$answer" = '  some name  ' ]
ask_secret token 'Token'
write_env "$CASE_ROOT/.env" TOKEN token
unset token
''', input_text="  some name  \n" + secret + "\n", trace=True)
        self.assert_ok(result)
        self.assertNotIn(secret, result.stdout + result.stderr)
        value = subprocess.run(
            [BASH, "-c", 'source "$1"; printf "%s" "$TOKEN"', "read-fixture", str(self.root / ".env")],
            capture_output=True, text=True,
        )
        self.assert_ok(value)
        self.assertEqual(secret, value.stdout)

    def test_secret_input_disables_terminal_echo(self):
        script = self.root / "terminal.sh"
        script.write_text('source "$WIZARD_TEMPLATE"\nwizard_init\nask_secret token "Token"\n[ -n "$token" ]\n')
        master, slave = pty.openpty()
        process = subprocess.Popen(
            [BASH, str(script)], cwd=self.root, env=self.environment,
            stdin=slave, stdout=slave, stderr=slave,
        )
        os.close(slave)
        output = b""
        secret = b"terminal-hidden-token"
        try:
            deadline = time.monotonic() + 5
            while b"Token: " not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 4096)
            self.assertIn(b"Token: ", output)
            # The prompt is written immediately before read -s changes echo mode.
            import termios
            while termios.tcgetattr(master)[3] & termios.ECHO and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(termios.tcgetattr(master)[3] & termios.ECHO)
            os.write(master, secret + b"\n")
            process.wait(timeout=5)
            while select.select([master], [], [], 0)[0]:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
            self.assertEqual(0, process.returncode)
            self.assertNotIn(secret, output)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    def test_input_eof_fails_and_clears_stale_value(self):
        for name in ("ask", "ask_secret"):
            result = self.run_script(f'''wizard_init
token=stale
if {name} token 'Token'; then exit 99; fi
[ -z "$token" ]
''')
            self.assert_ok(result)

    def test_env_update_preserves_other_entries_is_atomic_and_idempotent(self):
        path = self.root / ".env"
        old = "# retained\nOTHER=untouched\nTOKEN=old\nexport TOKEN=duplicate\nLAST=tail"
        path.write_text(old)
        path.chmod(0o644)
        first_inode = path.stat().st_ino
        secret = 'quote\' $HOME `not-a-command` " space'
        body = 'wizard_init\nwrite_env "$CASE_ROOT/.env" TOKEN INPUT_TOKEN\n'
        first = self.run_script(body, extra_env={"INPUT_TOKEN": secret})
        self.assert_ok(first)
        self.assertNotEqual(first_inode, path.stat().st_ino)
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        text = path.read_text()
        self.assertTrue(text.startswith("# retained\nOTHER=untouched\n"))
        self.assertTrue(text.endswith("LAST=tail"))
        self.assertEqual(1, sum(line.startswith(("TOKEN=", "export TOKEN=")) for line in text.splitlines()))
        before = (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
        self.assert_ok(self.run_script(body, extra_env={"INPUT_TOKEN": secret}))
        self.assertEqual(before, (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns))
        self.assertFalse(list(self.root.glob(".wizard-*")))

    def test_env_append_retains_final_line_and_uses_private_mode(self):
        path = self.root / ".env"
        path.write_text("OTHER=last")
        result = self.run_script('wizard_init\nvalue=\nwrite_env "$CASE_ROOT/.env" EMPTY value\n')
        self.assert_ok(result)
        self.assertEqual("OTHER=last\nEMPTY=''\n", path.read_text())
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))

    def test_env_preserves_export_for_child_process_after_source(self):
        (self.root / ".env").write_text("export DEMO_KEY=old\n")
        result = self.run_script(r'''
wizard_init
value=new
write_env "$CASE_ROOT/.env" DEMO_KEY value
unset DEMO_KEY
source "$CASE_ROOT/.env"
python3 -c 'import os; print(os.environ.get("DEMO_KEY", "missing"))'
''')
        self.assert_ok(result)
        self.assertEqual("new\n", result.stdout)

    def test_env_duplicate_assignments_retain_export_and_plain_keys_stay_local(self):
        path = self.root / ".env"
        path.write_text("DEMO_KEY=old\nexport DEMO_KEY=duplicate\nPLAIN_KEY=old\n")
        result = self.run_script(r'''
wizard_init
value=new
write_env "$CASE_ROOT/.env" DEMO_KEY value
write_env "$CASE_ROOT/.env" PLAIN_KEY value
unset DEMO_KEY PLAIN_KEY
source "$CASE_ROOT/.env"
[ "$PLAIN_KEY" = new ]
python3 -c 'import os; print(os.environ.get("DEMO_KEY", "missing")); print(os.environ.get("PLAIN_KEY", "not-exported"))'
''')
        self.assert_ok(result)
        self.assertEqual("new\nnot-exported\n", result.stdout)
        self.assertEqual(1, sum("DEMO_KEY=" in line for line in path.read_text().splitlines()))

    def test_env_rejects_symlink_multiline_and_unreadable_data_without_replacement(self):
        target = self.root / "real.env"
        target.write_text("SAFE=original\n")
        path = self.root / ".env"
        path.symlink_to(target)
        body = 'wizard_init\nwrite_env "$CASE_ROOT/.env" TOKEN INPUT_TOKEN\n'
        result = self.run_script(body, extra_env={"INPUT_TOKEN":"secret"})
        self.assertNotEqual(0, result.returncode)
        self.assertTrue(path.is_symlink())
        self.assertEqual("SAFE=original\n", target.read_text())
        path.unlink()
        for original, secret in ((b"SAFE=original\n", "one\ntwo"),
                                 (b"SAFE=original\n", "one\rtwo"),
                                 (b"\xff\n", "secret"),
                                 (b"TOKEN='multi\nline'\n", "secret")):
            with self.subTest(original=original, secret=secret):
                path.write_bytes(original)
                result = self.run_script(body, extra_env={"INPUT_TOKEN":secret})
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(original, path.read_bytes())
                self.assertNotIn(secret, result.stdout + result.stderr)
        result = self.run_script('wizard_init\nvalue=secret\nwrite_env "$CASE_ROOT/.env" $\'KEY\\nOTHER\' value\n')
        self.assertNotEqual(0, result.returncode)

    def test_env_rejects_key_inside_other_multiline_value_without_changing_file(self):
        path = self.root / ".env"
        for original in (
            "OTHER='first\nTOKEN=embedded\nlast'\n",
            'OTHER="first\nexport TOKEN=embedded\nlast"\nTOKEN=old\n',
            "OTHER=first\\\nTOKEN=embedded\n",
            "OTHER=$(cat <<'END'\nTOKEN=embedded\nEND\n)\n",
        ):
            with self.subTest(original=original):
                path.write_text(original)
                path.chmod(0o640)
                before = (path.read_bytes(), path.stat().st_ino,
                          path.stat().st_mtime_ns, stat.S_IMODE(path.stat().st_mode))
                secret = "replacement-secret"
                result = self.run_script(
                    'wizard_init\nwrite_env "$CASE_ROOT/.env" TOKEN INPUT_TOKEN\n',
                    extra_env={"INPUT_TOKEN": secret},
                )
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, (path.read_bytes(), path.stat().st_ino,
                                         path.stat().st_mtime_ns, stat.S_IMODE(path.stat().st_mode)))
                self.assertFalse(list(self.root.glob(".wizard-*")))
                self.assertNotIn(secret, result.stdout + result.stderr)
                self.assertNotIn("embedded", result.stdout + result.stderr)

    def test_env_preserves_single_line_quoted_values_and_comment_quotes(self):
        path = self.root / ".env"
        original = "# unmatched ' comment\nOTHER='literal TOKEN=embedded'\n"
        path.write_text(original)
        result = self.run_script(
            'wizard_init\nvalue=new\nwrite_env "$CASE_ROOT/.env" TOKEN value\n',
        )
        self.assert_ok(result)
        self.assertEqual(original + "TOKEN=new\n", path.read_text())
        sourced = subprocess.run(
            [BASH, "-c", 'source "$1"; printf "%s\\n%s" "$OTHER" "$TOKEN"',
             "read-fixture", str(path)], capture_output=True, text=True,
        )
        self.assert_ok(sourced)
        self.assertEqual("literal TOKEN=embedded\nnew", sourced.stdout)

    def test_env_read_permission_failure_is_not_treated_as_absent(self):
        if os.geteuid() == 0:
            self.skipTest("root can read mode-000 files")
        path = self.root / ".env"
        path.write_text("SAFE=original\n")
        path.chmod(0)
        try:
            result = self.run_script('wizard_init\nvalue=secret\nwrite_env "$CASE_ROOT/.env" TOKEN value\n')
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(0, stat.S_IMODE(path.stat().st_mode))
        finally:
            path.chmod(0o600)
        self.assertEqual("SAFE=original\n", path.read_text())

    def test_secret_is_not_in_python_arguments(self):
        python = shutil.which("python3")
        self.fake("python3", 'printf "%s\\n" "$@" > "$CASE_ROOT/python-args"\nexec ' + shlex.quote(python) + ' "$@"\n')
        secret = "unique-argv-test-secret"
        result = self.run_script('wizard_init\nwrite_env "$CASE_ROOT/.env" TOKEN INPUT_TOKEN\n', extra_env={"INPUT_TOKEN":secret})
        self.assert_ok(result)
        self.assertNotIn(secret, (self.root / "python-args").read_text())
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_atomic_replacement_failure_leaves_original_and_no_temporary_file(self):
        path = self.root / ".env"
        original = b"TOKEN=original\nOTHER=retained\n"
        path.write_bytes(original)
        program = '''import os, sys
code = sys.stdin.read()
sys.argv = sys.argv[1:]
def fail_replace(*args, **kwargs):
    raise OSError("simulated replacement failure")
os.replace = fail_replace
exec(compile(code, "wizard-write-env", "exec"))
'''
        python = shutil.which("python3")
        self.fake("python3", "exec " + shlex.quote(python) + " -c " + shlex.quote(program) + ' "$@"\n')
        result = self.run_script('wizard_init\nwrite_env "$CASE_ROOT/.env" TOKEN INPUT_TOKEN\n', extra_env={"INPUT_TOKEN":"new-secret"})
        self.assertEqual(1, result.returncode)
        self.assertEqual(original, path.read_bytes())
        self.assertFalse(list(self.root.glob(".wizard-*")))
        self.assertNotIn("new-secret", result.stdout + result.stderr)

    def test_stage_success_verifies_and_rerun_skips_action(self):
        body = r'''
wizard_init
probe() { [ -f "$CASE_ROOT/done" ]; }
action() { printf 'run\n' >> "$CASE_ROOT/actions"; touch "$CASE_ROOT/done"; }
verify() { [ -f "$CASE_ROOT/done" ]; }
run_stage 'Local change' probe action verify
'''
        first = self.run_script(body, input_text="y\n")
        self.assert_ok(first)
        self.assertIn("Verified:", first.stdout)
        second = self.run_script(body)
        self.assert_ok(second)
        self.assertIn("Already complete:", second.stdout)
        self.assertEqual("run\n", (self.root / "actions").read_text())

    def test_stage_cancel_probe_action_and_verification_failures(self):
        cases = [("return 1", "return 0", "return 0", "", 1, "Cancelled"),
                 ("return 3", "return 0", "return 0", "y\n", 3, "Probe failed"),
                 ("return 1", "return 7", "return 0", "y\n", 7, "Action failed"),
                 ("return 1", "return 0", "return 6", "y\n", 6, "Verification failed")]
        for probe, action, verify, text, code, message in cases:
            with self.subTest(message=message):
                result = self.run_script(f'''wizard_init
probe() {{ {probe}; }}
action() {{ {action}; }}
verify() {{ {verify}; }}
run_stage 'Local change' probe action verify
''', input_text=text)
                self.assertEqual(code, result.returncode, result.stdout + result.stderr)
                self.assertIn(message, result.stderr)
                self.assertNotIn("Verified:", result.stdout)

    def test_probe_maps_failed_read_to_error_not_configuration_needed(self):
        result = self.run_script(r'''
wizard_init
probe() {
  local status
  if status=$(cat "$CASE_ROOT/missing-state" 2>/dev/null); then
    [ "$status" = complete ]
  else
    return 2
  fi
}
action() { touch "$CASE_ROOT/acted"; }
verify() { return 0; }
run_stage 'Local change' probe action verify
''', input_text="y\n")
        self.assertEqual(2, result.returncode)
        self.assertFalse((self.root / "acted").exists())
        self.assertIn("Probe failed (2)", result.stderr)

    def test_unknown_option_unset_value_and_missing_stage_function_fail(self):
        for body in (
            'wizard_init --unexpected\n',
            'wizard_init\nwrite_env "$CASE_ROOT/.env" TOKEN MISSING_VALUE\n',
            'wizard_init\nrun_stage Task missing missing missing\n',
            'confirm Apply\n',
        ):
            with self.subTest(body=body):
                result = self.run_script(body)
                self.assertEqual(64, result.returncode)
                self.assertFalse((self.root / ".env").exists())

    def test_intermediate_callback_errors_survive_conditional_stage_call(self):
        self.fake("read-state", "exit 4\n")
        result = self.run_script(r'''
wizard_init
probe() { read-state; touch "$CASE_ROOT/probe-tail"; return 1; }
action() { touch "$CASE_ROOT/acted"; }
verify() { return 0; }
if run_stage 'Local change' probe action verify; then exit 99; else exit "$?"; fi
''', input_text="y\n")
        self.assertEqual(4, result.returncode, result.stdout + result.stderr)
        self.assertFalse((self.root / "probe-tail").exists())
        self.assertFalse((self.root / "acted").exists())
        self.assertIn("Probe failed (4)", result.stderr)
        result = self.run_script(r'''
wizard_init
probe() { return 1; }
action() { read-state; touch "$CASE_ROOT/action-tail"; }
verify() { return 0; }
if run_stage 'Local change' probe action verify; then exit 99; else exit "$?"; fi
''', input_text="y\n")
        self.assertEqual(4, result.returncode)
        self.assertFalse((self.root / "action-tail").exists())
        self.assertNotIn("Verified:", result.stdout)

    def test_browser_uses_exact_url_and_propagates_failure(self):
        self.fake("open", 'printf "%s" "$1" > "$CASE_ROOT/open-url"\nexit 5\n')
        result = self.run_script("wizard_init\nopen_url 'https://example.com/settings?tab=keys'\n")
        self.assertEqual(5, result.returncode)
        self.assertEqual("https://example.com/settings?tab=keys", (self.root / "open-url").read_text())
        for url in ("file:///tmp/example", "javascript:alert(1)", "https:///path", "https://?query", "https://user:password@example.com"):
            result = self.run_script("wizard_init\nopen_url " + shlex.quote(url) + "\n")
            self.assertEqual(64, result.returncode, url)


if __name__ == "__main__":
    unittest.main()
