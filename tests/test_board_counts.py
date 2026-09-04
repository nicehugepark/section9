"""열 머리 숫자와 띠 숫자 (REQ-20260827-070-62x6).

**2차 — 띠를 내렸다. 계약을 다시 썼다.**

1차는 띠와 열의 셈을 같은 집합에 맞췄다. 그랬더니 사용자가 되물었다:
"컬럼 헤더랑 동일한 기능인데 굳이 보여줘야하는게 맞나?? 디자이너 의견 줘."

맞는 물음이었고, 답은 "아니오"다.
  · 셈을 맞춘 뒤로 **같은 집합을 같은 낱말로 두 번** 센다.
  · 분포를 한눈에 보는 일도 열 머리가 그대로 한다 — 여섯 열 머리는 이미 같은
    높이에 가로로 늘어서 있어, 띠는 그 줄을 되풀이하고 있었다.
  · 띠의 필터는 보드에서 할 일이 없었다: 눌러도 나머지 네 열이 "…없음" 으로
    비어 걸기 전보다 나쁜 화면이 됐다. 상태로 가르는 일은 열이 이미 한다.
  · 열을 깊이 보는 일은 `+ N개 더 보기` 가 맡고 있다.

그래서 아래 계약 ①②는 **열 머리 한 곳**에 대한 것으로 좁아졌고, ③(띠는 컨트롤로
남긴다)은 뒤집혔다. 지우지 않고 다시 쓴 이유가 이것이다 — 1차의 판단과 그것이
왜 뒤집혔는지가 함께 남아야 다음 사람이 같은 자리를 왕복하지 않는다.

--- 1차 기록 ---

사용자: "cancelled 카운트 숫자가 다르다."

전수로 세어 보면 **계산은 틀리지 않았다**. 상단 띠는 전체를 세고(cancelled 4),
열 머리는 그 열에 실제로 있는 것만 센다(3). 차이는 REQ-20260827-057 의 하루
자르기다 — 끝난 열에서는 하루가 지난 요청을 내린다.

그래도 **같은 낱말에 다른 수**가 보이면 사람은 고장으로 읽는다. 그리고 그게
맞다: 띠는 열을 여닫는 **필터**라, 띠의 수는 눌렀을 때 나올 수와 같아야 한다.
그래서 세는 집합을 하나로 만든다 — 보드가 실제로 담는 것.

지금 계약은 셋이다.

  ① 열 머리는 **그 열이 실제로 담는 것**을 센다 — 끝난 상태는 하루 자르기를
     거친 것만.
  ② **한 숫자는 한 곳에만.** 같은 집합을 세는 두 번째 자리를 두지 않는다.
  ③ `3/4` 같은 슬래시 표기도, 설명 문구도 붙이지 않는다. 두 수가 다르다는 것을
     설명하는 표기는 같은 짐을 그대로 진다.

실행: python3 tests/ board_counts
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class BoardCounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.fn = cls._grab(cls.src, "renderBoard")

    @staticmethod
    def _grab(src, name):
        m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
        assert m, name
        return m.group(0)

    # ---------- ① 같은 집합에서 센다 ----------

    def test_board_counts(self):
        """BoardCounts 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_column_head_counts_what_the_column_holds"):
                col = self._grab(self.src, "colHTML")
                live = re.search(r"const colLive = [^;]*;", self.src)
                self.assertTrue(live, "colLive 를 못 찾았다")
                self.assertIn("colLive(key, grp)", col, "하루 자르기를 적용하지 않는다")
                self.assertIn("TERMINAL_WINDOW_MS", live.group(0))
                self.assertIn("termAt(r)", live.group(0),
                              "카드가 쓰는 그 시각으로 자르지 않는다")
                self.assertIn('<span class="n">${live.length}</span>', col,
                              "열 머리가 자르기 전 수를 보여 준다")

            # ---------- ② 한 숫자는 한 곳에만 ----------
        with self.subTest("the_count_is_not_repeated_anywhere_else"):
                # 화면 어디서도 다시 그리지 않는다 — renderBoard 안만 보면 다른 함수로
                # 옮겨 심는 것을 놓친다. (CSS 의 `.stats{...}` 는 이 검사에 걸리지 않는다:
                # 죽은 채로 남겨 뒀고, 되살리는 값이 싸도록 일부러 지우지 않았다.)
                self.assertNotIn('class="stats"', self.src, "상태 띠가 아직 그려진다")
                self.assertNotIn("data-statf", self.fn, "띠의 필터가 아직 붙어 있다")
                self.assertNotIn("__statusFilter", self.src,
                                 "쓰이지 않는 필터 상태가 남아 있다")
                self.assertNotIn("전체 요청", self.fn, "합계를 두 번째로 세는 자리가 남았다")

            # ---------- ③ 설명으로 메우지 않는다 ----------
        with self.subTest("no_slash_notation_and_no_excuse_line"):
            col = self._grab(self.src, "colHTML")
            head = col[col.index('<h2>'):col.index('</h2>')]
            self.assertNotIn("/${", head, "두 수를 나란히 적는 표기가 남아 있다")
            for word in ("하루", "제외", "기준", "가려", "숨긴"):
                self.assertNotIn(word, head, "열 머리에 변명하는 문구를 붙였다: %s" % word)

if __name__ == "__main__":
    unittest.main(verbosity=2)
