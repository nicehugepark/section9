"""Docs 목록은 최근 수정 순 · 못 도는 명령은 미리 말한다
(REQ-20260827-051 · REQ-20260827-050).

**정렬** — Board 는 "무엇부터 집을까"를 묻는 화면이라 우선순위가 앞선다. Docs 는
"무슨 일이 있었나"를 훑는 화면이라 최근 수정이 앞서야 한다. 우선순위 50짜리 옛
문서가 방금 고친 문서 위에 앉아 있으면 훑는 일이 안 된다.

정렬 규칙은 `workOrder` 한 곳에 모여 있다는 것이 이 화면의 약속이다. 그래서
변형도 **그 옆에** 두고, 목록 만드는 자리에서 `.sort()` 를 새로 부르지 않는다.

**N2 를 다시 썼다** (REQ-20260828-009). 최근순이라는 뜻은 그대로지만, 목록이
**매 렌더마다** 다시 정렬하면 안 된다. 이 저장소는 에이전트가 쉬지 않고 노트를
붙여서 15초 폴링 때마다 여러 문서의 `updated` 가 바뀌고 목록 전체가 다시 섞였다 —
사용자가 그것을 겪었다: "왼쪽 문서 목록이 거의 실시간으로 목록이 갱신이 되어버리니
본문 제목을 캐치하기 어렵다." 그래서 `stableOrder` 를 통해 쓴다: **처음 한 번은
recentOrder 로 순위를 매기고**, 그 뒤로는 그 순위를 얼려 둔다. 얼음을 깨는 것은
사람이 조건을 바꾸거나 화면에 새로 들어올 때뿐이고, 새로 생긴 문서는 맨 위로 온다.
"Docs 는 최근순"이라는 계약은 유지되고, "매번 다시 섞는다"만 빠졌다.

**팔레트** — `/permissions` 처럼 대시보드에서 못 도는 CC 명령이 목록에 없으면,
사용자가 친 그 줄이 **그냥 채팅 메시지로 전송된다.** 그러면 리드가 "그건 터미널에서만
됩니다"라고 답하는 데서 끝난다 — 팔레트가 미리 말해 주는 편이 한 왕복 빠르다.
(이 세션에서 실제로 그렇게 한 왕복을 썼다.)

실행: python3 tests/ docs_recent_order
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class DocsRecentOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # N1. 최근순 정렬 규칙이 있다
    def test_docs_recent_order(self):
        """DocsRecentOrder 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_recent_order_exists"):
                self.assertIn("const recentOrder", self.src)
                m = re.search(r"const recentOrder = rows =>(.*?);\n", self.src, re.S)
                self.assertIsNotNone(m)
                body = m.group(1)
                self.assertIn("updated", body)
                self.assertNotIn("prioOf", body,
                                 "Docs 정렬에 우선순위가 섞였다 — 최근순이어야 한다")

            # N2. Docs 목록이 그것을 쓴다 — 다만 **얼려서** (REQ-20260828-009)
        with self.subTest("n2_docs_uses_it"):
                m = re.search(r"async function renderDocs\(rows\)\{(.*?)\n\}\n",
                              self.src, re.S)
                self.assertIsNotNone(m)
                self.assertIn("stableOrder(rows,", m.group(1),
                              "Docs 목록이 정해진 순서를 쓰지 않는다")
                self.assertNotIn("recentOrder(rows)", m.group(1),
                                 "목록이 매 렌더마다 다시 정렬한다 — 15초마다 발밑이 흔들린다")
                # 얼린 순서의 **뿌리**는 여전히 최근순이다
                f = re.search(r"function stableOrder\([^)]*\)\{(.*?)\n\}\n", self.src, re.S)
                self.assertIsNotNone(f, "stableOrder 를 찾지 못했다")
                self.assertIn("recentOrder(rows)", f.group(1),
                              "처음 순위가 최근순이 아니다")

            # B1. Board 는 그대로 우선순위 순이다 — 두 화면의 물음이 다르다
        with self.subTest("b1_board_keeps_priority"):
                m = re.search(r"const workOrder = rows =>(.*?);\n", self.src, re.S)
                self.assertIsNotNone(m)
                self.assertIn("prioOf", m.group(1))

            # R1. 정렬은 한 자리에 모여 있다 — 목록 만드는 곳에서 새로 sort 하지 않는다
        with self.subTest("r1_no_scattered_sort_in_docs"):
                m = re.search(r"async function renderDocs\(rows\)\{(.*?)\n\}\n",
                              self.src, re.S)
                self.assertNotIn(".sort(", m.group(1),
                                 "Docs 렌더 안에서 정렬을 새로 걸고 있다")

            # N3. 대시보드에서 못 도는 명령을 팔레트가 미리 말한다
        with self.subTest("n3_cli_only_commands_listed"):
            m = re.search(r"const CC_BUILTINS = \[(.*?)\]\.map", self.src, re.S)
            self.assertIsNotNone(m)
            block = m.group(1)
            for name in ("permissions", "hooks"):
                self.assertIn(f'"{name}"', block,
                              f"/{name} 이 CLI 전용 목록에 없다 — 채팅으로 전송된다")

if __name__ == "__main__":
    unittest.main()
