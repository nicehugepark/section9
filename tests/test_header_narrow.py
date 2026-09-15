"""손전화 폭에서 머리글이 창을 얼마나 먹는가 (REQ-20260916-011-2n7g).

실측 2026-09-16, 실제 맥 Safari 26.4 · 400x900 · 대시보드 #board:
`.board` 의 화면 좌표 top 이 **428px** 이었다 — 창 900 의 47% 를 머리글이 먼저
쓰고 판에는 472px 만 남아 카드 두 장이 겨우 섰다. 쌓인 것은 여섯 덩이다:
브랜드 1줄 · 탭 **2줄** · 검색 1줄 · 거르개 1줄 · 사용량 **2줄** · 신원 **2줄**.

고친 규칙은 그 여섯 중 넷을 둘로 줄인다(≤560px 에서만):

  ① 브랜드와 탭이 **한 줄** — 탭은 가로로 밀되 밀 수 있다는 것이 **보인다**
  ② 거르개 넷은 손잡이 하나 뒤로 — **검색칸은 남고**, 걸린 조건은 접힌 채로도 읽힌다

사용량·신원의 네 줄은 이 요청이 건드리지 않았다 — 그 접힘은
REQ-20260915-001-2n7g 이 세운 계약이고 실브라우저 시험이 400·340px 에서
그것을 재고 있어(test_usage_chip_fit), 줄이는 일은 그 계약을 실브라우저로
다시 재면서 해야 한다. 그 몫은 REQ-20260916-012-2n7g 로 따로 섰다.

이 파일이 지키는 것은 그 둘의 **구조**다. 화소는 단위 시험이 볼 수 없다 —
「428 이 300 아래로 내려왔는가」는 실브라우저와 사람의 눈이 맡는다
(test_header_notice_area 와 같은 계보).

**줄이는 것과 지우는 것은 다르다.** 그래서 이 파일의 절반은 「여전히 닿는가」를
지킨다: 접힌 거르개에 이르는 손잡이가 있는가(test_folded_filters_have_a_handle),
접힌 채로도 걸린 것이 보이는가(test_folded_handle_tells_what_is_on), 밀리는 탭에
밀 수 있다는 표시가 있는가(test_scrollable_tabs_show_the_way) — 마지막 것은 바로
앞 요청(REQ-20260916-010)이 반려된 그 자리다: 보이지 않는 길은 길이 아니다.

실행: python3 tests/ header_narrow
"""
import os
import re
import unittest

import websrc
from webasset import index_path

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")
INDEX = index_path()

# 이 요청이 손댄 눈금 — 새로 만들지 않고 이미 있는 손전화 폭에 얹었다.
NARROW = "@media (max-width:560px)"


def _read(*parts):
    with open(os.path.join(WEB, *parts), encoding="utf-8") as f:
        return f.read()


def _narrow_block(tc, css):
    """tablet.css 의 ≤560px 블록 본문 — 중괄호를 세어 끝을 찾는다."""
    i = css.find(NARROW)
    tc.assertNotEqual(i, -1, "tablet.css 에 %s 눈금이 없다" % NARROW)
    j = css.index("{", i)
    depth, k = 0, j
    while k < len(css):
        if css[k] == "{":
            depth += 1
        elif css[k] == "}":
            depth -= 1
            if depth == 0:
                return css[j + 1:k]
        k += 1
    tc.fail("%s 블록이 닫히지 않았다" % NARROW)


