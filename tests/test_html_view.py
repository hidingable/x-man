"""html-view 渲染脚本的回归检查。脚本是 Node 写的，本机没有 node 时跳过。"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/html-view/scripts/render.mjs"


@unittest.skipUnless(shutil.which("node"), "需要 Node.js")
class HtmlViewTest(unittest.TestCase):
    def render(self, md):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.md"
            src.write_text(md, encoding="utf-8")
            subprocess.run(["node", str(SCRIPT), str(src)], check=True, capture_output=True)
            return src.with_suffix(".html").read_text(encoding="utf-8")

    def test_wide_chars_in_code_block_get_2ch_box(self):
        html = self.render("# t\n\n```\n| 身份证 ID |\n```\n\n正文中文不包\n")
        self.assertIn('<code>| <span class="w">身</span><span class="w">份</span><span class="w">证</span> ID |</code>', html)
        self.assertNotIn('<span class="w">正</span>', html, "只处理代码块")
        self.assertIn("pre .w{display:inline-block;width:2ch", html)


if __name__ == "__main__":
    unittest.main()
