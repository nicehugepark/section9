"""연결을 놓아 주는가 — keep-alive 유휴 상한·SSE 사망 감지·동시 연결 상한.

REQ-20260901-020. 대시보드 서버는 연결 하나에 스레드 하나다. 그래서 **놓아
주지 않는 연결은 곧 놓아 주지 않는 스레드**다. 실사고(2026-09-01 20:40 실측):
재시작 10분 만에 ESTAB 129·스레드 143 이 쌓여 새 연결이 리셋되고, 살아남은
좀비 SSE 140개가 4Hz 로 8.7코어를 태웠다.

이 시험이 지키는 것은 숫자 셋이다 — **스레드는 되돌아온다**(S2/S8),
**긴 연결은 그 자에 안 걸린다**(S4), **넘칠 때는 답을 준다**(S6).
사람이 `ss` 를 쳐서 아는 것은 재발 방지가 아니라서 여기 기계로 박는다.

격리: S9_ROOT=mktemp, portpool. 실행: python3 tests/test_conn_reap.py
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100)
from portpool import free_port, wait_server  # noqa: E402

IDLE = 2.0          # 시험용 유휴 상한 (초) — 서버에 환경변수로 준다
MAXC = 12           # 시험용 동시 연결 상한 (상한 시험 전용)


def _wait(cond, timeout, step=0.1):
    """고정 sleep 대신 조건 대기 (tdd 스킬: sleep 폴링 금지)."""
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


class ConnBase(unittest.TestCase):
    # 두 자를 클래스마다 따로 준다 — 유휴 시험은 상한에, 상한 시험은 유휴에
    # 걸리면 안 된다(서로의 결과를 가린다).
    idle = IDLE
    maxc = 200
    per_session = 50   # 세대 은퇴가 다른 판정을 가리지 않게 (전용 시험은 따로)

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9conn-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "boss", "S9_REWORK_WATCH": "off",
                   "S9_KEEPALIVE_IDLE": str(cls.idle),
                   "S9_MAX_CONNS": str(cls.maxc),
                   "S9_SSE_PER_SESSION": str(cls.per_session)}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=60)
        subprocess.run([S9, "user", "add", "boss", "--role", "admin"],
                       capture_output=True, env=cls.env, timeout=60)
        cls.errlog = os.path.join(cls.tmp, "serve.err")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL,
            stderr=open(cls.errlog, "wb"))
        wait_server(cls.port)
        cls.base = len(os.listdir(f"/proc/{cls.srv.pid}/task"))

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        try:
            cls.srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.srv.kill()
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # --- 도구 ---
    def threads(self):
        return len(os.listdir(f"/proc/{self.srv.pid}/task"))

    def conn(self, timeout=10):
        """연결 하나. **램프업+재시도**로 연다.

        WSL2 루프백은 동시 SYN 을 ~10개에서 자른다(DOC-20260827-004) —
        연속 connect 를 몰아치면 ECONNREFUSED 가 섞여 나오고, 그것은 서버의
        판정이 아니라 회선의 아티팩트다. 재는 대상(서버가 연결을 놓아 주는가)
        을 회선 잡음으로 가리지 않도록 여기서 흡수한다.
        """
        last = None
        for i in range(20):
            try:
                s = socket.create_connection(("127.0.0.1", self.port),
                                             timeout=timeout)
            except OSError as e:
                last = e
                time.sleep(0.05 * (i + 1))
                continue
            self.addCleanup(lambda s=s: s.close())
            return s
        raise last

    @classmethod
    def hdr(cls, path):
        """Host 는 실제 바인드 주소여야 한다 — 아니면 리바인딩 가드가 421."""
        return (f"GET {path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{cls.port}\r\n").encode()

    def get(self, path="/api/whoami", extra=b"", s=None):
        s.sendall(self.hdr(path) + extra + b"\r\n")
        return ConnBase.read_response(s)

    def opened(self, path="/api/whoami", timeout=10):
        """연결 하나를 열고 **요청 하나를 성공시켜** 돌려준다.

        연결을 여러 개 세우는 것이 목적인 시험(S3·S8·상한)에서 쓴다. 이
        기계의 루프백은 첫 왕복을 이따금 RST 로 끊는데(DOC-20260827-004),
        그것은 재는 대상(스레드가 걷히는가)이 아니라 회선의 잡음이다 —
        여기서 흡수하고, 이어쓰기 자체를 재는 S1·S2 는 재시도 없이 그대로
        간다(거기서 끊기면 그것이 곧 결함이다).
        """
        last = None
        for i in range(12):
            s = self.conn(timeout=timeout)
            try:
                r = self.get(s=s, path=path)
            except OSError as e:
                last = e
                s.close()
                time.sleep(0.05 * (i + 1))
                continue
            if r.startswith(b"HTTP/1.1 200"):
                return s
            return s          # 200 이 아니면 부르는 쪽이 판정한다 (503 등)
        raise last

    @staticmethod
    def read_response(s):
        """헤더 + Content-Length 만큼의 몸을 읽는다."""
        buf = b""
        while b"\r\n\r\n" not in buf:
            c = s.recv(65536)
            if not c:
                return buf
            buf += c
        head, _, body = buf.partition(b"\r\n\r\n")
        n = 0
        for ln in head.split(b"\r\n")[1:]:
            if ln.lower().startswith(b"content-length:"):
                n = int(ln.split(b":", 1)[1])
        while len(body) < n:
            c = s.recv(65536)
            if not c:
                break
            body += c
        return head + b"\r\n\r\n" + body


class TestKeepAliveIdle(ConnBase):
    idle = 8.0        # 40연결을 여는 시간(WSL2 루프백)보다 넉넉해야 한다

    def test_test_keep_alive_idle(self):
        """TestKeepAliveIdle 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("s1_keepalive_still_reused"):
            s = self.conn()
            for i in range(5):
                r = self.get(s=s)
                self.assertTrue(r.startswith(b"HTTP/1.1 200"),
                                f"{i}번째 요청이 200 이 아니다: {r[:80]!r}")
            # 아직 살아 있어야 한다 (상한 전)
            r = self.get(s=s)
            self.assertTrue(r.startswith(b"HTTP/1.1 200"))
        with self.subTest("s3_keepalive_header_announces_limit"):
            s = self.opened()
            r = self.get(s=s)
            self.assertIn(b"Keep-Alive: timeout=", r.split(b"\r\n\r\n")[0],
                          "keep-alive 응답이 유휴 상한을 알리지 않는다")
        with self.subTest("s2_idle_connection_is_released"):
            s = self.conn(timeout=self.idle * 4)
            self.get(s=s)
            s.settimeout(self.idle * 4)
            # 서버가 닫으면 recv 가 b'' 로 돌아온다. 안 닫으면 여기서 타임아웃.
            try:
                left = s.recv(4096)
            except socket.timeout:
                self.fail(f"유휴 {self.idle * 4:.0f}초가 지나도 서버가 연결을 안 놓았다")
            self.assertEqual(left, b"", f"닫는 대신 뭘 보냈다: {left[:80]!r}")
        with self.subTest("s8_idle_connections_do_not_pile_up"):
            # 정점은 **여는 동안** 재야 한다 — 상한이 짧으면 마지막을 여는 사이
            # 첫 것이 이미 걷힌다(그것이 고쳐졌다는 뜻이기도 하다).
            socks, peak = [], 0
            for _ in range(40):
                socks.append(self.opened())
                peak = max(peak, self.threads())
            self.assertGreaterEqual(peak, self.base + 20,
                                    "40연결이 스레드를 안 만들었다 — 시험이 헛돈다")
            ok = _wait(lambda: self.threads() <= self.base + 5, self.idle * 4, 0.2)
            after = self.threads()
            for s in socks:
                s.close()
            self.assertTrue(ok, f"스레드가 안 걷혔다: 기저 {self.base} → 정점 "
                                f"{peak} → {self.idle * 4:.0f}초 뒤 {after}")

