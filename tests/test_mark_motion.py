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
  N3 눈은 렌즈 안에서만 움직인다 — 상한까지 밀어도 점 셋이 테에 닿지 않는 것을
     기하로 잰다. 「움직이는 것은 transform 뿐」도 여기서 본다.
  N4 조각 목록에 있고 **마지막이 아니다** — 마지막 조각은 화면이 다 섰다는 표식을
     세우는 자리라 그것을 빼앗으면 「조각을 못 받았다」 알림이 멀쩡한 화면을 지운다.
  N7 구르는 동안 세 점이 같은 쪽으로 움직인다 — 앞선 점만 뒤로 도는 자리가
     지나감 밖에 있는지, 축이 도는 꼴이 직각으로 갈라 놓지 않는지, 밀어낸 끝에서
     세 점이 전부 테 밖인지를 조각의 실제 좌표로 푼다.
  N6 재주 표가 온전하다 — 합쳐 **80 을 넘고**(구르기만 마흔 넘게, 그리고 뽑는 몫의
     30퍼센트 이상), 점이 따로 노는
     재주는 **10%% 이하**이며, 비슷한 것을 표에 두 줄로 두지 않으며
     항목마다 넷이 있으며, 시계가 가드(움직임 줄이기·안 보이는 탭)를 보고 커서를
     좇는 중에는 끼어들지 않는다. 붓이 제 손으로 돔에서 자르는 것도 여기서 본다.
     점 셋은 **하나의 시선**이다 — 제각각 기어 다니면 장난이 아니라 벌레로 읽힌다
     (주인 2026-09-14 15:05).
  N5 정지 파일 셋(mark·favicon·logo)의 렌즈에 음영(radialGradient)과 반사가 있고,
     점 셋이 주인이 고른 비율(지름의 8~14% · 무게중심 13~17% 아래 · 정삼각)을 지킨다.

