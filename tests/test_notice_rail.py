"""알림 줄의 화면 계약 (REQ-20260915-001-62x6).

머리에 흩어져 있던 알림 넷(신원 글자 안의 발신함 막힘·token 만료, 머리 3행의
「서버가 옛 코드로 실행 중」, 진행 칩, 각 설정 판 안)을 한 줄로 모았다. 실제
결함은 경고의 색이 아니라 **경고가 신원 라벨 안에 들어간 것**이었다:
한 서비스의 이름이 화면 코드에 박혀 있어 서비스가 늘 때마다 화면을 고쳐야 했고,
mono 10px 신원 라벨에 한글 문장을 넣어 음절이 흩어졌다.

지키는 것 다섯. 다섯 다 코드를 조금만 손대면 조용히 무너지고, 무너져도 화면은
멀쩡해 보인다.

  ① **화면 코드에 서비스 이름이 없다.** 서버가 /api/notices 로 주체·문장·여는
     길을 주고 화면은 그리기만 한다 — 그것이 「한 서비스 전용 문구 금지」의
     구조적인 답이다. 서비스가 늘어도 web/app/notice.js 는 그대로다.
  ② **스킨은 토큰만 갈아 끼운다.** 부품(`.n-*`)을 칠하는 자리는 web/css/notice.css
     한 곳이다. 앞선 `.oc-*` 는 스킨마다 다시 칠해져 있었고(cobalt 만 11줄),
     새 부품이 같은 길을 가면 10 스킨 × 부품 여덟이 또 생긴다.
  ③ **알림이 없으면 흔적이 없다.** 상시 자리 표시자는 곧 배경이 되어 진짜 사고
     때도 안 읽힌다 — `:empty` 가 테두리까지 걷는다.
  ④ **막힘은 닫히지 않는다.** 일이 막힌 이유를 감출 수 없다. 대신 같은 크기의
     빈 칸을 두어 「언제부터」가 줄마다 한 열로 선다.
  ⑤ **옛 자리는 남지 않는다.** 같은 사실을 두 곳이 말하면 어느 쪽도 못 믿는다.

화소는 단위 시험이 볼 수 없다 — 마크의 잉크 중심·열 맞춤·좁은 폭은 사람의 캡처
검증이 맡는다(tests/_probe_marks.py 계열의 자와 REQ 문서에 붙인 그림).
여기서는 「믿을 수 없게 만들던 방식으로 되돌아갔는가」만 본다.

실행: python3 tests/ notice_rail
"""
import os
import re
import unittest

from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")


def read(*parts):
    with open(os.path.join(WEB, *parts), encoding="utf-8") as f:
        return f.read()


