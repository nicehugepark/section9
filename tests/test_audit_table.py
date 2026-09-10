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

    # ── E1 날짜는 하루 머리로 선다 (REQ-20260910-025) ────────────────────
    def test_the_date_stands_once_a_day_above_the_rows(self):
        """행 안에서 접는 것만으로는 열이 안 접힌다 — 첫 행이 열 폭을 잡는다.

        P5 는 날짜에도 접기를 걸었으나 첫 행은 접히는 대상이 아니라 날짜를 온전히
        보였고, 그 한 행이 시각 열을 130px 로 잡아 2행부터 네 칸이 내리 비었다.
        날짜를 하루 머리 행으로 올리면 어느 행도 날짜를 보이지 않아 열이 시:분
        폭으로 줄고, 날짜는 하루에 한 번 읽힌다.
        """
        self.assertIn('<tr class="day"><td colspan="5">', self.page,
                      "하루가 바뀌는 자리에 서는 머리 행이 없다")
        self.assertIn('if (d !== day){', self.page,
                      "날짜가 바뀔 때만 머리 행이 서야 한다")
        # 행 안에서 접는 방식은 제거했다 — 접어도 첫 행이 열 폭을 잡는다
        self.assertNotIn('once("day"', self.page,
                         "날짜는 접는 대상이 아니라 하루 머리로 올라간 값이다")

    def test_the_day_head_is_not_a_colour_field(self):
        body = self.rule(".audit tbody tr.day td")
        self.assertIn("background:none", body,
                      "하루 머리는 색면이 아니다 (s9-design 금지 목록)")
        self.assertIn("border-top:1px solid var(--border)", body,
                      "하루의 경계는 위 경계 한 줄로 말한다")
        self.assertIn("border-bottom:0", body, "머리와 첫 행 사이를 가르지 않는다")
        # 데이터 행이 아니므로 hover 로도 칠해지지 않는다 — 스킨의 tint 도 같다
        self.assertNotIn(".audit tr:hover td{", self.page,
                         "hover 는 데이터 행만 받는다 — tr:not(.day) 로 좁혀야 한다")
        self.assertIn(".audit tbody tr:not(.day):hover td{", self.page)
        self.assertIn('[data-skin="grid"] .audit tbody tr.day td{background:none}',
                      self.page, "줄무늬 스킨에서도 하루 머리는 칠하지 않는다")

    def test_the_row_still_carries_its_full_time(self):
        """날짜가 화면에서 하루 머리로 갔어도 행은 온전한 시각을 갖는다."""
        m = re.search(r'<td class="ts">(.*?)</td>', self.page, re.S)
        self.assertIsNotNone(m, "시각 칸을 찾지 못했다")
        self.assertIn('<span class="dup">${esc(d)} </span>', m.group(1),
                      "행마다 남는 날짜가 없으면 한 행만 복사할 때 며칠 것인지 잃는다")
        self.assertIn("${esc(e.ts.slice(11, 16))}", m.group(1),
                      "보이는 글자는 시:분뿐이다")
        # colspan 머리 행은 「남는 폭은 마지막 열이 가진다」에서 빠진다
        self.assertIn(".audit tbody tr:not(.day) td:last-child{width:100%}", self.page)
        self.assertNotIn(".audit th:last-child,.audit td:last-child{width:100%}",
                         self.page,
                         "colspan 칸에 100% 를 주면 열 폭 계약이 흔들린다")

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

    # ── E1 날짜는 행이 아니라 하루 머리로 (REQ-20260910-025) ─────────────
    def test_the_date_stands_once_a_day_above_the_rows(self):
        """행 안에서 접는 방식은 첫 행을 접지 않아 시각 열이 날짜 폭을 유지했다."""
        self.assertNotIn('once("day"', self.page,
                         "날짜는 행 안에서 접지 않는다 — 첫 행이 접히지 않아 열 폭이 남는다")
        self.assertIn('<tr class="day"><td colspan="5">', self.page,
                      "날짜가 바뀌는 자리마다 하루 머리 행 한 줄이 서야 한다")
        # 행의 시각 칸에 보이는 글자는 시:분뿐이다
        m = re.search(r'<td class="ts">(.*?)</td>', self.page, re.S)
        self.assertIsNotNone(m, "시각 칸을 찾지 못했다")
        visible = re.sub(r'<span class="dup">.*?</span>', "", m.group(1), flags=re.S)
        self.assertIn("slice(11, 16)", visible, "보이는 글자는 시:분이다")
        self.assertNotIn("slice(0, 10)", visible, "날짜는 보이는 자리에 남지 않는다")

    def test_the_day_head_is_not_a_colour_field(self):
        """하루 머리는 누를 것이 없는 이름 줄이다 — 칠하면 데이터 행으로 읽힌다."""
        body = self.rule(".audit tbody tr.day td")
        # 막는 것은 **칠**이지 `background` 라는 글자가 아니다. 이 줄은 스킨이
        # 데이터 행에 주는 줄무늬를 되돌려야 해서 `background:none` 을 명시로
        # 적는다 — 속성을 빼는 것보다 강하게 규칙을 지키는 쪽이라, 글자만 보고
        # 반려하면 옳은 코드가 걸린다 (REQ-20260910-027 에서 실제로 걸렸다).
        for paint in re.findall(r"background[^:;]*:\s*([^;]+)", body):
            self.assertIn(paint.strip(), ("none", "transparent"),
                          "하루 머리에 색면을 두지 않는다: background:%s" % paint.strip())
        self.assertIn("border-top:1px solid var(--border)", body,
                      "구분은 위 경계 한 줄이다")
        self.assertIn("color:var(--muted)", body)
        # hover 로도 칠해지지 않는다 — 스킨마다 있는 tint 규칙 전부
        for hover in re.findall(r"[^\n{]*\.audit tr[^{\n]*:hover td\{", self.page):
            self.assertIn(":not(.day)", hover,
                          "hover tint 가 하루 머리까지 칠한다: %s" % hover.strip())
        # grid 스킨의 줄무늬도 하루 머리를 세지 않는다
        zebra = re.search(r'\[data-skin="grid"\][^{]*\.audit tbody tr:nth-child\(even\)'
                          r'([^,{]*)', self.page)
        self.assertIsNotNone(zebra, "grid 스킨의 줄무늬 규칙이 없다")
        self.assertIn(":not(.day)", zebra.group(1),
                      "줄무늬가 하루 머리를 칠하면 데이터 행이 하나 더 있는 것으로 읽힌다")

    def test_the_row_still_carries_its_full_time(self):
        """눈에서 뺀 것이지 잃은 것이 아니다 — 한 행만 복사해도 며칠 것인지 남는다."""
        m = re.search(r'<td class="ts">(.*?)</td>', self.page, re.S)
        self.assertIsNotNone(m, "시각 칸을 찾지 못했다")
        self.assertIn('<span class="dup">', m.group(1),
                      "날짜는 .dup(1px·clip-path)으로 행에 남는다")
        # 남는 폭 규칙이 다섯 열에 걸친 하루 머리 칸에 걸리면 앞 열들이 벌어진다
        self.assertIn(".audit tbody tr:not(.day) td:last-child{width:100%}", self.page)
        self.assertNotIn(".audit th:last-child,.audit td:last-child{width:100%}", self.page)

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
