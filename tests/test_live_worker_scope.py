"""일 안 하는 요청이 초록으로 보인다 (REQ-20260827-027-62x6).

무인 워커는 **죽은 세션의 id 를 물려받아** 뜬다 (`--resume` — 컨텍스트 승계가
목적이다). 그런데 그 세션의 바인딩에는 죽기 전 리드가 등록해 둔 REQ 들이 통째로
남아 있다. 워커가 019 하나를 재작업하러 되살아나자, 그 바인딩의 활동 **하나**가
019 와 022 를 **함께** 초록으로 점멸시켰다. 022 에는 아무도 붙어 있지 않았다.

병행 REQ 를 다 초록으로 켜는 것 자체는 의도된 설계다 (REQ-20260823-079): 리드는
실제로 여러 건을 오간다. 하지만 **워커는 정의상 한 건짜리다** — 스폰될 때 대상
REQ 하나를 받고 그 한 턴만 돌고 죽는다. 그러니 워커 바인딩의 활동은 그 한 건에만
직접 증거여야 한다.

누가 그 한 건인지는 추측하지 않는다. 스폰 기록(`state/auto_resume/<REQ>.json`)에
그 워커의 pid 가 적혀 있고, 바인딩의 attach_pid 와 맞춰 보면 정확히 하나로 좁혀진다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ live_worker_scope
"""
import json
import os
import subprocess
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import free_port, wait_server  # noqa: E402


class LiveWorkerScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9wscope-")
        cls.base = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox"}
        cls.base.pop("S9_SESSION", None)
        cls.cli(None, "init")
        cls.cli(None, "user", "add", "alice")

        # 리드 세션 wwww1111 이 X·Y 를 등록해 두고 죽었다
        cls.X = cls.mk("wwww1111", "worker-target")
        cls.cli("wwww1111", "status", cls.X, "in-progress", "--note", "t")
        cls.Y = cls.mk("wwww1111", "left-behind")
        cls.cli("wwww1111", "status", cls.Y, "in-progress", "--note", "t")
        # 보통 세션 nnnn2222 — 병행 둘 다 직접이어야 한다 (기존 설계, B1)
        cls.P = cls.mk("nnnn2222", "normal-a")
        cls.cli("nnnn2222", "status", cls.P, "in-progress", "--note", "t")
        cls.Q = cls.mk("nnnn2222", "normal-b")
        cls.cli("nnnn2222", "status", cls.Q, "in-progress", "--note", "t")
        # 워커인데 어느 스폰 기록과도 pid 가 안 맞는 세션 vvvv3333 (B2)
        cls.Z1 = cls.mk("vvvv3333", "unknown-a")
        cls.cli("vvvv3333", "status", cls.Z1, "in-progress", "--note", "t")
        cls.Z2 = cls.mk("vvvv3333", "unknown-b")
        cls.cli("vvvv3333", "status", cls.Z2, "in-progress", "--note", "t")

        # 워커가 wwww1111 을 resume 해 X 를 재작업 중 — 이 프로세스가 그 워커다
        cls.wpid = os.getpid()
        cls.bind("wwww1111", worker="1", attach_pid=str(cls.wpid))
        cls.bind("nnnn2222", attach_pid=str(cls.wpid))   # 워커 아님
        # 워커이긴 한데 스폰 기록에 이 pid 가 없다 — 좁힐 근거가 없는 경우
        cls.bind("vvvv3333", worker="1", attach_pid=str(cls.wpid + 100000))
        ar = os.path.join(cls.tmp, "state", "auto_resume")
        os.makedirs(ar, exist_ok=True)
        with open(os.path.join(ar, cls.X + ".json"), "w") as f:
            json.dump({"last": time.time() - 30, "count": 1,
                       "pid": cls.wpid}, f)

        # 활동 신호: 두 세션 모두 방금 갱신 (스트림 미러)
        streams = os.path.join(cls.tmp, "streams")
        os.makedirs(streams, exist_ok=True)
        for sid in ("wwww1111", "nnnn2222", "vvvv3333"):
            with open(os.path.join(streams, sid + ".jsonl"), "w") as f:
                f.write(json.dumps({"role": "assistant", "text": "작업"}) + "\n")

        cls.rows = cls.catalog()

    @classmethod
    def cli(cls, sess, *argv):
        env = dict(cls.base)
        if sess:
            env["S9_SESSION"] = sess
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, timeout=20)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    @classmethod
    def mk(cls, sess, title):
        return cls.cli(sess, "new", "request", "--title", title, "--summary",
                       "t", "--goal", "t", "--size", "S", "--user", "alice",
                       "--body", "x").split()[0]

    @classmethod
    def bind(cls, sid, **kw):
        p = os.path.join(cls.tmp, "state", "sessions", f"testbox__{sid}.json")
        with open(p, encoding="utf-8") as f:
            b = json.load(f)
        b.update(kw)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f)

    @classmethod
    def catalog(cls):
        port = free_port()
        srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(port)],
            env=cls.base, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_server(port)
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/catalog", timeout=5) as r:
                return {x["id"]: x for x in json.loads(r.read().decode())}
        finally:
            srv.terminate()
            srv.wait(timeout=5)

    # N1. 워커가 재작업 중인 그 한 건만 직접 증거(초록)
    def test_live_worker_scope(self):
        """LiveWorkerScope 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_worker_target_is_live"):
                r = self.rows[self.X]
                self.assertTrue(r["live"], r)
                self.assertEqual(r.get("live_kind"), "direct", r)

            # N2. 같은 바인딩에 남아 있던 다른 건은 초록이 아니다 — 간접까지만
        with self.subTest("n2_left_behind_is_not_live"):
                r = self.rows[self.Y]
                self.assertFalse(r["live"], r)
                self.assertEqual(r.get("live_kind"), "session", r)

            # B1. 워커가 아닌 보통 세션은 예전 그대로 — 등록한 병행 REQ 전부 직접
        with self.subTest("b1_normal_session_unchanged"):
                for rid in (self.P, self.Q):
                    self.assertTrue(self.rows[rid]["live"], self.rows[rid])

            # B2. 워커인데 pid 를 어느 스폰 기록과도 못 맞추면 좁히지 않는다 —
            #     모르는 것으로 표시를 지우지 않는다
        with self.subTest("b2_unknown_worker_pid_not_narrowed"):
            for rid in (self.Z1, self.Z2):
                self.assertTrue(self.rows[rid]["live"], self.rows[rid])

if __name__ == "__main__":
    unittest.main()
