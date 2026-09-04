"""판정 대화상자 — 브라우저 얼굴을 이 제품의 얼굴로 (REQ-20260827-071-62x6).

사용자: "리뷰, 반려 시 작성하는 프롬프트 창도 너무 기본 브라우저 기능이라
안예쁘다. 스킨에 걸맞는 디자인으로 보이게 해줘."

REQ-20260827-056 과 정확히 같은 실패다 — 네이티브 위젯. `prompt`/`confirm`/
`alert` 는 브라우저와 OS 가 그리는 상자라 이 제품의 서체도 색도 깊이도 정렬도
하나도 쓰지 않는다. 그리고 하필 그 자리가 **판정 경로**다: 이 제품에서 가장
중요한 순간에 남의 얼굴이 나온다.

계약은 여덟이다.

  ① 네이티브 위젯이 판정 경로에 남아 있지 않다.
  ② 대화상자는 **하나**다. 입력(prompt)·예아니오(confirm)·알림(alert)은 한
     컴포넌트의 세 변형이다. 네 군데에 각각 창을 만들면 한 벌만 고쳐진다 —
     이 저장소가 반복해 겪은 실패를 화면에서 되풀이하지 않는다.
  ③ **탭을 잠그지 않는다.** 네이티브 prompt 는 브라우저를 통째로 멈춰서
     뒤의 문서를 보면서 사유를 쓸 수 없었다. 판정하는 사람이 근거를 보면서
     못 쓴다는 건 보기 문제가 아니다.
  ④ 필수 입력은 **벌주지 않는다.** 비었으면 확인이 안 눌릴 뿐, 창을 다시
     띄워 다그치지 않는다(전에는 빈 값이면 두 번째 prompt 가 떴다).
  ⑤ 키보드로 전부 된다: 열리면 입력에 포커스, Esc 로 닫기, 닫으면 원래 있던
     곳으로 포커스 복귀. **여러 줄 쓰는 상자에서는 Enter 가 줄바꿈이고
     ⌘/Ctrl+Enter 가 확인이다** (REQ-20260828-007 로 되돌림).

     이 계약은 두 번 뒤집혔다. 1차(071)에 Enter=줄바꿈으로 만들었고, "터미널
     입력줄과 같은 손버릇이어야 한다"는 이유로 Enter=확인으로 뒤집었다가,
     사용자가 겪고 되돌렸다: "판정 메시지 입력란이 큰데, 엔터키를 누르면
     줄바꿈이 아니라 승인이든, 반려든 메시지가 전송이 되어 버린다."

     뒤집었던 논거가 틀렸다. 터미널 입력줄은 **한 줄짜리 보내기 상자**고 이
     창은 **여러 줄 짜는 상자**다. 상자의 성격이 다르면 키도 다른 것이 맞다.
     그리고 잘못 눌렀을 때의 값이 다르다 — 채팅은 한 줄 더 치면 되지만 판정은
     문서의 상태를 옮겨 버린다. 되돌릴 수 없는 쪽에 더 어려운 키를 준다.
  ⑥ 껍데기는 물려받되 **판의 무게는 다르다** (2026-08-27 반려). 판은 여전히
     hovercard, 버튼은 .acts 다 — 그래야 10스킨 대응이 따라온다. 다만 쪽지는
     났다 사라지는 읽기 전용이고 대화상자는 머물러 행위를 하는 판이라, 무게가
     같으면 "팝업 느낌이 덜하고 이질감이 있다"가 된다. 무게는 3단 규칙선 구조 ·
     가장자리와 부양 한 급 · 주 행동 버튼의 잉크 반전으로 준다. 색면은 금지.
  ⑦ **어느 버튼에서 열든 같은 자리에 같은 폭** (2026-08-27 반려). 1차는 누른
     버튼에 창을 물렸는데, 승인과 반려 버튼이 카드 안 다른 자리라 같은 종류의
     행위가 매번 다른 곳에 다른 크기로 떴다. 근접성으로 얻으려던 것(무엇을
     판정하는지)은 창 안의 제목이 이미 하고 있다.
  ⑨ **화면은 '전이'라고 말하지 않는다. 상태 이름은 번역하지 않는다**
     (REQ-20260828-007 반려). 사용자: "승인,반려에 대한 판정인데, 전이 라는
     용어가 갑자기 등장한다. 그리고 다른 상태에서는 open, in-progress, done인데
     리뷰 단계에서만 … 한글로 승인/반려 라고 표시된다. 용어를 통일할 필요가 있다."

     두 갈래로 답한다.
     (a) '전이'는 코드·CLI 가 쓰는 말이라 화면에서 지운다. 창머리는 '판정' 하나로
         모은다 — 승인·반려·상태 옮기기·취소는 다 같은 성격의 행위다.
     (b) `done`·`in-progress` 는 **번역하지 않는다.** 그 글자는 화면에만 있는 것이
         아니라 문서 앞머리·CLI 출력·커밋 메시지에 같은 글자로 박혀 있다. 화면만
         한글로 바꾸면 화면에서 본 말과 문서에서 읽는 말이 달라진다. 대신 **이름은
         이름처럼(mono 식별자), 행위는 행위처럼(문장 속 동사)** 보이게 해서 같은
         줄에 서도 헷갈리지 않게 한다. 그리고 승인하면 무엇이 되는지를 귀띔이
         아니라 **창 안 문장**에 넣는다.

  ⑧ **무엇을 판정하는지 창 안에서 읽힌다** (REQ-20260828-007). 사용자:
     "팝업에 표시되는 문서제목이 코드로만 보이고, 제목은 보이지 않아서 무엇에
     대해서 판정하려 했는지 모르겠다." 넷(반려·승인·전이·취소)이 각자 문장을
     지어 쓰다 넷 다 id 만 적고 있었다 — 한 곳(dlgFor)에서 짓는다. 주소는 카드가
     그러듯 작은 글씨로 머리에, 제목은 본문에 크게. 아주 긴 제목은 자르되
     **뒤따르는 동사가 잘려 나가지 않을 만큼만** 자른다.

실행: python3 tests/ judge_dialog
"""
import glob
import importlib.machinery
import importlib.util
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)
import os
import re
import subprocess
import sys
import tempfile
import unittest


