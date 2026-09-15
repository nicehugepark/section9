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
     **숨기는 것은 새로 짓는 것이 아니다** (REQ-20260916-020): 막대를 지우기만 하는
     블록(display:none · width/height:0)은 스킨마다 다른 그림을 만들 수 없으니 세지
     않는다 — 좁은 폭 탭 줄은 가로로 미는 줄이라 그 위의 막대를 숨긴다. 색·폭·모양을
     다시 정하는 선언이 하나라도 섞이면 그대로 잡는다.
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


# 막대를 **지우는** 선언. 이것만 담긴 블록은 아무것도 그리지 않으므로 스킨마다
# 다른 그림이 새어 나올 수 없다 — S3 이 세지 않는다 (REQ-20260916-020).
ERASING = re.compile(r"^(display:none|(width|height):0(px)?)$")
RULE = re.compile(r"(?m)^([^\n{]*scrollbar[^\n{]*)\{([^}]*)\}")
COMMENT = re.compile(r"/\*.*?\*/", re.S)


def invents_its_own(css):
    """스크롤바를 **새로 짓는** 규칙의 선택자들. 지우기만 하는 것은 빼고 돌려준다."""
    out = []
    for m in RULE.finditer(css):
        decls = [d.replace(" ", "") for d in COMMENT.sub("", m.group(2)).split(";")]
        if all(ERASING.match(d) for d in decls if d.strip()):
            continue
        out.append(m.group(1).strip())
    return out


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
            bad += [f"{fn}: {sel}" for sel in invents_its_own(read(fn))]
        self.assertEqual(bad, [], "스킨이 제 스크롤바를 따로 짓는다 — tokens.css 한 곳으로")

    def test_s3_hiding_is_not_inventing(self):
        """지우는 블록은 통과하고, 그리는 선언이 하나라도 섞이면 잡힌다."""
        hide = ':root:not([data-skin="soft"]) .tabs::-webkit-scrollbar'
        self.assertEqual(invents_its_own(hide + "{display:none}"), [])
        self.assertEqual(invents_its_own(".x::-webkit-scrollbar{width:0;height:0}"), [])
        self.assertEqual(
            invents_its_own(hide + "{display:none;background:#888}"), [hide],
            "지우는 선언에 그리는 선언이 섞였는데 놓쳤다")
        self.assertEqual(
            invents_its_own(".x::-webkit-scrollbar{width:10px;background:red}"),
            [".x::-webkit-scrollbar"], "제 막대를 새로 짓는 규칙을 놓쳤다")

    def test_s4_the_thumb_is_never_a_filled_chip(self):
        for m in re.finditer(r"::-webkit-scrollbar-thumb[^{]*\{([^}]*)\}", self.tok):
            self.assertNotIn("border-radius:999px", m.group(1).replace(" ", ""))
        # 터미널 판은 제 팔레트로 같은 규칙을 한 번 더 적는다
        self.assertIn(".ccterm,.ccterm *{scrollbar-color:var(--cc-border) transparent}", self.tok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
