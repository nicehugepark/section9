"""준비 신호는 한 자리에서 짓는다 — 그 자리의 판단을 잰다 (REQ-20260907-057).

전체 실행에서만 나던 간헐 실패의 뿌리는 격리가 아니라 시험 자신의 준비였다.
판이 섰다는 신호는 스크립트가 실린 시점에 서고, 화면이 서버에서 받아 오는
재료는 그 뒤 왕복으로 온다 — 그 틈이 병렬 실행에서 벌어진다(DOC-20260907-003).
`cdpreal.wait_ready` 가 그 신호를 짓는 한 자리이고, 이 파일은 **그 판단**을 잰다:
브라우저 없이, 화면 대신 답하는 판(FakePage)에게 사실을 받아서.

화면은 사실만 낸다(판이 섰나 · 재료가 어디까지 왔나 · 볼 자리가 있나). 판단이
파이썬 쪽에 있는 까닭이 이것이다 — 판단을 화면 안에 두면 실브라우저 없이는
그 판단이 맞는지 잴 수 없고, 못 재는 판단은 결국 아무도 안 고친다.

실행: python3 tests/ ready_signal
"""
import unittest

from cdpreal import HANDMADE_READY_OK, ready_missing, wait_ready


class FakePage:
    """화면 대신 답하는 판 — 물을 때마다 준비된 답을 차례로 낸다.

    답이 떨어지면 마지막 답을 되풀이한다(「그 상태로 머문다」).
    """

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = []

    def eval(self, expr):
        self.asked.append(expr)
        return self.answers[min(len(self.asked) - 1, len(self.answers) - 1)]


def facts(ready=True, supply=None, sel=None):
    return {"ready": ready, "supply": supply or {}, "sel": sel or {}}


class TheReadySignalWaitsForTheMaterial(unittest.TestCase):
    """판·재료·볼 자리 — 셋이 다 서야 잰다."""

    def test_nothing_is_missing_when_everything_stands(self):
        """정상 — 다 갖춰진 판에는 못 선 것이 없다(= 재도 된다)."""
        page = FakePage(facts(True, {"whoami": "ok", "projects": "ok"},
                              {"#viewer": True}))
        self.assertEqual(
            ready_missing(page, ("whoami", "projects"), "#viewer"), [])
        self.assertEqual(len(page.asked), 1, "한 번 물어 끝낼 것을 여러 번 물었다")

    def test_it_waits_and_returns_quietly_when_the_material_arrives(self):
        """정상 — 안 갖춰진 답 뒤에 갖춰진 답이 오면 기다렸다가 조용히 돌아온다."""
        page = FakePage(facts(False, {"whoami": ""}, {"#v": False}),
                        facts(True, {"whoami": "wait"}, {"#v": True}),
                        facts(True, {"whoami": "ok"}, {"#v": True}))
        wait_ready(page, ("whoami",), "#v", tries=10, gap=0)
        self.assertEqual(len(page.asked), 3, "기다린 횟수가 다르다")

    def test_no_material_names_mean_the_old_signal(self):
        """경계 — 재료 이름을 안 주면 옛 신호와 뜻이 같다: 판과 볼 자리만 본다."""
        page = FakePage(facts(True, {"whoami": "wait"}, {"#v": True}))
        self.assertEqual(ready_missing(page, (), "#v"), [],
                         "안 물은 재료가 판정을 막았다")
        bare = FakePage(facts(False, {}, {"#v": True}))
        self.assertEqual(len(ready_missing(bare, (), "#v")), 1,
                         "판이 안 섰는데 통과시켰다")

    def test_a_page_that_cannot_be_asked_counts_as_absent(self):
        """경계 — 물을 자리가 없는 옛 판은 「없음」으로 센다 — 조용히 통과 안 된다."""
        page = FakePage(facts(True, {"whoami": None}, {"#v": True}))
        miss = ready_missing(page, ("whoami",), "#v")
        self.assertEqual(len(miss), 1, "못 묻는 것을 「왔다」로 쳤다: %r" % miss)
        self.assertIn("whoami", miss[0])
        self.assertIn("없음", miss[0], "왜 못 섰는지가 이름에 안 담겼다")

    def test_the_names_and_the_states_are_in_the_break(self):
        """실패 — 끝내 안 오면 못 기다린 것의 이름과 상태를 담아 끊긴다."""
        page = FakePage(facts(True, {"whoami": "ok", "projects": "lost"},
                              {"#v": True}))
        with self.assertRaises(ConnectionError) as e:
            wait_ready(page, ("whoami", "projects"), "#v", tries=3, gap=0)
        self.assertIn("projects(lost)", str(e.exception))
        self.assertNotIn("whoami(", str(e.exception), "이미 온 것까지 이름을 댔다")
        self.assertEqual(len(page.asked), 3, "정한 횟수만큼 안 기다렸다")

    def test_a_board_that_never_stands_is_named(self):
        """실패 — 판이 서지 않으면 그 사실을 이름으로 댄다."""
        page = FakePage(facts(False, {}, {}))
        with self.assertRaises(ConnectionError) as e:
            wait_ready(page, (), (), tries=2, gap=0)
        self.assertIn("판", str(e.exception))

    def test_an_answer_that_is_not_facts_is_not_silence(self):
        """실패 — 사실을 못 받아 오면 빈 목록이 아니라 끊긴다."""
        with self.assertRaises(ConnectionError):
            ready_missing(FakePage(None), ("whoami",), "#v")

    def test_the_handmade_list_is_empty_for_now(self):
        """회귀 — 신호를 제 손으로 짓는 것이 허용된 시험은 지금 하나도 없다."""
        self.assertEqual(HANDMADE_READY_OK, {},
                         "허용 목록에 처음 이름을 올린다면 이 줄도 함께 고쳐라 — "
                         "사유를 두 자리에 적게 하는 것이 이 문턱이다"
                         "(BUDGET.json 의 라쳇과 같은 결)")


if __name__ == "__main__":
    unittest.main()
