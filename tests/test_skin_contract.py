"""스킨은 재질을 바꾸고 어휘와 자리는 바꾸지 않는다 (REQ-20260910-028).

s9-design 규칙 1 은 2026-09-07 전 스킨 검수에서 세워졌고, 그 뒤로 **말로만**
있었다. 기계가 세지 않으니 calm 이 카드의 조각들을 `order` 로 다시 세워 식별자
줄을 맨 아래로 내리고, 이름 앞의 `@` 를 지우고 이니셜 원(`.av`)을 대신 세웠다 —
같은 사실이 스킨마다 다른 자리에, 같은 뜻이 스킨마다 다른 부품으로 선다
(REQ-20260910-009 designer 전수 점검 ③).

이 시험이 재는 것은 **카드 안**이다. 규칙 1 의 예(사람 이름·경과·더 보기)가
전부 카드의 조각이고, 판 껍데기는 예외가 아니라 다른 이야기다 — `soft` 는
「구조부터 다른 언어」로 세운 사이드바 셸이라(skins.css:2) 머리를 통째로
다시 세운다. 그 축까지 이 시험이 재면 규칙 1 이 아니라 스킨이라는 축 자체를
부정하게 된다.

지금 있는 어긋남은 아래 LEGACY 에 **선택자 한 줄씩** 적어 얼려 둔다. 지우면
시험이 「목록에서도 지우라」고 말하고, 늘리면 시험이 막는다 — 목록은 줄기만
한다. 어느 쪽으로 풀지(calm 을 base 로 되돌릴지, 제목 먼저를 전 스킨의 기본으로
올릴지)는 사람이 고를 취향이라 이 시험이 정하지 않는다.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "web", "css")

# 얼려 둔 어긋남 — (파일, 선택자, 속성). 2026-09-10 실측 그대로다.
LEGACY = {
    # 자리: calm 은 카드를 제목부터 읽게 다시 세운다 (식별자 줄이 맨 아래로).
    ("calm.css", '[data-skin="calm"] .card>*', "order"),
    ("calm.css", '[data-skin="calm"] .card .t', "order"),
    ("calm.css", '[data-skin="calm"] .card .xref', "order"),
    ("calm.css", '[data-skin="calm"] .card .m', "order"),
    ("calm.css", '[data-skin="calm"] .card .judge,[data-skin="calm"] .card>.rvpt,'
                 '[data-skin="calm"] .card>.rvmore,[data-skin="calm"] .card>.acts,'
                 '[data-skin="calm"] .card>.deedrow', "order"),
    ("calm.css", '[data-skin="calm"] .card .id', "order"),
    # 부품: calm 만 이름 앞의 `@`(board.css `.badge::before`)를 지우고
    # 이니셜 원(base 가 숨긴 `.av`)을 대신 세운다.
    ("calm.css", '[data-skin="calm"] .card .badge::before', "content"),
    ("calm.css", '[data-skin="calm"] .card .av', "display"),
}
# 목록에서 이미 빠진 줄: `[data-skin="calm"] .card .tag::before{content:none}`
# — base 에 `.tag::before` 가 없어 하는 일이 없던 한 줄이라 걷었다 (2026-09-10).


def _strip_comments(css):
    return re.sub(r"/\*[\s\S]*?\*/", "", css)


def _rules(css):
    """(선택자, 선언) 목록 — 주석은 걷고 @media 안쪽도 그대로 훑는다."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _strip_comments(css)):
        sel, dec = m.group(1).strip(), m.group(2).strip()
        if sel.startswith("@") or not dec:
            continue
        sel = re.sub(r"\s*([,>+~])\s*", r"\1", " ".join(sel.split()))
        out.append((sel, " ".join(dec.split())))
    return out


def _all_rules():
    for fn in sorted(os.listdir(CSS)):
        if not fn.endswith(".css"):
            continue
        with open(os.path.join(CSS, fn), encoding="utf-8") as f:
            for sel, dec in _rules(f.read()):
                yield fn, sel, dec


def _decl(dec, prop):
    m = re.search(r"(?:^|;)\s*" + prop + r"\s*:\s*([^;]+)", dec)
    return m.group(1).strip() if m else None


def _in_card(sel):
    return re.search(r"\.card\b", sel) is not None


def _skin(sel):
    return "[data-skin" in sel


