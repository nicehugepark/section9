"""공개는 왕복으로 끝난다 — 연결됨이 아니라 준비됨 (REQ-20260904-015).

네 역할의 합의(REQ-20260904-013): 재시도의 자리는 붙는 쪽이 아니라 **여는
쪽**이다. listen() 이 돌아온 것과 남들이 붙을 수 있는 것은 다른 사건이고
(WSL 중계의 창, 실측 7%), 그 창 안에 「떴다」를 알리면 사람과 훅이 거부를
만난다. 그래서 남들이 쓸 그 주소로 내가 나에게 물어 **내 답**을 받은 뒤에야
알린다 — 같은 왕복이 점거(남이 답한다)까지 가른다.

실행: python3 tests/ serve_ready
"""
import importlib.machinery
import importlib.util
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
sys.path.insert(0, HERE)
import portpool  # noqa: E402


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_ready", importlib.machinery.SourceFileLoader("s9_ready", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _responder(payload, started=None, rst=False, hold=False):
    """한 번 받고 답하는 최소 서버 — (소켓, 포트). payload 가 None 이면 중계 흉내
    (받고 아무것도 안 보내고 닫는다). rst 면 리셋으로 끊는다. hold 면 답한 뒤
    **닫지 않는다**(실서버의 keep-alive 모양)."""
    srv = portpool.pool_socket()
    port = srv.getsockname()[1]
    keep = []

    def run():
        try:
            c, _ = srv.accept()
        except OSError:
            return
        if rst:
            c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                         struct.pack("ii", 1, 0))
            c.close()
            return
        try:
            c.recv(4096)
        except OSError:
            c.close()
            return
        if payload is not None:
            c.sendall(payload)
        if hold:
            keep.append(c)          # 열어 둔다 — 시험이 끝나면 GC 가 닫는다
        else:
            c.close()
    threading.Thread(target=run, daemon=True).start()
    return srv, port


def _http_json(obj):
    body = json.dumps(obj).encode()
    return (b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)


class TheRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_r1_a_real_answer_with_my_stamp_is_ready_and_mine(self):
        srv, port = _responder(_http_json({"started": "X"}))
        try:
            r = self.m.dashboard_ready("127.0.0.1", port, expect_started="X")
        finally:
            srv.close()
        self.assertTrue(r["ready"], r)
        self.assertTrue(r["mine"])
        self.assertEqual(r["attempts"], 1)

    def test_r1b_a_kept_alive_answer_is_read_without_waiting_for_eof(self):
        """R1b. 답한 뒤 안 닫는 서버(keep-alive)도 Content-Length 로 끝을 안다.

        실서버가 그렇다 — EOF 를 기다리면 2초 타임아웃이 「준비 안 됨」으로 읽힌다
        (W3 첫 실행 실측: TimeoutError).
        """
        import time
        srv, port = _responder(_http_json({"started": "X"}), hold=True)
        t0 = time.monotonic()
        try:
            r = self.m.dashboard_ready("127.0.0.1", port, expect_started="X")
        finally:
            srv.close()
        self.assertTrue(r["ready"], r)
        self.assertLess(time.monotonic() - t0, 1.5, "EOF 를 기다렸다")

    def test_r2_one_refusal_then_answer_counts_the_window(self):
        """R2. 첫 연결이 거부되고 둘째에 붙으면 attempts=2 — 창이 횟수로 보인다."""
        n = {"i": 0}
        def connect(h, p):
            n["i"] += 1
            if n["i"] == 1:
                raise ConnectionRefusedError("window")
            return _http_json({"started": "X"})
        r = self.m.dashboard_ready("127.0.0.1", 1, expect_started="X",
                                   _connect=connect, _sleep=lambda s: None)
        self.assertTrue(r["ready"])
        self.assertEqual(r["attempts"], 2)

    def test_f1_relay_style_accept_and_close_is_not_ready(self):
        """F1. 중계 흉내(받고 아무것도 안 보내고 닫음) → 준비 아님."""
        srv, port = _responder(None)
        try:
            r = self.m.dashboard_ready("127.0.0.1", port)
        finally:
            srv.close()
        self.assertFalse(r["ready"])
        self.assertIn("HTTP 응답이 없다", r["why"])

    def test_f2_someone_elses_answer_is_ready_but_not_mine(self):
        """F2. 답은 오는데 started 가 다르다 → 점거로 이름이 붙는다."""
        srv, port = _responder(_http_json({"started": "Y"}))
        try:
            r = self.m.dashboard_ready("127.0.0.1", port, expect_started="X")
        finally:
            srv.close()
        self.assertTrue(r["ready"])
        self.assertIs(r["mine"], False)
        self.assertIn("점거", r["why"])

    def test_f3_a_reset_is_never_retried(self):
        """F3. 리셋은 재시도하지 않는다 — 우리 자리에서의 리셋은 점거의 지문이다."""
        n = {"i": 0}
        def connect(h, p):
            n["i"] += 1
            raise ConnectionResetError("rst")
        r = self.m.dashboard_ready("127.0.0.1", 1, _connect=connect,
                                   _sleep=lambda s: None)
        self.assertFalse(r["ready"])
        self.assertEqual(n["i"], 1, "리셋을 되걸었다 — 가로채기가 계기판에서 사라진다")
        self.assertIn("점거", r["why"])

    def test_f3b_a_real_rst_is_never_retried(self):
        """F3b. 흉내가 아니라 진짜 RST 로도 — 연결 한 번뿐이다."""
        srv, port = _responder(None, rst=True)
        try:
            r = self.m.dashboard_ready("127.0.0.1", port)
        finally:
            srv.close()
        self.assertFalse(r["ready"])
        self.assertEqual(r["attempts"], 1)

    def test_f4_nobody_listening_fails_fast(self):
        """F4. 거부만 오면 3회·1초 안에 False — 죽은 서버를 멈춤으로 바꾸지 않는다."""
        sleeps = []
        def connect(h, p):
            raise ConnectionRefusedError("dead")
        r = self.m.dashboard_ready("127.0.0.1", 1, _connect=connect,
                                   _sleep=sleeps.append)
        self.assertFalse(r["ready"])
        self.assertLessEqual(r["attempts"], self.m.DASH_READY_TRIES)
        self.assertLessEqual(sum(sleeps), self.m.DASH_READY_BUDGET + 1e-9)
        self.assertTrue(all(b >= a for a, b in zip(sleeps, sleeps[1:])),
                        f"간격이 자라지 않는다: {sleeps}")

    def test_b1_without_a_stamp_mine_is_not_asked(self):
        """B1. 지문 없이 물으면 mine 은 묻지 않는다 — `s9 code` 는 남의 지문을 모른다."""
        srv, port = _responder(_http_json({"started": "X"}))
        try:
            r = self.m.dashboard_ready("127.0.0.1", port)
        finally:
            srv.close()
        self.assertTrue(r["ready"])
        self.assertIsNone(r["mine"])

    def test_b2_a_foreign_web_server_is_not_ready(self):
        """B2. HTTP 200 이지만 serveinfo 가 아니면(다른 프로그램) 준비 아님."""
        srv, port = _responder(b"HTTP/1.0 200 OK\r\n\r\n<html>hi</html>")
        try:
            r = self.m.dashboard_ready("127.0.0.1", port)
        finally:
            srv.close()
        self.assertFalse(r["ready"])
        self.assertIn("serveinfo 가 아니다", r["why"])


