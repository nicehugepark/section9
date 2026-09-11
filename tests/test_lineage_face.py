"""카드의 「만든이」가 한 이름으로 서는가 (REQ-20260911-016).

주인 지적 2026-09-11 20:42: 「카드에서 '만든 사람' 항목이 잘려서 나온다.
'만든 사람'이라는 레이블 자체가 필요한가? … 만든 사람에 타치코마가 있고,
에이전트가 있는데 무슨 차이야?」

세 가지가 겹쳐 있었다.
 ① 칩과 손 위의 글이 **각자** 이름을 지었다 — 칩은 `originWho` 를 날것으로 써서
    「designer」 한 낱말만, 손 위의 글은 「에이전트 designer」를 냈다.
 ② `who === "리드"` 비교는 참이 될 수 없었다(`originWho` 는 「타치코마」를 돌려준다)
    — 그 자리에서 「에이전트 타치코마」라는 없는 말이 나왔다.
 ③ 폭 판정이 배지 폭을 **가정한** 산식이라, 긴 계정 이름에서는 값이 「에…」로
    뭉개졌다. 이제 렌더 뒤에 실제로 재서 온전히 세우거나 통째로 뺀다.

여기서 보는 것은 계약이지 구현이 아니다: 어느 자리에서 지어지든 **한 문서는 한
이름으로 불린다**, 리드도 갈래를 달고 선다, 잘린 채로 남지 않는다.

실행: python3 tests/ lineage_face
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = os.path.join(HERE, "..", "web", "app", "card.js")
BOARD = os.path.join(HERE, "..", "web", "css", "board.css")


class TheCreatorHasOneName(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(CARD, encoding="utf-8") as f:
            cls.js = f.read()
        # 주석을 걷은 원천 — 계약은 코드에 있어야 하고, 주석이 사고의 경위를
        # 적는 것은 막지 않는다(이 저장소의 주석은 그 몫을 진다).
        bare = re.sub(r"/\*.*?\*/", " ", cls.js, flags=re.S)
        cls.code = re.sub(r"//[^\n]*", " ", bare)
        with open(BOARD, encoding="utf-8") as f:
            cls.css = f.read()

    def body(self, name):
        """그 함수의 몸통만 — 주석의 낱말이 계약으로 읽히지 않게."""
        m = re.search(rf"function {name}\(([^)]*)\)\s*\{{", self.js)
        self.assertIsNotNone(m, f"{name} 가 없다")
        i = m.end() - 1
        depth, j = 0, i
        while j < len(self.js):
            if self.js[j] == "{":
                depth += 1
            elif self.js[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        src = self.js[i:j + 1]
        # 주석은 걷어 낸다 — 계약은 코드에 있어야 한다
        src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
        return re.sub(r"//[^\n]*", " ", src)

    # A1 — 이름을 짓는 자리는 하나다
    def test_a1_one_place_builds_the_face(self):
        self.assertTrue("function originFace(" in self.code,
                        "만든이의 이름을 짓는 한 자리가 없다")
        chip = self.body("lineageChip")
        self.assertIn("originFace(", chip,
                      "카드 칩이 제 손으로 이름을 짓는다 — 손 위의 글과 갈린다")
        self.assertNotIn("originWho(", chip,
                         "카드 칩이 `originWho` 를 날것으로 쓴다 — 위임 역할이 "
                         "「designer」 한 낱말로만 서서 문서 머리와 다른 말이 된다")
        bits = self.body("originBits")
        self.assertIn("originFace(", bits,
                      "손 위의 글이 제 손으로 이름을 짓는다")

    # A2 — 리드도 갈래를 달고 선다 (주인 물음 ③)
    def test_a2_the_lead_wears_its_kind(self):
        face = self.body("originFace")
        self.assertIn("리드 타치코마", face,
                      "리드만 갈래 없이 이름으로 선다 — 옆 카드의 "
                      "「에이전트 designer」와 딴 종류로 읽힌다")
        self.assertIn("에이전트 ${", face, "위임 역할에 갈래가 안 붙는다")

    # A3 — 참이 될 수 없던 비교가 사라졌다
    def test_a3_the_dead_branch_is_gone(self):
        self.assertFalse(
            'who === "리드"' in self.code,
            "`originWho` 는 리드를 「타치코마」로 돌려준다 — "
            '`who === "리드"` 는 참이 될 수 없고, 그 탓에 '
            "「에이전트 타치코마」라는 없는 말이 나왔다")

    # A4 — 같은 말을 두 번 하지 않는다
    def test_a4_the_tooltip_does_not_repeat_the_face(self):
        tell = self.body("lineageTell")
        self.assertIn("만든이", tell, "손 위의 글의 낱말이 카드와 다르다")
        self.assertNotIn("originBits(", tell,
                         "꼬리에 기원을 통째로 붙이면 "
                         "「만든이 에이전트 designer (에이전트 designer)」가 된다")

    # A5 — 라벨은 두 화면에서 같은 한 낱말이다
    def test_a5_one_word_on_both_screens(self):
        for fn in ("lineageChip", "lineageRowHTML"):
            b = self.body(fn)
            self.assertIn("만든이", b, f"{fn} 의 라벨이 「만든이」가 아니다")
            self.assertNotIn("만든 사람", b,
                             f"{fn} 가 같은 것을 다른 낱말로 부른다")

    # A6 — 잘린 채로 남지 않는다: 재서 빼는 자리가 있다
    def test_a6_whole_or_absent_is_measured(self):
        self.assertIn("function fitLineage(", self.js,
                      "폭 판정이 여전히 가정(배지 87.8px)에만 기댄다")
        fit = self.body("fitLineage")
        self.assertIn("scrollWidth", fit, "재지 않고 판정한다")
        self.assertIn("linhide", fit, "재고 나서 빼는 자리가 없다")
        # 먼저 다 세우고(remove) 다음에 뺀다(add) — 읽기·쓰기를 섞지 않는다
        self.assertLess(fit.index('classList.remove("linhide")'),
                        fit.index("scrollWidth"),
                        "숨긴 채로 재면 폭이 0 이라 판정이 굳는다")
        m = re.search(r"\.card\s+\.m\.mwho>\.lin\.linhide\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m, "빼는 CSS 규칙이 없다")
        self.assertIn("display:none", m.group(1).replace(" ", ""))

    # A7 — 렌더 뒤에도, 창 폭이 바뀐 뒤에도 잰다
    def test_a7_measured_after_render_and_resize(self):
        self.assertTrue('fitLineage($("#view"))' in self.code,
                        "판을 새로 그린 뒤에 재지 않는다")
        soon = self.body("markClampedSoon")
        self.assertIn("fitLineage", soon,
                      "창 폭이 바뀌면 잘림도 바뀐다 — 그때 다시 재지 않으면 "
                      "빠진 칩이 빠진 채로, 잘린 칩이 잘린 채로 남는다")


if __name__ == "__main__":
    unittest.main()
