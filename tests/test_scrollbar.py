"""스크롤바는 한 곳에서 그린다 (REQ-20260909-089).

주인 지적 2026-09-09: 「스크롤바가 상당히 디자인적으로 거슬린다.」 어두운 터미널
판 위에 브라우저 기본 스크롤바(화살표 달린 밝은 회색 막대)가 서 있었다. 그 막대는
이 화면이 그린 것이 아니라 브라우저가 그린 것이라, 규칙이 없으면 스킨마다 다른
브라우저의 기본이 새어 나온다.

계약 넷:
  S1 표준 속성(scrollbar-width·scrollbar-color)이 있다 — 요즘 Chrome 은 이 둘이
     있으면 ::-webkit-scrollbar 를 무시하고 이쪽을 그린다.
  S2 옛 WebKit 을 위한 같은 그림이 함께 있다(폭 · 트랙 투명 · 화살표 없음).
  S3 규칙은 tokens.css 한 곳에 산다 — 스킨 파일이 제 스크롤바를 새로 짓지 않는다.
  S4 트랙은 투명이고 썸은 색면이 아니라 선의 색(--hairline)·손이 얹히면 --muted 다.

실행: python3 tests/ scrollbar
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "..", "web", "css")


def read(name):
    return open(os.path.join(CSS, name), encoding="utf-8").read()


class ScrollbarIsDrawnInOnePlace(unittest.TestCase):
    def setUp(self):
        self.tok = read("tokens.css")

    def test_s1_the_standard_properties_are_there(self):
        self.assertRegex(self.tok, r"\*\{[^}]*scrollbar-width:\s*thin",
                         "전역 scrollbar-width 가 없다")
        self.assertRegex(self.tok, r"\*\{[^}]*scrollbar-color:\s*var\(--hairline\)\s+transparent",
                         "쉴 때의 썸 색이 선의 색이 아니다")
        self.assertIn("*:hover{scrollbar-color:var(--muted) transparent}", self.tok,
                      "손이 얹혔을 때 한 급 진해지지 않는다")

    def test_s2_the_old_webkit_gets_the_same_picture(self):
        self.assertRegex(self.tok, r"\*::-webkit-scrollbar\{[^}]*width:\s*6px")
        self.assertRegex(self.tok, r"\*::-webkit-scrollbar-track\{background:\s*transparent")
        self.assertRegex(self.tok, r"\*::-webkit-scrollbar-button\{[^}]*display:\s*none",
                         "화살표를 지우지 않았다")

    def test_s3_no_skin_invents_its_own(self):
        bad = []
        for fn in sorted(os.listdir(CSS)):
            if not fn.endswith(".css") or fn in ("tokens.css", "terminal.css"):
                continue
            for m in re.finditer(r"(?m)^([^\n{]*scrollbar[^\n{]*)\{", read(fn)):
                bad.append(f"{fn}: {m.group(1).strip()}")
        self.assertEqual(bad, [], "스킨이 제 스크롤바를 따로 짓는다 — tokens.css 한 곳으로")

    def test_s4_the_thumb_is_never_a_filled_chip(self):
        for m in re.finditer(r"::-webkit-scrollbar-thumb[^{]*\{([^}]*)\}", self.tok):
            self.assertNotIn("border-radius:999px", m.group(1).replace(" ", ""))
        # 터미널 판은 제 팔레트로 같은 규칙을 한 번 더 적는다
        self.assertIn(".ccterm,.ccterm *{scrollbar-color:var(--cc-border) transparent}", self.tok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