class HeaderNarrow(unittest.TestCase):
    def setUp(self):
        self.tablet = _read("css", "tablet.css")
        self.header = _read("css", "header.css")
        self.narrow = _narrow_block(self, self.tablet)
        with open(INDEX, encoding="utf-8") as f:
            self.index = f.read()

    # ---------- ① 브랜드와 탭이 한 줄 ----------

    def test_tabs_do_not_wrap_at_phone_width(self):
        """탭이 두 줄로 접히면 그 한 줄이 곧 32px 이다. 900 눈금이 켜 둔
        `flex-wrap:wrap` 을 이 폭에서는 되돌려야 한다."""
        self.assertRegex(
            self.narrow, r"\.tabs\{[^}]*flex-wrap:nowrap",
            "≤560px 에서 탭 줄이 nowrap 이 아니다 — 두 줄로 접힌다")

    def test_scrollable_tabs_show_the_way(self):
        """**보이지 않는 길은 길이 아니다** (REQ-20260916-010 반려 사유).
        맥·iOS 는 겹쳐 뜨는 스크롤막대라, 미는 상자를 만들면서 표시를 안 주면
        사용자에게는 「여기가 끝」으로 보인다. 흐림은 밀 수 있는 **쪽에만**
        걸려야 한다 — 양쪽에 상시 걸린 흐림은 표시가 아니라 장식이다."""
        self.assertRegex(self.narrow, r"\.tabs\{[^}]*overflow-x:auto",
                         "탭 줄이 미는 상자가 아니다")
        self.assertRegex(self.narrow, r"\.tabs\{[^}]*mask-image:linear-gradient",
                         "밀 수 있다는 표시(가장자리 흐림)가 없다")
        for side in ("edge-l", "edge-r"):
            self.assertIn(
                ".tabs.%s" % side, self.narrow,
                "%s 쪽 흐림을 켜는 규칙이 없다 — 흐림이 상태를 말하지 못한다" % side)
        app = _read("app", "app.js")
        body = websrc.fn(self, app, "tabEdges")
        self.assertIn("scrollWidth", body)
        self.assertRegex(body, r'toggle\("edge-l"', "왼쪽 흐림을 켜고 끄는 손이 없다")
        self.assertRegex(body, r'toggle\("edge-r"', "오른쪽 흐림을 켜고 끄는 손이 없다")

    def test_picked_tab_is_pushed_into_view(self):
        """미는 상자에서는 고른 탭이 화면 밖에 있을 수 있다 — 그러면 화면이
        「지금 어디인가」를 말해 주지 못한다. 탭을 맞출 때마다 밀어 넣는다."""
        app = _read("app", "app.js")
        # 부르는 자리는 tabSync 가 아니라 그 바로 뒤의 render 다 — tabSync 는 제
        # 본문만 떼어 실제로 실행되는 계약이 걸려 있어(test_tab_active_sync) 가짜
        # 화면에 없는 손을 부르면 그 계약이 깨진다.
        self.assertRegex(app, r"tabSync\(\);[\s\S]{0,400}?tabReveal\(\);",
                         "화면을 그리는 자리가 고른 탭을 밀어 넣지 않는다")
        self.assertRegex(websrc.fn(self, app, "tabReveal"), r"scrollIntoView",
                         "고른 탭을 보이는 자리로 밀지 않는다")

    def test_no_scroll_bar_stands_on_the_tab_row(self):
        """가로로 미는 줄 위의 막대는 자리를 먹고 눈에 거슬린다 — 표시는 흐림이
        맡는다(위 시나리오). 두 갈래로 지운다: 표준 속성 `scrollbar-width:none`
        과 옛 WebKit 의 `::-webkit-scrollbar{display:none}`.

        이 시험이 서 있는 까닭은 test_scrollbar S3 과 부딪혔던 자리이기
        때문이다 (REQ-20260916-020) — S3 은 「숨기는 것은 새로 짓는 것이
        아니다」로 좁혔고, 여기서는 그 숨김을 지워서 S3 을 통과시키는 길을 닫는다."""
        self.assertRegex(self.narrow, r"\.tabs\{[^}]*scrollbar-width:none",
                         "탭 줄에 표준 속성으로 막대를 지우는 규칙이 없다")
        self.assertRegex(
            self.narrow, r"\.tabs::-webkit-scrollbar\{[^}]*display:none",
            "옛 WebKit 에서 탭 줄 막대가 그대로 선다")

    def test_side_shell_skin_keeps_its_vertical_tabs(self):
        """soft 스킨의 탭은 왼쪽 셸에 **세로로** 선다 — 거기에 가로 밀기를
        얹으면 셸이 무너진다. 규칙에서 빼 둔 것을 지운 적이 없어야 한다."""
        self.assertIn('.tabs', self.narrow)
        m = re.search(r"([^\n{]*)\.tabs\{[^}]*overflow-x:auto", self.narrow)
        self.assertIsNotNone(m)
        self.assertIn('not([data-skin="soft"])', m.group(1),
                      "soft 스킨(세로 탭)이 가로 밀기 규칙에서 빠져 있지 않다")

    def test_no_flex_basis_leaks_into_the_vertical_toolbar(self):
        """soft 스킨의 툴바는 **세로 상자**다(왼쪽 셸) — 거기서 `flex-basis`
        는 폭이 아니라 **높이**가 된다. 검색칸과 손잡이가 첫 줄을 나눠 쓰게
        하는 기준 폭이 그 스킨으로 새면 손잡이 하나가 줄 높이의 38% 를
        가져간다. 줄을 가르는 값은 `width` 로 적거나 soft 를 빼야 한다."""
        for m in re.finditer(r"([^\n{]*)\{([^}]*)\}", self.narrow):
            sel, body = m.group(1).strip(), m.group(2)
            if "flex-basis:100%" in body.replace(" ", "") or \
                    re.search(r"flex:[^;]*\d%", body):
                self.assertIn('not([data-skin="soft"])', sel,
                              "세로 상자로 새는 기준 폭: %s" % sel[:70])

    # ---------- ② 거르개는 접히고 검색은 남는다 ----------

    def test_filters_fold_at_phone_width(self):
        """거르개 넷은 한 번 정하면 세션 내내 그대로인 값인데 손끝 높이
        44px 짜리 두 줄을 상시 먹었다."""
        self.assertRegex(
            self.narrow,
            r"\.hrow2:not\(\.fopen\) \.fgroup > :not\(#q\)[^{]*\{[^}]*display:none",
            "≤560px 에서 거르개가 접히지 않는다")

    def test_search_box_stays_visible_when_folded(self):
        """**줄이는 것과 지우는 것은 다르다.** 좁은 폭에서는 목록을 훑는 것보다
        찾는 것이 빠르다 — 검색칸까지 접으면 가장 값싼 길이 한 번 더 눌러야
        닿는 곳으로 간다. 접는 규칙은 `#q` 를 반드시 비켜 가야 한다."""
        hide = re.findall(r"\.hrow2:not\(\.fopen\)[^{]*\{[^}]*display:none[^}]*\}",
                          self.narrow)
        self.assertTrue(hide, "접는 규칙 자체가 없다")
        for rule in hide:
            self.assertIn(":not(#q)", rule,
                          "접는 규칙이 검색칸까지 지운다: %s" % rule[:80])

    def test_folded_filters_have_a_handle(self):
        """접힌 것에 이르는 길 — 손잡이는 화면에 **있고**, 열림 상태를 말한다."""
        self.assertRegex(
            self.index,
            r'<button id="fold-f"[^>]*class="ffold"[^>]*aria-expanded="false"',
            "거르개 손잡이가 없거나 열림 상태를 말하지 않는다")
        self.assertRegex(self.index, r'id="fold-f"[\s\S]{0,200}?aria-controls="fgroup"',
                         "손잡이가 무엇을 여는지 가리키지 않는다")
        self.assertRegex(self.index, r'class="fgroup" id="fgroup"',
                         "손잡이가 가리키는 거르개 묶음에 이름이 없다")
        ev = _read("app", "events.js")
        self.assertRegex(ev, r'#fold-f"\)\?\.addEventListener\("click"',
                         "손잡이를 누르는 손이 배선되지 않았다")
        self.assertRegex(ev, r'classList\.toggle\("fopen"',
                         "손잡이가 거르개를 펴지 못한다")

    def test_handle_never_stands_at_wide_widths(self):
        """넓은 폭에서는 거르개가 그대로 펼쳐져 있어야 한다 — 손잡이는 이
        폭만의 부품이라 기본이 「없음」이고, 560 눈금에서만 선다."""
        self.assertRegex(self.header, r"\.ffold\{[^}]*display:none",
                         "손잡이의 기본값이 「없음」이 아니다 — 넓은 폭에도 선다")
        self.assertRegex(self.narrow, r"\.ffold\{[^}]*display:flex",
                         "손잡이가 손전화 폭에서 서지 않는다")

    def test_folded_handle_tells_what_is_on(self):
        """거르개가 켜진 줄 모르고 빈 목록을 「없다」로 읽으면 그건 고장으로
        보인다. 걸린 조건의 사전은 하나뿐이어야 한다 — 손잡이는 그래프의
        안내가 쓰는 그 사전(hdrConds)을 그대로 읽는다."""
        app = _read("app", "app.js")
        body = websrc.fn(self, app, "foldSummary")
        self.assertIn("hdrConds()", body,
                      "손잡이가 걸린 조건의 사전을 읽지 않는다 — 사전이 두 벌이 된다")
        self.assertIn("fold-f-on", body, "손잡이에 조건을 적지 않는다")
        # 부르는 자리는 화면을 다시 그리는 한 곳이다 — 조건을 바꾸는 손(입력·
        # '내 것만'·그래프의 되돌리기)이 전부 그리로 모인다. 손마다 이 줄을
        # 더하면 언젠가 하나가 빠지고, 그때 손잡이는 없는 조건을 말한다.
        # 종류 축이 이 화면에 없으면 조건도 아니므로 syncTypeFilter 뒤여야 한다.
        self.assertRegex(app, r"syncTypeFilter\(\);[\s\S]{0,400}?foldSummary\(\);",
                         "조건이 바뀌어도 손잡이가 다시 적히지 않는다"
                         " (render 가 syncTypeFilter 뒤에서 foldSummary 를 부르지 않는다)")

    def test_account_row_stays_last(self):
        """거르개가 순서를 얻었으므로(검색 1 · 손잡이 2 · 거르개 3) 계정·신원
        묶음도 제 번호를 가져야 한다 — 안 그러면 기본값 0 이라 줄의 **맨 앞**
        으로 올라온다. 이 묶음의 내용은 이 요청이 건드리지 않았다
        (REQ-20260916-012-2n7g 로 따로 섰다)."""
        self.assertRegex(self.narrow, r"\.pgroup\.idcol\{[^}]*order:4",
                         "계정·신원 묶음이 순서를 안 받아 줄 맨 앞으로 올라온다")

    # ---------- 이 요청이 눈금을 새로 만들지 않았는가 ----------

    def test_no_new_breakpoint(self):
        """눈금이 늘면 다음 사람이 어느 폭을 봐야 하는지 알 수 없게 된다.
        이 저장소의 폭 눈금은 셋뿐이다: 1180 · 900 · 560."""
        found = set(re.findall(r"@media \(max-width:(\d+)px\)", self.tablet))
        self.assertEqual(found, {"1180", "900", "560"},
                         "tablet.css 의 폭 눈금이 셋이 아니다: %s" % sorted(found))


if __name__ == "__main__":
    unittest.main()
