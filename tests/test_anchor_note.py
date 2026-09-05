"""구간에 메모 달기 (REQ-20260827-072-62x6).

사용자: "문서에 특정 라인에 메모를 추가할 수 있는 기능이 있으면 좋겠고, 특정
단어, 문장, 구간을 드래그 하면 미니 프롬프트 팝업창이 떠서 애드혹 하게 프롬프팅
하고, 그 결과나 응답이 문단에 추가 되었으면 좋겠다."

서버는 `doc` 와 함께 `anchor`(끌어 고른 글 그대로)를 받으면 문서 노트 첫 줄에
`> ⌖ 고른 글` 인용으로 남긴다(커밋 2a83a17). 다시 읽는 함수는 `note_anchor(entry_text)`.

**보내는 자리가 바뀌었다** (REQ-20260828-006, 커밋 eea7382): 처음에는 `/api/chat`
으로 보냈는데, 그 길은 살아 있는 클로드 세션을 요구해서 세션이 없으면 메모가 통째로
실패했다 — 사용자가 캡처로 지적했다: "메모를 보내지 못했습니다 — 지금 붙어 있는
세션이 없습니다". **메모는 기록이지 메시지가 아니다.** 문서에 한 줄 남기는 데
클로드가 깨어 있어야 할 이유가 없다. 그래서 서버가 두 갈래를 갈랐고(`/api/note` =
기록, `/api/chat` = 답이 필요한 것) 화면은 앞쪽을 탄다.

계약은 여섯이다.

  ① 문서 본문에서 글을 끌어 고르면 그 자리에 미니 팝업이 뜨고, **고른 글이
     팝업 안에 보인다**.
  ② 쓴 말이 `doc` + `anchor` 로 전송된다.
  ③ 앵커 달린 노트를 **그 구간 옆에서** 읽을 수 있게 짚는다(양방향).
  ④ **고르기만 하고 아무것도 안 쓰면 팝업은 조용히 사라진다.** 이 기능의 가장
     큰 위험이다 — 문서를 읽으려고 끄는 사람이 훨씬 많고, 매번 쓰기 상자가
     튀어나오면 문서를 못 읽는다. 그래서 뜨는 것은 버튼 하나뿐이고, 쓰는 자리는
     눌러야 열린다.
  ⑤ 쓰는 자리는 071 의 판정 대화상자와 **같은 어휘**다. 팝업이 두 벌이면 한
     벌만 고쳐진다.
  ⑥ 문서가 바뀌어 그 글을 못 찾으면 **못 찾았다고 말한다.** 엉뚱한 곳을
     짚으면서 짚는 척하는 것이 제일 나쁘다.

실행: python3 tests/ anchor_note
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


class AnchorNote(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 고른 글이 팝업에 보인다 ----------

    def test_anchor_note(self):
        """AnchorNote 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_popup_shows_what_was_picked"):
                fn = self._fn("anchorPopShow")
                self.assertIn("anchorSelText", fn, "고른 글을 읽지 않는다")
                self.assertIn("ANCHOR_MARK", fn, "표식이 없다")
                self.assertRegex(fn, r"s\.text\.slice\(0, 34\)", "긴 글을 그대로 흘린다")
                self.assertIn("에 메모", fn, "무엇을 하는 버튼인지 말하지 않는다")
                # 문서 본문에서 고른 것만 — 메타표에서 고른 글은 문서의 글이 아니다
                sel = self._fn("anchorSelText")
                self.assertIn('root.querySelector(".md")', sel, "본문 밖의 선택도 받는다")
                self.assertIn("ANCHOR_MIN", sel, "한두 글자에도 팝업이 뜬다")
                self.assertIn("ANCHOR_MAX", sel, "문서 전체를 앵커로 삼을 수 있다")

            # ---------- ② doc + anchor ----------
        with self.subTest("it_sends_doc_and_anchor"):
                fn = self._fn("anchorSend")
                self.assertIn('"/api/note"', fn, "기록을 대화 경로로 보낸다")
                self.assertNotIn('"/api/chat"', fn, "아직 세션 경로를 탄다")
                self.assertIn("doc: docId, text, anchor", fn,
                              "doc·anchor 를 함께 보내지 않는다")
                self.assertNotIn("T.sid", fn, "메모가 아직 살아 있는 세션을 요구한다")
                # 실패 문구에서도 세션 이야기가 사라져야 한다 — 이제 무관한 사실이다
                self.assertNotIn("세션", fn, "실패 문구가 아직 세션 탓을 한다")
                # 끝난 요청이면 서버가 말해 준 것(warn)을 먼저 믿는다 — 화면의 목록은
                # 15초 묵은 것일 수 있다
                self.assertIn("d.warn", fn, "문서가 끝났는지를 서버에게 묻지 않는다")

            # ---------- ③ 그 구간 옆에서 읽는다 ----------
        with self.subTest("anchored_notes_point_both_ways"):
            fn = self._fn("anchorMark")
            self.assertIn("blockquote", fn, "앵커 인용을 찾지 않는다")
            self.assertIn("anjump", fn, "구간에서 메모로 갈 수 없다")
            self.assertIn("anback", fn, "메모에서 구간으로 갈 수 없다")
            self.assertIn("anchorFind", fn, "본문에서 그 글을 찾지 않는다")
            # 인용은 렌더돼야 찾을 수 있다 — md2html 에 인용 처리가 있어야 한다
            self.assertIn("<blockquote>", self.src, "마크다운이 인용을 그리지 않는다")
            self.assertRegex(self.src, r"const QUOTE_RE = /\^\\s\*&gt;",
                             "이미 esc() 를 지난 줄에서 `>` 로 찾는다 (한 줄도 안 걸린다)")
        with self.subTest("pointing_at_a_span_does_not_change_the_screen"):
            fn = self._fn("anchorMark")
            # 주석은 걷어내고 본다 — 왜 href 를 안 쓰는지 적어 둔 그 주석이 곧
            # 검사에 걸리면, 다음 사람은 설명을 지워서 테스트를 통과시킨다.
            code = self._nocomment(fn)
            self.assertNotIn("href", code, "문서 안 조각 링크는 이 화면에서 라우트 오염이다")
            self.assertNotRegex(code, r"\.id\s*=", "해시로 닿는 id 를 심는다")
            self.assertIn("dataset.anq", fn, "짚을 표적을 데이터로 달지 않는다")
            # 두 방향이 같은 재료 — `<a>` 가 아니라 `<button>` 이라야 키보드로도 닿는다
            self.assertEqual(
                2, len(re.findall(r'<button type="button" class="an(?:jump|back)"', code)),
                "두 손잡이가 같은 재료가 아니다 (한쪽만 고치면 반쪽이다)")
            # 옮기는 것이 아니라 **굴린다**. 위임은 한 곳에서 — anchorMark 안에서
            # 붙이면 문서를 다시 그릴 때마다 리스너가 쌓인다(떼는 코드가 없었다).
            self.assertNotIn("addEventListener", code, "다시 그릴 때마다 리스너가 쌓인다")
            self.assertIn('closest("[data-anjump],[data-anback]")', self.src,
                          "누른 것을 받아 줄 위임 핸들러가 없다")
            # 짚기는 **한 곳**에서 한다 — 위임 핸들러는 anchorGo 에 넘길 뿐이고,
            # 구르는 것도 도착을 밝히는 것도 그 함수 안에 있다. 두 벌이면 한 벌만
            # 고쳐진다(이 요청이 이미 그 값을 치렀다).
            self.assertRegex(
                self.src,
                r'closest\("\[data-anjump\],\[data-anback\]"\)[\s\S]{0,600}?anchorGo\(to\)',
                "짚기를 위임 핸들러가 제 손으로 한다")
            go = self._nocomment(self._fn("anchorGo"))
            self.assertIn("scrollIntoView", go, "짚기가 스크롤이 아니라 이동이다")
            self.assertNotIn("location", go, "짚으면서 주소를 만진다 (이 화면에서 곧 라우트다)")
            self.assertNotIn("href", go, "짚으면서 주소를 만진다")
        with self.subTest("it_finds_a_span_that_crosses_bold_and_code"):
            fn = self._fn("anchorFind")
            code = self._nocomment(fn)
            # 옛 방식의 흔적 — 마디 하나에 대고 indexOf 하던 자리
            self.assertNotIn("norm(n.nodeValue).indexOf", code,
                             "아직 글자 마디 하나 안에서만 찾는다")
            self.assertIn("flat.indexOf(want)", code, "본문을 이어 놓고 찾지 않는다")
            self.assertIn("at.push", code, "이어 붙인 글자가 어느 마디의 것인지 잃는다")
            # 마디별로 나눠 감싼다 — 조각이 여럿일 수 있다
            self.assertRegex(code, r"parts\.push", "찾은 구간을 마디별로 나누지 않는다")
            self.assertRegex(code, r"return spans\.length \? spans : null",
                             "조각들을 돌려주지 않는다")
            # 부르는 쪽도 조각들을 받는다: 전부 밑줄, 표적은 첫 조각, ⌖ 는 마지막 뒤
            mk = self._nocomment(self._fn("anchorMark"))
            self.assertIn("hits.forEach", mk, "조각 일부만 밑줄이 그어진다")
            self.assertIn("hits[0]", mk, "짚을 표적이 첫 조각이 아니다")
            self.assertIn("hits[hits.length - 1]", mk, "⌖ 가 구간 한가운데에 낀다")
        with self.subTest("arriving_is_visible_even_without_scrolling"):
            go = self._nocomment(self._fn("anchorGo"))
            self.assertIn('classList.add("anhit")', go, "도착한 자리를 밝히지 않는다")
            self.assertIn('classList.remove("anhit")', go,
                          "연달아 누르면 두 번째부터 아무 표시가 없다")
            self.assertIn("offsetWidth", go, "애니메이션을 되감지 않는다 (한 번만 밝다)")
            css = self._css()
            self.assertIn(".anhit", css, "밝히는 규칙이 없다")
            self.assertIn("@keyframes anhit", css, "밝혔다 사라지지 않는다 (표시가 남는다)")
            self.assertIn("prefers-reduced-motion", css,
                          "움직임을 줄여 달라고 한 사람에게는 도착이 보이지 않는다")
            # 자리를 미는 재료(테두리·여백)로 밝히면 글이 흔들린다 — 선(outline)이다
            self.assertIn("outline", css, "레이아웃을 미는 방식으로 밝힌다")
        with self.subTest("it_matches_exactly_not_approximately"):
            fn = self._fn("anchorFind")
            self.assertIn('replace(/\\s+/g, " ")', fn, "공백 차이로 못 찾는다")
            self.assertIn("surroundContents", fn, "찾은 자리를 감싸지 않는다")
            # 앵커 인용 자신을 짚지 않는다 (인용문 안에 같은 글이 있다)
            self.assertIn('closest("blockquote.anchorq")', fn,
                          "메모가 제 인용문을 가리킨다")
        with self.subTest("it_shows_the_memo_it_just_left"):
                fn = self._fn("anchorSend")
                code = self._nocomment(fn)
                self.assertIn("await s9dlg", code, "창을 닫기도 전에 문서를 갈아 끼운다")
                self.assertIn("loadDoc(docId)", code, "남긴 메모가 화면에 나타나지 않는다")
                # bg 재로드는 카탈로그의 updated 를 보고 '안 바뀌었다'며 돌아선다 —
                # 방금 쓴 노트는 그 목록에 아직 없으므로 앞면 재로드여야 한다.
                self.assertNotIn("loadDoc(docId, true)", code,
                                 "백그라운드 재로드는 방금 쓴 노트를 못 본다")
                self.assertIn("anchorGoNewest()", code, "남긴 메모로 데려가지 않는다")
                # 다른 문서를 보고 있을 때 남의 화면을 갈아 끼우지 않는다
                self.assertIn("dataset.showing === docId", code,
                              "보고 있지도 않은 문서를 다시 그린다")
                newest = self._nocomment(self._fn("anchorGoNewest"))
                self.assertIn("blockquote.anchorq", newest, "메모를 찾지 않는다")
                self.assertIn("anchorGo(", newest, "짚기를 제 손으로 따로 한다 (두 벌이 된다)")

            # ---------- ④ 조용히 사라진다 ----------
        with self.subTest("it_disappears_silently_when_nothing_is_written"):
                bind = self._fn("anchorBind")
                for how in ("Escape", "scroll", "mousedown"):
                    self.assertIn(how, bind, "%s 로 안 사라진다" % how)
                self.assertIn("anchorPopClose", bind)
                # 뜨는 것은 버튼 하나 — 쓰기 상자를 먼저 들이밀지 않는다
                show = self._fn("anchorPopShow")
                self.assertIn('createElement("button")', show, "고르자마자 쓰기 상자가 뜬다")
                self.assertNotIn("textarea", show, "고르자마자 쓰기 상자가 뜬다")
                self.assertNotIn("s9dlg", show, "고르자마자 대화상자가 뜬다")
                # 아무것도 안 쓰고 닫으면 아무 일도 없다
                ask = self._fn("anchorAsk")
                self.assertIn("if (text === null) return;", ask, "취소해도 무언가 보낸다")

            # ---------- ⑤ 같은 어휘 ----------
        with self.subTest("the_writing_surface_is_the_judgement_dialog"):
                ask = self._fn("anchorAsk")
                self.assertIn('s9dlg({kind: "prompt"', ask, "제 대화상자를 새로 만든다")
                self.assertIn("required: true", ask, "빈 메모도 보낸다")
                # 제목 자리에는 **판정의 대상**이 온다 (REQ-20260828-007 로 판정 창과
                # 문법을 맞췄다): 여기서 대상은 문서가 아니라 끌어 고른 그 글이다.
                # 주소는 판정 창과 같이 머리에 작은 글씨로 선다.
                self.assertIn("에 메모를 답니다", ask, "무엇을 하는 창인지 말하지 않는다")
                self.assertIn("`「${shown}」", ask, "무엇에 대고 하는 말인지 제목에 없다")
                self.assertIn("doc: shortId(docId)", ask, "어느 문서인지 머리에 적지 않는다")
                # 아주 긴 구간을 골라도 제목이 창을 밀어내지 않는다 (앵커는 400자까지)
                self.assertIn("anchor.slice(0, 60)", ask, "긴 구간을 그대로 흘린다")
                # 색면 금지 · 스킨 전용 스타일 금지
                css = self._css()
                websrc.no_hex(self, css)
                self.assertNotRegex(css, r"\[data-(?:skin|theme)=", "스킨 전용 스타일 금지")
                for v in re.findall(r"background\s*:\s*([^;}\n]+)", css):
                    self.assertIn(v.strip(), ("none", "transparent", "var(--panel)", "var(--text)"),
                                  "색면을 깔지 않는다: %s" % v)

            # ---------- ⑥ 못 찾으면 못 찾았다고 ----------
        with self.subTest("it_says_when_it_cannot_find_the_span"):
                fn = self._fn("anchorMark")
                self.assertIn("anlost", fn, "못 찾았을 때의 표시가 없다")
                self.assertIn("문서가 바뀌어 이 구간을 찾지 못했습니다", fn,
                              "왜 못 짚는지 말하지 않는다")
                self.assertRegex(fn, r"if \(!hits\)\{[\s\S]{0,300}?return;",
                                 "못 찾았는데도 짚으려 든다")

            # ---------- 서버와 같은 표식을 쓴다 ----------
        with self.subTest("the_mark_matches_the_server"):
            with open(S9_SRC, encoding="utf-8") as f:
                s9 = f.read()
            self.assertIn('ANCHOR_MARK = "\\u2316"', s9, "서버 표식이 바뀌었다")
            self.assertIn('const ANCHOR_MARK = "⌖"', self.src,
                          "화면이 서버와 다른 표식을 쓴다")
        with self.subTest("it_can_be_opened_without_hands"):
            self.assertIn("[?&]anchor\\b", self.src, "진단 파라미터가 없다")
            diag = self._fn("anchorDiag")
            self.assertIn("anchorPopShow(host", diag, "진단이 팝업을 세우지 않는다")
            # 반려는 "눌렀더니 화면이 바뀌더라" 였다 — 확인도 **눌러 보는 것**이어야
            # 한다. 누른 뒤의 탭·해시를 제목에 찍어 헤드리스에서 읽는다.
            self.assertIn("[?&]anclick=(jump|back)", diag, "눌러 보는 진단이 없다")
            self.assertIn("b.click()", diag, "누르지 않고 있는지만 본다")
            self.assertIn("tab=", diag, "누른 뒤 어느 화면인지 찍지 않는다")
        with self.subTest("the_diagnostic_is_readable_from_a_capture"):
            diag = self._nocomment(self._fn("anchorDiag"))
            self.assertIn('className = "andiag"', diag, "결과를 화면에 적지 않는다")
            self.assertIn("el.textContent = s", diag, "결과를 화면에 적지 않는다")
            self.assertIn("setTimeout(press, 250)", diag,
                          "손잡이가 늦게 생기면 누르지 않고 지나간다")
            self.assertIn("MISSING", diag, "못 눌렀다는 사실을 말하지 않는다")
            # 눌린 결과가 무엇이었는지 — 어디에 도착했는지까지 적는다
            self.assertIn("hit=", diag, "어디에 도착했는지 적지 않는다")
            self.assertIn("top=", diag, "화면이 굴렀는지 적지 않는다")
            # 앵커가 몇 개 붙고 몇 개가 길을 잃었는지도 헤드리스로 셀 수 있어야 한다
            self.assertIn("[?&]anlost\\b", self.src, "길 잃은 앵커를 셀 길이 없다")
        with self.subTest("the_diagnostic_can_press_the_last_handle"):
                diag = self._fn("anchorDiag")
                self.assertIn("[?&]anclick=(jump|back)(-last)?", diag,
                              "마지막 손잡이를 눌러 볼 길이 없다")
                self.assertIn("querySelectorAll", diag, "손잡이를 하나만 집는다")
                self.assertIn("all.length - 1", diag, "마지막 것을 고르지 않는다")

            # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _nocomment(self, js):
        """주석을 걷어낸 코드. 설명문에 적힌 낱말이 검사에 걸리지 않게."""
        js = re.sub(r"/\*[\s\S]*?\*/", "", js)
        return re.sub(r"(?m)^\s*//.*$", "", js)

    def _css(self):
        return websrc.css_section(self, self.src, r"/\* -+ 구간에 메모 달기")


if __name__ == "__main__":
    unittest.main(verbosity=2)
