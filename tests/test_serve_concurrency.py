"""대시보드가 동시 요청을 견디는가 (REQ-20260827-014-62x6).

designer 가 REQ-20260827-005 작업 중 보고했다: `127.0.0.1:9909` 에 동시 12요청을
보내면 6건이 연결 리셋된다. 대시보드는 카탈로그 폴링·SSE·감시 기록·첨부 본문을
한 화면에서 겹쳐 보내므로 이건 드문 상황이 아니라 평소 상황이다.

**전제를 다시 쟀다.** 문서에 적힌 "기본 HTTPServer 라 한 번에 한 요청만 처리한다"는
지금 코드에 해당하지 않는다 — `cmd_serve` 는 이미 `ThreadingHTTPServer` 에
`request_queue_size = 32` 다. 그런데도 증상은 재현되고, **맨살 stdlib 서버로도
똑같이 재현된다**(동시 40 → 10 성공/30 거절, 리슨 큐 128, 즉답 핸들러). 즉 남은
것은 우리 서버의 결함이 아니라 이 환경(WSL2 루프백)이 **같은 순간에 도착한 SYN**
을 열 개쯤에서 자르는 성질이다. 5ms 만 벌려 보내면 40건이 전부 통과한다.

그래서 이 파일이 지키는 것은 "몇 개까지 되는가"가 아니라 **서버가 병렬로 돈다**는
계약이다. 그 계약이 깨지면(단일 스레드로 되돌아가면) 증상은 환경과 무관하게,
그리고 훨씬 낮은 동시성에서 돌아온다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ serve_concurrency
"""
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import free_port, wait_server  # noqa: E402

# 브라우저가 한 출처에 여는 HTTP/1.1 연결 수 상한. 이 아래에서는 위 환경 성질에
# 걸리지 않으므로, 여기서 실패하면 그건 정말 우리 서버 문제다.
BROWSER_CONNS = 6


class ServeConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9conc-")
        env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
               "S9_PORT_GUARD": "off"}
        env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=env, timeout=20)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=env, timeout=20)
        for i in range(12):        # 카탈로그에 무게를 준다
            subprocess.run([S9, "new", "request", "--title", f"doc{i}",
                            "--summary", "t", "--goal", "t", "--size", "S",
                            "--user", "alice", "--body", "x" * 400],
                           capture_output=True, env=env, timeout=20)
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    def get(self, path="/api/catalog", timeout=20):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=timeout) as r:
            return r.status, r.read()

    def burst(self, n, path="/api/catalog"):
        """n건을 동시에 던지고 (결과들, 벽시계 초) 를 준다."""
        out = [None] * n

        def one(i):
            try:
                out[i] = self.get(path)[0]
            except Exception as e:            # noqa: BLE001 — 무엇이든 기록한다
                out[i] = repr(e)

        ts = [threading.Thread(target=one, args=(i,)) for i in range(n)]
        t0 = time.time()
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        return out, time.time() - t0

    # N1. 브라우저가 여는 만큼(6)은 전부 200 이다
    def test_serve_concurrency(self):
        """ServeConcurrency 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_browser_level_concurrency_all_ok"):
                out, _ = self.burst(BROWSER_CONNS)
                self.assertEqual(out, [200] * BROWSER_CONNS, out)

            # N2. 직렬이 아니다 — 동시 6건이 한 건의 6배가 아니라 그에 가깝게 끝난다.
            #     '스레드로 돈다'의 관측 가능한 정의가 이것이다. 단일 스레드였다면
            #     6배(+대기열 리셋)가 되고, 넉넉히 잡은 3배 문턱에서 걸린다.
        with self.subTest("n2_not_serialized"):
                t0 = time.time()
                self.get()
                solo = time.time() - t0
                _, wall = self.burst(BROWSER_CONNS)
                self.assertLess(wall, max(solo * 3, 1.0),
                                f"동시 {BROWSER_CONNS}건 {wall:.2f}s vs 단건 {solo:.2f}s "
                                f"— 직렬로 처리되고 있다")

            # B1. 한 연결이 오래 붙잡고 있어도 다른 요청이 막히지 않는다.
            #     SSE 가 그러듯 커넥션을 점유하는 상황을 라우트에 의존하지 않고 만든다 —
            #     요청 줄만 보내고 헤더를 끝내지 않으면 그 핸들러는 계속 읽기에 앉아 있다.
            #     단일 스레드 서버였다면 그 한 자리가 서버 전체를 세운다.
        with self.subTest("b1_stuck_connection_does_not_block"):
                hold = socket.create_connection(("127.0.0.1", self.port), 5)
                try:
                    hold.sendall(b"GET /api/catalog HTTP/1.1\r\nHost: x\r\n")
                    time.sleep(0.2)                     # 서버가 그 연결을 집게 둔다
                    out, _ = self.burst(3)
                    self.assertEqual(out, [200] * 3, out)
                finally:
                    hold.close()

            # F1. 리슨 큐 계약 — 파이썬 기본값(5)으로 되돌아가면 잡는다.
            #     수는 이제 이름을 얻었다(SERVE_BACKLOG, REQ-20260901-020) — 그래서
            #     대입 자리의 글자가 아니라 **실제로 쓰이는 값**을 잰다. 리터럴만 보면
            #     이름 뒤에서 5로 내려가도 시험이 침묵한다.
        with self.subTest("f1_queue_size_contract"):
                src = open(os.path.join(HERE, "..", "bin", "s9"), encoding="utf-8").read()
                self.assertIsNotNone(
                    re.search(r"ThreadingHTTPServer\.request_queue_size\s*=\s*"
                              r"SERVE_BACKLOG", src),
                    "request_queue_size 설정이 사라졌다")
                m = re.search(r"^SERVE_BACKLOG\s*=.*?(\d+)\s*,\s*int\)", src,
                              re.M)
                self.assertIsNotNone(m, "SERVE_BACKLOG 기본값을 못 찾았다")
                self.assertGreaterEqual(int(m.group(1)), 32, m.group(0))

            # R1. 서버가 다시 단일 스레드로 바뀌면 잡는다 — N2 보다 먼저, 명시적으로
            # (REQ-20260830-028 뒤로 바인드 지점은 QuietDisconnectServer 지만, 그것이
            #  ThreadingHTTPServer 의 자식이라는 사실까지 함께 계약한다 — 이름만 보면
            #  단일 스레드 부모로 바꿔치기해도 이 시험이 침묵한다.)
        with self.subTest("r1_server_is_threaded"):
            src = open(os.path.join(HERE, "..", "bin", "s9"), encoding="utf-8").read()
            flat = src.replace(" ", "")
            self.assertIn("QuietDisconnectServer((", flat,
                          "serve 바인드 지점이 사라졌다")
            self.assertIn("classQuietDisconnectServer(http.server.ThreadingHTTPServer)",
                          flat, "serve 가 단일 스레드 HTTPServer 로 되돌아갔다")

if __name__ == "__main__":
    unittest.main()
