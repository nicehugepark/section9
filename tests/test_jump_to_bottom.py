"""바닥으로 내려가는 손잡이 (REQ-20260827-061-62x6).

사용자: "로컬 터미널 클로드 코드의 점프 투 바텀, new message 기능을 똑같이
구현해줘." (캡처 2장: `Jump to bottom (ctrl+End) ↓` · `1 new message (ctrl+End) ↓`)

대시보드 터미널의 자동 따라가기는 **바닥 근처일 때만** 돈다 — 위로 올려 읽는
중에 화면이 끌려가면 읽던 줄을 잃기 때문이다. 그 규칙 자체는 옳다. 문제는
그것이 **조용히** 돈다는 것이다: 위로 올려 둔 사람에게는 새 출력이 와도 아무
일도 안 일어나는 것처럼 보이고, 멈춘 것과 구분되지 않는다.

계약은 다섯이다.

  ① 바닥에 붙어 있으면 아무것도 안 뜬다. 늘 떠 있는 표시는 곧 안 읽힌다.
  ② 바닥에서 떨어지면 손잡이가 뜬다. 경계값은 자동 따라가기와 **같은 값**이다
     — 다르면 "버튼은 없는데 안 따라가는" 구간이 생겨 규칙이 다시 안 보인다.
  ③ 그 사이 쌓인 줄이 있으면 **수**를 말한다. 없으면 그냥 내려가는 손잡이다
     ("0개"라고 적지 않는다).
  ④ 두 상태는 색상이 아니라 **무게**로 갈린다 — 안 읽은 쪽이 인버스다.
     (터미널이 이미 쓰는 강조. 색면 하이라이트가 아니다.)
  ⑤ 손잡이에 적은 키(Ctrl+End)가 실제로 듣는다. 적어만 두고 안 먹는 키는
     없느니만 못하다.

실행: python3 tests/ jump_to_bottom
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class JumpToBottom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 바닥이면 조용하다 ----------

    def test_jump_to_bottom(self):
        """JumpToBottom 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("hidden_while_stuck_to_the_bottom"):
                fn = self._fn("termJumpSync")
                self.assertRegex(fn, r"btn\.hidden = bottom",
                                 "바닥에서도 손잡이가 떠 있다 — 늘 떠 있는 표시는 안 읽힌다")
                self.assertRegex(fn, r"if \(bottom\) T\.unread = 0",
                                 "바닥까지 내려갔는데 안 읽은 수가 남는다")
                self.assertIn("hidden", self._markup(), "처음부터 떠 있다")

            # ---------- ② 경계값은 자동 따라가기와 같다 ----------
        with self.subTest("it_appears_exactly_when_auto_follow_stops"):
                self.assertRegex(self.src, r"const TERM_FOLLOW_GAP = 140",
                                 "따라가기 경계값이 이름을 갖지 않는다")
                # 손잡이도, 따라가기 판단도 같은 함수를 쓴다
                body = self._fn("termAppendBatch")
                self.assertIn("termAtBottom(out)", body,
                              "따라갈지 말지를 손잡이와 다른 잣대로 판단한다")
                self.assertIn("termAtBottom", self._fn("termJumpSync"))

            # ---------- ③ 쌓인 줄을 센다 ----------
        with self.subTest("it_counts_what_piled_up_while_reading"):
            body = self._fn("termAppendBatch")
            self.assertRegex(body, r"else T\.unread \+= termCountLines\(html\)",
                             "위로 읽는 중에 온 줄을 세지 않는다")
            cnt = re.search(r"const termCountLines = [^;]+;", self.src)
            self.assertIsNotNone(cnt, "줄 세는 함수를 찾지 못했다")
            self.assertIn('<div class="ln', cnt.group(0),
                          "그려진 줄이 아니라 이벤트 수를 센다 — 숨긴 것을 새 메시지라 부른다")
            sync = self._fn("termJumpSync")
            self.assertIn("새 메시지", sync, "몇 줄이 쌓였는지 말하지 않는다")
            self.assertIn("맨 아래로", sync, "안 읽은 게 없을 때의 말이 없다")
            self.assertRegex(sync, r"n \?", "0개를 0개라고 적는다")
        with self.subTest("switching_pane_restarts_the_count"):
                for fn in ("termAgentClose",):
                    self.assertIn("T.unread = 0", self._fn(fn),
                                  "판을 바꿔도 앞 판의 셈이 남는다")
                self.assertIn("function termPane", self.src,
                              "지금 보이는 판을 고르는 자리가 없다")

            # ---------- ④ 색이 아니라 무게 ----------
        with self.subTest("two_states_differ_by_weight_not_hue"):
                css = self._css()
                m = re.search(r"\.ccjump\.unread\{([^}]*)\}", css)
                self.assertIsNotNone(m, "안 읽은 상태의 규칙이 없다")
                self.assertIn("background:var(--cc-text)", m.group(1).replace(" ", ""),
                              "인버스(잉크 반전)가 아니다")
                # 색상 하드코딩 금지 — 터미널 팔레트 토큰만 쓴다
                blk = ";".join(re.findall(r"\.ccjump[^{]*\{([^}]*)\}", css))
                websrc.no_hex(self, blk)
                self.assertNotRegex(blk, r"\bborder-left\b", "좌측 세로 띠 금지")
                for v in re.findall(r"(?:background|color|border-color)\s*:\s*([^;}\n]+)", blk):
                    self.assertRegex(v.strip(), r"^var\(--cc-[a-z]+\)$",
                                     "터미널 팔레트 토큰 밖의 색: %s" % v)

            # ---------- ⑤ 적은 키는 듣는다 ----------
        with self.subTest("the_key_it_advertises_actually_works"):
            self.assertIn("Ctrl+End", self._fn("termJumpSync"), "키를 알려 주지 않는다")
            self.assertRegex(self.src,
                             r'e\.ctrlKey && !e\.shiftKey && !e\.altKey && e\.key === "End"',
                             "Ctrl+End 를 받는 자리가 없다")
            self.assertRegex(self.src, r'e\.key === "End"\)\{\s*\n\s*e\.preventDefault\(\); termJumpGo',
                             "Ctrl+End 가 맨 아래로 보내지 않는다")
        with self.subTest("it_is_reachable_without_a_mouse"):
                mk = self._markup()
                self.assertIn("<button", mk, "버튼이 아니면 Tab 으로 닿지 않는다")
                self.assertIn('aria-live="polite"', mk,
                              "안 읽은 수가 바뀌는 것을 소리로 알리지 않는다")
                self.assertIn("aria-label", self._fn("termJumpSync"), "읽어 줄 이름이 없다")
                self.assertIn(".ccjump:focus-visible", self._css(), "포커스가 보이지 않는다")

            # ---------- 진단 ----------
        with self.subTest("it_can_be_opened_without_hands"):
                self.assertRegex(self._fn("termJumpBind"), r"ccjump\(\?:=",
                                 "손 없이 손잡이를 세울 진단 파라미터가 없다")

            # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _css(self):
        return websrc.css_section(
            self, self.src, r"/\* -+ 바닥으로 내려가는 손잡이")

    def _markup(self):
        m = re.search(r'<button class="ccjump"[^>]*>', self.src)
        self.assertIsNotNone(m, "손잡이 마크업을 찾지 못했다")
        return m.group(0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
