"""머리글의 눈이 움직이고, 움직이지 않아야 할 때는 멈춘다 (REQ-20260914-001-62x6).

주인(2026-09-14 10:24): 「저 타치코마 눈을 움직이게 할 수는 없나? 그냥 흰 원이
아니라 정말 타치코마의 눈처럼 입체감 있게 움직였으면」.

움직임은 눈으로 보고 판정하는 것이라 이 파일이 재는 것은 **그림이 아니라 계약**
다섯이다 — 눈이 문서의 것인가 · 사람의 설정과 화면 상태를 보는가 · 상한이 코드에
있는가 · 조각 목록에 제자리로 서 있는가 · 정지 파일도 같은 얼굴인가.

  N1 머리글 마크는 인라인이고, 그 점 셋은 파비콘의 점 셋과 **같은 값**이다.
     (`<img>` 안의 요소는 문서의 것이 아니라 붙잡아 움직일 수 없다.)
  N2 mark.js 가 `prefers-reduced-motion`·`document.hidden` 을 둘 다 보고,
     안 보이는 창에서는 타이머를 끈다.
  N3 이동 상한이 코드에 있다 — 렌즈 반지름의 20%, 그리고 그 상한을 넘는 값이
     들어와도 잘라 낸다. 같은 시험이 「움직이는 것은 transform 뿐」도 함께 본다
     (cx/cy 를 고치면 그림이 매번 다시 계산되고, 자리를 읽으면 레이아웃이 다시 돈다).
  N4 조각 목록에 있고 **마지막이 아니다** — 마지막 조각은 화면이 다 섰다는 표식을
     세우는 자리라 그것을 빼앗으면 「조각을 못 받았다」 알림이 멀쩡한 화면을 지운다.
  N5 정지 파일 셋(mark·favicon·logo)의 렌즈에 음영(radialGradient)과 반사가 있고,
     점 셋이 주인이 고른 비율(지름의 8~14% · 무게중심 13~17% 아래 · 정삼각)을 지킨다.

실행: python3 tests/ mark_motion
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webasset  # noqa: E402

WEB = os.path.normpath(os.path.join(HERE, "..", "web"))
DOT = re.compile(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" fill="#141518"/>')
DOME = re.compile(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" fill="url\(#s9dome\)"/>')


def read(*parts):
    with open(os.path.join(WEB, *parts), encoding="utf-8") as f:
        return f.read()


def dots(src):
    """그 그림의 잉크 점 셋 — (cx, cy, r). 잉크로 칠하는 원은 렌즈의 테도 있으므로
    **마지막 셋**만 센다(눈은 언제나 맨 위에 얹힌다)."""
    return [tuple(round(float(v), 2) for v in m) for m in DOT.findall(src)][-3:]


class TheEyeBelongsToThePage(unittest.TestCase):
    """N1. 머리글 마크는 인라인이고 탭과 같은 얼굴이다."""

    def test_n1_the_header_mark_is_inline_and_shares_the_tab_face(self):
        shell = read("index.html")
        brand = re.search(r'<div class="brand">(.*?)section9', shell, re.S)
        self.assertIsNotNone(brand, ".brand 가 없다")
        mark = brand.group(1)
        self.assertIn('<svg class="mark"', mark, "머리글 마크가 인라인 svg 가 아니다")
        self.assertIn('<g class="pupil">', mark,
                      "점 셋이 g.pupil 로 묶여 있지 않다 — 묶이지 않으면 못 움직인다")
        self.assertNotIn('<img class="mark"', mark,
                         "그림 파일 마크가 남아 있다 — 한 자리에 얼굴이 둘이다")
        self.assertEqual(dots(mark), dots(read("assets", "favicon.svg")),
                         "머리글의 점 셋과 탭 파비콘의 점 셋이 다르다 "
                         "— 한 제품이 자리마다 다른 얼굴을 보인다")


class TheMotionRespectsThePerson(unittest.TestCase):
    """N2. 사람의 설정과 화면 상태를 본다."""

    def test_n2_reduced_motion_and_a_hidden_tab_both_stop_it(self):
        src = read("app", "mark.js")
        self.assertIn("prefers-reduced-motion: reduce", src,
                      "움직임 줄이기 설정을 보지 않는다")
        self.assertIn("document.hidden", src, "탭이 보이는지를 보지 않는다")
        self.assertIn('"visibilitychange"', src,
                      "탭이 가려지는 순간을 안 듣는다 — 안 보이는 창에서 타이머가 계속 돈다")
        self.assertIn("clearTimeout", src, "걸어 둔 타이머를 끄는 곳이 없다")
        # 규칙 쪽도 같은 말을 해야 한 쪽이 늦게 와도 안 흔들린다
        css = read("css", "header.css")
        self.assertIn("prefers-reduced-motion:reduce", css.replace(" ", ""),
                      "header.css 가 움직임 줄이기에서 눈을 세우지 않는다")


class TheMoveHasACeiling(unittest.TestCase):
    """N3. 이동 상한이 코드에 있고, 움직이는 것은 transform 뿐이다."""

    def test_n3_the_offset_is_capped_and_only_transform_moves(self):
        src = read("app", "mark.js")
        m = re.search(r"var\s+LENS_R\s*=\s*([\d.]+)", src)
        self.assertIsNotNone(m, "렌즈 반지름이 상수로 없다")
        cap = re.search(r"var\s+MAX\s*=\s*LENS_R\s*\*\s*([\d.]+)", src)
        self.assertIsNotNone(cap, "이동 상한이 반지름에서 나오지 않는다")
        self.assertLessEqual(float(cap.group(1)), 0.2,
                             "이동 상한이 반지름의 20% 를 넘는다 — 점 셋이 렌즈 밖으로 밀린다")
        self.assertIn("if (d > MAX)", src,
                      "상한을 넘는 값을 잘라 내지 않는다 — 상수만 있고 지키는 곳이 없다")
        self.assertIn("pupil.style.transform", src, "transform 으로 옮기지 않는다")
        for banned in ('setAttribute("cx"', 'setAttribute("cy"',
                       "style.left", "style.top"):
            self.assertNotIn(banned, src,
                             "%s 로 옮긴다 — 그림·배치가 매번 다시 계산된다" % banned)
        self.assertEqual(src.count("svg.getBoundingClientRect()"), 1,
                         "자리를 여러 곳에서 읽는다 — 포인터를 따라가며 읽으면 "
                         "움직일 때마다 레이아웃이 다시 돈다")


class TheScriptStandsInLine(unittest.TestCase):
    """N4. 조각 목록에 있고 마지막은 아니다."""

    def test_n4_mark_js_is_in_the_manifest_but_not_last(self):
        _, app = webasset.parts()
        self.assertIn("mark.js", app,
                      "mark.js 가 조각 목록에 없다 — 아무도 안 부르는 조각은 화면을 못 바꾼다")
        self.assertNotEqual(app[-1], "mark.js",
                            "mark.js 가 마지막 조각이다 — 그 자리는 화면이 다 섰다는 "
                            "표식을 세우는 자리다")


class TheStillFacesHaveDepth(unittest.TestCase):
    """N5. 정지 파일에도 입체감이 있고, 점 셋은 주인이 고른 **비율**을 지킨다.

    절대 좌표로 못박지 않는 까닭: 마크는 이제 이름 붙은 버전으로 갈아 끼운다
    (REQ-20260914-002-62x6). 버전이 바뀌면 좌표는 달라지지만 **얼굴의 비율**은
    그대로여야 한다 — 그것이 주인이 고른 것이다. 그래서 좌표가 아니라 비율을 잰다.
      · 점 지름은 돔 지름의 8~14% (큰 새김 8% · 작은 새김 13%)
      · 점 셋은 정삼각이고, 무게중심이 돔 지름의 13~17% 만큼 아래
    """

    def face(self, src):
        """첫 렌즈와 **그 뒤에 오는** 점 셋을 잰다 — logo.svg 는 렌즈가 셋이라
        (타일 하나 · o 와 9 의 속 둘) 맨 뒤의 점을 집으면 9 의 눈을 타일에 견주게 된다."""
        m = DOME.search(src)
        self.assertIsNotNone(m, "돔 음영을 쓰는 렌즈가 없다")
        cx, cy, R = (float(v) for v in m.groups())
        d = [tuple(round(float(v), 2) for v in g)
             for g in DOT.findall(src[m.end():])][:3]
        self.assertEqual(len(d), 3, "점이 셋이 아니다")
        dd = R * 2
        self.assertTrue(0.08 <= d[0][2] * 2 / dd <= 0.14,
                        "점 지름이 돔 지름의 8~14%% 밖이다: %.3f" % (d[0][2] * 2 / dd))
        side = abs(d[1][0] - d[0][0])
        self.assertAlmostEqual((d[2][1] - d[0][1]) / side, 0.866, delta=0.02,
                               msg="점 셋이 정삼각이 아니다")
        drop = (sum(p[1] for p in d) / 3 - cy) / dd
        self.assertTrue(0.13 <= drop <= 0.17,
                        "점 무리의 중심이 돔 지름의 13~17%% 아래가 아니다: %.3f" % drop)

    def test_n5_the_lens_is_shaded_and_the_three_dots_keep_their_ratios(self):
        for name in ("mark.svg", "favicon.svg", "logo.svg"):
            with self.subTest(name):
                src = read("assets", name)
                self.assertIn("<radialGradient", src, "%s 의 렌즈에 음영이 없다" % name)
                self.assertIn("url(#s9dome)", src, "%s 가 돔 음영을 안 쓴다" % name)
                self.assertIn("url(#s9lit)", src, "%s 에 반사가 없다" % name)
                self.face(src)
        # 머리글의 얼굴도 같은 자로 잰다 — 탭·가이드와 한 얼굴이어야 한다
        brand = re.search(r'<div class="brand">(.*?)</svg>', read("index.html"), re.S)
        self.face(brand.group(1) + "</svg>")


if __name__ == "__main__":
    unittest.main(verbosity=2)
