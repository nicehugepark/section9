"""샤드가 끊기면 「끊긴 자리」를 말한다 — 66건이 실패로 적히지 않는다 (REQ-20260916-003-2n7g).

실제 사고 2026-09-15 23:30 (state/tests-async/c5b348449.log): 전체 회차가 66개
파일을 실패로 적었는데 unittest 의 FAIL/ERROR 은 **한 줄도 없었다.** 샤드 하나가
`test_after_commit_red` 의 한 시험 도중 출력이 잘린 채 끝났고, 러너가
`found or list(group)` 로 물러나 그 샤드의 파일 전부를 red 로 적은 것이다.
그 66개가 저장소 전체의 커밋 차단에 실렸고 **그중 진 것은 하나도 없었다** —
단독으로도, 같은 샤드 이웃과 함께도 통과했다. 65명에게 고칠 것 없는 것을 고치라고
말한 셈이고, 알림은 이름 66개를 늘어놓아 무엇을 볼지 알 수 없었다.

물러나는 것 자체는 옳다 — 죽은 샤드를 통과로 읽으면 안 된다. 틀린 것은 **말**이다:
「이 66개가 졌다」가 아니라 「이 샤드가 <시험> 에서 끊겼다」가 사실이다.

이 시험이 지키는 계약:
  ① 끊긴 자리는 출력의 **마지막으로 시작한** 시험이 말한다. 없으면 지어내지 않는다.
  ② 진 시험이 없는데 끝난 샤드는 그 한 자리만 red 에 싣는다 — 나머지는 「돌지
     못했다」이지 「졌다」가 아니다.
  ③ 진 시험이 있으면 종전대로 그것들만 싣는다(이 길은 바뀌지 않았다).
  ④ 끊김·상한 줄에 나머지 파일 이름을 늘어놓지 않는다 — 커밋 검사가 출력에서
     경로를 줍기 때문이다(s9-guard 의 gate_failure_paths).

실행: python3 tests/ shard_broke
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _runner():
    name = "s9_tests_main_probe"
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(
            name, os.path.join(HERE, "__main__.py")))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 그날 로그의 모양 그대로 — 여럿이 ok 로 끝나고, 마지막 하나가 결과 없이 잘린다.
CUT = """test_s3_a_missing_line_is_not_a_pass (test_release_try.Sums.test_s3) ... ok
test_s4_a_different_hash_fails (test_release_try.Sums.test_s4) ... ok
test_after_commit_consults_both (test_after_commit_red.FixCommit.test_after_commit_consults_both) ... """

WITH_FAIL = """test_a (test_x.C.test_a) ... ok
test_b (test_y.C.test_b) ... FAIL

======================================================================
FAIL: test_b (test_y.C.test_b)
----------------------------------------------------------------------
AssertionError: 1 != 2
"""


class WhereItWasCut(unittest.TestCase):
    """① 끊긴 자리는 마지막으로 시작한 시험이 말한다."""

    def setUp(self):
        self.m = _runner()

    def test_the_last_started_test_names_the_file(self):
        self.assertEqual(self.m.last_started_file(CUT), "test_after_commit_red.py")

    def test_a_finished_shard_still_points_at_its_last_test(self):
        self.assertEqual(self.m.last_started_file(WITH_FAIL), "test_y.py")

    def test_nothing_to_go_on_is_not_a_guess(self):
        """출력에 시험 표시가 없으면 빈 문자열 — 아무 파일이나 고르지 않는다."""
        for text in ("", "Killed\n", "Traceback (most recent call last):\n"):
            self.assertEqual(self.m.last_started_file(text), "", repr(text))


class OnlyWhatActuallyLost(unittest.TestCase):
    """②③ 진 것과 돌지 못한 것을 가른다."""

    def setUp(self):
        self.m = _runner()

    def test_a_cut_shard_marks_one_file_not_all(self):
        """그날의 66개가 다시는 서지 않는다."""
        self.assertEqual(self.m.red_files_from(CUT), [],
                         "진 시험이 없는 출력에서 진 파일을 찾아냈다")
        self.assertEqual(self.m.last_started_file(CUT), "test_after_commit_red.py")

    def test_real_failures_are_still_read_from_the_output(self):
        """③ 진 시험이 있으면 그 길은 그대로다."""
        self.assertEqual(self.m.red_files_from(WITH_FAIL), ["test_y.py"])

    def test_one_file_is_few_enough_to_be_retried_alone(self):
        """끊긴 자리 하나는 좁혀서-다시 실행이 단독으로 돌려 본다.

        그래서 그것이 간헐이면 회차가 통과로 뒤집히고 커밋 차단이 서지 않는다 —
        샤드 전부를 red 로 적던 때에는 66개가 상한(3개)을 넘겨 재실행조차 없었다.
        """
        self.assertTrue(self.m.should_retry(["test_after_commit_red.py"]))
        self.assertFalse(self.m.should_retry([f"test_{i}.py" for i in range(66)]),
                         "66개를 단독으로 다시 돌리려 든다")


class TheLineDoesNotListTheRest(unittest.TestCase):
    """④ 끊김·상한 줄에 나머지 이름을 늘어놓지 않는다."""

    def setUp(self):
        self.m = _runner()
        with open(os.path.join(HERE, "__main__.py"), encoding="utf-8") as f:
            self.src = f.read()

    def test_the_cut_line_names_only_where(self):
        i = self.src.index("[끊김] 샤드가 진 시험 없이 끝났다")
        chunk = self.src[i:i + 500]
        self.assertIn("{where}", chunk)
        self.assertNotIn("' '.join(group)", chunk,
                         "끊긴 샤드의 파일 이름을 전부 찍는다 — 커밋 검사가 그것을 줍는다")

    def test_the_timeout_line_names_only_where(self):
        i = self.src.index("[상한] 샤드가")
        chunk = self.src[i:i + 500]
        self.assertIn("{stuck}", chunk)
        self.assertNotIn("' '.join(group)", chunk)

    def test_a_real_failure_still_names_the_shard(self):
        """진짜 실패에는 샤드 목록이 남는다 — 커밋 검사가 그 줄로 시험을 고른다."""
        self.assertIn('f"실패한 샤드: {\' \'.join(group)}"', self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
