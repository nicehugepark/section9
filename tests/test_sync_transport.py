"""전송은 serve 가, 이벤트는 로컬 커밋만 (REQ-20260902-023).

문서 이벤트 10곳이 CLI 안에서 pull 8s·push 8s 를 동기로 물었고, 쓰지 않는 머신은
남의 변경을 영원히 못 받았다. remote 모드에서 serve 가 떠 있으면 이벤트는 커밋 +
큐만 남기고, serve 의 루프가 디바운스해 밀며 10초/60초마다 fast-forward 로 당긴다.

실행: python3 tests/ sync_transport
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def sh(*argv, cwd=None, env=None):
    return subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=60, stdin=subprocess.DEVNULL)


class CP:
    def __init__(self, rc=0, err="", out=""):
        self.returncode, self.stderr, self.stdout = rc, err, out


class TransportUnit(unittest.TestCase):
    """T1·T2·T3·T6 — 가짜 git 으로 경로만 본다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9tr-")
        os.makedirs(os.path.join(self.root, "state"))
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_tr", importlib.machinery.SourceFileLoader("s9_tr", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.calls = []

        def fake(*argv, timeout=6):
            self.calls.append(argv[0])
            if argv[0] == "diff":
                return CP(out="vault/x.md\n")
            return CP()
        self.fake = fake

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def net_calls(self):
        return [c for c in self.calls if c in ("pull", "push")]

    # T1. serve 가 살아 있으면 이벤트는 커밋 + 큐, 네트워크 0
    def test_t1_event_commits_and_queues_when_serve_owns_transport(self):
        m = self.m
        with mock.patch.object(m, "_sync_git", self.fake), \
                mock.patch.object(m, "sync_mode", lambda: "remote"), \
                mock.patch.object(m, "sync_enabled", lambda: True), \
                mock.patch.object(m, "_serve_owner_alive", lambda: True):
            r = m.maybe_sync("new X")
        self.assertEqual(r, "queued")
        self.assertIn("commit", self.calls)
        self.assertEqual(self.net_calls(), [])
        self.assertTrue(os.path.exists(m._SYNC_QUEUE))

    # T2. serve 가 없으면 종전대로 그 자리에서 전송
    def test_t2_fallback_without_serve(self):
        m = self.m
        with mock.patch.object(m, "_sync_git", self.fake), \
                mock.patch.object(m, "sync_mode", lambda: "remote"), \
                mock.patch.object(m, "sync_enabled", lambda: True), \
                mock.patch.object(m, "_serve_owner_alive", lambda: False):
            r = m.maybe_sync("new X")
        self.assertEqual(r, "ok")
        self.assertEqual(self.net_calls(), ["pull", "push"])
        self.assertFalse(os.path.exists(m._SYNC_QUEUE))

    # T3. 전송 루프 — 디바운스 뒤 한 번 밀고 큐를 지운다
    def test_t3_transport_tick_debounces_and_pushes(self):
        m = self.m
        with open(m._SYNC_QUEUE, "w"):
            pass
        now = time.time()
        with mock.patch.object(m, "_sync_git", self.fake), \
                mock.patch.object(m, "sync_mode", lambda: "remote"), \
                mock.patch.object(m, "sync_poll_due", lambda now=None, active=None: False):
            self.assertEqual(m.sync_transport_tick(now=now), [])        # 창 안 — 아직
            did = m.sync_transport_tick(now=now + m.SYNC_DEBOUNCE_SEC + 0.1)
        self.assertEqual(did, ["push:ok"])
        self.assertFalse(os.path.exists(m._SYNC_QUEUE))
        self.assertEqual(self.net_calls(), ["pull", "push"])

    # T6. 폴링 주기 — 라이브 세션 유무로 10/60초
    def test_t6_poll_interval(self):
        m = self.m
        now = time.time()
        with open(m._SYNC_POLL_TS, "w") as f:
            f.write(str(now - 30))
        self.assertTrue(m.sync_poll_due(now=now, active=True))
        self.assertFalse(m.sync_poll_due(now=now, active=False))
        self.assertTrue(m.sync_poll_due(now=now + 31, active=False))


class TransportRepo(unittest.TestCase):
    """T4·T5 — 진짜 git: bare origin + 클론 둘."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9trrepo-")
        cls.bare = os.path.join(cls.base, "origin.git")
        sh("git", "init", "-q", "--bare", "-b", "main", cls.bare)
        cls.a = os.path.join(cls.base, "a")
        cls.b = os.path.join(cls.base, "b")
        for d in (cls.a, cls.b):
            os.makedirs(d)
            for c in (["git", "init", "-q", "-b", "main"],
                      ["git", "config", "user.name", "t"],
                      ["git", "config", "user.email", "t@t"],
                      ["git", "remote", "add", "origin", cls.bare]):
                sh(*c, cwd=d)
        with open(os.path.join(cls.a, "seed.txt"), "w") as f:
            f.write("seed\n")
        sh("git", "add", "-A", cwd=cls.a)
        sh("git", "commit", "-q", "-m", "seed", cwd=cls.a)
        sh("git", "push", "-q", "-u", "origin", "main", cwd=cls.a)
        sh("git", "pull", "-q", "origin", "main", cwd=cls.b)
        sh("git", "branch", "-q", "--set-upstream-to=origin/main", "main", cwd=cls.b)
        os.makedirs(os.path.join(cls.a, "state"), exist_ok=True)
        with open(os.path.join(cls.a, ".s9-sync"), "w") as f:
            f.write("remote\n")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.base, ignore_errors=True)

    def load_a(self):
        os.environ["S9_ROOT"] = self.a
        spec = importlib.util.spec_from_loader(
            "s9_tr_a", importlib.machinery.SourceFileLoader("s9_tr_a", S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    # T4. B 의 push 를 A 의 폴링이 당긴다; A 가 앞서 있으면 건너뛴다
    def test_t4_poll_fast_forwards_and_skips_when_diverged(self):
        m = self.load_a()
        with open(os.path.join(self.b, "from_b.txt"), "w") as f:
            f.write("b\n")
        sh("git", "add", "-A", cwd=self.b)
        sh("git", "commit", "-q", "-m", "from b", cwd=self.b)
        sh("git", "push", "-q", cwd=self.b)
        with mock.patch.object(m, "rebuild_index", lambda quiet=True: None):
            self.assertEqual(m.sync_poll(), "ok")
            self.assertTrue(os.path.exists(os.path.join(self.a, "from_b.txt")))
            self.assertEqual(m.sync_poll(), "none")
            # 갈림 — A 로컬 커밋 + B 의 새 push
            with open(os.path.join(self.a, "local.txt"), "w") as f:
                f.write("a\n")
            sh("git", "add", "-A", cwd=self.a)
            sh("git", "commit", "-q", "-m", "local a", cwd=self.a)
            with open(os.path.join(self.b, "from_b2.txt"), "w") as f:
                f.write("b2\n")
            sh("git", "add", "-A", cwd=self.b)
            sh("git", "commit", "-q", "-m", "from b2", cwd=self.b)
            sh("git", "push", "-q", cwd=self.b)
            self.assertEqual(m.sync_poll(), "diverged")
            self.assertFalse(os.path.exists(os.path.join(self.a, "from_b2.txt")))

    # T5. 손잡이와 폴링이 같은 명령
    def test_t5_handle_and_poll_share_the_command(self):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertGreaterEqual(src.count('git_run(["pull", "--ff-only"]'), 2)
        self.assertIn("sync_transport_tick()", src)      # serve 루프가 부른다


if __name__ == "__main__":
    unittest.main()
