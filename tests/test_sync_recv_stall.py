"""받는 쪽이 멈춘 것을 가릴 수 있게 (REQ-20260908-013-62x6).

실제 발생 2026-09-08: 맥미니가 2시간 16분 동안 origin 의 커밋 46건을 한 건도
받지 않았다. `state/.sync-poll.ts` 는 매분 갱신되고 있었으니 폴은 돌았는데,
`sync_poll` 이 `sync.jsonl` 에 아무것도 남기지 않아 **매번 조용히 건너뛴 것인지
스레드가 죽은 것인지 가를 근거가 없었다**. 그리고 오래 못 받은 사실은 화면
어디에도 서지 않았다(종전 경고는 **보내는 쪽** 밀림만 쟀다).

여기서 재는 것 둘: ① 폴의 결과가 남는가 — 매번은 아니고, 바뀌는 순간과 5분에
한 번 ② 못 받은 커밋이 있는 채로 오래 못 받으면 sync_status 가 그것을 말하는가.

실행: python3 tests/ sync_recv_stall
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9_SRC = os.path.join(HERE, "..", "bin", "s9.py")


def sh(*argv, cwd=None, check=False):
    r = subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True,
                       timeout=60, stdin=subprocess.DEVNULL)
    if check and r.returncode != 0:
        raise AssertionError("%s 실패: %s%s" % (" ".join(argv), r.stdout, r.stderr))
    return r


class SyncRecvStall(unittest.TestCase):
    """bare origin + 클론 A(S9_ROOT) + 클론 B. 모듈은 한 번만 싣는다."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9recv-")
        cls.bare = os.path.join(cls.base, "origin.git")
        sh("git", "init", "-q", "--bare", "-b", "main", cls.bare, check=True)
        cls.a = os.path.join(cls.base, "a")
        cls.b = os.path.join(cls.base, "b")
        for d in (cls.a, cls.b):
            os.makedirs(d)
            for c in (["git", "init", "-q", "-b", "main"],
                      ["git", "config", "user.name", "t"],
                      ["git", "config", "user.email", "t@t"],
                      ["git", "remote", "add", "origin", cls.bare]):
                sh(*c, cwd=d, check=True)
        os.makedirs(os.path.join(cls.a, "state"), exist_ok=True)
        with open(os.path.join(cls.a, ".s9-sync"), "w") as f:
            f.write("remote\n")
        with open(os.path.join(cls.a, "seed.txt"), "w") as f:
            f.write("seed\n")
        sh("git", "add", "-A", cwd=cls.a, check=True)
        sh("git", "commit", "-q", "-m", "seed", cwd=cls.a, check=True)
        sh("git", "push", "-q", "-u", "origin", "main", cwd=cls.a, check=True)
        sh("git", "pull", "-q", "origin", "main", cwd=cls.b, check=True)
        sh("git", "branch", "-q", "--set-upstream-to=origin/main", "main",
           cwd=cls.b, check=True)
        os.environ["S9_ROOT"] = cls.a
        os.environ.setdefault("S9_USER", "tester")
        spec = importlib.util.spec_from_loader(
            "s9_recv", importlib.machinery.SourceFileLoader("s9_recv", S9_SRC))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.base, ignore_errors=True)

    def setUp(self):
        for n in ("sync.jsonl", ".sync-poll.json", ".sync-pull.ts",
                  ".sync-stall-seen", ".sync-queue", ".sync-fail.ts"):
            try:
                os.remove(os.path.join(self.a, "state", n))
            except OSError:
                pass

    # ---- 도우미 ---------------------------------------------------------
    def events(self):
        p = os.path.join(self.a, "state", "sync.jsonl")
        try:
            with open(p, encoding="utf-8") as f:
                return [json.loads(ln) for ln in f if ln.strip()]
        except OSError:
            return []

    def polls(self):
        return [e for e in self.events() if e.get("stage") == "poll"]

    def set_received(self, ago):
        with open(os.path.join(self.a, "state", ".sync-pull.ts"), "w") as f:
            f.write(str(time.time() - ago))

    def origin_ahead(self, name):
        """B 가 origin 에 한 건 밀고, A 는 fetch 만 한다 — 못 받은 커밋이 생긴다."""
        with open(os.path.join(self.b, name), "w") as f:
            f.write(name)
        sh("git", "add", "-A", cwd=self.b, check=True)
        sh("git", "commit", "-q", "-m", name, cwd=self.b, check=True)
        sh("git", "push", "-q", cwd=self.b, check=True)
        sh("git", "fetch", "-q", cwd=self.a, check=True)

    # ---- S1 -------------------------------------------------------------
    def test_s1_ok_is_recorded(self):
        """폴이 당겼으면 그 한 번이 남는다."""
        rec = self.m._sync_poll_record("ok", now=1000.0, ms=42)
        self.assertIsNotNone(rec)
        got = self.polls()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["result"], "ok")
        self.assertEqual(got[0]["rc"], 0)
        self.assertEqual(got[0]["count"], 1)
        self.assertEqual(got[0]["ms"], 42)

    # ---- S2 -------------------------------------------------------------
    def test_s2_same_reason_is_grouped(self):
        """같은 사유가 이어지면 5분에 한 줄 — 몇 번째인지를 함께 적는다."""
        t = 1000.0
        for i in range(30):                      # 10초 주기로 5분
            self.m._sync_poll_record("net", now=t + i * 10)
        got = self.polls()
        self.assertEqual(len(got), 1, got)       # 첫 줄만 (5분이 아직 안 찼다)
        self.m._sync_poll_record("net", now=t + 301)
        got = self.polls()
        self.assertEqual(len(got), 2, got)
        self.assertEqual(got[1]["count"], 31)    # 연속 31번째
        self.assertEqual(got[1]["kind"], "net")
        self.assertEqual(got[0]["since"], got[1]["since"])   # 같은 멈춤

    # ---- S3 -------------------------------------------------------------
    def test_s3_change_is_recorded_none_is_not(self):
        """바뀌는 순간은 언제나 남고, 조용한 "none" 이 이어지는 동안은 늘지 않는다."""
        self.m._sync_poll_record("net", now=1000.0)
        self.m._sync_poll_record("none", now=1010.0)         # 전이 — 남는다
        self.assertEqual([p["result"] for p in self.polls()], ["net", "none"])
        for i in range(60):                                  # 10분 내내 none
            self.m._sync_poll_record("none", now=1020.0 + i * 10)
        self.assertEqual(len(self.polls()), 2)
        self.m._sync_poll_record("net", now=1700.0)          # 다시 전이
        self.assertEqual([p["result"] for p in self.polls()],
                         ["net", "none", "net"])
        self.assertEqual(self.polls()[2]["count"], 1)        # 새로 센다

    # ---- S4 -------------------------------------------------------------
    def test_s4_behind_and_old_receive_is_stale(self):
        """맥 사고 재현: 못 받은 커밋이 있는 채 2시간 16분이면 stale 이다."""
        self.origin_ahead("m1.txt")
        self.set_received(2 * 3600 + 16 * 60)
        st = self.m.sync_status()
        self.assertEqual(st["behind"], 1)
        self.assertGreater(st["received_sec"], 8000)
        self.assertEqual(st["recv_level"], "stale")
        self.assertEqual(st["level"], "stale")               # 화면 단계가 오른다
        self.assertIn("못 받은 커밋 1건", self.m.sync_status_line(st))
        sh("git", "merge", "-q", "--ff-only", "origin/main", cwd=self.a, check=True)

    # ---- S5 -------------------------------------------------------------
    def test_s5_quiet_is_not_stalled(self):
        """받을 것이 없으면 오래 못 받아도 멈춤이 아니다."""
        self.set_received(4 * 3600)
        st = self.m.sync_status()
        self.assertEqual(st["behind"], 0)
        self.assertEqual(st["recv_kind"], "")
        self.assertEqual(st["recv_level"], "")
        self.assertEqual(st["level"], "")

    # ---- S6 -------------------------------------------------------------
    def test_s6_failing_poll_stands_even_without_behind(self):
        """폴이 계속 실패하면 origin 이 안 보여 behind 가 0 이어도 멈춤이다."""
        self.set_received(3600)
        self.m._sync_poll_record("net", now=time.time())
        st = self.m.sync_status()
        self.assertEqual(st["behind"], 0)
        self.assertEqual(st["recv_kind"], "net")
        self.assertEqual(st["recv_level"], "stale")
        self.assertIn("닿지 못합니다", self.m.sync_status_line(st))
        self.assertIn("네트워크", self.m.sync_status_hint(st))

    # ---- S7 -------------------------------------------------------------
    def test_s7_same_surface_and_old_fixed_points(self):
        """같은 자리로 나간다 — 훅 주입은 한 번, 보내는 쪽 문구는 그대로."""
        now = 1_000_000.0
        self.assertEqual(
            self.m.sync_status_line(
                {"last_sent": now - 12, "last_received": now - 8, "pending": 3},
                now),
            "마지막 보냄 12초 전 · 받음 8초 전 · 대기 3건")
        self.origin_ahead("m2.txt")
        self.set_received(2 * 3600)
        first = self.m.sync_stall_once()
        self.assertIn("못 받은 커밋", first)
        self.assertEqual(self.m.sync_stall_once(), "")       # 같은 멈춤은 한 번
        self.set_received(30)                                # 한 번 받았다
        self.assertEqual(self.m.sync_stall_once(), "")       # 멈춤이 풀렸다
        self.set_received(3 * 3600)                          # 다시 멈췄다
        self.assertNotEqual(self.m.sync_stall_once(), "")
        sh("git", "merge", "-q", "--ff-only", "origin/main", cwd=self.a, check=True)

    # ---- S8 -------------------------------------------------------------
    def test_s8_record_failure_does_not_change_poll(self):
        """기록이 실패해도 폴의 반환값은 그대로다."""
        def boom(*a, **k):
            raise RuntimeError("기록 실패")
        with mock.patch.object(self.m, "_sync_poll_once", lambda t=8: "diverged"), \
                mock.patch.object(self.m, "_sync_poll_record", boom):
            self.assertEqual(self.m.sync_poll(), "diverged")


if __name__ == "__main__":
    unittest.main()
