"""Audit 표의 규율 — 열·정렬·밀도·같은 값 접기 (REQ-20260907-026-62x6).

검수(REQ-20260907-012)가 audit 표에서 둘을 짚었다. ① 걸러 놓고 보면 종류·남긴
사람·세션 열이 스무 행 내리 같은 값이라, 눈이 읽을 것이 없는 열 셋이 폭을 차지했다.
② 표를 설명하는 두 문장이 판 위에 붙박이였다. 그리고 그 판정을 내릴 잣대가 없었다 —
s9-design 에 표(테이블) 절이 아예 없었다.

이 시험이 지키는 계약은 아홉이다. 표의 규율은 화면 조각 여러 개(audit.js·docs.css·
density.css·tablet.css·skins.css)에 흩어져 사는데, 계약이 보는 것은 브라우저가 받는
한 장이라 `webasset.index_path()` 로 이어 붙인 그 한 장만 본다.

실행: python3 tests/ audit_table
"""
import os
import re
import unittest
from webasset import index_path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "harness", "claude", "skills", "s9-design", "SKILL.md")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class AuditTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = _load(index_path())

    def rule(self, selector):
        """CSS 규칙 하나의 본문 — `.audit th{…}` 의 중괄호 안."""
        m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", self.page)
        self.assertIsNotNone(m, "%s 규칙이 없다" % selector)
        return m.group(1)

    # ── S1·S2 같은 값 접기 ───────────────────────────────────────────────
    def test_repeated_values_are_folded_into_the_first_row(self):
        self.assertIn("const once = (col, key, html)", self.page,
                      "연속 같은 값을 접는 자리가 없다 (s9-design 표 절 8)")
        self.assertIn("seen[col] === key", self.page,
                      "앞 행과 값이 같은지로 판정해야 한다 — 값이 바뀌면 다시 보인다")
        self.assertIn('class="dup"', self.page)
        for col in ("kind", "by", "ses"):
            self.assertIn('once("%s"' % col, self.page,
                          "%s 열은 폭이 고정된 열이라 접히는 대상이다" % col)
        # 시각은 행마다 바뀌고 사건 내용은 이 표의 본문이다 — 접지 않는다
        self.assertNotIn('once("ev"', self.page)
        self.assertNotIn('once("ts"', self.page)

    # ── S3 접은 값을 잃지 않는다 ─────────────────────────────────────────
    def test_the_folded_value_is_not_lost(self):
        body = self.rule(".audit td .dup")
        self.assertIn("clip-path:inset(50%)", body)
        self.assertIn("width:1px", body)
        for lost in ("display:none", "visibility:hidden"):
            self.assertNotIn(lost, body,
                             "값을 지우면 화면낭독기와 복사가 값을 잃는다")

    # ── S4 열 머리 얼굴 ─────────────────────────────────────────────────
    def test_the_column_head_face_is_ready_for_hangul(self):
        body = self.rule(".audit th")
        self.assertNotIn("var(--mono)", body,
                         "mono 는 한글을 대체 글꼴로 떨어뜨려 얼굴이 두 벌이 된다")
        self.assertNotIn("uppercase", body, "uppercase 는 한글에 아무 일도 하지 않는다")
        self.assertNotIn("var(--faint)", body, "열 머리는 읽어야 하는 글자다")
        self.assertIn("font-size:11px", body)
        self.assertIn("font-weight:600", body)
        self.assertIn("color:var(--muted)", body)
        self.assertIn("text-transform:capitalize", body)

    # ── S5 열 순서 ──────────────────────────────────────────────────────
    def test_the_variable_width_column_is_last(self):
        m = re.search(r"<thead><tr>(.*?)</tr></thead>", self.page)
        self.assertIsNotNone(m, "audit 표의 열 머리를 찾지 못했다")
        heads = re.findall(r"<th>([^<]+)</th>", m.group(1))
        # 라벨은 한글이다 (REQ-20260907-018) — designer 가 세운 한글 열 머리
        # 얼굴(본문체 11px·600·muted·capitalize) 위에 읽히는 낱말이 선다.
        self.assertEqual(["시각", "종류", "남긴 사람", "세션", "내용"], heads,
                         "폭이 고정된 열이 앞, 폭이 변하는 본문 열이 마지막이다 (표 절 3)")

    # ── S6 안내문이 상주하지 않는다 ──────────────────────────────────────
    def test_the_caption_above_the_table_is_folded(self):
        self.assertIn('<details class="cap">', self.page)
        self.assertNotIn('<div class="cap">', self.page,
                         "표 위 안내는 접어 둔다 — 두 번째부터는 자리만 차지한다")
        self.assertNotIn('<details class="cap" open', self.page, "기본은 닫힘이다")

    # ── S7 행 밀도 눈금 ─────────────────────────────────────────────────
    def test_the_row_density_has_two_steps_on_the_four_grid(self):
        self.assertIn("padding:8px 14px", self.rule(".audit td"))
        self.assertIn("padding:4px 10px", self.rule('[data-density="compact"] .audit td'))

    # ── S8 줄무늬와 헤어라인 ─────────────────────────────────────────────
    def test_zebra_and_hairline_do_not_stack(self):
        zebra = re.search(r'\[data-skin="grid"\][^{]*\.audit tbody tr:nth-child\(even\)',
                          self.page)
        self.assertIsNotNone(zebra, "grid 스킨의 줄무늬 규칙이 없다")
        self.assertIn("border-bottom:0", self.rule('[data-skin="grid"] .audit td'),
                      "줄무늬를 쓰는 스킨은 헤어라인을 내린다 (표 절 5)")

    # ── S9 폭이 모자랄 때 (회귀 REQ-20260906-092) ────────────────────────
    def test_the_table_still_scrolls_sideways_when_the_width_runs_out(self):
        self.assertIn("overflow-x:auto", self.rule(".audit .tblwrap"))
        # 최소폭은 태블릿 폭 규칙 안에 산다 — 규칙 하나가 아니라 그 줄을 찾는다
        self.assertRegex(self.page, r"\.audit table\{min-width:680px\}",
                         "최소폭이 없으면 가로 스크롤 대신 셀이 눌린다")

    # ── S10 잣대가 있다 ────────────────────────────────────────────────
    def test_the_design_system_has_a_table_section(self):
        doc = _load(SKILL)
        self.assertIn("## 표(테이블)", doc, "표 절이 없으면 판단 근거가 없다")
        sec = doc.split("## 표(테이블)", 1)[1].split("\n## ", 1)[0]
        for rule in ("열 머리", "tabular-nums", "compact", "헤어라인",
                     "min-width", "doclink", "clip-path"):
            self.assertIn(rule, sec, "표 절에 「%s」 규율이 빠졌다" % rule)


if __name__ == "__main__":
    unittest.main()
