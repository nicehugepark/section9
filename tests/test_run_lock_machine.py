"""전체 회차는 컴퓨터 하나에 하나다 (REQ-20260916-005-2n7g).

실측 2026-09-16 00:29~00:33, 이 맥. 본 저장소의 전체 회차와 작업자 worktree 의
전체 회차가 각각 샤드 여덟으로 동시에 돌았다. 값은 둘이었다 —

  · 한 회차가 메모리 부족으로 죽었고(하네스가 세웠다),
  · 살아남은 회차가 헛된 실패 둘(test_port_pin_ghost · test_link_newtab)을 냈다.
    두 파일 다 단독으로는 통과한다. 그 빨강이 커밋 차단으로 다음 사람까지 막았다.

러너에는 이미 실행 잠금이 있었다(hold_run_lock). 못 본 것은 **잠금이 사는 자리**다:
`RUN_LOCKS = <REPO>/state/jobs` 인데 worktree 의 REPO 는 그 worktree 라, 두 회차가
서로 다른 파일을 잠그고 서로를 못 봤다. CPU 도 메모리도 포트도 컴퓨터 하나의
것이니 「이미 돌고 있나」를 묻는 자리도 컴퓨터 하나에 한 벌이어야 한다.

실행: python3 tests/ run_lock_machine
"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "__main__.py")


def runner_mod():
    """러너를 모듈로 읽는다 — main() 은 __main__ 가드 뒤라 안 돈다."""
    sys.path.insert(0, HERE)
    spec = importlib.util.spec_from_loader(
        "s9_runner_lock", importlib.machinery.SourceFileLoader(
            "s9_runner_lock", RUNNER))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class LockLivesOnTheMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = runner_mod()

    def test_1_a_worktree_climbs_to_the_main_checkout(self):
        """작업자 worktree 의 잠금은 본 저장소의 자리다 — 이번 사고."""
        main = tempfile.mkdtemp(prefix="s9lockmain-")
        os.makedirs(os.path.join(main, "bin"), exist_ok=True)
        wt = os.path.join(main, "state", "worktrees", "w-916-004")
        os.makedirs(wt, exist_ok=True)
        self.assertEqual(self.m._machine_root(wt), main,
                         "worktree 가 제 잠금을 따로 썼다")

    def test_2_the_main_checkout_stays_itself(self):
        """본 저장소는 그대로 제 자리를 쓴다."""
        main = tempfile.mkdtemp(prefix="s9lockmain-")
        os.makedirs(os.path.join(main, "bin"), exist_ok=True)
        self.assertEqual(self.m._machine_root(main), main)

    def test_3_a_worktree_somewhere_else_is_left_alone(self):
        """다른 자리에 둔 worktree 는 종전대로 — 넓히지 않는다."""
        odd = tempfile.mkdtemp(prefix="s9lockodd-")
        self.assertEqual(self.m._machine_root(odd), odd)

    def test_4_no_bin_means_not_a_checkout(self):
        """`bin/` 이 없으면 본 저장소가 아니다 — 아무 데나 올라가지 않는다."""
        main = tempfile.mkdtemp(prefix="s9lockmain-")     # bin/ 없음
        wt = os.path.join(main, "state", "worktrees", "w-x")
        os.makedirs(wt, exist_ok=True)
        self.assertEqual(self.m._machine_root(wt), wt)

    def test_5_run_locks_points_at_the_machine_root(self):
        """RUN_LOCKS 가 그 자리를 쓴다 — 상수가 함수를 지나야 뜻이 산다."""
        self.assertEqual(
            self.m.RUN_LOCKS,
            os.path.join(self.m._machine_root(self.m.REPO), "state", "jobs"))

    def test_6_the_green_record_stays_per_tree(self):
        """통과 기록은 tree 마다 그대로 — 내용이 다르면 결과도 다르다."""
        self.assertEqual(self.m.REUSE_DIR,
                         os.path.join(self.m.REPO, "state", "tests-green"))


if __name__ == "__main__":
    unittest.main()
