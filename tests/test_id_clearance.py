"""식별자는 경과시각과 같은 칸을 쓰지 않는다 (REQ-20260831-021 · 084 개정).

**옛 계약(예약폭)** — 경과시각과 「이어 말하기」가 카드 모서리에 절대 위치로
떠 있던 시절, id 줄은 그 자리를 `padding-right:calc(11ch + 8px)` 로 비워 두어야
했다. 상수 px(62px)이던 것을 글자 단위(ch)로 묶은 것이 그 계약이었다.

**새 계약(한 흐름)** — REQ-20260909-084 이 셋을 id 줄 안의 한 묶음(`.idr`)으로
옮겼다. 시각·손잡이가 흐름 안에 서니 자리는 레이아웃이 정하고, 비워 둘 자리도
스킨마다 다시 정할 자리도 없어졌다. 그래서 이 시험이 지키는 것도 바뀐다:
**예약이 있는가**가 아니라 **묶음이 흐름 안에 있는가**다.

  · 묶음(`.idr`)은 흐름 항목이고 늘 줄의 오른끝에 선다(`margin-left:auto`) —
    한 줄에 서든 아랫줄로 내려가든 벨트가 시각 곁을 떠나지 않는다.
  · 시각과 손잡이는 `.idnow` 의 **한 칸을 겹쳐** 쓴다 — 손이 얹혀 손잡이가
    시각을 대신해도 칸 폭이 변하지 않아 줄이 흔들리지 않는다.
  · **칸의 폭은 시각이 정한다** — 손잡이는 그 칸 안에 떠 있다. 손잡이를 흐름에
    세우면 칸이 「이어 말하기」의 폭(54px)으로 넓어져, 그보다 짧은 시각을 단
    카드마다 벨트와 시각 사이에 빈 자리가 생긴다. 세로로는 안 갈라져도 사람은
    그 빈 자리를 갈라짐으로 읽는다 (주인 반려 2026-09-09 17:09).
  · 시각은 절대 위치로 뜨지 않는다 — 뜨는 순간 흐름 밖이 되어 좁은 카드에서
    묶음이 다시 갈라진다(주인 캡처 2026-09-09 15:54).
  · 그러므로 id 줄과 제목에는 **예약폭이 없다** — 어느 스킨에서도.

폭 0 스트럿(`::before`)은 그대로 산다: flex 는 줄의 첫 항목을 아랫줄로 못
내리므로, 점(livedot)이 없는 카드에서 식별자가 첫 항목이 되어 밀고 들어가던
결함(cork compact @1000px 실측 -1.19px)을 그 스트럿이 막는다.

실제로 겹치지 않는지는 브라우저가 그린 상자만 안다 — 그쪽은 test_id_realscale
이 잰다. 여기는 규칙의 모양만 본다.

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
        with self.subTest("the_group_stays_in_the_flow"):
            idr = [d for s2, d in self.rules if s2.endswith(".card .id .idr")]
            self.assertTrue(idr, "`.card .id .idr` 묶음이 없다 — 벨트와 시각이 "
                                 "낱개로 서면 좁은 카드에서 갈라진다")
            self.assertEqual("auto", _decl(idr[0], "margin-left"),
                             "묶음이 줄의 오른끝을 안 잡는다 — 아랫줄로 내려갈 "
                             "때 시각이 서는 쪽을 떠난다")
            self.assertIsNotNone(_decl(idr[0], "flex"),
                                 "묶음에 flex 가 없다 — 눌리면 안쪽이 접혀 "
                                 "벨트와 시각이 다시 갈라진다")
            for sel, dec in self.rules:
                if not (sel.endswith(".card .id") or ".card .id," in sel + ","):
                    continue
                if "::" in sel or ".id ." in sel:
                    continue
                val = _decl(dec, "padding-right")
                if val is None:
                    continue
                self.assertRegex(
                    val, r"^\s*0(px)?\s*$",
                    "%s 에 예약폭이 되살아났다(%s) — 시각은 흐름 안에 서므로 "
                    "비워 둘 자리가 없다" % (sel, val))
        with self.subTest("the_clock_and_the_handle_share_one_cell"):
            cell = [d for s2, d in self.rules if s2.endswith(".card .id .idnow")]
            self.assertTrue(cell, "`.card .id .idnow` 칸이 없다")
            self.assertEqual("grid", _decl(cell[0], "display"),
                             "칸이 격자가 아니다 — 시각과 손잡이가 나란히 서면 "
                             "손이 얹힐 때 칸 폭이 변해 줄이 흔들린다")
            kids = [d for s2, d in self.rules if s2.endswith(".card .id .idnow>*")]
            self.assertTrue(kids, "`.card .id .idnow>*` 규칙이 없다")
            self.assertEqual("1/1", (_decl(kids[0], "grid-area") or "").replace(" ", ""),
                             "칸 안의 둘이 같은 자리를 안 쓴다 — 겹쳐야 폭이 "
                             "변하지 않는다")
            # 흐름 밖으로 뜨면 안 되는 것은 **경과 시각**이다 — 그것이 벨트와
            # 한 묶음으로 움직여야 하는 쪽이다. 손잡이는 반대로 떠 있어야 한다:
            # 흐름에 서면 칸의 폭을 「이어 말하기」(54px)로 넓혀 짧은 시각을 단
            # 카드마다 벨트와 시각 **사이**에 빈 자리를 만든다 (REQ-20260909-084
            # 재작업 · 주인 반려 2026-09-09 17:09).
            for sel, dec in self.rules:
                if ".elapsed" not in sel:
                    continue
                self.assertNotEqual(
                    "absolute", (_decl(dec, "position") or ""),
                    "%s 가 흐름 밖으로 떴다 — 벨트만 흐름에 남아 좁은 카드에서 "
                    "묶음이 갈라진다" % sel)
            pick = [d for s2, d in self.rules if s2.endswith(".card .pickdoc")]
            self.assertTrue(pick, "`.card .pickdoc` 규칙이 없다")
            self.assertEqual(
                "absolute", (_decl(pick[0], "position") or ""),
                "손잡이가 흐름에 섰다 — 칸의 폭을 제 낱말로 넓혀 벨트와 시각 "
                "사이를 벌린다")
            self.assertEqual(
                "0", (_decl(pick[0], "right") or "").replace("px", ""),
                "손잡이가 칸의 오른끝에 안 맞는다 — 시각과 오른끝이 갈리면 손이 "
                "얹힐 때 자리가 옮겨 보인다")
            self.assertEqual(
                "relative", (_decl(cell[0], "position") or ""),
                "칸이 기준 상자가 아니다 — 떠 있는 손잡이가 칸이 아니라 카드 "
                "모서리에 붙어, 묶음이 내려가도 따라오지 않는다")
            self.assertIsNotNone(
                _decl(cell[0], "min-width"),
                "칸에 최소폭이 없다 — 경과 시각이 없는 카드에는 손잡이가 설 "
                "자리가 없고, 시각이 아주 짧으면 손잡이가 벨트를 덮는다")
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
            seen = False
            for sel, dec in self.rules:
                if ".card .t" not in sel:
                    continue
                seen = True
                val = _decl(dec, "padding-right")
                if val is None:
                    continue
                self.assertNotRegex(
                    val, r"[1-9]",
                    "%s 에 죽은 예약이 되돌아왔다(%s) — 제목 위 모서리에 뜨는 "
                    "것이 없으니 제목은 카드 폭을 다 쓴다" % (sel, val))
            self.assertTrue(seen, "`.card .t` 규칙이 없다")

if __name__ == "__main__":
    unittest.main()