class TestSSELifetime(ConnBase):
    def _sse(self):
        s = self.conn(timeout=self.idle * 8)
        s.sendall(self.hdr("/api/stream/sse?session=nosuch") + b"\r\n")
        return s

    def test_s4_sse_is_not_measured_by_the_idle_ruler(self):
        """S4. 긴 연결과 폴링 연결을 같은 자로 재지 않는다.

        SSE 는 요청 하나가 오래 사는 것이지 노는 것이 아니다 — 유휴 상한의
        여러 배가 지나도 서버가 끊으면 안 된다(끊으면 대시보드가 죽는다).
        """
        sid = "sselive"
        os.makedirs(os.path.join(self.tmp, "streams"), exist_ok=True)
        with open(os.path.join(self.tmp, "streams", f"{sid}-0000.jsonl"),
                  "w", encoding="utf-8") as f:
            f.write("")
        s = self.conn(timeout=self.idle * 10)
        s.sendall(self.hdr(f"/api/stream/sse?session={sid}") + b"\r\n")
        head = b""
        while b"\r\n\r\n" not in head:
            head += s.recv(4096)
        self.assertIn(b"text/event-stream", head)
        # 유휴 상한의 여러 배 동안 붙어 있는다 — beat 가 오거나, 최소한
        # 서버가 끊지 않는다.
        deadline = time.time() + self.idle * 4
        s.settimeout(self.idle * 4 + 2)
        closed = False
        while time.time() < deadline:
            try:
                c = s.recv(4096)
            except socket.timeout:
                break
            if c == b"":
                closed = True
                break
        self.assertFalse(closed, f"SSE 가 유휴 상한({self.idle}s)에 걸려 끊겼다 — "
                                 "긴 연결을 폴링 자로 잰다")

    def test_s5_sse_reaped_when_client_vanishes(self):
        """S5. 상대가 사라진 SSE 는 만기(300초)를 기다리지 않고 걷힌다.

        고치기 전: 클라이언트가 닫아도 서버는 0.25초마다 스트림을 다시 읽으며
        300초를 살았다 — 좀비 140개가 8.7코어를 태운 그 경로다.
        """
        sid = "ssedead"
        os.makedirs(os.path.join(self.tmp, "streams"), exist_ok=True)
        with open(os.path.join(self.tmp, "streams", f"{sid}-0000.jsonl"),
                  "w", encoding="utf-8") as f:
            f.write("")
        base = self.threads()
        socks = []
        for _ in range(6):
            s = self.conn(timeout=10)
            s.sendall(self.hdr(f"/api/stream/sse?session={sid}") + b"\r\n")
            head = b""
            while b"\r\n\r\n" not in head:
                head += s.recv(4096)
            socks.append(s)
        self.assertTrue(_wait(lambda: self.threads() >= base + 5, 5, 0.1),
                        "SSE 6개가 스레드를 안 만들었다 — 시험이 헛돈다")
        peak = self.threads()
        for s in socks:
            s.close()
        ok = _wait(lambda: self.threads() <= base + 1, 8, 0.2)
        self.assertTrue(ok, f"상대가 사라진 SSE 가 안 걷혔다: {base} → "
                            f"{peak} → 8초 뒤 {self.threads()} "
                            "(300초 만기까지 CPU 를 태우는 그 결함)")


