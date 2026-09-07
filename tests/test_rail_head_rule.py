"""세는 줄 / 손잡이 줄 규칙 (REQ-20260907-024) · 그래프 라벨의 안전한 자리 (REQ-20260907-025).

두 규칙 다 CSS·JS 원천에 남는 모양이라 원천을 읽어 지킨다 — 실제 렌더는
`s9 shot` 캡처가 판정했고(요청 문서의 그림), 여기서는 그 결론이 코드에서
되돌려지지 않게 못을 박는다.

REQ-013 이 타입 띠에서 세운 규칙: 성격이 다른 둘(세는 것 · 누르는 것)을 한
wrap 줄에 두지 않는다. 오른끝으로 미는 값(`margin-left:auto` · `space-between`)은
줄이 접히는 순간 뜻을 갈라 놓는다.
"""
import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def read(rel):
    return (WEB / rel).read_text(encoding="utf-8")


class TheRailHeadHasTwoRows(unittest.TestCase):
    """REQ-20260907-024 — 프로젝트 레일 머리."""

    @classmethod
    def setUpClass(cls):
        cls.css = read("css/project.css")
        cls.js = read("app/project.js")

    def head_rule(self):
        m = re.search(r"^\.pjhead\{(.*?)\}", self.css, re.S | re.M)
        self.assertIsNotNone(m, ".pjhead 규칙을 찾지 못했다")
        return m.group(1)

    def test_s1_handle_row_is_full_width_with_a_dividing_line(self):
        # 손잡이 줄은 제 줄을 갖고, 위에 가르는 선을 둔다 (.tbtail 과 같은 문법)
        m = re.search(r"\.pjhead \.pjtail\{(.*?)\}", self.css, re.S)
        self.assertIsNotNone(m, ".pjhead .pjtail 규칙이 없다")
        body = m.group(1)
        self.assertIn("border-top", body)
        self.assertRegex(body, r"width:calc\(100% \+ var\(--pjgut\) \* 2\)")
        self.assertIn('<span class="pjtail">', self.js)

    def test_s2_no_push_to_the_far_end(self):
        # 오른끝으로 미는 값은 접히는 줄에 쓰지 않는다
        head = self.head_rule()
        self.assertNotIn("space-between", head)
        for sel in (r"\.pjhead[^{]*\{[^}]*margin-left:auto",
                    r"\.pjtail[^{]*\{[^}]*margin-left:auto"):
            self.assertIsNone(re.search(sel, self.css, re.S),
                              "머리에 오른끝으로 미는 값이 남았다")

    def test_s3_handle_starts_at_the_same_gutter_as_the_label(self):
        # 안여백은 한 곳(--pjgut)에서만 정한다 — 밀도는 그 변수만 바꾼다
        self.assertIn("--pjgut:14px", self.css)
        self.assertRegex(self.css, r'\[data-density="compact"\] \.pjhead\{--pjgut:10px')
        # 낱개 손잡이에 안여백을 또 주면 두 겹이 된다
        self.assertRegex(
            self.css,
            r'\[data-density="compact"\] \.pjlist \.pjhead \.more\{padding-left:0')

    def test_s4_a_lone_handle_row_draws_no_line(self):
        # 가를 이웃이 없으면 획도 없다 (Docs 좌측 레일 · headLabel:false)
        self.assertRegex(self.css, r"\.pjhead \.pjtail:first-child\{[^}]*border-top:0")

    def test_s5_skins_may_change_the_material_not_the_place(self):
        # `[data-skin=calm] .more` 와 같은 급이면 뒤에 실린 스킨이 이긴다 —
        # 자리를 정하는 규칙은 한 급 위에 선다
        self.assertIn(".pjlist .pjhead .more{", self.css)
        self.assertNotRegex(self.css, r"(?<!\.pjlist )\.pjhead \.more\{")


class TheGraphLabelKeepsItsRoom(unittest.TestCase):
    """REQ-20260907-025 — 그래프 판과 캔버스의 경계."""

    @classmethod
    def setUpClass(cls):
        cls.js = read("app/graph.js")

    def test_s1_labels_are_clamped_inside_the_canvas(self):
        # 라벨 상자는 캔버스 안쪽으로 물린다 — 가장자리에서 글자가 잘리지 않는다
        self.assertIn("LAB_EDGE", self.js)
        self.assertRegex(self.js, r"function labBox\([^)]*\)\{(?:.|\n){0,900}?LAB_EDGE")

    def test_s2_floating_panels_are_treated_as_taken_room(self):
        # 캔버스 위에 떠 있는 판(.ghint · .gfit)은 라벨이 피해야 할 자리다
        self.assertIn("floatBoxes", self.js)
        self.assertIn(".ghint", self.js)
        self.assertIn(".gfit", self.js)

    def test_s3_the_room_is_measured_not_hardcoded(self):
        # 판의 자리는 폭마다 다르다(tablet.css 가 768 에서 좌우로 가른다) —
        # 값을 베껴 적지 말고 실측한다
        self.assertIn("getBoundingClientRect", self.js)


if __name__ == "__main__":
    unittest.main()
