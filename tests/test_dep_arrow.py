"""화살촉이 보이는가 — 의존 엣지 렌더 계약 (REQ-20260826-009 반려 재작업).

반려 사유: "화살표 촉이 보이지 않는다."

원인은 촉의 크기 하나가 아니라 그리기 순서에 쌓인 네 겹이었다. 촉을 키우는
것만으로 고쳤다고 판단하면 같은 반려가 다시 난다 — 그래서 네 겹을 각각
계약으로 박는다.

  ① 획이 촉을 관통했다. 엣지 루프가 중심→중심으로 긋고 그 위에 삼각형을
     얹으니, 획이 촉을 지나 노드 중심까지 이어져 실루엣이 "끝이 좀 두꺼운 선"
     으로만 읽혔다. 삼각형은 밑변이 배경과 만나야 삼각형으로 보인다.
  ② 촉이 획과 같은 알파였다(0.60~0.92, 다른 노드 hover 중엔 0.16). 반투명한
     10px 삼각형은 배경에 녹는다.
  ③ 분리선이 없었다. 노드 상태 링·교차하는 계보 선과 겹치면 윤곽이 사라진다.
  ④ 밑변이 좁았다(L*0.44). 길이가 짧아지면 폭 4px대의 가는 다트가 되어
     9/5 대시 한 칸과 구별되지 않는다.

캔버스 그림은 단위 테스트로 픽셀을 볼 수 없다. 그래서 이 파일은 "무엇이
보이는가"가 아니라 **"보이지 않게 만들던 그리기 방식으로 되돌아갔는가"** 를
검사한다 — web/index.html 정적 계약(test_priority_visible.py와 같은 계보).
실제 가시성 판정은 사람의 캡처 검증이 맡는다.

리팩터링으로 이름이 바뀌면 이 파일도 같이 고쳐라. 고칠 때 지켜야 할 것은
이름이 아니라 위 네 줄이다.

실행: python3 tests/ dep_arrow
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

DASH_ON = 9      # 의존 획의 대시 한 칸 길이 — 촉은 이보다 확실히 커야 구별된다
HEAD_MIN = 11    # 촉 길이 하한 (대시 한 칸 + 여유)
BASE_MIN = 0.5   # 밑변 반폭 / 촉 길이 — 이보다 좁으면 삼각형이 아니라 다트다


def _read():
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def _blocked_branch(html):
    """의존 획이 실제로 그려지는 구간.

    분기 본문만 잘라 보면 안 된다 — 반려를 만든 코드는 경로(beginPath/moveTo/
    lineTo)를 **분기 바깥, 루프 머리에서** 미리 만들어 두고 분기 안에서 stroke
    만 했다. 분기부터 읽으면 그 관통 획이 시야 밖으로 빠져 계약이 헛돈다.
    그래서 엣지 루프 머리부터 분기의 `continue;` 까지를 본다.
    """
    m = re.search(r'if\s*\(\s*e\.rel\s*===\s*"blocked_by"\s*\)\s*\{', html)
    if not m:
        return ""
    head = list(re.finditer(r"for\s*\(\s*const\s+e\s+of\s+\w+\s*\)\s*\{", html[:m.start()]))
    start = head[-1].end() if head else m.end()
    rest = html[start:]
    end = rest.find("continue;")
    return rest[:end] if end >= 0 else rest


def _arrow_fn(html):
    """화살촉을 칠하는 함수 본문 — 닫힌 삼각형 경로를 fill 하는 곳."""
    for m in re.finditer(r"\n\s*function\s+(\w*[Aa]rrow\w*)\s*\([^)]*\)\s*\{", html):
        rest = html[m.end():]
        nxt = re.search(r"\n\s*function\s+\w+\s*\(", rest)
        body = rest[:nxt.start()] if nxt else rest
        if "closePath()" in body and "fill()" in body:
            return body
    return ""


def _geom_fn(html):
    """촉의 기하(길이 L·밑변 B·끝점)를 계산하는 함수 본문."""
    for m in re.finditer(r"\n\s*function\s+(\w+)\s*\([^)]*\)\s*\{", html):
        rest = html[m.end():]
        nxt = re.search(r"\n\s*function\s+\w+\s*\(", rest)
        body = rest[:nxt.start()] if nxt else rest
        if re.search(r"\bB\s*=\s*L\s*\*", body) and "Math.hypot" in body:
            return body
    return ""


class ArrowIsNotSwallowedByItsOwnStroke(unittest.TestCase):
    """① 획이 촉을 관통하면 안 된다 — 획은 촉의 밑변에서 끊긴다."""

    @classmethod
    def setUpClass(cls):
        cls.html = _read()
        cls.branch = _blocked_branch(cls.html)

    def test_arrow_is_not_swallowed_by_its_own_stroke(self):
        """① 획이 촉을 관통하면 안 된다 — 획은 촉의 밑변에서 끊긴다."""
        with self.subTest("a1_branch_exists"):
            self.assertTrue(self.branch.strip(),
                            "엣지 루프에 blocked_by 분기가 없다 — 의존 획 자체가 사라졌다")
        with self.subTest("a2_stroke_does_not_run_center_to_center"):
            # 반려를 만든 바로 그 모양: moveTo(노드중심) → lineTo(다른 노드중심).
            # 두 끝점이 모두 노드 중심이면 획이 촉을 관통한다.
            pat = re.compile(
                r"moveTo\(\s*sxOf\(\s*(\w+)\s*\)[^;]*?\)\s*;?\s*"
                r"ctx\.lineTo\(\s*sxOf\(\s*(\w+)\s*\)")
            hit = pat.search(self.branch)
            self.assertIsNone(
                hit,
                "의존 획을 노드 중심에서 노드 중심까지 긋고 있다 — 획이 화살촉을 "
                "관통해 실루엣이 '끝이 두꺼운 선'으로만 읽힌다(1차 반려의 원인). "
                "획의 끝점은 촉의 밑변이어야 한다")
        with self.subTest("a3_stroke_ends_at_head_base"):
            # 끝점은 기하 계산이 돌려준 밑변 좌표여야 한다. 이름을 bx/by 로 고정하지는
            # 않는다 — '노드 중심이 아닌 계산된 지점'이면 된다. 이 구간의 lineTo 는
            # 전부 그래야 하므로 하나만 보지 않고 전수로 검사한다.
            calls = re.findall(r"ctx\.lineTo\(([^)]*\)?[^)]*)\)", self.branch)
            self.assertTrue(calls, "blocked_by 획을 긋는 lineTo 가 없다")
            bad = [c for c in calls if "sxOf(" in c or "syOf(" in c]
            self.assertEqual(
                bad, [],
                f"의존 획의 끝점이 노드 중심 좌표다({bad}) — 촉의 밑변에서 끊어야 "
                "화살촉이 실루엣으로 남는다")

class ArrowHeadReadsAgainstEverything(unittest.TestCase):
    """②③ 촉은 획보다 진하고, 배경색 테두리로 주변에서 떨어진다."""

    @classmethod
    def setUpClass(cls):
        cls.html = _read()
        cls.branch = _blocked_branch(cls.html)
        cls.arrow = _arrow_fn(cls.html)

    def test_arrow_head_reads_against_everything(self):
        """②③ 촉은 획보다 진하고, 배경색 테두리로 주변에서 떨어진다."""
        with self.subTest("b1_arrow_painter_exists"):
            self.assertTrue(self.arrow.strip(), "화살촉을 칠하는 함수를 찾지 못했다")
        with self.subTest("b2_head_has_background_outline"):
            # 노드 링·교차 계보선과 겹쳐도 윤곽이 남으려면 배경색 테두리가 필요하다.
            self.assertRegex(
                self.arrow, r"strokeStyle\s*=\s*\w*[Bb]g\w*",
                "촉에 배경색 분리 테두리가 없다 — 노드 링·교차 엣지와 겹치면 윤곽이 사라진다")
            self.assertIn("stroke()", self.arrow,
                          "테두리 색만 정하고 긋지 않았다")
        with self.subTest("b3_head_color_is_not_the_stroke_color"):
            # 촉이 획과 같은 반투명 색이면 배경에 녹는다 — 별도의 (더 진한) 색이어야 한다.
            line = re.search(r"ctx\.strokeStyle\s*=\s*(\w+)\s*;", self.branch)
            self.assertIsNotNone(line, "의존 획의 strokeStyle 대입을 찾지 못했다")
            call = re.search(r"\b\w*[Aa]rrow\w*\(([^;]*)\)\s*;", self.branch)
            self.assertIsNotNone(call, "분기에서 화살촉 그리기 호출을 찾지 못했다")
            passed = [a.strip() for a in call.group(1).split(",")]
            self.assertNotIn(
                line.group(1), passed,
                f"촉을 획과 같은 색 변수({line.group(1)})로 칠하고 있다 — 그 색은 "
                "반투명(hover 중엔 0.16)이라 촉이 배경에 녹는다. 촉은 획보다 "
                "한 단계 진해야 한다")

class ArrowHeadIsBigEnoughToBeATriangle(unittest.TestCase):
    """④ 대시 한 칸과 구별되는 크기·비율이어야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.html = _read()
        cls.geom = _geom_fn(cls.html)

    def test_arrow_head_is_big_enough_to_be_a_triangle(self):
        """④ 대시 한 칸과 구별되는 크기·비율이어야 한다."""
        with self.subTest("c1_geometry_fn_exists"):
            self.assertTrue(self.geom.strip(), "촉 기하를 계산하는 함수를 찾지 못했다")
        with self.subTest("c2_length_floor_clears_one_dash"):
            floors = [float(x) for x in re.findall(r"Math\.max\(\s*(\d+(?:\.\d+)?)", self.geom)]
            self.assertTrue(floors, "촉 길이에 하한이 없다 — 줌아웃하면 촉이 사라진다")
            self.assertGreaterEqual(
                max(floors), HEAD_MIN,
                f"촉 길이 하한이 {max(floors)}px 다. 의존 획의 대시 한 칸이 "
                f"{DASH_ON}px 이므로 이보다 크지 않으면 촉이 '대시 한 칸'과 구별되지 "
                f"않는다 (하한 {HEAD_MIN}px 이상)")
        with self.subTest("c3_base_is_wide_enough"):
            m = re.search(r"\bB\s*=\s*L\s*\*\s*(\d*\.?\d+)", self.geom)
            self.assertIsNotNone(m, "밑변 반폭(B)을 촉 길이(L)에서 파생하지 않았다")
            k = float(m.group(1))
            self.assertGreaterEqual(
                k, BASE_MIN,
                f"밑변 반폭이 길이의 {k}배다 — 이보다 좁으면 화살촉이 아니라 가는 "
                f"다트로 보이고, 길이가 하한까지 줄면 대시와 구별되지 않는다 "
                f"({BASE_MIN} 이상)")

class ArrowVanishesWhenTheDependencyEnds(unittest.TestCase):
    """수명 규칙 (DOC-20260826-001 규칙 4): 끝난 의존은 그리지 않는다.

    촉을 잘 보이게 만든 만큼, 끝난 의존까지 또렷하게 그리면 그래프가 과거로
    채워진다. 화살표 가시성과 한 쌍인 계약이라 같이 둔다.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = _read()

    def test_d1_edge_filter_drops_finished_ends(self):
        m = re.search(r'e\.rel\s*===\s*"blocked_by"\s*&&\s*\(([^\n]*)\)', self.html)
        self.assertIsNotNone(
            m, "그래프 엣지 필터에서 blocked_by 수명 조건을 찾지 못했다")
        cond = m.group(1)
        self.assertEqual(
            cond.count("DEP_DEAD"), 2,
            "양끝 중 한쪽만 검사하고 있다 — 선행이 끝난 경우와 후행이 먼저 끝난 "
            "경우 둘 다 그리지 않아야 한다(서버는 후자를 지우지 않는다)")


if __name__ == "__main__":
    unittest.main()
