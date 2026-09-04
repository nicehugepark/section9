"""전환 안내가 **거짓말하지 않고, 되풀이를 싣고, 결과 없이 사라지지 않는다**
(REQ-20260901-014).

사용자: "계정을 바꾸려는데 같은 문구만 네 번 떴다. 아무런 반응이 없다."

반응은 있었다. 문제는 그 문구가 **거짓**이었다는 것이다. 화면은 그 순간
우상단에 `fable 100%` 를 붉게 띄우고 있었고 아래 터미널 판은 클로드가 보낸
`You've reached your Fable 5 limit.` 를 그대로 찍고 있었는데, 그 사이에 낀
우리 문장만 「지금 이 세션이 일하는 중이라」라고 말했다. 한도로 굳은 턴은
일하는 중이 아니다 — 그래서 「멈추고 바꿀 수 있습니다」라는 다음 행동도
닿지 않았다(중단 신호도 그 세션이 한 턴을 돌아야 읽는데, 그 모델이 한도다).

## 계약

  ① **한도는 제 이름을 가진 갈래다.** 서버가 `why_kind`·`limit` 를 실어 주면
     그 말이 이기고, 아직 안 실어 주는 서버에서도 화면이 이미 아는 사실
     (`usageLast` 의 100%)로 같은 갈래를 세운다 — 서버 없이도 온전하다.
  ② **한도 창은 길을 둘 나란히 세운다.** 다른 모델로 바꾸기(기본 초점) +
     세션이 떠 있는 터미널 창의 명령 한 줄. **실행할 수 없는 행동을 버튼
     이름으로 약속하지 않는다** — 한도 갈래에 「중단하고 바꾸기」는 없다.
  ③ **되풀이가 사람에게 보인다.** 같은 사유 2회째부터 회차가 서고, 같은 실패가
     다시 와도 칩이 다시 그려진다(재렌더 없이 조기 반환하던 결함).
  ④ **한 사건에 문장 한 벌.** 사유는 이름으로 먼저 서고, 칩·창·줄이 그 이름
     하나에서 문장을 받는다. 내부 토막(「안 끝남」)이 창 제목이 되지 않는다.
  ⑤ **문장 속 시간은 사람 말로.** `(1m 31s)` 는 모노 메타데이터의 어휘다.
  ⑥ **눈은 탭 밖에 하나.** 시계는 상수 한 벌이라 칩이 감시보다 오래 못 산다.
  ⑦ **전환 결과는 안 줄어든다.** 좁은 폭에서 줄어야 하는 것은 배경 칩이다.
  ⑧ **사실이 아니게 되면 거둔다.** 청한 설정이 참이 되면 실패 칩을 내린다.
  ⑨ **손 없이 본다** — `?svchip=fail&again=3&svlimit` · `?dlg=limit|limitagain`.

실행: python3 tests/ switch_notice
"""
import os
import re
import unittest

import websrc
from webasset import index_path

INDEX = index_path()


