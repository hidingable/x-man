import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "render_card.py"
SPEC = importlib.util.spec_from_file_location("ascii_card_render", SCRIPT)
render_card = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(render_card)


class RenderCardTest(unittest.TestCase):
    def assert_all_lines_have_width(self, output: str, width: int) -> None:
        self.assertEqual(
            [width] * len(output.splitlines()),
            [render_card.disp_width(line) for line in output.splitlines()],
        )

    def test_text_hard_breaks_are_rendered_as_bordered_lines(self) -> None:
        output = render_card.render(
            {"width": 12, "rows": [{"type": "text", "text": "A\n中文"}]}
        )

        self.assertEqual(
            "+----------+\n| A        |\n| 中文     |\n+----------+",
            output,
        )
        self.assert_all_lines_have_width(output, 12)

    def test_pre_preserves_multiline_spacing(self) -> None:
        output = render_card.render(
            {
                "width": 14,
                "rows": [{"type": "pre", "text": "A -> B\n  B --> A"}],
            }
        )

        self.assertIn("| A -> B     |", output)
        self.assertIn("|   B --> A  |", output)
        self.assert_all_lines_have_width(output, 14)

    def test_pre_rejects_overflow_instead_of_reflowing(self) -> None:
        with self.assertRaisesRegex(render_card.CardError, "pre.*放不下"):
            render_card.render(
                {"width": 8, "rows": [{"type": "pre", "text": "1234567"}]}
            )

    def test_tab_and_escape_are_rejected(self) -> None:
        for text in ("A\tB", "A\x1b[31mB", "A\u2028B"):
            with self.subTest(text=repr(text)):
                with self.assertRaisesRegex(render_card.CardError, "控制字符"):
                    render_card.render(
                        {"width": 12, "rows": [{"type": "text", "text": text}]}
                    )

    def test_schema_rejects_invalid_card_and_row_fields(self) -> None:
        invalid_cases = [
            ({"width": "wide", "rows": []}, "width"),
            ({"width": 12, "padding": -1, "rows": []}, "padding"),
            ({"width": 12, "rows": ["hello"]}, r"rows\[0\]"),
            (
                {"width": 12, "rows": [{"type": "text", "text": "A", "algin": "left"}]},
                r"rows\[0\].*algin",
            ),
        ]
        for data, message in invalid_cases:
            with self.subTest(data=data):
                with self.assertRaisesRegex(render_card.CardError, message):
                    render_card.render(data)

    def test_auto_width_keeps_at_least_one_content_column(self) -> None:
        output = render_card.render({"width": "auto", "rows": []})

        self.assertEqual("+---+\n+---+", output)
        self.assert_all_lines_have_width(output, 5)

    def test_unicode_and_rounded_styles_use_distinct_box_junctions(self) -> None:
        unicode_output = render_card.render(
            {
                "width": 10,
                "style": "unicode",
                "rows": [{"type": "text", "text": "中文"}, {"type": "divider"}],
            }
        )
        rounded_output = render_card.render(
            {"width": 10, "style": "rounded", "rows": [{"type": "blank"}]}
        )

        self.assertEqual("┌────────┐", unicode_output.splitlines()[0])
        self.assertIn("├────────┤", unicode_output)
        self.assertEqual("└────────┘", unicode_output.splitlines()[-1])
        self.assertEqual("╭────────╮", rounded_output.splitlines()[0])
        self.assertEqual("╰────────╯", rounded_output.splitlines()[-1])
        self.assert_all_lines_have_width(unicode_output, 10)
        self.assert_all_lines_have_width(rounded_output, 10)

    def test_custom_border_glyphs_must_be_one_display_column(self) -> None:
        with self.assertRaisesRegex(render_card.CardError, "显示宽度必须为 1"):
            render_card.render(
                {
                    "width": 12,
                    "chars": {"vertical": "中"},
                    "rows": [{"type": "text", "text": "A"}],
                }
            )

    def test_legacy_border_keys_remain_compatible(self) -> None:
        output = render_card.render(
            {
                "width": 8,
                "chars": {"corner": "*", "h": "=", "v": "!"},
                "rows": [{"type": "divider"}],
            }
        )

        self.assertEqual("*======*\n*======*\n*======*", output)

    def test_button_aliases_are_mutually_exclusive(self) -> None:
        with self.assertRaisesRegex(render_card.CardError, "不能同时提供"):
            render_card.render(
                {
                    "width": 20,
                    "rows": [
                        {
                            "type": "row",
                            "text": "事项",
                            "button": "查看",
                            "buttons": ["处理"],
                        }
                    ],
                }
            )

    def test_cli_style_override_and_invalid_json_errors_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "card.json"
            source.write_text('{"width": 10, "rows": [{"type": "blank"}]}', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--style", "double", "--check"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(result.stdout.startswith("╔════════╗"))
            self.assertIn("[check] OK", result.stderr)

            source.write_text("{bad json", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("无法解析", result.stderr)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
