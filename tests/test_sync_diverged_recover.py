"""갈래가 갈린 저장소를 폴이 스스로 다시 붙인다 (REQ-20260910-034).

실제 발생 2026-09-06 11:35 ~ 09-10 11:24: 한 머신의 pull 이 한 번 실패한 뒤
나흘 동안 한 번도 다시 시도하지 않았다. 폴은 `pull --ff-only` 뿐이라 로컬
commit 이 앞서 갈래가 갈리면 그 갈래를 영영 못 넘고, 넘는 유일한 길(전송 경로:
commit→pull --rebase→push)은 state/.sync-queue 가 있을 때만 돌기 때문이다.

실행: python3 tests/ sync_diverged_recover
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


class DivergedRecover(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_SYNC")}
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        os.environ.pop("S9_SYNC", None)
        self.tmp = tempfile.mkdtemp(prefix="s9reattach-")
        self.bare = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", self.bare)
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "vault"))
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        os.environ["S9_ROOT"] = self.root
        name = "s9reattach_" + os.path.basename(self.tmp)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.sync_set_mode("remote")
        with open(os.path.join(self.root, "vault", "첫.md"), "w") as f:
            f.write("첫\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "첫")
        git(self.root, "remote", "add", "origin", self.bare)
        git(self.root, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ 도구
    def _other_pushes(self, msg="남의 문서"):
        """다른 머신이 origin 에 한 건 올린다."""
        other = os.path.join(self.tmp, "other")
        if not os.path.isdir(other):
            git(self.tmp, "clone", "-q", self.bare, other)
            git(other, "config", "user.email", "o@example.com")
            git(other, "config", "user.name", "o")
        with open(os.path.join(other, "vault", f"{msg}.md"), "w") as f:
            f.write(msg + "\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", msg)
        git(other, "push", "-q", "origin", "main")

    def _i_commit_locally(self, msg="내 문서"):
        """이 머신이 밀지 못한 채 가진 로컬 commit 한 건."""
        with open(os.path.join(self.root, "vault", f"{msg}.md"), "w") as f:
            f.write(msg + "\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)

    def _log(self, cwd):
        return git(cwd, "log", "--format=%s", "-20").stdout

    # ------------------------------------------------------------ N1
    def test_n1_diverged_poll_reattaches(self):
        """갈래가 갈리면 폴이 전송 경로를 불러 rebase→push 로 다시 붙는다."""
        m = self.m
        self._other_pushes("남의 문서")
        self._i_commit_locally("내 문서")
        # 이 상태에서 ff 는 불가능하다 — 종전 코드는 여기서 멈춘 채 나흘을 보냈다
        self.assertNotEqual(git(self.root, "pull", "--ff-only").returncode, 0)

        calls = []
        real = m.sync_run
        m.sync_run = lambda reason="", transport=True: (
            calls.append(reason) or real(reason, transport))
        try:
            kind = m._sync_poll_once()
        finally:
            m.sync_run = real

        self.assertEqual(calls, ["poll-reattach"], "갈래는 전송 경로가 푼다")
        self.assertEqual(kind, "ok", "다시 붙었으면 폴의 결과는 받음이다")
        # 실측 둘: 남의 commit 이 내려왔고, 내 commit 이 origin 에 섰다
        self.assertIn("남의 문서", self._log(self.root))
        self.assertIn("내 문서", self._log(self.bare))
        # 붙었으니 미룸의 표는 남지 않는다
        self.assertEqual(m._sync_reattach_state(), {})

    # ------------------------------------------------------------ N2
    def test_n2_interval_doubles_and_caps(self):
        """실패가 이어지면 간격이 배로 늘고 30분에서 멈춘다."""
        m = self.m
        self.assertEqual(m._sync_reattach_wait(0), 0.0, "첫 갈래는 미루지 않는다")
        self.assertEqual(m._sync_reattach_wait(1), 60.0)
        self.assertEqual(m._sync_reattach_wait(2), 120.0)
        self.assertEqual(m._sync_reattach_wait(3), 240.0)
        self.assertEqual(m._sync_reattach_wait(20), float(m.SYNC_REATTACH_MAX_SEC))

        p = os.path.join(self.root, "state", "reattach-n2.json")
        self.assertTrue(m._sync_reattach_due(now=1000.0, path=p), "첫 시도는 곧바로")
        self.assertFalse(m._sync_reattach_due(now=1030.0, path=p), "60s 안에는 차례가 아니다")
        self.assertTrue(m._sync_reattach_due(now=1060.0, path=p))
        self.assertFalse(m._sync_reattach_due(now=1060.0 + 119, path=p))
        self.assertTrue(m._sync_reattach_due(now=1060.0 + 120, path=p))
        self.assertEqual(m._sync_reattach_state(p)["tries"], 3)

    # ------------------------------------------------------------ N3
    def test_n3_never_gives_up(self):
        """상한에 닿아도 차례는 계속 온다 — 포기하는 자리가 없다."""
        m = self.m
        p = os.path.join(self.root, "state", "reattach-n3.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump({"tries": 500, "last": 1000.0}, f)
        self.assertFalse(m._sync_reattach_due(now=1000.0 + m.SYNC_REATTACH_MAX_SEC - 1, path=p))
        self.assertTrue(m._sync_reattach_due(now=1000.0 + m.SYNC_REATTACH_MAX_SEC, path=p))
        # 나흘 뒤에도 — 실제로 한 컴퓨터가 그만큼 멈춰 있었다 (REQ-20260910-034)
        with open(p, "w") as f:
            json.dump({"tries": 500, "last": 1000.0}, f)
        self.assertTrue(m._sync_reattach_due(now=1000.0 + 4 * 86400, path=p))

    # ------------------------------------------------------------ N4
    def test_n4_success_clears_the_delay(self):
        """받는 데 성공하면 미룸이 풀린다 — 다음 갈래는 다시 곧바로 시도한다."""
        m = self.m
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        with open(m._SYNC_REATTACH, "w") as f:
            json.dump({"tries": 5, "last": 1.0}, f)
        self._other_pushes("혼자 온 문서")          # 갈래 없이 origin 만 앞선다
        self.assertEqual(m._sync_poll_once(), "ok")
        self.assertEqual(m._sync_reattach_state(), {}, "붙었으면 표는 지워진다")

    # ------------------------------------------------------------ N5
    def test_n5_other_kinds_are_left_alone(self):
        """net·코드가 섞인 dirty 에서는 전송 경로를 부르지 않는다."""
        m = self.m
        for stderr, want in (
            ("fatal: unable to access 'https://x': Could not resolve host\n", "net"),
            ("error: Your local changes to the following files would be "
             "overwritten by merge:\n\tbin/s9.py\n\tstate/x\n", "dirty"),
        ):
            calls = []
            real_pull, real_run = m.git_run, m.sync_run
            m.git_run = lambda argv, timeout=25: types.SimpleNamespace(
                returncode=1, stdout="", stderr=stderr)
            m.sync_run = lambda reason="", transport=True: calls.append(reason)
            try:
                kind = m._sync_poll_once()
            finally:
                m.git_run, m.sync_run = real_pull, real_run
            self.assertEqual(kind, want)
            self.assertEqual(calls, [], f"{want} 에서는 다시 붙이기를 하지 않는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
