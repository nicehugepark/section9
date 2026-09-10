"""마크 사전 한 곳 (REQ-20260910-027) — 그림은 `web/css/marks.css` 에만 있다.

이 화면의 마크는 출처가 넷이었다: 손으로 격자에 맞춘 SVG · 폰트 코드포인트 ·
`.cdot` · `.livedot`. 폰트 코드포인트는 맥·iPad Safari 에서 컬러 이모지로 나오고
획 두께를 OS 가 정해, 손으로 맞춘 SVG 와 나란히 서면 결이 따로 논다.

여기서 기계로 세는 것 넷.
1. 화면 코드에 마크 코드포인트(▲ ↻ ⧉ ▸ ▾ ⏳ ⏱)가 남아 있지 않다. 문장 안의
   부호(× + −)는 글자라 세지 않는다.
2. 사전의 그림은 전부 11칸 격자이고 **제 크기(width·height)를 적는다** —
   `viewBox` 만 있는 SVG 를 mask 로 쓰면 배율 1.25 에서 마크가 통째로 사라진다.
3. 획은 1px 뿐이다 — 1.5px 는 어느 배율에서도 한쪽 끝이 반 화소에 걸린다.
4. mask 는 낱개 속성으로 적는다 — `mask:var(…) …` 단축은 크롬이 그림을 못 싣는다.

실행: python3 tests/ marks_dictionary
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "..", "web")
MARKS = os.path.join(WEB, "css", "marks.css")

# 그림으로 서야 하는 코드포인트 — 문장 부호(× + −)는 여기 없다(글자다)
GLYPHS = "▲↻⧉▸▾⏳⏱"

# 아직 사전으로 못 옮긴 자리 — **왜 못 옮겼는지가 여기 적혀 있어야** 다음 사람이
# 이것을 통과로 오해하지 않는다. REQ-20260910-027 을 하는 동안 다른 요청이
# `settings.js` 를 담고 있어 손댈 수 없었다(펼침 표 ▸ ▾ 두 자리).
OWED = {os.path.join("app", "settings.js")}


def _strip_comments(text, js):
    """주석은 세지 않는다 — 규칙을 적어 둔 글에 그 글자가 나오는 것은 결함이 아니다."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    if js:
        text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return text


def _sources():
    """화면 소스를 **한 번씩만** 읽는다 (예산 기준선)."""
    out = {}
    for sub in ("css", "app"):
        d = os.path.join(WEB, sub)
        for name in sorted(os.listdir(d)):
            if not name.endswith((".css", ".js")):
                continue
            path = os.path.join(d, name)
            with open(path, encoding="utf-8") as fh:
                out[os.path.join(sub, name)] = fh.read()
    return out


SRC = _sources()
with open(MARKS, encoding="utf-8") as _fh:
    MARKS_TEXT = _fh.read()


class TheMarksComeFromOneDictionary(unittest.TestCase):
    def test_no_font_codepoint_marks_left_in_screen_code(self):
        """폰트 코드포인트로 그린 마크가 남아 있지 않다."""
        left = []
        for rel, text in SRC.items():
            if rel.endswith("marks.css") or rel in OWED:
                continue                     # 사전은 제 규칙을 글로 적는 자리다
            body = _strip_comments(text, rel.endswith(".js"))
            for ch in GLYPHS:
                if ch in body:
                    left.append("%s: %s" % (rel, ch))
        self.assertEqual([], left, "마크는 사전에서 온다 — 남은 코드포인트: %s" % left)

    def test_every_mark_declares_its_own_size_on_the_eleven_grid(self):
        """그림마다 11칸 격자 + 제 크기. 배율 1.25 에서 사라지는 것을 막는다."""
        svgs = re.findall(r"%3Csvg[^\"]*?%3E", MARKS_TEXT)
        self.assertGreaterEqual(len(svgs), 6, "사전에 그림이 없다")
        for svg in svgs:
            self.assertIn("width='11'", svg)
            self.assertIn("height='11'", svg)
            self.assertIn("viewBox='0 0 11 11'", svg)

    def test_strokes_are_one_pixel(self):
        """획은 1px 뿐 — 1.5px 는 배율마다 다르게 그려진다."""
        widths = set(re.findall(r"stroke-width='([\d.]+)'", MARKS_TEXT))
        self.assertEqual({"1"}, widths or {"1"}, "획이 1px 이 아닌 그림이 있다: %s" % widths)

    def test_mask_is_written_as_longhand(self):
        """`mask:var(…) …` 단축은 크롬이 그림을 못 싣는다 — 낱개 속성으로 적는다."""
        body = _strip_comments(MARKS_TEXT, False)
        self.assertNotRegex(body, r"(?<!-)\bmask\s*:\s*var\(")
        self.assertNotRegex(body, r"-webkit-mask\s*:\s*var\(")
        self.assertIn("mask-image:var(--mk)", body)

    def test_the_two_faces_of_one_control_carry_the_same_ink(self):
        """접힘 ▸ 과 펼침 ▾ 은 한 축의 두 방향이라 잉크가 같아야 한다."""
        def area(name):
            m = re.search(r"--mk-%s-src:.*?d='M([\d.]+) ([\d.]+) L([\d.]+) ([\d.]+) L([\d.]+) ([\d.]+) Z'"
                          % name, MARKS_TEXT)
            self.assertIsNotNone(m, "%s 세모를 못 찾았다" % name)
            (x1, y1, x2, y2, x3, y3) = [float(v) for v in m.groups()]
            return abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / 2
        self.assertAlmostEqual(area("fold"), area("unfold"), places=2)


if __name__ == "__main__":
    unittest.main()
