"""글로만 있던 규칙 둘이 기계로 선다 (REQ-20260916-008-62x6).

staff-engineer 실측 2026-09-16: 규약의 규율 아홉이 글로만 있고 아무 장치도
막지 않는다. 그리고 그 되풀이 모양이 이 저장소의 이력에 있다 — 12조
「담긴 것만 review」는 **세 번째** 사고에서야 전이가 막았다.

오늘 리드가 그중 둘을 직접 어겼다. 그래서 그 둘부터 세운다.
- **13조** — done 근거가 시험뿐: 실측 최근 done 전이 40건 중 13건(33%).
- **17조** — 거부당한 것을 고치지 않고 다시 걸기: 리드가 오늘 세 번 그랬다.

둘 다 **막지 않는다** — 짚기만 한다. 막으면 옳은 자리까지 서고, 서는 순간
사람은 우회를 찾는다.

실행: python3 tests/ rule_guards
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TheDoneEvidenceIsNudged(unittest.TestCase):
    """13조 — 「시험 N건 통과」는 사람이 받을 것이 섰다는 증거가 아니다."""

    def setUp(self):
        self.m = _load("s9_rg", os.path.join(HERE, "..", "bin", "s9.py"))

    def nudge(self, goal, note):
        return self.m.goal_evidence_nudge(goal, note)

    # 사고의 본체 — goal 은 화면인데 근거는 시험뿐
    def test_a_tests_only_note_is_nudged(self):
        n = self.nudge("Settings 에서 보고 고칠 수 있다", "시험 19건 통과")
        self.assertIn("13조", n)
        self.assertIn("막지 않습니다", n)

    # 직접 본 자취가 하나라도 있으면 짚지 않는다
    def test_direct_verification_is_not_nudged(self):
        for note in ("시험 19건 통과 · 화면을 열어 봤다",
                     "시험 통과, 그리고 그 명령을 쳐 봤다",
                     "테스트 8건 통과 — 캡처를 찍어 눈으로 확인했다",
                     "시험 통과하고 값이 파일에 앉는 것을 직접 봤다"):
            with self.subTest(note=note[:20]):
                self.assertEqual("", self.nudge("화면에서 고칠 수 있다", note))

    # goal 자체가 시험이면 시험이 곧 근거다 — 옳은 것을 짚지 않는다
    def test_a_test_shaped_goal_is_not_nudged(self):
        for goal in ("실패한 파일이 통과하고 통과 기록이 남는다",
                     "세 시험이 main 에서 통과한다",
                     "회귀 테스트가 그 자리를 지킨다"):
            with self.subTest(goal=goal[:16]):
                self.assertEqual("", self.nudge(goal, "시험 12건 통과"))

    # 시험을 아예 안 댄 근거는 이 짚기의 몫이 아니다
    def test_a_note_without_tests_is_not_nudged(self):
        self.assertEqual("", self.nudge("화면이 선다", "캡처로 확인했다"))
        self.assertEqual("", self.nudge("화면이 선다", ""))


class TheUnreadRefusalIsNudged(unittest.TestCase):
    """17조 — 고친 것 없이 다시 거는 것은 재시도가 아니라 안 읽은 것이다."""

    def setUp(self):
        self.m = _load("s9c_rg", os.path.join(HERE, "..", "bin", "s9_commit.py"))
        self.root = tempfile.mkdtemp(prefix="s9rg-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.f = os.path.join(self.root, "a.py")
        self.write("첫 판")

    def write(self, t):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(t)

    # 거부가 없었으면 아무 말도 않는다
    def test_nothing_is_said_without_a_refusal(self):
        self.assertEqual("", self.m.unread_refusal(self.root, ["a.py"]))

    # 사고의 본체 — 안 고치고 다시 건다
    def test_re_running_without_a_change_is_nudged(self):
        self.m._remember_refusal(self.root, ["a.py"])
        n = self.m.unread_refusal(self.root, ["a.py"])
        self.assertIn("17조", n)
        self.assertIn("읽을 때", n)
        self.assertIn("막지 않습니다", n)

    # 고쳤으면 그것이 재시도다
    def test_a_real_fix_is_not_nudged(self):
        self.m._remember_refusal(self.root, ["a.py"])
        self.write("고쳤다")
        self.assertEqual("", self.m.unread_refusal(self.root, ["a.py"]))

    # 다른 것을 걸면 이 짚기의 몫이 아니다
    def test_a_different_target_is_not_nudged(self):
        self.m._remember_refusal(self.root, ["a.py"])
        self.assertEqual("", self.m.unread_refusal(self.root, ["b.py"]))

    # 오래되면 잊는다 — 어제 거부를 오늘 짚지 않는다
    def test_an_old_refusal_is_forgotten(self):
        self.m._remember_refusal(self.root, ["a.py"])
        import time as _t
        self.assertEqual("", self.m.unread_refusal(
            self.root, ["a.py"], now=_t.time() + 3600))


if __name__ == "__main__":
    unittest.main()
