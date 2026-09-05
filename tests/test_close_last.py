"""서버는 둘째로 닫는다 — 리스닝 쪽이 먼저 보낸 FIN 마다 WSL 중계가 호스트
동적 포트를 제 수명 동안 쥔다 (REQ-20260905-002).

실측 2026-09-05: 서버가 먼저 닫은 연결 20건 → 윈도우 Bound +20, 안 돌아옴.
클라이언트가 먼저 닫은 20건 → 0. `Connection: close` 를 청하는 urllib 기본
요청이 곧 「서버가 먼저 닫는」 경로였고, 시험 스위트 한 바퀴가 그렇게 ~480 을
쌓았다. 서버는 응답 뒤 상대의 FIN 을 잠깐 기다렸다가 닫는다 — 그러면
TIME-WAIT 이 서버 포트가 아니라 클라이언트 포트 쪽에 남는다. 이 파일은 그
방향을 리눅스 `ss` 로 잰다(다른 OS 는 건너뛴다).

실행: python3 tests/ close_last
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
sys.path.insert(0, HERE)
from portpool import free_port, wait_server  # noqa: E402


def _time_waits(port):
    """(서버 포트가 로컬인 TIME-WAIT 수, 서버 포트가 상대인 TIME-WAIT 수)."""
    out = subprocess.run(["ss", "-Htan"], capture_output=True, text=True).stdout
    srv = cli = 0
    for line in out.splitlines():
        f = line.split()
        if len(f) < 5 or f[0] != "TIME-WAIT":
            continue
        if f[3].endswith(f":{port}"):
            srv += 1
        elif f[4].endswith(f":{port}"):
            cli += 1
    return srv, cli


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("ss"),
                     "리눅스의 ss 로 TIME-WAIT 방향을 잰다")
class ServerClosesLast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9close-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester", "S9_REWORK_WATCH": "off"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=30, stdin=subprocess.DEVNULL)
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_t1_connection_close_requests_leave_time_wait_on_the_client(self):
        """T1. `Connection: close` 요청 10건 뒤 TIME-WAIT 은 전부 클라이언트 쪽이다."""
        srv0, cli0 = _time_waits(self.port)
        for _ in range(10):
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/api/serveinfo", timeout=5) as r:
                r.read()
        time.sleep(0.3)
        srv, cli = _time_waits(self.port)
        self.assertEqual(srv - srv0, 0,
                         f"서버가 먼저 닫은 연결 {srv - srv0}건 — 중계가 그만큼 쥔다")
        self.assertGreaterEqual(cli - cli0, 10,
                                "클라이언트 쪽 TIME-WAIT 이 안 늘었다 — 계측 자체를 의심하라")

    def test_t2_a_client_that_never_closes_is_still_let_go(self):
        """T2. 상대가 안 닫아도 상한 안에 서버가 닫는다 — 기다림은 유계다."""
        c = socket.create_connection(("127.0.0.1", self.port), 5)
        c.sendall(f"GET /api/serveinfo HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                  f"Connection: close\r\n\r\n".encode())
        c.settimeout(5)
        buf = b""
        t0 = time.time()
        while True:
            try:
                chunk = c.recv(65536)
            except ConnectionResetError:
                break                # 서버가 리셋으로 놓았다 — 놓은 것은 놓은 것이다
            if not chunk:
                break                # 서버의 FIN
            buf += chunk
        self.assertIn(b"HTTP/1.1 200", buf)
        self.assertLess(time.time() - t0, 4.0, "상대가 안 닫는 연결을 서버가 놓지 않는다")
        c.close()


if __name__ == "__main__":
    unittest.main()
