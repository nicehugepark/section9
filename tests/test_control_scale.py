"""손잡이 눈금은 셋뿐이다 (REQ-20260910-009 S1).

주인 지적 2026-09-10: 「pause 버튼을 보니까 너무 못생겼다」.

⏸ 하나의 문제가 아니었다. 다섯 탭의 모든 손잡이를 실브라우저로 재니 **높이가
16종**(11~37px)이었고, 그중 과녁·모서리·시각 피드백을 갖춘 것은 ⏸ 하나였다.
규칙을 지키는 것이 혼자면 그것이 튄다.

이 시험이 막는 것은 그림이 아니라 **값이 다시 흩어지는 것**이다. 사람 눈으로
16종을 세는 일은 다음 번에 아무도 안 한다.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "web", "css")

# md 가 27 인 것은 실측이 정했다 — 그림 13 + 안여백 6x2 + 테 1x2.
# 28/14 로 옮겼더니 비정수 배율에서 잉크가 원 중심에서 0.5화소 치우쳤다
# (test_hover_realscale, REQ-20260910-009). 값이 셋이라는 것이 규율이지
# 그 값이 4의 배수라는 것이 규율이 아니다.
GRADES = {"--ctl-lg": "36px", "--ctl-md": "27px", "--ctl-sm": "20px"}


def _read(name):
    with open(os.path.join(CSS, name), encoding="utf-8") as f:
        return f.read()


def _strip_comments(css):
    return re.sub(r"/\*[\s\S]*?\*/", "", css)


def _rules(css):
    """(선택자, 선언) 목록 — 주석은 걷고 @media 안쪽도 그대로 훑는다."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _strip_comments(css)):
        sel, dec = m.group(1).strip(), m.group(2).strip()
        if sel.startswith("@") or not dec:
            continue
        out.append((" ".join(sel.split()), dec))
    return out


class TheHandleScaleHasThreeGrades(unittest.TestCase):
    def test_the_three_values_live_in_one_place(self):
        """값은 tokens.css 한 곳에 있고 셋이다."""
        tok = _read("tokens.css")
        for name, val in GRADES.items():
            with self.subTest(name):
                self.assertRegex(
                    tok, re.escape(name) + r":\s*" + re.escape(val),
                    "%s 가 tokens.css 에 %s 로 서 있지 않다 — 손잡이 눈금의 "
                    "값은 토큰이 소유한다" % (name, val))

    def test_no_skin_redefines_a_grade(self):
        """스킨은 색·모서리·면·깊이를 말하고 **크기는 말하지 않는다**.

        지금까지 높이가 16종이 된 길이 이것이다 — 스킨마다 제 값을 다시 적었다.
        """
        for fn in sorted(os.listdir(CSS)):
            if not fn.endswith(".css"):
                continue
            for sel, dec in _rules(_read(fn)):
                if "--ctl-" not in dec:
                    continue
                if not re.search(r"--ctl-(lg|md|sm)(-fs)?\s*:", dec):
                    continue          # 값을 **쓰는** 것은 자유다
                with self.subTest(fn + " :: " + sel[:60]):
                    self.assertNotIn(
                        "[data-skin", sel,
                        "스킨이 손잡이 눈금을 다시 정한다 (%s) — 스킨은 재질을 "
                        "바꾸고 크기는 바꾸지 않는다" % fn)
                    self.assertNotIn(
                        "[data-density", sel,
                        "밀도가 손잡이 눈금을 다시 정한다 (%s) — 밀도는 여백을 "
                        "줄이는 축이지 과녁을 깎는 축이 아니다" % fn)

    def test_every_handle_rule_names_a_grade(self):
        """control.css 의 모든 과녁 규칙은 날 px 가 아니라 토큰을 쓴다."""
        for sel, dec in _rules(_read("control.css")):
            for prop in ("min-height", "height"):
                m = re.search(prop + r"\s*:\s*([^;]+)", dec)
                if not m:
                    continue
                v = m.group(1).strip()
                with self.subTest(sel[:60] + " " + prop):
                    self.assertRegex(
                        v, r"var\(--ctl-(lg|md|sm)\)",
                        "%s 가 날 값 %r 을 적었다 — 눈금은 토큰 이름으로만 "
                        "부른다" % (sel, v))

    def test_the_glyph_handle_uses_the_middle_grade(self):
        """⏸/▶ 의 과녁도 사전 안에 있다 — 혼자 서 있던 그 손잡이다.

        칠을 원 안에 가두는 mask 와 한 몸이라 규칙 자체는 actions.css 에 남지만,
        **값은 사전에서 온다**.
        """
        hit = [d for s, d in _rules(_read("actions.css"))
               if s.endswith(".acts button.deed.ico")]
        self.assertTrue(hit, "글리프 손잡이의 과녁 규칙이 없다")
        self.assertIn("min-width:var(--ctl-md)", hit[0])
        self.assertIn("min-height:var(--ctl-md)", hit[0])

    def test_the_target_is_not_the_paint_for_small_handles(self):
        """줄 안의 글자 손잡이는 **겹판으로만** 과녁을 얻는다.

        상자를 20px 로 키우면 그 줄이 통째로 자란다 — ⏸ 가 12px 줄을 26px 로
        부풀린 그 병이다. 겹판은 흐름 밖(absolute)이라 줄 높이를 안 건드린다.
        """
        for sel, dec in _rules(_read("control.css")):
            if "var(--ctl-sm)" not in dec:
                continue
            with self.subTest(sel[:70]):
                self.assertIn("::after", sel,
                              "sm 급이 겹판이 아닌 자리에서 쓰였다 — 상자를 "
                              "키우면 줄이 자란다")
                self.assertIn("position:absolute", dec,
                              "겹판이 흐름 안에 있다")


