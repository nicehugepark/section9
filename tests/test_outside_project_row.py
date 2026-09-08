"""멤버가 아닌 채 보이는 문서에 그 까닭 한 줄 (REQ-20260908-035-62x6).

가시성이 넓어져 자기가 만든 문서는 프로젝트 멤버가 아니어도 보인다
(REQ-20260908-026). 쓰기와 상태 전이는 그대로 막히므로, 화면이 잠자코 있으면
사람은 눌러 본 뒤에야 거절을 만난다. 서버가 `/api/doc` 에 실어 보내는
`outside_project` 를 문서 판이 읽어 한 줄로 말한다.

실행: python3 tests/ outside_project_row
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(HERE_F := __file__))
ROOT = os.path.dirname(HERE)
JS = open(os.path.join(ROOT, "web", "app", "docs.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "docs.css"), encoding="utf-8").read()
FN = JS[JS.index("function outsideProjectHTML"):]
FN = FN[:FN.index("\n}\n") + 3]


class OutsideProjectRow(unittest.TestCase):
    def test_row_says_where_and_why(self):
        """값이 있으면 한 줄이 서고, 그 줄에서 쓰기가 막힌 까닭까지 읽힌다."""
        # 판이 그 함수를 실제로 부르고, 부른 결과가 문서 머리 바로 뒤에 선다
        self.assertIn("const outside = outsideProjectHTML(d);", JS)
        self.assertIn("</div>${outside}${lineage}", JS)
        for word in ("프로젝트에 속합니다", "만든 사람이라 보이지만",
                     "멤버가 아니어서", "상태를 바꿀 수는 없습니다"):
            self.assertIn(word, FN, word)
        self.assertIn("${esc(slug)}", FN)          # 이름은 서버가 준 slug 그대로

    def test_no_value_no_row(self):
        """값이 없거나 빈 문자열이면 아무것도 서지 않는다."""
        self.assertRegex(FN, r'String\(\(d && d\.outside_project\) \|\| ""\)\.trim\(\)')
        self.assertRegex(FN, r'if \(!slug\) return "";')

    def test_reuses_the_one_line_part(self):
        """새 부품을 만들지 않는다 — 화면이 이미 쓰는 .rvpt 한 줄 문법."""
        self.assertIn('class="rvpt outside"', FN)
        self.assertIn('class="rvcap"', FN)
        self.assertNotRegex(FN, r"background|border-left|style=")
        rules = re.findall(r"^\.viewer \.rvpt\.outside[^{]*\{([^}]*)\}", CSS, re.M)
        self.assertTrue(rules, "docs.css 에 캡션 잉크 규칙이 없다")
        for body in rules:                          # 색면·좌측 띠 금지
            self.assertNotRegex(body, r"background|border-left")

    def test_screen_voice(self):
        """화면의 문장은 「…습니다」 한 층이고, slug 는 글자로만 선다."""
        sentences = re.findall(r"[가-힣][^`<>]*?(?:니다|다)\.", FN)
        self.assertTrue(sentences)
        for s in sentences:
            self.assertTrue(s.endswith("니다."), s)
        self.assertNotIn("${slug}", FN)             # esc 를 거치지 않은 자리 없음


if __name__ == "__main__":
    unittest.main()
