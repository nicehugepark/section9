"""카드의 모서리는 안여백을 따라온다 (REQ-20260831-010-62x6).

사용자가 본 것: slate·cork 스킨에서 카드의 경과 시각이 식별자보다 조금 낮게
서고, grid 에서는 더 낮게 선다. 상태별 결함이 아니라 **그 스킨의 모든 카드가
똑같이** 어긋났다.

뿌리는 자가 두 개였다는 것이다. 경과 시각(.elapsed)과 집는 손잡이(.pickdoc)는
카드 모서리에 절대 위치로 서는데, 그 좌표를 `top:10px; right:12px` 처럼 손으로
적어 두었다. 스킨은 안여백만 바꾸면 되는 줄 알고 `padding:7px 12px` 를 적었고,
좌표는 기본값 자리에 그대로 남았다. 실측(CDP, 배율 2):

    ledger 11px  -0.25px   soft  11px  (제 줄)      grid  7px  +3.75px
    slate   9px  +1.75px   cork   9px  +1.75px      calm 14px  +0.25px

같은 수를 두 곳에 적으면 다음 사람이 한쪽만 고친다 — 이 파일이 그 두 곳을 다시
못 생기게 한다. 계약은 셋이다.

  ① **자는 하나다.** 카드의 안여백은 `--card-pt/--card-pb/--card-px` 가 쥐고,
     padding 도 모서리 좌표도 그 토큰을 읽는다. 스킨은 토큰만 바꾼다 —
     `.card` 에 padding 을 직접 적는 규칙이 있으면 좌표가 다시 떨어져 나간다.
  ② **줄 상자도 하나다.** 좌표를 맞춰도 줄 높이가 다르면 중심이 다르다.
     시각 앞의 ⏱ 는 이모지 글꼴에서 와 제 줄 상자를 13.5px 로 부풀렸고,
     식별자는 12px 이었다 — 스킨과 무관한 0.75px 상수 어긋남이 여기서 났다.
     한 줄에 서는 셋(.id · .elapsed · .pickdoc)이 `--card-edge` 하나를 읽는다.
  ③ **줄에 선 벨트는 줄을 부풀리지 않는다.** `.acts` 는 제 줄에 설 때 윗여백을
     갖는 부품이라 스킨·밀도가 그 값을 저마다 다시 적는다 — 그 중 하나가 id
     줄의 벨트에 닿으면 줄이 부풀고 가운데 정렬된 식별자가 밀린다(calm compact
     에서 실제로 2px 밀렸다). 여백을 0 으로 돌리는 자리는 한 곳뿐이다.

실행: python3 tests/ card_corner
"""
import re
import unittest

from webasset import index_path

INDEX = index_path()

# 좌표를 상수로 굳히면 안 되는 부품들 — 카드 모서리에 절대 위치로 선다.
CORNER = (".elapsed", ".pickdoc")
# 모서리 좌표가 읽어야 하는 자.
RULER = ("--card-pt", "--card-pb", "--card-px")
# 모서리 줄에 서는 셋 — 이 셋을 겨누는 규칙은 줄높이를 `--card-edge` 로만 적는다.
CORNER_LEAF = re.compile(r"\.(elapsed|pickdoc|id)$")


def _targets_corner(part):
    """이 선택자가 겨누는 **마지막 원소**가 모서리 줄의 셋 중 하나인가.

    마지막 원소만 보는 까닭: `.card .id .idn` 은 식별자 줄 **안의** 다른 부품이라
    제 줄높이를 가져도 된다. 줄 상자를 정하는 것은 셋 자신뿐이다.
    """
    bare = re.sub(r"::?[a-zA-Z-]+(\([^)]*\))?", "", part).strip()
    leaf = re.split(r"[\s>+~]+", bare)[-1] if bare else ""
    return bool(CORNER_LEAF.search(leaf))


def _css(src):
    """주석을 걷어낸 CSS 만 — 주석은 고쳐 낸 옛 값을 근거로 인용한다."""
    return re.sub(r"/\*[\s\S]*?\*/", " ", src)


def _rules(src):
    out = []
    for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", src):
        out.append((" ".join(m.group(1).split()), m.group(2)))
    return out


def _decl(dec, prop):
    """선언 덩어리에서 한 속성의 값 — 없으면 None."""
    m = re.search(r"(?:^|;)\s*%s\s*:([^;]*)" % re.escape(prop), dec)
    return m.group(1).strip() if m else None