import websrc  # 공용 원문 도우미 (REQ-20260830-029)
HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()
S9 = os.path.join(HERE, "..", "bin", "s9")

# 이름표가 상태머신을 벗어나지 않는지 보려면 상태머신 원본을 봐야 한다
_spec = importlib.util.spec_from_loader(
    "s9judge", importlib.machinery.SourceFileLoader("s9judge", S9))
s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s9)

# 판정 경로에서 네이티브 위젯이 사라져야 하는 자리
NATIVE = re.compile(r"(?<![.\w])(?:window\.)?(prompt|confirm|alert)\s*\(")


class JudgeDialog(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()
        # 주석·문자열 안의 낱말은 계약의 대상이 아니다 — 실행되는 줄만 본다
        self.code = re.sub(r"/\*[\s\S]*?\*/", "", self.src)
        self.code = re.sub(r"(?m)^\s*//.*$", "", self.code)

    # ---------- ① 네이티브 위젯이 없다 ----------

    def test_no_native_dialogs_left(self):
        """prompt·confirm·alert 가 실행 경로에 남아 있지 않다."""
        hits = [m.group(1) for m in NATIVE.finditer(self.code)]
        self.assertEqual(hits, [],
                         "네이티브 위젯이 남았다: %s" % ", ".join(sorted(set(hits))))

    # ---------- ② 대화상자는 하나 ----------

    def test_one_dialog_serves_all_three_shapes(self):
        """한 컴포넌트의 세 변형 — prompt·confirm·alert."""
        fn = self._fn("s9dlg")
        for kind in ("prompt", "confirm", "alert"):
            self.assertIn('"%s"' % kind, fn, "%s 변형이 없다" % kind)
        # 판을 두 벌 만들지 않는다 — DOM 에 한 번만 붙인다
        self.assertEqual(self.src.count('dlg.className = "dlg '), 1,
                         "대화상자 판이 여러 벌이다")

    def test_every_judgement_path_uses_it(self):
        """반려·전이 메모·승인 메모·취소 확인·오류 알림이 모두 이것을 쓴다."""
        for fn in ("judgeAct", "postStatus"):
            self.assertIn("s9dlg(", self._fn(fn), "%s 가 아직 쓰지 않는다" % fn)
        self.assertGreaterEqual(self.code.count("s9dlg({"), 6,
                                "판정 경로 일부가 아직 옛 위젯 자리에 있다")

    # ---------- ③ 뒤가 읽힌다 ----------

    def test_it_does_not_lock_the_page(self):
        """뒤의 문서를 보면서 쓸 수 있어야 한다 — 판을 덮는 막을 두지 않는다."""
        css = self._css()
        # 전면 스크림(inset:0 + 배경)은 뒤를 가린다
        for blk in re.findall(r"\.dlg[a-z]*\{([^}]*)\}", css):
            if "inset:0" in blk.replace(" ", ""):
                self.assertNotRegex(blk, r"background\s*:\s*(?!none|transparent)",
                                    "전면 막이 뒤를 가린다")
        self.assertNotIn('aria-modal="true"', self.src,
                         "모달로 선언하면 보조기술에도 뒤가 없는 것이 된다")

    def test_it_closes_when_the_screen_moves(self):
        """화면을 떠나면 창도 닫힌다 (REQ-20260827-084 → REQ-20260828-007 재작업).

        사용자: "팝업이 탭을 옮겨다녀도 계속 떠있는건 의도된게 맞는건가?"
        아니다. 이 창은 **특정 문서를 판정하는 자리**라, 그 문서가 있던 화면을
        떠나면 무엇을 판정하는지가 사라진다.

        **계약을 다시 쓴 이유**: 1차 고침은 `applyRoute` 안에서 "화면이 바뀌었나"를
        셌고, 이 테스트는 그 셈식(`const moved = …`)의 모양을 검사했다. 그런데
        사람이 화면을 옮기는 길 셋(헤더 탭 버튼·문서 링크/카드·그래프 노드)은
        **하나도 applyRoute 를 거치지 않는다** — 전부 tab/selectedDoc 을 직접 바꾸고
        pushRoute() 를 부른다. applyRoute 는 첫 진입과 뒤로가기에서만 돈다. 그래서
        테스트도 진단(?dlgnav)도 통과했는데 사용자는 계속 겪었다: 검사한 것이
        **사람이 쓰지 않는 길**이었다.

        그래서 특정 함수의 셈식이 아니라 **동작의 성질**을 계약으로 둔다:
        창은 열릴 때 화면 이름을 적어 두고, 화면이 바뀔 수 있는 길목마다 견줘
        다르면 닫는다. 15초 카탈로그 갱신처럼 화면 이름이 그대로인 재그리기에는
        닫히지 않는다 — 사유를 쓰는 중에 창이 사라지면 그게 더 나쁘다.
        """
        # 창이 매인 화면을 열 때 적어 둔다 — prompt 판과 고르는 판 둘 다
        self.assertEqual(self.code.count("dlgAt = dlgScreen()"), 2,
                         "창이 어느 화면에서 열렸는지 적어 두지 않는다")
        chk = self._fn("dlgCheckNav")
        self.assertIn("dlgScreen() !== dlgAt", chk,
                      "열린 화면과 지금 화면을 견주지 않는다")
        self.assertIn("dlgClose(null)", chk, "달라도 닫지 않는다")
        # 화면 이름에는 탭뿐 아니라 **같은 탭 안의 대상**도 들어간다 — docs 탭에서
        # 다른 문서로 옮겨 가는 것도 화면 이동이다
        scr = self._fn("dlgScreen")
        for k in ("tab", "selectedDoc", "selectedStream", "settingsSection"):
            self.assertIn(k, scr, "%s 이동을 세지 않는다" % k)
        # 길목 둘: 화면을 옮기는 모든 손이 지나는 pushRoute, 그리고 그리는 자리
        self.assertIn("dlgCheckNav()", self._fn("pushRoute"),
                      "탭 버튼·문서 링크·그래프 노드 클릭 경로에서 닫히지 않는다")
        self.assertIn("dlgCheckNav()", self._fn("render"),
                      "다시 그릴 때 화면이 바뀐 것을 보지 않는다")
        self.assertIn("dlgCheckNav()", self._fn("applyRoute"),
                      "뒤로가기로 옮겨도 창이 남는다")

    def test_it_stands_in_the_same_place_at_the_same_width(self):
        """어느 버튼에서 열든 같은 자리에 같은 폭으로 선다 (2026-08-27 반려).

        1차는 누른 버튼에 창을 물려 세웠다 — 승인 버튼과 반려 버튼이 카드 안
        다른 자리에 있어 **같은 종류의 행위가 매번 다른 곳에 다른 크기로** 떴고,
        사용자가 "의도가 있는건가"라고 물었다. 무엇을 판정하는지는 창 안의
        제목이 이미 말한다.
        """
        fn = self._fn("s9dlg")
        self.assertNotRegex(fn, r"getBoundingClientRect\(\)|placeDlg\(",
                            "여는 자리에 따라 창이 옮겨 다닌다")
        self.assertNotIn("placeDlg", self.src, "자리 계산 함수가 아직 살아 있다")
        box = self._rule(".dlgbox")
        self.assertIn("position:fixed", box.replace(" ", ""), "화면에 고정되지 않는다")
        self.assertRegex(box, r"left:50%", "가로 가운데가 아니다")
        self.assertRegex(box, r"top:", "세로 자리가 고정이 아니다")
        self.assertRegex(box, r"width:min\(", "폭이 내용에 따라 달라진다")
        # 윗변 고정 — 세로 가운데 정렬이면 내용이 긴 창과 짧은 창의 윗변이 어긋난다
        self.assertNotRegex(box, r"translate\([^)]*,[^)]*-50%",
                            "세로 가운데 정렬은 창마다 윗변을 어긋나게 한다")

    # ---------- ④ 벌주지 않는다 ----------

    def test_required_disables_instead_of_re_asking(self):
        """비었으면 확인이 안 눌릴 뿐, 창을 다시 띄우지 않는다."""
        fn = self._fn("s9dlg")
        self.assertIn("disabled", fn, "빈 값일 때 확인을 막지 않는다")
        # 판정이 judgeAct 한 곳으로 모이면서 세 갈래(승인·반려·상태 옮기기)가
        # 한 함수에 있다. 그러니 세는 것은 호출 수가 아니라 **되묻는 고리**다.
        ja = self._fn("judgeAct")
        self.assertEqual(len(re.findall(r"required:\s*true", ja)), 1,
                         "필수 입력을 여러 곳에서 요구한다")
        self.assertNotRegex(ja, r"\b(while|for)\s*\(",
                            "빈 값이면 다시 묻는 고리가 있다 — 그건 벌주는 흐름이다")

    # ---------- ⑤ 키보드 ----------

    def test_keyboard_contract(self):
        """열면 포커스, Esc 로 닫기, 닫으면 원래 자리로 복귀."""
        fn = self._fn("s9dlg")
        self.assertRegex(fn, r'"Escape"', "Esc 로 닫히지 않는다")
        self.assertIn(".focus()", fn, "열릴 때 포커스를 주지 않는다")
        self.assertRegex(fn, r"activeElement", "닫은 뒤 돌아갈 자리를 기억하지 않는다")

    def test_enter_breaks_the_line_and_cmd_enter_confirms(self):
        """여러 줄 쓰는 상자에서 Enter 는 줄바꿈이다 (REQ-20260828-007).

        **계약을 다시 쓴 이유**: 앞선 계약(Enter=확인)은 "터미널 입력줄과 같은
        손버릇"을 근거로 삼았다. 그 근거가 틀렸다 — 터미널 입력줄은 한 줄짜리
        보내기 상자고 이 창은 여러 줄 짜는 상자다. 사용자가 겪은 것: "판정 메시지
        입력란이 큰데, 엔터키를 누르면 줄바꿈이 아니라 승인이든, 반려든 메시지가
        전송이 되어 버린다." 채팅에서 잘못 누르면 한 줄 더 치면 되지만, 여기서
        잘못 누르면 문서의 상태가 옮겨진다. 값이 큰 쪽에 더 어려운 키를 준다.
        """
        fn = self._fn("s9dlg")
        self.assertIn("textarea", fn, "한 줄 입력이면 여러 줄 사유가 죽는다")
        # 쓰는 창에서 맨 Enter 는 **가로채지 않는다** — textarea 가 줄을 넣는다
        m = re.search(r"if \(ask\)\{([\s\S]*?)\n      \}", fn)
        self.assertIsNotNone(m, "쓰는 창의 Enter 처리를 찾지 못했다")
        self.assertIn("!(e.ctrlKey || e.metaKey)", m.group(1),
                      "수식키 없는 Enter 를 그냥 흘려보내지 않는다")
        self.assertNotIn("selectionStart", fn,
                         "줄을 손으로 끼워 넣을 이유가 없다 — 이제 기본 동작이다")
        # ⌘/Ctrl+Enter 가 확인이다
        self.assertRegex(fn, r"yes\.click\(\)", "확인을 누르는 자리가 없다")
        # 힌트가 사용자에게 같은 규칙을 말한다 — 자판에 새겨진 글자로
        self.assertRegex(fn, r"<kbd>\$\{DLG_CMD\}\+Enter</kbd> 로",
                         "확인 키를 알려 주지 않는다")
        self.assertRegex(fn, r"<kbd>Enter</kbd> 로 줄바꿈", "줄바꿈 키를 알려 주지 않는다")
        self.assertRegex(self.code, r'DLG_CMD = [\s\S]{0,120}Mac[\s\S]{0,120}"⌘"',
                         "맥에서 Ctrl 이라고 적으면 힌트가 거짓말이 된다")

    def test_it_says_which_document_is_being_judged(self):
        """제목이 창 안에서 읽힌다 (REQ-20260828-007 ⑧).

        사용자: "팝업에 표시되는 문서제목이 코드로만 보이고, 제목은 보이지 않아서
        무엇에 대해서 판정하려 했는지 모르겠다."
        """
        # 문장을 짓는 곳은 하나다 — 넷이 각자 지으면 언젠가 하나만 제목을 잃는다
        mk = self._fn("dlgFor")
        self.assertIn("catFind(", mk, "카탈로그에서 제목을 찾지 않는다")
        self.assertIn("「", mk, "제목을 이름으로 감싸지 않는다")
        self.assertIn("doc: shortId(", mk, "주소를 머리에 넘기지 않는다")
        # 긴 제목은 자르되 뒤따르는 동사를 밀어내지 않는다
        self.assertRegex(mk, r"t\.length > \d+", "긴 제목을 자르지 않는다")
        self.assertIn("…", mk, "잘렸다는 표시가 없다")
        # 판정·전이 넷이 모두 이것을 쓴다
        for fn in ("judgeAct",):
            self.assertIn("dlgFor(", self._fn(fn), "%s 가 제목을 말하지 않는다" % fn)
        self.assertGreaterEqual(self.code.count("dlgFor("), 5,
                                "판정 경로 일부가 아직 id 만 적는다")
        # 주소는 카드의 .id 와 같은 어휘로 머리에 선다
        self.assertIn('class="dlgdoc"', self._fn("s9dlg"), "주소를 머리에 두지 않는다")
        rule = self._rule(".dlgdoc")
        self.assertIn("var(--mono)", rule, "주소가 mono 가 아니다")
        self.assertIn("text-overflow:ellipsis", rule, "긴 주소가 머리를 밀어낸다")

    # ---------- ⑥ 새 어휘를 만들지 않는다 ----------

    def test_it_wears_the_existing_card_and_buttons(self):
        """이미 있는 hovercard 판과 .acts 판정 버튼을 그대로 입는다."""
        # 판은 만들 때 한 번 입는다(hovercard), 버튼은 그릴 때 입는다(.acts)
        self.assertRegex(self.src, r'dlg\.className = "dlg hovercard',
                         "카드 어휘를 재사용하지 않는다")
        self.assertIn('<div class="acts">', self._fn("s9dlg"),
                      "판정 버튼 어휘를 재사용하지 않는다")

    def test_no_colour_fill_no_side_bar_no_hardcoded_colour(self):
        """색면 하이라이트·세로 띠 금지, 색은 토큰으로만."""
        css = self._css()
        # 잉크(--text)와 지면(--panel/--bg)을 섞은 값은 색면이 아니다 — 무채의
        # 획을 한 급 옮긴 것이다. 금하는 것은 **색상**을 깐 면이다(--c-*/--t-*).
        INK = {"none", "transparent", "var(--panel)", "var(--text)", "var(--bg)",
               "var(--border)", "var(--hairline)"}
        for bg in re.findall(r"background\s*:\s*([^;}]+)", css):
            v = bg.strip()
            if v in INK:
                continue
            if v.startswith("color-mix("):
                toks = set(re.findall(r"var\(--[a-z-]+\)", v))
                self.assertTrue(toks, "색면을 깔지 않는다: %s" % bg)
                self.assertTrue(toks <= INK, "색면을 깔지 않는다: %s" % bg)
                continue
            self.fail("색면을 깔지 않는다: %s" % bg)
        self.assertNotIn("border-left", css, "좌측 세로 띠 금지")
        websrc.no_hex(self, css)
        self.assertNotRegex(css, r"\[data-(?:skin|theme)=",
                            "특정 스킨/톤 전용 스타일이 아니다")

    def test_buttons_say_what_they_do(self):
        """확인/취소 단독 금지 — 버튼은 동사+목적이다 (s9-design 6)."""
        calls = re.findall(r"s9dlg\(\{[\s\S]{0,400}?\}\)", self.code)
        self.assertTrue(calls, "s9dlg 호출을 찾지 못했다")
        oks = re.findall(r'ok:\s*[`"\']([^`"\']+)', "\n".join(calls))
        self.assertTrue(oks, "확인 버튼 문구를 정하지 않았다")
        for label in oks:
            self.assertNotIn(label.strip(), ("확인", "OK", "예"),
                             "모호한 확인 버튼: %r" % label)

    # ---------- ⑨ 용어 ----------

    def test_the_screen_never_says_the_internal_word(self):
        """'전이'는 코드가 쓰는 말이지 사람에게 보여 줄 말이 아니다."""
        # 실행되는 줄(주석 제거)에 남은 '전이'는 곧 화면에 뜨는 글자다
        # 줄 끝에 달린 `//` 주석도 걷어낸다 — 남은 것만이 화면에 뜨는 글자다
        lines = [re.sub(r"\s//.*$", "", ln) for ln in self.code.split("\n")]
        bad = [ln.strip() for ln in lines
               if "전이" in ln and "반전이" not in ln and "진전이" not in ln]
        self.assertEqual(bad, [], "화면 문구에 '전이'가 남았다: %s" % bad[:3])

    def test_state_names_are_not_translated(self):
        """상태 이름은 이름이다 — 문서·CLI·커밋과 같은 글자여야 한다."""
        # 창머리는 하나로 모인다
        caps = set(re.findall(r'cap:\s*"([^"]+)"', self.code))
        self.assertIn("판정", caps)
        # 상태를 **이름의 자리에** 그릴 때는 식별자를 그대로 쓴다. (낱말 자체를
        # 금할 수는 없다 — "하루 안에 완료된 요청 없음" 같은 문장에서 그 낱말은
        # 상태의 이름이 아니라 우리말 서술어다. 금하는 것은 이름 자리의 번역이다.)
        self.assertIn('<span class="stn">${esc(to)}</span>', self.code,
                      "상태 버튼이 식별자를 그대로 쓰지 않는다")
        # 승인/반려 창은 **어느 상태로 가는지**를 창 안 문장에서 말한다
        rj = self._fn("judgeAct")
        self.assertIn('stName("in-progress")', rj, "반려가 어디로 가는지 말하지 않는다")
        self.assertIn('stName("done")', self.code, "승인이 어디로 가는지 말하지 않는다")
        # 이름은 mono 로 선다
        self.assertRegex(self.src, r"\.dlgst\{[^}]*var\(--mono\)",
                         "문장 속 상태 이름이 이름처럼 보이지 않는다")

    def test_names_and_deeds_do_not_look_alike(self):
        """`→ done` 은 이름이고 `✓ 승인` 은 사람이 하는 일이다 — 글꼴로 가른다."""
        m = re.search(r"\.acts button\.deed\{([^}]*)\}", self.src)
        self.assertIsNotNone(m, "행위 버튼이 이름과 같은 글꼴로 선다")
        self.assertIn("font-family:inherit", m.group(1), "행위가 mono 로 그려진다")
        self.assertIn("letter-spacing:0", m.group(1), "한글에 트래킹이 걸려 있다")
        # 보드 판정 카드·문서 본문 둘 다 그 옷을 입는다
        self.assertRegex(self.code, r'class="deed" data-approve', "보드 승인 버튼")
        self.assertRegex(self.code, r'class="deed" data-reject', "보드 반려 버튼")
        # 5차: 옮기기 버튼도 같은 옷을 입는다 — 행위 칸의 기호와 낱말만 다르다
        self.assertIn('`<button class="deed" data-trans=', self.code,
                      "문서 본문에서 이름과 행위가 같은 옷을 입는다")

    # ---------- ⑩ 한 행동, 한 창 ----------

    def test_one_act_one_dialog_from_every_entry(self):
        """같은 행동은 어디서 눌러도 같은 창이다 (REQ-20260828-007 3차 반려).

        사용자: "보드 화면에서 승인을 할 때는 '승인하기'이고 문서에서 승인을
        할 때에는 '상태옮기기' 라고 나온다. 판정 이 단계만 보거나, 국소적으로
        판단하지말고, 전체적인 디자인, 흐름, 맥락을 다 챙기도록 해."

        원인은 문구가 아니라 **길이 둘이었다는 것**이다. 보드 카드는
        `data-approve` 로 승인 창을 열고, 문서 화면의 같은 `✓ 승인` 버튼은
        `data-trans` 로 일반 상태 옮기기 창을 열었다. 반려만 두 길이 한 함수를
        쓰고 있었고 승인은 갈라져 있었다 — 그래서 같은 버튼이 어느 화면에서
        눌리느냐에 따라 다른 창을 띄웠다. **판정이 두 벌이면 한 벌만 고쳐진다.**

        끌어 옮기기도 같은 길로 넣었다. 그 길만 창 없이 "drag 이동" 이라고
        적혀서, 반려에 사유가 필수라는 규칙이 거기로만 비껴갔고 같은 행동이
        History 에 세 가지 말로 남았다.
        """
        for anchor in ('judgeAct(ap.dataset.approve, "done", "review")',
                       'judgeAct(rj.dataset.reject, "in-progress", "review")',
                       "judgeAct(id, to, from)",
                       "judgeAct(d.id, to, d.from)"):
            self.assertIn(anchor, self.code,
                          "진입점 하나가 아직 제 창을 짓는다: %s" % anchor)
        # 창을 짓는 자리는 각각 하나뿐이다. `?dlg=` 진단 미리보기는 같은 모양을
        # 헤드리스로 열어 보는 **붙박이 견본**이라 세지 않는다 — 그것까지 세면
        # "직접 보고 고쳐라"는 규율과 이 계약이 서로를 막는다.
        live = self.code.split("function dlgPreview(")[0]
        for label in ('ok:"승인하기"', 'ok:"반려하기"', 'ok:"상태 옮기기"'):
            self.assertEqual(live.count(label), 1,
                             "%s 창이 여러 곳에서 지어진다" % label)

    def test_labels_never_promise_a_road_that_is_closed(self):
        """판정 이름표는 상태머신이 실제로 주는 길에만 붙는다.

        `review → blocked` 는 허용 전이가 아닌데 `⏸ 보류` 라벨이 달려 있었다 —
        한 번도 그려진 적 없는 이름이다. 없는 길을 가리키는 이름은 다음 사람이
        그 길이 있다고 믿게 만든다.

        레지스트리를 세우는 대신 이 한 줄로 잠근다 (REQ-20260828-007 4차):
        읽는 쪽이 하나뿐인 표는 단일 출처가 아니라 간접층이다.
        """
        keys = set(self._rvdeed())
        self.assertTrue(keys, "판정 버튼 이름표를 찾지 못했다")
        self.assertLessEqual(keys, set(s9.TRANSITIONS["review"]),
                             "review 에서 갈 수 없는 상태에 이름표가 붙어 있다: %s"
                             % sorted(keys - set(s9.TRANSITIONS["review"])))

    # ---------- ⑪ 두 화면이 같은 글자 ----------

    def test_one_grammar_for_every_state(self):
        """다섯 상태의 버튼 줄이 **한 문법**이다 (REQ-20260828-007 5차).

        사용자: "다른 상태의 카드에 대한 상태 전이도 고려해서 판단한게 맞나?"
        4차는 판정 버튼에만 도착지 이름을 붙였고, 그래서 같은 것(상태의 이름)이
        두 크기로 그려졌다 — `open` 문서의 `→ in-progress` 와 review 문서의
        `반려 in-progress` 는 목적지가 같은데 글자가 달랐다.

        규칙: 옮기는 버튼은 전부 [행위][도착지]. 행위 칸에 기호가 서면 그냥
        이동, 낱말이 서면 판정. 이름의 얼굴은 하나뿐이다.
        """
        # 라벨을 짓는 함수가 하나다 — 판정도 옮기기도 같은 틀을 통과한다
        self.assertIn("const actLabel = (to, judging)", self.code,
                      "옮기기와 판정이 각자 라벨을 짓는다")
        self.assertIn("actLabel(to, judging)", self.code,
                      "문서 화면의 전이 버튼이 그 틀을 쓰지 않는다")
        # 이름을 그리는 규칙도 하나다 — 크기·자간이 갈리면 5차 지적이 되풀이된다
        self.assertEqual(len(re.findall(r"\.acts \.stn\{", self.src)), 1,
                         "도착지 이름의 규칙이 여러 벌이다")
        # 옮기기 버튼도 판정 버튼과 같은 옷(.deed)을 입는다
        self.assertIn('`<button class="deed" data-trans=', self.code,
                      "옮기기 버튼만 다른 옷을 입는다")

    def test_board_and_document_say_the_same_word(self):
        """보드 판정 카드와 문서 화면의 버튼은 **한 함수**가 짓는다.

        3차까지 두 화면이 각자 글자를 갖고 있었고, 그래서 매번 한쪽만 고쳐졌다
        (REQ-20260828-007 4차). 같은 함수를 부르면 갈라질 수 없다.
        """
        self.assertIn('${rvLabel("done")}', self.code, "보드 승인 버튼이 제 글자를 짓는다")
        self.assertIn('${rvLabel("in-progress")}', self.code, "보드 반려 버튼이 제 글자를 짓는다")
        self.assertIn("actLabel(to, judging)", self.code,
                      "문서 화면이 같은 함수를 쓰지 않는다")
        self.assertNotIn("RVLABEL", self.code, "옛 이름표가 남아 두 벌이 됐다")

    def test_the_deed_carries_the_name_of_where_it_goes(self):
        """행위 옆에 **도착지의 이름**이 선다 — 글꼴은 갈라진 채로.

        사용자(4차): "review 문서만 버튼이 한국어라 다른 상태의 영어 이름과
        섞인다." 원인은 낱말이 아니라 `→ done` 에는 도착지 이름이 있는데
        `승인` 에는 없다는 것이었다. 이름을 붙이되 이름은 mono, 행위는 본문체 —
        한 줄에 두 얼굴이 서는 그 규칙이 곧 무게 차이다.
        """
        self.assertIn('<span class="stn">${esc(to)}</span>', self.code,
                      "행위 버튼이 도착지 이름을 달지 않는다")
        m = re.search(r"\.acts \.stn\{([^}]*)\}", self.src)
        self.assertIsNotNone(m, ".stn 규칙을 찾지 못했다")
        decl = m.group(1)
        self.assertIn("var(--mono)", decl, "도착지 이름이 이름처럼 보이지 않는다")
        # 반전(hover)에서 muted 잉크는 배경에 묻힌다 — 색을 물려받아야 읽힌다
        self.assertIn("color:inherit", decl,
                      "버튼 반전에서 도착지 이름이 묻힌다")
        # 축약은 쓰지 않는다 — 어디에도 없는 글자를 만드는 순간 전제가 무너진다
        self.assertNotIn("in-prog\"", self.code)

    def test_the_arrow_means_one_thing_on_a_row(self):
        """`→` 는 "이 상태로 옮김" 하나만 뜻한다.

        같은 줄에서 `→ blocked` 의 화살표는 도착 상태를 가리키는데
        `→ 이어 말하기` 의 화살표는 "저기로 감" 이었다 — 이어 말하기가 다섯
        번째 목적지로 위장했다 (REQ-20260828-007 4차).
        """
        self.assertNotIn("→ 이어 말하기", self.code, "화살표가 두 뜻으로 갈린다")
        self.assertIn(">이어 말하기</button>", self.code, "집기 손잡이가 사라졌다")

    def test_the_josa_is_computed_not_hedged(self):
        """`을(를)` 은 서식 편지투다 — 받침으로 계산한다."""
        self.assertNotIn("을(를)", self.code, "서식 편지투가 화면에 남았다")
        fn = self._fn("josa")
        self.assertIn("0xAC00", fn, "한글 음절 범위를 보지 않는다")
        self.assertIn("% 28", fn, "받침 유무를 세지 않는다")
        # 한글이 아니면 물러선다 — 읽는 법이 글자에 없는 것을 지어내지 않는다
        self.assertIn('`${withT}(${withoutT})`', fn, "한글이 아닐 때의 폴백이 없다")

    def test_the_cap_says_where_the_act_came_from(self):
        """창 머리는 어디서 왔는가로 정해진다 — review 에서 나가야 `판정`."""
        ja = self._fn("judgeAct")
        judging = ja.split("// 판정이 아닌 이동")[0] if "// 판정이 아닌 이동" in ja else ja
        self.assertEqual(judging.count('cap:"판정"'), 2,
                         "승인·반려만 판정이어야 한다")
        self.assertIn('cap:"상태 옮기기"', ja, "그 밖의 이동이 아직 판정을 자칭한다")
        # 서버가 전이를 못 받은 것은 사람의 거절이 아니다
        self.assertNotIn('cap:"거부"', self.code, "실패 알림이 사람의 거절로 읽힌다")
        self.assertIn('cap:"실패"', self.code, "전이 실패 알림의 머리가 없다")

    # ---------- ⑫ 의미를 문자열에 싣지 않는다 ----------

    def test_the_screen_sends_the_memo_not_the_meaning(self):
        """화면은 사람이 쓴 **원문만** 보낸다 (REQ-20260828-007 4차).

        `"승인: " + memo` 로 의미를 문자열에 실어 보내고 서버가 그 한글 두
        글자를 파싱했다 — 화면 낱말 하나를 고치면 승인 메모 인계가 소리 없이
        죽는 결합이다. 접두어를 정하는 근거는 화면에 없고 `(from, to)` 에 있다.
        """
        ja = self._fn("judgeAct")
        self.assertNotIn('"승인: "', ja, "화면이 아직 접두어를 짓는다")
        self.assertNotIn('"반려: "', ja, "화면이 아직 접두어를 짓는다")
        self.assertNotIn("대시보드 승인", self.code, "장소를 내용인 양 적는다")
        # 원문 그대로 넘기는지만 본다 — 붙임이 생기면서 인자가 하나 늘었다
        # (REQ-20260829-015). 계약은 "접두어를 화면이 짓지 않는다"이지
        # 인자 개수가 아니다.
        self.assertRegex(ja, r'postStatus\(id, "done", memo(\.text)?[,)]')
        self.assertRegex(ja, r'postStatus\(id, "in-progress", why(\.text)?[,)]')


    # ---------- helpers ----------

    def _rvdeed(self):
        """화면이 쓰는 판정 이름표의 키 — 상태 이름 그대로여야 한다."""
        m = re.search(r"const RVDEED = \{([^}]*)\}", self.code)
        if not m:
            return []
        return re.findall(r'(?:"([^"]+)"|([a-z-]+))\s*:', m.group(1)) and [
            (a or b) for a, b in re.findall(r'(?:"([^"]+)"|([a-z-]+))\s*:', m.group(1))]

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _rule(self, sel):
        """선택자 하나의 선언 블록 — 여러 규칙에 나뉘어 있으면 이어 붙인다."""
        css = self._css()
        blks = re.findall(re.escape(sel) + r"\{([^}]*)\}", css)
        self.assertTrue(blks, "%s 규칙을 찾지 못했다" % sel)
        return ";".join(blks)

    def _css(self):
        return websrc.css_section(self, self.src, r"/\* -+ 판정 대화상자")


class JudgeNoteContract(unittest.TestCase):
    """History 문구를 짓는 쪽과 되읽는 쪽이 한 쌍인가 (REQ-20260828-007 4차).

    이 계약이 없어서 `web/index.html` 의 `"승인: " + memo` 와 `bin/s9` 의
    `memo.startswith("승인:")` 가 아무 표시 없이 마주 보고 있었다.
    """

    def test_judge_note_contract(self):
        """History 문구를 짓는 쪽과 되읽는 쪽이 한 쌍인가 (REQ-20260828-007 4차)."""
        with self.subTest("only_review_exits_get_a_verb"):
            self.assertEqual(s9.judge_note("review", "done", "잘 됐다"), "승인: 잘 됐다")
            self.assertEqual(s9.judge_note("review", "in-progress", "부족"), "반려: 부족")
            # 판정이 아닌 이동은 메모 그대로 — 여기에 동사를 붙이면 거짓말이다
            self.assertEqual(s9.judge_note("in-progress", "done", "끝냄"), "끝냄")
            self.assertEqual(s9.judge_note("open", "cancelled", ""), "")
        with self.subTest("no_memo_is_said_so_and_is_not_a_memo"):
            n = s9.judge_note("review", "done", "")
            self.assertEqual(n, "승인 (메모 없음)")
            self.assertFalse(n.startswith("승인:"),
                             "메모 없는 승인이 메모 있는 승인으로 읽힌다")
            self.assertEqual(s9.judge_memo(n), "")
        with self.subTest("the_pair_round_trips"):
            for memo in ("한 줄", "콜론: 이 들어간 메모", "  앞뒤 공백  "):
                for to in ("done", "in-progress"):
                    note = s9.judge_note("review", to, memo)
                    self.assertEqual(s9.judge_memo(note + " [via dashboard]"),
                                     memo.strip(),
                                     "%r 가 왕복에서 달라진다" % memo)
        with self.subTest("old_records_still_read_the_same"):
            self.assertEqual(s9.judge_memo("대시보드 승인 [via dashboard]"), "")
            self.assertEqual(s9.judge_memo("승인: 이전 기록 [via dashboard]"), "이전 기록")
            self.assertEqual(s9.judge_memo("반려: 사유 [via dashboard]"), "사유")
        with self.subTest("the_write_path_composes_it_end_to_end"):
            tmp = tempfile.mkdtemp(prefix="s9judge-")
            env = {**os.environ, "S9_ROOT": tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
            env.pop("S9_SESSION", None)

            def cli(*argv):
                r = subprocess.run([S9, *argv], capture_output=True, text=True,
                                   env=env, timeout=20, stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 0,
                                 "s9 %s: %s%s" % (" ".join(argv), r.stdout, r.stderr))
                return r

            cli("init")
            cli("user", "add", "tester")
            cli("new", "request", "--title", "판정 문구 계약", "--summary", "s",
                "--size", "S", "--goal", "g", "--body", "b")
            doc = glob.glob(os.path.join(tmp, "vault", "requests", "**", "REQ-*.md"),
                            recursive=True)[0]
            rid = os.path.splitext(os.path.basename(doc))[0]
            cli("status", rid, "in-progress", "--note", "착수")
            cli("status", rid, "review", "--note", "확인 포인트")

            # 대시보드가 하는 그대로 — 메모 **원문만** 넘긴다
            script = ("import os,sys;"
                      "import importlib.machinery as m, importlib.util as u;"
                      "sp=u.spec_from_loader('s9x', m.SourceFileLoader('s9x', %r));"
                      "mod=u.module_from_spec(sp); sp.loader.exec_module(mod);"
                      "mod.do_transition(%r, 'done', note='이대로 갑시다',"
                      " user='tester', judge=True, via='dashboard')" % (S9, rid))
            r = subprocess.run([sys.executable, "-c", script], env=env,
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            with open(doc, encoding="utf-8") as f:
                last = [ln for ln in f.read().split("\n") if " status: " in ln][-1]
            self.assertIn("review -> done", last)
            self.assertIn("— 승인: 이대로 갑시다 [via dashboard]", last,
                          "쓰기 경로가 판정 문구를 짓지 않는다: %s" % last)
            # 그리고 읽는 쪽이 그것을 메모로 되찾는다
            note = last.split(" — ", 1)[1]
            self.assertEqual(s9.judge_memo(note), "이대로 갑시다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
