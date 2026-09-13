"""머리글의 마크는 탭 파비콘과 같은 그림 하나다 (REQ-20260913-004-2n7g).

맥 실브라우저 검증(REQ-20260913-019-62x6)에서 본 것: 탭에는 새 마크(assets/mark.svg 와
같은 얼굴의 favicon.svg)가 떴는데 머리글은 아직 8x8 CSS 정사각(.brand .dot)이었고,
guide.html 의 차례도 같은 정사각(.sq)이었다 — 한 제품이 자리마다 다른 얼굴을 보였다.

계약 셋:
  M1 index.html 머리글 .brand 는 img.mark 로 assets/mark.svg 를 쓰고, 그 파일이 있다.
  M2 guide.html 차례의 .brand 도 같은 그림을 쓴다.
  M3 옛 정사각 규칙(.brand .dot · .brand .sq)이 CSS 어디에도 남아 있지 않다.

실행: python3 tests/ brand_mark
"""
import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(HERE, "..", "web"))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


BRAND = re.compile(r'<div class="brand">(.*?)section9', re.S)
MARK = re.compile(r'<img class="mark" src="assets/mark\.svg"[^>]*>')


class BrandMark(unittest.TestCase):
    def test_m1_index_header_uses_the_mark_file(self):
        """M1. index.html 머리글은 assets/mark.svg 를 img.mark 로 쓴다."""
        m = BRAND.search(read(os.path.join(WEB, "index.html")))
        self.assertIsNotNone(m, ".brand 가 없다")
        self.assertRegex(m.group(1), MARK)
        self.assertTrue(os.path.exists(os.path.join(WEB, "assets", "mark.svg")))

    def test_m2_guide_toc_uses_the_same_mark(self):
        """M2. guide.html 차례의 .brand 도 같은 그림이다."""
        m = BRAND.search(read(os.path.join(WEB, "guide.html")))
        self.assertIsNotNone(m, "guide.html 에 .brand 가 없다")
        self.assertRegex(m.group(1), MARK)

    def test_m3_no_css_square_rule_is_left(self):
        """M3. 옛 CSS 정사각 규칙이 남아 있지 않다."""
        left = []
        for p in glob.glob(os.path.join(WEB, "css", "*.css")) + [os.path.join(WEB, "guide.html")]:
            for i, line in enumerate(read(p).splitlines(), 1):
                if re.search(r"\.brand\s+\.(dot|sq)\b", line):
                    left.append("%s:%d" % (os.path.relpath(p, WEB), i))
        self.assertEqual(left, [])


if __name__ == "__main__":
    unittest.main()
