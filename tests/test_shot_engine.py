"""`s9 shot --engine webkit` 의 계약 (REQ-20260906-098) — 브라우저를 띄우지 않는다.

검사하는 것은 셋이다: ① Playwright WebKit 명령줄이 어떻게 조립되는가
② 엔진(run-npx.cmd)이 없을 때 비-0 종료와 설치 안내 ③ 기본 엔진은 auto(러너가 있으면 chromium, 없으면 chrome)라
종전 동작이 그대로인가. 실제 캡처는 REQ 문서의 실측 노트가 맡는다.

실행: python3 tests/ shot_engine
"""
import argparse
import importlib.machinery
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-shotengine-")
os.environ["S9_ROOT"] = TMP


class ShotEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_loader(
            "s9shotengine", importlib.machinery.SourceFileLoader("s9shotengine", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def _run_webkit(self, platform, runner):
        """webkit 경로를 부르고 (종료 코드, stderr) 를 돌려준다. cmd.exe 는 mock.

        판을 만드는 일(os.makedirs)도 함께 막아 **부르지 않았음**을 재는 이유는
        REQ-20260907-050 이다: 러너가 없어 안내만 내고 끝나는 갈래가 그 전에
        /mnt/c/Temp 를 만들고 있었고, 그 자리가 없는 리눅스(원격 시험 머신)에서
        PermissionError 로 죽었다. 이 시험은 윈도우 판이 있는 기계를 요구하지
        않는다 — 요구하면 리눅스에서 설 수 없다.
        """
        m = self.m
        err = io.StringIO()
        with mock.patch.object(m, "os_platform", return_value=platform), \
                mock.patch.object(m, "SHOT_WEBKIT_RUNNER_WSL", runner), \
                mock.patch("subprocess.run") as run, \
                mock.patch("os.makedirs") as mk, \
                redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                m._shot_webkit("http://127.0.0.1:1/#board", "768x1024", 4000,
                               os.path.join(TMP, "never.png"))
        run.assert_not_called()
        mk.assert_not_called()
        return cm.exception.code, err.getvalue()

    def test_shot_engine(self):
        m = self.m
        with self.subTest("s1_command_has_viewport_and_wait"):
            cmd = m._shot_webkit_cmd("http://127.0.0.1:9909/#board", "768x1024",
                                     4000, r"C:\Temp\s9-shot-wk-1.png")
            self.assertEqual(cmd[:2], ["cmd.exe", "/c"])
            line = cmd[2]
            for tok in ("run-npx.cmd", "screenshot", "--browser=webkit",
                        "--viewport-size=768,1024", "--wait-for-timeout=4000",
                        "http://127.0.0.1:9909/#board", r"C:\Temp\s9-shot-wk-1.png"):
                self.assertIn(tok, line)
            # 순서: 옵션 → url → 출력 파일 (playwright screenshot 의 위치 인자 순서)
            self.assertLess(line.index("--viewport-size"), line.index("http://"))
            self.assertLess(line.index("http://"), line.index(r"C:\Temp\s9-shot-wk-1.png"))
        with self.subTest("s2_comma_size_is_accepted"):
            cmd = m._shot_webkit_cmd("http://127.0.0.1:9909/", "1440,900", 3000,
                                     r"C:\Temp\x.png")
            self.assertIn("--viewport-size=1440,900", cmd[2])
        with self.subTest("s2b_url_with_cmd_special_char_is_rejected"):
            with self.assertRaises(ValueError):
                m._shot_webkit_cmd("http://h/?a=1&b=2#x", "800x600", 1, r"C:\x.png")
            with self.assertRaises(ValueError):
                m._shot_webkit_cmd("http://h/", "800", 1, r"C:\x.png")
        with self.subTest("s3_missing_runner_exits_with_install_guide"):
            code, err = self._run_webkit("WSL", os.path.join(TMP, "no", "run-npx.cmd"))
            self.assertNotEqual(code, 0)
            self.assertIn("install webkit", err)
            self.assertIn("run-npx.cmd", err)
            self.assertIn("install webkit", m._shot_webkit_install_guide())
        with self.subTest("s4_plain_linux_has_no_webkit_path"):
            code, err = self._run_webkit("Linux", "/mnt/c/Temp/s9-webkit/run-npx.cmd")
            self.assertNotEqual(code, 0)
            self.assertIn("WebKit 경로가 없다", err)
        with self.subTest("s5_default_engine_is_auto"):
            # 파서는 main() 안에서 만들어진다 — 실행 파일을 그대로 부른다(2회, 0.4초).
            h = subprocess.run([S9, "shot", "--help"], capture_output=True, text=True)
            self.assertIn("--engine {auto,chrome,chromium,webkit}", h.stdout)
            bad = subprocess.run([S9, "shot", "http://127.0.0.1:1/", "--engine", "firefox"],
                                 capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            self.assertIn("invalid choice", bad.stderr)
            with open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8") as f:
                src = f.read()
            self.assertIn('sh.add_argument("--engine", choices=("auto", "chrome", "chromium", "webkit"),', src)
            self.assertIn('default="auto"', src)

if __name__ == "__main__":
    unittest.main()


class ShotDirectNode(unittest.TestCase):
    """runner 옆에 node.exe 와 playwright/cli.js 가 있으면 cmd.exe 없이 node 를 직접 부른다
    (REQ-20260907-016) — 그러면 url 의 `&`·`?` 가 껍데기에 먹히지 않는다."""

    def test_direct_node_accepts_special_url(self):
        import importlib.machinery, importlib.util, tempfile, shutil
        loader = importlib.machinery.SourceFileLoader("s9shotdirect", S9)
        spec = importlib.util.spec_from_loader("s9shotdirect", loader)
        m = importlib.util.module_from_spec(spec); loader.exec_module(m)
        d = tempfile.mkdtemp(prefix="s9-shotdirect-")
        try:
            os.makedirs(os.path.join(d, "node-v22.0.0-win-x64"))
            open(os.path.join(d, "node-v22.0.0-win-x64", "node.exe"), "w").close()
            os.makedirs(os.path.join(d, "node_modules", "playwright"))
            open(os.path.join(d, "node_modules", "playwright", "cli.js"), "w").close()
            runner = os.path.join(d, "run-npx.cmd")
            cmd = m._shot_webkit_cmd("http://127.0.0.1:9909/?nosse&noscroll#terminal",
                                     "768x1024", 4000, r"C:\x.png", runner=runner, browser="chromium")
            self.assertTrue(cmd[0].endswith("node.exe"), cmd)
            self.assertTrue(cmd[1].endswith("cli.js"), cmd)
            self.assertIn("--browser=chromium", cmd)
            self.assertIn("--viewport-size=768,1024", cmd)
            self.assertIn("http://127.0.0.1:9909/?nosse&noscroll#terminal", cmd)
            self.assertNotIn("cmd.exe", cmd)
            # node 가 없으면 종전 cmd.exe 경로 그대로
            os.remove(os.path.join(d, "node-v22.0.0-win-x64", "node.exe"))
            cmd2 = m._shot_webkit_cmd("http://127.0.0.1:9909/#board", "768x1024", 4000,
                                      r"C:\x.png", runner=runner)
            self.assertEqual(cmd2[:2], ["cmd.exe", "/c"])
            self.assertEqual(m._shot_win_path("/mnt/c/Temp/x/cli.js"), r"C:\Temp\x\cli.js")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ShotNavRetry(unittest.TestCase):
    """탐색 단계의 소켓 오류만 다시 시도한다 (REQ-20260907-016)."""

    def test_retryable_predicate(self):
        import importlib.machinery, importlib.util
        loader = importlib.machinery.SourceFileLoader("s9shotretry", S9)
        spec = importlib.util.spec_from_loader("s9shotretry", loader)
        m = importlib.util.module_from_spec(spec); loader.exec_module(m)
        self.assertTrue(m._shot_nav_retryable(b"Error: net::ERR_SOCKET_NOT_CONNECTED at http://h/"))
        self.assertTrue(m._shot_nav_retryable("Error: net::ERR_CONNECTION_RESET"))
        self.assertFalse(m._shot_nav_retryable(b"Error: page.goto: 404"))
        self.assertFalse(m._shot_nav_retryable(b""))
        self.assertGreaterEqual(m.SHOT_NAV_RETRIES, 2)