class TestServeBoots(unittest.TestCase):
    """S12. 감시 스위치를 다 끄고도 서버가 뜬다.

    실사고(REQ-20260901-020 구현 중): `cmd_serve` 안에 `import threading` 이
    **if 블록 안에** 두 번 있었다 — 그래서 `threading` 은 cmd_serve 의 조건부
    지역 이름이 되고, 그 안에 중첩된 클래스가 그 이름을 닫아 잡는다.
    두 스위치를 다 끄면(S9_REWORK_WATCH=off·S9_PORT_GUARD=off) 어느 쪽도 실행
    안 돼 `NameError: cannot access free variable 'threading'` 로 서버가 기동
    즉시 죽었다. 모듈 최상단에 이미 있는 import 를 함수 안에서 다시 하는 것이
    덫이었다 — 지웠고, 여기서 그 조합을 기계가 지킨다.
    """

    def test_s12_boots_with_every_watcher_off(self):
        import shutil
        tmp = tempfile.mkdtemp(prefix="s9boot-")
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {**os.environ, "S9_ROOT": tmp, "S9_USER": "boss",
               "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off"}
        env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=env, timeout=60)
        port = free_port()
        err = os.path.join(tmp, "e")
        srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(port)],
            env=env, stdout=subprocess.DEVNULL, stderr=open(err, "wb"))
        self.addCleanup(srv.kill)
        try:
            wait_server(port)
        except RuntimeError:
            self.fail("감시 스위치를 다 끄면 서버가 안 뜬다:\n"
                      + open(err, encoding="utf-8", errors="replace").read()[-1200:])