class TheWiring(unittest.TestCase):
    """W1·W2. 도우미가 있어도 쓰는 자리가 안 지나면 없는 것이다."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(S9_SRC, encoding="utf-8").read()

    def _body(self, name):
        return self.src.split(f"def {name}(", 1)[1].split("\ndef ", 1)[0]

    def test_w1_code_asks_readiness_not_a_bare_connect(self):
        body = self._body("cmd_code")
        self.assertIn("dashboard_ready(", body)
        self.assertNotIn("create_connection", body,
                         "연결 한 번으로 「실행 중」을 찍는 자리가 남았다")

    def test_w2_serve_round_trips_before_it_announces(self):
        body = self._body("cmd_serve")
        self.assertIn("dashboard_ready(", body)
        self.assertLess(body.index("dashboard_ready("), body.index("serve-code.json"),
                        "지문(serve-code.json)을 왕복 전에 쓴다")
        self.assertLess(body.index("dashboard_ready("),
                        body.index("section9 dashboard: http"),
                        "주소를 왕복 전에 알린다")
        self.assertIn("expect_started=SERVE_STARTED", body,
                      "자기 지문으로 묻지 않으면 점거를 못 가른다")


class TheRealServer(unittest.TestCase):
    """W3. 진짜 `s9 serve` 하나 — 왕복이 True 이고 started 가 serveinfo 와 같다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        cls.root = tempfile.mkdtemp(prefix="s9ready-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_REWORK_WATCH": "off",
                   "S9_PORT_GUARD": "off", "S9_METRICS": "off"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env, timeout=30)
        cls.port = portpool.free_port()
        cls.proc = subprocess.Popen([sys.executable, S9, "serve", "--host",
                                     "127.0.0.1", "--port", str(cls.port)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=cls.env, stdin=subprocess.DEVNULL)
        portpool.wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait(10)
        import shutil
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_w3_the_real_server_answers_and_its_stamp_matches(self):
        r = self.m.dashboard_ready("127.0.0.1", self.port)
        self.assertTrue(r["ready"], r)
        self.assertTrue(r["started"], "serveinfo 에 started 가 없다")
        again = self.m.dashboard_ready("127.0.0.1", self.port,
                                       expect_started=r["started"])
        self.assertTrue(again["mine"])


class TheHandshakeWindow(unittest.TestCase):
    """W4. 알리기 전 창은 요청을 하나만 받지 않는다 (REQ-20260906-046).

    serve 는 listen 뒤 자기왕복이 끝나야 주소를 알리는데, 그 사이 요청을 받는
    자리가 handle_request 한 번뿐이었다. 밖의 클라이언트(시험의 wait_server)가
    그 한 자리를 먼저 차지하면 서버 자신의 왕복은 backlog 에 남고, 부모는
    recv 2초를 다 기다린 뒤에야 serve_forever 로 들어간다 — 그 2초 창에 온
    다음 요청(W3)도 같이 기다려 timed out 됐다(1ms 간격으로 첫 자리를 노리면
    8회 중 4회). 창 안에서도 요청은 **끝날 때까지 계속** 받아야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def _server(self):
        import http.server

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"started": "X"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        # portpool 밖의 커널 임의 포트 — 이 서버는 밖에 알리지 않고 곧 닫는다.
        return srv, srv.server_address[1]

    def _get(self, port, deadline=1.0):
        import time
        # 갓 공개된 포트의 거부 창(WSL 중계, 실측 7%)만 짧게 되건다 — 여기서
        # 재는 것은 거부가 아니라 **붙은 뒤의 대기**다.
        for _ in range(20):
            try:
                c = socket.create_connection(("127.0.0.1", port), 1.0)
                break
            except ConnectionRefusedError:
                time.sleep(0.05)
        else:
            raise AssertionError("포트가 1초 넘게 거부한다")
        with c:
            c.sendall(b"GET / HTTP/1.0\r\n\r\n")
            c.settimeout(deadline)
            return c.recv(5)

    def test_w4_an_outsider_taking_the_first_slot_does_not_starve_the_probe(self):
        """W4. 밖의 요청이 먼저 자리를 차지해도 자기왕복과 그 다음 요청이 각각
        1초 안에 답을 받는다."""
        import time
        srv, port = self._server()
        try:
            seen = {}

            def probe():
                seen["outsider"] = self._get(port)         # 첫 자리를 뺏는다
                t0 = time.monotonic()
                r = self.m.dashboard_ready("127.0.0.1", port, expect_started="X")
                seen["probe_sec"] = time.monotonic() - t0
                seen["next"] = self._get(port)             # W3 의 자리
                return r

            r = self.m.serve_handshake(srv, probe)
            self.assertTrue(r["ready"] and r["mine"], r)
            self.assertEqual(r["attempts"], 1)
            self.assertTrue(seen["outsider"].startswith(b"HTTP/"))
            self.assertTrue(seen["next"].startswith(b"HTTP/"))
            self.assertLess(seen["probe_sec"], 1.0,
                            "자기왕복이 밖의 요청 뒤에서 기다린다")
        finally:
            srv.server_close()

    def test_w4b_the_pump_stops_and_the_timeout_is_restored(self):
        """W4b. 왕복이 끝나면 임시 펌프는 멈추고 timeout 은 원래 값으로 —
        serve_forever 가 그대로 이어받는다."""
        srv, port = self._server()
        try:
            srv.timeout = None
            before = threading.active_count()
            r = self.m.serve_handshake(
                srv, lambda: self.m.dashboard_ready("127.0.0.1", port))
            self.assertTrue(r["ready"], r)
            self.assertIsNone(srv.timeout)
            # 펌프 스레드는 끝났다 — 핸들러 스레드는 keep-alive 로 남을 수 있어
            # 펌프 하나만 센다.
            import time
            for _ in range(40):                 # 최대 1초 — 연결 없는 대기
                if threading.active_count() <= before + 1:
                    break
                time.sleep(0.025)
            self.assertLessEqual(threading.active_count(), before + 1)
        finally:
            srv.server_close()

if __name__ == "__main__":
    unittest.main()
