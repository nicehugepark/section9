"""접는다면 **펼 수단을 짝으로 준다** — 그 수단이 호버 전개는 아니다.

이력이 둘이다. 순서대로 읽어야 한다.

① REQ-20260825-071 반려: "보드 화면에서 카드만 봤을 때 리뷰 내용이 줄어들어서
   내용을 파악할 수가 없다. 마우스 호버를 했을 때라도 내용을 확인이 되면
   좋겠는데." → calm 의 3줄 클램프에 호버·포커스 전개(-webkit-line-clamp:unset
   + max-height:60em)를 붙였다.

② REQ-20260829-009: "확인 메시지가 너무 기니까 잘린다. 잘리는게 맞나? 그리고
   이렇게까지 길게 보여주는게 맞을까? 너무 길면 결국 가독성이 떨어져서 본문으로
   들어가서 보게 되는데 말이야." → 사용자가 신고한 화면은 **①이 만든 화면**이다.
   호버가 걸린 카드가 스무 줄로 자라 위아래가 화면 밖으로 나갔다.

그래서 ①의 요구는 살리고 수단만 바꾼다. 살아 있는 요구: *접기만 하고 펼칠
수단을 주지 않으면 안 된다.* 바뀐 수단: 카드 안에서 펼치는 대신, 잘렸을 때만
뜨는 손잡이(.rvmore)가 전문이 있는 곳(문서)으로 데려간다. 호버 전개가 탈락한
이유 셋 —

  · 카드 높이가 포인터 위치에 따라 변해 아래 카드들이 통째로 밀린다.
  · 마우스를 떼면 읽던 글이 사라진다. 오래 읽고 판정하는 글에 맞지 않는다.
  · 펼친 결과가 폭 210~250px 짜리 스무 줄 문단이다 — 읽으라고 준 것이 아니다.

실행: python3 tests/ hover
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class TestReviewHoverExpand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()

    def _clamp_rules(self):
        """`.rvpt`/`.rvtx` 를 몇 줄로 접는 규칙 전부 — 베이스도 스킨도."""
        out = []
        for m in re.finditer(r"(?m)^([^\n{]*\.rv(?:pt|tx)[^{]*)\{([^}]*)\}", self.html):
            if re.search(r"line-clamp:\s*\d", m.group(2)):
                out.append((m.group(1).strip(), m.group(2)))
        return out

    def test_test_review_hover_expand(self):
        """TestReviewHoverExpand 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("something_still_clamps"):
            self.assertTrue(self._clamp_rules(), ".rvpt/.rvtx 를 접는 규칙이 하나도 없다")
        with self.subTest("clamp_is_paired_with_a_way_out"):
            self.assertIn('class="rvmore"', self.html,
                          "접기만 하고 전문으로 가는 손잡이가 없다 — REQ-071 반려가 재발한다")
            self.assertRegex(self.html, r"\.rvpt\.iscut\s*\+\s*\.rvmore\{",
                             "잘린 카드에만 손잡이를 여는 규칙이 없다")
        with self.subTest("the_way_out_is_reachable_without_a_mouse"):
            self.assertRegex(self.html, r'<button type="button" class="rvmore"',
                             "손잡이가 진짜 button 이 아니다 — 키보드로 닿지 않는다")
            self.assertRegex(self.html, r"\.rvmore:focus-visible\{[^}]*outline",
                             "손잡이에 포커스 링이 없다")
        with self.subTest("no_in_card_hover_expansion"):
            for sel, css in re.findall(r"(?m)^([^\n{]*:(?:hover|focus-within)[^\n{]*\.rvpt[^{]*)\{([^}]*)\}",
                                       self.html):
                flat = css.replace(" ", "")
                self.assertNotIn("line-clamp:unset", flat,
                                 "호버/포커스로 클램프를 푸는 규칙이 남아 있다: " + sel.strip())
                self.assertNotRegex(flat, r"max-height:\d{2,}em",
                                    "호버/포커스로 카드를 늘리는 규칙이 남아 있다: " + sel.strip())

if __name__ == "__main__":
    unittest.main(verbosity=2)
