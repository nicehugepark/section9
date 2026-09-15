"""playwright 없는 맥에서도 캡처가 남는다 (REQ-20260916-018-2n7g).

맥의 Chrome `--headless --screenshot` 은 끝나지 않는다(REQ-20260911-002-2n7g). 그 자리를
Playwright(channel=chrome)로 우회해 두었는데, 이 파이썬에 playwright 가 없는 맥에서는
chrome·chromium·webkit **세 갈래가 모두** 막혀 400px 화면을 눈으로 볼 길이 그 컴퓨터에
없었다 — REQ-20260916-011-2n7g 의 작업자가 그 이유로 검증을 못 하고 blocked 로 올렸다.

없는 것은 브라우저가 아니라 캡처 경로 하나다: 같은 Chrome 을 CDP 로는 띄운다
(tests/cdpreal.py 가 실측에 쓴다). 그래서 `Page.captureScreenshot` 한 자리를 stdlib 만으로
bin/s9.py 에 두고, 맥 + playwright 없음일 때 그 길로 간다.

여기서 고정하는 것은 **고르는 규칙**이다. 실제로 찍히는가는 이 맥에서 직접 쟀다
(REQ 문서의 response 노트: 400x900 5.6초, dpr 2 에서 800x1800).

실행: python3 tests/ shot_cdp
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def load_s9():
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = tempfile.mkdtemp(prefix="s9-shotcdp-")
    try:
        spec = importlib.util.spec_from_loader(
            "s9_shotcdp", importlib.machinery.SourceFileLoader("s9_shotcdp", S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


class Args:
    def __init__(self, **kw):
        self.url = "http://127.0.0.1:1/"
        self.size = "400x900"
        self.wait = 0
        self.out = "/tmp/s9-shotcdp-out.png"
        self.engine = "chrome"
        self.dpr = 1
        self.__dict__.update(kw)


class WhichPathIsTaken(unittest.TestCase):
    """엔진 고르기 — 새 길이 종전 길을 앞지르지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.m = load_s9()

    def run_shot(self, platform, has_pw, **kw):
        """어느 길로 갔는지만 본다. 맥이 아닌 판에서는 종전 Chrome 갈래가 후보를
        못 찾아 sys.exit 로 끝나는데, 그것이 곧 「CDP 로 새지 않았다」는 뜻이다."""
        m, calls = self.m, {}

        def fake_webkit(*a, **k):
            calls["webkit"] = k.get("browser")
            return None

        def fake_cdp(*a, **k):
            calls["cdp"] = k
            return 0

        with mock.patch.object(m, "os_platform", lambda: platform), \
             mock.patch.object(m, "_playwright_available", lambda: has_pw), \
             mock.patch.object(m, "_shot_webkit", fake_webkit), \
             mock.patch.object(m, "_shot_cdp", fake_cdp), \
             mock.patch.object(m, "_shot_tune", lambda u, w: (u, w, None, "")):
            try:
                m.cmd_shot(Args(**kw))
            except SystemExit:
                calls["exited"] = True
        return calls

    def test_3_playwright_on_mac_keeps_the_old_path(self):
        """3. playwright 가 있으면 종전 chromium 갈래 — 새 길이 앞지르지 않는다."""
        calls = self.run_shot("macOS", True)
        self.assertEqual(calls.get("webkit"), "chromium")
        self.assertNotIn("cdp", calls)

    def test_1_no_playwright_on_mac_uses_cdp(self):
        """1. playwright 가 없는 맥은 CDP 로 간다 — 종전에는 여기서 막혔다."""
        calls = self.run_shot("macOS", False)
        self.assertIn("cdp", calls, "맥에서 playwright 가 없는데 CDP 로 안 갔다")
        self.assertNotIn("webkit", calls)

    def test_4_the_scale_rides_along(self):
        """4. --dpr 이 그 길에도 실린다 — 배율 불변 검증이 맥에서도 되게."""
        calls = self.run_shot("macOS", False, dpr=2)
        self.assertEqual(calls["cdp"].get("dpr"), 2.0)

    def test_5_other_platforms_are_unchanged(self):
        """5. 맥이 아니면 고르는 엔진이 종전과 같다 — CDP 로 새지 않는다."""
        for plat in ("WSL", "Windows", "Linux"):
            with self.subTest(plat):
                calls = self.run_shot(plat, False)
                self.assertNotIn("cdp", calls, f"{plat} 에서 맥 전용 길로 갔다")

    def test_explicit_engine_still_wins(self):
        """사람이 --engine 을 짚었으면 그 뜻이 먼저다."""
        calls = self.run_shot("macOS", False, engine="webkit")
        self.assertEqual(calls.get("webkit"), "webkit")
        self.assertNotIn("cdp", calls)


class WhenItCannotWork(unittest.TestCase):
    """못 할 때는 매달리지 않고 사유와 함께 끝낸다."""

    @classmethod
    def setUpClass(cls):
        cls.m = load_s9()

    def test_6_no_browser_is_a_nonzero_with_a_hint(self):
        """6. 브라우저가 하나도 없으면 비-0 으로 끝나고 안내를 준다."""
        m = self.m
        with mock.patch.object(m, "_shot_mac_candidates", lambda: []), \
             mock.patch.object(m, "os_platform", lambda: "macOS"):
            rc = m._shot_cdp("http://127.0.0.1:1/", "400,900", 0,
                             "/tmp/s9-shotcdp-none.png")
        self.assertNotEqual(rc, 0)

    def test_7_a_browser_that_dies_does_not_hang(self):
        """7. 브라우저가 곧바로 끝나면 시한을 기다리지 않고 비-0 으로 끝낸다."""
        m = self.m
        with mock.patch.object(m, "_shot_mac_candidates", lambda: ["/usr/bin/false"]), \
             mock.patch.object(m, "os_platform", lambda: "macOS"):
            rc = m._shot_cdp("http://127.0.0.1:1/", "400,900", 0,
                             "/tmp/s9-shotcdp-dead.png")
        self.assertNotEqual(rc, 0)

    def test_8_the_temp_profile_is_swept(self):
        """8. 띄운 임시 프로필은 끝날 때 거둔다 — 남기면 다음 실행이 만난다."""
        import glob
        m = self.m
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "s9-shot-cdp-*")))
        with mock.patch.object(m, "_shot_mac_candidates", lambda: ["/usr/bin/false"]), \
             mock.patch.object(m, "os_platform", lambda: "macOS"):
            m._shot_cdp("http://127.0.0.1:1/", "400,900", 0,
                        "/tmp/s9-shotcdp-dead2.png")
        after = set(glob.glob(os.path.join(tempfile.gettempdir(), "s9-shot-cdp-*")))
        self.assertEqual(after - before, set(), "임시 프로필이 남았다")


class TheTimeoutIsBounded(unittest.TestCase):
    """시한이 코드에 서 있다 — 매달리지 않는다는 계약은 숫자로만 지켜진다."""

    @classmethod
    def setUpClass(cls):
        cls.m = load_s9()

    def test_the_cdp_wait_has_a_ceiling(self):
        self.assertGreater(self.m.SHOT_CDP_TIMEOUT, 0)
        self.assertLessEqual(self.m.SHOT_CDP_TIMEOUT, 180)


if __name__ == "__main__":
    unittest.main()
