"""폴 한 바퀴가 `/proc` 을 한 번만 훑는다 (REQ-20260901-024-62x6).

REQ-20260901-020(연결 누수)이 앞을 치우자 다음 병목이 드러났다. 실측 스택
100개 중 32개가 `_proc_table_read` 안에 있었고 16개가 그 뒤에 줄 서 있었다.

뿌리는 `proc_table` 이 `/proc` 갈래를 "싸다"는 전제로 캐시하지 않은 것이다.
싸지 않았다 — 착수 전 실측(2026-09-02, 바인딩 156개 · 프로세스 66개):

    session_rows()        /proc 전수 훑기 228회 · 1.538s
    catalog_with_live()                    43회 · 0.074s
    /api/chat/target                       76회 · 0.046s   ← 폴 게이트 밖
    /api/sessions  동시 8건 0.22s → 동시 32건 1.27s (동시성이 곱한다)

고침은 TTL 캐시가 아니다. TTL 은 판정을 낡게 만들고, 그 낡음이
`test_dashboard_chat` C9/C18(«tail 을 죽이면 0.2초 안에 live 가 꺼진다»)을
깬다. 낡음을 사지 않고 중복만 지우는 두 겹을 쓴다:

  ① **요청 스코프** (`proc_scope`, `Handler.handle_one_request`) — 한 요청이
     도는 동안만 표를 나눠 쓴다. 표는 언제나 그 요청이 시작된 뒤에 뜬 것이다.
  ② **단일비행** (`_proc_table_shared`) — 동시에 겹친 훑기를 하나로 접는다.
     대기자가 받는 표는 자기가 도착하기 직전에 뜬 것(낡음 상한 = 훑기 1회).

계기는 `/api/serveinfo` 의 `proc` 이다 — 재발을 사람이 스택을 떠서 세지 않고
`reads`·`max_inflight` 로 잡는다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ proc_scan
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

from portpool import free_port, wait_server  # noqa: E402

BINDINGS = 40          # 폴 한 바퀴가 훑던 횟수의 곱셈 인자 (실환경은 156개)


def s9mod(root, tag):
    os.environ["S9_ROOT"] = root
    name = "s9proc_" + tag
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ProcScope(unittest.TestCase):
    """스코프·단일비행 자체의 계약 — 서버를 띄우지 않고 모듈로 직접 잰다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9procs-")
        cls.m = s9mod(cls.tmp, "scope")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.m.proc_cache_clear()
        self.calls = {"n": 0}
        self._orig = self.m._proc_table_read

        def counted(how):
            self.calls["n"] += 1
            return self._orig(how)
        self.m._proc_table_read = counted

    def tearDown(self):
        self.m._proc_table_read = self._orig
        self.m.proc_cache_clear()

    # ---- S1. 한 요청 = 한 번의 훑기 -------------------------------------
    def test_s1_scope_reads_once(self):
        with self.m.proc_scope():
            for _ in range(20):
                self.m.proc_table()
        self.assertEqual(self.calls["n"], 1,
                         "스코프 안에서 표를 여러 번 떴다 — 폴 한 바퀴가 "
                         "세션 수만큼 훑던 그 결함이다")

    def test_s1b_scope_table_is_the_same_table(self):
        with self.m.proc_scope():
            a, b = self.m.proc_table(), self.m.proc_table()
        self.assertIs(a, b)

    # ---- S5. 스코프 밖은 종전대로 매번 신선 ------------------------------
    def test_s5_outside_scope_always_fresh(self):
        for _ in range(3):
            self.m.proc_table()
        self.assertEqual(self.calls["n"], 3,
                         "스코프 밖(CLI·백그라운드 스레드)이 캐시를 얻어 탔다 "
                         "— tail 종료 반영 계약이 깨진다")

    def test_s5b_scope_does_not_leak_out(self):
        with self.m.proc_scope():
            self.m.proc_table()
        self.m.proc_table()
        self.assertEqual(self.calls["n"], 2, "스코프가 요청 밖까지 살아남았다")

    def test_s5c_scope_is_per_thread(self):
        seen = []

        def other():
            seen.append(getattr(self.m._PROC_SCOPE, "v", None))
        with self.m.proc_scope():
            t = threading.Thread(target=other)
            t.start()
            t.join()
        self.assertEqual(seen, [None],
                         "스코프가 스레드 사이로 샌다 — 한 요청의 표가 다른 "
                         "요청의 판정이 된다")

    # ---- S6/S8. 버릴 수 있어야 오래 사는 요청이 안 굳는다 ----------------
    def test_s6_scope_reset_refreshes(self):
        with self.m.proc_scope():
            self.m.proc_table()
            self.m.proc_scope_reset()
            self.m.proc_table()
        self.assertEqual(self.calls["n"], 2)

    def test_s8_cache_clear_clears_scope_too(self):
        with self.m.proc_scope():
            self.m.proc_table()
            self.m.proc_cache_clear()
            self.m.proc_table()
        self.assertEqual(self.calls["n"], 2,
                         "proc_cache_clear 가 '다시 뜬다'고 말하고 안 떴다")

    def test_s6b_sse_loop_drops_the_scope(self):
        """5분짜리 응답이 5분 낡은 표를 들지 않는다 — 소스 계약."""
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index('parsed.path == "/api/stream/sse"')
        j = src.index("elif parsed.path ==", i + 10)
        self.assertIn("proc_scope_reset()", src[i:j],
                      "SSE 루프가 요청 스코프를 바퀴마다 버리지 않는다")

    def test_s6c_scope_gate_is_one_place(self):
        """문은 메서드마다가 아니라 handle_one_request 한 곳이다."""
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index("def handle_one_request(self):")
        j = src.index("        def ", i + 10)
        # 문의 자리를 묻지 글자를 묻지 않는다 — 같은 문에 다른 범위가 함께
        # 서면(`with proc_scope(), streams_scope():`, REQ-20260902-004) 글자만
        # 달라진다. 계약은 "이 메서드가 스코프를 연다"다.
        self.assertIn("proc_scope()", src[i:j],
                      "요청 스코프의 문이 handle_one_request 에 없다 — "
                      "나중에 붙는 메서드가 그냥 지나간다")

    # ---- S4. 겹친 훑기는 하나로 접힌다 -----------------------------------
    def test_s4_concurrent_reads_collapse(self):
        slow = threading.Event()

        def slowread(how):
            slow.wait(5)
            return self._orig(how)
        self.m._proc_table_read = slowread
        self.m._PROC_STAT["max_inflight"] = 0
        n0 = self.m._PROC_STAT["reads"]
        out = [None] * 16

        def one(i):
            out[i] = self.m.proc_table()
        ts = [threading.Thread(target=one, args=(i,)) for i in range(16)]
        for t in ts:
            t.start()
        time.sleep(0.3)               # 16개가 모두 문 앞에 서게 둔다
        slow.set()
        for t in ts:
            t.join(20)
        self.assertEqual(self.m._PROC_STAT["max_inflight"], 1,
                         "동시 진입이 1이 아니다 — 32개가 함께 훑던 그림이 "
                         "그대로다")
        self.assertLessEqual(self.m._PROC_STAT["reads"] - n0, 2,
                             "동시 16건이 훑기 16번을 만들었다")
        self.assertTrue(all(o is not None for o in out), "빈손으로 돌아왔다")

    # ---- S7. 훑기가 죽어도 대기자가 갇히지 않는다 ------------------------
    def test_s7_failed_read_does_not_trap_waiters(self):
        gate = threading.Event()
        boom = {"on": True}

        def fragile(how):
            if boom["on"]:
                gate.wait(5)
                boom["on"] = False
                raise OSError("훑기가 죽었다")
            return self._orig(how)
        self.m._proc_table_read = fragile
        res = {}

        def loser():
            try:
                res["v"] = self.m.proc_table()
            except OSError as e:      # 첫 훑기를 집은 스레드는 예외를 받는다
                res["e"] = repr(e)

        def waiter():
            time.sleep(0.2)
            try:
                res["w"] = self.m.proc_table()
            except OSError as e:
                res["we"] = repr(e)
        a, b = threading.Thread(target=loser), threading.Thread(target=waiter)
        a.start()
        b.start()
        gate.set()
        a.join(20)
        b.join(20)
        self.assertFalse(a.is_alive() or b.is_alive(),
                         "훑기가 죽자 대기자가 30초 상한까지 갇혔다")
        self.assertTrue(res.get("w"), "대기자가 스스로 다시 뜨지 않았다")
        self.m._proc_table_read = self._orig
        self.assertTrue(self.m.proc_table(), "한 번의 실패가 표를 굳혔다")


