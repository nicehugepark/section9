"""한 요청이 streams 디렉토리를 한 번만 훑는다 (REQ-20260902-004-62x6).

REQ-20260901-024 가 `/proc` 전수 훑기를 치우자 같은 자리에서 다음 병목이
드러났다 — 스택 27개 중 19개가

    glob._iterdir <- streams_glob <- _binding_activity_paths
                  <- chat_alive <- chat_live <- chat_target

`chat_target` 은 바인딩을 전수로 돌며 후보마다 `chat_live` 를 부르고, 그것이
**바인딩마다** streams 디렉토리를 glob 했다. 착수 전 실측(2026-09-02, 실볼트
바인딩 159개 · streams 항목 137개):

    chat_target()          streams_glob 73회 · 0.081s   (자리가 둘이니 훑기 146회)
    실서버 /api/chat/target  1건 0.02s · 8동시 5.38s · 24동시 9.10s(연결 거부 11)

고침은 024 가 `/proc` 에 쓴 것과 같은 두 겹이다: 요청 스코프(`streams_scope`,
`Handler.handle_one_request`)와 단일비행(`_streams_names_shared`). 캐시하는
것은 **이름 목록뿐**이라 「활동이 신선한가」(mtime)는 종전대로 매번 새로 읽는다.

시간이 아니라 **훑기 횟수**를 센다 — 시간을 재면 기계가 바뀔 때마다 흔들린다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ streams_scan
"""
import fnmatch
import glob as _glob
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

from portpool import free_port, wait_server  # noqa: E402

BINDINGS = 40          # 훑기를 곱하던 인자 (실환경은 159개)
NOISE = 137            # streams 디렉토리 항목 수 (실환경 실측치)


def s9mod(root, tag):
    os.environ["S9_ROOT"] = root
    name = "s9str_" + tag
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def old_streams_glob(m, pattern, user=None):
    """고치기 전 구현 — 결과가 글자 그대로 같아야 한다 (S8)."""
    seen, out = set(), []
    for d in m.streams_read_dirs(user):
        for p in sorted(_glob.glob(os.path.join(d, pattern))):
            b = os.path.basename(p)
            if b not in seen:
                seen.add(b)
                out.append(p)
    return out


