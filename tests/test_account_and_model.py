"""계정 전환 자리와 모델 팝업 (REQ-20260827-079-62x6).

사용자: "대시보드 터미널에서 클로드 계정 변경은 모델 변경하는 곳에서 제공하지
말고, 대시보드 상단에 있는 클로드 계정을 사용하는게 훨씬 직관적이지 않나?
그리고 대시보드 터미널의 모델 클릭하면 나오는 팝업창도 안예쁘다. 바꿔줘"

두 가지다.

  **자리** — 모델은 "무엇으로 생각할까"고 계정은 "누구로 로그인할까"다. 서로
  다른 두 결정이 모델 라벨 하나에 얹혀 있었다. 계정에 관한 일은 계정이 적혀
  있는 자리(상단 사용량 칩)에서 되는 것이 맞다.

  **얼굴** — 이 제품에서 팝업이 세 벌이 되면 안 된다. 사용량 툴팁 · 판정 창 ·
  모델 팝업이 각각 다른 얼굴이었고 사용자가 세 번 같은 지적을 했다. 모델
  고르기와 계정 바꾸기를 판정 대화상자와 **같은 판**에 얹는다 — 다른 것은
  안에 든 것뿐이다(확인/취소 대신 줄 목록).

계약은 일곱이다.

  ① 모델 창에 계정 항목이 없다.
  ② 상단 계정 칩을 누르면 계정 창이 열린다. 키보드로도 눌린다.
  ③ 두 창은 판정 대화상자와 같은 판(.dlgbox)을 쓴다 — 팝업이 두 벌 되지 않는다.
  ④ 고르기와 실행이 갈라져 있다 — 줄은 고르고, 이름 붙은 주 버튼이 실행한다.
     (2026-08-29 뒤집힘: 처음엔 "줄이 곧 버튼"이었다. 되돌리기 쉬운 선택을
      전제했는데 모델·계정 변경은 대화를 끊는 일이었다. 자세한 것은 그 시험의
      docstring 에.)
  ⑤ 지금 쓰는 모델이 목록에서 분명히 보인다. 색만이 아니라 표식과 낱말로.
  ⑥ 키보드로 위아래 이동과 Esc 닫기가 된다.
  ⑦ 지금 붙어 있는 계정은 서버가 말한 값이다 — 화면이 추측하지 않는다.
     (2026-08-29 뒤집힘: 처음엔 "서버가 안 주니 찍지 않는다"였다. 전제가 틀렸다 —
      세션의 CLAUDE_CONFIG_DIR 에 답이 있었고 /api/accounts 가 current 로 준다.
      자세한 것은 그 시험의 docstring 에.)

실행: python3 tests/ account_and_model
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class AccountAndModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 두 결정을 갈랐다 ----------

    def test_account_and_model(self):
        """AccountAndModel 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("model_dialog_no_longer_switches_accounts"):
            fn = self._fn("termModelChange")
            self.assertNotIn("account", fn, "모델 창에 계정이 남아 있다")
            self.assertNotIn("profiles", fn, "모델 창이 계정 프로필을 읽는다")
            # 옛 인라인 패널은 흔적까지 걷어낸다 — 두 벌이면 한 벌만 고쳐진다
            self.assertNotIn("ccmpanel", self.src, "옛 모델 패널이 남아 있다")
        with self.subTest("account_switch_lives_where_the_account_is_shown"):
                self.assertIn("function claudeAccountSwitch", self.src,
                              "계정 바꾸기가 없다")
                self.assertRegex(self.src, r'evEl\(e\.target\)\?\.closest\("#usage-chip"\)[\s\S]{0,80}claudeAccountSwitch',
                                 "상단 계정 칩을 눌러도 계정 창이 안 열린다")
                # 눌리는 것이면 눌리게 보여야 한다
                self.assertRegex(self._css_chip(), r"cursor:pointer", "누를 수 있어 보이지 않는다")
                self.assertRegex(self.src, r'id="usage-chip"[^>]*role="button"',
                                 "키보드로 누를 수 없다 (전역 role=button 경로를 못 탄다)")

            # ---------- ③④ 판은 하나 ----------
        with self.subTest("both_wear_the_judgement_dialog"):
            for fn in ("termModelChange", "acctShape"):
                self.assertIn('kind: "choose"', self._fn(fn), "%s 가 다른 팝업을 만든다" % fn)
            self.assertIn('if (kind === "choose") return s9choose(o);', self.src,
                          "고르는 변형이 s9dlg 의 한 갈래가 아니다")
            # 판은 판정 대화상자 그것 하나다
            self.assertNotRegex(self._fn("s9choose"), r"document\.createElement",
                                "고르는 변형이 제 판을 새로 만든다")
        with self.subTest("the_row_is_the_button"):
                fn = self._fn("s9choose")
                self.assertIn("dlgopt", fn, "줄이 버튼이 아니다")
                self.assertIn("dlgyes", fn, "되돌릴 수 없는 실행에 주 버튼이 없다")
                # ① 줄은 고르기만 한다
                self.assertRegex(fn, r"onclick = cf \? \(\) => pick\(b\.dataset\.opt\)",
                                 "줄을 누르는 순간 실행된다 — 고르기와 실행이 안 갈렸다")
                # ② 누른 줄이 즉시 응답한다 (표식이 옮겨 온다)
                self.assertRegex(fn, r'om\.textContent = on \? "●" : "○"',
                                 "고른 줄에 표식이 옮겨 오지 않는다")
                # ③ 안 바뀌었으면 못 누르고, 바뀌면 무슨 일이 일어날지 적힌다
                self.assertRegex(fn, r"yes\.disabled = !d", "안 바뀌었는데도 실행이 열려 있다")
                self.assertIn("dlgsay", fn, "무슨 일이 일어나는지 말하지 않는다")
                # 목록 밖의 행동은 그대로 즉시
                self.assertRegex(fn, r"done\(\{act: b\.dataset\.act",
                                 "목록 밖 행동까지 확인을 거친다")

            # ---------- ⑤ 지금 것이 보인다 ----------
        with self.subTest("current_choice_is_unmistakable"):
            fn = self._fn("s9choose")
            self.assertIn("지금 이것", fn, "지금 쓰는 것을 낱말로 말하지 않는다")
            self.assertRegex(fn, r'it\.cur \? "●" : "○"', "표식으로 가르지 않는다")
            css = self._css()
            cur = re.search(r"\.dlgopt\.cur[^{]*\{([^}]*)\}", css)
            self.assertIsNotNone(cur, "지금 쓰는 줄의 규칙이 없다")
            # 색면 금지 — 호버 틴트(카드가 이미 쓰는 그것) 말고 채운 면이 없어야 한다
            for bg in re.findall(r"background\s*:\s*([^;}\n]+)", css):
                self.assertIn(bg.strip(), ("none", "transparent", "var(--panel)",
                                           "var(--text)", "var(--bg)", "var(--accent-soft)"),
                              "색면을 깔지 않는다: %s" % bg)
            websrc.no_hex(self, css)
            self.assertNotRegex(css, r"\bborder-left\b", "좌측 세로 띠 금지")
            self.assertNotRegex(css, r"\[data-(?:skin|theme)=", "스킨 전용 스타일 금지")
        with self.subTest("current_model_comes_from_the_session"):
                fn = self._fn("termModelChange")
                self.assertIn("T.model", fn, "지금 모델을 세션에서 읽지 않는다")
                self.assertRegex(fn, r"cur: isCur\(k\)", "지금 것을 목록에 찍지 않는다")
                self.assertRegex(fn, r'cur\.indexOf\(k \+ "-"\) === 0',
                                 "세션이 주는 긴 이름(opus-5)을 별칭(opus)으로 알아보지 못한다")
                # 아무것도 안 바뀌는데 대화를 끊지 않는다
                self.assertRegex(fn, r"if \(!model && !picked\.chip\) return",
                                 "같은 것을 골라도 세션을 재시작한다")

            # ---------- ⑥ 키보드 ----------
        with self.subTest("keyboard_moves_and_escapes"):
                fn = self._fn("s9choose")
                self.assertRegex(fn, r'"ArrowDown"', "아래로 못 간다")
                self.assertRegex(fn, r'"ArrowUp"', "위로 못 간다")
                self.assertRegex(fn, r'"Escape"', "Esc 로 안 닫힌다")
                self.assertIn("activeElement", fn, "닫은 뒤 돌아갈 자리를 기억하지 않는다")
                self.assertRegex(fn, r'opts\.find\(b => b\.classList\.contains\("cur"\)\)',
                                 "지금 쓰는 줄에서 시작하지 않는다")

            # ---------- ⑦ 지어내지도, 안 찾아보지도 않는다 ----------
        with self.subTest("it_does_not_fake_the_current_profile"):
            fn = self._fn("claudeAccountSwitch") + self._fn("acctShape")
            self.assertIn("/api/accounts", fn, "계정 목록을 서버에서 받지 않는다")
            self.assertNotIn("usageLast", fn,
                             "칩이 들고 있던 값으로 지금 계정을 추측한다")
            # 빈 것은 고장이 아니다 — 무엇을 하면 되는지 말한다
            self.assertIn("empty:", fn, "목록이 비었을 때 할 말이 없다")
            self.assertIn("/api/account/add", self._fn("claudeAccountAdd"),
                          "계정을 더할 길이 없다 — 만드는 법을 글로만 가르치지 않는다")
        with self.subTest("it_can_be_opened_without_hands"):
                for k in ("model:", "account:", "empty:"):
                    self.assertIn(k, self.src.split("function dlgPreview")[1],
                                  "진단 파라미터에 %s 가 없다" % k)

            # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _css(self):
        return websrc.css_section(self, self.src, r"/\* -+ 고르는 변형")

    def _css_chip(self):
        m = re.search(r"\.usagechip\{cursor:[^}]*\}", self.src)
        self.assertIsNotNone(m, "칩의 커서 규칙을 찾지 못했다")
        return m.group(0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
