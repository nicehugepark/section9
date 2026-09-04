"""우선순위가 화면에 보이는가 (REQ-20260826-005 반려 재작업).

반려 사유: "오늘 새로 만든 요청 문서에서 우선순위 값이 하나도 보이지 않는다.
숨겨져있는건가? 판단할 수 없다."

원인은 표기 조건이었다. 직전 구현은 기본값(50)과 다를 때만 `!75` 를 찍었는데
기존 문서 299건과 그날 만든 문서가 전부 기본값이라 결과적으로 어디에도 값이
없었다. 대시보드에는 표기 자체가 없었다.

이 테스트가 고정하는 것은 하나다 — **도입 직후에는 보이지 않는 축은 없는 축**.
기본값도 항상 보여야 축의 존재가 읽히고 무엇을 올릴지 판단할 수 있다. 그래서
"조건부 표기"로 되돌아가는 회귀를 계약으로 막는다.

DOM 계약(테스트가 검사하는 이름):
  <span class="prio[ pfull]" data-prio="75" data-tier="high" …>…</span>
  등급 파생: >=90 urgent · >=75 high · >=50 normal · 그 아래 low

후속: REQ-20260827-029 에서 **사람이 읽는 글자**가 숫자에서 등급 낱말로 바뀌었다
(카드 306장이 전부 `50` 을 달고 있어도 뜻이 안 읽혔다는 두 번째 불만). 이 파일이
지키는 계약은 그대로다 — 축이 조건 없이 보일 것, 파생·정렬 진입점이 하나일 것,
색면을 칠하지 않을 것. 표기의 모양은 test_priority_legible.py 가 맡는다.

표기는 세 화면(보드 카드·Docs 목록 행·문서 뷰어 메타)이 공용 함수 prioHTML()
하나로 그린다. 그래서 "카드에 마크업이 있는가"가 아니라 "카드가 그 함수를
조건 없이 부르는가 + 그 함수가 계약대로 그리는가" 두 갈래로 검사한다 —
마크업 위치를 고정하면 공용화가 회귀로 잡히는 잘못된 계약이 된다.

실행: python3 tests/ priority_visible
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


class CardShowsPriority(unittest.TestCase):
    """보드 카드 — 우선순위는 조건 없이 항상 찍힌다."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()
        cls.card = _fn_body(cls.html, "cardHTML")
        cls.prio = _fn_body(cls.html, "prioHTML")

    def test_card_shows_priority(self):
        """보드 카드 — 우선순위는 조건 없이 항상 찍힌다."""
        with self.subTest("cardhtml_exists"):
            self.assertTrue(self.card, "cardHTML() 를 찾지 못했다")
        with self.subTest("card_renders_prio_span"):
            self.assertIn("prioHTML(r)", self.card,
                          "보드 카드가 우선순위를 그리지 않는다 — 반려 사유 그대로다")
            # 클래스 목록은 문서 뷰어용 pfull 로 갈라진다 (REQ-20260827-029) —
            # 여는 따옴표까지만 본다. 여기서 고정할 것은 이름이지 문자열 모양이 아니다.
            self.assertIn('class="prio', self.prio,
                          "prioHTML() 이 .prio 를 그리지 않는다")
        with self.subTest("card_carries_numeric_value"):
            self.assertIn("data-prio=", self.prio)
            self.assertIn("data-tier=", self.prio)
            self.assertIn("pnum", self.prio, "사람이 읽는 숫자 자리가 없다")
        with self.subTest("all_three_surfaces_share_one_renderer"):
            self.assertGreaterEqual(
                len(re.findall(r"prioHTML\(", self.html)), 4,
                "prioHTML() 선언 + 세 화면 호출이 모두 있어야 한다")
        with self.subTest("card_prio_is_unconditional"):
            guard = re.search(
                r"(priority|prio)\s*(!==|!=|===|==|>|<|>=|<=)\s*"
                r"(50|PRIORITY_DEFAULT|PRIO_DEFAULT)\s*\?", self.card)
            self.assertIsNone(
                guard,
                "카드의 우선순위 표기가 기본값 비교로 감춰진다: "
                + (guard.group(0) if guard else ""))
            # 조건부 표기가 어떻게 생겼는지 아는 상태로 위를 단언한다는 근거
            self.assertIn("r.size ?", self.card,
                          "전제 확인 실패: .size 의 조건부 표기가 사라졌다")
        with self.subTest("prio_precedes_size_on_meta_row"):
            self.assertLess(self.card.index("prioHTML(r)"),
                            self.card.index("r.size ?"),
                            "우선순위가 크기 뒤에 온다")

