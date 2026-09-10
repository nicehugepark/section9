"""실측 브라우저를 고르는 두 물음 (REQ-20260910-003).

맥에서는 CDP 실측 시험이 전부 「브라우저 없음」으로 건너뛰었다 — `chrome_path`
가 WSL 의 Windows Chrome 과 PATH 이름만 찾았기 때문이다. 그런데 맥 후보를 그냥
더하면 이번엔 `test_hover_realscale` 3항목이 실패한다: 그 시험의 기대값은
Windows Chrome 에서 잰 화소이고, 같은 Chrome 이어도 운영체제가 다르면 획이 다른
화소에 앉는다(실측 2026-09-10 맥 Chrome: 과녁 27 이 28 · ⏸ +0.5화소 · ▶ -1.095화소).

그래서 물음이 둘이다 — **브라우저를 찾았나**, **그 브라우저로 화소를 재도 되나.**
여기서 재는 것은 그 두 물음이 실제로 갈라져 있는지다.

실행: python3 tests/ chrome_pick
"""
import os
import shutil
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cdpreal  # noqa: E402


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("")
    return path


class BrowserPick(unittest.TestCase):
    """후보 표를 임시 자리로 돌려 놓고 고르는 순서를 잰다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9chromepick-")
        self.keep = (cdpreal.WIN_CANDIDATES, cdpreal.PATH_NAMES,
                     cdpreal.MAC_CANDIDATES, cdpreal.MAC_PLAYWRIGHT_GLOB,
                     os.environ.get("PATH", ""))
        # 이 머신에 실제로 깔린 브라우저가 답을 흐리지 않게 전부 비운다.
        cdpreal.WIN_CANDIDATES = ()
        cdpreal.MAC_CANDIDATES = ()
        cdpreal.MAC_PLAYWRIGHT_GLOB = os.path.join(self.tmp, "none", "*", "x")
        os.environ["PATH"] = os.path.join(self.tmp, "emptybin")
        os.makedirs(os.environ["PATH"], exist_ok=True)
        cdpreal._said.clear()

    def tearDown(self):
        (cdpreal.WIN_CANDIDATES, cdpreal.PATH_NAMES, cdpreal.MAC_CANDIDATES,
         cdpreal.MAC_PLAYWRIGHT_GLOB, os.environ["PATH"]) = self.keep
        cdpreal._said.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mac_app(self, name="Google Chrome"):
        p = touch(os.path.join(self.tmp, "Applications", name + ".app",
                               "Contents", "MacOS", name))
        cdpreal.MAC_CANDIDATES = (p,)
        return p

    def _on_path(self, name="google-chrome"):
        p = touch(os.path.join(os.environ["PATH"], name))
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        return p

    def test_mac_serves_layout_tests_and_says_why_it_skips_pixel_tests(self):
        """맥 브라우저는 배치 시험에는 나오고, 화소 시험에는 사유와 함께 안 나온다."""
        app = self._mac_app()
        self.assertEqual(cdpreal.chrome_path(pixel_contract=False), app,
                         "배치·스크롤만 재는 시험은 맥에서도 실측해야 한다")
        self.assertEqual(cdpreal.skip_reason(pixel_contract=False), "")

        self.assertIsNone(cdpreal.chrome_path(),
                          "화소를 재는 시험에 계약 밖 브라우저를 주면 안 된다")
        why = cdpreal.skip_reason()
        self.assertNotEqual(why, cdpreal.NO_BROWSER,
                            "브라우저는 찾았으니 「없음」은 사실이 아니다")
        self.assertIn("화소 계약", why)

    def test_the_newest_playwright_build_wins(self):
        """받아 둔 Chromium 이 여러 벌이면 build 번호가 가장 큰 것 — 글자 순서가 아니라."""
        base = os.path.join(self.tmp, "ms-playwright")
        for build in ("99", "1100", "1005"):
            touch(os.path.join(base, "chromium-" + build, "chrome-mac",
                               "Google Chrome for Testing.app", "Contents",
                               "MacOS", "Google Chrome for Testing"))
        cdpreal.MAC_PLAYWRIGHT_GLOB = os.path.join(
            base, "chromium-*", "chrome-mac*", "Google Chrome for Testing.app",
            "Contents", "MacOS", "Google Chrome for Testing")
        self.assertIn("chromium-1100",
                      cdpreal.chrome_path(pixel_contract=False))

    def test_other_platforms_keep_their_old_answer(self):
        """PATH 브라우저가 있으면 맥 후보가 함께 있어도 그것이 먼저다 — 계약도 그대로."""
        want = self._on_path()
        self._mac_app()
        self.assertEqual(cdpreal.chrome_path(), want)
        self.assertEqual(cdpreal.chrome_path(pixel_contract=False), want)
        self.assertEqual(cdpreal.skip_reason(), "")

        os.remove(want)
        cdpreal.MAC_CANDIDATES = ()
        self.assertIsNone(cdpreal.chrome_path(pixel_contract=False))
        self.assertEqual(cdpreal.skip_reason(), cdpreal.NO_BROWSER,
                         "아무것도 못 찾은 자리의 사유는 종전 그대로다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
