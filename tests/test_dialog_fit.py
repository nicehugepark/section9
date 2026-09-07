"""창의 키는 위 모서리에서 시작해 바닥 여유까지 재고, 창은 세 띠다 (REQ-20260901-015 · -019).

실사고 2026-09-01: 계정 창이 4줄이 되자 하단 버튼(닫기·다시 시작)가 화면
밖으로 잘렸다. `.dlgbox` 의 max-height 가 100vh-96px 인데 top 은 최대
180px 라 — 시작점과 최대 키가 서로 다른 자를 썼다. 스크롤은 내용이
max-height 를 넘을 때만 생기므로 잘린 바닥에는 아무 손잡이도 없었다.

고정할 성질 하나: 시작점(top)과 최대 키(max-height)가 **같은 값**을 나눠
쓴다 — 그래야 top 이 얼마로 굳든 바닥 여유가 남는다.

실사고 2026-09-01 (2차, REQ-20260901-019): 키를 물린 뒤에도 모델 창의
바닥 버튼이 잘렸다 — 창이 **통째로** 굴렀기 때문이다. 머리도 바닥도 본문과
같은 흐름에 실려 있어서, 내용이 최대 키를 넘는 순간 바닥 띠가 접힌 자리
아래로 밀려났다(배율 125%, 뷰포트 1531×684).

고정할 성질 둘: ① 시작점(top)과 최대 키(max-height)가 같은 값을 나눠 쓴다 ·
② 창은 세로 세 띠(머리·본문·바닥)이고 **구르는 것은 본문 띠뿐**이다.

실행: python3 tests/ dialog_fit
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "..", "web", "css", "overlay.css")


class DialogFits(unittest.TestCase):
    def test_top_and_max_height_share_one_ruler(self):
        with open(CSS, encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"\.dlgbox\{[\s\S]*?\}", src)
        self.assertTrue(m, ".dlgbox 규칙이 없다")
        box = m.group(0)
        self.assertIn("--dlgtop:", box, "시작점 값이 이름을 잃었다")
        self.assertIn("top:var(--dlgtop)", box.replace(" ", ""),
                      "top 이 공용 자를 안 쓴다")
        self.assertRegex(
            box.replace(" ", ""),
            r"max-height:calc\(100vh-var\(--dlgtop\)-\d+px\)",
            "max-height 가 시작점을 빼지 않는다 — 바닥이 다시 잘린다")

    def test_three_bands_only_the_body_scrolls(self):
        """머리·바닥은 붙박이, 본문만 구른다 (REQ-20260901-019)."""
        with open(CSS, encoding="utf-8") as f:
            # 줄바꿈·들여쓰기만 걷는다 — 값 안의 한 칸(`0 0 auto`)은 문법이다
            src = re.sub(r"\s*\n\s*", "", f.read())
        box = re.search(r"\.dlgbox\{[\s\S]*?\}", src).group(0)
        self.assertIn("display:flex", box, "창이 띠로 서지 않는다")
        self.assertIn("flex-direction:column", box, "띠가 세로로 쌓이지 않는다")
        self.assertIn("overflow:hidden", box,
                      "창이 통째로 구른다 — 바닥 띠가 다시 접힌 자리로 밀려난다")
        self.assertNotIn("overflow:auto", box,
                         "창 자체가 구르면 머리·바닥이 흐름에 실린다")
        # 붙박이 기본값: 이름을 안 적은 새 띠는 안 구르는 쪽으로 굳는다
        self.assertIn(".dlgbox>*{flex:0 0 auto}", src, "직계 자식의 붙박이 기본이 없다")
        # 구르는 띠는 이름으로 지목한다 — 본문과 보관함·휴지통 판의 목록
        m = re.search(r"\.dlgbox>\.dlgbody,\.dlgbox>\.tlist\{([^}]*)\}", src)
        self.assertTrue(m, "구르는 띠(.dlgbody · .tlist)를 지목한 규칙이 없다")
        band = m.group(1)
        self.assertIn("flex:1 1 auto", band, "본문 띠가 남은 자리를 안 가져간다")
        self.assertIn("min-height:0", band,
                      "min-height:0 이 없으면 띠가 안 줄어 판이 다시 넘친다")
        self.assertIn("overflow:auto", band, "본문 띠가 구르지 않는다")


if __name__ == "__main__":
    unittest.main()
