"""xman-verify（web-access 补丁层）的行为测试。

真浏览器不在测试环境里，所以这里用一个假 proxy 顶替 cdp-proxy 的 /targets 和 /eval，
覆盖参数解析、超时、轮询逻辑、输出格式和退出码。注入页面那段 JS 只验证语法，
它在真浏览器里的行为要靠人工跑一遍。
"""

import json
import os
import pathlib
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "skills" / "web-access" / "scripts" / "xman-verify.mjs"

STATE = {"settled": True, "console": [], "net": [], "hang": False}


class FakeProxy(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/targets"):
            if STATE["hang"]:
                threading.Event().wait(5)       # 模拟 proxy 挂着不回
            self._json([{"id": "T1", "title": "fake"}])
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        expr = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        if "__xmanProbe = p" in expr:                       # RECORDER
            self._json({"value": {"already": False}})
        elif "readyState: document.readyState" in expr:      # PROBE_STATE
            self._json({"value": {
                "armed": True,
                "readyState": "complete" if STATE["settled"] else "loading",
                "pending": 0 if STATE["settled"] else 2,
                "sinceMutation": 9999 if STATE["settled"] else 0,
                "htmlLen": 1234,
            }})
        elif "window.__xmanProbe.console" in expr:           # READ_CONSOLE
            self._json({"value": STATE["console"]})
        elif "getEntriesByType" in expr:                     # READ_NET
            self._json({"value": {"armed": True, "hooked": STATE["net"], "observed": []}})
        else:
            self._json({"error": f"未预期的表达式: {expr[:60]}"}, 400)


class VerifyProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProxy)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_cli(self, *args, timeout=30):
        return subprocess.run(
            ["node", str(CLI), *args],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "CDP_PROXY_PORT": str(self.port)},
        )

    def setUp(self):
        STATE.update({"settled": True, "console": [], "net": [], "hang": False})

    def test_注入页面的记录器是合法_JS(self):
        source = CLI.read_text(encoding="utf-8")
        start = source.index("const RECORDER = `") + len("const RECORDER = `")
        recorder = source[start:source.index("`;", start)]
        check = subprocess.run(["node", "-e", f"new Function({json.dumps(recorder)})"],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_doctor_报告标签页(self):
        r = self.run_cli("doctor", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["targets"][0]["id"], "T1")

    def test_proxy_不回应时限时失败而不是卡死(self):
        STATE["hang"] = True
        r = self.run_cli("doctor", "--net-timeout", "800", timeout=15)
        self.assertEqual(r.returncode, 1)
        self.assertIn("没回应", r.stderr)
        self.assertIn("check-deps.mjs", r.stderr)      # 告诉 agent 该干什么

    def test_缺_target_时给出下一步而不是报栈(self):
        r = self.run_cli("console")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--target", r.stderr)
        self.assertIn("doctor", r.stderr)

    def test_arm_的_dry_run_不发请求(self):
        r = self.run_cli("arm", "--target", "T1", "--dry-run", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["wouldInject"])

    def test_页面稳了就返回_0(self):
        r = self.run_cli("wait-settle", "--target", "T1", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["settled"])

    def test_页面没稳是证据_退出码_2_并说明卡在哪(self):
        STATE["settled"] = False
        r = self.run_cli("wait-settle", "--target", "T1", "--timeout", "1200", "--json")
        self.assertEqual(r.returncode, 2)
        out = json.loads(r.stdout)
        self.assertFalse(out["settled"])
        self.assertEqual(out["pending"], 2)

    def test_console_有_error_时退出码_2(self):
        STATE["console"] = [{"level": "error", "at": 1, "text": "boom"},
                            {"level": "log", "at": 2, "text": "noise"}]
        r = self.run_cli("console", "--target", "T1", "--json")
        self.assertEqual(r.returncode, 2)
        out = json.loads(r.stdout)
        self.assertEqual(out["total"], 2)
        self.assertEqual([e["text"] for e in out["entries"]], ["boom"])   # 默认滤掉 log

    def test_console_没有_error_时退出码_0(self):
        STATE["console"] = [{"level": "log", "at": 1, "text": "fine"}]
        r = self.run_cli("console", "--target", "T1", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_network_失败请求退出码_2_且能只列失败(self):
        STATE["net"] = [
            {"kind": "fetch", "url": "https://a/ok", "status": 200, "ok": True, "ms": 10},
            {"kind": "fetch", "url": "https://a/bad", "status": 500, "ok": False, "ms": 20},
        ]
        r = self.run_cli("network", "--target", "T1", "--only-failed", "--json")
        self.assertEqual(r.returncode, 2)
        out = json.loads(r.stdout)
        self.assertEqual(out["failed"], 1)
        self.assertEqual([x["url"] for x in out["requests"]], ["https://a/bad"])

    def test_每个子命令都有独立_help_和例子(self):
        for cmd in ("arm", "wait-settle", "console", "network", "doctor"):
            r = self.run_cli(cmd, "--help")
            self.assertEqual(r.returncode, 0, cmd)
            self.assertIn("例子:", r.stdout, cmd)


if __name__ == "__main__":
    unittest.main()
