"""부모 요청의 카드가 파생 요청을 센다 (REQ-20260919-010-62x6 · REQ-20260921-007-62x6).

주인 물음 2026-09-19 11:31: 「왜 004만 돌아? 002는 뭐해?」 — 그때 진행 중 칸에
부모 하나와 자식 하나가 나란히 서 있었습니다. 카드만 보면 둘 다 도는 것으로
읽히는데, 부모는 처음부터 제 손으로 할 일이 없었고 자식마저 그 사이 클레임을 놓아
실제로는 아무것도 돌고 있지 않았습니다.

계약 다섯.
  K1 파생이 있는 요청의 카드가 그 수를 말한다 (파생 M/N 끝)
  K2 다 끝났으면 끝난 얼굴이다 (.full) — 사람이 손대지 않아도 그 사실이 드러난다
  K3 자식이 없으면 아무 칩도 서지 않는다 — 고칠 수 없는 빈 사실을 세우지 않는다
  K4 새 시각 언어를 들이지 않는다 — TDD 칩과 같은 모양·같은 자리다
  K6 칩이 마우스를 올리기 전에 스스로 말한다 — 낱말은 화면 사전의 「파생」이고,
     「끝」이 분수의 방향을 닫는다 (REQ-20260921-007-62x6, 주인 물음 2026-09-21:
     「자식 1/2는 뭐야?」 — 툴팁이 있어도 사람은 칩만 보고 몰랐다)

실행: python3 tests/ card_kids
"""
import os
import re
import unittest
from webasset import index_path

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(HERE, "..", "web"))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class CardCountsItsChildren(unittest.TestCase):
    def setUp(self):
        self.js = read(os.path.join(WEB, "app", "card.js"))
        self.css = read(os.path.join(WEB, "css", "actions.css"))

    def test_k1_the_card_says_how_many_children(self):
        m = re.search(r"function kidsHTML\(r\)\{([\s\S]{0,2400}?)\n\}", self.js)
        self.assertIsNotNone(m, "파생을 세는 칩이 없습니다")
        self.assertIn("파생 ${k.done}/${k.total} 끝", m.group(1),
                      "끝난 수와 전체 수를 함께 말하지 않습니다")
        self.assertIn("kidsHTML(r)", self.js.split("function kidsHTML")[0]
                      + self.js.split("function kidsHTML")[-1],
                      "칩을 카드가 부르지 않습니다")

    def test_k2_all_done_wears_the_done_face(self):
        m = re.search(r"function kidsHTML\(r\)\{([\s\S]{0,2400}?)\n\}", self.js)
        self.assertIn("k.done === k.total", m.group(1))
        self.assertIn('class="kids${all ? " full" : ""}"', m.group(1),
                      "다 끝났을 때의 얼굴이 없습니다")
        self.assertRegex(self.css, r"\.kids\.full\{[^}]*--c-done")

    def test_k3_no_children_no_chip(self):
        m = re.search(r"function kidsOf\(id\)\{([\s\S]{0,900}?)\n\}", self.js)
        self.assertIsNotNone(m, "파생을 세는 색인이 없습니다")
        self.assertIn("|| null", m.group(1), "파생이 없을 때 빈 값을 주지 않습니다")
        body = re.search(r"function kidsHTML\(r\)\{([\s\S]{0,2400}?)\n\}", self.js).group(1)
        self.assertIn('if (!k) return "";', body, "파생이 없는데 칩을 세웁니다")

    def test_k4_same_shape_as_the_tdd_chip(self):
        """K4. 새 시각 언어를 들이지 않는다 — 글꼴·크기·테두리·모서리가 TDD 칩과 같다."""
        tdd = re.search(r"\.tdd\{([^}]+)\}", self.css).group(1)
        kids = re.search(r"\.kids\{([^}]+)\}", self.css).group(1)
        norm = lambda s: sorted(x.strip() for x in s.split(";") if x.strip())
        self.assertEqual(norm(tdd), norm(kids),
                         "자식 칩이 TDD 칩과 다른 모양입니다")
        # 스킨에서도 한 벌로 움직인다
        calm = read(os.path.join(WEB, "css", "calm.css"))
        self.assertRegex(calm, r'\.card \.kids,\s*\n?\[data-skin="calm"\] \.card \.tdd\{')

    def test_k5_only_requests_are_counted(self):
        """K5. 요청만 센다 — 지식·질문 문서가 parent 를 가져도 일의 수가 아닙니다."""
        m = re.search(r"function kidsOf\(id\)\{([\s\S]{0,900}?)\n\}", self.js)
        self.assertIn('row.type !== "request"', m.group(1))


class TheChipSpeaksBeforeHover(unittest.TestCase):
    """K6. 칩의 글자만으로 뜻이 서야 한다 (REQ-20260921-007-62x6).

    툴팁은 마우스를 올려야 보인다 — 주인이 칩을 보고 물었다는 것이 그 증거다.
    막힌 자리가 둘이었다: 낱말(무엇의 수인가)과 분수(끝난 쪽인가 남은 쪽인가)."""

    def setUp(self):
        self.js = read(os.path.join(WEB, "app", "card.js"))
        self.body = re.search(r"function kidsHTML\(r\)\{([\s\S]{0,2400}?)\n\}",
                              self.js).group(1)

    # K6a. 화면 사전의 낱말을 쓴다 — 이 개념에 두 번째 이름을 만들지 않는다
    def test_k6a_the_chip_uses_the_screen_word(self):
        chip = re.search(r'\+ `([^`]*)</span>`', self.body).group(1)
        self.assertIn("파생", chip)
        self.assertNotIn("자식", chip)

    # K6b. 분수의 방향을 글자가 닫는다
    def test_k6b_the_fraction_says_which_side(self):
        chip = re.search(r'\+ `([^`]*)</span>`', self.body).group(1)
        self.assertIn("끝", chip)
        # 「완료」는 쓰지 않는다 — 이 수는 cancelled 도 세고, 상태 값 done 과 겹친다
        self.assertNotIn("완료", chip)

    # K6c. 툴팁은 한 벌이다 — 끝난 수를 되풀이하지 않는다
    def test_k6c_one_tooltip_not_two(self):
        self.assertNotIn("k.done}개가 끝났습니다", self.body)
        self.assertIn("파생 요청 ${k.total}개에 나뉘어 있습니다", self.body)

    # K6d. 화면 어디에도 이 개념을 「자식」으로 부르는 글자가 없다
    def test_k6d_no_child_word_left_on_screen(self):
        guide = read(os.path.join(WEB, "guide.html"))
        self.assertNotIn("부모-자식", guide)
        self.assertIn("부모-파생", guide)


if __name__ == "__main__":
    unittest.main()