class TestSSEGeneration(ConnBase):
    """S11. 같은 세션의 새 스트림이 옛 스트림을 은퇴시킨다.

    WSL2 프록시 뒤에서는 브라우저가 EventSource 를 닫아도 FIN 이 서버까지
    오지 않는다 — 상대의 죽음을 못 보니 시간(5분 만기)만 남고, 그동안 스트림이
    쌓인다(실측 ESTAB 64). 그래서 세대를 신호로 쓴다: 새 스트림이 열리면
    같은 세션의 여유분 밖 옛 스트림은 스스로 물러난다.
    """
    idle = 30.0            # 유휴 걷힘이 세대 판정을 가리지 않게
    per_session = 2

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_s11_new_stream_retires_old_ones(self):
        sid = "ssegen"
        os.makedirs(os.path.join(self.tmp, "streams"), exist_ok=True)
        open(os.path.join(self.tmp, "streams", f"{sid}-0000.jsonl"),
             "w", encoding="utf-8").close()
        base = self.threads()
        socks = []
        for _ in range(8):
            s = self.conn(timeout=15)
            s.sendall(self.hdr(f"/api/stream/sse?session={sid}") + b"\r\n")
            head = b""
            while b"\r\n\r\n" not in head:
                head += s.recv(4096)
            self.assertIn(b"text/event-stream", head)
            socks.append(s)
        # 여유분(S9_SSE_PER_SESSION)만 남고 나머지는 스스로 물러나야 한다.
        ok = _wait(lambda: self.threads() <= base + self.per_session + 1,
                   8, 0.2)
        got = self.threads()
        for s in socks:
            s.close()
        self.assertTrue(ok, f"옛 스트림이 안 물러났다: 기저 {base} → {got} "
                            f"(여유 {self.per_session})")


class TestConnCap(ConnBase):
    idle = 60.0       # 유휴 걷힘이 상한 판정을 가리지 않게 넉넉히
    maxc = MAXC

    def test_s6_over_cap_answers_503(self):
        """S6. 넘치면 조용한 리셋이 아니라 답을 준다."""
        held = [self.opened() for _ in range(MAXC)]   # 점유한 채 유휴로 둔다
        # 상한을 넘긴 연결: 리셋(끊김)이 아니라 503 이어야 한다.
        s = self.conn(timeout=10)
        try:
            r = self.get(s=s)
        except (ConnectionResetError, socket.timeout) as e:
            self.fail(f"상한 초과가 조용히 끊겼다({e!r}) — 답을 줘야 한다")
        self.assertTrue(r.startswith(b"HTTP/1.1 503"),
                        f"상한 초과 응답이 503 이 아니다: {r[:100]!r}")
        head = r.split(b"\r\n\r\n")[0]
        self.assertIn(b"Retry-After:", head)
        self.assertIn(b"close", head.lower())
        for h in held:
            h.close()

    def test_s7_recovers_after_slots_free(self):
        """S7. 거절은 영구 고장이 아니다 — 자리가 나면 다시 200."""
        held = [self.opened() for _ in range(MAXC)]
        for s in held:
            s.close()
        ok = _wait(lambda: self._probe_ok(), self.idle * 4, 0.2)
        self.assertTrue(ok, "연결을 다 놓았는데도 새 연결이 200 을 못 받는다")

    def _probe_ok(self):
        try:
            s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        except OSError:
            return False
        try:
            s.sendall(self.hdr("/api/whoami") + b"Connection: close\r\n\r\n")
            return self.read_response(s).startswith(b"HTTP/1.1 200")
        except OSError:
            return False
        finally:
            s.close()


if __name__ == "__main__":
    if not sys.platform.startswith("linux"):
        print("linux 전용 (/proc 스레드 수 판정)")
        sys.exit(0)
    unittest.main(verbosity=2)
