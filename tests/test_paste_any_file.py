"""터미널 붙여넣기가 그림만 받지 않는다 (REQ-20260829-035 에서 건진 조각).

같은 터미널의 drop 과 📎 는 무엇이든 받는데 **붙여넣기만** `^image/` 로 걸렀다.
pdf·mp4·csv 를 붙이면 조용히 사라지고, 사람은 붙였다고 믿은 채 근거 없이 말을
보낸다. 판정 창은 이미 같은 판단을 내려 두었다(REQ-20260829-015 반려):
"무엇으로 적을지는 서버가 정하므로 화면은 종류를 묻지 않는다."

칩의 이모지 폴백도 같은 워크트리에서 건졌다 — 앞머리가 🖼/📎 인데 mono 하나만
물리면 그 글리프가 없는 자리에서 두부 상자가 된다.
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(index_path(), encoding="utf-8").read()


def _paste_handler():
    """**터미널의** 붙여넣기 처리기를 집는다.

    이 파일에는 붙여넣기 처리기가 둘이다 — 판정 창의 것(먼저 나오고, 이미
    무엇이든 받는다)과 터미널의 것. 앞의 것을 집으면 이 시험은 고치기 전에도
    통과해 아무것도 못 잡는다. 터미널의 것은 `L5` 표식이 가른다.
    """
    i = SRC.index('ta.addEventListener("paste", e => {            // L5')
    return SRC[i:i + 1400]


class PasteTakesAnyFile(unittest.TestCase):
    def test_paste_takes_any_file(self):
        """붙여넣기 처리기가 종류로 거르지 않는다."""
        with self.subTest("p1_paste_does_not_filter_by_image"):
            h = _paste_handler()
            self.assertIn('i.kind === "file"', h)
            # 주석에는 옛 정규식이 경위로 적혀 있어도 된다 — **코드**에 없어야 한다.
            code = re.sub(r"/\*.*?\*/", "", h, flags=re.S)
            code = re.sub(r"//[^\n]*", "", code)
            self.assertNotIn("^image/", code,
                             "붙여넣기가 그림만 받으면 pdf·mp4 가 조용히 사라진다")
        with self.subTest("p2_the_three_ways_in_agree"):
            h = _paste_handler()
            self.assertIn("termUpload", h)
            # drop 과 파일 고르기도 같은 함수를 지난다
            self.assertGreaterEqual(SRC.count("termUpload("), 3)
        with self.subTest("p3_why_is_written_down"):
            h = _paste_handler()
            self.assertIn("REQ-20260829-035", h)
        with self.subTest("p4_dialog_chip_has_an_emoji_fallback"):
            m = re.search(r"\.dlgatt \.chip\{[^}]*\}", SRC, re.S)
            self.assertTrue(m)
            body = m.group(0)
            self.assertIn("Segoe UI Emoji", body)
            self.assertIn("Noto Color Emoji", body)
        with self.subTest("p5_the_terminal_already_had_that_fallback"):
            self.assertGreaterEqual(SRC.count('"Segoe UI Emoji","Noto Color Emoji"'), 3)

if __name__ == "__main__":
    unittest.main(verbosity=2)
