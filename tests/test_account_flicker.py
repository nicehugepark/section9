"""계정 목록 깜빡임 (REQ-20260901-013).

사용자: "계정 전환을 하는 화면 자체도 이상하다. 계정이 없다가 나타나거나 있는데
사라지거나 한다."

**목록이 흔들린 것이 아니라 연결이 끊긴 것이다.** 계정 창은 열 때 한 번만 목록을
받는데(`claudeAccountSwitch` → `/api/accounts`), 그 한 발이 `ccFetch` 라 재시도가
없었다. 요청이 한 번 끊기면 `d = null` 이 되고 `acctShape(null)` 이 **줄을 통째로
지운 창**을 그린다 — 다음에 열면 멀쩡히 다시 뜬다.

실측(2026-09-01, 실서버 9909): `/api/accounts` 60회 순차 호출 중 **4회가
ConnectionResetError(6.7%)** 였고, 성공한 56회는 4줄로 모양이 완전히 같았다.
흔들린 것은 목록이 아니라 연결이다.

이 벼랑은 이 저장소가 **이미 재서 처방해 둔 것**이다(DOC-20260827-004 ·
REQ-20260829-019): 같은 순간에 도착한 연결이 잘리고, 듣는 처방은 상한(큐)이
아니라 **클라이언트 재시도(120·320ms + 지터)** 뿐이다. 그림(`attImg`)과 부트
보급(`loadSupply`)은 그 처방을 받고 있었는데 **고르는 창들만 밖에 있었다.**

계약은 일곱이다.

  ① 고르는 창의 목록은 재시도가 붙은 한 길(`ccFetchTry`)로만 받는다.
  ② 한 번이라도 답이 오면 그 답이다 — 성공한 뒤에 더 걸지 않는다.
  ③ 물러서는 폭에 **지터**를 섞는다(다 같이 다시 출발하면 같은 벼랑을 또 만난다).
  ④ 사람이 기다리는 시간에는 한도가 있다 — 시도 3회 · 시도당 5초 이내.
  ⑤ 끝내 못 받은 창은 막다른 길이 아니다: `다시 받기` 가 서고, 서버가 답하지
     않는 판에서 눌러도 안 되는 `＋ 계정 추가` 는 서지 않는다.
  ⑥ **열어 둔 창을 배경이 다시 그리지 않는다** — 이 건의 이름이 「깜빡임」인
     이상, 창을 다시 그리는 손이 어느 폴에도 없다는 것까지가 계약이다.
  ⑦ 손 없이 재현된다 — `?apifail=accounts[:once]`. 끊긴 연결은 같은 순간에 열
     개가 도착해야 나므로 캡처로 재현할 수 없다. 새 스위치를 짓지 않고
     boot.js 가 이미 쓰는 그 어휘를 그대로 쓴다.

실행: python3 tests/ account_flicker
"""
import os
import re
import unittest

import websrc                      # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path    # 계약은 브라우저가 받는 한 장을 본다

INDEX = index_path()


