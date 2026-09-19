"""요청 전용 worktree 의 코드는 그 요청의 것이다 (REQ-20260916-013-2n7g).

실제로 막힌 자리 2026-09-16 04:0x, worktree `w-916-011-2n7g`:

    s9-guard: 다른 세션이 붙어 있는 중에, 그 사이 바뀐 파일을 담으려 합니다.
      지금 실행 중인 다른 세션: REQ-20260916-010-2n7g (백그라운드 작업 pid 15084, 31분째)
      최근에 바뀐 스테이지 파일: web/css/tablet.css (24초 전 바뀜) …

그 파일은 그 worktree 의 사본이고 REQ-010 을 맡은 세션은 제 worktree 에서 돌아 닿을 수
없다. 검사가 보던 `fresh_staged` 는 파일이 **왜** 새것인지 묻지 않고 mtime 만 본다 —
worktree 안에서 그 답은 늘 「내가 방금 고쳤다」다. 빠져나가는 길은 환경변수 접두
(`S9_ALLOW_CONCURRENT=<표>`)뿐인데 무인 세션의 allowlist 에 안 맞아 승인 대기로 떨어지고
승인할 사람이 없다. 그 세션은 FRESH_SEC(15분)이 지나기를 기다려 넘어갔다 — 해결이
아니라 대기다.

고정하는 계약 둘.
  ① 요청 전용 worktree(`…/state/worktrees/<이름>`)에서는 「방금 바뀐 파일」 검사를
     세우지 않는다.
  ② **검사의 힘은 그대로다** — 남이 담은 것(`recent_foreign_commits`)은 worktree 안에서도
     그대로 막고, 본 저장소와 다른 자리의 checkout 은 종전대로 두 검사를 다 받는다.

실행: python3 tests/ worktree_gate
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")

TMP = tempfile.mkdtemp(prefix="s9-wtgate-")
_prev = os.environ.get("S9_ROOT")
os.environ["S9_ROOT"] = TMP
try:
    _spec = importlib.util.spec_from_loader(
        "s9_guard_wt", importlib.machinery.SourceFileLoader("s9_guard_wt", GUARD))
    g = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(g)
finally:
    if _prev is None:
        os.environ.pop("S9_ROOT", None)
    else:
        os.environ["S9_ROOT"] = _prev


def worktree_under(main, name="w-916-013"):
    wt = os.path.join(main, "state", "worktrees", name)
    os.makedirs(wt, exist_ok=True)
    return wt


class WhereAmI(unittest.TestCase):
    """자리 판정 — 경로 모양만 본다(훅은 본체가 못 뜰 때도 돌아야 한다)."""

    def test_1_a_request_worktree_is_recognised(self):
        main = tempfile.mkdtemp(prefix="s9-wtmain-")
        self.assertTrue(g.in_request_worktree(worktree_under(main)))

    def test_2_the_main_checkout_is_not(self):
        main = tempfile.mkdtemp(prefix="s9-wtmain-")
        self.assertFalse(g.in_request_worktree(main))

    def test_3_a_checkout_somewhere_else_is_not(self):
        """다른 자리에 둔 checkout 은 종전대로 검사를 받는다 — 넓히지 않는다."""
        odd = tempfile.mkdtemp(prefix="s9-wtodd-")
        self.assertFalse(g.in_request_worktree(odd))

    def test_4_a_lookalike_path_is_not(self):
        """`state/` 아래가 아니면 이름이 worktrees 여도 아니다."""
        odd = tempfile.mkdtemp(prefix="s9-wtodd-")
        p = os.path.join(odd, "worktrees", "w-1")
        os.makedirs(p, exist_ok=True)
        self.assertFalse(g.in_request_worktree(p))


class TheGateInAWorktree(unittest.TestCase):
    """`concurrent_gate` 를 실제로 부른다 — 소스 글자를 대조하지 않는다."""

    def setUp(self):
        self.main = tempfile.mkdtemp(prefix="s9-wtmain-")
        self.wt = worktree_under(self.main)
        self.f = "web/css/tablet.css"
        for root in (self.main, self.wt):
            p = os.path.join(root, self.f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").close()      # 방금 만든 파일 = 방금 바뀐 파일

    def _gate(self, root, foreign=((), ())):
        workers = ["REQ-20260916-010-2n7g (백그라운드 작업 pid 15084, 31분째)"]
        with mock.patch.object(g, "ROOT", root), \
                mock.patch.object(g, "live_workers", lambda: list(workers)), \
                mock.patch.object(g, "recent_foreign_commits",
                                  lambda staged: (list(foreign[0]),
                                                  list(foreign[1]))):
            os.environ.pop(g.OVERRIDE, None)
            return g.concurrent_gate([self.f])

    def test_5_the_main_checkout_still_blocks(self):
        """본 저장소에서는 종전대로 막는다 — 이 요청이 푼 것은 worktree 뿐이다."""
        with self.assertRaises(SystemExit):
            self._gate(self.main)

    def test_6_a_request_worktree_passes(self):
        """worktree 안에서는 기다리지 않고 지나간다 — 이번 사고."""
        self.assertIsNone(self._gate(self.wt),
                          "제 사본을 담는데 15분을 기다리게 했다")

    def test_7_someone_elses_commit_still_blocks_in_a_worktree(self):
        """남이 담은 것은 worktree 안에서도 그대로 막는다 — 검사의 힘은 그대로다."""
        stop = [(self.f, "abc1234", 30, "남의 고침", "다른세션")]
        with self.assertRaises(SystemExit):
            self._gate(self.wt, foreign=(stop, ()))


class TheFlagsAgree(unittest.TestCase):
    """검사와 조회는 같은 값을 본다 (REQ-20260907-070) — 자리 판정이 끼어도 그렇다."""

    def setUp(self):
        self.main = tempfile.mkdtemp(prefix="s9-wtmain-")
        self.wt = worktree_under(self.main)
        self.f = "bin/s9.py"
        p = os.path.join(self.wt, self.f)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").close()

    def test_8_fresh_is_empty_inside_a_worktree(self):
        with mock.patch.object(g, "ROOT", self.wt), \
                mock.patch.object(g, "live_workers", lambda: ["REQ-x (pid 1, 1분째)"]), \
                mock.patch.object(g, "recent_foreign_commits",
                                  lambda staged: ([], [])):
            workers, fresh, foreign, unknown, names = g.concurrent_flags([self.f])
        self.assertTrue(workers, "작업자는 그대로 보인다 — 숨기는 것이 아니다")
        self.assertEqual(fresh, [], "worktree 안의 mtime 을 증거로 셌다")
        self.assertEqual(names, [])


if __name__ == "__main__":
    unittest.main()
