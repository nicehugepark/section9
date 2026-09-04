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
        cls.src = open(S9, encoding="utf-8").read()

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


if __name__ == "__main__":
    unittest.main()
