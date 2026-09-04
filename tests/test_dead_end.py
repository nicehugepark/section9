"""막다른 화면을 없앤다 — 계정 창과 깨우기 손잡이 (REQ-20260827-079 · REQ-20260828-041).

사용자의 말은 두 건 다 "안된다" 한 마디였다. 진단이 밝힌 그 "안된다"의 실체는
**고장이 아니라 막다른 길**이다.

  계정 창   고를 수 있는 줄이 0개인데 화면은 "바꿀 계정을 고르면 다시 시작할 수
            있습니다" 라고 적고 ↑↓·Ctrl+Enter 를 가르쳤다. 두 키 모두 아무 일도
            하지 않는다. `다시 시작` 은 영영 잠겨 있었다.
  깨우기     단추가 **애초에 한 번도 그려지지 않았다.** 카드는 정지 마크로
            "멈췄다"고 말하면서 깨울 손잡이는 주지 않았다 — 마크와 손잡이가
            서로 다른 시계를 봤기 때문이다.

이 파일이 못 박는 계약은 여섯이다.

  ① **갈 곳이 없으면 그렇게 말한다.** 창은 `고를 수 있음`이 아니라 `옮겨 갈 수
     있음`으로 판정하고, 0이면 조작을 가르치지 않고 다음 걸음을 가리킨다.
  ② **막힌 이유는 한 곳에서만 말한다.** 목록을 못 받음 · 세션 없음 · 갈 곳
     없음은 순서가 있는 세 처지고, 한 화면이 그중 하나만 말한다.
  ③ **만들다 만 자리를 치울 수 있다.** 로그인 전 자리에만 지우기 손잡이가 붙고,
     되돌릴 수 없으니 한 번 묻되 맨 Enter 는 물러나는 쪽에 닿는다.
  ④ **정지 마크는 손잡이가 있을 때만 선다.** 마크가 서는 조건이 손잡이가 서는
     조건의 부분집합이어야 "멈췄다고 그려 놓고 할 일은 안 주는 카드"가 구조적
     으로 생길 수 없다.
  ⑤ **같은 행동은 두 화면에서 같은 규칙.** 선행 대기가 걸린 요청은 카드에서도
     문서에서도 깨울 수 없다.
  ⑥ **눈으로 볼 길을 남긴다.** 깨우기 화면·계정 창의 네 처지를 헤드리스로
     세우는 진단이 있고, 그것은 **진짜 함수**를 부른다.

실행: python3 tests/ dead_end
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

# 서버가 돌려주는 action 낱말 — 화면은 이 중 어느 것도 알아서는 안 된다.
REMOVE_ACTIONS = ("bad-name", "outside", "not-found", "logged-in", "in-use",
                  "removed")


def grab(src, name):
    """최상위 function 하나를 통째로 떠 온다 (닫는 중괄호가 열에 0)."""
    m = re.search(r"\nfunction %s\([^)]*\)\{[\s\S]*?\n\}" % re.escape(name), src)
    assert m, name
    return m.group(0)


def grab_async(src, name):
    m = re.search(r"\nasync function %s\([^)]*\)\{[\s\S]*?\n\}" % re.escape(name), src)
    assert m, name
    return m.group(0)


class DeadEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.choose = grab(cls.src, "s9choose")
        cls.state = grab(cls.src, "acctState")
        cls.shape = grab(cls.src, "acctShape")
        cls.foot = grab(cls.src, "acctFoot")
        cls.items = grab(cls.src, "acctItems")
        cls.remove = grab_async(cls.src, "acctRemove")
        cls.switch = grab_async(cls.src, "claudeAccountSwitch")
        cls.card = grab(cls.src, "cardHTML")
        cls.probe = grab(cls.src, "stallProbe")
        cls.watch = grab(cls.src, "restartWatch")
        cls.chip = grab(cls.src, "restartChip")
        cls.tell = grab_async(cls.src, "restartTell")
        cls.dlg = grab(cls.src, "s9dlg")

    # ---------- ① 갈 곳이 없으면 그렇게 말한다 ----------

    def test_dead_end(self):
        """DeadEnd 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_choose_asks_movable_not_selectable"):
            self.assertIn("!it.off && !it.cur", self.choose)
            # 옛 술어가 남아 있으면 한 벌만 고쳐진 것이다
            self.assertNotIn("o.items.some(it => !it.off)", self.choose)
        with self.subTest("a2_hint_and_focus_both_read_movable"):
            self.assertIn("const movable = o.items.some(", self.choose)
            hint = self.choose[self.choose.index('class="dlghint"'):]
            self.assertRegex(hint[:400], r"\+ \(movable\b")
            focus = self.choose[self.choose.index("const first = movable"):]
            self.assertIn("dlg.querySelector(\".dlgact\")", focus[:300])
        with self.subTest("a3_state_has_four_branches_in_order"):
            for word in ("lost", "nosession", "nowhere", "ok"):
                self.assertIn('"%s"' % word, self.state)
            self.assertLess(self.state.index('"lost"'), self.state.index('"nosession"'))
            self.assertLess(self.state.index('"nosession"'), self.state.index('"nowhere"'))
        with self.subTest("a4_switchable_comes_from_server"):
                self.assertIn("d.switchable", self.state)
                # 옛 서버(값 없음) 대비 폴백은 있어야 한다: 없으면 늘 nowhere 가 된다
                self.assertIn("r.ready && !r.current", self.state)

            # ---------- ② 막힌 이유는 한 곳에서만 ----------
        with self.subTest("a5_four_descs_are_distinct"):
            m = re.search(r"const ACCT_DESC = \{[\s\S]*?\};", self.src)
            self.assertTrue(m)
            body = m.group(0)
            for word in ("ok:", "nowhere:", "nosession:", "lost:"):
                self.assertIn(word, body)
            lines = re.findall(r'"([^"]{6,})"', body)
            self.assertEqual(len(lines), len(set(lines)), "같은 문장을 두 처지가 쓴다")
        with self.subTest("a6_nowhere_points_at_the_next_step"):
            m = re.search(r"nowhere: \"([^\"]+)\"", self.src)
            self.assertTrue(m)
            self.assertIn("계정 추가", m.group(1))
        with self.subTest("a7_idle_speaks_only_when_it_can_become_live"):
                m = re.search(r"const ACCT_IDLE = \{[\s\S]*?\};", self.src)
                self.assertTrue(m)
                body = m.group(0)
                self.assertIn("ok:", body)
                for word in ("nowhere:", "lost:"):
                    self.assertNotIn(word, body)
                # nosession 이 있다면, 그것은 **누를 수 있게 됐다**는 뜻이어야 한다.
                if "nosession:" in body:
                    self.assertIn('st === "nosession"', self.shape)
                self.assertIn("ACCT_IDLE[st] ||", self.shape)

            # ---------- ③ 만들다 만 자리를 치운다 ----------
        with self.subTest("a8_remove_handle_only_on_unfinished_seats"):
            self.assertIn("!r.ready", self.foot)
            self.assertIn("ACCOUNT_HOME", self.foot)   # 기본 자리는 대상 밖
            self.assertIn('data-act="rm:', self.foot)
            # 손잡이는 목록 밖 어휘(.dlgact)를 그대로 입는다 — 새 컴포넌트 금지
            self.assertIn('class="dlgact gone"', self.foot)
        with self.subTest("a9_remove_reads_ok_and_message_only"):
            self.assertIn("d.message", self.remove)
            for word in REMOVE_ACTIONS:
                self.assertNotIn('"%s"' % word, self.remove)
            self.assertNotIn("d.action", self.remove)
        with self.subTest("a10_remove_asks_once_and_enter_backs_off"):
            self.assertIn('kind: "confirm"', self.remove)
            self.assertIn("safe: true", self.remove)
            self.assertIn("되돌릴 수 없습니다", self.remove)
            # s9dlg 가 그 약속을 실제로 지킨다: 첫 포커스와 바닥 힌트 둘 다
            self.assertIn("(o.safe && no ? no : yes).focus()", self.dlg)
            self.assertIn("o.safe ? (o.cancel", self.dlg)
        with self.subTest("a11_removing_reopens_the_list"):
            self.assertGreaterEqual(self.remove.count("claudeAccountSwitch()"), 3)
        with self.subTest("a12_dup_seat_does_not_take_a_line"):
                self.assertIn("r.also", self.items)
                self.assertIn("hint:", self.items)
                # 줄에 그려지는 세 값(이름·곁말·오른쪽 한마디) 어디에도 실리지 않는다
                for field in ("label", "tag", "note"):
                    m = re.search(r"^\s*%s: (.+)$" % field, self.items, re.M)
                    self.assertTrue(m, field)
                    self.assertNotIn("also", m.group(1))

            # ---------- ④ 정지 마크는 손잡이가 있을 때만 ----------
        with self.subTest("w1_stopped_dot_requires_the_servers_stall_verdict"):
            self.assertIn("const st = stallState(r);", self.card)
            head = self.card.index("const liveDot")
            tail = self.card[head:]
            hits = [m.start() for m in re.finditer(r"dot-stopped", tail)]
            self.assertTrue(hits, "정지 마크 갈래가 없다")
            for hit in hits:
                before = tail[:hit]
                q = before.rindex("?")
                # 이 갈래의 조건 = 직전 분기 기호 이후 ~ 그 물음표까지
                cut = max(before.rfind(":", 0, q), before.rfind("(", 0, q))
                cond = before[cut + 1:q]
                # 서버가 실어 준 판정은 이제 둘이다 (REQ-20260829-024 라운드4):
                # `stalled_mins`(저절로 조용해졌다)와 `stopped`(사람이 중단했다).
                # 계약은 그대로다 — 둘 다 **손잡이가 함께 서는** 사실이라,
                # 마크가 서는 조건은 여전히 손잡이가 서는 조건의 부분집합이다.
                self.assertRegex(cond, r"\b(st|r\.stopped)\b",
                                 "정지 마크가 서버 판정 없이 선다: " + cond.strip())
        with self.subTest("w2_screen_never_measures_minutes_itself"):
                self.assertNotRegex(self.card, r"Date\.now\(\)\s*-\s*[A-Za-z_.]*updated")

            # ---------- ⑤ 같은 행동은 두 화면에서 같은 규칙 ----------
        with self.subTest("w3_card_and_doc_call_the_same_gate"):
                self.assertIn("const stall = stallHTML(r);", self.card)
                self.assertIn("const belt = deedBeltHTML(r);", self.card)
                m = re.search(r"const stallRow = ([\s\S]+?);\n", self.src)
                self.assertTrue(m, "문서 화면이 조각을 잇는 자리가 없다")
                made = " ".join(m.group(1).split())
                # 벨트·잠금은 머리 띠(.dacts)로 갔다 (REQ-20260830-046). 사실 줄 층의
                # 맨 앞에는 정책 예고 줄이 선다 (REQ-20260901-005) — 관문은 그 함수
                # 안의 holdLockHTML 하나라 조건이 두 벌이 되지 않는다.
                self.assertEqual(made, "holdForecastHTML(stallDoc) + stallHTML(stallDoc)"
                                       " + holdTellHTML(stallDoc)")
                # 띠도 **같은 함수**를 부른다 — wordy 는 얼굴 인자일 뿐 조건이 아니다.
                # 정책 단추는 제 무리로 갈라섰다 (REQ-20260901-005 designer 보조).
                m2 = re.search(r"const beltDoc = ([\s\S]+?);\n", self.src)
                self.assertTrue(m2, "문서 머리 띠가 벨트를 잇는 자리가 없다")
                self.assertEqual(" ".join(m2.group(1).split()),
                                 "deedBeltHTML(stallDoc, true)")
                m3 = re.search(r"const polBtn = ([\s\S]+?);\n", self.src)
                self.assertTrue(m3, "정책 단추 무리가 없다")
                self.assertEqual(" ".join(m3.group(1).split()),
                                 "holdLockHTML(stallDoc)")

            # ---------- ⑥ 눈으로 볼 길 ----------
        with self.subTest("w4_stall_probe_only_lends_the_servers_own_field"):
            self.assertIn("stalled_mins", self.probe)
            self.assertNotIn("stallHTML", self.probe)
            self.assertNotIn("<div", self.probe)
            # 파라미터가 없으면 아무 일도 하지 않는다
            self.assertIn("if (!m || !Array.isArray(rows)) return rows;", self.probe)
            # 그리고 실제 카탈로그 길에 물려 있어야 세워진다
            self.assertIn("stallProbe(fresh)", self.src)
        with self.subTest("w5_account_previews_call_the_real_shape"):
                for name in ("account:", "nowhere:", "empty:", "lost:"):
                    m = re.search(re.escape(name) + r" acctShape\(", self.src)
                    self.assertTrue(m, name + " 이 그림으로 굳어 있다")

            # ---------- 다시 시작의 마감 ----------
        with self.subTest("w6_restart_closes_without_a_terminal_panel"):
            self.assertIn("restartWatch(T, sid, d)", self.tell)
            self.assertIn('restartSettle("done"', self.watch)
            self.assertIn('restartSettle("lost")', self.watch)
            self.assertNotIn("TERM === T && T.restart", self.watch,
                             "감시를 터미널 판에 넘긴다 — 탭을 떠나면 눈이 사라진다")
            settle = grab(self.src, "restartSettle")
            self.assertIn("restartChip(", settle, "마감이 칩을 안 고친다")
            self.assertIn("termRestartDone(", settle, "마감이 줄을 안 닫는다")
            # 줄을 닫는 손은 판정하지 않는다 — 판정 자리가 둘이면 한쪽이 거짓말한다
            line = grab(self.src, "termRestartDone")
            self.assertNotIn("restartChip(", line,
                             "줄이 칩까지 세운다 — 판정 자리가 둘이다")
            # 시계는 한 벌이다 (95/90/90 이 따로 살면 칩이 감시보다 오래 산다)
            for name in ("RESTART_WAIT_MS", "RESTART_SETTLE_MS"):
                self.assertIn(name, self.watch, "%s 를 안 쓴다" % name)
        with self.subTest("w7_lost_chip_has_one_face"):
            self.assertIn('kind === "lost"', self.chip)
            self.assertEqual(self.src.count("세션이 돌아왔는지 모름"), 1)
            self.assertNotIn("세션이 안 돌아옴", self.src,
                             "칩이 화면이 아는 것보다 단정적으로 말한다")

if __name__ == "__main__":
    unittest.main()
