"""누른 자리에서 결과가 보인다 · 일하는 중이면 멈추고 바꾼다 (REQ-20260827-079 반려).

사용자: "계정을 claude02.pfe로 변경하고 다시 시작을 해도 아무런 반응이 없다.
그리고 계정을 변경하면 기존에 진행 중이던 작업들을 중단하는게 맞지 싶다.
진행 중인 작업을 중단하고 계정을 바꿔서 다시 이어서 하고 말이야."

**둘이 고장 나 있었다.**

① **말할 자리가 하나뿐이었다.** 결과를 적는 곳이 터미널 탭의 출력 판(`#ccout`)
   뿐인데, 계정 칩은 화면 맨 위라 대개 Board 에서 눌린다. 게다가 호출부가
   `if (TERM)` 로 감싸여 있어 **그 페이지에서 터미널을 한 번도 안 열었으면
   요청조차 나가지 않았다** — 누르고 아무 일도 안 일어나고 이유도 모르는 것,
   이 저장소가 여러 번 가장 나쁘다고 적어 둔 그것이다.

② **일하는 중이면 안 바꿨다.** 서버 가드(`_transcript_busy`)가 막았고 그것은
   옳다 — 없으면 말없이 끊긴다. 없던 것은 **멈추는 한 걸음**이다. 대화는
   `--resume` 으로 그대로 이어지므로 '이어서'는 이미 보장돼 있었다.

## 계약

  ① 세션 id 만 있으면 간다 — 터미널 판은 있으면 기록을 남길 뿐이다.
  ② 어떤 결과든 **말한다.** 조용히 빠져나가는 길이 없다.
  ③ 어느 탭에서나 보이는 자리가 있다 — 헤더 칩(새 줄이 아니다:
     REQ-20260827-017 "줄은 사람의 손을 요구하는 사실에만 준다").
  ④ 일하는 중이면 **묻고** 멈춘다. 말없이 끊지 않는다.
  ⑤ 멈추는 길은 이미 있는 그 길이다 — 수신함 `kind=interrupt`(Esc 가 쓰는 것).
     업로드 엔드포인트를 두 벌로 만들지 않는 것과 같은 이유다.
  ⑥ 멈춘 뒤 유휴가 되기까지 걸리는 **그 사이도 말한다.**
  ⑦ 서버 가드는 그대로 둔다 — 화면이 먼저 멈추고 나서 다시 청하는 순서다.
  ⑧ 모델 창에도 같이 간다 — 같은 API, 같은 무게.
  ⑨ 손 없이 본다 — `?svchip=` · `?dlg=busy|nostop|byhand|norestart`.

실행: python3 tests/ restart_reach
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


class RestartReach(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _code(self, name):
        """주석을 걷어낸 알맹이 — 옛 방식을 왜 버렸는지 적은 기록이 그 옛
        방식의 흔적으로 잡히면, 사람은 기록을 지워 시험을 통과시킨다."""
        fn = self._fn(name)
        fn = re.sub(r"/\*[\s\S]*?\*/", "", fn)
        return re.sub(r"(?m)^\s*//.*$", "", fn)

    # ---------- ① 터미널 판이 없어도 간다 ----------

    def test_restart_reach(self):
        """RestartReach 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("it_does_not_need_the_terminal_pane"):
            i = self.src.find("async function claudeAccountSwitch(")
            self.assertGreater(i, 0)
            blk = self.src[i:i + 2000]
            self.assertNotRegex(blk, r"if \(TERM\) ",
                                "터미널을 한 번도 안 연 사람은 계정을 못 바꾼다 — "
                                "요청조차 나가지 않는다")
            self.assertIn("sessionRestart(", blk, "다시 시작을 청하지 않는다")
        with self.subTest("the_session_id_comes_from_the_answer_it_already_has"):
                i = self.src.find("async function claudeAccountSwitch(")
                blk = self.src[i:i + 2000]
                self.assertRegex(blk, r"sessionRestart\(d && d\.sid",
                                 "세션 id 를 목록의 답에서 읽지 않는다")

            # ---------- ② 조용히 빠져나가지 않는다 ----------
        with self.subTest("nothing_returns_silently"):
            fn = self._code("sessionRestart")
            self.assertIn("restartTell", fn, "결과를 말하지 않는다")
            # 세션이 없으면 요청이 성립하지 않는데, 그것도 말해야 한다
            self.assertIn("s9dlg", fn, "세션이 없을 때 조용히 넘어간다")
            log = self._code("restartLog")
            self.assertIn("return", log, "기록 자리는 없을 수 있다")
            tell = self._code("restartTell")
            # 갈래마다 사람에게 닿는 것이 하나씩 있다
            self.assertIn("restartChip", tell, "어느 탭에서나 보이는 자리가 없다")
        with self.subTest("every_branch_says_something"):
                tell = self._code("restartTell")
                for kind in ('"going"', '"hand"', '"fail"'):
                    self.assertIn(kind, tell, "%s 갈래가 말하지 않는다" % kind)

            # ---------- ③ 어느 탭에서나 보이는 자리 ----------
        with self.subTest("it_is_a_chip_not_a_new_row"):
            self.assertIn("svRestartSet", self.src, "칩 상태를 두는 자리가 없다")
            chip = self._code("renderSvChip")
            self.assertIn("svRestart", chip, "칩이 다시 시작을 그리지 않는다")
            # 새 헤더 행을 만들지 않았다
            self.assertEqual(self.src.count('class="hrow3"'),
                             len(re.findall(r'class="hrow3"', self.src)))
            self.assertNotIn("hrow4", self.src, "헤더에 새 줄을 만들었다")
        with self.subTest("the_chip_does_not_reread_itself_every_second"):
            fn = self._code("restartChip")
            self.assertNotRegex(fn, r"label:[^\n]*\$\{[^\n]*sec",
                                "칩 낱말에 초를 넣었다")
            self.assertIn("spin: true", fn, "도는 표시가 없다")
            self.assertRegex(self.src, r"prefers-reduced-motion[\s\S]{0,200}sv-spin",
                             "움직임을 원치 않는 사람에게 멈춰 세우지 않는다")
        with self.subTest("the_good_news_leaves_by_itself"):
                fn = self._code("restartChip")
                done = fn[fn.index('"done"'):]
                self.assertRegex(done[:400], r"\}, \d+\)", "성공 칩이 안 사라진다")
                fail = fn[fn.rindex("sv-bad"):]
                self.assertNotRegex(fail[:300], r"\}, \d+\)",
                                    "못 바꾼 사실이 스스로 사라진다")

            # ---------- ④⑤⑥ 멈추고 바꾼다 ----------
        with self.subTest("it_asks_before_it_stops"):
            tell = self._code("restartTell")
            # 갈래를 알아보는 손이 `restartBusy` 하나에서 `restartWhy` 로 넓어졌다
            # (REQ-20260901-014 ①) — 한도로 굳은 턴은 「일하는 중」이 아니라 제 이름을
            # 가진 갈래라, 두 갈래를 가르는 판정이 여기 있어야 한다.
            self.assertRegex(tell, r"restartWhy\(|restartBusy",
                             "일하는 중인 것을 알아보지 못한다")
            self.assertRegex(tell, r'why !== "busy"',
                             "한도를 「일하는 중」과 같은 갈래로 다룬다")
            self.assertRegex(tell, r'kind: "confirm"', "묻지 않고 넘어간다")
            # 「멈추기」는 이제 **상태**의 낱말이라 행동에서 뺐다 (REQ-20260829-024
            # 라운드4 반려). 계약은 그대로다 — 버튼이 무엇을 하는지 이름이 말한다.
            self.assertIn("중단하고 바꾸기", tell, "무엇을 하는 버튼인지 이름이 없다")
            self.assertRegex(tell, r'cancel: "그대로 두기"', "안 멈출 길이 없다")
            # 되돌릴 수 있다는 사실을 말한다 — 대화가 끊기는 줄 알면 아무도 못 누른다
            self.assertIn("대화는 그대로 이어지므로", tell)
        with self.subTest("the_stop_uses_the_road_that_exists"):
            fn = self._code("restartAfterStop")
            self.assertIn('"/api/chat"', fn, "중단을 청하지 않는다")
            self.assertRegex(fn, r'kind: "interrupt"', "다른 길로 멈추려 한다")
        with self.subTest("it_speaks_while_it_waits"):
            fn = self._code("restartAfterStop")
            self.assertRegex(fn, r'restartChip\("stopping"', "기다리는 사이를 말하지 않는다")
            self.assertIn("RESTART_STOP_TRIES", fn, "언제까지 기다릴지가 없다")
            # 끝내 안 멈추면 지어내지 않고 있는 그대로 말한다. 창을 여는 손이
            # `s9dlg` 직접 호출에서 `restartDlgOpen` 으로 바뀌었다 —
            # 한 사건에 문장 한 벌을 지키려면 창도 칩과 같은 표에서 받아야 한다
            # (REQ-20260901-014 V2).
            tail = fn.split("RESTART_STOP_TRIES")[-1]
            self.assertRegex(tail, r"restartDlgOpen\(|s9dlg",
                             "안 멈췄을 때 아무 말이 없다")
            self.assertIn('why_kind: "nostop"', tail,
                          "사유를 이름 없이 토막으로 넘긴다 — 내부 토큰이 창 제목이 된다")
        with self.subTest("it_retries_only_while_busy"):
                fn = self._code("restartAfterStop")
                self.assertIn("if (restartBusy(d)) continue;", fn,
                              "다른 사유에도 계속 다시 청한다")

            # ---------- ⑦ 서버 가드는 그대로 ----------
        with self.subTest("the_server_guard_is_untouched"):
                with open(S9_SRC, encoding="utf-8") as f:
                    src = f.read()
                i = src.find("def restart_session(")
                self.assertGreater(i, 0)
                blk = src[i:i + 3000]
                self.assertIn("transcript_read(tp)", blk, "판정의 출처가 사라졌다")
                self.assertIn('st.get("busy") and not force', blk,
                              "작업 보호 가드가 사라졌다")
                self.assertIn("턴 진행 중", blk)

            # ---------- ⑧ 모델 창에도 같이 ----------
        with self.subTest("the_model_dialog_takes_the_same_road"):
            i = self.src.find("async function termModelChange(")
            blk = self.src[i:i + 3000]
            self.assertIn("sessionRestart(", blk,
                          "모델 창이 옛 길로 간다 — 같은 API 인데 규칙이 갈린다")
            self.assertEqual(self.src.count("termModelApply"), 0,
                             "옛 함수가 남아 있다 — 두 벌이면 한 벌만 고쳐진다")
        with self.subTest("the_dialogs_no_longer_promise_idle_only"):
                self.assertNotIn("세션이 쉬고 있을 때만 됩니다", self.src)
                self.assertIn("세션이 일하는 중이면 멈출지 먼저 물어봅니다", self.src)

            # ---------- ⑨ 손 없이 본다 ----------
        with self.subTest("it_can_be_seen_without_hands"):
            self.assertIn("svchip=", self.src, "칩을 세워 볼 길이 없다")
            prev = self.src.split("function dlgPreview")[1]
            for k in ("busy:", "nostop:", "byhand:", "norestart:"):
                self.assertIn(k, prev, "진단 창에 %s 가 없다" % k)
            # 그림을 따로 만들지 않고 진짜 함수를 부른다
            self.assertIn("restartChip(m[1]", self.src,
                          "칩 진단이 제 그림을 따로 그린다")

if __name__ == "__main__":
    unittest.main()
