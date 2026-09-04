"""줄바꿈은 Shift+Enter 와 Ctrl+Enter 둘 다 (REQ-20260827-038-62x6).

사용자 지적: "터미널에서 줄바꿈 방식이 shift+enter만 지원되는데 원래 클로드 코드는
ctrl+enter이다. 그런데 여기는 둘 다 지원하게 해줘."

주의할 점 하나가 있다. **textarea 는 Shift+Enter 에는 스스로 줄바꿈을 넣지만
Ctrl+Enter 에는 아무것도 넣지 않는다.** 그래서 "전송하지 않는다"로만 막으면
Ctrl+Enter 는 **아무 일도 안 일어나는 키**가 된다 — 사용자 눈에는 여전히 안 되는
것이다. 줄바꿈을 손으로 넣어야 한다.

이 테스트가 지키는 계약 넷:
  ① Enter 는 전송이다 (회귀 방지 — 이게 깨지면 대화 자체가 안 된다).
  ② Shift 나 Ctrl 이 눌린 Enter 는 전송이 아니다.
  ③ Ctrl+Enter 는 **실제로 줄바꿈을 넣는다** — 커서 자리에.
  ④ 안내 문구가 두 키를 다 말한다. 되는데 안 알려주면 없는 기능이다.

실행: python3 tests/ newline_keys
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class NewlineKeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        m = re.search(r"function termKeydown\(T, e\)\{(.*?)\n\}\n", cls.src,
                      re.S)
        assert m, "termKeydown() 을 못 찾았다"
        cls.body = m.group(1)

    # ① Enter 전송은 그대로다
    def test_newline_keys(self):
        """NewlineKeys 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("enter_still_sends"):
                self.assertIn("sendChat()", self.body)

            # ② Ctrl 이 눌린 Enter 는 전송으로 가지 않는다
        with self.subTest("ctrl_enter_is_not_send"):
                m = re.search(r'e\.key === "Enter" && ([^)]*)\)\{[^\n]*sendChat',
                              self.body)
                self.assertIsNotNone(m, self.body[-800:])
                guard = m.group(1)
                self.assertIn("shiftKey", guard, guard)
                self.assertIn("ctrlKey", guard,
                              f"Ctrl+Enter 가 여전히 전송으로 간다: {guard}")

            # ③ Ctrl+Enter 가 실제로 줄바꿈을 넣는다 — textarea 는 스스로 넣지 않는다
        with self.subTest("ctrl_enter_inserts_newline"):
                m = re.search(r"ctrlKey[^\n]*Enter|Enter[^\n]*ctrlKey", self.body)
                self.assertIsNotNone(m, "Ctrl+Enter 분기가 없다")
                seg = self.body[m.start():m.start() + 700]
                self.assertIn("\\n", seg, f"줄바꿈을 넣는 자리가 없다:\n{seg[:400]}")
                self.assertIn("selectionStart", seg,
                              f"커서 자리에 넣지 않는다:\n{seg[:400]}")

            # ④ 안내 문구가 두 키를 다 말한다
        with self.subTest("placeholder_mentions_both"):
            m = re.search(r"placeholder = \"메시지[^\"]*\"", self.src)
            self.assertIsNotNone(m, "입력줄 안내 문구를 못 찾았다")
            hint = m.group(0)
            self.assertIn("Shift+Enter", hint, hint)
            self.assertIn("Ctrl+Enter", hint, hint)

if __name__ == "__main__":
    unittest.main()
