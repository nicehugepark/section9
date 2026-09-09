"""보드가 첫 컬럼 카드의 왼쪽 획을 잘라 먹지 않는가 (REQ-20260827-058-62x6).

사용자: "open 상태의 카드 테두리 왼쪽이 잘려서 가려지는것같다." 캡처를 보면
카드의 **왼쪽 세로 획만** 없다 — 위·오른쪽·아래는 온전하다.

실브라우저로 재 봤더니 원인이 정확히 나왔다 (프록시로 geometry 측정):

    skin=calm tone=carbon
    board overflowX=auto  padL=0px  borderL=0px
    board contentLeft=26.00
    card  rect.left=26.00   → 여유 0.00px
    card  box-shadow= rgb(35,37,41) 0 0 0 1px , rgb(0,0,0) 0 14px 32px -26px

두 사실이 겹친 자리다.

  ① `.board` 는 가로 스크롤 컨테이너다(`overflow-x:auto`). overflow 는 스크롤이
     실제로 생기든 아니든 **자기 패딩 상자에서 자른다.**
  ② calm 의 어두운 톤에서 카드 윤곽은 `border` 가 아니라 `0 0 0 1px` **그림자
     링**이다(어두운 배경에서는 그림자가 안 보여 깊이를 링으로 준다). 링은
     박스 **바깥**에 그려진다.

첫 컬럼 카드는 판 왼쪽 끝에 정확히 붙어 있어(여유 0) 그 링의 왼쪽 1px 이 통째로
잘린다. 위·아래·오른쪽은 자르는 모서리에 닿지 않으니 살아남는다 — 사용자가 본
그림 그대로다.

같은 이유로 **포커스 링도 잘린다**: calm 의 `.card:focus-visible` 은
`outline:2px + outline-offset:2px` 라 박스 밖 4px 을 쓴다. 키보드로 첫 컬럼
카드를 짚으면 그 표시의 왼쪽이 사라진다 — 이건 보기 문제가 아니라 접근성이다.

그래서 고칠 것은 카드가 아니라 **판이 잘라 먹는 여유**다. 카드가 박스 밖에
그림을 그리는 스킨에서는 판이 그만큼 안쪽 여유를 준다.

다른 스킨은 안전하다(같은 측정):
    soft 여유 8px · cork 10px · glass 8px — 애초에 붙어 있지 않다
    ledger 여유 0px 이지만 box-shadow:none, border 0 — 박스 밖에 그리는 것이 없고
           포커스 링도 outline-offset 이 음수라 안쪽이다

실행: python3 tests/ card_edge_clip
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

# 박스 밖에 그리는 것 중 가장 먼 것 = 포커스 링(2px 굵기 + 2px 오프셋)
NEED_PX = 4


class CardEdgeClip(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()

    def test_board_is_a_clipping_scroll_container(self):
        """전제 ①: 판은 스크롤 컨테이너라 제 안에서 자른다.

        REQ-20260909-093 이 판을 세로로도 스크롤하게 만들면서 선언이
        `overflow-x:auto` 에서 `overflow:auto` 로 바뀌었다 — 자르는 성질은
        그대로이고 오히려 두 축 모두에 선다. 전제는 「가로만」이 아니라
        「스크롤 컨테이너인가」이므로 그 둘을 다 받는다."""
        m = re.search(r"\.board\{([^}]*)\}", self.src)
        self.assertIsNotNone(m, ".board 규칙을 찾지 못했다")
        self.assertRegex(m.group(1), r"overflow(-x)?\s*:\s*auto",
                         "이 계약의 전제가 사라졌다면 테스트도 다시 써야 한다")

    def test_dark_calm_draws_the_card_outline_outside_the_box(self):
        """전제 ②: 어두운 톤 calm 의 카드 윤곽은 박스 밖 1px 링이다."""
        m = re.search(r'\[data-skin="calm"\]\[data-theme="graphite"\][\s\S]{0,400}?'
                      r"--calm-shadow:([^;]*);", self.src)
        self.assertIsNotNone(m, "어두운 톤 calm 의 그림자 토큰을 찾지 못했다")
        self.assertRegex(m.group(1), r"0 0 0 1px",
                         "링이 사라졌다면 이 계약의 근거도 다시 확인해야 한다")

    def test_calm_board_leaves_room_for_what_is_drawn_outside(self):
        """판이 좌우로 잘림 여유를 준다 — 이 요청의 전부."""
        rules = re.findall(r'\[data-skin="calm"\] \.board\{([^}]*)\}', self.src)
        self.assertTrue(rules, "calm 의 .board 규칙을 찾지 못했다")
        pads = []
        for body in rules:
            for prop in ("padding", "padding-left", "padding-inline"):
                for m in re.finditer(prop + r"\s*:\s*([^;]+)", body):
                    parts = m.group(1).split()
                    # padding: <top> <inline> ... 에서 가로 값을 뽑는다
                    val = parts[1] if (prop == "padding" and len(parts) > 1) else parts[0]
                    n = re.match(r"([\d.]+)px", val.strip())
                    if n:
                        pads.append(float(n.group(1)))
        self.assertTrue(pads, "calm 판에 가로 여유가 아예 없다 — 첫 카드의 왼쪽 획이 잘린다")
        self.assertGreaterEqual(
            max(pads), NEED_PX,
            "여유가 %gpx 다 — 포커스 링(2px+2px)까지 살리려면 %dpx 이상이어야 한다"
            % (max(pads), NEED_PX))

    def test_focus_ring_sits_outside_in_calm_so_the_room_must_cover_it(self):
        """포커스 링이 박스 밖이라는 사실을 계약으로 붙들어 둔다."""
        m = re.search(r'\[data-skin="calm"\] \.card:focus-visible\{([^}]*)\}', self.src)
        self.assertIsNotNone(m, "calm 의 카드 포커스 규칙을 찾지 못했다")
        off = re.search(r"outline-offset:\s*(-?[\d.]+)px", m.group(1))
        self.assertIsNotNone(off, "포커스 링의 오프셋을 읽지 못했다")
        # 양수면 박스 밖 — 위 여유가 그것까지 덮어야 한다
        self.assertGreater(float(off.group(1)), 0,
                           "오프셋이 음수로 바뀌었다면 필요한 여유도 다시 계산해야 한다")

    def test_room_is_given_to_the_board_not_taken_from_the_card(self):
        """카드를 줄여서 해결하지 않는다 — 자르는 쪽이 판이므로 판이 양보한다.

        카드에 margin 을 주면 컬럼 간격(gap)과 두 벌이 되어 밀도가 어긋나고,
        나중에 gap 을 고칠 때 한 벌만 고쳐진다."""
        m = re.search(r'\[data-skin="calm"\] \.card\{([^}]*)\}', self.src)
        self.assertIsNotNone(m)
        self.assertNotRegex(m.group(1), r"margin-left|margin-inline",
                            "카드에 여백을 붙여 피했다 — 간격 규칙이 두 벌이 된다")

    def test_no_colour_fill_was_introduced(self):
        """고치면서 색면을 깔지 않는다 — 여유는 여백이지 판이 아니다."""
        rules = re.findall(r'\[data-skin="calm"\] \.board\{([^}]*)\}', self.src)
        for body in rules:
            for bg in re.findall(r"background\s*:\s*([^;}]+)", body):
                self.assertIn(bg.strip(), ("none", "transparent"),
                              "판에 색면이 생겼다: %s" % bg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
