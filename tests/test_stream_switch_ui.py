"""스트림 스위치를 화면에 (REQ-20260828-013-62x6).

사용자(08:36 이어서): "세션 껐다켜기를 말한 게 아니라 스트림을 세션에서 사용할지
말지에 대한 기능 말한 것."

화면은 그 값을 **읽기만** 했다 — `streamOn()` 이 whoami 의 `stream_mirror` 를 보고
Stream 탭을 감추거나 보였다. 끄고 켜는 자리는 없었고, 오히려 꺼진 화면에 이렇게
적혀 있었다: "켜려면 터미널에서 s9 user config <이름> stream_mirror on".
**대시보드로 일하는 사람에게 터미널로 가라고 말하는 화면**이었다.

계약은 여섯이다.

  ① 개인설정(내 계정)에 켜고 끄는 스위치와 보관 기간이 있다.
  ② **바꾸면 바로 저장된다.** 저장 버튼을 따로 두면 "켰는데 왜 안 켜지지"가
     생긴다 — 디스플레이 설정이 이미 같은 손버릇을 쓴다.
  ③ 저장한 뒤 신원을 다시 받아 Stream 탭을 그 자리에서 올리거나 내린다. 껐는데
     탭이 남아 있으면 설정이 안 먹은 것으로 읽힌다.
  ④ 끄면 보관 기간 줄을 통째로 한 단계 물린다 — 칸만 잠그면 옆의 설명이 아직 쓸
     수 있는 것처럼 남는다.
  ⑤ 잘못 적은 보관 기간은 비난하지 않고 예를 준다. 빈 값·0 의 뜻을 미리 말한다.
  ⑥ 손 없이 눌러 볼 수 있고(`?stdbg=off|on`), 그 진단은 **끝나고 되돌린다** —
     진단이 사용자의 설정을 바꿔 놓고 끝나면 안 된다.

실행: python3 tests/ stream_switch_ui
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class StreamSwitchUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 자리가 있다 ----------

    def test_stream_switch_u_i(self):
        """StreamSwitchUI 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_switch_exists_in_my_account"):
                blk = self._block()
                self.assertIn('id="cf-stream"', blk, "켜고 끄는 스위치가 없다")
                self.assertIn('id="cf-streamdays"', blk, "보관 기간 칸이 없다")
                self.assertIn("켬 — 대화를 남깁니다", blk, "선택지가 무엇을 뜻하는지 말하지 않는다")
                self.assertIn("끔 — 남기지 않습니다", blk)
                # 기타 설정 뭉치에 섞여 JSON 으로 보이면 스위치가 아니다
                self.assertIn('"stream_mirror","stream_keep_days"', self.src,
                              "스트림 키가 '기타' 뭉치에 그대로 남는다")

            # ---------- ② 바꾸면 바로 저장 ----------
        with self.subTest("it_saves_the_moment_you_change_it"):
                self.assertIn('smSel.addEventListener("change"', self.src, "고른 것이 저장되지 않는다")
                self.assertIn('smDays.addEventListener("change"', self.src, "보관 기간이 저장되지 않는다")
                fn = self._fn("saveStream")
                self.assertIn('postJSONRaw("/api/user/config"', fn, "서버에 저장하지 않는다")
                self.assertIn("바꾸면 바로 저장됩니다", self.src, "바로 저장된다는 것을 말하지 않는다")
                # 진행·실패를 말없이 삼키지 않는다
                self.assertIn('"저장하는 중…"', fn, "저장 중인지 알 수 없다")
                self.assertIn('"secmsg bad"', fn, "실패를 알리지 않는다")

            # ---------- ③ 탭이 그 자리에서 따라온다 ----------
        with self.subTest("the_tab_follows_immediately"):
                fn = self._fn("saveStream")
                # 신원을 받는 자리는 하나다 (REQ-20260828-039) — 직접 fetch 하면 그
                # 한 번의 실패로 탭이 옛 설정에 묶인다. loadWhoami 는 물러섰다 다시 받는다.
                self.assertIn("loadWhoami()", fn, "신원을 다시 받지 않는다")
                self.assertIn("applyStreamVisibility()", fn, "탭이 그대로 남는다")
                self.assertGreater(fn.index("applyStreamVisibility()"),
                                   fn.index("loadWhoami()"),
                                   "옛 신원으로 탭을 다시 그린다")

            # ---------- ④ 끄면 보관 기간 줄이 물러난다 ----------
        with self.subTest("keep_days_recedes_when_recording_is_off"):
                blk = self.src[self.src.index("const smSyncDays ="):]
                blk = blk[:blk.index("async function saveStream")]
                self.assertIn('smDays.disabled = off', blk, "끈 뒤에도 보관 기간을 물어본다")
                self.assertIn('classList.toggle("rowoff", off)', blk, "줄 전체가 물러나지 않는다")
                self.assertIn("tr.rowoff td{opacity:", self.src, "물러나는 표현이 없다")
                # 색이 아니라 명도로 — 색면 금지
                css = self.src[self.src.index("tr.rowoff td{"):]
                self.assertNotIn("background", css[:css.index("}")], "물러나는 데 색면을 쓴다")

            # ---------- ⑤ 문구 ----------
        with self.subTest("the_words_explain_the_edges"):
                blk = self._block()
                self.assertIn("비우면 7일 · 0 이면 지우지 않습니다", blk, "빈 값·0 의 뜻이 없다")
                self.assertIn("이미 남은 기록은 지우지 않습니다", blk,
                              "끄면 기록이 지워지는 줄 알게 된다")
                self.assertIn("날짜 수만 적어 주세요. 예: 7", self.src,
                              "잘못 적었을 때 예를 주지 않는다")
                # 꺼진 Stream 화면이 터미널로 보내지 않는다 (이 요청의 사유)
                off = self.src[self.src.index("대화 기록이 꺼져 있습니다"):]
                off = off[:off.index("return;")]
                self.assertNotIn("s9 user config", off, "꺼진 화면이 여전히 터미널로 보낸다")
                self.assertIn("설정에서 켜기", off, "켜러 갈 손잡이가 없다")

            # ---------- ⑥ 손 없이 눌러 보고, 되돌린다 ----------
        with self.subTest("it_can_be_flipped_without_hands_and_restored"):
                self.assertIn("[?&]stdbg=", self.src, "손 없이 눌러 볼 길이 없다")
                dbg = self.src[self.src.index("if (smSel && /[?&]stdbg=/"):]
                dbg = dbg[:dbg.index("/* ?secdbg")]
                self.assertIn('smSel.dispatchEvent(new Event("change"', dbg,
                              "진짜 손짓을 태우지 않는다")
                self.assertIn("Stream 탭", dbg, "탭이 따라왔는지 보지 않는다")
                self.assertIn("되돌린다", dbg, "진단이 설정을 바꿔 놓고 끝난다")
                self.assertIn("if (was !== want){", dbg, "되돌리는 코드가 없다")

            # ---------- helpers ----------

    def _block(self):
        i = self.src.index('<div class="cfg-h">대화 기록')
        j = self.src.index('<div class="cfg-h">개인 선호')
        return self.src[i:j]

    def _fn(self, name):
        m = re.search(r"(async )?function %s\([^)]*\)\{[\s\S]*?\n  \}" % name, self.src)
        return m.group(0) if m else ""


if __name__ == "__main__":
    unittest.main(verbosity=2)
