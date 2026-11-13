"""面向人的产物文风检查（scripts/check-prose.py）。

背景：conventions.md〈输出〉对这四类表达有明确规则，但原先没有任何脚本跑在散文上——
规则会随下一次改文档静默退化。check-prose.py 把禁令变成可检测的报告，这里钉住
它的判定行为：四类命中都报、围栏与行内反引号里的引用不算、规则源文件本身不扫、
以及「只报告不阻断」——文风命中退出码为 0，真实读取错误仍需报错。

最后一条是刻意钉的：把主观的文风判定接成红灯，下次有人为了过校验改写措辞，
规则就失效了。这条用例存在的意义就是防止有人日后顺手把它改成 fail。
"""

import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-prose.py"


def run_check(*paths: Path, script: Path = SCRIPT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *[str(p) for p in paths]],
        check=False, capture_output=True, text=True, cwd=script.parent.parent,
    )


def isolated_script(directory: Path) -> Path:
    """保留脚本相对仓库根的布局，使默认范围完全来自临时夹具。"""
    script = directory / "scripts" / SCRIPT.name
    script.parent.mkdir()
    script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    return script


def write_sample(directory: Path, body: str, name: str = "sample.md") -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


class ProseCheckTest(unittest.TestCase):
    def test_clean_prose_reports_ok_with_verdict_marker(self) -> None:
        """干净产物首行是 OK<TAB>…，供 validate.sh 渲染成 pass。"""
        with tempfile.TemporaryDirectory() as tmp:
            write_sample(Path(tmp), "# 结论\n\n改 `src/auth.ts:42`，然后跑 `npm test`。\n")
            result = run_check(Path(tmp))
        self.assertEqual(0, result.returncode, result.stderr)
        head = result.stdout.splitlines()[0]
        self.assertEqual("OK", head.split("\t", 1)[0], result.stdout)

    def test_each_of_the_four_categories_is_reported(self) -> None:
        # 每类各占一行：脚本每行只报第一条命中的规则，同一行压两类会漏掉一类。
        body = (
            "让我来看看这个问题。\n\n"
            "改完了。还有什么需要帮忙的吗？\n\n"
            "这个做法应该没问题。\n\n"
            "哎呀，测试失败了，好像出了点问题。\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            write_sample(Path(tmp), body)
            result = run_check(Path(tmp))
        self.assertEqual(0, result.returncode, result.stderr)
        for category in ("开场预告", "客套收尾", "报错语气", "含糊堆砌"):
            self.assertIn(category, result.stdout, f"漏报 {category}\n{result.stdout}")

    def test_fenced_code_block_is_not_scanned(self) -> None:
        """围栏里的内容是对规则的引用或示例，不该算命中。"""
        body = "正文没有禁用表达。\n\n```\n让我来看看\n随时问我\n```\n"
        with tempfile.TemporaryDirectory() as tmp:
            write_sample(Path(tmp), body)
            result = run_check(Path(tmp))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("PROSE_WARN", result.stdout, result.stdout)

    def test_inline_code_is_not_scanned(self) -> None:
        """行内反引号里引用禁令原文时同样不该算命中。"""
        body = "规则里禁止 `让我来看看`，也禁止 `随时问我`。\n"
        with tempfile.TemporaryDirectory() as tmp:
            write_sample(Path(tmp), body)
            result = run_check(Path(tmp))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("PROSE_WARN", result.stdout, result.stdout)

    def test_rule_source_is_never_scanned(self) -> None:
        """conventions.md 本身写着全部禁用词，扫它必然满屏命中——必须排除。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = isolated_script(root)
            context = root / "context"
            context.mkdir()
            source = write_sample(context, "让我来看看。\n", "conventions.md")
            result = run_check(source, script=script)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("PROSE_WARN", result.stdout, result.stdout)

    def test_hits_do_not_change_exit_code(self) -> None:
        """只报告不阻断：有命中也退出 0。"""
        with tempfile.TemporaryDirectory() as tmp:
            write_sample(Path(tmp), "让我来看看。\n")
            result = run_check(Path(tmp))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PROSE_WARN", result.stdout, result.stdout)
        self.assertEqual("WARN", result.stdout.splitlines()[0].split("\t", 1)[0])

    def test_validate_long_prose_report_only_warns_and_reaches_summary(self) -> None:
        """覆盖真实 Shell 包装层：长报告只警告，完整输出并到达汇总。"""
        validator = (REPO_ROOT / "scripts" / "validate.sh").read_text(encoding="utf-8")
        # 沿用实际初始化、输出函数、文风检查及汇总，隔离其他仓库检查。
        preamble = validator[:validator.index("# agent 定义")]
        prose_and_summary = validator[validator.index("# ─── 12."):]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = isolated_script(root)
            scope = root / ".ai-configs"
            scope.mkdir()
            write_sample(scope, "应该可以。\n" * 3000)
            runner = script.parent / "validate-prose.sh"
            runner.write_text(preamble + prose_and_summary, encoding="utf-8")
            result = subprocess.run(
                ["/bin/bash", str(runner)], cwd=root,
                check=False, capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout[-2000:])
        self.assertIn("3000 处", result.stdout)
        self.assertIn("sample.md:3000", result.stdout)
        self.assertIn("=== 汇总 ===", result.stdout)
        self.assertIn("失败: 0", result.stdout)
        self.assertIn("警告: 1", result.stdout)

    def test_default_scope_reports_fixture_verdict_without_blocking(self) -> None:
        """默认范围按固定夹具判定，不要求真实项目产物零命中。"""
        for state, verdict in (
            ("missing", "WARN"),
            ("empty", "OK"),
            ("clean", "OK"),
            ("warning", "WARN"),
        ):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                script = isolated_script(root)
                scope = root / ".ai-configs"
                if state != "missing":
                    scope.mkdir()
                if state in ("clean", "warning"):
                    body = "让我来看看。\n" if state == "warning" else "已运行测试。\n"
                    write_sample(scope, body)
                result = run_check(script=script)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertTrue(result.stdout.startswith(f"{verdict}\t"), result.stdout)
                self.assertEqual(state == "warning", "PROSE_WARN" in result.stdout, result.stdout)

    def test_missing_scope_does_not_displace_warning_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = write_sample(root, "让我来看看。\n")
            result = run_check(root / "missing", sample)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("WARN", result.stdout.splitlines()[0].split("\t", 1)[0], result.stdout)
        self.assertIn("不存在", result.stdout, result.stdout)
        self.assertIn("PROSE_WARN", result.stdout, result.stdout)

    def test_invalid_utf8_is_an_execution_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "invalid.md"
            sample.write_bytes(b"\xff")
            result = run_check(sample)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("UnicodeDecodeError", result.stderr)
        self.assertNotIn("OK\t", result.stdout)

    def test_read_errors_are_not_reported_as_clean(self) -> None:
        scan_file = runpy.run_path(str(SCRIPT))["scan_file"]
        with patch.object(Path, "read_text", side_effect=OSError("fixture read failure")):
            with self.assertRaisesRegex(OSError, "fixture read failure"):
                scan_file(Path("sample.md"))


if __name__ == "__main__":
    unittest.main()