class SwitchNotice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _code(self, name):
        """주석을 걷어낸 알맹이 — 옛 방식을 왜 버렸는지 적은 기록이 그 옛
        방식의 흔적으로 잡히면, 사람은 기록을 지워 시험을 통과시킨다."""
        s = re.sub(r"/\*[\s\S]*?\*/", " ", self._fn(name))
        return re.sub(r"(?m)^\s*//.*$", " ", s)

    def _css(self):
        return "\n".join(re.findall(r"<style>([\s\S]*?)</style>", self.src))

    # ---------- ① 한도는 제 이름을 가진 갈래다 ----------

    def test_switch_notice(self):
        """SwitchNotice 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_server_name_wins_and_the_screen_can_stand_alone"):
            lim = self._code("restartLimit")
            self.assertIn("d.limit", lim, "서버가 준 한도를 안 쓴다")
            self.assertIn("usageLast", lim, "화면이 아는 사실로 폴백하지 않는다")
            self.assertIn("percent >= 100", lim, "무엇이 한도인지 판정하지 않는다")
            self.assertIn("scope_name", lim, "어느 모델의 한도인지 안 견준다")
            why = self._code("restartWhy")
            self.assertIn("why_kind", why, "서버가 실어 준 이름을 안 읽는다")
        with self.subTest("a_capped_turn_is_not_called_busy"):
            why = self._code("restartWhy")
            self.assertRegex(why, r'"busy".*restartLimit\(|restartLimit\(.*"limit"',
                             "한도를 진행 중 갈래에서 떼어내지 않는다")
            say = self.src[self.src.index("const RESTART_WHY = {"):]
            say = say[:say.index("\n};")]
            self.assertIn("limit:", say, "한도 갈래의 문장이 없다")
            self.assertIn("한도를 다 써서", say, "한도를 이름으로 말하지 않는다")
        with self.subTest("it_does_not_claim_a_limit_it_cannot_prove"):
                lim = self._code("restartLimit")
                self.assertRegex(lim, r"if \(!mine\) return null",
                                 "모델을 모르는 채 한도라고 단정한다")
                # 판이 없는 화면(Board)에서도 그 기준을 얻을 길이 있어야 한다
                self.assertIn("svModelSeen", self._code("restartTell"),
                              "판이 없으면 갈래를 영영 못 가른다")

            # ---------- ② 길 둘 · 못 지킬 약속 금지 ----------
        with self.subTest("the_limit_dialog_offers_two_roads"):
            shape = self._code("restartDlgShape")
            self.assertIn('ok: "다른 모델로 바꾸기"', shape, "대시보드 안의 길이 없다")
            self.assertIn("dlgcmd", shape, "로컬 터미널 명령 한 줄이 없다")
            self.assertIn("남은 길은 둘입니다", shape)
            # 기본 초점은 첫 길이다 — safe(물러나는 쪽에서 시작)를 걸지 않는다
            self.assertNotIn("safe: true", shape, "한도 창이 물러나는 쪽에서 시작한다")
        with self.subTest("it_never_promises_an_action_it_cannot_perform"):
            self.assertNotIn("중단하고 바꾸기", self._code("restartDlgShape"))
            tell = self._code("restartTell")
            # 그 버튼은 **진짜 진행 중** 갈래에서만 선다
            i = tell.index("중단하고 바꾸기")
            self.assertIn('why !== "busy"', tell[:i],
                          "갈래를 가르기 전에 중단을 권한다")
        with self.subTest("the_dialog_points_at_the_window_the_session_lives_in"):
                self.assertIn("세션이 떠 있는 터미널 창", self.src)
                self.assertNotIn("세션 터미널을 봐 주세요", self.src)

            # ---------- ③ 되풀이 ----------
        with self.subTest("repeats_count_by_reason_not_by_target"):
            again = self._code("restartAgain")
            self.assertIn("d.attempt", again, "서버가 센 회차를 안 쓴다")
            self.assertIn("svTries", again, "화면이 셀 길이 없다")
            chip = self._code("restartChip")
            self.assertIn("번째", chip, "회차가 칩에 안 선다")
            self.assertRegex(chip, r"n >= 2", "첫 번째부터 회차를 달면 소음이다")
            self.assertRegex(chip, r"svTries = \{\}", "성공해도 회차가 안 풀린다")
        with self.subTest("the_same_failure_redraws_the_chip"):
                setter = self._code("svRestartSet")
                self.assertIn("svSeq", setter, "사건에 일련번호가 없다")
                render = self._code("renderSvChip")
                self.assertRegex(render, r"const sig = [^\n]*seq",
                                 "sig 가 사건 번호를 안 본다 — 같은 실패가 조용히 묻힌다")

            # ---------- ④ 한 사건에 문장 한 벌 ----------
        with self.subTest("the_screens_own_reasons_have_names"):
            block = self.src[self.src.index("const RESTART_WHY = {"):]
            block = block[:block.index("\n};")]
            for name in ("nostop:", "nosend:", "no_resume:", "limit:", "busy:"):
                self.assertIn(name, block, "%s 갈래의 문장이 없다" % name)
            stop = self._code("restartAfterStop")
            self.assertIn('why_kind: "nostop"', stop, "사유를 이름 없이 넘긴다")
            self.assertIn('why_kind: "nosend"', stop, "사유를 이름 없이 넘긴다")
        with self.subTest("the_unknown_reason_is_not_pasted_into_the_sentence"):
            say = self._code("restartSay")
            self.assertNotRegex(say, r"바꾸지 못했습니다 — \$\{r",
                                "기계 토막을 문장에 잇는다")
            self.assertIn("까닭을 알 수 없습니다", say)
            # 원문을 버리지는 않는다 — 손이 얹힌 자리(title)에는 기계 말을 남긴다
            self.assertIn('title="${esc(d.reason', self._code("restartLine"))
        with self.subTest("chip_and_dialog_share_one_table"):
                chip = self._code("restartChip")
                self.assertIn("restartSay(d, what)", chip, "칩이 제 문장을 따로 짓는다")
                self.assertIn("restartDlgOpen", chip, "칩이 제 창을 따로 짓는다")

            # ---------- ⑤ 어휘 ----------
        with self.subTest("a_sentence_speaks_its_units"):
                self.assertIn("function fmtSpoken(", self.src, "문장용 시간 표기가 없다")
                done = self._code("termRestartDone")
                self.assertIn("fmtSpoken", done, "줄이 라틴 축약을 쓴다")
                self.assertNotIn("fmtElapsed", done)
                # 진행 줄의 흐르는 시간도 같은 어휘다
                self.assertNotRegex(self._code("restartLog"), r"\$\{secs\}s")

            # ---------- ⑥ 눈은 탭 밖에 하나 · 시계는 한 벌 ----------
        with self.subTest("one_eye_outside_the_tab"):
            watch = self._code("restartWatch")
            self.assertNotIn("T.restart", watch,
                             "감시를 터미널 판에 넘긴다 — 탭을 떠나면 눈이 사라진다")
            self.assertIn("RESTART_WAIT_MS", watch)
            self.assertIn("RESTART_SETTLE_MS", watch)
        with self.subTest("the_clocks_are_one_set"):
            for name in ("RESTART_WAIT_MS", "RESTART_SETTLE_MS", "RESTART_POLL_MS"):
                self.assertRegex(self.src, r"const %s = \d+" % name,
                                 "%s 가 한 곳에 없다" % name)
            chip = self._code("restartChip")
            going = chip[chip.index('"going"'):chip.index('"stopping"')]
            self.assertNotRegex(going, r"\}, \d+\)",
                                "진행 칩이 저 혼자 사라지는 시계를 단다")
            # 진행 줄은 저 혼자 포기 판정을 하지 않는다
            self.assertNotRegex(self._code("restartLog"), r"secs > 90")
        with self.subTest("the_line_only_records"):
                line = self._code("termRestartDone")
                self.assertNotIn("restartChip", line, "줄이 칩까지 세운다")
                settle = self._code("restartSettle")
                for part in ("svWatchStop()", "termRestartDone(", "restartChip("):
                    self.assertIn(part, settle, "마감이 %s 를 안 한다" % part)

            # ---------- ⑦ 좁은 폭 ----------
        with self.subTest("the_switch_chip_does_not_shrink_away"):
                css = self._css()
                blk = "".join(re.findall(r"\.svchip[^{]*\{[^}]*\}", css))
                m = re.search(r"\.svchip \.sv-keep\{([^}]*)\}", css)
                self.assertTrue(m, "전환 칩에 축소 하한이 없다")
                self.assertIn("flex:none", m.group(1).replace(" ", ""))
                self.assertIn("max-width:none", m.group(1).replace(" ", ""))
                # 계기판 언어는 그대로다 — 색면·라운드·좌측 띠 금지
                websrc.no_hex(self, blk)
                self.assertNotIn("border-left", blk)
                render = self._code("renderSvChip")
                self.assertIn("sv-keep", render, "그 자리표가 칩에 안 붙는다")

            # ---------- ⑧ 사실이 아니게 되면 거둔다 ----------
        with self.subTest("a_failed_chip_retires_when_it_stops_being_true"):
                gone = self._code("svTruthGone")
                self.assertIn("want.model", gone, "청한 모델이 참이 된 것을 안 본다")
                self.assertIn("want.account", gone, "청한 계정이 참이 된 것을 안 본다")
                self.assertIn("resets_at", gone, "한도가 풀린 것을 안 본다")
                watch = self._code("svTruthWatch")
                self.assertIn("document.hidden", watch, "안 보이는 화면에도 폴이 돈다")
                self.assertIn("RESTART_TRUTH_MAX_MS", watch, "영원히 되묻는다")
                self.assertIn("svRestartSet(null)", watch, "칩을 거두지 않는다")
                # 되묻는 눈도 **같은 자리 하나**를 쓴다 — 타이머가 둘이면 또 갈린다
                self.assertIn("svWatch", watch)

            # ---------- ⑨ 손 없이 본다 ----------
        with self.subTest("it_can_be_seen_without_hands"):
            self.assertIn("svlimit", self.src, "한도 칩을 세워 볼 길이 없다")
            self.assertIn("again=", self.src, "되풀이 칩을 세워 볼 길이 없다")
            prev = self.src.split("function dlgPreview")[1]
            for k in ("limit:", "limitagain:", "limitstop:", "nostop:"):
                self.assertIn(k, prev, "진단 창에 %s 가 없다" % k)
            # 그림을 따로 그리지 않고 진짜 짓는 함수를 부른다
            self.assertIn("nostop: restartDlgShape(", prev)
            self.assertIn("limit: restartDlgShape(", prev)

if __name__ == "__main__":
    unittest.main()
