"""자리 칩을 **찾을 수 있다** (REQ-20260829-030-62x6 3차 반려).

사용자: "이건 어떤 화면에서 확인할 수 있는지 설명을 봐도 잘 모르겠다."

두 번의 라운드가 같은 자리에서 미끄러졌다. 1차는 낱말만 세웠고, 2차는 표(◇)를
붙이고 누를 수 있게 만들었다 — 그런데 **재질은 두 번 다 메타 줄의 어휘 그대로**
였다. mono 10px 흐린 글자는 옆에 선 `#태그`·`보통`·`S` 와 같은 급이라, 좁은 열에서
태그 줄로 밀려 내려가면 `#index` 옆에 붙어 태그로 읽힌다(560px 실측 캡처).
표는 "무엇이 있다"까지만 말하고 "눌러 보라"는 말하지 않는다.

그래서 이 라운드가 붙잡는 계약은 셋이다.

① **누를 수 있다는 것이 재질로 보인다.** 이 화면에는 그 말을 하는 문법이 이미
   있다 — doclink 의 점선 밑줄, 그리고 같은 이유로 같은 밑줄을 쓰는 문서 뷰어의
   등급 낱말(`.prio.pfull .pname`). 칩이 그 셋째가 된다. 새 표식을 발명하면
   사람이 배울 것이 하나 더 늘 뿐이고, 태그와 갈리지도 않는다.
② **누를 면적이 글자보다 크다.** 10px 글자의 누를 자리는 13px 높이다. 인라인
   요소의 세로 패딩은 줄 상자를 넓히지 않으므로, 판을 한 픽셀도 밀지 않고
   면적만 키울 수 있다.
③ **창의 첫 줄이 그 질문의 답이다.** 사람이 이 칩을 누르며 품은 질문은 "왜 저기
   앉았나"가 아니라 "그래서 이걸 어느 화면에서 확인하나"다 — 반려문이 그대로 그
   문장이었다. 2차는 사유를 먼저 놓고 답을 둘째 줄에 뒀다. 첫 줄이 답이 아니면
   사람은 답을 못 찾은 채로 창을 닫는다.

색면·테두리 금지(2차 계약)와 "없으면 안 그린다"(1차 계약)는 그대로다 —
`test_workspace_chip.py` 가 지킨다. 이 파일은 그 위의 **찾을 수 있는가**만 본다.

실행: python3 tests/ ws_findable
"""
import re
import unittest

from webasset import part

CARD_JS = "app/card.js"
BOARD_CSS = "css/board.css"
OVERLAY_CSS = "css/overlay.css"
DOCS_CSS = "css/docs.css"


def rule(css, selector):
    """셀렉터 하나의 선언 블록. 주석은 걷어낸다 — 계약은 코드가 말한다."""
    body = re.search(r"(?m)^%s\{(.*?)\}" % re.escape(selector), css, re.S)
    assert body, f"{selector} 규칙이 없다"
    return re.sub(r"/\*.*?\*/", "", body.group(1), flags=re.S)


class ChipIsFindable(unittest.TestCase):
    """조각 하나만 본다 — 이어 붙인 한 장에서 `.wsat` 를 찾으면 앞선 조각의 같은
    이름이 잡힌다(REQ-20260829-038 이 실제로 밟은 함정)."""

    @classmethod
    def setUpClass(cls):
        cls.board = part(BOARD_CSS)
        cls.overlay = part(OVERLAY_CSS)
        cls.docs = part(DOCS_CSS)
        cls.card = part(CARD_JS)
        cls.wsat = rule(cls.board, ".wsat")

    # ---------- ① 누를 수 있다는 것이 보인다 ----------

    def test_chip_is_findable(self):
        """조각 하나만 본다 — 이어 붙인 한 장에서 `.wsat` 를 찾으면 앞선 조각의 같은"""
        with self.subTest("f1_the_chip_wears_the_pressable_grammar"):
            self.assertIn("text-decoration", self.wsat,
                          "칩에 누를 수 있다는 표시가 없다 — 표만으로는 태그와 안 갈린다")
            self.assertIn("dotted", self.wsat, "점선이 아니다")
            # 이 화면에서 점선 밑줄은 새 어휘가 아니다 — 이미 둘이 쓰고 있다
            self.assertIn("dotted", rule(self.docs, "a.doclink")
                          + re.search(r"\.prio\.pfull \.pname\{([^}]*)\}",
                                      self.board).group(1),
                          "빌려 온 문법의 원래 자리가 사라졌다 — 칩만 남으면 새 표식이다")
        with self.subTest("f2_tags_do_not_wear_it"):
            self.assertNotIn("text-decoration", rule(self.board, ".tag"),
                             "태그에도 밑줄이 있다 — 칩이 다시 태그로 읽힌다")
        with self.subTest("f3_still_a_word_not_a_field"):
            for banned in ("background", "border"):
                self.assertNotIn(banned, self.wsat,
                                 "칩에 색면·테두리를 줬다")
        with self.subTest("f4_the_underline_comes_from_the_word"):
                self.assertIn("text-decoration-color", self.wsat, "밑줄 색을 안 정했다")
                m = re.search(r"text-decoration-color:([^;]+)", self.wsat)
                self.assertIn("currentColor", m.group(1),
                              "밑줄 색이 글자에서 파생하지 않는다 — 톤·스킨을 못 따라간다")

            # ---------- ② 누를 면적 ----------
        with self.subTest("f5_the_target_is_bigger_than_the_letters"):
            pad = re.search(r"(?<![\w-])padding:\s*(\d+)px", self.wsat)
            self.assertTrue(pad, "칩에 누를 여유가 없다 — 글자 높이가 곧 과녁이다")
            self.assertGreaterEqual(int(pad.group(1)), 4,
                                    "여유가 너무 얇다 — 과녁이 여전히 글자다")
        with self.subTest("f6_the_target_does_not_move_the_row"):
                self.assertIn("margin:0 -", self.wsat,
                              "가로로 벌어진 여유를 안 되돌렸다 — 메타 줄이 밀린다")

            # ---------- ③ 창의 첫 줄이 답이다 ----------
        with self.subTest("f7_the_answer_comes_first"):
            body = re.search(r"(?m)^function wsOpen\(id\)\{.*?^\}", self.card,
                             re.S).group(0)
            i_means = body.index("WS_MEANS")
            i_why = body.index("s.why")
            self.assertLess(i_means, i_why,
                            "사유가 답보다 먼저 선다 — 사람은 답을 못 찾고 창을 닫는다")
        with self.subTest("f8_only_the_answer_rises_to_ink"):
            body = re.search(r"(?m)^function wsOpen\(id\)\{.*?^\}", self.card,
                             re.S).group(0)
            self.assertRegex(body, r"title:\s*`\$\{WS_MEANS\[",
                             "답이 제목으로 오르지 않는다")
            for sel in (".dlgbox .wsrow", ".dlgbox .wsfix"):
                self.assertNotIn("--faint", rule(self.overlay, sel),
                                 f"{sel} 을 흐림으로 내렸다 — 본문 대비가 무너진다")
        with self.subTest("f9_the_answer_is_one_line_not_a_second_copy"):
            body = re.search(r"(?m)^function wsOpen\(id\)\{.*?^\}", self.card,
                             re.S).group(0)
            self.assertEqual(body.count("WS_MEANS["), 1, "답이 두 자리에 선다")
            self.assertNotIn("나타납니다", body,
                             "창이 답 문장을 손으로 다시 적었다 — WS_MEANS 와 두 벌이다")

if __name__ == "__main__":
    unittest.main()
