"""읽는 동안 제목을 잃는다 (REQ-20260828-009-62x6).

사용자: "문서 본문 보기를 할 때 화면 스크롤을 해서 내용을 보다보면, 본문의 제목을
잊어버린다. 무슨 내용을 보고 있었는지. 스크롤할 때 본문 제목은 앵커를 거는게 어때?
좌측 문서 목록에서 현재 보고 있는 문서를 고정하거나 강제를 해도 되는데 지금 왼쪽
문서 목록이 거의 실시간으로 목록이 갱신이 되어버리니 본문 제목을 캐치하기 어렵다."

캡처로 확인한 사실 둘: 메타 표까지 내려가면 **제목이 화면 어디에도 없다.** 그리고
왼쪽 목록에 **지금 보는 문서가 없다** — 표시가 약한 것이 아니라 그 줄이 아예 보이는
범위 밖으로 밀려나 있었다.

계약은 다섯이다.

  ① 문서 제목이 **판에 붙는다.** 아무리 내려도 제목·번호·상태 한 줄이 위에 남는다.
     어휘는 새로 만들지 않는다 — 이 화면이 이미 쓰는 붙박이(.typebar·.doclist .grp)
     그대로다: sticky top:0 · 판 배경 · 아래 헤어라인.
  ② **한 줄을 넘기지 않는다.** 읽으려고 연 화면이다. 파일 경로는 붙지 않고 함께
     올라가 사라진다.
  ③ 붙박이 줄은 판 **끝까지** 늘어난다. 좌우 여백은 스킨·밀도마다 다르므로
     (--vpad) 고정 픽셀로 적지 않는다 — 어긋나면 본문이 줄 옆으로 새어 보인다.
  ④ **목록이 발밑에서 움직이지 않는다.** 원인은 폴링 주기가 아니라 정렬 축이었다:
     `updated` 내림차순인데 에이전트가 쉬지 않고 노트를 붙이므로 15초마다 목록이
     다시 섞였다. 화면에 들어온 순간의 순위를 얼려 두고, 사람이 조건을 바꾸거나
     화면에 새로 들어올 때만 다시 언다. 그 사이 **새로 생긴 문서는 맨 위로** —
     그건 발밑이 흔들리는 것이 아니라 실제로 새것이다.
  ⑤ **지금 보는 문서는 맨 위에 못 박고, 잉크로 표시한다.** 사용자가 낸 안이
     "고정하거나 강제를 해도 되는데" 였다. 표시는 색면도 세로 띠도 아니다 —
     ● 표식과 제목 굵기다(둘 다 이 저장소가 이미 쓰는 어휘). 조건에 걸러져
     목록에 없는 문서를 열어 두었을 때도 같은 자리에 선다: 그룹 **밖** 맨 위라
     "이것도 조건에 맞는다"는 거짓말을 하지 않는다.

실행: python3 tests/ doc_title_anchor
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class DocTitleAnchor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        # 주석에 적어 둔 설명이 검사에 걸리면 다음 사람은 설명을 지워 통과시킨다
        cls.code = re.sub(r"/\*[\s\S]*?\*/", "", cls.src)
        cls.code = re.sub(r"(?m)^\s*//.*$", "", cls.code)

    # ---------- ① 제목이 붙는다 ----------

    def test_doc_title_anchor(self):
        """DocTitleAnchor 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_title_sticks_to_the_top_of_the_pane"):
            rule = self._rule(r"\.viewer \.dhead")
            self.assertIn("position:sticky", rule, "머리가 붙지 않는다")
            self.assertIn("top:0", rule, "붙는 자리가 판 위가 아니다")
            self.assertIn("background:var(--panel)", rule,
                          "배경이 없으면 본문이 제목을 뚫고 지나간다")
            self.assertIn("border-bottom:1px solid var(--hairline)", rule,
                          "목록 붙박이와 다른 어휘를 쓴다")
            # 마크업이 실제로 그 옷을 입는다 — 머리 안에 제목과 행동 띠가 함께 선다
            self.assertIn('<h1 class="dtitle">', self.code, "제목 줄에 이름표가 없다")
            self.assertIn('<div class="dhead">', self.code, "머리 덩어리가 없다")
            self.assertIn('class="acts dacts"', self.code, "행동 띠가 머리에 없다")
        with self.subTest("the_title_line_carries_name_number_and_state"):
                self.assertRegex(self.code, r'class="did"', "문서 번호가 붙박이 줄에 없다")
                self.assertRegex(self.code, r'class="dst"', "상태가 붙박이 줄에 없다")
                did = self._rule(r"\.viewer \.dtitle \.did")
                self.assertIn("var(--mono)", did, "번호가 이름처럼 보이지 않는다")
                dst = self._rule(r"\.viewer \.dtitle \.dst")
                self.assertIn("var(--mono)", dst, "상태가 이름처럼 보이지 않는다")
                self.assertIn("color:var(--sc)", dst, "상태 잉크를 쓰지 않는다")
                # 면은 깔지 않는다 — 색은 글자에만
                self.assertNotRegex(dst, r"background\s*:", "상태를 색면으로 칠했다")

            # ---------- ② 한 줄 ----------
        with self.subTest("only_one_line_sticks"):
                dpath = self._rule(r"\.viewer \.dpath")
                self.assertNotIn("position:sticky", dpath, "경로 줄까지 붙는다")
                # 붙는 것은 판 안에서 이 한 줄뿐
                stick = re.findall(r"\.viewer [^{]*\{[^}]*position:sticky", self.src)
                self.assertEqual(len(stick), 1, "판 안에 붙는 줄이 둘 이상이다: %s" % stick)

            # ---------- ③ 판 끝까지 ----------
        with self.subTest("the_sticky_line_spans_the_pane_in_every_skin"):
                rule = self._rule(r"\.viewer \.dhead")
                self.assertIn("calc(-1 * var(--vpad))", rule, "음수 여백이 고정값이다")
                self.assertIn("padding:8px var(--vpad)", rule, "안쪽 여백이 고정값이다")
                # --vpad 를 바꾸는 곳은 여백을 바꾸는 곳과 같아야 한다
                for sel in (r"\.viewer\{", r'\[data-skin="grid"\] \.viewer\{',
                            r'\[data-density="compact"\] \.viewer\{'):
                    m = re.search(sel + r"([^}]*)\}", self.src)
                    self.assertIsNotNone(m, sel)
                    self.assertIn("--vpad", m.group(1), "%s 가 --vpad 를 정하지 않는다" % sel)
                    self.assertNotRegex(m.group(1), r"padding:\s*\d+px \d",
                                        "%s 에 윗 여백이 남아 붙박이 줄 위로 본문이 스친다" % sel)

            # ---------- ④ 목록이 흔들리지 않는다 ----------
        with self.subTest("the_list_order_freezes_while_reading"):
                fn = self._fn("stableOrder")
                self.assertIn("docRank", fn, "순위를 기억하지 않는다")
                self.assertIn("refreeze", fn, "다시 얼릴 조건이 없다")
                self.assertIn("docRankKey !== key", fn, "조건이 바뀌어도 얼음이 그대로다")
                # 새 문서는 맨 위로 — 얼렸다고 새것을 묻어 두지 않는다
                self.assertIn("!docRank.has(r.id)", fn, "새 문서를 알아보지 못한다")
                self.assertIn("Math.min", fn, "새 문서가 맨 위로 오지 않는다")
                # 목록은 이제 얼린 순서로 그린다
                rd = self._fn("renderDocs")
                self.assertIn("stableOrder(rows, okey, refreeze)", rd,
                              "목록이 아직 매번 다시 정렬된다")
                self.assertNotIn("recentOrder(rows)", rd,
                                 "옛 정렬이 남아 있다 — 15초마다 다시 섞인다")
                # 다시 어는 조건: 사람이 한 일뿐 (조건 서명 + Docs 화면 재진입)
                # 판을 찾는 셀렉터에 주인 이름이 붙었다 (REQ-20260831-026 — 같은 셸을 쓰는
                # 탭이 하나 더 섰다). 묻는 것은 여전히 "판이 이미 서 있나" 하나다.
                self.assertRegex(rd, r"const refreeze = !\(\$\('#view \.docs\[data-pane=",
                                 "배경 갱신에도 순서가 다시 언다")
                for k in ("#f-user", "#f-project", "#f-tag", "mineActive()"):
                    self.assertIn(k, rd[rd.index("const okey"):rd.index("const ordered")],
                                  "조건 서명에 %s 가 빠졌다" % k)

            # ---------- ⑤ 지금 보는 문서 ----------
        with self.subTest("the_open_document_is_marked_in_place"):
            rd = self._fn("renderDocs")
            self.assertNotIn("const pin = selectedDoc", rd, "고른 문서를 아직 뽑아낸다")
            self.assertNotIn("rowHTML(pin)", rd, "뽑은 줄을 아직 맨 위에 세운다")
            # 줄을 짓는 자리는 하나 — 두 벌이면 한 벌만 고쳐진다
            self.assertEqual(rd.count('class="row${on ? " sel" : ""}"'), 1,
                             "목록 행을 두 곳에서 짓는다")
            # 표시는 잉크로. 색면도 세로 띠도 아니다. 쉼 얼굴에만 면이 없다 —
            # `:not(:hover)` 를 빼면 이 규칙이 이웃과 같아야 할 hover 틴트까지 삼킨다.
            sel = self._rule(r"\.doclist \.row\.sel:not\(:hover\)")
            self.assertIn("background:none", sel, "선택 표시가 색면이다")
            self.assertNotIn("inset", sel, "선택 표시가 세로 띠다")
            self.assertRegex(self.src, r"\.doclist \.row\.sel \.id::before\{[^}]*content:\"●\"",
                             "지금 이것이라는 표식이 없다")
            self.assertRegex(self.src,
                             r"\.doclist \.row\.sel>div:nth-child\(3\)\{[^}]*font-weight:650",
                             "제목 무게로 구분하지 않는다")
        with self.subTest("no_skin_puts_the_colour_field_or_side_bar_back"):
                for m in re.finditer(r'\[data-skin="([a-z]+)"\][^{]*\.doclist \.row\.sel[^{]*\{([^}]*)\}',
                                     self.src):
                    skin, body = m.group(1), m.group(2)
                    if skin in ("terminal", "glass"):
                        continue
                    self.assertNotRegex(body, r"inset \d", "%s 가 세로 띠를 되살렸다" % skin)
                    self.assertNotRegex(body, r"background:(?!none)", "%s 가 색면을 되살렸다" % skin)

            # ---------- 진단 ----------
        with self.subTest("there_is_a_way_to_see_it_scrolled_without_hands"):
                self.assertIn("vscroll", self.code, "내린 상태를 손 없이 세울 길이 없다")
                self.assertIn("window.scrollTo", self.code,
                              "판이 스스로 구르지 않는 스킨(soft)에서는 확인할 수 없다")

            # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _rule(self, sel):
        blks = re.findall(sel + r"\{([^}]*)\}", self.src)
        self.assertTrue(blks, "%s 규칙을 찾지 못했다" % sel)
        return ";".join(blks)


if __name__ == "__main__":
    unittest.main(verbosity=2)