class StreamsScope(unittest.TestCase):
    """스코프·단일비행 자체의 계약 — 서버를 띄우지 않고 모듈로 직접 잰다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9strs-")
        cls.m = s9mod(cls.tmp, "scope")
        cls.dirs = [os.path.join(cls.tmp, "users", "alice", "streams"),
                    os.path.join(cls.tmp, "streams")]
        for d in cls.dirs:
            os.makedirs(d, exist_ok=True)
        for i in range(NOISE):
            open(os.path.join(cls.dirs[0], f"noise{i:04d}.jsonl"), "w").close()
        for n in ("aa11.jsonl", "aa11-sub.jsonl", ".hidden.jsonl", "가나.jsonl",
                  "aa11.txt"):
            open(os.path.join(cls.dirs[0], n), "w").close()
        for n in ("aa11.jsonl", "bb22.jsonl", ".hidden.jsonl"):
            open(os.path.join(cls.dirs[1], n), "w").close()
        cls.user = "alice"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.m.streams_scope_reset()
        self.calls = {"n": 0}
        self._orig = self.m._streams_names_read

        def counted(d):
            self.calls["n"] += 1
            return self._orig(d)
        self.m._streams_names_read = counted

    def tearDown(self):
        self.m._streams_names_read = self._orig

    def dirs_read(self):
        return len(self.m.streams_read_dirs(self.user))

    # ---- S1. 한 요청 = 자리마다 한 번의 훑기 -----------------------------
    def test_s1_scope_reads_once_per_dir(self):
        with self.m.streams_scope():
            for i in range(20):
                self.m.streams_glob(f"aa{i:02d}*.jsonl", self.user)
        self.assertEqual(self.calls["n"], self.dirs_read(),
                         "스코프 안에서 자리를 여러 번 훑었다 — 바인딩마다 "
                         "훑던 그 결함이다")

    def test_s1b_scope_list_is_the_same_list(self):
        d = self.m.streams_read_dirs(self.user)[0]
        with self.m.streams_scope():
            a, b = self.m.streams_names(d), self.m.streams_names(d)
        self.assertIs(a, b)

    # ---- S5. 스코프 밖은 종전대로 매번 신선 ------------------------------
    def test_s5_outside_scope_always_fresh(self):
        for _ in range(3):
            self.m.streams_glob("aa11*.jsonl", self.user)
        self.assertEqual(self.calls["n"], 3 * self.dirs_read(),
                         "스코프 밖(CLI·백그라운드 스레드)이 캐시를 얻어 탔다")

    def test_s5b_scope_does_not_leak_out(self):
        with self.m.streams_scope():
            self.m.streams_glob("aa11*.jsonl", self.user)
        self.m.streams_glob("aa11*.jsonl", self.user)
        self.assertEqual(self.calls["n"], 2 * self.dirs_read(),
                         "스코프가 요청 밖까지 살아남았다")

    def test_s5c_scope_is_per_thread(self):
        seen = []

        def other():
            seen.append(getattr(self.m._STREAMS_SCOPE, "v", None))
        with self.m.streams_scope():
            t = threading.Thread(target=other)
            t.start()
            t.join()
        self.assertEqual(seen, [None],
                         "스코프가 스레드 사이로 샌다 — 한 요청의 목록이 "
                         "다른 요청의 판정이 된다")

    # ---- S6. 버릴 수 있어야 오래 사는 요청이 안 굳는다 -------------------
    def test_s6_scope_reset_refreshes(self):
        with self.m.streams_scope():
            self.m.streams_glob("aa11*.jsonl", self.user)
            self.m.streams_scope_reset()
            self.m.streams_glob("aa11*.jsonl", self.user)
        self.assertEqual(self.calls["n"], 2 * self.dirs_read())

    def test_s6b_sse_loop_drops_the_scope(self):
        """5분짜리 응답이 5분 낡은 파일 목록을 들지 않는다 — 소스 계약."""
        src = open(S9, encoding="utf-8").read()
        i = src.index('parsed.path == "/api/stream/sse"')
        j = src.index("elif parsed.path ==", i + 10)
        self.assertIn("streams_scope_reset()", src[i:j],
                      "SSE 루프가 요청 스코프를 바퀴마다 버리지 않는다")

    def test_s6c_scope_gate_is_one_place(self):
        """문은 메서드마다가 아니라 handle_one_request 한 곳이다."""
        src = open(S9, encoding="utf-8").read()
        i = src.index("def handle_one_request(self):")
        j = src.index("        def ", i + 10)
        self.assertIn("streams_scope()", src[i:j],
                      "요청 스코프의 문이 handle_one_request 에 없다 — "
                      "나중에 붙는 메서드가 그냥 지나간다")

    # ---- S4. 겹친 훑기는 하나로 접힌다 -----------------------------------
    def test_s4_concurrent_reads_collapse(self):
        slow = threading.Event()

        def slowread(d):
            slow.wait(5)
            return self._orig(d)
        self.m._streams_names_read = slowread
        self.m._STREAMS_STAT["max_inflight"] = 0
        n0 = self.m._STREAMS_STAT["reads"]
        d = self.m.streams_read_dirs(self.user)[0]
        out = [None] * 16

        def one(i):
            out[i] = self.m.streams_names(d)
        ts = [threading.Thread(target=one, args=(i,)) for i in range(16)]
        for t in ts:
            t.start()
        time.sleep(0.3)               # 16개가 모두 문 앞에 서게 둔다
        slow.set()
        for t in ts:
            t.join(20)
        self.assertEqual(self.m._STREAMS_STAT["max_inflight"], 1,
                         "동시 진입이 1이 아니다 — 19개가 함께 훑던 그림이 "
                         "그대로다")
        self.assertLessEqual(self.m._STREAMS_STAT["reads"] - n0, 2,
                             "동시 16건이 훑기 16번을 만들었다")
        self.assertTrue(all(o is not None for o in out), "빈손으로 돌아왔다")

    # ---- S7. 훑기가 죽어도 대기자가 갇히지 않는다 ------------------------
    def test_s7_failed_read_does_not_trap_waiters(self):
        gate = threading.Event()
        boom = {"on": True}
        d = self.m.streams_read_dirs(self.user)[0]

        def fragile(dd):
            if boom["on"]:
                gate.wait(5)
                boom["on"] = False
                raise OSError("훑기가 죽었다")
            return self._orig(dd)
        self.m._streams_names_read = fragile
        res = {}

        def loser():
            try:
                res["v"] = self.m.streams_names(d)
            except OSError as e:      # 첫 훑기를 집은 스레드는 예외를 받는다
                res["e"] = repr(e)

        def waiter():
            time.sleep(0.2)
            try:
                res["w"] = self.m.streams_names(d)
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
        self.assertTrue(res.get("w"), "대기자가 스스로 다시 훑지 않았다")
        self.m._streams_names_read = self._orig
        self.assertTrue(self.m.streams_names(d), "한 번의 실패가 목록을 굳혔다")

    def test_s7b_missing_dir_is_empty_not_fatal(self):
        self.assertEqual(self.m._streams_names_read(
            os.path.join(self.tmp, "없는자리")), [])

    # ---- S8. 결과가 옛 구현과 글자 그대로 같다 ---------------------------
    def test_s8_same_result_as_glob(self):
        for pat in ("*.jsonl", "aa11*.jsonl", "aa11.jsonl", "bb22*.jsonl",
                    "가나*.jsonl", "없는것*.jsonl", ".hidden*", "*"):
            with self.subTest(pat=pat):
                self.assertEqual(self.m.streams_glob(pat, self.user),
                                 old_streams_glob(self.m, pat, self.user),
                                 f"패턴 {pat!r} 의 결과가 달라졌다")

    def test_s8b_same_result_inside_scope(self):
        with self.m.streams_scope():
            got = self.m.streams_glob("*.jsonl", self.user)
        self.assertEqual(got, old_streams_glob(self.m, "*.jsonl", self.user))

    # ---- S9. 새 파일은 다음 요청이 곧바로 본다 ---------------------------
    def test_s9_new_file_seen_by_next_scope(self):
        d = self.m.streams_read_dirs(self.user)[0]
        p = os.path.join(d, "zz99.jsonl")
        try:
            with self.m.streams_scope():
                self.assertEqual(self.m.streams_glob("zz99*.jsonl", self.user),
                                 [])
                open(p, "w").close()
            with self.m.streams_scope():
                self.assertEqual(self.m.streams_glob("zz99*.jsonl", self.user),
                                 [p], "다음 요청이 새 스트림을 못 본다 — "
                                 "스코프가 요청을 넘어 살아 있다")
        finally:
            os.path.exists(p) and os.unlink(p)


class StreamsScanServer(unittest.TestCase):
    """실서버로 잰다 — 한 요청이 streams 자리를 몇 번 훑는가."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9strd-")
        env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
               "S9_PORT_GUARD": "off"}
        env.pop("S9_SESSION", None)
        cls.env = env
        subprocess.run([S9, "init"], capture_output=True, env=env, timeout=60)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=env, timeout=60)
        sdir = os.path.join(cls.tmp, "state", "sessions")
        strd = os.path.join(cls.tmp, "users", "alice", "streams")
        os.makedirs(sdir, exist_ok=True)
        os.makedirs(strd, exist_ok=True)
        for i in range(NOISE):
            open(os.path.join(strd, f"noise{i:04d}.jsonl"), "w").close()
        # 바인딩을 파일로 직접 놓는다 (CLI 왕복 40회 = 7초를 아낀다).
        # 스트림 파일이 신선하니 후보는 전부 live — 훑기의 곱셈 인자가 산다.
        for i in range(BINDINGS):
            sid = f"scan{i:04d}"
            open(os.path.join(strd, f"{sid}.jsonl"), "w").close()
            with open(os.path.join(sdir, f"testbox__{sid}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"machine": "testbox", "session": sid,
                           "user": "alice", "history": [], "active_reqs": []},
                          f)
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

    def get(self, path, timeout=120):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=timeout) as r:
            return r.status, r.read()

    def gauge(self):
        return json.loads(self.get("/api/serveinfo")[1])["streams"]

    def scans(self, path, n=1):
        """그 요청이 실제로 streams 자리를 몇 번 훑었나 (계기 델타)."""
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
                t.join(180)
            self.assertEqual(out, [200] * n, out)
        return self.gauge()["reads"] - before

    # ---- S14. 계기가 있다 ------------------------------------------------
    def test_s14_serveinfo_reports_the_gauge(self):
        g = self.gauge()
        for k in ("reads", "shared", "max_inflight"):
            self.assertIn(k, g, g)

    # ---- S2/S3. 한 요청 = 자리마다 한 번의 훑기 (실서버) -----------------
    def test_s2_chat_target_scans_once(self):
        # 계기 델타에는 배경 스레드(워처·하트비트)의 훑기가 섞일 수 있으므로
        # 여유를 준다. 고치기 전 이 값은 바인딩 수(40)의 두 배를 넘었다.
        d = self.scans("/api/chat/target")
        self.assertLessEqual(d, 4, f"/api/chat/target 한 요청이 {d}번 훑었다")

    def test_s3_sessions_scans_once(self):
        d = self.scans("/api/sessions")
        self.assertLessEqual(d, 4, f"/api/sessions 한 요청이 {d}번 훑었다")

    def test_s3b_catalog_scans_once(self):
        d = self.scans("/api/catalog")
        self.assertLessEqual(d, 4, f"/api/catalog 한 요청이 {d}번 훑었다")

    # ---- S4. 동시 요청이 훑기를 곱하지 않는다 ----------------------------
    def test_s4_concurrency_does_not_multiply(self):
        one = self.scans("/api/chat/target")
        eight = self.scans("/api/chat/target", n=8)
        self.assertLessEqual(eight, one + 8,
                             f"동시 8건이 훑기 {eight}번 — 동시성이 곱한다")
        self.assertLessEqual(self.gauge()["max_inflight"], 1,
                             "동시 진입이 1을 넘었다 — 단일비행이 없다")

    # ---- S9. 신선도 계약: 요청마다 새로 뜬다 -----------------------------
    def test_s9_new_stream_seen_next_request(self):
        sid = "fresh999"
        strd = os.path.join(self.tmp, "users", "alice", "streams")
        with open(os.path.join(self.tmp, "state", "sessions",
                               f"testbox__{sid}.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"machine": "testbox", "session": sid, "user": "alice",
                       "history": [], "active_reqs": []}, f)
        r = json.loads(self.get(f"/api/chat/target?sid={sid}")[1])
        self.assertFalse(r.get("live"), r)
        open(os.path.join(strd, f"{sid}.jsonl"), "w").close()
        r = json.loads(self.get(f"/api/chat/target?sid={sid}")[1])
        self.assertTrue(r.get("live"),
                        "새 스트림이 생겼는데 다음 요청이 여전히 죽었다고 "
                        "말한다 — 목록 캐시가 요청을 넘어 살아 있다")


if __name__ == "__main__":
    unittest.main()
