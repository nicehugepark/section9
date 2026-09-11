"""맥의 s9 shot 은 Playwright 로 찍는다 (REQ-20260911-002-2n7g).

맥미니 실측 2026-09-11 10:31: /Applications 의 Google Chrome 을 찾게 고친 뒤에도
`--headless --screenshot` 이 data: URL 조차 60초 안에 끝나지 않았다(옛·새 headless,
GPU 플래그 유무 모두) — 사람 화면에는 추적 정보 열 줄이 찍혔다. 같은 Chrome 을
Playwright(channel=chrome)로 띄우면 곧바로 찍힌다. 그래서 맥에서는 engine
chrome/auto 가 Playwright 갈래로 가고, webkit 도 같은 갈래가 받는다.

실행: python3 tests/ shot_mac_playwright
"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
SRC = open(S9 + ".py", encoding="utf-8").read()


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_shotmac", importlib.machinery.SourceFileLoader("s9_shotmac", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ShotMacPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_p1_mac_webkit_branch_exists(self):
        """핵심 — _shot_webkit 이 맥을 npx 러너가 아니라 파이썬 playwright 로 보낸다."""
        i = SRC.index("def _shot_webkit(")
        body = SRC[i:i + 3000]
        self.assertIn('plat == "macOS"', body, "맥은 여전히 「WebKit 경로가 없다」로 끝난다")
        self.assertIn("_shot_mac_playwright(", body)

    def test_p2_mac_chrome_engine_goes_to_playwright(self):
        """정상 — 맥에서 engine chrome(auto 포함)은 playwright 가 있으면 Playwright(channel=chrome) 갈래다."""
        i = SRC.index("def cmd_shot(")
        body = SRC[i:i + 2500]
        self.assertIn('engine == "chrome" and os_platform() == "macOS" and _playwright_available()', body)

    def test_p3_chrome_timeout_is_one_line_not_a_traceback(self):
        """경계 — Chrome --screenshot 이 60초를 넘기면 사실 한 줄로 끝난다."""
        i = SRC.index("f\"--virtual-time-budget={args.wait}\", url],")
        body = SRC[i:i + 900]
        self.assertIn("except subprocess.TimeoutExpired:", body, "시간 초과가 추적 정보로 새어 나간다")

    def test_p4_missing_playwright_says_how_to_install(self):
        """경계 — playwright 가 없으면 설치 명령과 함께 비-0 으로 끝난다."""
        m = self.m
        with mock.patch.object(m, "_playwright_available", lambda: False):
            with self.assertRaises(SystemExit) as cm:
                m._shot_mac_playwright("http://127.0.0.1:1/", "800,600", 100,
                                       os.path.join(tempfile.mkdtemp(), "x.png"))
        self.assertEqual(cm.exception.code, 3)

    @unittest.skipUnless(sys.platform == "darwin", "맥에서만 실물을 찍는다")
    def test_p5_live_capture_on_mac(self):
        """실측(맥) — data: URL 을 Playwright 로 찍어 PNG 가 생긴다."""
        m = self.m
        if not m._playwright_available():
            self.skipTest("이 파이썬에 playwright 가 없다")
        out = os.path.join(tempfile.mkdtemp(prefix="s9shotmac-"), "hi.png")
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # 백지 판정(균일한 가로줄 75%)에 걸리지 않게 줄마다 다른 그림을 채운다
            rows = "".join(f"<div style='height:12px;background:hsl({i * 7 % 360},70%,50%);"
                           f"width:{30 + i % 60}%'>{i}</div>" for i in range(60))
            m._shot_mac_playwright("data:text/html," + rows, "800,600", 200, out)
        self.assertTrue(os.path.exists(out), buf.getvalue())
        self.assertEqual(buf.getvalue().strip().splitlines()[-1], out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