실행: python3 tests/ mark_motion
"""
import math
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webasset  # noqa: E402

WEB = os.path.normpath(os.path.join(HERE, "..", "web"))
DOT = re.compile(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" fill="#(?:141518|000000)"/>')
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
    """N3. 눈은 렌즈 안에서만 움직이고, 커서는 거리로 자르지 않는다.

    상한을 숫자로만 재면 렌즈가 커지거나 점이 굵어질 때 그 숫자가 거짓말을 한다.
    그래서 **기하로** 잰다 — 상한만큼 밀었을 때 점 셋의 바깥 테두리가 돔 안에
    남는가. 아래쪽에 따로 상한이 있는 까닭도 이 계산에서 나온다: 점 무리가 이미
    중심보다 아래에 앉아 있어, 옆으로 갈 만큼 아래로 가면 테를 파고든다.
    """

    def consts(self, src):
        """`var 이름 = 숫자` 또는 `var 이름 = 앞선이름 * 숫자` 를 읽는다."""
        out = {}
        for key in ("LENS_R", "MAX", "MAX_DOWN", "NEAR_R", "NEAR_MIN"):
            m = re.search(r"var\s+%s\s*=\s*(?:([A-Z_]+)\s*\*\s*)?([\d.]+)" % key, src)
            self.assertIsNotNone(m, "%s 가 상수로 없다" % key)
            v = float(m.group(2))
            if m.group(1):
                self.assertIn(m.group(1), out, "%s 가 아직 없는 값을 곱한다" % key)
                v *= out[m.group(1)]
            out[key] = v
        return out

    def test_n3_the_offset_is_capped_and_only_transform_moves(self):
        src = read("app", "mark.js")
        c = self.consts(src)
        self.assertTrue(0.2 < c["MAX"] / c["LENS_R"] <= 0.35,
                        "이동 상한이 돔 반지름의 20~35%% 밖이다: %.3f"
                        % (c["MAX"] / c["LENS_R"]))
        self.assertLess(c["MAX_DOWN"], c["MAX"],
                        "아래쪽 상한이 옆·위와 같다 — 점 무리가 이미 아래에 앉아 있다")
        self.assertGreater(c["NEAR_MIN"], 0,
                           "반경 가장자리에서의 세기(NEAR_MIN)가 0 이다 — 들어오는 "
                           "순간 눈이 튄다")

        # 상한까지 밀어도 점 셋이 돔 안에 남는가 — 옆·위·아래 셋을 실제로 재 본다
        head = re.search(r'<div class="brand">(.*?)</svg>', read("index.html"), re.S)
        snippet = head.group(1) + "</svg>"
        m = DOME.search(snippet)
        cx, cy, R = (float(v) for v in m.groups())
        dots3 = [tuple(float(v) for v in g) for g in DOT.findall(snippet[m.end():])][:3]
        self.assertEqual(len(dots3), 3)
        for name, ox, oy in (("오른쪽", c["MAX"], 0), ("위", 0, -c["MAX"]),
                             ("아래", 0, c["MAX_DOWN"])):
            for dx, dy, r in dots3:
                reach = math.hypot(dx + ox - cx, dy + oy - cy) + r
                with self.subTest(name):
                    self.assertLess(reach, R - 1.0,
                                    "%s 끝까지 밀면 점이 테에 닿는다 (%.2f / %.2f)"
                                    % (name, reach, R))

        self.assertIn("el.style.transform = tr", src, "transform 으로 옮기지 않는다")
        self.assertIn("css(pupil,", src, "무리를 옮기는 붓이 없다")
        for banned in ('setAttribute("cx"', 'setAttribute("cy"',
                       "style.left", "style.top"):
            self.assertNotIn(banned, src,
                             "%s 로 옮긴다 — 그림·배치가 매번 다시 계산된다" % banned)
        self.assertEqual(src.count("svg.getBoundingClientRect()"), 1,
                         "자리를 여러 곳에서 읽는다 — 커서를 좇으며 읽으면 "
                         "움직일 때마다 레이아웃이 다시 돈다")


class TheRollKeepsOneDirection(unittest.TestCase):
    """N7. 구르는 동안 세 점이 **같은 쪽으로** 움직인다.

    주인(2026-09-14 18:28): 「눈 2개가 왼쪽으로 돌아갈 때 입은 오른쪽으로 돌아가는
    경우가 있는 것 같다.」

    구르기는 진행 방향 u 로 밀면서 그 방향으로 납작해진다. 한 점의 화면 속도는

        v = (π/2)·[ HIDE·cos(a) − (1−K_MIN)·sin(a)·((p−O)·u) ],   a = t·T_MAX·π/2

    로 **전부 u 위에** 있다 — 방향이 갈리는 것이 아니라 **부호**가 갈린다. 앞선
    점은 `(p−O)·u` 가 크므로 뒤 항이 먼저 커져, 어느 순간 그 점만 뒤로 돈다.
    뒤집히는 자리는 `cot(a) = (1−K_MIN)·proj/HIDE` 이고, 지나감의 끝(T_MAX)이 그보다
    앞서야 한다. 이 시험은 그 부등식을 **조각의 실제 좌표로** 푼다 — 재주를 흉내
    내지 않고도 「갈라지지 않는다」가 참이 된다.
    """

    def consts(self, src):
        out = {}
        for k in ("HIDE", "T_MAX", "K_MIN", "CURVE_MAX"):
            m = re.search(r"var\s+%s\s*=\s*([\d.]+)" % k, src)
            self.assertIsNotNone(m, "%s 가 상수로 없다" % k)
            out[k] = float(m.group(1))
        return out

    def test_n7_three_dots_never_split(self):
        src = read("app", "mark.js")
        c = self.consts(src)
        snippet = re.search(r'<div class="brand">(.*?)</svg>', read("index.html"), re.S)
        snippet = snippet.group(1) + "</svg>"
        m = DOME.search(snippet)
        cx, cy, R = (float(v) for v in m.groups())
        d3 = [tuple(float(v) for v in g) for g in DOT.findall(snippet[m.end():])][:3]
        ox = sum(p[0] for p in d3) / 3.0
        oy = sum(p[1] for p in d3) / 3.0
        proj = max(math.hypot(p[0] - ox, p[1] - oy) for p in d3)

        # ① 지나감이 끝나기 전에 앞선 점이 뒤로 돌지 않는가
        cot = 1.0 / math.tan(c["T_MAX"] * math.pi / 2)
        lim = (1 - c["K_MIN"]) * proj / c["HIDE"]
        self.assertGreater(cot, lim * 1.5,
                           "구르기 끝에서 앞선 점이 뒤로 돈다 — cot(%.2f)=%.3f 이 "
                           "문턱 %.3f 의 1.5배를 못 넘는다. 끝(T_MAX)을 앞당기거나 "
                           "납작해짐의 바닥(K_MIN)을 올려라"
                           % (c["T_MAX"], cot, lim))

        # ② 축이 도는 꼴(휘어짐)이 직각으로 갈라 놓지 않는가
        common = c["HIDE"] * math.cos(c["T_MAX"] * math.pi / 2) * (math.pi / 2)
        perp = math.radians(c["CURVE_MAX"]) * proj
        self.assertLess(perp, 0.55 * common,
                        "휘어짐 %.0f도가 공통 속도(%.1f)의 절반을 넘는 직각 성분(%.1f)을 "
                        "만든다 — 축 양쪽의 점이 서로 다른 쪽으로 간다"
                        % (c["CURVE_MAX"], common, perp))
        # 지나감 안에서 축이 도는 꼴은 휘어짐뿐이어야 한다
        dr = src[src.index("function rollDraw("):src.index("\n  }", src.index("function rollDraw("))]
        self.assertIn("curve = rnd(24, CURVE_MAX)", dr, "휘어짐이 상한을 안 쓴다")

        # ③ 밀어낸 끝에서 세 점이 **전부** 테 밖인가 (위로 구를 때가 가장 빡빡하다)
        k = c["K_MIN"] + (1 - c["K_MIN"]) * math.cos(c["T_MAX"] * math.pi / 2)
        low = max(p[1] for p in d3) - oy          # 무게중심에서 아래 점까지
        r = d3[0][2]
        inner = abs((oy - cy) - c["HIDE"] + low * k) - r
        self.assertGreater(inner, R,
                           "위로 구를 때 점 하나가 테 안(%.1f < %.1f)에 남는다 — "
                           "허공에 뜬 점으로 보인다. HIDE 를 키워라" % (inner, R))


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


class TheTrickTableIsWhole(unittest.TestCase):
    """N6. 재주 표 — 손으로 지은 것과 **틀이 곱해 낸 것**을 합쳐 110 을 넘고, 시계가
    가드를 지키며, 어떤 재주도 점을 돔 밖에 두지 않는다.

    표가 백 줄을 넘으면 「하나씩 눈으로 본다」로도, 「줄마다 시험을 쓴다」로도 못
    지킨다. 그래서 재는 자리를 둘로 잡는다.
      · **수와 꼴** — 손으로 지은 줄은 글자로 세고, 곱해 낸 것은 원소의 수로 센다
        (경로 × 속도 × 대상). 틀이 넷(이름·희귀도·길이·하는 일)을 채우는지는
        틀 하나만 보면 전부에 대해 참이다.
      · **경계** — 붓이 **제 손으로** 자른다. 무리를 옮기는 붓(capped)은 배율까지
        셈에 넣고, 점을 옮기는 붓(dcap)은 옮긴 거리가 아니라 **옮긴 자리**로 잰다.
        재주가 어떤 값을 주어도 그 둘을 지나야 화면에 닿으므로, 재주를 하나씩
        흉내 내지 않고도 「돔 밖으로 못 나간다」가 참이다.
    """

    ENTRY = re.compile(r'\{name: "([^"]+)", fam: "([^"]+)", rare: "([^"]+)", ms: (\d+)(, solo: true)?')
    RARE = ("흔함", "가끔", "드묾", "아주 드묾")

    def counts(self, src):
        hand = [e for e in self.ENTRY.findall(src) if e[1] == "표정"]
        def arr(name):
            i = src.index("var %s = [" % name)
            return src[i:src.index("\n  ];", i)].count('{n: "')
        chains = src[src.index("var CHAINS = ["):src.index("\n  ];", src.index("var CHAINS = ["))]
        # 구르기 = 꼴마다 대표 하나 + 이름으로 지은 것(빙그르르·데구르르 …).
        # 벌의 수가 아니라 **뽑는 방법**이 다양성을 낸다(v13).
        shapes = len(re.findall(r'\{n: "[^"]+", ax:', src))
        named = len(re.findall(r'fam: "구르기", rare:', src))
        return (hand, arr("PATHS"), arr("SPEEDS"), shapes + named,
                chains.count("[\""))

    def test_n6_the_table_is_big_and_the_three_dots_stay_one_gaze(self):
        src = read("app", "mark.js")
        hand, paths, speeds, rolls, chains = self.counts(src)
        made = paths * speeds
        total = len(hand) + made + rolls + chains
        self.assertGreaterEqual(paths, 10, "경로가 열 가지도 안 된다")
        self.assertGreaterEqual(total, 60,
                                "재주가 %d 개다 — 손 %d + 곱해 낸 것 %d + 구르기 %d + 연쇄 %d"
                                % (total, len(hand), made, rolls, chains))
        self.assertGreaterEqual(rolls, 8,
                                "구르기 대표가 %d 뿐이다 — 꼴마다 하나씩은 있어야 한다" % rolls)
        # 구르기는 표가 아니라 **뽑는 방법**이다 (주인 2026-09-14 18:00)
        self.assertIn("function rollDraw(", src,
                      "구르기를 실행 때마다 새로 짓지 않는다 — 표는 유한하고, 유한한 "
                      "표는 한참 보면 되풀이가 보인다")
        dr = src[src.index("function rollDraw("):src.index("\n  }", src.index("function rollDraw("))]
        for want in ("rnd(0, 360)", "turns = rnd(", "spd = rnd(", "ein = rnd(", "tilt = rnd("):
            with self.subTest(want):
                self.assertIn(want, dr, "%s — 연속 변수로 뽑지 않는다" % want)
        vec = dr[dr.index("v: ["):]
        self.assertGreaterEqual(vec.count(","), 8,
                                "새로움을 재는 벡터가 너무 짧다 — 축이 여덟은 되어야 "
                                "「비슷한 것」을 가려낼 수 있다")
        m = re.search(r"var\s+NOVEL\s*=\s*([\d.]+)", src)
        self.assertIsNotNone(m, "새로움 문턱(NOVEL)이 없다")
        self.assertTrue(0.18 <= float(m.group(1)) <= 0.45,
                        "문턱이 0.18~0.45 밖이다: %s — 방향 30도(0.259)·바퀴 0.5(0.200)·"
                        "속도 30%%(0.300)가 잣대다" % m.group(1))
        for want in ("function fresh(", "function nearest(", "function remember(",
                     "function reseed("):
            with self.subTest(want):
                self.assertIn(want, src, "%s 가 없다 — 비슷한 것을 걸러 낼 수 없다" % want)
        self.assertIn("reseed();", src,
                      "재주마다 폭과 빠르기를 새로 뽑지 않는다 — 표정도 매번 조금씩 "
                      "달라야 한다")
        # 표가 기대는 것이 실제로 **정의되어** 있는가
        # 실제 사고 2026-09-14 17:50: 구르기 가족을 넓히는 편집이 그 아래에 있던
        # roll·landing·rollPace·rollMs 와 ROLL_TURNS·ROLL_SPEEDS·ROLL_FINS 를 통째로
        # 지웠는데, 글자를 세는 시험은 전부 통과했다(지워진 이름을 아무도 안 찾았다).
        # 화면에서는 mark.js 가 불러오자마자 죽어 **눈이 아예 안 움직였다**.
        # 표가 부르는 이름은 여기서 하나씩 있는지 본다.
        for want in ("var ROLL_DIRS", "var ROLL_SHAPES", "var ROLL_TURNS",
                     "var ROLL_SPEEDS", "var ROLL_FINS", "function roll(",
                     "function landing(", "function rollPace(", "function rollMs(",
                     "function slide(", "function ramp(", "function seq("):
            with self.subTest(want):
                self.assertIn(want, src,
                              "%s 가 없다 — 표가 부르는 것이 정의되어 있지 않으면 "
                              "mark.js 가 불러오자마자 죽는다" % want)

        # 방위와 꼴 — 구르기가 갈리는 두 축
        dirs = len(re.findall(r'\{n: "[^"]+", x:', src))
        shapes = len(re.findall(r'\{n: "[^"]+", ax:', src))
        self.assertGreaterEqual(dirs, 8, "방위 이름이 %d 뿐이다 — 여덟은 있어야 한다" % dirs)
        self.assertGreaterEqual(shapes, 5, "구르는 꼴이 %d 뿐이다 — 다섯은 있어야 한다" % shapes)
        self.assertIn("p.back ? w + \"에서\" : toward(w)", src,
                      "굴러가는 쪽과 되돌아오는 쪽을 가르지 않는다 — 방위가 한쪽뿐이면 "
                      "같은 그림이 절반이다")
        # 의성어 넷은 이름 그대로 표에 있어야 한다
        for w in ("빙그르르", "데구르르", "데굴데굴", "휘리리릭"):
            with self.subTest(w):
                self.assertIn('{name: "%s", fam: "구르기"' % w, src,
                              "%s 가 그 이름으로 표에 없다" % w)
        # 가족 몫 — 구르기가 세 번에 한 번은 나와야 한다
        fm = src[src.index("var FAMS = ["):src.index("\n  ];", src.index("var FAMS = ["))]
        ws = dict((a, int(b)) for a, b in re.findall(r'\{n: "([^"]+)", w: (\d+)\}', fm))
        self.assertEqual(sorted(ws), sorted(["구르기", "곱", "연쇄", "표정"]),
                         "가족이 넷이 아니다: %r" % sorted(ws))
        share = 100.0 * ws["구르기"] / sum(ws.values())
        self.assertGreaterEqual(share, 30.0,
                                "구르기 몫이 %.0f퍼센트다 — 서른은 넘어야 10초에 한 번쯤 "
                                "구른다" % share)
        # 몫 밖으로 새는 재주가 없어야 한다 — 손으로 적은 줄도, 틀이 내는 줄도
        self.assertEqual(src.count('{name: "'),
                         len(re.findall(r'\{name: "[^"]+", fam: "', src)),
                         "가족표(fam)가 없는 줄이 있다 — 그것은 몫 밖에서 돈다")
        for fam in ("곱", "연쇄", "구르기"):
            with self.subTest(fam):
                self.assertIn('fam: "%s"' % fam, src, "%s 을 내는 틀에 가족표가 없다" % fam)
        # 비슷한 것을 표에 두지 않는다 — 속도는 둘, 결은 경로마다 하나
        self.assertLessEqual(speeds, 2,
                             "속도가 %d 갈래다 — 「보통」은 어느 경로에서도 「느리게」와 "
                             "눈으로 갈리지 않았다" % speeds)
        self.assertIn("var PATH_MOOD = [", src,
                      "경로마다 결을 하나로 고르는 자리가 없다 — 네 결을 다 곱하면 "
                      "폭만 다른 짝이 표에 두 줄로 남는다")
        # 점 셋은 하나의 시선이다
        solo = src.count("solo: true,")
        self.assertLessEqual(solo * 100.0 / total, 10.0,
                             "점이 따로 노는 재주가 %d 개(%.1f%%)다 — 10%% 를 넘으면 "
                             "화면이 장난이 아니라 벌레로 읽힌다" % (solo, solo * 100.0 / total))
        self.assertGreater(solo, 0, "점이 따로 노는 재주가 아예 없다 — 소수는 남긴다")
        self.assertNotIn('{n: "점 셋 따로"', src,
                         "곱하는 축에 점을 따로 놀리는 갈래가 남아 있다 — 그러면 표의 "
                         "태반이 그것이 된다")
        names = [g[0] for g in hand]
        self.assertEqual(len(names), len(set(names)), "같은 이름의 재주가 둘이다")
        for name, _fam, rare, ms, _solo in hand:
            with self.subTest(name):
                self.assertIn(rare, self.RARE, "희귀도가 넷 중 하나가 아니다: %r" % rare)
                self.assertTrue(200 <= int(ms) <= 3000, "길이가 0.2~3초 밖이다: %sms" % ms)
        # 틀이 내는 줄도 넷을 채운다 — 틀 하나를 보면 곱해 낸 것 전부가 참이다
        cb = src[src.index("function combo("):src.index("\n  }", src.index("function combo("))]
        for want in ("name:", "rare:", "ms:", "run:"):
            with self.subTest(want):
                self.assertIn(want, cb, "틀이 %s 를 안 채운다" % want)
        self.assertIn("Math.random()", cb, "각도를 실행 때 뽑지 않는다 — 표가 각도만 다른 "
                                           "줄로 부풀어도 보는 사람에게는 같은 재주다")
        # 주인이 예시로 든 넷 (손으로 지은 줄에서)
        joined = " ".join(names)
        for want, why in ((("부르르", "지그재그", "다다닥"), "요란하게 움직이는 재주"),
                          (("숨 쉬기", "툭 벌어짐"), "무리가 벌어졌다 좁아지는 재주"),
                          (("홀로", "흩어", "자리 바꾸기", "물결"), "점 셋이 따로 노는 재주")):
            with self.subTest(why):
                self.assertTrue(any(w in joined for w in want), "%s 가 표에 없다" % why)
        # 축이 다른 회전은 구르기 가족의 방위가 맡는다(위에서 여덟 이상을 이미 봤다)
        self.assertGreaterEqual(chains, 6, "연쇄 재주가 여섯도 안 된다")

    def test_n6b_the_clock_yields_and_the_brushes_cut_at_the_dome(self):
        src = read("app", "mark.js")
        stage = src[src.index("function stage()"):src.index("\n  }", src.index("function stage()"))]
        self.assertIn("unseen() || still()", stage, "시계가 안 보이는 탭·움직임 줄이기를 안 본다")
        self.assertIn("following", stage, "시계가 커서를 좇는 중에 끼어든다")
        self.assertIn("lastPick", src, "같은 재주를 연달아 뽑지 않는 장치가 없다")
        # 뽑기는 섞은 주머니다 — 순서가 표 순서를 드러내면 안 된다
        self.assertIn("function refill(fam)", src, "가족별 섞은 주머니가 없다")
        rf = src[src.index("function refill(fam)"):src.index("\n  }", src.index("function refill(fam)"))]
        self.assertIn("Math.floor(Math.random() * (i + 1))", rf,
                      "주머니를 섞지 않는다 — 피셔–예이츠가 없다")
        self.assertIn("WEIGHT[TRICKS[i].rare]", rf, "희귀도만큼 담지 않는다")

        # 커서 추종 — 반경 안에서 움직이면 **재주를 끊고** 좇는다
        tr = src[src.index("  function track(e)"):src.index("\n  }", src.index("  function track(e)"))]
        self.assertIn("d > NEAR_R", tr, "반경 밖 커서를 걸러 내지 않는다")
        self.assertIn("stop();", tr,
                      "커서가 와도 재주를 안 끊는다 — 재주 중에는 눈이 커서를 무시하게 된다")
        self.assertIn("calmTimer", tr, "커서가 멎기를 기다리는 시계가 없다")
        for key, lo, hi in (("NEAR_R", 120, 600), ("CALM_MS", 800, 3000)):
            m = re.search(r"var\s+%s\s*=\s*([\d.]+)" % key, src)
            self.assertIsNotNone(m, "%s 가 상수로 없다" % key)
            self.assertTrue(lo <= float(m.group(1)) <= hi,
                            "%s 가 %s~%s 밖이다: %s" % (key, lo, hi, m.group(1)))
        cm = src[src.index("  function calm()"):src.index("\n  }", src.index("  function calm()"))]
        self.assertIn("stage()", cm, "커서가 멎어도 재주가 다시 돌지 않는다")
        self.assertIn("rest()", stage, "재주 끝에 쉼 자세로 돌려놓지 않는다")

        # 붓이 제 손으로 자르는가 — 여기가 참이면 재주를 하나씩 흉내 내지 않아도 된다
        cap = src[src.index("function capped("):src.index("\n  }", src.index("function capped("))]
        self.assertIn("LENS_R - REACH", cap, "무리의 상한이 배율을 셈에 안 넣는다")
        dc = src[src.index("function dcap("):src.index("\n  }", src.index("function dcap("))]
        self.assertIn("LENS_R - b[2]", dc, "점의 상한이 옮긴 자리로 재지 않는다")
        dfn = src[src.index("  function D(i,"):src.index("\n  }", src.index("  function D(i,"))]
        self.assertIn("dcap(i, x, y)", dfn, "점을 옮기는 붓이 상한을 지나지 않는다")
        self.assertIn('BASE.push([+c.getAttribute("cx")', src,
                      "점의 제자리를 조각에서 읽지 않는다 — 좌표를 두 곳에 적으면 갈린다")

        css = read("css", "header.css").replace(" ", "").replace("\n", "")
        for sel in (".pupil", ".spin", ".d0", ".d1", ".d2"):
            with self.subTest(sel):
                self.assertIn(sel, css, "%s 층의 규칙이 없다" % sel)
        self.assertIn(".d2{transition:none;transform:none}", css,
                      "움직임 줄이기에서 점 층을 안 세운다")

        snippet = re.search(r'<div class="brand">(.*?)</svg>', read("index.html"), re.S)
        snippet = snippet.group(1) + "</svg>"
        for want in ("<clipPath", 'clip-path="url(#s9lensclip)"', '<g class="spin">',
                     '<g class="d0"', '<g class="d1"', '<g class="d2"'):
            with self.subTest(want):
                self.assertIn(want, snippet, "머리 조각에 %s 가 없다" % want)

        # 상한이 실제 좌표에서 돔 안에 남는가
        c = {}
        for key, pat in (("LENS_R", r"var\s+LENS_R\s*=\s*([\d.]+)"),
                         ("MAXF", r"var\s+MAX\s*=\s*LENS_R\s*\*\s*([\d.]+)"),
                         ("HIDE", r"var\s+HIDE\s*=\s*([\d.]+)")):
            m = re.search(pat, src)
            self.assertIsNotNone(m, "%s 가 상수로 없다" % key)
            c[key] = float(m.group(1))
        R = c["LENS_R"]
        m = DOME.search(snippet)
        cx, cy, domeR = (float(v) for v in m.groups())
        self.assertAlmostEqual(R, domeR, delta=0.05,
                               msg="코드의 돔 반지름이 조각의 것과 다르다")
        d3 = [tuple(float(v) for v in g) for g in DOT.findall(snippet[m.end():])][:3]
        far = max(math.hypot(x - cx, y - cy) + r for x, y, r in d3)
        self.assertLess(far, R, "쉼 자세에서 이미 점이 테를 넘는다")
        self.assertGreater(c["HIDE"] - far, 0,
                           "뒤로 밀어내는 거리(%.1f)가 모자라 점이 테에 걸친다" % c["HIDE"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
