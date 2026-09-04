"""식별자는 경과시각을 덮지 않는다 (REQ-20260831-021-62x6).

사용자가 본 것: 창 1000px·cork compact 처럼 열이 좁아지면 카드 식별자가
경과시각 밑으로 1.19px 파고들었다.

뿌리는 둘이었다.

① **예약이 상수였다.** `.card .id{padding-right:62px}` 는 경과시각의 실폭
   (⏱ 공백 "999d 23h" ≈ 11자)보다 작아질 수 있고, 스킨이 글자를 키워도
   (calm 11px) 따라오지 못한다. 예약은 그 내용 모델에 **글자 단위(ch)** 로
   묶는다 — ch 는 그 줄의 글꼴을 읽으므로 크기가 변하면 예약이 함께 변한다.

② **첫 항목은 줄바꿈이 안 된다.** id 줄은 flex-wrap 인데, flex 는 줄의 첫
   항목을 아랫줄로 못 내린다. 점(livedot)이 있는 카드는 식별자가 둘째
   항목이라 좁아지면 얌전히 내려가는데, 점 없는 카드는 식별자가 첫 항목이
   되어 예약을 뚫고 시각을 덮었다 — 같은 폭에서 카드마다 결이 갈렸다.
   폭 0 스트럿(::before)이 줄 첫머리에 서서 식별자를 늘 '둘째 이후'로
   만든다. 높이는 줄 상자(--card-edge)를 따라가, 내려간 식별자가 시각
   **아래** 줄에 선다.

곁: `.card .t` 의 56px 예약은 죽은 것이었다 — 제목은 시각이 선 첫 줄
아래에서 시작하므로 덮을 수 없는데, 제목만 일찍 접고 있었다.

soft 는 시각을 제 줄로 내려 예약을 0 으로 덮는 스킨이다 — 그 덮어쓰기
(padding-right:0)는 그대로 산다. 0 은 예약이 아니므로 이 시험도 허용한다.

실행: python3 tests/ id_clearance
"""
import re
import unittest

from webasset import index_path

INDEX = index_path()


def _css(src):
    """주석을 걷어낸 CSS 만 — 주석은 고쳐 낸 옛 값을 근거로 인용한다."""
    return re.sub(r"/\*[\s\S]*?\*/", " ", src)


def _rules(src):
    out = []
    for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", src):
        out.append((" ".join(m.group(1).split()), m.group(2)))
    return out


def _decl(dec, prop):
    m = re.search(r"(?:^|;)\s*%s\s*:([^;]*)" % re.escape(prop), dec)
    return m.group(1).strip() if m else None


class TheIdNeverCoversTheClock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.rules = _rules(_css(f.read()))

    def test_the_id_never_covers_the_clock(self):
        """TheIdNeverCoversTheClock 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_reservation_is_letters_not_pixels"):
            seen = []
            for sel, dec in self.rules:
                if ".card .id" not in sel or "::" in sel or ".id ." in sel:
                    continue
                val = _decl(dec, "padding-right")
                if val is None:
                    continue
                seen.append((sel, val))
                if re.fullmatch(r"0(px)?", val):
                    continue
                self.assertNotRegex(
                    val, r"^\s*-?\d+(\.\d+)?px\s*$",
                    "%s 의 예약폭이 상수 px 이다(%s) — ch 로 경과시각의 "
                    "내용 모델을 읽어라" % (sel, val))
                self.assertIn("ch", val,
                              "%s 의 예약폭이 글자 단위를 안 읽는다: %s"
                              % (sel, val))
            self.assertTrue(any(s == ".card .id" for s, _ in seen),
                            "`.card .id` 의 예약폭 선언이 사라졌다 — 예약이 "
                            "없으면 식별자가 시각과 같은 칸을 쓴다")
        with self.subTest("the_strut_keeps_the_id_wrappable"):
            strut = [d for s, d in self.rules if s == ".card .id::before"]
            self.assertTrue(strut, "`.card .id::before` 스트럿이 없다")
            self.assertIsNotNone(_decl(strut[0], "content"),
                                 "스트럿에 content 가 없다 — 그려지지 않는 "
                                 "가상 요소는 flex 항목이 아니다")
            h = _decl(strut[0], "height")
            self.assertIsNotNone(h, "스트럿에 높이가 없다 — 식별자가 내려갈 때 "
                                    "첫 줄이 0 으로 접혀 시각과 같은 높이가 된다")
            self.assertIn("var(--card-edge", h,
                          "스트럿 높이가 줄 상자의 자를 안 읽는다: %s" % h)
            self.assertIsNone(_decl(strut[0], "width"),
                              "스트럿에 폭이 생겼다 — 폭 0 이어야 예약과 "
                              "이중으로 자리를 먹지 않는다")
        with self.subTest("the_title_carries_no_dead_reservation"):
            base = [d for s, d in self.rules if s == ".card .t"]
            self.assertTrue(base, "`.card .t` 기본 규칙이 없다")
            for d in base:
                val = _decl(d, "padding-right")
                if val is None:
                    continue
                self.assertNotRegex(
                    val, r"\d+(\.\d+)?px",
                    "`.card .t` 에 죽은 예약이 되돌아왔다: %s" % val)

if __name__ == "__main__":
    unittest.main()
