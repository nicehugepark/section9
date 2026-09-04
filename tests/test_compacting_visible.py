"""압축 중을 화면에도 (REQ-20260827-065-62x6).

사용자: "로컬 터미널에서 컨텍스트가 컴팩션 되는 중을 대시보드 터미널에서도
인지하고 똑같이 보여줄 수 없나?"

압축이 도는 동안 세션은 한동안 아무 말도 하지 않는다. 로컬 터미널을 보는
사람은 압축 표시를 보고 기다리지만, **대시보드만 보는 사람에게 그 침묵은
고장과 구분되지 않는다.** 서버는 이미 `/api/chat/target` 응답에 `compacting`
을 준다(REQ-065 뒤쪽, 커밋 5197dd5) — 화면이 말하기만 하면 된다.

계약은 다섯이다.

  ① `compacting` 이 참인 동안 "컨텍스트 압축 중"이 보인다.
  ② `live` 를 덮지 않는다 — 압축 중에도 세션은 살아 있다. 상태줄에서 live
     자리를 빼앗지 않고 **그 옆에** 선다.
  ③ 색으로만 가르지 않는다 — 낱말을 함께 적는다 (s9-design 7).
  ④ 정적인 문구는 멈춘 것처럼 읽힌다 — 경과 시간이 **초 단위로** 흐른다
     (대상 감시가 5초 박자라 그 박자로 적으면 오히려 굳어 보인다).
  ⑤ 끝나면 흔적 없이 사라진다. 타임라인을 다시 붙이는 동안에도 살아남는다 —
     압축 줄이 지워지면 압축이 도는 내내 화면이 다시 침묵한다.

실행: python3 tests/ compacting_visible
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class CompactingVisible(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 보인다 ----------

    def test_compacting_visible(self):
        """CompactingVisible 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_server_flag_reaches_the_screen"):
            self.assertIn("termCompactSync(T, !!nt.compacting)", self.src,
                          "서버 신호를 화면에 연결하지 않았다")
            fn = self._fn("termCompactSync")
            self.assertIn("컨텍스트 압축 중", fn, "무슨 일이 도는지 말하지 않는다")
        with self.subTest("it_stands_where_the_silence_happens"):
                self.assertRegex(self.src, r'<div class="ccwaitline cccompact" id="cc-compact"',
                                 "응답 대기 줄과 같은 어휘를 쓰지 않는다")
                # 붙박이 줄이라 타임라인을 비울 때 함께 쓸려 나가면 안 된다
                self.assertIn("n !== w && n !== c", self._fn("termClearOut"),
                              "타임라인을 비울 때 압축 줄까지 지운다")

            # ---------- ② live 를 덮지 않는다 ----------
        with self.subTest("it_does_not_take_over_the_live_badge"):
                st = self._fn("termStatus")
                # live 라벨을 정하는 자리에 compacting 이 끼어들지 않는다
                m = re.search(r'lv\.textContent = [^\n]*', st)
                self.assertIsNotNone(m)
                self.assertNotIn("압축", m.group(0), "live 자리를 압축이 빼앗았다")
                self.assertNotIn("compact", m.group(0))
                self.assertIn('id="cc-cmpk"', self.src, "상태줄에 따로 설 자리가 없다")

            # ---------- ③ 색만으로 가르지 않는다 ----------
        with self.subTest("word_not_only_colour"):
                fn = self._fn("termCompactSync")
                self.assertIn("압축 중", fn, "상태줄에 낱말이 없다")
                css = self._css()
                blk = ";".join(re.findall(r"\.cc(?:compact|cmpk)[^{]*\{([^}]*)\}", css))
                websrc.no_hex(self, blk)
                for v in re.findall(r"(?:background|color|border-color)\s*:\s*([^;}\n]+)", blk):
                    self.assertRegex(v.strip(), r"^var\(--cc-[a-z]+\)$",
                                     "터미널 팔레트 토큰 밖의 색: %s" % v)

            # ---------- ④ 흐른다 ----------
        with self.subTest("elapsed_ticks_every_second"):
                fn = self._fn("termCompactSync")
                self.assertIn("fmtElapsed", fn, "경과를 보여 주지 않는다")
                self.assertRegex(fn, r"setInterval\([\s\S]*?, 1000\)",
                                 "대상 감시 박자(5초)로 적으면 오히려 굳어 보인다")
                self.assertIn("ccspin", fn, "돌고 있다는 표시가 없다")

            # ---------- ⑤ 끝나면 사라진다 ----------
        with self.subTest("it_leaves_no_trace_when_done"):
            fn = self._fn("termCompactSync")
            self.assertRegex(fn, r"if \(!on\)\{[\s\S]*?clearInterval\(T\.compactT\)",
                             "끝나도 타이머가 계속 돈다")
            self.assertRegex(fn, r'box\.hidden = true; box\.innerHTML = ""',
                             "끝나도 줄이 남는다")
            self.assertIn("termCompactSync(T, false)", self._fn("termStatus"),
                          "대상이 사라져도 압축 중이라고 말한다")
        with self.subTest("it_can_be_opened_without_hands"):
            self.assertIn("compacting/.test(location.search)", self._fn("termCompactSync"),
                          "손 없이 압축 상태를 세울 진단 파라미터가 없다")
        with self.subTest("it_does_not_yank_the_reader_around"):
                fn = self._fn("termCompactSync")
                self.assertIn("termAtBottom(out)", fn, "따라갈지 말지를 다른 잣대로 판단한다")
                self.assertRegex(fn, r"if \(wasBottom && out\) out\.scrollTop",
                                 "바닥에 있든 없든 끌어내린다")

            # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _css(self):
        return websrc.css_section(self, self.src, r"/\* -+ 컨텍스트 압축 중")


if __name__ == "__main__":
    unittest.main(verbosity=2)