class TheCardHasOneRuler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.rules = _rules(_css(f.read()))
        cls.card = [(s, d) for s, d in cls.rules
                    if re.search(r"(^|[\s,])\.card$", s)]
        cls.corner = [(s, d) for s, d in cls.rules
                      if any(c in s for c in CORNER)]

    def test_the_card_has_one_ruler(self):
        """TheCardHasOneRuler 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_ruler_is_declared_on_the_card"):
            base = [d for s, d in self.card if s == ".card"]
            self.assertTrue(base, "`.card` 기본 규칙이 없다")
            for tok in RULER + ("--card-edge",):
                self.assertTrue(any(tok in d for d in base),
                                "카드가 %s 를 세우지 않는다 — 세우지 않으면 "
                                "모서리 좌표가 읽을 자가 없다" % tok)
        with self.subTest("the_padding_reads_the_ruler"):
            base = [d for s, d in self.card if s == ".card"]
            pad = _decl(base[0], "padding")
            self.assertIsNotNone(pad, "`.card` 에 padding 선언이 없다")
            for tok in RULER:
                self.assertIn("var(%s" % tok, pad,
                              "안여백이 %s 를 안 읽는다: %s" % (tok, pad))
        with self.subTest("no_skin_writes_the_padding_again"):
            again = [s for s, d in self.card
                     if s != ".card" and _decl(d, "padding") is not None]
            self.assertEqual(
                again, [],
                "이 규칙들이 카드 안여백을 자 밖에서 다시 적는다: %s — "
                "`--card-pt/--card-pb/--card-px` 로 옮겨라" % again)
        with self.subTest("the_corner_never_hardcodes_a_coordinate"):
            for sel, dec in self.corner:
                for side in ("top", "right", "bottom", "left"):
                    val = _decl(dec, side)
                    if val is None:
                        continue
                    self.assertNotRegex(
                        val, r"-?\d+(\.\d+)?px",
                        "%s 의 %s 이 상수 px 이다(%s) — `var(--card-p*)` 로 "
                        "안여백을 읽어라" % (sel, side, val))
        with self.subTest("the_corner_line_is_one_number"):
            want = {".card .id": None, ".elapsed": None, ".card .pickdoc": None}
            for sel, dec in self.rules:
                if sel in want and _decl(dec, "line-height"):
                    want[sel] = _decl(dec, "line-height")
            for sel, val in want.items():
                self.assertIsNotNone(val, "%s 에 줄높이 선언이 없다" % sel)
                self.assertIn("var(--card-edge", val,
                              "%s 의 줄높이가 자를 안 읽는다: %s" % (sel, val))
        with self.subTest("no_skin_writes_the_corner_line_again"):
            # **덮어쓰기까지 봐야 계약이다** (REQ-20260910-042). 위 검사는 선택자
            # 이름이 정확히 맞을 때만 봤다 — `[data-skin="soft"] .card .elapsed`
            # 는 이름이 달라 검사에 들지 않았고, 거기 남아 있던 `line-height:1.4`
            # 가 soft 에서만 시계 그림을 숫자보다 1px 위에 세웠다. `.elapsed` 는
            # 그림과 글자를 `align-items:center` 로 맞추므로, 줄 상자가 12px 에서
            # 14px 로 바뀌면 11px 그림이 화소 격자에 얹히는 자리가 갈린다.
            # 스킨이 이 줄의 키를 달리 하려면 고칠 것은 `.card` 의 `--card-edge`
            # 다 — 그래야 셋이 함께 온다.
            off = []
            for sel, dec in self.rules:
                val = _decl(dec, "line-height")
                if not val or "var(--card-edge" in val:
                    continue
                for part in sel.split(","):
                    if _targets_corner(part):
                        off.append("%s{line-height:%s}" % (part.strip(), val))
            self.assertEqual(
                off, [],
                "모서리 줄의 줄높이를 자 밖에서 다시 적는 규칙이 있다: %s — "
                "스킨이 이 줄을 달리 하려면 `.card` 의 `--card-edge` 를 바꿔라"
                % off)
        with self.subTest("the_who_line_never_folds"):
            # **1행은 접히지 않는다** (REQ-20260910-009 4차 반려. 주인 2026-09-10
            # 13:44: 「들여쓰기도 안맞고, 가려지고, 깨지고」).
            #
            # 실서버 실측: 카드 23장 중 **14장에서 이 줄이 접혔다**(줄높이 18 ·
            # 36 · 52px 세 갈래). 식별자 왼끝은 23장 전부 34px 로 같았으니,
            # 「들여쓰기가 안 맞는다」로 읽힌 것은 id 줄이 아니라 이 줄이 카드마다
            # 다른 키를 갖는 것이었다. REQ-20260907-022 의 주석은 이미 「nowrap
            # 이고, 넘치면 줄이 아니라 프로젝트 이름이 줄어든다」고 적어 두었는데
            # **CSS 에는 그 말이 없었다** — 계약이 주석에만 있으면 지켜지지 않는다.
            #
            # 픽스처가 아니라 실서버에서만 잡힌 까닭은 「만든 사람 백그라운드
            # 작업」 같은 **실제로 긴 값**이 픽스처에 없었기 때문이다. 그래서
            # 여기서는 값이 아니라 **규칙**을 잰다.
            mw = [d for s2, d in self.rules if s2 == ".card .m.mwho"]
            self.assertTrue(mw, "`.card .m.mwho` 규칙이 없다")
            self.assertEqual("nowrap", _decl(mw[0], "flex-wrap"),
                             "1행이 접힐 수 있다 — 「누구」와 「어디」가 위아래로 "
                             "갈리면 카드마다 키가 달라진다")
            self.assertIsNotNone(_decl(mw[0], "min-height"),
                                 "담당 배지가 없는 카드는 이 줄이 낮아진다 — "
                                 "자리를 잡아 두지 않으면 키가 두 값이 된다")
        with self.subTest("nothing_in_the_who_line_paints_over_its_neighbour"):
            # 값이 제 상자보다 커지면 **잘려야** 한다. 바닥(min-width)만 주고
            # 자르지 않았더니 「만든」이 옆의 「section9」 위에 겹쳐 찍혔다
            # (4배 캡처, REQ-20260910-009 4차) — 주인이 말한 「가려지고」를
            # 고치다가 새로 만든 자리다.
            for name in (".card .m.mwho .lin", ".card .m.mwho .linv"):
                hit = [d for s2, d in self.rules if s2 == name]
                self.assertTrue(hit, "%s 규칙이 없다" % name)
                self.assertEqual("hidden", _decl(hit[0], "overflow"),
                                 "%s 가 제 상자 밖으로 넘친다 — 넘친 글자는 "
                                 "이웃의 잉크 위에 앉는다" % name)
            cap = [d for s2, d in self.rules if s2 == ".card .m.mwho .lincap"]
            self.assertTrue(cap, "계보 라벨 규칙이 없다")
            self.assertEqual("none", _decl(cap[0], "flex"),
                             "라벨이 줄어든다 — 「만…」 처럼 라벨의 부스러기만 "
                             "남으면 뜻이 없고 고장으로 보인다. 줄어드는 것은 값이다")
        with self.subTest("the_judgement_word_never_breaks"):
            # `반려 in-progress` 가 `반려 in-` / `progress` 로 갈라졌다
            # (실서버 review 열). 상태 값은 사람이 CLI 에 그대로 치는 글자라
            # 줄일 수 없다(규약 2조 ⑤) — 낱말을 지키고 줄을 내준다.
            bt = [d for s2, d in self.rules if s2 == ".acts button.deed"]
            self.assertTrue(bt, "판정 버튼 규칙이 없다")
            self.assertEqual("nowrap", _decl(bt[0], "white-space"),
                             "버튼 안에서 낱말이 접힌다")
        with self.subTest("the_belt_never_swells_the_id_line"):
            nail = [d for s, d in self.rules
                    if s == ".card .id .acts.deedbelt"]
            self.assertTrue(nail, "id 줄 벨트의 자리 규칙이 없다")
            self.assertEqual(_decl(nail[0], "margin-top"), "0",
                             "id 줄 벨트의 윗여백이 0 으로 못박히지 않았다")
            self.assertEqual(_decl(nail[0], "margin-bottom"), "0",
                             "id 줄 벨트의 아랫여백이 0 으로 못박히지 않았다")

if __name__ == "__main__":
    unittest.main()
