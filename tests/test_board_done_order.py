"""끝난 카드를 무엇으로 세우는가 (REQ-20260827-016-62x6).

사용자 지적: "done 카드 목록에서 우선순위 가중치가 높은 순으로 화면에 보여주는데
마지막 업데이트 시간 기준으로 보여줘."

맞는 말이다. **우선순위는 "다음에 무엇을 할 것인가"에 답하는 축인데, 이미 끝난
일에는 그 질문이 없다.** done 이 286건까지 쌓인 지금 가중치 계단으로 묶여 있으면,
방금 끝난 것을 찾으려고 계단마다 훑어야 한다. 이 컬럼에서 알고 싶은 것은
"무엇이 최근에 끝났나" 하나뿐이다.

실측(카탈로그 286건):

    예전 첫 3   !85(08-26T22:13) · !85(08-27T00:02) · !80(08-26T19:19)
    이제 첫 3   !50(08-27T10:07) · !50(08-27T10:07) · !50(08-27T09:16)

살아 있는 컬럼(open·in-progress·review)은 그대로 우선순위가 1차 키다 — 거기서는
그 질문이 여전히 유효하다. **끝난 것과 살아 있는 것에 같은 자를 대지 않는 것**이
이 변경의 요점이다.

실행: python3 tests/ board_done_order
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class BoardDoneOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        m = re.search(r"for \(const st of STATUSES\)\{(.*?)\n  \}",
                      cls.src, re.S)
        cls.loop = m.group(1) if m else ""

    def test_board_done_order(self):
        """BoardDoneOrder 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("b1_terminal_columns_sort_by_updated"):
            self.assertTrue(self.loop, "보드 컬럼 루프를 찾지 못했다")
            self.assertIn("TERMINAL.has(st)", self.loop,
                          "끝난 컬럼을 따로 가르지 않는다")
            self.assertIn("b.status_since || b.updated", self.loop,
                          "카드가 보여주는 시각(status_since)으로 세우지 않는다")
        with self.subTest("b1b_it_sorts_by_what_the_card_shows"):
            self.assertRegex(
                self.src,
                r'data-since="\$\{esc\(r\.status_since\)\}"',
                "카드 시계가 status_since 가 아니다 — 정렬 기준을 다시 맞춰야 한다")
            self.assertIn("b.status_since", self.loop)
        with self.subTest("b2_it_uses_the_shared_terminal_set"):
            self.assertRegex(
                self.src, r'const TERMINAL = new Set\(\["done",\s*"cancelled"\]\)')
            self.assertNotIn('st === "done"', self.loop,
                             "끝난 상태를 손으로 다시 적었다")
        with self.subTest("b3_live_columns_keep_priority"):
            self.assertRegex(
                self.src,
                r"const workOrder = rows => \[\.\.\.rows\]\.sort\(\(a, b\) =>\s*"
                r"\n\s*\(prioOf\(b\) - prioOf\(a\)\)")
        with self.subTest("b4_the_original_list_is_not_mutated"):
            self.assertIn("[...grp].sort(", self.loop,
                          "복사본이 아니라 원본을 정렬한다")

if __name__ == "__main__":
    unittest.main()