class TheGlyphInkIsLighterThanBefore(unittest.TestCase):
    """⏸ 는 줄에서 가장 무거운 것이 아니다 (REQ-20260910-009 P1)."""

    def setUp(self):
        with open(os.path.join(ROOT, "web", "app", "card.js"),
                  encoding="utf-8") as f:
            self.src = f.read()

    def _glyph(self, name):
        m = re.search(r"const %s = ([\s\S]*?;)" % name, self.src)
        self.assertIsNotNone(m, name)
        return m.group(1)

    def test_the_stop_mark_is_a_square_not_a_player_glyph(self):
        """멈춤 마크는 **채운 사각**이다 — 재생기의 두 막대가 아니다.

        REQ-20260910-009 2차 반려. `||` 는 재생기의 「잠시 멈춤」이라 이 손잡이가
        하는 일(`STOP_KIND` 셋: 거기서 끝난다 · 중단하라고 전한다 · 하던 일은
        마치고 멈춘다)과 뜻이 다르다. 셋의 공통은 「잠시」가 아니라 「멎게
        한다」이고, 그 마크는 재생기에서도 이 제품의 점 어휘에서도 사각이다.
        """
        stop = self._glyph("GLYPH_STOP")
        rects = re.findall(r'width="(\d+)" height="(\d+)"', stop)
        self.assertEqual(len(rects), 1,
                         "멈춤 마크가 사각 하나가 아니다 — 막대 둘로 돌아갔나")
        w, h = int(rects[0][0]), int(rects[0][1])
        self.assertEqual(w, h, "멈춤 마크가 정사각이 아니다 (%dx%d)" % (w, h))
        self.assertNotIn("path", stop, "멈춤 마크에 곡선/삼각이 섞였다")

    def test_the_stop_mark_sits_dead_centre(self):
        """사각은 상자 한가운데다 — 사방 틈이 같고 좌표는 정수다.

        비정수 배율에서 반올림이 갈릴 자리를 만들지 않는다(s9-design 배율 불변).
        """
        stop = self._glyph("GLYPH_STOP")
        box = int(re.search(r'viewBox="0 0 (\d+)', stop).group(1))
        x = int(re.search(r'x="(\d+)"', stop).group(1))
        y = int(re.search(r'y="(\d+)"', stop).group(1))
        w = int(re.search(r'width="(\d+)"', stop).group(1))
        h = int(re.search(r'height="(\d+)"', stop).group(1))
        self.assertEqual(x, box - x - w,
                         "좌우 틈이 다르다 (왼 %d · 오른 %d)" % (x, box - x - w))
        self.assertEqual(y, box - y - h,
                         "상하 틈이 다르다 (위 %d · 아래 %d)" % (y, box - y - h))

    def test_the_two_faces_weigh_the_same(self):
        """▶ 와 ■ 의 잉크가 ±10% 안이다 — 상태 배타의 전제다.

        「한 축의 두 방향, 하나만 참」을 그림으로 약속하려면 두 그림의 무게가
        같아야 한다 (REQ-20260830-042).
        """
        stop = self._glyph("GLYPH_STOP")
        w = int(re.search(r'width="(\d+)"', stop).group(1))
        h = int(re.search(r'height="(\d+)"', stop).group(1))
        pink = w * h
        play = self._glyph("GLYPH_PLAY")
        d = re.search(r'd="([^"]+)"', play).group(1)
        pts = re.findall(r"([\d.]+) ([\d.]+)", d)
        self.assertEqual(len(pts), 3, "▶ 가 삼각형이 아니다")
        (x1, y1), (x2, y2), (x3, y3) = [(float(a), float(b)) for a, b in pts]
        yink = abs(x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)) / 2
        self.assertLessEqual(
            abs(yink - pink) / pink, 0.10,
            "▶ %.1fpx^2 와 ■ %dpx^2 의 무게가 10%% 넘게 다르다" % (yink, pink))

    def test_the_resting_ink_is_not_darker_than_the_line(self):
        """쉬는 얼굴의 잉크는 같은 줄의 식별자와 한 층(--faint)이다."""
        with open(os.path.join(CSS, "actions.css"), encoding="utf-8") as f:
            css = f.read()
        off = [d for s, d in _rules(css)
               if "deed.ico" in s and ":not(:hover)" in s]
        self.assertTrue(off, "쉬는 얼굴의 규칙이 없다")
        self.assertIn("color:var(--faint)", off[0],
                      "쉬는 얼굴이 --muted 다 — 줄에서 가장 조용해야 할 자리에 "
                      "가장 진한 덩어리가 선다")


if __name__ == "__main__":
    unittest.main()
