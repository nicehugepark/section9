"""우선순위 표기가 읽히는가 (REQ-20260827-029).

사용자 불만: "카드나 문서 본문의 우선순위 표시하는 디자인에 대해서 불만이다.
예쁘지 않고, 직관적이라면 직관적이지만, 보기 불편하고 어떤 의미인지 모르는
사람 입장에서는 알수가 없다."

현상은 셋이었다.
  1) 카드·목록 306건이 전부 `▃ 50` — 50 은 처음 보는 사람에게 아무 뜻이 없고,
     게이지 마크 ▂▃▅▇ 는 10px 모노에서 두부(■)로 떨어져 얼룩으로 읽힌다.
  2) 문서 메타 행은 `■ 50 보통(normal) · 높을수록 먼저 집는다 (1~99, 기본 50)` —
     값·범례·설명문이 한 줄에 다 붙는다. 한 번 읽으면 끝인 설명이 늘 떠 있다.
  3) 그 표기가 카드 메타 줄의 첫 칸이라, 제목보다 먼저 눈에 걸린다.

이 테스트가 고정하는 계약:
  * 사람이 읽는 자리는 **등급 낱말**이다 — 50 이 아니라 '보통'.
  * 원래 가중치가 사라지지는 않는다 — data-prio(기계·정렬)와 문서 뷰어의
    `50/99`(사람) 두 곳에 남는다. 접은 것은 표기이지 값이 아니다.
  * 척도 설명은 상주하지 않는다 — 이미 있는 hovercard(doclink 미리보기)를
    재사용해 필요할 때만 연다. 새 어휘를 만들지 않는다.
  * 우선순위는 카드 메타 줄의 첫 칸이 아니다.

실행: python3 tests/ priority_legible
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


def _fn_body(html, name):
    """`function <name>(` 부터 다음 최상위 `function ` 선언 직전까지."""
    m = re.search(r"\nfunction\s+" + re.escape(name) + r"\s*\(", html)
    if not m:
        return ""
    rest = html[m.end():]
    nxt = re.search(r"\nfunction\s+\w+\s*\(", rest)
    return rest[:nxt.start()] if nxt else rest


class _Src(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()
        cls.prio = _fn_body(cls.html, "prioHTML")
        cls.card = _fn_body(cls.html, "cardHTML")


class GradeWordIsTheLabel(_Src):
    """① 숫자를 등급으로 접는다 — 다만 값을 잃지는 않는다."""

    def test_tier_names_are_rendered(self):
        """등급 낱말 네 개가 표기 함수 안에서 실제로 쓰인다."""
        self.assertRegex(self.prio, r"PRIO_TIERS\[",
                         "등급 이름표를 참조하지 않는다")
        table = re.search(r"const PRIO_TIERS = \{(.*?)\n\};", self.html, re.S)
        self.assertIsNotNone(table, "PRIO_TIERS 표를 찾지 못했다")
        for name in ("긴급", "높음", "보통", "낮음"):
            self.assertIn(name, table.group(1), "등급 이름 '%s' 이 없다" % name)

    def test_gauge_mark_is_gone(self):
        """게이지 마크는 글꼴 의존이라 두부(■)로 떨어진다 — 표기에서 뺀다."""
        # 주석에 남은 이력(왜 뺐는지)까지 금지하면 근거가 지워진다 —
        # 실제로 그려지는 곳(표기 함수·등급 표)만 본다.
        table = re.search(r"const PRIO_TIERS = \{.*?\};", self.html, re.S)
        for scope, where in ((self.prio, "prioHTML()"),
                             (table.group(0) if table else "", "PRIO_TIERS")):
            for glyph in ("▁", "▂", "▃", "▅", "▇"):
                self.assertNotIn(
                    glyph, scope,
                    "%s 에 게이지 마크 %s 가 남아 있다 — 이 불만의 절반이 "
                    "그 글자였다" % (where, glyph))
        self.assertNotIn("pmark", self.prio, ".pmark 잔재가 남아 있다")
        self.assertFalse(
            re.search(r"[^{}]*\.pmark[^{}]*\{", self.html),
            ".pmark CSS 규칙이 남아 있다 — 죽은 선택자다")

    def test_card_label_carries_no_raw_number(self):
        """카드가 그리는 '글자'에는 숫자가 없다 — 값은 속성으로만 나간다.

        data-prio 는 남아야 한다(정렬·테스트·기계가 읽는 축). 사라지는 것은
        사람이 읽을 이유가 없는 `50` 이라는 글자다."""
        self.assertIn("data-prio=", self.prio, "기계가 읽는 값이 사라졌다")
        self.assertIn("pname", self.prio, "등급 낱말을 담는 자리가 없다")

    def test_number_survives_in_the_viewer_only(self):
        """정확한 값은 '읽는 자리'(문서 뷰어)에만 남는다 — `50/99` 형태로
        척도까지 함께 가르친다."""
        self.assertIn("pnum", self.prio, "정확한 값 자리가 통째로 사라졌다")
        self.assertRegex(
            self.prio, r"full\s*\?", "카드용/문서용 표기가 갈리지 않는다")
        self.assertRegex(self.html, r"PRIO_MAX\s*=\s*99",
                         "척도 상한(99) 상수가 없다 — `50/99` 를 못 그린다")

    def test_viewer_asks_for_the_full_form(self):
        fields = re.search(r"const fields = \[(.*?)\n  \];", self.html, re.S)
        self.assertIsNotNone(fields, "뷰어 메타 표(fields)를 찾지 못했다")
        self.assertRegex(fields.group(1), r"prioHTML\(m,\s*true\)",
                         "문서 뷰어가 전체 표기를 요구하지 않는다")


class ScaleIsLearnedOnDemand(_Src):
    """② 설명문을 상주시키지 않는다 — 이미 있는 hovercard 로 부른다."""

    def test_permanent_sentence_is_gone(self):
        """항상 떠 있던 척도 설명문이 메타 행에서 사라진다."""
        fields = re.search(r"const fields = \[(.*?)\n  \];", self.html, re.S)
        self.assertNotIn(
            "높을수록 먼저 집는다", fields.group(1),
            "설명문이 여전히 메타 행에 상주한다 — 한 번 읽으면 끝인 문장이다")

    def test_scale_uses_the_existing_hovercard(self):
        """새 팝오버 컴포넌트를 만들지 않는다 — doclink 미리보기와 같은 카드."""
        self.assertRegex(self.html, r"function showPrioHover\(",
                         "척도를 여는 경로가 없다")
        body = _fn_body(self.html, "showPrioHover")
        self.assertIn("hovercard.innerHTML", body,
                      "기존 hovercard 를 쓰지 않고 새 어휘를 만들었다")
        self.assertIn("PRIO_DEFAULT", body, "기본값을 가르치지 않는다")

    def test_scale_opens_for_both_hands(self):
        """마우스와 키보드 둘 다 — 이 화면이 REQ-20260827-013 에서 정한 규칙."""
        self.assertRegex(
            self.html, r'closest\("a\.doclink[^"]*\.prio',
            "hover 대상 선택자에 우선순위가 들어가지 않았다 "
            "(mouseover/focusin 두 경로가 같은 선택자를 쓴다)")

    def test_tooltip_answers_the_direction_question(self):
        """훑는 자리(카드·목록)는 title 툴팁 한 문장으로 답한다 —
        '높은 게 급한 건가'가 이 불만의 본체다."""
        self.assertIn("title=", self.prio, "카드 표기에 툴팁이 없다")
        self.assertRegex(self.prio, r"클수록|높을수록",
                         "툴팁이 방향(큰 값이 먼저)을 말하지 않는다")


class PriorityDoesNotLeadTheCard(_Src):
    """③ 카드에서 우선순위가 앞장서지 않는다."""

    def test_user_badge_comes_first(self):
        """메타 줄의 첫 칸은 담당자다 — 우선순위는 그 뒤."""
        self.assertLess(
            # 담당자 칸이 ownerBadgeHTML 로 묶인 뒤로 카드 원문에는
            # class="badge" 글자가 없다 — 계약(첫 칸이 담당자다)은 그대로다.
            self.card.index("ownerBadgeHTML(r)"), self.card.index("prioHTML(r)"),
            "우선순위가 여전히 카드 메타 줄의 첫 칸이다")

    def test_still_ahead_of_size(self):
        """뒤로 밀되 크기보다는 앞이다 — 무엇부터 집을지가 먼저다."""
        self.assertLess(self.card.index("prioHTML(r)"),
                        self.card.index("r.size ?"),
                        "우선순위가 크기 뒤로 밀렸다")

    def test_doclist_row_leads_with_the_id(self):
        """Docs 목록 행도 마찬가지 — 문서 ID 가 먼저 읽힌다."""
        row = re.search(r'<div class="id">.*?prioHTML\(r\).*?</div>', self.html)
        self.assertIsNotNone(row, "Docs 목록 행의 id 칸을 찾지 못했다")
        seg = row.group(0)
        self.assertLess(seg.index("shortId(r.id)"), seg.index("prioHTML(r)"),
                        "우선순위가 문서 ID 앞에 선다")

    def test_default_tier_stays_quiet(self):
        """306건 중 대부분이 기본값이다 — 그 낱말이 잉크를 끌면 화면이 얼룩진다.
        조용함은 색을 빼서가 아니라 무게로 만든다(대비는 지킨다)."""
        rules = {m.group(1).strip(): m.group(2) for m in re.finditer(
            r"([^{}\n]*\.prio\[data-tier=\"\w+\"\][^{}]*)\{([^}]*)\}", self.html)}
        loud = [s for s in rules
                if 'data-tier="normal"' in s or 'data-tier="low"' in s]
        for sel in loud:
            self.assertNotRegex(
                rules[sel], r"font-weight\s*:\s*(700|800|bold)",
                "%s 가 기본 등급을 굵게 만든다" % sel)
            self.assertNotRegex(
                rules[sel], r"var\(--c-(blocked|inprogress|open|review)\)",
                "%s 가 기본 등급에 상태 잉크를 쓴다" % sel)

    def test_urgent_is_readable_without_colour(self):
        """색을 못 보는 조건에서도 등급이 갈려야 한다 — 이제 낱말 자체가
        그 채널이다. 그러니 낱말을 지우고 색만 남기는 회귀를 막는다."""
        self.assertNotRegex(
            self.prio, r'aria-hidden="true"[^>]*>\$\{name',
            "등급 낱말이 보조기술에서 숨겨진다")


if __name__ == "__main__":
    unittest.main()
