"""집힌 카드는 **집혔다고** 말한다 — 얹힌 척하지 않는다 (REQ-20260829-011).

사용자: "카드 테두리와 경과시간, 이어 말하기 위치가 고정이 되어 원래대로
돌아오지 않는 경우가 있다."

`?pick=` 로 그 화면을 그대로 세워 보고 원인을 잡았다. **멈춘 hover 가 아니다.**
`이어 말하기` 로 집어 둔 카드(docTarget)의 모습이다. 셋이 한꺼번에 걸린다 —
잉크 테두리(.card.picked), 늘 떠 있는 손잡이, 그리고 그 손잡이가 밀어낸
경과시각. 그 세 가지가 정확히 사용자가 "고정됐다"고 말한 셋이다.

왜 hover 로 읽히나: 집힘의 손잡이 규칙이 hover 의 규칙과 **글자 그대로 같았다**
(`color:var(--text); text-decoration:underline`). 지속 상태를 찰나 상태의
재료로 그리면, 사람은 마우스를 치웠는데도 안 풀리는 화면으로 읽는다.

그래서 셋을 가른다.

  ① 집힘은 **낱말**로 말한다. 테두리 하나는 모양일 뿐이라 무슨 상태인지
     말하지 못한다 — id 줄에 잉크 낱말 한 마디를 세운다(색면 아님).
  ② 집혔다고 **데이터가 사라지지 않는다.** 경과시각은 카드가 늘 지고 있는
     사실이고, 문서 하나를 집어 둔 내내 그 사실이 없어질 이유가 없다.
  ③ 손잡이는 여전히 **얹거나 포커스했을 때만** 뜬다. 집힘이 손잡이를 붙들지
     않는다 — 붙들면 손잡이와 시각이 그 모서리를 놓고 영영 다툰다.

모서리 한 칸을 손잡이와 시각이 나눠 쓰는 것 자체는 남긴다. 실측했더니 세
가지가 한 줄에 설 자리가 없다(id 97 + 손잡이 56 + 시각 57 ≈ 226px > 카드 줄
199px). 나눌 수 있는 축은 픽셀이 아니라 **시간**이다: 찰나(포인터가 그 카드에
있는 동안)의 교대는 괜찮고, 지속 상태의 점유는 안 된다. 키보드 포커스도
사용자가 스스로 옮기는 찰나라 같은 규칙을 쓴다.

실행: python3 tests/ pick_state_look
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


def rules_for(src, needle):
    """셀렉터에 needle 이 들어간 CSS 규칙 (셀렉터, 본문) 전부."""
    out = []
    for m in re.finditer(r"(?m)^([^\n{}]*\{)", src):
        pass
    for m in re.finditer(r"(?m)^([^\n{}]+)\{([^{}]*)\}", src):
        if needle in m.group(1):
            out.append((m.group(1).strip(), m.group(2)))
    return out


class PickStateLook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # --- ① 집힘은 낱말로 말한다 ---

    def test_pick_state_look(self):
        """PickStateLook 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("picked_says_it_in_words"):
            self.assertIn('class="pkst"', self.src,
                          "집힘을 말하는 낱말이 카드에 없다 — 테두리만으로는 무슨 상태인지 모른다")
            shown = [css for sel, css in rules_for(self.src, ".picked .pkst")]
            self.assertTrue(shown, ".card.picked 에서 그 낱말을 켜는 규칙이 없다")
            hidden = [css for sel, css in rules_for(self.src, ".pkst")
                      if ".picked" not in sel and ":hover" not in sel]
            self.assertTrue(any("display:none" in c.replace(" ", "") for c in hidden),
                            "집지 않은 카드에도 그 낱말이 붙어 있다")
        with self.subTest("the_word_is_ink_not_a_filled_chip"):
            for sel, css in rules_for(self.src, ".pkst"):
                flat = css.replace(" ", "")
                self.assertNotRegex(flat, r"background:(?!none)",
                                    "집힘 표시를 색면으로 그렸다: " + sel)
                self.assertNotIn("border-radius:999px", flat, "알약으로 그렸다: " + sel)
        with self.subTest("the_word_shares_the_row_instead_of_the_corner"):
            m = re.search(r'<div class="id">(.+?)</div>', self.src)
            self.assertIsNotNone(m, "카드 id 줄을 찾지 못했다")
            self.assertIn('class="pkst"', m.group(1),
                          "집힘 낱말이 id 줄 밖에 있다 — 모서리는 이미 시각이 쓴다")
            for sel, css in rules_for(self.src, ".pkst"):
                self.assertNotIn("position:absolute", css.replace(" ", ""),
                                 "낱말을 모서리에 띄웠다: " + sel)
        with self.subTest("the_identifier_never_breaks_across_lines"):
                m = re.search(r'<div class="id">(.+?)</div>', self.src)
                self.assertIsNotNone(m)
                self.assertIn('class="idn"', m.group(1),
                              "식별자가 제 이름의 덩어리로 싸여 있지 않다 — 아무 데서나 끊긴다")
                idn = [css for sel, css in rules_for(self.src, ".idn")]
                self.assertTrue(any("white-space:nowrap" in c.replace(" ", "") for c in idn),
                                "식별자가 줄을 넘어 쪼개질 수 있다")
                row = [css for sel, css in rules_for(self.src, ".card .id")]
                self.assertTrue(any("flex-wrap:wrap" in c.replace(" ", "") for c in row),
                                "id 줄이 넘칠 때 낱말이 아래로 내려갈 길이 없다")

            # --- ② 집혔다고 데이터가 사라지지 않는다 ---
        with self.subTest("picked_does_not_hide_the_clock"):
            for sel, css in rules_for(self.src, ".elapsed"):
                if "visibility:hidden" not in css.replace(" ", ""):
                    continue
                for part in sel.split(","):
                    if ".picked" in part:
                        self.fail("집힌 카드가 경과시각을 지운다: " + part.strip())
        with self.subTest("the_word_and_the_handles_never_share_ink"):
            # **004 의 「비켜서기」는 물러났다** (REQ-20260910-009 3차).
            #
            # 그 규칙(손 얹히면 집힘 낱말을 감춘다)의 까닭은 「손잡이가 칸을
            # 넘쳐 바로 옆의 「대상」을 덮는다」였다 — 낱말이 오른쪽 묶음의
            # 첫 자식이라 손잡이 바로 왼쪽에 있었기 때문이다. 3차에서 낱말을
            # **식별자 바로 뒤**로 옮기고 행위 둘을 각자 제 자리(점의 자리 ·
            # 시각 칸의 떠 있는 묶음)로 보내면서 **덮을 거리가 사라졌다**.
            # 지속 상태를 찰나의 규칙으로 감추던 것이니, 까닭이 사라졌으면
            # 규칙도 물러나는 것이 맞다.
            #
            # 계약은 지우지 않고 **다시 세운다**: 감추는 것으로 겹침을 피하는
            # 대신, **자리로** 겹치지 않게 한다. 집힘 낱말은 흐름 안(식별자
            # 뒤)이고 행위 묶음은 흐름 밖(칸의 오른끝)이라, 어느 얼굴에서도
            # 두 상자가 만나지 않는다. 실제 화소로 겹치지 않는지는
            # tests/test_id_realscale.py 의 the_picked_word_keeps_its_ink 가
            # 스킨·밀도·폭·배율 전수로 잰다.
            gone = [part for sel, css in rules_for(self.src, ".pkst")
                    if "visibility:hidden" in css.replace(" ", "")
                    for part in sel.split(",") if ":hover" in part]
            self.assertEqual(
                [], gone,
                "집힘 낱말이 아직 손 얹힘에 감춰진다 — 덮을 거리가 없어졌으므로 "
                "지속 상태를 찰나의 규칙으로 지울 이유도 없다: %s" % gone)
            act = [c for s2, c in rules_for(self.src, ".idact")
                   if s2.endswith(".card .idact")]
            self.assertTrue(act, "행위 묶음 규칙이 없다")
            flat = act[0].replace(" ", "")
            self.assertIn("position:absolute", flat,
                          "행위 묶음이 흐름 안에 섰다 — 라벨 줄의 폭을 먹고, "
                          "집힘 낱말과 자리를 다투기 시작한다")
            self.assertIn("right:0", flat, "행위 묶음이 칸의 오른끝에 안 맞는다")
        with self.subTest("the_word_comes_back_when_the_hand_leaves"):
            # 지속 상태의 점유가 아니어야 한다 — `.picked` 만으로 지우면 집어 둔
            # 내내 무엇을 집었는지 화면에서 사라진다.
            for sel, css in rules_for(self.src, ".pkst"):
                if "visibility:hidden" not in css.replace(" ", ""):
                    continue
                for part in sel.split(","):
                    self.assertTrue(":hover" in part or ":focus" in part,
                                    "집힘 낱말이 찰나가 아닌 자리에서 지워진다: "
                                    + part.strip())
        with self.subTest("the_clock_still_steps_aside_while_the_pointer_is_there"):
                hit = [part for sel, css in rules_for(self.src, ".elapsed")
                       if "visibility:hidden" in css.replace(" ", "")
                       for part in sel.split(",") if ":hover" in part]
                self.assertTrue(hit, "얹었을 때 시각이 손잡이에게 자리를 비키는 규칙이 사라졌다")

            # --- ③ 집힘이 손잡이를 붙들지 않는다 ---
        with self.subTest("picked_does_not_pin_the_handle_open"):
            for sel, css in rules_for(self.src, ".pickdoc"):
                if "display:block" not in css.replace(" ", ""):
                    continue
                for part in sel.split(","):
                    if ".picked" in part and ":hover" not in part and ":focus" not in part:
                        self.fail("집힌 카드가 손잡이를 상시로 붙들고 있다: " + part.strip())
        with self.subTest("picked_does_not_borrow_the_hover_mark"):
            for sel, css in rules_for(self.src, ".pickdoc"):
                if "text-decoration:underline" not in css.replace(" ", ""):
                    continue
                for part in sel.split(","):
                    if ".picked" in part and ":hover" not in part and ":focus" not in part:
                        self.fail("집힘이 hover 의 밑줄을 쓰고 있다: " + part.strip())
        with self.subTest("picked_does_not_wear_a_border_either"):
            for sel, css in rules_for(self.src, ".card.picked"):
                if ":focus" in sel:
                    continue
                flat = css.replace(" ", "")
                for prop in ("outline:", "border:", "box-shadow:"):
                    self.assertNotIn(prop, flat,
                                     "집힘을 테두리로 그렸다: " + sel)
        with self.subTest("keyboard_focus_still_shows"):
            hit = [css for sel, css in rules_for(self.src, ".card:focus-visible")
                   if "outline:" in css]
            self.assertTrue(hit, "카드의 키보드 포커스 링이 사라졌다")
        with self.subTest("the_word_is_loud_enough_to_find"):
            rules = dict(rules_for(self.src, ".pkst"))
            base = [c for s2, c in rules.items() if s2.endswith(".pkst")]
            self.assertTrue(base, ".pkst 규칙이 없다")
            flat = base[0].replace(" ", "")
            # **두 채널로 갈린다 — 크기가 아니라 무게와 색** (REQ-20260910-009 3차).
            #
            # 종전 값(11.5px·700)의 근거는 「id 줄이 가장 작고 흐리니 한 급 크게,
            # 굵게」였다. 그런데 그 줄은 카드에서 **가장 조용해야 하는 줄**이고,
            # 결과는 「눈에 걸린다」가 아니라 「가장 조용한 줄에서 혼자 소리친다」
            # 였다 (주인 2026-09-10 11:09, s9-design 2절: 강조가 셋 이상이면
            # 강조가 없는 것과 같다).
            #
            # 크기는 줄에 맞추고(10px) 갈리는 일은 **무게와 색**이 맡는다:
            # 이웃은 mono 10px `--faint`(대비 4.69:1) 400 이고 이 낱말은 본문체
            # `--text`(15.6:1) 600 이다 — 굵기 한 급 + 잉크 세 배 차라 열 장
            # 중에서 골라진다(캡처로 확인, REQ 첨부).
            self.assertIn("font-weight:600", flat,
                          "낱말이 주변 글자(400)와 같은 무게다 — 갈릴 채널이 "
                          "색 하나뿐이 된다")
            self.assertIn("color:var(--text)", flat,
                          "낱말이 --text 가 아니다 — 이웃(--faint)과 잉크가 "
                          "안 갈리면 무게만으로는 안 걸린다")
            self.assertRegex(flat, r"font-size:10px",
                             "낱말이 줄의 크기(10px)를 벗어났다 — 한 급 키우면 "
                             "가장 조용해야 할 줄에서 혼자 소리친다")

if __name__ == "__main__":
    unittest.main()