class ProcScanServer(unittest.TestCase):
    """실서버로 잰다 — 한 요청이 `/proc` 을 몇 번 훑는가."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9procd-")
        env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
               "S9_PORT_GUARD": "off"}
        env.pop("S9_SESSION", None)
        cls.env = env
        subprocess.run([S9, "init"], capture_output=True, env=env, timeout=30)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=env, timeout=30)
        # 바인딩을 파일로 직접 놓는다 (CLI 왕복 40회 = 7초를 아낀다).
        # 서버가 읽는 것은 이 파일이고, 곱셈 인자는 그 개수다.
        sdir = os.path.join(cls.tmp, "state", "sessions")
        os.makedirs(sdir, exist_ok=True)
        for i in range(BINDINGS):
            sid = f"scan{i:04d}"
            with open(os.path.join(sdir, f"testbox__{sid}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"machine": "testbox", "session": sid,
                           "user": "alice", "attach_pid": "1",
                           "history": [], "active_reqs": []}, f)
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=10)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, path, timeout=60):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=timeout) as r:
            return r.status, r.read()

    def gauge(self):
        return json.loads(self.get("/api/serveinfo")[1])["proc"]

    def scans(self, path, n=1):
        """그 요청이 실제로 `/proc` 을 몇 번 훑었나 (계기 델타)."""
        before = self.gauge()["reads"]
        if n == 1:
            self.assertEqual(self.get(path)[0], 200)
        else:
            out = [None] * n
            ts = [threading.Thread(target=lambda i=i: out.__setitem__(
                i, self.get(path)[0])) for i in range(n)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(90)
            self.assertEqual(out, [200] * n, out)
        return self.gauge()["reads"] - before

    # ---- S14. 계기가 있다 ------------------------------------------------
    def test_proc_scan_server(self):
        """실서버로 잰다 — 한 요청이 `/proc` 을 몇 번 훑는가."""
        with self.subTest("s14_serveinfo_reports_the_gauge"):
                g = self.gauge()
                for k in ("backend", "reads", "shared", "max_inflight"):
                    self.assertIn(k, g, g)

            # ---- S2/S3. 한 요청 = 한 번의 훑기 (실서버) --------------------------
        with self.subTest("s2_chat_target_scans_once"):
            # 계기 델타에는 배경 스레드(워처·하트비트)의 훑기가 섞일 수 있으므로
            # 여유를 준다. 고치기 전 이 값은 바인딩 수(40)를 넘었다.
            d = self.scans("/api/chat/target")
            self.assertLessEqual(d, 3, f"/api/chat/target 한 요청이 {d}번 훑었다")
        with self.subTest("s3_sessions_scans_once"):
            d = self.scans("/api/sessions")
            self.assertLessEqual(d, 3, f"/api/sessions 한 요청이 {d}번 훑었다")
        with self.subTest("s3b_catalog_scans_once"):
                d = self.scans("/api/catalog")
                self.assertLessEqual(d, 3, f"/api/catalog 한 요청이 {d}번 훑었다")

            # ---- S4. 동시 요청이 훑기를 곱하지 않는다 ----------------------------
        with self.subTest("s4_concurrency_does_not_multiply"):
                one = self.scans("/api/chat/target")
                eight = self.scans("/api/chat/target", n=8)
                self.assertLessEqual(eight, one + 8,
                                     f"동시 8건이 훑기 {eight}번 — 동시성이 곱한다")
                self.assertLessEqual(self.gauge()["max_inflight"], 1,
                                     "동시 진입이 1을 넘었다 — 단일비행이 없다")

            # ---- S9. 신선도 계약: 요청마다 새로 뜬다 -----------------------------
        with self.subTest("s9_freshness_survives"):
            tail = shutil.which("tail")
            if not tail:
                self.skipTest("tail 없음")
            sid = "scan0000"
            inbox = os.path.join(self.tmp, "state", "terminal",
                                 f"inbox-{sid}.jsonl")
            os.makedirs(os.path.dirname(inbox), exist_ok=True)
            open(inbox, "a").close()
            p = subprocess.Popen([tail, "-f", inbox], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            try:
                time.sleep(0.3)
                r = json.loads(self.get(f"/api/chat/target?sid={sid}")[1])
                self.assertTrue(r["listening"], r)
            finally:
                p.terminate()
                p.wait(timeout=5)
            time.sleep(0.3)
            r = json.loads(self.get(f"/api/chat/target?sid={sid}")[1])
            self.assertFalse(r["listening"],
                             "tail 이 죽었는데 다음 요청이 여전히 수신 대기라 "
                             "말한다 — 스코프가 요청을 넘어 살아 있다")

if __name__ == "__main__":
    unittest.main()
