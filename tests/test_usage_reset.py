"""사용량 칩이 "언제 풀리는지"를 말하는가 (REQ-20260827-056-62x6).

사용자는 이렇게 썼다: "대시보드 상단에 클로드 사용량을 보여주는 곳에서 마우스를
올려두면 5시간이 갱신되기까지의 시간, 위클리의 갱신되는 시간, fable이 갱신되는
시간을 보이게 해줘."

칩은 이미 `5h 16% · wk 75% · fable 100%` 를 보여 준다. 빠진 것은 **그래서 언제
풀리느냐**다. 100% 를 보고 사람이 정말로 알고 싶은 것은 숫자가 아니라 "지금
기다릴까, 다른 길로 갈까"이고, 그 결정은 남은 시간이 답한다.

서버는 이미 한도마다 `resets_at` 을 준다 — 화면만 말하면 된다.

이 테스트가 지키는 계약은 다섯이다.

  ① 세 한도가 각각 남은 시간과 초기화 시각을 갖는다.
  ② 시간은 사람 말이다 — 문장 안에서 "2시간 37분 뒤"이지 "2h 37m"이 아니다.
     (카드 경과시간의 라틴 축약은 모노 메타데이터의 어휘라 문장에 쓰지 않는다.)
  ③ 마우스를 올릴 때 다시 센다. 탭이 숨겨져 있으면 60초 폴이 멈추는데,
     그때 굳은 "2시간 37분 뒤"는 설명이 아니라 거짓말이다.
  ④ 모르는 것은 모른다고 한다 — 초기화 시각이 없거나 이미 지난 한도에서
     문장이 깨지지 않는다.
  ⑤ 보이는 칩은 길어지지 않는다. 헤더는 2행 고정 구조라(s9-design) 칩이
     늘어나면 툴바가 접힌다 — 그래서 이 정보는 호버에 둔다.
  ⑥ 그릇은 **이 제품의 hovercard** 다. 1차는 네이티브 `title` 툴팁으로
     냈다가 반려됐다 — "너무 못생겼다 디자인을 하나도 고려안한듯". 맞는
     말이다: 네이티브 툴팁은 브라우저/OS 가 그리는 상자라 이 제품의 서체도
     색도 깊이도 정렬도 하나도 쓰지 않는다. doclink 미리보기·우선순위 척도가
     이미 쓰는 그 카드를 재사용한다 — 위치 계산과 10스킨 대응이 이미 풀려
     있는 것이 재사용의 이유다.
  ⑦ 숫자는 세로로 맞는다. 세 줄의 퍼센트와 시각이 어긋나면 읽는 눈이 매번
     다시 찾는다 — 모노 + tabular-nums + 우측 정렬.

픽셀이 아니라 이 계약만 검사한다. 실제 렌더와 툴팁 문자열은 사람의 캡처·
실브라우저 확인 몫이다.

실행: python3 tests/ usage_reset
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class UsageReset(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()

    # ---------- ① 세 한도가 각각 말한다 ----------

    def test_reset_time_is_read_from_the_server_field(self):
        """서버가 이미 주는 resets_at 을 쓴다 — 추정하지 않는다."""
        self.assertIn("resets_at", self.src,
                      "한도의 초기화 시각을 화면이 읽지 않는다")

    def test_all_three_limits_get_a_line(self):
        """5h 세션 · 주간 · 모델 세 한도가 각각 한 줄을 갖는다."""
        blk = self._title_fn()
        for kind in ("session", "weekly_all", "weekly_scoped"):
            self.assertIn(kind, blk, "%s 한도가 툴팁에 없다" % kind)

    def test_line_carries_both_the_wait_and_the_clock(self):
        """남은 시간과 절대 시각을 함께 준다 — 하나만으로는 부족하다.

        남은 시간은 '지금 기다릴까'에, 절대 시각은 '일정에 맞출까'에 답한다."""
        blk = self._title_fn()
        self.assertIn("fmtUntil(", blk, "남은 시간을 세지 않는다")
        self.assertIn("fmtWhen(", blk, "초기화 시각을 말하지 않는다")

    def test_chip_tokens_are_repeated_so_the_lines_map_to_the_chip(self):
        """툴팁 줄이 칩의 어느 조각인지 알 수 있어야 한다 — 같은 토큰을 준다."""
        blk = self._title_fn()
        for tok in ("5h", "wk"):
            self.assertIn(tok, blk, "칩에 찍힌 %r 이 툴팁에 없다" % tok)
        self.assertIn("scope_name", blk,
                      "모델 한도는 그 모델 이름으로 불러야 한다")

    # ---------- ② 사람의 시간 ----------

    def test_wait_is_spoken_in_korean_units(self):
        """문장 안의 시간은 사람 말이다 — 분·시간·일."""
        m = self._fn("fmtUntil")
        for unit in ("분", "시간", "일"):
            self.assertIn(unit, m, "%r 단위가 없다" % unit)
        # 라틴 축약(2h 37m)은 모노 메타데이터의 어휘다 — 문장에 섞지 않는다.
        # 값 바로 뒤에 붙는 h/m/d 가 곧 그 축약이다 (변수 이름은 무관).
        self.assertNotRegex(m, r"\}\s*[hmd]\b",
                            "문장에 라틴 축약 단위를 쓰지 않는다")

    def test_soon_is_a_word_not_a_negative_number(self):
        """이미 지난 한도는 '-3분 뒤'가 아니라 '곧'이라고 말한다."""
        m = self._fn("fmtUntil")
        self.assertIn("곧", m, "지난 시각을 사람 말로 처리하지 않는다")

    def test_clock_uses_the_viewers_own_timezone(self):
        """시각대는 화면이 쓰는 것과 같다 — 브라우저 로컬."""
        m = self._fn("fmtWhen")
        self.assertRegex(m, r"getHours\(\)|toLocale",
                         "로컬 시각으로 말하지 않는다")
        # '오늘/내일'은 날짜를 옮겨 세지 않게 해 주는 가장 값싼 장치다
        self.assertIn("오늘", m)

    # ---------- ③ 호버 때 다시 센다 ----------

    def test_hover_recomputes_the_wait(self):
        """카드를 열 때마다 다시 센다 — 숨은 탭에서는 60초 폴이 멈추고,
        그때 굳은 "2시간 37분 뒤"는 설명이 아니라 거짓말이다."""
        m = self._fn("showUsageHover")
        self.assertIn("fmtUntil(", m,
                      "카드를 열 때 남은 시간을 다시 세지 않는다 (미리 만들어 둔 문자열)")
        # 카드는 열 때 만들어진다 — 캐시해 두면 다시 세는 뜻이 사라진다
        self.assertIn("hovercard.innerHTML", m)

    def test_last_answer_is_kept_so_hover_has_something_to_recount(self):
        """다시 세려면 마지막으로 받은 한도를 들고 있어야 한다."""
        self.assertRegex(self.src, r"(?:let|var) usageLast\s*=",
                         "마지막 응답을 보관하지 않는다")

    # ---------- ④ 모르는 것은 모른다고 ----------

    def test_missing_reset_does_not_break_the_line(self):
        """초기화 시각이 없는 한도에서도 문장이 성립한다."""
        blk = self._title_fn()
        # 시각을 모르면 괄호째 빠져야 한다 — 빈 괄호 "()"를 남기지 않는다
        self.assertRegex(blk, r"when\s*\?",
                         "초기화 시각이 없을 때 괄호를 접지 않는다")
        self.assertIn("알 수 없음", self._fn("fmtUntil"),
                      "모르는 것을 모른다고 말하지 않는다")

    def test_failure_falls_back_to_the_plain_notice(self):
        """사용량을 못 받으면 원래 안내로 돌아간다 — 빈 툴팁을 남기지 않는다."""
        blk = self._title_fn()
        self.assertRegex(blk, r"if \(!usageLast",
                         "받은 것이 없을 때의 갈래가 없다")

    # ---------- ⑤ 보이는 칩은 길어지지 않는다 ----------

    def test_chip_text_still_shows_only_percentages(self):
        """칩 본문에는 시각을 넣지 않는다 — 헤더 2행 구조가 접힌다."""
        m = re.search(r"el\.innerHTML = `[\s\S]*?;", self.src)
        self.assertIsNotNone(m, "칩 본문 조립을 찾지 못했다")
        body = m.group(0)
        for w in ("초기화", "fmtUntil", "fmtWhen", "resets_at"):
            self.assertNotIn(w, body,
                             "칩 본문에 %r 이 들어가면 헤더가 접힌다" % w)

    def test_screen_reader_line_is_plain_text(self):
        """보조기술이 읽는 줄은 평문이다 — 태그를 넣으면 글자 그대로 읽힌다."""
        blk = self._fn("usageTitle")
        self.assertNotRegex(blk, r"<(?:span|b|code|div)\b",
                            "aria 문자열에 태그를 넣지 않는다 — 글자 그대로 읽힌다")

    # ---------- ⑥ 그릇은 이 제품의 카드다 ----------

    def test_no_native_tooltip_anywhere_on_the_chip(self):
        """네이티브 title 툴팁을 쓰지 않는다 — 반려 사유가 그것이었다."""
        m = re.search(r'<span id="usage-chip"[^>]*>', self.src)
        self.assertIsNotNone(m, "사용량 칩 마크업을 찾지 못했다")
        self.assertNotIn("title=", m.group(0),
                         "칩에 네이티브 툴팁이 남아 있다 — OS 가 그리는 상자다")
        self.assertNotRegex(self.src, r"uc\.title\s*=|el\.title\s*=\s*usageTitle",
                            "코드가 네이티브 툴팁을 다시 채운다")

    def test_card_is_the_product_hovercard_not_a_new_widget(self):
        """새 팝오버를 만들지 않는다 — 이미 있는 카드에 얹는다."""
        m = self._fn("showUsageHover")
        self.assertIn("hovercard.innerHTML", m, "제품 카드에 그리지 않는다")
        self.assertIn("placeHover(", m, "이미 풀린 위치 계산을 쓰지 않는다")

    def test_chip_is_registered_as_a_hover_handle(self):
        """카드를 여는 손잡이 목록에 칩이 들어 있다 — 네 경로가 같은 것을 본다."""
        m = re.search(r"const hoverTarget = [^;]+;", self.src)
        self.assertIsNotNone(m, "hoverTarget 선택자를 찾지 못했다")
        self.assertIn("usage-chip", m.group(0), "칩이 손잡이로 등록되지 않았다")
        self.assertIn("showUsageHover", self._fn("showHover"),
                      "showHover 가 사용량 카드로 갈라지지 않는다")

    def test_keyboard_can_reach_the_card(self):
        """마우스 없이도 닿아야 한다 — 카드는 focusin 에서도 뜬다."""
        m = re.search(r'<span id="usage-chip"[^>]*>', self.src)
        self.assertIn("tabindex", m.group(0), "칩에 키보드가 닿지 않는다")
        self.assertIn('setAttribute("aria-label"', self.src,
                      "보조기술에 읽어 줄 이름이 없다")

    # ---------- ⑦ 숫자가 세로로 맞는다 ----------

    def test_numbers_line_up(self):
        """모노 + tabular-nums + 우측 정렬 — 세 줄이 세로로 맞아야 한다."""
        css = self._usage_css()
        self.assertIn("var(--mono)", css, "숫자를 모노로 두지 않았다")
        self.assertIn("tabular-nums", css, "자릿수가 흔들린다")
        self.assertIn("text-align:right", css, "퍼센트가 우측 정렬이 아니다")
        self.assertIn("grid", css, "칸이 열로 서지 않는다")

    def test_card_paints_no_fill_and_no_side_bar(self):
        """색면 하이라이트·세로 띠 금지, 색 하드코딩 금지 — 색은 글자에만."""
        css = self._usage_css()
        for bg in re.findall(r"background\s*:\s*([^;}]+)", css):
            self.assertIn(bg.strip(), ("none", "transparent"),
                          "카드 안에 색면을 깔지 않는다: %s" % bg)
        self.assertNotIn("border-left", css, "좌측 세로 띠 금지")
        websrc.no_hex(self, css)
        self.assertNotRegex(css, r"\[data-(?:skin|theme)=",
                            "특정 스킨/톤 전용 스타일이 아니다")

    def test_severity_colour_is_the_only_colour(self):
        """색은 신호일 때만 — 임계 퍼센트에만 상태 잉크를 얹는다."""
        css = self._usage_css()
        self.assertIn("var(--c-inprogress)", css)
        self.assertIn("var(--c-blocked)", css)
        m = self._fn("showUsageHover")
        self.assertRegex(m, r"90|crit", "임계 구간을 가르지 않는다")

    # ---------- helpers ----------

    def _fn(self, name):
        m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n\}" % name, self.src)
        self.assertIsNotNone(m, "%s() 를 찾지 못했다" % name)
        return m.group(0)

    def _title_fn(self):
        """한도를 말하는 자리 전부 — 행 모델·평문 줄·카드가 한 사실을 나눠 맡는다."""
        return (self._fn("usageRows") + self._fn("usageTitle")
                + self._fn("showUsageHover"))

    def _usage_css(self):
        m = re.search(r"/\* -+ 사용량 카드[\s\S]*?\*/([\s\S]*?)\n\n", self.src)
        self.assertIsNotNone(m, "사용량 카드 CSS 블록을 찾지 못했다")
        return m.group(1)

    def _usage_css(self):
        m = re.search(r"/\* -+ 사용량 카드[\s\S]*?\*/([\s\S]*?)\n\n", self.src)
        self.assertIsNotNone(m, "사용량 카드 CSS 블록을 찾지 못했다")
        return m.group(1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
