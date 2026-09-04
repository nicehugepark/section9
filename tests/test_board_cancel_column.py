"""취소 열은 **취소된 것이 있는 날에만** 선다 (REQ-20260829-031-62x6).

사용자(17:15): "이걸 보여줄 필요가 있나?" — 판의 취소 열이 `하루 안에 취소된
요청 없음` 한 줄만 담은 채 한 칸을 통째로 쓰고 있었다.

**이 화면이 이미 적어 둔 규칙이 있다** (colHTML 의 열 머리 주석): "0건이면 아예
안 나온다 — 매번 참인 문장은 곧 안 읽히고, 없는 것을 굳이 말하는 자리가 늘면
있는 것이 묻힌다." 취소 열이 그 규칙의 예외로 남아 있었다.

**다른 열과 가르는 잣대는 '비어 있음이 정보인가'다.**
  · open·in-progress·review 는 비어 있음 자체가 사람이 확인하러 오는 값이다
    ("판정 대기 0"은 눈으로 확인하러 오는 수다) — 비어도 선다.
  · done 은 "오늘 무엇을 끝냈나"라 매일 보는 값이다 — 비어도 선다.
  · 취소는 예외적 사건이라 **비어 있는 것이 기본값**이고, 기본값을 매일 한 칸으로
    말할 이유가 없다.
  · blocked·draft 는 이 요청 이전부터 "있을 때만" 서 있었다 — 건드리지 않는다.

**감추는 것과 잃는 것은 다르다**: 취소된 것이 생긴 날에는 그대로 서고, 그 열의
하루 잣대·접기·개수는 done 과 똑같다(REQ-20260827-057). 하루가 지나 내려간 것은
done 과 마찬가지로 Docs 에 그대로 있다.

딸려 오는 값 하나를 적어 둔다: **열이 없는 날에는 끌어다 취소하는 자리도 없다.**
취소는 문서 화면의 `→ cancelled` 로 늘 갈 수 있고 되돌릴 수도 있어서, 매일 한
칸을 내주고 지킬 만큼의 지름길은 아니라고 봤다.

판정을 정규식으로 짐작하지 않고 `colStanding` 을 그대로 떼어 node 로 **실행**한다
(test_board_done_window 와 같은 방식).

실행: python3 tests/ board_cancel_column
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

DAY = 24 * 60 * 60 * 1000


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = find_node()


def grab(src, pattern, what):
    m = re.search(pattern, src, re.S | re.M)
    assert m, f"{what} 를 못 찾았다 — 이름이 바뀌었으면 이 시험도 따라가야 한다"
    return m.group(0)


class BoardCancelColumn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.win = grab(cls.src, r"const TERMINAL_WINDOW_MS = [^\n]*;",
                       "TERMINAL_WINDOW_MS")
        cls.at = grab(cls.src, r"const termAt = [^\n]*;", "termAt")
        cls.live = grab(cls.src, r"const colLive = [^;]*;", "colLive")
        cls.always = grab(cls.src, r"const COL_ALWAYS = [^\n]*;", "COL_ALWAYS")
        cls.stand = grab(cls.src, r"const colStanding = [^;]*;", "colStanding")
        cls.board = grab(cls.src, r"^function renderBoard\(rows\)\{.*?^\}",
                         "renderBoard")

    def stands(self, key, agos):
        """`ago` = 몇 ms 전에 그 상태가 됐나. 고정 시각을 박으면 시험이 스스로 늙는다."""
        if not NODE:
            self.skipTest("node 없음 — 실행 검증 생략 (소스 계약은 별도 검사)")
        script = "\n".join([
            'const TERMINAL = new Set(["done","cancelled"]);',
            self.win, self.at, self.live, self.always, self.stand,
            "const rows = %s.map(ago => ago === null ? {} :" % json.dumps(agos),
            "  ({status_since: new Date(Date.now() - ago).toISOString()}));",
            "console.log(JSON.stringify(colStanding(%s, rows)));" % json.dumps(key),
        ])
        p = subprocess.run([NODE, "-e", script], capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0, f"node 실행 실패:\n{p.stderr[-2000:]}")
        return json.loads(p.stdout.strip().splitlines()[-1])

    # X1 — 이 요청의 전부: 오늘 취소된 것이 없으면 열이 서지 않는다
    def test_board_cancel_column(self):
        """BoardCancelColumn 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("x1_no_cancels_today_no_column"):
                self.assertFalse(self.stands("cancelled", []),
                                 "취소가 한 건도 없는데 열이 자리를 먹는다")
                self.assertFalse(self.stands("cancelled", [3 * DAY, 9 * DAY]),
                                 "이틀 지난 취소 때문에 열이 서서 '없음' 한 줄만 말한다")

            # X2 — 있는 것을 놓치게 하지는 않는다
        with self.subTest("x2_a_cancel_today_stands_the_column"):
                self.assertTrue(self.stands("cancelled", [60 * 1000]),
                                "오늘 취소한 것이 있는데 열이 없다 — 감춘 게 아니라 잃었다")
                self.assertTrue(self.stands("cancelled", [5 * 60 * 60 * 1000, 9 * DAY]),
                                "오늘 것 하나와 옛것이 섞이면 열이 서야 한다")

            # X3 — 경계는 done 과 같은 하루다 (잣대를 새로 만들지 않는다)
        with self.subTest("x3_the_same_day_as_done"):
                self.assertTrue(self.stands("cancelled", [DAY - 60 * 1000]))
                self.assertFalse(self.stands("cancelled", [DAY + 60 * 1000]))

            # X4 — done 은 비어도 선다: "오늘 무엇을 끝냈나"는 매일 보는 값이다
        with self.subTest("x4_done_still_stands_when_empty"):
                self.assertTrue(self.stands("done", []))
                self.assertTrue(self.stands("done", [9 * DAY]),
                                "하루 지난 완료뿐이어도 done 열은 제 이름을 지킨다")

            # X5 — 비어 있음이 정보인 열은 그대로다
        with self.subTest("x5_the_live_columns_are_untouched"):
                for key in ("open", "in-progress", "review"):
                    self.assertTrue(self.stands(key, []),
                                    f"{key} 열이 비었다고 사라졌다 — 그 0 은 사람이 보러 오는 값이다")

            # X6 — 원래 "있을 때만" 서던 열의 규칙은 건드리지 않는다
        with self.subTest("x6_the_old_rule_survives_for_the_others"):
                for key in ("blocked", "draft"):
                    self.assertFalse(self.stands(key, []))
                    self.assertTrue(self.stands(key, [9 * DAY]),
                                    "취소 아닌 열까지 시간으로 잘랐다")

            # ---------- 소스 계약 ----------
        with self.subTest("c1_one_judgement_in_one_place"):
            self.assertIn("colStanding(st, grp)", self.board)
            self.assertNotIn('"open","in-progress","review","done"', self.board,
                             "열 목록이 renderBoard 에 다시 적혀 있다")
        with self.subTest("c2_the_same_clock_for_standing_and_drawing"):
            col = grab(self.src, r"^function colHTML\(key, label, color, grp\)\{.*?^\}",
                       "colHTML")
            self.assertIn("colLive(key, grp)", col)
            self.assertIn("colLive(", self.stand)
            self.assertIn("TERMINAL_WINDOW_MS", self.live)
            self.assertIn("TERMINAL.has(key)", self.live,
                          "끝난 상태의 정의를 손으로 다시 적었다")
        with self.subTest("c3_only_cancelled_is_special"):
            self.assertIn('key === "cancelled"', self.stand)
            self.assertNotIn('key === "done"', self.stand)

if __name__ == "__main__":
    unittest.main()
