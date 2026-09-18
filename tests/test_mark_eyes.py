"""마크의 눈 셋은 **위 1 · 아래 2** 삼각형이다 (REQ-20260918-015-62x6·016-62x6).

주인 지적 2026-09-18 18:51: 「실제 타치코마는 검은점 1개가 위, 2개가 아래에 있는
삼각형 모양이다」 그리고 18:52: 「검은 점이 조금 더 작고, 더 모여있다」.
그때까지 마크는 위 2 · 아래 1(▽)이었다.

계약 다섯:
  E1 얼굴을 쓰는 세 파일(index.html 머리글 · assets/mark.svg · assets/favicon.svg)이
     같은 좌표·같은 반지름을 쓴다 — 한 제품에 얼굴은 하나다.
  E2 가장 위 점이 하나, 가장 아래 점이 둘이다.
  E3 점이 종전(반지름 3.06)보다 작고, 한 변이 종전(12.58)보다 짧다.
  E4 무게중심이 (32, 41.50) 에 머문다 — web/app/mark.js 의 HIDE·MAX_DOWN 이
     「무리가 렌즈 중심보다 10.6 아래」를 전제로 맞춰져 있다.
  E5 정삼각형이고, 잉크까지 렌즈(반지름 28.9) 안에 있다.

실행: python3 tests/ mark_eyes
"""
import math
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(HERE, "..", "web"))

WAS_R = 3.06          # 뒤집기 전의 점 반지름
WAS_SIDE = 12.58      # 뒤집기 전의 한 변
LENS_R = 28.9         # 돔 반지름 (mark.js 의 LENS_R 과 같은 값)
MID = (32.0, 42.60)   # 무리의 무게중심 (주인 18:55: 「지금보다 더 아래쪽이다」)

DOT = re.compile(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" fill="#000000"')


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def dots(path):
    """그 파일이 그리는 검은 점 셋을 (cx, cy, r) 로 돌려준다."""
    got = [(float(a), float(b), float(c)) for a, b, c in DOT.findall(read(path))]
    return sorted(got)


def side_lengths(pts):
    out = []
    for i in range(3):
        x1, y1, _ = pts[i]
        x2, y2, _ = pts[(i + 1) % 3]
        out.append(math.hypot(x2 - x1, y2 - y1))
    return out


class MarkEyes(unittest.TestCase):
    paths = ("index.html", os.path.join("assets", "mark.svg"),
             os.path.join("assets", "favicon.svg"))

    def setUp(self):
        self.faces = {p: dots(os.path.join(WEB, p)) for p in self.paths}

    def test_e1_three_files_draw_the_same_face(self):
        """E1. 세 파일의 점 셋이 같은 값이다."""
        for p, got in self.faces.items():
            self.assertEqual(len(got), 3, "%s 에 검은 점이 셋이 아니다: %r" % (p, got))
        first = self.faces[self.paths[0]]
        for p in self.paths[1:]:
            self.assertEqual(self.faces[p], first,
                             "%s 의 얼굴이 머리글과 다르다 — 한 자리만 고쳤다" % p)

    def test_e2_one_dot_on_top_two_below(self):
        """E2. 위가 하나, 아래가 둘이다 (▽ 가 아니라 △)."""
        for p, got in self.faces.items():
            ys = sorted(y for _, y, _ in got)
            top = [y for y in ys if abs(y - ys[0]) < 0.5]
            bottom = [y for y in ys if abs(y - ys[-1]) < 0.5]
            self.assertEqual(len(top), 1, "%s: 위 점이 하나가 아니다 %r" % (p, ys))
            self.assertEqual(len(bottom), 2, "%s: 아래 점이 둘이 아니다 %r" % (p, ys))

    def test_e3_dots_are_smaller_and_closer(self):
        """E3. 점이 더 작고 한 변이 더 짧다."""
        got = self.faces[self.paths[0]]
        r = got[0][2]
        self.assertLess(r, WAS_R, "점이 종전(%.2f)보다 작지 않다" % WAS_R)
        self.assertLess(max(side_lengths(got)), WAS_SIDE,
                        "한 변이 종전(%.2f)보다 짧지 않다" % WAS_SIDE)

    def test_e4_centroid_stays_put(self):
        """E4. 무게중심이 그대로다 — 구르기의 상한이 이 값에 맞춰져 있다."""
        got = self.faces[self.paths[0]]
        cx = sum(x for x, _, _ in got) / 3.0
        cy = sum(y for _, y, _ in got) / 3.0
        self.assertAlmostEqual(cx, MID[0], delta=0.05)
        self.assertAlmostEqual(cy, MID[1], delta=0.05)

    def test_e5_equilateral_and_inside_the_lens(self):
        """E5. 정삼각형이고 잉크까지 렌즈 안이다."""
        got = self.faces[self.paths[0]]
        sides = side_lengths(got)
        self.assertLess(max(sides) - min(sides), 0.05,
                        "정삼각형이 아니다: %r" % [round(s, 3) for s in sides])
        for x, y, r in got:
            self.assertLess(math.hypot(x - 32.0, y - 32.0) + r, LENS_R,
                            "점 (%s, %s) 의 잉크가 렌즈를 넘는다" % (x, y))

    def test_e6_motion_origin_follows_the_dot(self):
        """E6. 머리글의 transform-origin 이 그 점의 좌표와 같다 — 어긋나면 헛돈다."""
        src = read(os.path.join(WEB, "index.html"))
        pairs = re.findall(
            r'transform-origin:([\d.]+)px ([\d.]+)px"><circle cx="([\d.]+)" cy="([\d.]+)"',
            src)
        self.assertEqual(len(pairs), 3, "점 셋의 transform-origin 을 못 읽었다")
        for ox, oy, cx, cy in pairs:
            self.assertEqual((ox, oy), (cx, cy),
                             "transform-origin 이 점의 자리와 다르다")


if __name__ == "__main__":
    unittest.main()
