"""죽은 pid 의 commit 표식은 commit 이 아니다 (REQ-20260915-005-62x6).

실제 사고 2026-09-15 11:16. `s9 commit` 의 pre-commit(s9-guard)이 검사를 통과하며
state/commit-in-progress 에 「pid 4120702 …」를 남겼고, 그 뒤 git 이 져서(post-commit
이 돌지 않아) 표식이 그대로 남았다. 다음 `s9 commit` 은 그 표식을 「다른 commit 이
진행 중」으로 읽어 90초를 기다린 뒤 exit 3 이었고, sync 도 그 5분 동안 회차를 세웠다
— 그 pid 는 이미 없었는데.

계약: 표식의 pid 가 죽었으면 `_sync_commit_busy` 는 busy 가 아니고, 그 표식을 지우며
sync.log 에 한 줄 남긴다. 산 pid·pid 없는 옛 형식·신선한 .git/index.lock 은 종전대로
busy 다.
실행: python3 tests/ commit_mark_dead
"""
import importlib.machinery
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


def dead_pid():
    """방금 끝나 거둔 프로세스의 pid — 지금은 없는 번호다."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class DeadMarkIsNotACommit(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9cmk-")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_USER"] = "hong"
        os.environ.pop("S9_SESSION", None)
        name = "s9cmk_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.mark = os.path.join(self.root, "state", "commit-in-progress")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def write_mark(self, text, age=0):
        with open(self.mark, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        if age:
            t = time.time() - age
            os.utime(self.mark, (t, t))

    def sync_log(self):
        try:
            with open(os.path.join(self.root, "state", "sync.log"), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    # 정상 — 죽은 pid 의 신선한 표식: busy 가 아니고, 지워지며, 한 줄 남는다
    def test_dead_pid_mark_is_cleared_and_logged(self):
        pid = dead_pid()
        self.write_mark(f"pid {pid} 2026-09-15T11:16:33")
        self.assertEqual(self.m._sync_commit_busy(), "", "죽은 pid 의 표식을 commit 으로 읽었다 — 그날 그 자리")
        self.assertFalse(os.path.exists(self.mark), "죽은 표식이 남아 있다 — 다음에 또 같은 판정을 한다")
        log = self.sync_log()
        self.assertIn(str(pid), log, "sync.log 에 어느 pid 의 표식을 지웠는지 없다")
        self.assertEqual(log.count("commit-in-progress 를 제거했다"), 1)
        # 두 번째 물음은 조용하다 — 표식이 없으니 적을 것도 없다
        self.assertEqual(self.m._sync_commit_busy(), "")
        self.assertEqual(self.sync_log().count("commit-in-progress 를 제거했다"), 1)

    # 정상 — 산 pid 의 표식은 종전대로 busy 다
    def test_live_pid_mark_is_busy(self):
        self.write_mark(f"pid {os.getpid()} 2026-09-15T11:16:33")
        self.assertEqual(self.m._sync_commit_busy(), "commit-in-progress")
        self.assertTrue(os.path.exists(self.mark), "산 commit 의 표식을 지웠다")

    # 경계 — pid 없는 옛 형식은 나이로만 판정한다 (5분 안이면 busy)
    def test_old_format_mark_is_judged_by_age_only(self):
        self.write_mark("2026-09-15T11:16:33")
        self.assertEqual(self.m._sync_commit_busy(), "commit-in-progress")
        self.assertTrue(os.path.exists(self.mark))

    # 경계 — 5분 넘은 표식은 종전대로 무시한다 (pid 가 살아 있어도)
    def test_stale_mark_is_ignored_as_before(self):
        self.write_mark(f"pid {os.getpid()} 2026-09-15T11:16:33",
                        age=self.m.SYNC_COMMIT_BUSY_STALE_SEC + 5)
        self.assertEqual(self.m._sync_commit_busy(), "")

    # 회귀 — 신선한 .git/index.lock 은 여전히 busy 다 (guard 가 끝나고 git 이 ref 를 쓰는 사이)
    def test_fresh_index_lock_is_still_busy(self):
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        with open(os.path.join(self.root, ".git", "index.lock"), "w") as f:
            f.write("")
        self.write_mark(f"pid {dead_pid()} 2026-09-15T11:16:33")
        self.assertEqual(self.m._sync_commit_busy(), "index.lock")

    # 실패 — s9 commit 의 창 잡기가 죽은 표식 앞에서 --wait 를 다 쓰지 않는다 (그날 90초 → exit 3)
    def test_take_sync_window_does_not_wait_for_a_dead_mark(self):
        self.write_mark(f"pid {dead_pid()} 2026-09-15T11:16:33")
        cm = self.m.commit_module()
        err = io.StringIO()
        t0 = time.time()
        lock = cm.take_sync_window(20.0, err)
        took = time.time() - t0
        self.assertTrue(lock, f"창을 못 잡았다: {err.getvalue()}")
        self.assertLess(took, 5.0, f"죽은 표식 앞에서 {took:.1f}초를 기다렸다")
        try:
            os.remove(lock)
        except OSError:
            pass

    # 뿌리 — 그날 commit 을 죽인 것: 받기 poll 의 pull --ff-only 가 진행 중인 commit 사이에
    #       HEAD 를 옮겼다. pull 은 sync 잠금 아래에서만 하고, 잠금이 잡혀 있으면 받지 않는다
    def test_poll_does_not_pull_while_the_sync_lock_is_held(self):
        m = self.m
        lock = os.path.join(self.root, "state", ".sync.lock")
        with open(lock, "w") as f:
            f.write("")                      # s9 commit 의 take_sync_window 가 쥔 잠금
        m.sync_mode = lambda: "remote"
        calls = []
        m.git_run = lambda argv, timeout=25: calls.append(list(argv))
        self.assertEqual(m._sync_poll_once(), "busy")
        self.assertEqual(calls, [], "commit 이 잠금을 쥐고 있는데 pull 했다 — 그날 HEAD 를 옮긴 자리")
        self.assertIn("잠금", m._SYNC_POLL_LAST["error"])
        self.assertTrue(os.path.exists(lock), "남의 잠금을 지웠다")

    # 뿌리 — pull 하는 동안은 잠금을 쥐고, 끝나면 놓는다 (commit 쪽이 기다릴 수 있게)
    def test_poll_holds_the_sync_lock_while_pulling(self):
        m = self.m
        lock = os.path.join(self.root, "state", ".sync.lock")
        m.sync_mode = lambda: "remote"
        seen = []
        done = types.SimpleNamespace(returncode=0, stdout="Already up to date.\n", stderr="")
        m._sync_git = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="abc\n", stderr="")
        m.git_run = lambda argv, timeout=25: (seen.append(os.path.exists(lock)) or done)
        m._sync_poll_once()
        self.assertEqual(seen, [True], "pull 하는 동안 잠금을 쥐지 않았다")
        self.assertFalse(os.path.exists(lock), "poll 이 끝났는데 잠금이 남았다")

    # 회귀 — 죽은 표식은 poll 을 막지 않는다 (sync_poll 이 표식을 지우고 받는다)
    def test_poll_proceeds_past_a_dead_mark(self):
        m = self.m
        self.write_mark(f"pid {dead_pid()} 2026-09-15T11:16:33")
        m.sync_mode = lambda: "remote"
        m._sync_poll_record = lambda *a, **k: None
        m.machine_recv_beat = lambda push=False: None
        calls = []
        done = types.SimpleNamespace(returncode=0, stdout="Already up to date.\n", stderr="")
        m._sync_git = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="abc\n", stderr="")
        m.git_run = lambda argv, timeout=25: (calls.append(list(argv)) or done)
        m.sync_poll()
        self.assertEqual(calls, [["pull", "--ff-only"]], "죽은 표식이 받기를 막았다")
        self.assertFalse(os.path.exists(self.mark))

    # 회귀 — 산 commit 의 표식은 종전대로 poll 을 세운다 (sync_poll 의 commit-busy 검사)
    def test_poll_skips_a_live_commit(self):
        m = self.m
        self.write_mark(f"pid {os.getpid()} 2026-09-15T11:16:33")
        m.sync_mode = lambda: "remote"
        calls = []
        m.git_run = lambda argv, timeout=25: calls.append(list(argv))
        self.assertEqual(m.sync_poll(), "none")
        self.assertEqual(calls, [])

if __name__ == "__main__":
    unittest.main()
