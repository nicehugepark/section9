"""「대시보드 연결 끊김」이 뜨는 문턱 (REQ-20260918-001-62x6).

사용자: "대시보드 연결이 가끔 끊기는데 원인이 뭐지?"

**끊긴 것은 연결 하나이고, 화면은 그것을 상태로 옮겨 적었다.** 5초 폴
(`termTargetLoop`)은 한 tick 이 응답을 못 받으면 그 자리에서
`termStatus(T, null, "offline")` 을 불러 「대시보드 연결 끊김」을 세웠다.

그렇게 정한 데에는 까닭이 있었다(REQ-20260901-013, terminal.js 머리글):
「폴의 재시도는 다음 tick 이고, 못 받은 한 번은 offline 이라는 설계된 얼굴이
있다」. 전제는 **한 번 못 받아도 다음 tick 이 메운다**는 것이었다.

그 전제가 이 기계에서 깨졌다. 실측(2026-09-18 10:50, DESKTOP-1A2B3C):
`/api/chat/target` 40회 중 **26회 실패(65%)**, 같은 시각 임시 서버(9931)
대조군은 40/40 성공. 뿌리는 WSL 루프백 중계의 연결 리셋이고(REQ-20260909-067),
실패율 65% 에서는 두 tick 연속 실패가 42%·세 tick 연속이 27% 다 — 다음 tick 이
메운다는 전제가 서지 않으니 그 얼굴이 거의 상시로 보인다.

고칠 것은 재시도가 아니라 **얼굴이 뜨는 문턱**이다. 폴에 재시도를 붙이면 왕복과
취소가 늘고, 이 환경에서 리셋을 만드는 것이 바로 그 취소다 — 고치려다 원인을
키운다. 그래서 왕복 수는 그대로 두고, 연속으로 못 받았을 때만 보인다.

계약은 넷이다.

  ① 한 번 못 받은 것으로는 얼굴이 서지 않는다 — 폴은 연속 실패를 센다.
  ② 문턱은 2 이상이다. 1 이면 세지 않는 것과 같다.
  ③ 응답이 오면 센 것은 0 으로 돌아간다 — 하루에 흩어진 실패가 쌓여 뜨면 안 된다.
  ④ 왕복 수는 늘지 않는다 — 폴 한 tick 은 여전히 `ccFetch` 한 번이다.
     (재시도가 붙은 `ccFetchTry` 는 사람이 눌러 기다리는 자리의 것이다.)

실행: python3 tests/ offline_threshold
"""
import re
import unittest

import websrc                      # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path    # 계약은 브라우저가 받는 한 장을 본다

INDEX = index_path()


class TheOfflineFace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _loop(self):
        return websrc.fn(self, self.src, "termTargetLoop")

    def test_the_offline_face(self):
        """TheOfflineFace 의 계약을 한 항목으로 — 검사는 그대로다."""
        loop = self._loop()

        with self.subTest("one_miss_does_not_raise_the_face"):
            # 못 받은 자리에서 곧바로 offline 을 세우면 문턱이 없는 것이다.
            bare = re.search(r'if\s*\(!nt\)\s*\{?\s*termStatus\(\s*T\s*,\s*null\s*,\s*"offline"\s*\)',
                             loop)
            self.assertIsNone(bare,
                              "폴이 한 번 못 받은 것을 그대로 「대시보드 연결 끊김」으로 "
                              "옮겨 적는다 — 문턱이 없다")

        with self.subTest("the_poll_counts_consecutive_misses"):
            self.assertIn("CC_MISS_MAX", loop,
                          "폴이 연속 실패를 세지 않는다")

        with self.subTest("the_threshold_is_at_least_two"):
            m = re.search(r"const\s+CC_MISS_MAX\s*=\s*(\d+)", self.src)
            self.assertIsNotNone(m, "문턱이 한 자리에 상수로 서 있지 않다")
            self.assertGreaterEqual(int(m.group(1)), 2,
                                    "문턱이 1 이면 세지 않는 것과 같다")

        with self.subTest("a_reply_clears_the_count"):
            self.assertRegex(loop, r"T\.miss\s*=\s*0",
                             "응답이 와도 센 것이 0 으로 돌아가지 않는다 — "
                             "흩어진 실패가 쌓여 얼굴이 선다")

        with self.subTest("the_poll_still_makes_one_round_trip"):
            self.assertIn("ccFetch(\"/api/chat/target", loop,
                          "폴이 재시도 붙은 길로 옮겨 갔다 — 왕복과 취소가 늘고, "
                          "이 환경에서 리셋을 만드는 것이 그 취소다")
            self.assertNotIn("ccFetchTry(\"/api/chat/target", loop,
                             "폴에 재시도가 붙었다 — 고치려다 원인을 키운다")


if __name__ == "__main__":
    unittest.main()