class TierDerivation(unittest.TestCase):
    """등급은 값 하나에서 파생된다 — 저장은 수치, 표기는 등급."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()

    def test_single_derivation_point(self):
        """파생이 카드·뷰어에 각각 복제되면 두 화면의 등급이 갈라진다."""
        self.assertEqual(
            len(re.findall(r"function\s+prioTier\s*\(", self.html)), 1,
            "prioTier() 파생 함수가 없거나 둘 이상이다")

    def test_thresholds(self):
        body = _fn_body(self.html, "prioTier")
        for cut, name in ((90, "urgent"), (75, "high"), (50, "normal")):
            self.assertRegex(body, r">=\s*%d" % cut,
                             "%s 경계(%d)가 없다" % (name, cut))
        for name in ("urgent", "high", "normal", "low"):
            self.assertIn('"%s"' % name, body, "%s 등급이 없다" % name)


class ViewerShowsPriority(unittest.TestCase):
    """문서 뷰어 메타 표 — "숨겨져있는건가?" 에 대한 직접적인 답."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()

    def test_meta_table_has_priority_row(self):
        fields = re.search(r"const fields = \[(.*?)\n  \];", self.html,
                           re.S)
        self.assertIsNotNone(fields, "뷰어 메타 표(fields)를 찾지 못했다")
        self.assertIn('"priority"', fields.group(1),
                      "메타 표에 priority 행이 없다 — 문서를 열어도 값을 볼 수 없다")


class VisualConstraints(unittest.TestCase):
    """프로젝트 시각 규약: 색은 면이 아니라 글자·마크·타이포·깊이로."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()
        # `.prio` 를 선택자에 포함하는 모든 CSS 규칙의 (선택자, 본문)
        cls.rules = [(m.group(1), m.group(2)) for m in re.finditer(
            r"([^{}]*\.prio[^{}]*)\{([^}]*)\}", cls.html)]

    def test_visual_constraints(self):
        """프로젝트 시각 규약: 색은 면이 아니라 글자·마크·타이포·깊이로."""
        with self.subTest("prio_is_styled"):
            self.assertTrue(self.rules, ".prio 에 대한 CSS 규칙이 하나도 없다")
        with self.subTest("no_color_fill"):
            for sel, body in self.rules:
                for decl in re.findall(r"background(?:-color)?\s*:([^;]+)", body):
                    v = decl.strip().lower()
                    ok = (v.startswith("none") or v.startswith("transparent")
                          or v == "inherit")
                    self.assertTrue(
                        ok, "%s 가 .prio 에 색면을 칠한다: background:%s"
                            % (sel.strip(), decl.strip()))
        with self.subTest("not_all_achromatic"):
            joined = " ".join(b for _, b in self.rules)
            self.assertRegex(
                joined, r"(hsl|--c-|--accent|--warn|--hot|color-mix)",
                ".prio 규칙이 전부 무채색이다 — 등급 대비가 생기지 않는다")

class BoardOrder(unittest.TestCase):
    """조회 순서가 우선순위를 따른다 (유도이지 강제가 아니다)."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()

    def test_board_order(self):
        """조회 순서가 우선순위를 따른다 (유도이지 강제가 아니다)."""
        with self.subTest("single_ordering_point"):
            self.assertEqual(
                len(re.findall(r"const\s+workOrder\s*=", self.html)), 1,
                "workOrder 정렬 진입점이 없거나 둘 이상이다")
        with self.subTest("priority_is_primary_key"):
            m = re.search(r"const\s+workOrder\s*=(.*?);\n", self.html, re.S)
            self.assertIsNotNone(m)
            body = m.group(1)
            # 값 읽기는 prioOf() 하나를 거친다(표기와 같은 파생) — 정렬만 raw
            # r.priority 를 직접 보면 값이 없거나 망가진 문서에서 순서와 표기가
            # 갈린다.
            self.assertIn("prioOf(", body, "정렬이 우선순위를 보지 않는다")
            self.assertLess(body.index("prioOf("),
                            body.index("updated"),
                            "우선순위가 1차 키가 아니다")
        with self.subTest("filtered_uses_work_order"):
            body = _fn_body(self.html, "filtered")
            self.assertIn("workOrder(catalog)", body,
                          "filtered() 가 workOrder 를 쓰지 않는다")
        with self.subTest("default_priority_constant"):
            self.assertRegex(self.html, r"PRIO_DEFAULT\s*=\s*50",
                             "기본값 50 상수가 없다")

if __name__ == "__main__":
    unittest.main()
