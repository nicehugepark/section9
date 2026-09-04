"""아티클 문서 종류 — 화면 몫 (REQ-20260827-073-62x6).

뒤쪽(발번·저장·API)의 계약은 `test_article_type.py` 가 지킨다. 여기는 화면이다.

`ART-` 로 발번되는 새 문서 종류가 생겼다(`vault/articles/`, 상태 `published`
고정, 본문이 `## Original` + `## Article` 두 절 — 커밋 5e81359).

요청 문서와 달리 **읽으려고 여는 문서**다. 그래서 같은 자를 대지 않는다.

계약은 여섯이다.

  ① Docs 타입바에 아티클이 선다 — 없으면 만든 글을 찾을 길이 없다.
  ② Graph 에도 나온다. 나중에 생긴 종류는 **켠 채로** 들어온다 — 저장된 집합은
     그 종류가 있기 전에 만들어졌으므로, 그대로 쓰면 사용자가 끈 적도 없는데
     영영 꺼진 채다.
  ③ 채팅에서 새 아티클로 쓸 수 있다(`as_type: "article"`).
  ④ 그 스위치는 **문서 집기(REQ-064)와 양립하지 않는다** — 있는 문서에 이어
     붙이는 것과 새 글을 시작하는 것은 같은 메시지로 둘 다일 수 없다.
  ⑤ `## Article` 절이 **본문**으로 읽힌다. 메타·이력은 글보다 앞자리를 차지하지
     않는다(글 뒤로 접는다). 폭·행간이 요청 문서와 다르다 — 훑는 글과 읽는 글은
     같은 자를 쓰지 않는다.
  ⑥ 절의 경계는 **이름이 정해진 절**뿐이다. 아티클 본문은 제 소제목을 `##` 로
     쓰므로, "다음 ##" 으로 자르면 본문이 통째로 빈다(자가 검증에서 잡았다).

실행: python3 tests/ article_screen
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class ArticleScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 찾을 길 ----------

    def test_article_screen(self):
        """ArticleScreen 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("it_has_a_place_in_the_type_bar"):
                self.assertRegex(self.src, r'const TYPE_ORDER = \["request", "article"',
                                 "타입바에 아티클 자리가 없다")
                self.assertIn('const groups = {request:[],article:[]', self.src,
                              "목록이 아티클을 담을 자리를 만들지 않는다")
                self.assertIn("<option>article</option>", self.src,
                              "헤더 종류 필터에 아티클이 없다")
                self.assertIn('article:"아티클"', self.src, "화면에 쓸 우리말 이름이 없다")

            # ---------- ② 그래프 ----------
        with self.subTest("graph_shows_it_and_new_types_arrive_switched_on"):
                self.assertRegex(self.src, r'const GRAPH_TYPES = \["request", "article"',
                                 "그래프가 아티클을 그리지 않는다")
                self.assertIn('article:"var(--t-article)"', self.src, "타입색이 없다")
                self.assertIn('article:"#6b21a8"', self.src, "토큰을 못 읽을 때의 대체색이 없다")
                self.assertIn("const GTYPES_DEFAULT", self.src, "기본으로 켤 종류 목록이 없다")
                self.assertIn("GTYPES_SEEN", self.src,
                              "사용자가 끈 것과 '아직 있어 본 적 없는 것'을 가르지 않는다")
                self.assertRegex(self.src,
                                 r"GTYPES_DEFAULT\.forEach\(t => \{ if \(!GTYPES_SEEN\.has\(t\)\) gtypes\.add\(t\)",
                                 "새 종류가 꺼진 채로 들어온다")
                # 타입색은 모든 tone 에서 정의돼야 한다 — 하나라도 빠지면 그 톤에서 색이 없다
                self.assertGreaterEqual(len(re.findall(r"--t-article:#", self.src)), 4,
                                        "일부 톤에 아티클 색이 없다")

            # ---------- ③④ 채팅에서 쓰기 ----------
        with self.subTest("chat_can_start_an_article"):
            send = self._fn("sendChat")
            self.assertIn('as_type: "article"', send, "아티클로 보내지 않는다")
            self.assertIn("function artToggle", self.src, "켜고 끄는 자리가 없다")
            self.assertIn('id="cc-art"', self.src, "입력줄에 손잡이가 없다")
            self.assertIn('aria-pressed', self.src, "켜졌는지 보조기술이 알 수 없다")
        with self.subTest("article_and_doc_pick_are_exclusive"):
            t = self._fn("artToggle")
            self.assertIn("docTarget = null", t, "아티클을 켜도 집어 둔 문서가 남는다")
            self.assertIn("TERM.target = null", t, "아티클을 켜도 에이전트 지목이 남는다")
            self.assertIn("if (asArticle) artToggle(false)", self._fn("docPick"),
                          "문서를 집어도 아티클 모드가 남는다")
            send = self._fn("sendChat")
            self.assertIn("!tgt && !dt && asArticle", send, "셋을 함께 보낸다")
        with self.subTest("the_chip_says_which_of_the_three_is_standing"):
                fn = self._fn("termTargetRender")
                self.assertIn("새 아티클", fn, "아티클 모드일 때 아무 말도 없다")
                self.assertIn("box.hidden = !t && !docTarget && !asArticle;", fn,
                              "아무것도 안 걸렸는데 줄이 남거나, 걸렸는데 줄이 없다")

            # ---------- ⑤ 읽는 문서 ----------
        with self.subTest("the_article_is_the_body_not_a_section"):
                load = self._fn("loadDoc")
                self.assertIn('m.type === "article" ? docSection(d.body, "Article")', load,
                              "아티클 절을 본문으로 삼지 않는다")
                self.assertIn('<article class="artdoc">', load, "읽는 글의 틀이 없다")
                self.assertIn('<details class="artmeta">', load,
                              "메타·이력을 접지 않는다 — 글보다 앞자리를 차지한다")
                self.assertIn("docWithout(d.body", load, "원문·이력을 어디에도 남기지 않는다")
                # 읽는 폭·행간은 요청 문서와 다르다
                css = self._css()
                self.assertRegex(css, r"\.artdoc\{[^}]*max-width:3[0-9]em",
                                 "한 줄이 너무 길어 다음 줄 첫 글자를 못 찾는다")
                self.assertRegex(css, r"\.artdoc \.artmd\{[^}]*line-height:1\.[89]",
                                 "행간이 훑는 글 그대로다")
                websrc.no_hex(self, css)
            # ---------- ⑥ 절 경계 ----------
        with self.subTest("section_boundaries_are_named_sections_only"):
            self.assertIn('const DOC_SECTIONS = ["Original", "Article", "Notes", "History"]',
                          self.src, "경계로 삼을 절 이름이 정해져 있지 않다")
            at = self._fn("docSectionAt")
            self.assertIn("DOC_SEC_RE.exec", at, "다음 경계를 이름으로 찾지 않는다")
            self.assertNotRegex(at, r"/\^##\\s\+/m", "아무 ## 이나 경계로 삼는다")
        with self.subTest("it_can_be_opened_without_hands"):
                self.assertIn("[?&]art\\b", self.src, "아티클 모드를 세울 진단 파라미터가 없다")

            # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _css(self):
        return websrc.css_section(
            self, self.src, r"/\* -+ 아티클 \(REQ-20260827-073\)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