def strip_comments(src):
    """코드만 본다 — 주석 안의 `.n-`·서비스 이름은 설명이지 칠도 문구도 아니다."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


class NoticeRail(unittest.TestCase):
    def setUp(self):
        self.js = read("app", "notice.js")
        self.css = read("css", "notice.css")
        self.skins = read("css", "skins.css")
        self.marks = read("css", "marks.css")
        with open(index_path(), encoding="utf-8") as f:
            self.shell = f.read()

    # ── ① 화면 코드에 서비스 이름이 없다 ──────────────────────────────
    def test_no_service_name_in_the_drawing_code(self):
        """서비스가 늘어도 화면은 그대로다 — 이름은 서버가 주는 **값**이다."""
        # 재는 자리는 **알림 줄을 그리는 구간**이다 — 이 파일의 다른 자리(프로필
        # 미기재 라벨 등)는 이 계약 밖이다.
        start = self.js.index("/* ── 알림 줄 (REQ-20260915-001-62x6)")
        body = strip_comments(self.js[start:])
        # 진단용 표본(nDemo)만 예외다. 그것은 서버가 주는 값의 자리를 흉내내는
        # 곳이고, `?notices=` 로만 선다 — 알림은 사고가 난 그 몇 분에만 존재해
        # 파라미터 없이는 열 스킨 × 두 tone × 좁은 폭을 찍을 수가 없다.
        i = body.find("function nDemo(")
        self.assertGreater(start, 0, "알림 줄 구간의 머리말이 없다")
        self.assertGreater(i, 0, "진단 표본(nDemo)이 없다 — 이름이 바뀌었으면 이 시험도 고쳐라")
        drawing = body[:i]
        for name in ("Jira", "GitHub", "SMTP", "Atlassian", "jira", "github"):
            self.assertNotIn(name, drawing,
                             "그리는 코드에 서비스 이름 「%s」이 박혔다 — 서버가 주는 값이어야 한다" % name)
        self.assertIn("location.search", self.js[self.js.index("function nDemo("):][:400],
                      "표본이 진단 스위치(?notices=) 밖에서도 설 수 있다")

    def test_reads_one_contract(self):
        """계약은 하나다 — /api/notices 가 여섯 조각을 싣고 화면은 그린다."""
        self.assertIn("/api/notices", self.js)
        for field in ("sev", "source", "say", "go", "since", "sig"):
            self.assertIn(field, self.js, "계약의 조각 「%s」를 화면이 안 읽는다" % field)

    # ── ② 스킨은 토큰만 ───────────────────────────────────────────────
    def test_skins_only_swap_tokens(self):
        """`skins.css` 에 `.n-` 선택자가 없어야 한다 — 부품은 notice.css 한 곳."""
        rules = strip_comments(self.skins)
        self.assertNotIn(".n-", rules,
                         "스킨이 알림 줄의 부품을 다시 칠한다 — 토큰(--n-*)만 갈아 끼워라")
        # 옛 `.oc-*` 는 이 파일에서 걷혔다 (그 자리가 이 규칙이 생긴 까닭이다)
        self.assertNotIn(".oc-", rules, "옛 알림 띠의 부품 규칙이 스킨에 남아 있다")
        # 토큰은 실제로 쓰인다 — 짙은 머리 띠를 칠하는 스킨이 잉크를 갈아 끼운다
        self.assertIn("--n-ink-halt", rules, "스킨이 토큰을 갈아 끼우는 자리가 없다")

    def test_parts_are_painted_in_one_place(self):
        for part in (".n-mark", ".n-src", ".n-say", ".n-go", ".n-cmd",
                     ".n-when", ".n-x", ".n-more"):
            self.assertIn(part, self.css, "부품 %s 의 규칙이 notice.css 에 없다" % part)

    # ── ③ 알림이 없으면 흔적이 없다 ───────────────────────────────────
    def test_empty_rail_leaves_no_trace(self):
        rules = strip_comments(self.css)
        self.assertRegex(rules, r"\.nrail:empty[^{]*\{[^}]*display:\s*none",
                         "빈 줄이 테두리·여백을 남긴다 — 상시 띠는 곧 안 읽힌다")
        self.assertRegex(self.js, r'nSig\s*=\s*"off"',
                         "말할 것이 없을 때 줄을 비우는 경로가 없다")

    def test_the_rail_sits_where_hrow3_sat(self):
        """자리는 머리 2행 아래다 — 10 스킨이 이미 그 자리를 안다."""
        m = re.search(r'<div class="nrail"[^>]*>', self.shell)
        self.assertIsNotNone(m, "머리에 알림 줄(.nrail) 자리가 없다")
        self.assertIn('role="status"', m.group(0), "동적 알림은 상태 변화를 알려야 한다")
        self.assertIn('aria-live="polite"', m.group(0))
        self.assertLess(self.shell.index('class="hrow2"'), m.start(),
                        "알림 줄이 툴바보다 앞에 있다")
        self.assertNotIn('id="oldcode"', self.shell,
                         "옛 「서버가 옛 코드로 실행 중」 띠가 남아 있다 — 알림 줄로 옮겼다")
        # 좁은 폭에서는 툴바보다 위로 (400px 에서 툴바가 세 줄로 접히면 막힘이 밀린다)
        rules = strip_comments(self.css)
        self.assertRegex(rules, r"max-width:\s*900px\)\{[^@]*\.nrail\{order:1\}",
                         "좁은 폭에서 알림 줄이 툴바 위로 올라가지 않는다")
        self.assertIn("max-width:560px", rules, "좁은 폭의 2열 접기가 없다")

    # ── ④ 막힘은 닫히지 않는다 ────────────────────────────────────────
    def test_halt_cannot_be_dismissed(self):
        self.assertRegex(self.js, r'sev\s*!==\s*"halt"',
                         "막힘에도 닫기가 선다 — 일이 막힌 이유는 감출 수 없다")
        self.assertIn("n-xgap", self.js,
                      "막힘 줄에 같은 크기의 빈 칸이 없다 — 시각 열이 줄마다 어긋난다")
        self.assertIn("n-xgap", self.css)

    def test_dismissal_returns_when_the_fact_changes(self):
        """닫기는 「다시는 안 보기」가 아니라 「이 사실에 한해 접어 두기」다."""
        self.assertIn("s9notice_ack", self.js)
        self.assertRegex(self.js, r"e\.s\s*===\s*it\.sig",
                         "지문이 달라져도 다시 안 뜬다 — 조건이 바뀌면 다시 서야 한다")
        self.assertIn("noticeUnpark", read("app", "settings.js"),
                      "닫은 알림을 되돌리는 자리(Settings › 디스플레이)가 없다")

    # ── ⑤ 옛 자리는 남지 않는다 ───────────────────────────────────────
    def test_old_places_are_gone(self):
        self.assertNotIn("jiraBlockHtml", self.js,
                         "신원 글자 안의 발신함 경고가 남아 있다")
        self.assertNotIn("renderOldCode", self.js, "옛 코드 띠의 그리는 함수가 남아 있다")
        self.assertNotIn("jblock", read("css", "header.css"),
                         "신원 글자 안의 경고 규칙이 남아 있다")
        self.assertNotIn(".oc-", strip_comments(read("css", "header.css")))
        # 같은 사실을 줄과 옛 자리가 함께 말하지 않는다
        self.assertIn("noticeHas", self.js,
                      "알림 줄이 맡은 사실을 옛 자리가 비켜 주는 길이 없다")

    # ── 마크 사전 — ■ ▲ ○ 는 한 자리에 선다 ──────────────────────────
    def test_three_marks_live_in_the_dictionary(self):
        for name in ("--mk-halt-src", "--mk-note-src", "--mk-warn-src"):
            self.assertIn(name, self.marks, "마크 %s 가 사전에 없다" % name)
        for cls in (".mk-halt{", ".mk-note{"):
            self.assertIn(cls, self.marks)
        # 배율 불변: 획이 반 화소에 걸리지 않게 좌표가 정수다 (사전 규칙 ②)
        halt = re.search(r"--mk-halt-src:[^\n]*", self.marks).group(0)
        self.assertIn("x='3' y='4' width='5' height='5'", halt,
                      "막힘 마크의 네 모서리가 정수가 아니다 — 비정수 배율에서 갈린다")
        note = re.search(r"--mk-note-src:[^\n]*", self.marks).group(0)
        self.assertIn("cx='5.5' cy='6.5' r='3'", note,
                      "정보 마크의 테가 정수에 안 앉는다 (바깥 3.0/10.0 · 안 4.0/9.0)")
        # 그림에 제 크기가 있어야 한다 — 없으면 배율 1.25 에서 통째로 사라진다(사전 규칙 ④)
        for src in (halt, note):
            self.assertIn("width='11' height='11'", src)

    # ── 금지 셋 (s9-design) ───────────────────────────────────────────
    def test_no_colour_field_no_side_bar(self):
        rules = strip_comments(self.css)
        for row in re.findall(r"\.nrow\{[^}]*\}", rules):
            self.assertNotIn("border-left", row, "카드 좌측 세로 띠 금지")
            self.assertNotRegex(row, r"background(-color)?:\s*(?!none|transparent)",
                                "색면 하이라이트 금지 — 색은 마크와 주체 이름에만")
        # 문장은 언제나 읽는 잉크색이다 — 긴 경고색 문장은 열 스킨 어디서도
        # 4.5:1 을 보장할 수 없고 「읽어야 하는 글」과 「신호」가 서로를 지운다
        self.assertRegex(rules, r"\.n-say\{[^}]*color:var\(--n-ink\)")
        for sev in ("halt", "warn", "note"):
            self.assertRegex(
                rules, r"\.nrow\.%s \.n-mark,\.nrow\.%s \.n-src\{color:var\(--n-ink-%s\)\}"
                       % (sev, sev, sev),
                "%s 의 잉크가 마크와 주체 이름 밖으로 나갔다" % sev)

    # ── 과녁은 상자가 아니다 (REQ-20260915-010-62x6) ───────────────────
    def test_tap_target_does_not_grow_the_box(self):
        """44px 과녁은 겹판으로 넓힌다 — 상자째 키우면 접히는 폭에서 제 줄로
        내려앉아 44px 빈 띠가 되고 시각과 닫기가 30px 넘게 벌어진다
        (실측 2026-09-15 맥, chromium·webkit 같은 자리)."""
        rules = strip_comments(self.css)
        box = re.search(r"\.n-x,\.n-xgap\{([^}]*)\}", rules)
        self.assertIsNotNone(box, "닫기와 빈 칸의 상자 규칙이 없다")
        self.assertNotIn("min-width:var(--tap-min)", box.group(1),
                         "과녁으로 상자를 키웠다 — 접히는 폭에서 빈 띠가 된다")
        self.assertNotIn("min-height:var(--tap-min)", box.group(1),
                         "과녁으로 상자를 키웠다 — 접히는 폭에서 빈 띠가 된다")
        self.assertRegex(rules, r"\.n-x::after\{[^}]*width:var\(--tap-min\)",
                         "손가락이 닿을 44px 겹판이 없다")
        # 보이는 손잡이가 보이지 않는 겹판을 이긴다 — 두 줄로 접히는 폭에서
        # 겹판이 윗줄 손잡이의 아랫단을 덮어 복사 대신 닫기가 먹었다
        self.assertRegex(rules, r"\.n-go,\.n-cmd\{[^}]*z-index:1",
                         "겹판이 손잡이를 덮는다 — 손잡이가 위에 서야 한다")


if __name__ == "__main__":
    unittest.main()
