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
  E7 탭 아이콘의 주소에 **그 파일의 지문**이 실려 있다 — 브라우저는 파비콘을 따로
     담아 두고 주소가 바뀔 때만 다시 가져간다. `Cache-Control: no-store` 도 그 장에는
     닿지 않아, 얼굴만 고치면 탭은 옛 얼굴 그대로다(실제 반려 2026-09-18 19:01,
     주인: 「파비콘은 그대로다」). 지문이 주소에 있으면 얼굴이 바뀔 때 주소도 바뀐다.
  E8 래스터 아이콘 넷(favicon.ico · apple-touch-icon · icon-192 · icon-512)이 **지금
     얼굴에서 구운 것**이다. 같은 반려의 나머지 절반이 여기였다 — 이 넷은 손으로
     구운 산출물이라 SVG 를 고쳐도 따라올 길이 없었고, 브라우저가 실제로 탭에
     띄우는 것은 그중 favicon.ico 일 때가 많다. `bin/s9-mark-icons` 가 굽고,
     이 시험이 낡았는지 본다.
  E9 그중 **favicon.ico 는 투명**이고 앱 아이콘 셋은 불투명이다. 처음 구울 때
     넷을 다 바탕색 위에 찍어 favicon.ico 가 RGBA 에서 RGB 로 바뀌었고, 탭과
     북마크 줄에서 렌즈가 검은 사각형을 달고 앉았다(주인 지적 2026-09-18 20:22:
     「파비콘과 북마크에 들어갈 이미지 로고가 실제 로고와 다르게 검은 배경이다」).
     앱 아이콘 셋은 반대다 — 홈 화면·앱 목록이 투명을 제 맘대로 메우므로 불투명이
     맞고, 옛 파일도 그랬다.

실행: python3 tests/ mark_eyes
"""
import hashlib
import math
import os
import subprocess
import sys
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

    def test_e7_favicon_url_carries_the_file_fingerprint(self):
        """E7. 아이콘 link 셋의 주소가 각각 **그 파일의** 지문을 달고 있다.

        svg 만 달았을 때 한 번 더 물렸다 — .ico 를 고쳐도 주소가 그대로라 북마크
        줄은 옛 그림을 쥐고 있었다(2026-09-18 20:22). 지문은 파일마다 제 것이다.
        """
        for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png"):
            want = hashlib.sha256(
                open(os.path.join(WEB, "assets", name), "rb").read()
            ).hexdigest()[:8]
            for page in ("index.html", "guide.html"):
                m = re.search(r'href="assets/%s\?v=([0-9a-f]+)"' % re.escape(name),
                              read(os.path.join(WEB, page)))
                self.assertIsNotNone(
                    m, "%s 의 %s 주소에 ?v= 지문이 없다 — 고쳐도 탭·북마크는 안 바뀐다"
                    % (page, name))
                self.assertEqual(
                    m.group(1), want,
                    "%s 의 %s 지문이 낡았다 — 파일을 고쳤으면 ?v= 도 %s 로 옮겨라"
                    % (page, name, want))

    def test_e8_raster_icons_are_baked_from_this_face(self):
        """E8. 래스터 아이콘 넷이 지금의 favicon.svg 에서 구운 것이다."""
        gen = os.path.normpath(os.path.join(HERE, "..", "bin", "s9-mark-icons"))
        r = subprocess.run([sys.executable, gen, "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout.strip() or r.stderr.strip())

    def test_e9_the_tab_icon_is_transparent_the_app_icons_are_not(self):
        """E9. favicon.ico 의 세 장은 RGBA 에 모서리가 비어 있고, 앱 아이콘 셋은 불투명이다."""
        import struct

        def colortype(blob):
            pos = 8
            while pos < len(blob):
                ln = struct.unpack(">I", blob[pos:pos + 4])[0]
                if blob[pos + 4:pos + 8] == b"IHDR":
                    w, h, _bd, ct = struct.unpack(">IIBB", blob[pos + 8:pos + 18])
                    return w, h, ct
                pos += ln + 12
            return 0, 0, -1

        ico = open(os.path.join(WEB, "assets", "favicon.ico"), "rb").read()
        _, _, n = struct.unpack("<HHH", ico[:6])
        self.assertEqual(n, 3, "favicon.ico 에 16·32·48 세 장이 아니다")
        for i in range(n):
            _w, _h, _r, _x, _p, _bpp, size, off = struct.unpack(
                "<BBBBHHII", ico[6 + 16 * i:22 + 16 * i])
            blob = ico[off:off + size]
            self.assertEqual(blob[:8], b"\x89PNG\r\n\x1a\n")
            w, h, ct = colortype(blob)
            self.assertEqual(ct, 6,
                             "favicon.ico 의 %dx%d 가 투명이 아니다(colortype %d) — "
                             "탭과 북마크에서 검은 사각형이 따라붙는다" % (w, h, ct))
        for name in ("apple-touch-icon.png", "icon-192.png", "icon-512.png"):
            with open(os.path.join(WEB, "assets", name), "rb") as f:
                _w, _h, ct = colortype(f.read())
            self.assertEqual(ct, 2,
                             "%s 는 불투명이어야 한다 — 홈 화면이 투명을 제 맘대로 "
                             "메운다 (colortype %d)" % (name, ct))


if __name__ == "__main__":
    unittest.main()
