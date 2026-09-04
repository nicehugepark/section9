"""비밀 키를 화면에서 다루는 자리 (REQ-20260828-012-62x6 — 화면 몫).

사용자(08:36): "세션을 껐다켜거나 시크릿 관련 기능들이 다 완료된걸로 아는데 왜
볼 수가 없지?"

볼 수 없던 이유는 하나다 — **화면이 없었다.** 서버는 열려 있었고(`/api/secrets`
· `/api/secret/set` · `/api/secret/rm`, 시험은 test_secret_api) `web/index.html`
에는 "secret" 이라는 낱말조차 없었다. 이 사람은 대시보드로 일한다.

이 파일이 지키는 것은 **값이 화면 어디에도 나오지 않는다**는 것이다. 서버가 값을
안 준다는 것만으로는 부족하다 — 화면이 넣은 값을 입력칸에 남겨 두면 캡처·화면
공유·어깨너머로 그대로 따라간다.

계약은 일곱이다.

  ① 목록은 키 이름과 어느 쪽에 있는지뿐이다. 값을 그리는 자리가 없다.
  ② 값 칸은 password 유형이고, 저장 뒤 성패와 무관하게 비운다.
  ③ 지우기는 되돌릴 수 없으므로 확인 창을 한 단계 둔다.
  ④ 빈 상태·불러오기 실패·불러오는 중을 모두 그린다.
  ⑤ 내 계정 판에서만 낸다 — 서버의 목록은 admin 대리(as)를 받지 않는데 쓰기는
     받으므로, 남의 이름표 밑에 내 키를 늘어놓으면 그 화면은 거짓말이다.
  ⑥ 색면·세로 띠 없음. 어느 쪽에 있는지는 색이 아니라 낱말로 말한다.
  ⑦ 손 없이 넣고 지워 볼 수 있다(`?secdbg`) — 그리고 그 진단은 `S9DBG_` 로
     시작하는 키만 건드린다. 진단이 진짜 비밀을 지울 수 있으면 사고다.

실행: python3 tests/ secret_ui
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class SecretUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 목록은 이름과 둔 곳뿐 ----------

    def test_secret_u_i(self):
        """SecretUI 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_list_shows_names_not_values"):
                fn = self._fn("loadSecrets")
                self.assertIn('fetch("/api/secrets")', fn, "목록을 서버에서 받지 않는다")
                self.assertIn("k.key", fn, "키 이름을 안 그린다")
                self.assertIn("저장소 밖", fn, "어느 쪽에 있는지 말하지 않는다")
                # 서버 응답에 value 가 없지만, 화면이 그걸 그리려 든 흔적도 없어야 한다
                # 줄 하나가 읽는 필드는 이름과 둔 곳뿐이다 — 그 밖의 필드를 읽으면 언젠가
                # 값이 딸려 온다
                row = fn[fn.index("d.keys.map"):fn.index('.join("")')]
                # 가려짐(shadowed)이 붙었다 (REQ-20260828-017) — 밖에 넣은 값이 안의
                # 같은 이름에 가려 안 쓰이는 사실은 줄이 직접 말해야 한다. 그래도 읽는
                # 것은 여전히 셋뿐이다: 값을 그리는 길은 열리지 않는다.
                self.assertEqual(sorted(set(re.findall(r"\bk\.(\w+)", row))),
                                 ["key", "shadowed", "where"],
                                 "줄이 이름·둔 곳·가려짐 말고 다른 것을 읽는다")

            # ---------- ② 값 칸은 password, 저장 뒤 비운다 ----------
        with self.subTest("the_value_box_is_masked_and_cleared"):
                blk = self._block()
                self.assertRegex(blk, r'id="sec-val" type="password"', "값 칸이 가려지지 않는다")
                self.assertIn('autocomplete="new-password"', blk,
                              "브라우저가 값을 채워 넣는다")
                add = self.src[self.src.index('addBtn.addEventListener'):]
                add = add[:add.index("// 엔터로도 넣는다")]
                # 성공/실패를 가르기 **전에** 비운다 — 실패했다고 남겨 두면 그대로 방치된다
                self.assertLess(add.index('vIn.value = "";'), add.index("if (!res.ok)"),
                                "저장에 실패하면 값이 칸에 남는다")
                self.assertIn("값은 다시 보이지 않습니다", add,
                              "다시 볼 수 없다는 것을 말해 주지 않는다")

            # ---------- ③ 지우기는 확인 한 단계 ----------
        with self.subTest("removing_asks_once_because_it_cannot_be_undone"):
                blk = self._block()
                rm = blk[blk.index("secList.addEventListener"):]
                self.assertIn('kind: "confirm"', rm, "확인 없이 지운다")
                self.assertIn("되살릴 수 없습니다", rm, "되돌릴 수 없다는 것을 말하지 않는다")
                self.assertIn('ok: "지우기"', rm, "확인 버튼이 동사+목적이 아니다")
                self.assertIn('postJSONRaw("/api/secret/rm"', rm, "서버에 지우라고 하지 않는다")
                self.assertGreater(rm.index('postJSONRaw("/api/secret/rm"'),
                                   rm.index('kind: "confirm"'), "묻기 전에 지운다")

            # ---------- ④ 상태를 다 그린다 ----------
        with self.subTest("every_state_is_drawn"):
                fn = self._fn("loadSecrets")
                self.assertIn("불러오는 중…", fn, "불러오는 동안 화면이 멈춘 것처럼 보인다")
                self.assertIn("아직 넣은 비밀이 없습니다", fn, "빈 상태가 없다")
                self.assertIn("비밀 목록을 받아오지 못했습니다", fn, "받아오기 실패 상태가 없다")
                self.assertIn('id="sec-retry"', fn, "실패했을 때 다시 시도할 손잡이가 없다")
                # 빈 상태가 설명과 같은 회색으로 이어 붙으면 한 문단으로 읽힌다
                self.assertIn(".secempty{", self.src, "빈 상태를 설명과 구별하지 않는다")

            # ---------- ⑤ 내 계정 판에서만 ----------
        with self.subTest("it_only_appears_on_my_own_account"):
                self.assertIn("const mySecrets = !isAdminEdit && !asUser && u.name === getMe();",
                              self.src, "남의 계정 판에도 내 비밀이 나온다")
                self.assertIn("${mySecrets ? `", self.src, "그 판단이 화면에 안 걸려 있다")

            # ---------- ⑥ 색면 없음 ----------
        with self.subTest("it_wears_ink_not_a_colour_field"):
                css = self.src[self.src.index("/* ------- 비밀 키 · 대화 기록"):]
                css = css[:css.index(".cfg-h{")]
                # 허용되는 배경은 지면·판·잉크(hover 인버스)뿐이다 — 상태색 색면은 없다
                for m in re.finditer(r"background:([^;}]+)", css):
                    self.assertIn(m.group(1).strip(), ("none", "var(--panel)", "var(--text)",
                                                       "var(--bg)"), "배경에 색면을 깐다")
                self.assertNotIn("border-left:", css, "세로 띠를 두른다")
                self.assertNotIn("border-radius", css, "라운드를 쓴다")
                self.assertNotIn("box-shadow", css, "그림자를 쓴다")
                websrc.no_hex(self, css, "색을 하드코딩한다")
            # ---------- ⑦ 손 없이 넣고 지운다 (그리고 진짜 비밀은 못 건드린다) ----------
        with self.subTest("it_can_be_exercised_without_hands"):
                self.assertIn("[?&]secdbg", self.src, "손 없이 눌러 볼 길이 없다")
                dbg = self.src[self.src.index("if (secList && /[?&]secdbg/"):]
                dbg = dbg[:dbg.index('host.querySelector("#pf-save")')]
                self.assertIn('const K = "S9DBG_TEST"', dbg,
                              "진단이 진짜 비밀을 건드릴 수 있다")
                self.assertIn('host.querySelector("#sec-add").click()', dbg,
                              "진짜 버튼을 누르지 않는다")
                self.assertIn("dlg.querySelector(\".dlgyes\")", dbg,
                              "확인 창을 실제로 지나지 않는다")
                self.assertIn("inPanel()", dbg, "값이 샜는지 재지 않는다")

            # ---------- helpers ----------

    def _block(self):
        i = self.src.index('<div class="cfg-h">비밀 키')
        j = self.src.index('host.querySelector("#pf-save")')
        return self.src[i:j]

    def _fn(self, name):
        m = re.search(r"(async )?function %s\([^)]*\)\{[\s\S]*?\n  \}" % name, self.src)
        self.assertIsNotNone(m, "%s() 를 찾지 못했다" % name)
        return m.group(0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
