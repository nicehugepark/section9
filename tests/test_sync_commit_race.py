"""동기화가 진행 중인 커밋과 부딪히지 않는다 (REQ-20260906-030).

문서 이벤트마다 도는 sync 의 즉시 커밋이 리드의 `git commit` 과 같은 순간 겹치면
리드 쪽이 `cannot lock ref 'HEAD'` 로 실패했다(실측 2026-09-06 09:2x·09:43).
pre-commit(s9-guard) 이 시작에 state/commit-in-progress 표식을 만들고 post-commit 이
지운다; sync_run 은 그 표식이나 .git/index.lock 을 보면 그 회차를 건너뛰고(busy),
자기 commit 이 잠금 실패면 0.5초 뒤 한 번만 다시 한다.

흉내 방식은 tests/test_sync_classify.py 와 같다 — _sync_git 을 mock 으로.

실행: python3 tests/ sync_commit_race
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
GUARD = os.path.join(REPO, "bin", "s9-guard")
INSTALL = os.path.join(REPO, "bin", "s9-install")

LOCK_REF = "fatal: cannot lock ref 'HEAD': is at 1111111 but expected 2222222\n"
LOCK_IDX = "fatal: Unable to create '/x/.git/index.lock': File exists.\n"


class CP:
    def __init__(self, rc=0, err="", out=""):
        self.returncode, self.stderr, self.stdout = rc, err, out


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class SyncCommitRace(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9syncrace-")
        os.makedirs(os.path.join(self.root, "state"))
        os.makedirs(os.path.join(self.root, ".git"))
        self.old_root = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = self.root
        self.m = _load("s9_syncrace", S9)
        self.calls = []
        self.sleeps = []

    def tearDown(self):
        if self.old_root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self.old_root
        shutil.rmtree(self.root, ignore_errors=True)

    def run_sync(self, commit=(), transport=True):
        q = list(commit)

        def fake(*argv, timeout=6):
            self.calls.append(argv)
            if argv[0] == "diff":
                return CP(out="vault/x.md\n")
            if argv[0] == "commit" and q:
                return q.pop(0)
            return CP()
        with mock.patch.object(self.m, "_sync_git", fake), \
                mock.patch.object(self.m, "sync_mode", lambda: "remote"), \
                mock.patch("time.sleep", self.sleeps.append):
            return self.m.sync_run("t", transport=transport)

    def commits(self):
        return [c for c in self.calls if c[0] == "commit"]

    def mark(self, age_sec=0):
        p = os.path.join(self.root, "state", "commit-in-progress")
        with open(p, "w", encoding="utf-8") as f:
            f.write("pid 1\n")
        if age_sec:
            t = time.time() - age_sec
            os.utime(p, (t, t))
        return p

    # S1. 표식이 있으면 그 회차를 건너뛴다 — commit 을 부르지 않는다
    def test_s1_marker_skips_this_round(self):
        self.mark()
        r = self.run_sync(transport=False)
        self.assertEqual(r, "busy")
        self.assertEqual(self.commits(), [], "커밋이 진행 중인데 sync 가 commit 을 걸었다")
        self.assertFalse(os.path.exists(os.path.join(self.root, "state", ".sync.lock")),
                         "건너뛴 회차가 .sync.lock 을 남겼다")
        self.assertTrue(os.path.exists(self.m._SYNC_QUEUE),
                        "건너뛴 회차는 큐를 남겨 다음 회차가 다시 하게 해야 한다")

    # S2. .git/index.lock 이 있으면 건너뛴다
    def test_s2_index_lock_skips_this_round(self):
        open(os.path.join(self.root, ".git", "index.lock"), "w").close()
        r = self.run_sync()
        self.assertEqual(r, "busy")
        self.assertEqual(self.commits(), [])

    # S3. 오래된 표식(5분 초과)은 죽은 커밋의 잔재다 — 무시하고 평소대로 간다
    def test_s3_stale_marker_is_ignored(self):
        self.mark(age_sec=self.m.SYNC_COMMIT_BUSY_STALE_SEC + 60)
        r = self.run_sync()
        self.assertEqual(r, "ok")
        self.assertEqual(len(self.commits()), 1)

    # S4a. commit 이 잠금 실패면 0.5초 뒤 한 번 더 — 두 번째가 통과하면 ok
    def test_s4a_lock_failure_retries_once_then_ok(self):
        r = self.run_sync(commit=[CP(1, LOCK_REF), CP(0)])
        self.assertEqual(r, "ok")
        self.assertEqual(len(self.commits()), 2)
        self.assertEqual(self.sleeps, [self.m.SYNC_RETRY_BASE_SEC])

    # S4b. 두 번째도 잠금 실패면 error — 세 번째는 없다
    def test_s4b_lock_failure_twice_is_error(self):
        r = self.run_sync(commit=[CP(1, LOCK_IDX), CP(1, LOCK_IDX)])
        self.assertEqual(r, "error")
        self.assertEqual(len(self.commits()), 2)

    # S4c. 잠금이 아닌 실패는 재시도하지 않는다
    def test_s4c_other_failure_no_retry(self):
        r = self.run_sync(commit=[CP(1, "error: pre-commit hook rejected\n")])
        self.assertEqual(r, "error")
        self.assertEqual(len(self.commits()), 1)
        self.assertEqual(self.sleeps, [])


    def idx_lock(self, age_sec=0):
        p = os.path.join(self.root, ".git", "index.lock")
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        if age_sec:
            t = time.time() - age_sec
            os.utime(p, (t, t))
        return p

    # S6. 5분 넘은 index.lock 은 중단된 commit 의 잔재다 — 제거하고 평소대로 간다
    #     (REQ-20260912-004-62x6: 이 파일 하나에 자동 commit 이 79회 연속 졌다)
    def test_s6_stale_index_lock_is_removed(self):
        lock = self.idx_lock(age_sec=self.m.SYNC_COMMIT_BUSY_STALE_SEC + 60)
        r = self.run_sync()
        self.assertEqual(r, "ok")
        self.assertEqual(len(self.commits()), 1)
        self.assertFalse(os.path.exists(lock),
                         "5분 넘은 index.lock 이 그대로 남아 다음 회차도 진다")

    # S7. 5분이 안 된 index.lock 은 진행 중인 commit 의 것이다 — 건드리지 않는다
    def test_s7_fresh_index_lock_is_kept(self):
        lock = self.idx_lock()
        r = self.run_sync()
        self.assertEqual(r, "busy")
        self.assertEqual(self.commits(), [])
        self.assertTrue(os.path.exists(lock),
                        "진행 중인 commit 의 index.lock 을 sync 가 제거했다")

    # S8. index.lock 이 오래됐어도 commit-in-progress 표식이 신선하면 두 파일 다 둔다
    #     — 사람의 commit 이 pre-commit 훅 안에서 오래 도는 중일 수 있다
    def test_s8_fresh_marker_protects_old_lock(self):
        lock = self.idx_lock(age_sec=self.m.SYNC_COMMIT_BUSY_STALE_SEC + 60)
        self.mark()
        r = self.run_sync()
        self.assertEqual(r, "busy")
        self.assertTrue(os.path.exists(lock),
                        "진행 중인 commit 표식이 있는데 index.lock 을 제거했다")

    # S9. 제거한 사실이 state/sync.log 에 남는다 — 조용히 지우지 않는다
    def test_s9_removal_is_logged(self):
        self.idx_lock(age_sec=self.m.SYNC_COMMIT_BUSY_STALE_SEC + 60)
        self.run_sync()
        log = os.path.join(self.root, "state", "sync.log")
        self.assertTrue(os.path.exists(log), "sync.log 가 없다")
        with open(log, encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("index.lock", txt, "제거 사실이 기록에 없다")


    # S10. 받기(poll)도 같은 잠금에 막힌다 — 5분 넘은 index.lock 은 pull 전에 제거한다
    def test_s10_poll_clears_stale_index_lock(self):
        lock = self.idx_lock(age_sec=self.m.SYNC_COMMIT_BUSY_STALE_SEC + 60)
        seen = []

        def fake_pull(argv, timeout=8):
            seen.append(os.path.exists(lock))
            return CP(out="Already up to date.\n")
        with mock.patch.object(self.m, "_sync_git",
                               lambda *a, timeout=6: CP(out="abc\n")), \
                mock.patch.object(self.m, "sync_mode", lambda: "remote"), \
                mock.patch.object(self.m, "git_run", fake_pull):
            self.m._sync_poll_once()
        self.assertEqual(seen, [False],
                         "pull 을 걸 때까지 5분 넘은 index.lock 이 남아 있었다")


class CommitMarkHooks(unittest.TestCase):
    """S5. 훅이 표식을 만들고 지운다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9cmark-")
        self.g = _load("s9guard_cmark", GUARD)
        self.g.ROOT = self.root
        self.mark = os.path.join(self.root, "state", "commit-in-progress")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _main(self, gates):
        with mock.patch.object(self.g, "_pre_commit_gates", gates):
            try:
                self.g.main()
            except SystemExit as e:
                return e.code
        return 0

    def test_s5a_guard_makes_mark_and_keeps_it_when_gates_pass(self):
        seen = {}

        def gates():
            seen["during"] = os.path.exists(self.mark)
        self.assertEqual(self._main(gates), 0)
        self.assertTrue(seen["during"], "검사가 도는 동안 표식이 없다")
        self.assertTrue(os.path.exists(self.mark), "통과한 커밋의 표식은 post-commit 이 지운다 — 여기서 지우면 안 된다")

    def test_s5b_guard_removes_mark_when_gates_reject(self):
        def gates():
            raise SystemExit(1)
        self.assertEqual(self._main(gates), 1)
        self.assertFalse(os.path.exists(self.mark), "거부된 커밋은 post-commit 이 없다 — 가드가 스스로 지워야 한다")

    def test_s5c_guard_removes_mark_when_it_crashes(self):
        def gates():
            raise RuntimeError("boom")
        with mock.patch.object(self.g, "_pre_commit_gates", gates):
            with self.assertRaises(RuntimeError):
                self.g.main()
        self.assertFalse(os.path.exists(self.mark))

    def test_s5d_post_commit_template_clears_mark_before_commit_note(self):
        src = open(INSTALL, encoding="utf-8").read()
        i_rm = src.index('rm -f "$MAIN/state/commit-in-progress"')
        i_note = src.index("commit-note ", i_rm)
        self.assertLess(i_rm, i_note, "표식은 commit-note 의 sync 가 돌기 전에 지워야 한다")


if __name__ == "__main__":
    unittest.main()


class SyncCommitsAreNotWork(unittest.TestCase):
    """sync 의 문서 commit 은 commit-note 의 대상이 아니다 (REQ-20260906-082) — 노트가 다시 문서
    변경이 되어 sync 가 또 commit 하는 회전을 끊는다(실제 발생 2026-09-06: 006 에 commit 노트 30건)."""
    def test_sync_subjects_are_skipped(self):
        import importlib.machinery, importlib.util, os
        S9 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "s9")
        spec = importlib.util.spec_from_loader("s9_sync_subj", importlib.machinery.SourceFileLoader("s9_sync_subj", S9))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        self.assertTrue(m.sync_commit_subject("s9 sync: lease REQ-20260903-006-62x6"))
        self.assertTrue(m.sync_commit_subject("  s9 sync: note REQ-20260906-004-2n7g"))
        self.assertFalse(m.sync_commit_subject("serve --stop 은 판을 가리지 않는다 (REQ-20260906-077-62x6)"))
        self.assertFalse(m.sync_commit_subject(""))