class ASkinDoesNotMoveThingsInTheCard(unittest.TestCase):
    """자리 — 같은 사실은 어느 스킨에서나 카드의 같은 자리에 선다."""

    def test_no_skin_reorders_the_card(self):
        for fn, sel, dec in _all_rules():
            if not (_skin(sel) and _in_card(sel)):
                continue
            if _decl(dec, "order") is None:
                continue
            with self.subTest(fn + " :: " + sel[:70]):
                self.assertIn(
                    (fn, sel, "order"), LEGACY,
                    "스킨이 카드의 조각을 다시 세운다 (%s) — 스킨은 재질을 "
                    "바꾸고 자리는 바꾸지 않는다. 자리는 카드를 그리는 곳 "
                    "(web/app/card.js)이 정하고 전 스킨이 그대로 따른다" % fn)

    def test_no_skin_takes_a_piece_out_of_the_flow(self):
        """흐름 밖으로 빼는 것(absolute·fixed·float)도 자리를 바꾸는 일이다."""
        for fn, sel, dec in _all_rules():
            if not (_skin(sel) and _in_card(sel)):
                continue
            for prop in ("position", "float"):
                v = _decl(dec, prop)
                if v is None or v in ("static", "none"):
                    continue
                with self.subTest(fn + " :: " + sel[:60] + " " + prop):
                    self.assertIn(
                        (fn, sel, prop), LEGACY,
                        "스킨이 카드의 조각을 흐름에서 뺀다 (%s: %s) — 겹쳐 "
                        "그리는 것은 스킨의 몫이 아니다" % (fn, v))


class ASkinDoesNotSwapPartsInTheCard(unittest.TestCase):
    """어휘 — 같은 뜻은 어느 스킨에서나 같은 부품으로 선다."""

    def _hidden_by_base(self):
        """base(스킨 없는 규칙)가 `display:none` 으로 숨긴 선택자들."""
        out = set()
        for _fn, sel, dec in _all_rules():
            if _skin(sel):
                continue
            if _decl(dec, "display") == "none":
                out.update(sel.split(","))
        return out

    def test_no_skin_invents_or_erases_a_word(self):
        """`content` 는 화면에 글자·마크를 세우거나 지운다 — 어휘 그 자체다."""
        for fn, sel, dec in _all_rules():
            if not (_skin(sel) and _in_card(sel)):
                continue
            if _decl(dec, "content") is None:
                continue
            with self.subTest(fn + " :: " + sel[:70]):
                self.assertIn(
                    (fn, sel, "content"), LEGACY,
                    "스킨이 카드의 어휘를 바꾼다 (%s) — 세울 글자·마크는 "
                    "전 스킨이 같다" % fn)

    def test_no_skin_turns_on_a_part_the_others_hide(self):
        """base 가 숨긴 부품을 한 스킨만 켜면 같은 뜻에 부품이 둘이 된다."""
        hidden = self._hidden_by_base()
        for fn, sel, dec in _all_rules():
            if not (_skin(sel) and _in_card(sel)):
                continue
            v = _decl(dec, "display")
            if v is None or v == "none":
                continue
            tail = sel.split()[-1] if sel.split() else sel
            if tail not in hidden:
                continue
            with self.subTest(fn + " :: " + sel[:70]):
                self.assertIn(
                    (fn, sel, "display"), LEGACY,
                    "스킨이 저만 쓰는 부품을 세운다 (%s: %s) — 같은 뜻에 "
                    "부품이 둘이면 사람은 둘을 배운다" % (fn, tail))


class TheFrozenListOnlyShrinks(unittest.TestCase):
    """얼려 둔 목록은 줄기만 한다 — 사라진 줄은 목록에서도 사라져야 한다."""

    def test_every_frozen_line_is_still_in_the_css(self):
        live = {(fn, sel, p)
                for fn, sel, dec in _all_rules() if _skin(sel)
                for p in ("order", "content", "display", "position", "float")
                if _decl(dec, p) is not None}
        for entry in sorted(LEGACY):
            with self.subTest(entry[0] + " :: " + entry[1][:60]):
                self.assertIn(
                    entry, live,
                    "얼려 둔 어긋남이 CSS 에 없다 — 고쳤으면 이 시험의 "
                    "LEGACY 에서도 그 줄을 지워라(목록은 줄기만 한다)")


if __name__ == "__main__":
    unittest.main()
