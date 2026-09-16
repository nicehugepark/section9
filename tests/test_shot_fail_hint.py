"""캡처가 지면 **무엇이 없는지** 한 줄로 말한다 (REQ-20260915-097-62x6).

실제 사고 2026-09-15 23:08: `s9 shot` 이 어느 엔진으로도 안 찍히고 여덟 줄짜리
Playwright 설치 절차만 냈다. 22:45 까지 같은 러너로 잘 찍던 자리다 — 러너는
있었고 실행이 진 것인데, 화면은 「설치가 안 됐다」고 말하고 있었다. 그 글을 읽은
사람은 멀쩡한 설치를 다시 깐다.

가르는 선: **러너가 아예 없을 때만** 설치 절차를 낸다. 러너가 있는데 실행이
지면 그 자리는 「왜 졌나」를 한 줄로 말할 자리다.

실행: python3 tests/ shot_fail_hint
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_hint", importlib.machinery.SourceFileLoader("s9_hint", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ItSaysWhatIsMissing(unittest.TestCase):

    def setUp(self):
        self.m = _load()

    def hint(self, tail):
        return self.m._shot_fail_hint(tail)

    # 브라우저 알맹이만 없을 때 — 러너를 다시 깔라고 하지 않는다
    def test_a_missing_browser_says_one_command(self):
        h = self.hint("browserType.launch: Executable doesn't exist at "
                      "C:\\Users\\x\\AppData\\Local\\ms-playwright\\webkit-2140")
        self.assertIn("install webkit", h)
        self.assertIn("러너는 이미 있다", h)

    # 서버가 안 뜬 것 — 엔진 문제가 아니다
    def test_a_dead_server_is_not_an_engine_problem(self):
        for t in ("net::ERR_CONNECTION_REFUSED", "connect ECONNREFUSED 127.0.0.1:9909",
                  "Error: net::ERR_SOCKET_NOT_CONNECTED"):
            with self.subTest(t=t):
                h = self.hint(t)
                self.assertIn("서버가 떠 있나", h)
                self.assertIn("엔진 문제가 아니다", h)

    # WSL 경로 — 오늘 리드가 실제로 부딪힌 자리
    def test_a_wsl_path_says_to_serve_it(self):
        h = self.hint("net::ERR_FILE_NOT_FOUND at file:///tmp/x/dlg.html")
        self.assertIn("WSL 경로", h)
        self.assertIn("http://", h)

    def test_a_timeout_says_to_wait_longer(self):
        h = self.hint("TimeoutError: Timeout 30000ms exceeded.")
        self.assertIn("--wait", h)

    def test_a_locked_place_says_to_retry(self):
        h = self.hint("EBUSY: resource busy or locked")
        self.assertIn("다시 찍어라", h)

    # 못 읽으면 지어내지 않는다
    def test_an_unreadable_failure_is_admitted(self):
        h = self.hint("무슨 말인지 모를 글")
        self.assertIn("못 읽었다", h)
        self.assertIn("러너는 있고", h)

    # 사고의 본체 — 진단은 **한 줄**이고 설치 절차를 쏟지 않는다
    def test_the_hint_is_one_line_and_not_an_install_guide(self):
        guide = self.m._shot_webkit_install_guide()
        for tail in ("Executable doesn't exist", "Could not connect to server",
                     "TimeoutError: Timeout 30000ms exceeded.", "무슨 말인지 모를 글"):
            with self.subTest(tail=tail):
                h = self.hint(tail)
                self.assertEqual(1, len(h.strip().splitlines()),
                                 "진단이 한 줄이 아니다: %r" % h)
                # 설치 절차의 몸통(명령 줄)이 진단에 섞이지 않는다
                for cue in ("mkdir -p", "curl -sL", "npm.cmd", "run-npx.cmd 를 만듭니다"):
                    self.assertNotIn(cue, h,
                                     "실행이 진 자리에서 설치 절차를 낸다 — "
                                     "사람이 멀쩡한 설치를 다시 깐다")
        # 절차 자체는 그대로 있다 — 러너가 없을 때 쓸 자리다
        self.assertIn("mkdir -p", guide)

    # 브라우저 알맹이만 없을 때의 한 줄은 **그 한 명령**을 짚는다 (절차 전문이 아니라)
    def test_the_missing_browser_hint_names_just_the_one_command(self):
        h = self.hint("Executable doesn't exist at .../ms-playwright/webkit-2140")
        self.assertIn("install webkit", h)
        self.assertNotIn("curl", h, "설치 절차를 끌어왔다")
        self.assertLess(len(h), 200, "한 줄이라기엔 길다: %d자" % len(h))


if __name__ == "__main__":
    unittest.main()