class TheAccountList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    # ---------- ① 받는 길은 하나, 그리고 그 길에는 재시도가 있다 ----------

    def test_the_account_list(self):
        """TheAccountList 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_window_asks_through_the_retrying_path"):
            fn = self._fn("claudeAccountSwitch")
            self.assertIn("ccFetchTry(\"/api/accounts\"", fn,
                          "계정 창이 재시도 없는 맨 ccFetch 로 목록을 받는다 — "
                          "연결이 한 번 끊기면 계정이 통째로 사라진다")
            self.assertNotIn("ccFetch(\"/api/accounts\"", fn,
                             "재시도 없는 옛 길이 남아 있다")
        with self.subTest("the_retry_helper_exists_and_loops"):
                fn = self._fn("ccFetchTry")
                self.assertIn("for (", fn, "ccFetchTry 가 다시 걸지 않는다")
                self.assertIn("await ccFetch(", fn,
                              "재시도가 제 fetch 를 따로 짓는다 — 시간 제한이 두 벌이 된다")

            # ---------- ② 성공하면 거기서 끝난다 ----------
        with self.subTest("a_good_answer_ends_it"):
                fn = self._fn("ccFetchTry")
                self.assertRegex(fn, r"if \(d != null\) return d;",
                                 "답을 받고도 계속 거는 길이 열려 있다")

            # ---------- ③ 물러설 때는 지터를 섞는다 ----------
        with self.subTest("the_backoff_has_jitter"):
                fn = self._fn("ccFetchTry")
                self.assertIn("Math.random()", fn,
                              "지터가 없다 — 실패한 것들이 한꺼번에 다시 출발하면 "
                              "같은 벼랑을 또 만난다 (DOC-20260827-004)")
                m = re.search(r"const CC_TRY_BACKOFF = \[([^\]]*)\]", self.src)
                self.assertIsNotNone(m, "CC_TRY_BACKOFF 를 찾지 못했다")
                waits = [int(x) for x in re.findall(r"\d+", m.group(1))]
                self.assertTrue(waits, "물러서는 폭이 비어 있다")
                self.assertEqual(waits, sorted(waits),
                                 "물러서는 폭이 넓어지지 않는다 — 백오프가 아니다")

            # ---------- ④ 사람이 기다리는 시간에는 한도가 있다 ----------
        with self.subTest("the_wait_is_bounded"):
                m = re.search(r"const CC_TRY_BACKOFF = \[([^\]]*)\]", self.src)
                waits = [int(x) for x in re.findall(r"\d+", m.group(1))]
                self.assertLessEqual(len(waits) + 1, 3,
                                     "시도가 셋을 넘는다 — 눌러 놓고 기다리는 창이다")
                fn = self._fn("claudeAccountSwitch")
                ms = re.search(r'ccFetchTry\("/api/accounts",\s*(\d+)', fn)
                self.assertIsNotNone(ms, "시도당 시간 제한을 안 준다")
                self.assertLessEqual(int(ms.group(1)), 5000,
                                     "한 시도가 5초를 넘는다 — 세 번이면 사람이 창을 "
                                     "포기한다")

            # ---------- ⑤ 못 받은 창도 막다른 길이 아니다 ----------
        with self.subTest("the_lost_window_offers_a_way_out"):
            self.assertIn('data-act="again"', self.src,
                          "끝내 못 받은 창에 `다시 받기` 가 없다 — 닫는 것 말고 "
                          "할 수 있는 일이 없는 창이다")
            fn = self._fn("acctFoot")
            self.assertIn("ACCOUNT_AGAIN", fn,
                          "acctFoot 이 그 손잡이를 세우지 않는다")
            sw = self._fn("claudeAccountSwitch")
            self.assertIn('"again"', sw,
                          "`다시 받기` 를 누른 손을 아무도 받지 않는다")
        with self.subTest("the_lost_window_does_not_offer_adding"):
                fn = self._fn("acctFoot")
                self.assertRegex(fn, r"lost",
                                 "acctFoot 이 못 받은 처지를 구분하지 않는다")

            # ---------- ⑥ 열어 둔 창을 배경이 다시 그리지 않는다 ----------
        with self.subTest("no_poll_redraws_the_open_window"):
            for name in ("claudeAccountSwitch", "acctShape", "acctItems"):
                for m in re.finditer(r"setInterval\(", self.src):
                    # setInterval 인자 안(같은 줄~다음 몇 줄)에 창을 여는 손이 있나
                    seg = self.src[m.start():m.start() + 400]
                    self.assertNotIn(name + "(", seg,
                                     f"{name}() 가 주기 폴 안에서 불린다 — 열어 둔 "
                                     f"창이 그때마다 다시 그려진다")
        with self.subTest("the_window_is_painted_in_one_place"):
                self.assertEqual(self.src.count("dlg.innerHTML ="), 2,
                                 "창을 그리는 자리가 s9dlg·s9choose 둘이 아니다 — "
                                 "셋째 손이 생기면 열린 창이 그 손에 덮인다")

            # ---------- ⑦ 손 없이 재현된다 ----------
        with self.subTest("the_failure_can_be_staged_without_hands"):
            fn = self._fn("ccFetchTry")
            self.assertIn("ccTryFail(", fn,
                          "일부러 못 받게 하는 길이 없다 — 끊긴 연결은 같은 순간에 "
                          "열 개가 도착해야 나므로 손으로는 재현할 수 없다")
            helper = self._fn("ccTryFail")
            self.assertIn("API_FAIL", helper,
                          "제 스위치를 새로 짓는다 — boot.js 의 ?apifail 어휘를 "
                          "그대로 쓴다(배울 것을 늘리지 않는다)")
            sw = self._fn("claudeAccountSwitch")
            self.assertIn('"accounts"', sw, "?apifail=accounts 가 닿을 이름이 없다")

class TheSiblingWindows(unittest.TestCase):
    """같은 결함이 옆자리에도 있었다 — 한 곳만 고치면 다음 사람이 거기서 넘어진다."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def test_the_session_window_retries_too(self):
        fn = self._fn("termSessionPick")
        self.assertIn("ccFetchTry(\"/api/sessions\"", fn,
                      "세션 고르기 창도 한 발이다 — 끊기면 세션이 통째로 사라진다")

    def test_attaching_to_the_picked_session_retries_too(self):
        """고른 세션에 붙는 길이 끊기면 **누른 것이 아무 일도 안 한다** —
        이 저장소가 가장 나쁘다고 여러 번 적어 둔 그것이다."""
        fn = self._fn("termSessionPick")
        self.assertIn("ccFetchTry(\"/api/chat/target?sid=\"", fn)


if __name__ == "__main__":
    unittest.main()
