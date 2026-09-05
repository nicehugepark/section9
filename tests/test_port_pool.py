"""테스트 네트워크 규율 테스트 — 고갈을 만들지 않는다 (REQ-20260825-100).

감지(`s9 doctor`)와 회수(`--recover`)는 불이 난 뒤에 쓰는 소화기다. 불씨는
우리가 여는 커넥션 수다 — 실측으로 리눅스 localhost 커넥션 30개가 윈도우
Bound 소켓 +30 을 만들었다(리스너를 새로 공개하는 건 +0~1, 윈도우에서
WSL 로 들어오는 요청은 +0). portpool 모듈 머리말에 측정표가 있다.

여기서 고정하는 것:
1) 서버 대기가 지수 백오프다 — 40초를 기다려도 시도는 30회 이하. 예전
   400회 루프는 호스트가 마르는 순간 고갈을 가속하는 되먹임이었다.
2) 풀이 윈도우 동적 범위·커널 임시 범위 **밖**에 있고, 몇 번을 할당하든
   서로 다른 포트 번호가 풀 크기를 넘지 않는다.
3) 소스 규율 — 임시 포트 직접 bind 금지, 촘촘한 재시도 루프 금지.
4) 사용자 대시보드 포트(9909~9950)를 테스트가 물지 않는다 — 물면 사람이 보는
   화면이 404 나 **옛 화면**으로 바뀐다(REQ-20260828-001).

실행: python3 tests/ port_pool
"""
import ast
import os
import re
import socket
import tempfile
import time
import textwrap
import unittest

import portpool

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- 연결을 여는 루프 (REQ-20260904-001) ----------
#
# 2026-09-04: 진단용으로 두었던 tests/test_long_lived_reset.py 가 전체 스위트에
# 끌려들어 **WSL 을 통째로 먹통으로** 만들었다. 잠 없는 `while` 을 120초 돌며
# 매 바퀴 연결 3개를 열었고(실측 초당 ~170) 윈도우 동적 포트 16,384개가 말랐다.
#
# 그때 아래 `test_no_tight_retry_loop` 가 이미 서 있었는데도 못 잡았다. 좁았던
# 축이 정확히 셋이다:
#   ① 루프 모양을 `for _ in range(N)` 하나만 알았다 — 시간으로 묶은 `while` 은 못 본다.
#   ② 연결을 `create_connection` 이라는 **글자**로만 셌다 — `socket().connect()` 는 못 본다.
#   ③ 연결이 헬퍼 함수 뒤에 있으면 루프 본문 글자에 안 보인다.
#
# 그래서 글자 대신 **나무(AST)** 를 본다. 세는 규칙 한 줄:
# **연결을 열 수 있는 루프는 잠을 재우거나(백오프) 작게 묶여 있어야 한다.**
#
# 일부러 좁게 둔 곳: `for x in <이름>` 은 크기를 알 수 없어 걸지 않는다. 이 사고의
# 해는 "끝을 모르는 반복"에서 왔고, 알 수 없는 것까지 걸면 오탐이 규율을 먼저 죽인다.

TIGHT = 50                      # 이 이상 두드리면 촘촘하다
CONNECT_CALLS = {"create_connection", "connect"}


def _calls(node):
    """이 나무 안에서 불리는 이름들 — `f()` 와 `x.f()` 를 함께."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                yield f.attr
            elif isinstance(f, ast.Name):
                yield f.id


def connecting_names(tree):
    """연결을 여는 함수 이름 전부 — 직접 여는 것에서 시작해 부르는 쪽으로 번진다.

    `one()` 안에서 connect 하고 루프는 `one()` 만 부르는 모양(실제 사고의 모양)을
    잡으려면 한 겹으로는 모자란다. 더 번지지 않을 때까지 돌린다.
    """
    funcs = {n.name: n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    hot = {name for name, fn in funcs.items()
           if CONNECT_CALLS & set(_calls(fn))}
    changed = True
    while changed:                              # 고정점까지
        changed = False
        for name, fn in funcs.items():
            if name in hot:
                continue
            if hot & set(_calls(fn)):
                hot.add(name)
                changed = True
    return hot


def _may_connect(loop, hot):
    return bool((CONNECT_CALLS | hot) & set(_calls(loop)))


def _paced(loop):
    """본문 어디서든 잠을 잔다 — except 안이어도 센다(대기 루프의 흔한 모양)."""
    return "sleep" in set(_calls(loop))


def _loop_cap(loop):
    """이 루프가 최대 몇 바퀴인가. 셀 수 없으면 None.

    `while` 은 언제나 None 이다 — 조건이 참인 동안이라는 말은 끝을 모른다는 뜻이다.
    """
    if not isinstance(loop, ast.For):
        return None
    it = loop.iter
    if (isinstance(it, ast.Call) and isinstance(it.func, ast.Name)
            and it.func.id == "range"):
        nums = [a.value for a in it.args
                if isinstance(a, ast.Constant) and isinstance(a.value, int)]
        if len(nums) != len(it.args) or not nums:
            return None
        return nums[0] if len(nums) == 1 else max(nums[1] - nums[0], 0)
    if isinstance(it, (ast.List, ast.Tuple, ast.Set)):
        return len(it.elts)
    return None


def connection_loop_offenders(src, name="<mem>"):
    """(파일:줄, 루프 모양) 목록 — 잠도 안 자고 끝도 모르는 연결 루프."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    hot = connecting_names(tree)
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, (ast.While, ast.For)):
            continue
        if not _may_connect(n, hot):
            continue
        cap = _loop_cap(n)
        if cap is not None and cap < TIGHT:
            continue                    # 몇 바퀴짜리는 고갈을 만들지 않는다
        if cap is None and _paced(n):
            continue                    # 끝은 몰라도 잠을 잔다면 백오프 대기다
        # 셀 수 있는데 촘촘하면 잠을 자도 offender 다 — 예전 「0.1초 간격 400회」가
        # 바로 그 모양이었고, 그때 고갈에 기름을 부은 것은 간격이 아니라 횟수였다.
        shape = "while" if isinstance(n, ast.While) else f"for x{cap}"
        out.append(f"{name}:{n.lineno} ({shape})")
    return out


class PoolRange(unittest.TestCase):
    def test_below_windows_dynamic_range(self):
        """풀 전체가 윈도우 동적 범위 아래여야 한다 — 여기가 마르면 망이 끊긴다."""
        ports = portpool.pool_ports()
        self.assertLess(max(ports), portpool.WIN_DYNAMIC_START,
                        "풀이 윈도우 동적 포트 범위를 침범한다")

    def test_outside_kernel_ephemeral_range(self):
        """커널이 아웃바운드 연결에 나눠주는 범위와 겹치면 무작위로 충돌한다."""
        lo, hi = portpool.ephemeral_range()
        ports = portpool.pool_ports()
        self.assertTrue(max(ports) < lo or min(ports) > hi,
                        f"풀 {min(ports)}~{max(ports)} 이 임시 범위 {lo}~{hi} 와 겹친다")

    def test_avoids_dashboard_ports(self):
        """대시보드 기본 포트와 그 스캔 대역(9909~9950)은 피한다."""
        ports = set(portpool.pool_ports())
        self.assertFalse(ports & set(range(9909, 9951)))


class ForeignListens(unittest.TestCase):
    """윈도우 중계가 붙든 낡은 공개는 풀에서 건너뛴다 (REQ-20260905-007).

    리눅스 쪽 bind 가 성공해도 그 포트로 오는 연결은 중계가 가로채 서버에
    닿지 않는다(2026-09-05 실측: 서버는 select 에서 놀고 대기열 0). 그러니 판정은
    bind 가 아니라 윈도우 쪽 LISTEN 목록이다.
    """
    NETSTAT = textwrap.dedent("""\
        \r
        Active Connections\r
        \r
          Proto  Local Address          Foreign Address        State\r
          TCP    0.0.0.0:135            0.0.0.0:0              LISTENING\r
          TCP    0.0.0.0:18812          0.0.0.0:0              LISTENING\r
          TCP    127.0.0.1:9909         127.0.0.1:52011        ESTABLISHED\r
          TCP    127.0.0.1:52011        127.0.0.1:9909         TIME_WAIT\r
          TCP    [::]:18813             [::]:0                 LISTENING\r
          TCP    [::1]:30000            [::]:0                 LISTENING\r
        """)

    def test_parse_windows_netstat(self):
        """LISTENING 줄의 로컬 포트만 — IPv6 꼬리도 같이, 연결·대기 줄은 제외."""
        self.assertEqual(portpool.parse_listen_ports(self.NETSTAT),
                         {135, 18812, 18813, 30000})
        self.assertEqual(portpool.parse_listen_ports(""), set())

    def test_foreign_port_is_deferred(self):
        """윈도우가 붙든 포트는 bind 가 돼도 — 안 붙든 포트가 남아 있는 한 — 나눠 주지 않는다."""
        ports = portpool.slot_ports()
        saved = portpool._foreign
        try:
            portpool._foreign = set(ports[:len(ports) // 2])
            got = {portpool.free_port() for _ in range(6)}
            self.assertFalse(got & portpool._foreign,
                             f"중계가 붙든 포트를 나눠 줬다: {got & portpool._foreign}")
            self.assertTrue(got <= set(ports))
        finally:
            portpool._foreign = saved

    def test_all_foreign_still_allocates(self):
        """칸 전체가 공개 중이어도 풀은 마르지 않는다 — 미루는 것이지 빼는 것이 아니다.

        실측 2026-09-06: 직전 실행의 32포트가 전부 아직 윈도우에 공개 중이었다.
        """
        ports = portpool.slot_ports()
        saved = portpool._foreign
        try:
            portpool._foreign = set(ports)
            self.assertIn(portpool.free_port(), set(ports))
        finally:
            portpool._foreign = saved

    def test_not_windows_means_nothing_changes(self):
        """netstat.exe 가 없는 판(리눅스·맥)에서는 빈 집합 — 풀은 그대로다."""
        saved_exe, saved = portpool.WIN_NETSTAT, portpool._foreign
        try:
            portpool.WIN_NETSTAT = "/nonexistent/netstat.exe"
            self.assertEqual(portpool.foreign_listens(refresh=True), set())
        finally:
            portpool.WIN_NETSTAT, portpool._foreign = saved_exe, saved


class BoundedReuse(unittest.TestCase):
    def test_distinct_ports_are_capped(self):
        """할당을 몇 번 하든 서로 다른 포트 수는 풀 크기 이하."""
        seen = {portpool.free_port() for _ in range(portpool.POOL_SIZE * 5)}
        self.assertLessEqual(len(seen), portpool.POOL_SIZE)
        self.assertTrue(seen <= set(portpool.pool_ports()))

    def test_repeated_runs_reuse_the_same_ports(self):
        """반복 할당은 같은 구간을 돌려쓴다 — 쓰는 포트 번호가 계속 늘지 않는다.

        (정확히 같은 집합을 요구하지는 않는다 — 다른 테스트의 서버가 잠깐
        한 칸을 쥐고 있으면 그 회차만 건너뛰기 때문이다. 고정하려는 성질은
        '구간 밖으로 새지 않는다'와 '총량이 슬롯 크기 이하다' 두 가지다.)
        """
        slot = set(portpool.slot_ports())
        first = {portpool.free_port() for _ in range(portpool.SLOT_SIZE * 2)}
        second = {portpool.free_port() for _ in range(portpool.SLOT_SIZE * 2)}
        self.assertTrue(first <= slot, first - slot)
        self.assertTrue(second <= slot, second - slot)
        self.assertLessEqual(len(first | second), portpool.SLOT_SIZE)

    def test_allocated_port_is_usable(self):
        """할당받은 자리에 **실서버와 같은 방식으로** 붙을 수 있다.

        SO_REUSEADDR 없이 붙으면 안 된다 — 풀은 TIME_WAIT 자리를 일부러
        '비어 있다'고 판정한다(_try_bind 의 근거: 실서버 HTTPServer 는
        allow_reuse_address 로 그 자리를 다시 잡는다). 여기서만 더 엄한
        기준으로 붙으면 스위트가 포트를 데울수록 이 시험이 붉어진다 —
        2026-09-04 전체 실행 네 번이 전부 이 자리에서 넘어졌다
        (Errno 98; 그때 18800 에 TIME_WAIT 27개, LISTEN 은 0개).
        """
        port = portpool.free_port()
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", port))
            srv.listen(1)
            socket.create_connection(("127.0.0.1", port), 3).close()
        finally:
            srv.close()

    def test_time_wait_port_is_still_allocatable(self):
        """요청을 처리하고 내려간 서버의 포트는 60초쯤 TIME_WAIT 로 남는다.

        그걸 '사용 중'으로 판정하면 방금 쓴 칸이 1분간 죽고 풀이 헛되이 마른다
        (실제로 test_whoami 가 '풀 소진'으로 깨졌다). 실서버(HTTPServer)는
        allow_reuse_address 로 그 포트를 다시 잡으므로 판정도 같아야 한다.
        """
        srv = portpool.pool_socket()
        port = srv.getsockname()[1]
        c = socket.create_connection(("127.0.0.1", port), 3)
        a, _peer = srv.accept()
        a.close()          # 서버가 먼저 닫는다 → 서버 쪽 포트가 TIME_WAIT
        c.close()
        srv.close()
        s = portpool._try_bind(port)
        self.assertIsNotNone(s, f"TIME_WAIT 인 {port} 를 다시 잡지 못한다")
        s.close()

    def test_pool_socket_holds_the_port(self):
        a = portpool.pool_socket()
        b = portpool.pool_socket()
        try:
            self.assertNotEqual(a.getsockname()[1], b.getsockname()[1])
        finally:
            a.close()
            b.close()

    def test_exhausted_pool_says_what_to_do(self):
        """다 찼으면 임시 포트로 몰래 도망가지 말고 회수를 안내하며 실패한다."""
        base = portpool.free_port()          # 지금 비어 있는 한 칸
        held = portpool.pool_socket(base=base, size=1)
        try:
            with self.assertRaises(RuntimeError) as cm:
                portpool.free_port(base=base, size=1)
            self.assertIn("doctor", str(cm.exception))
        finally:
            held.close()


class WaitBackoff(unittest.TestCase):
    """서버 대기는 '시도 횟수'가 비용이다 — 커넥션 1개 = 호스트 동적 포트 1개."""

    def test_gives_up_after_few_attempts(self):
        """40초를 기다리더라도 두드리는 횟수는 30회 이하 — 예전엔 400회였다."""
        calls = []

        def never():
            calls.append(1)
            raise OSError("refused")

        t0 = time.monotonic()
        with self.assertRaises(RuntimeError):
            portpool.wait_server(1, timeout=3.0, _connect=never)
        elapsed = time.monotonic() - t0
        self.assertGreaterEqual(elapsed, 2.9)      # 대기 시간은 줄이지 않는다
        self.assertLessEqual(len(calls), 12, f"{len(calls)}회 시도 — 너무 자주 두드린다")

    def test_full_timeout_stays_under_thirty_attempts(self):
        """기본 40초 대기의 시도 횟수 상한(수식으로 계산 — 실제로 기다리지 않는다)."""
        n, t, delay = 0, 0.0, portpool.WAIT_FIRST
        while t < portpool.WAIT_TIMEOUT:
            n += 1
            t += delay
            delay = min(delay * portpool.WAIT_GROWTH, portpool.WAIT_MAX)
        self.assertLessEqual(n, 30)

    def test_returns_attempt_count_on_success(self):
        seq = [OSError, OSError, None]

        def flaky():
            x = seq.pop(0)
            if x:
                raise x("refused")

        self.assertEqual(portpool.wait_server(1, timeout=5, _connect=flaky), 3)

    def test_http_server_answers_on_first_try(self):
        """진짜 HTTP 서버는 첫 시도에 준비됨으로 잡힌다."""
        import http.server
        import threading
        s = portpool.pool_socket()
        port = s.getsockname()[1]
        s.close()
        srv = http.server.HTTPServer(
            ("127.0.0.1", port), http.server.SimpleHTTPRequestHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            # **몇 번째에 잡히느냐는 이 시험의 계약이 아니다** (REQ-20260904-003).
            # 여기서 재는 것은 「응답하는 진짜 서버는 준비됨으로 잡힌다」이고,
            # 그 반대쪽(듣기만 하는 소켓은 준비됨이 아니다)은 바로 아래 시험이
            # 맡는다. 시도 횟수의 상한은 `test_full_timeout_stays_under_thirty_
            # attempts` 가 따로 못박는다.
            #
            # `== 1` 은 「이 기계가 첫 시도 안에 뜬다」를 함께 재고 있었다 —
            # 부하가 걸린 병렬 실행에서 5가 나와 붉었다(실측 2026-09-04).
            n = portpool.wait_server(port, timeout=10)
            self.assertGreaterEqual(n, 1)
            self.assertLessEqual(n, 30, "백오프 예산을 넘겨 잡혔다")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_bare_listener_is_not_ready(self):
        """**연결됨 ≠ 준비됨.** 듣기만 하고 응답하지 않는 소켓은 준비된 게 아니다.

        WSL virtioproxy 는 리스너가 없어도 connect 를 받아준다 — connect 만으로
        판정하면 서버가 뜨기 전에 통과하고, 뒤이은 요청이 ConnectionReset 으로
        깨진다. 아무 응답도 주지 않는 리스너로 그 판정을 재현한다."""
        s = portpool.pool_socket()
        try:
            with self.assertRaises(RuntimeError):
                portpool.wait_server(s.getsockname()[1], timeout=3)
        finally:
            s.close()


class NoEphemeralBind(unittest.TestCase):
    """테스트가 임시 포트를 직접 뽑는 습관으로 돌아가지 못하게 막는다."""

    EPHEMERAL_BIND = re.compile(r"\.bind\(\(\s*[\"'][^\"']*[\"']\s*,\s*0\s*\)\)")

    def test_no_test_file_binds_an_ephemeral_port(self):
        offenders = []
        for name in sorted(os.listdir(HERE)):
            if not name.startswith("test_") or not name.endswith(".py"):
                continue
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if self.EPHEMERAL_BIND.search(line):
                        offenders.append(f"{name}:{i}")
        self.assertEqual(offenders, [], "portpool.free_port() 를 써라 — "
                         "임시 포트 bind 는 윈도우 동적 포트를 영구히 소모한다: "
                         + ", ".join(offenders))

    def test_no_tight_retry_loop(self):
        """서버 기동을 촘촘히 두드리는 루프 금지 — 고갈 중일 때 고갈을 가속한다."""
        offenders = []
        for name in sorted(os.listdir(HERE)):
            if not name.startswith("test_") or not name.endswith(".py"):
                continue
            src = open(os.path.join(HERE, name), encoding="utf-8").read()
            for m in re.finditer(r"for\s+\w+\s+in\s+range\((\d+)\)", src):
                if int(m.group(1)) >= 50 and "create_connection" in src:
                    offenders.append(f"{name}:range({m.group(1)})")
        self.assertEqual(offenders, [], "wait_server() 를 써라 — "
                         "연결 시도 1회가 호스트 동적 포트 1개다: " + ", ".join(offenders))

    def test_no_unpaced_connection_loop(self):
        """잠도 안 자고 끝도 모르는 연결 루프 금지 (REQ-20260904-001).

        `for range(N)` 만 보던 위 시험이 놓친 자리다 — 시간으로 묶은 `while`,
        `socket().connect()`, 헬퍼 뒤에 숨은 연결 셋 다 여기서 걸린다.
        """
        offenders = []
        for name in sorted(os.listdir(HERE)):
            if not name.startswith("test_") or not name.endswith(".py"):
                continue
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                offenders += connection_loop_offenders(f.read(), name)
        self.assertEqual(
            offenders, [],
            "연결을 여는 루프는 wait_server() 처럼 잠을 재우거나 작게 묶어라 — "
            "커넥션 1개가 호스트 동적 포트 1개이고, 마르면 WSL 이 먹통이 된다"
            "(REQ-20260904-001 실측: 잠 없는 while 120초 = 2만 커넥션 > 16,384): "
            + ", ".join(offenders))

    def test_server_tests_use_the_pool(self):
        """서버를 띄우는 테스트는 풀에서 포트를 받아야 한다."""
        missing = []
        for name in sorted(os.listdir(HERE)):
            if not name.startswith("test_") or not name.endswith(".py"):
                continue
            src = open(os.path.join(HERE, name), encoding="utf-8").read()
            if "free_port(" not in src and "pool_socket(" not in src:
                continue
            if "import portpool" not in src and "from portpool import" not in src:
                missing.append(name)
        self.assertEqual(missing, [])


class StrayDashboardServers(unittest.TestCase):
    """테스트가 **사용자 대시보드 포트**를 물지 않는다 (REQ-20260828-001).

    2026-08-28: 스위트가 끝난 뒤에도 `/tmp/s9smx-*` 작업공간의 `s9 serve` 가
    9909 를 물고 살아남았다. 진짜 서버와 번갈아 응답해 새로고침마다 404 가
    났고, 더 나쁘게는 **테스트 시작 시점의 옛 web/index.html** 을 내줘 화면을
    고치고 눈으로 확인하는 절차를 조용히 통과시켰다.
    """

    REPO = os.path.dirname(HERE)
    TMP = tempfile.gettempdir()

    def proc(self, **kw):
        base = {"pid": 4242, "argv": ["/repo/bin/s9", "serve", "--port", "9909"],
                "cwd": "", "root": ""}
        base.update(kw)
        return base

    # ---------- 무엇을 거두고 무엇을 남기는가 ----------

    def test_temp_workspace_on_dashboard_port_is_stray(self):
        p = self.proc(root=os.path.join(self.TMP, "s9smx-abcd"))
        self.assertTrue(portpool.is_stray_dashboard_server(p))

    def test_cwd_alone_is_enough_to_recognize(self):
        """S9_ROOT 를 못 읽어도 작업 디렉토리로 알아본다 — 사람이 쓴 방법과 같다."""
        p = self.proc(cwd=os.path.join(self.TMP, "s9smx-abcd"))
        self.assertTrue(portpool.is_stray_dashboard_server(p))

    def test_real_server_is_never_touched(self):
        """진짜 서버(작업공간=저장소)는 절대 회수 대상이 아니다."""
        p = self.proc(cwd=self.REPO, root=self.REPO)
        self.assertFalse(portpool.is_stray_dashboard_server(p))

    def test_pool_port_test_server_is_left_alone(self):
        """풀 포트를 쓰는 정상적인 테스트 서버는 남의 몫이다(s9-doctor --sweep).

        여기서 거두면 **동시에 도는 다른 스위트**의 서버를 죽인다.
        """
        p = self.proc(argv=["/repo/bin/s9", "serve", "--port",
                            str(portpool.POOL_BASE)],
                      root=os.path.join(self.TMP, "s9guardp-x"))
        self.assertFalse(portpool.is_stray_dashboard_server(p))

    def test_scan_band_counts_too(self):
        """9909 하나가 아니라 스캔 대역 전체가 사용자 자리다."""
        p = self.proc(argv=["/repo/bin/s9", "serve", "--port", "9931"],
                      root=os.path.join(self.TMP, "s9smx-abcd"))
        self.assertTrue(portpool.is_stray_dashboard_server(p))

    def test_other_programs_are_not_ours(self):
        p = self.proc(argv=["python3", "-m", "http.server", "--port", "9909"],
                      root=os.path.join(self.TMP, "x"))
        self.assertFalse(portpool.is_stray_dashboard_server(p))

    def test_port_flag_forms(self):
        self.assertEqual(portpool._argv_port(["s9", "serve", "--port=9909"]), 9909)
        self.assertEqual(portpool._argv_port(["s9", "serve", "--port", "9909"]), 9909)
        self.assertIsNone(portpool._argv_port(["s9", "serve"]))

    # ---------- 거두는 방식 ----------

    def test_guard_dies_before_its_child(self):
        """감시자를 먼저 죽여야 한다 — 자식만 죽이면 곧바로 되살아난다."""
        tmp = os.path.join(self.TMP, "s9smx-abcd")
        child = self.proc(pid=101, root=tmp)
        guard = self.proc(pid=100, root=tmp,
                          argv=["/repo/bin/s9", "serve", "--supervise",
                                "--port", "9909"])
        killed = []
        rounds = [[child, guard], []]
        portpool.reap_stray_dashboard_servers(
            snapshot=lambda: rounds.pop(0) if rounds else [],
            kill=lambda pid, sig: killed.append(pid),
            sleep=lambda _s: None)
        self.assertEqual(killed, [100, 101])

    def test_reap_retries_until_gone(self):
        """한 바퀴로 안 죽으면 다시 본다 — 되살아난 자식을 놓치지 않는다."""
        tmp = os.path.join(self.TMP, "s9smx-abcd")
        alive = [[self.proc(pid=1)], [self.proc(pid=2)], []]
        for p in (alive[0][0], alive[1][0]):
            p["root"] = tmp
        killed = []
        reaped = portpool.reap_stray_dashboard_servers(
            snapshot=lambda: alive.pop(0) if alive else [],
            kill=lambda pid, sig: killed.append(pid),
            sleep=lambda _s: None)
        self.assertEqual(killed, [1, 2])
        self.assertEqual([p["pid"] for p in reaped], [1, 2])

    def test_nothing_to_reap_is_silent(self):
        self.assertEqual(portpool.reap_stray_dashboard_servers(
            snapshot=lambda: [], kill=None, sleep=lambda _s: None), [])

    def test_runner_reaps_and_fails(self):
        """러너가 회수를 부르고, 남은 게 있으면 실패로 센다 — 조용히 치우면
        다음 실행에서 또 생긴다."""
        src = open(os.path.join(HERE, "__main__.py"), encoding="utf-8").read()
        self.assertIn("reap_stray_dashboard_servers", src,
                      "러너가 스위트 뒤에 포트를 거두지 않는다")
        self.assertIn("return 1", src.split("leaked")[-1][:400],
                      "포트를 뺏은 채 끝났는데 성공으로 끝난다")

    # ---------- 소스 규율 ----------

    HOOK_RUN = re.compile(
        r"(?:run|Popen)\(\s*\[[^\]]*(?:SESSION_HOOK|\bHOOK\b|hook|"
        r"\"s9-audit-session\")", re.S)

    def test_session_hook_tests_isolate_the_port(self):
        """세션 훅을 돌리는 테스트는 S9_PORT 로 격리해야 한다.

        훅의 `ensure_serve()` 는 S9_PORT 가 없으면 `state/port` → 9909 로
        떨어진다. 임시 작업공간에는 그 파일이 없으니 **사용자 포트**에
        감시자를 세운다. 이 검사가 없으면 다음 테스트가 같은 자리에 빠진다.
        """
        offenders = []
        for name in sorted(os.listdir(HERE)):
            if not name.startswith("test_") or not name.endswith(".py"):
                continue
            src = open(os.path.join(HERE, name), encoding="utf-8").read()
            if "s9-audit-session" not in src:
                continue
            if not self.HOOK_RUN.search(src):
                continue          # 소스만 읽는 테스트 — 훅을 돌리지 않는다
            # 주석에 이름만 적어 두는 것으로는 격리가 되지 않는다 —
            # env 에 실제로 들어간 형태(따옴표로 감싼 키)를 본다.
            if not re.search(r"[\"']S9_PORT[\"']", src):
                offenders.append(name)
        self.assertEqual(offenders, [],
                         "세션 훅을 돌리면서 포트를 격리하지 않는다 — "
                         "S9_PORT='1' 을 env 에 넣어라: " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()


class ConnectionLoopGate(unittest.TestCase):
    """게이트 자신을 못박는다 (REQ-20260904-001).

    소스를 훑는 게이트는 조용히 좁아진다 — 2026-09-04 사고가 그랬다. 무엇을
    잡고 무엇을 놓아주는지를 여기서 값으로 고정한다.
    """

    def off(self, src):
        return connection_loop_offenders(textwrap.dedent(src), "t.py")

    # ---------- 잡아야 하는 것 ----------

    def test_f1_time_bounded_while_is_caught(self):
        """시간으로만 묶은 while — 실제 사고의 모양."""
        self.assertTrue(self.off("""
            def probe(port):
                end = time.monotonic() + 120
                while time.monotonic() < end:
                    socket.create_connection(("127.0.0.1", port)).close()
        """))

    def test_f2_connection_behind_a_helper_is_caught(self):
        """루프 본문에는 `one()` 밖에 없다 — 글자만 보면 안 보인다."""
        self.assertTrue(self.off("""
            def one(port):
                s = socket.socket()
                s.connect(("127.0.0.1", port))
                s.close()

            def probe(port):
                while True:
                    one(port)
        """))

    def test_f3_socket_connect_counts_as_a_connection(self):
        """create_connection 만 연결인 게 아니다."""
        self.assertTrue(self.off("""
            def probe(port):
                while True:
                    s = socket.socket()
                    s.connect(("127.0.0.1", port))
        """))

    def test_f4_message_names_the_file_line_and_the_shape(self):
        got = self.off("""
            def probe(port):
                while True:
                    socket.create_connection(("127.0.0.1", port))
        """)
        self.assertEqual(len(got), 1)
        self.assertIn("t.py:", got[0])
        self.assertIn("while", got[0])

    def test_r1_the_old_tight_range_shape_still_falls(self):
        """앞 시험이 잡던 모양을 새 문도 잡는다 — 좁아지지 않았다."""
        # 옛 글자 게이트가 이 파일의 **예시**까지 범인으로 세지 않도록
        # 리터럴 `range(400)` 을 소스에 남기지 않는다.
        self.assertTrue(self.off("""
            def probe(port):
                for _ in range(%d):
                    socket.create_connection(("127.0.0.1", port)).close()
        """ % 400))

    # ---------- 놓아줘야 하는 것 (오탐 0) ----------

    def test_b1_a_waiting_loop_that_sleeps_passes(self):
        """test_live_signal.py 의 실제 모양 — 잠을 자고 성공하면 나간다."""
        self.assertEqual(self.off("""
            def ready(addr):
                deadline = time.time() + 20
                while True:
                    try:
                        socket.create_connection(addr, 0.5).close()
                        break
                    except OSError:
                        if time.time() > deadline:
                            raise
                        time.sleep(0.25)
        """), [])

    def test_b2_backoff_helper_passes(self):
        """portpool.wait_server 의 모양 — 잠이 점점 길어진다."""
        self.assertEqual(self.off("""
            def wait(port):
                delay = 0.02
                while time.monotonic() < end:
                    try:
                        probe(port)
                        return
                    except OSError:
                        time.sleep(delay)
                        delay *= 1.6
        """), [])

    def test_b3_a_small_bounded_loop_passes(self):
        """몇 개짜리 리터럴·range 는 고갈을 만들지 않는다."""
        self.assertEqual(self.off("""
            def check(port):
                for path in ("/a", "/b", "/c"):
                    socket.create_connection(("127.0.0.1", port)).close()
                for _ in range(3):
                    socket.create_connection(("127.0.0.1", port)).close()
        """), [])

    def test_b4_a_loop_that_never_connects_passes(self):
        self.assertEqual(self.off("""
            def count(rows):
                while True:
                    rows.pop()
        """), [])


class UrlopenRetryIsInstalledOnce(unittest.TestCase):
    """되걸기는 한 자리에 있고, 서버가 준 답은 되걸지 않는다 (REQ-20260904-003).

    2026-09-04 하루에 네 파일이 차례로 같은 모양으로 넘어졌다 — 되걸기가
    POST 에만 있거나 아예 없어서다. 파일마다 고치면 실행마다 희생자가 바뀐다.
    """

    def setUp(self):
        import urllib.request
        self._real = urllib.request.urlopen
        portpool._URLOPEN_WRAPPED = False

    def tearDown(self):
        import urllib.request
        urllib.request.urlopen = self._real
        portpool._URLOPEN_WRAPPED = False

    def test_a_reset_is_retried(self):
        import urllib.request
        calls = []

        def flaky(*a, **kw):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionResetError("붙자마자 끊겼다")
            return "ok"

        urllib.request.urlopen = flaky
        portpool.install_urlopen_retry(tries=3, pause=0)
        self.assertEqual(urllib.request.urlopen(), "ok")
        self.assertEqual(len(calls), 3)

    def test_an_http_answer_is_not_retried(self):
        """404 는 서버가 준 답이다 — 다시 걸면 시험이 보려던 것을 늦출 뿐이다."""
        import urllib.error
        import urllib.request
        calls = []

        def answered(*a, **kw):
            calls.append(1)
            raise urllib.error.HTTPError("u", 404, "no", {}, None)

        urllib.request.urlopen = answered
        portpool.install_urlopen_retry(tries=3, pause=0)
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen()
        self.assertEqual(len(calls), 1, "서버가 준 답을 되걸었다")

    def test_a_dead_server_still_raises(self):
        """정말 없으면 세 번 뒤 같은 예외가 오른다 — 판정은 안 바뀐다."""
        import urllib.request
        calls = []

        def dead(*a, **kw):
            calls.append(1)
            raise ConnectionRefusedError("아무도 없다")

        urllib.request.urlopen = dead
        portpool.install_urlopen_retry(tries=3, pause=0)
        with self.assertRaises(ConnectionRefusedError):
            urllib.request.urlopen()
        self.assertEqual(len(calls), 3)

    def test_installing_twice_does_not_stack(self):
        """두 번 입히면 되걸기가 겹쳐 9번이 된다 — 한 번만 입는다."""
        import urllib.request
        calls = []

        def dead(*a, **kw):
            calls.append(1)
            raise ConnectionRefusedError("아무도 없다")

        urllib.request.urlopen = dead
        portpool.install_urlopen_retry(tries=3, pause=0)
        portpool.install_urlopen_retry(tries=3, pause=0)
        with self.assertRaises(ConnectionRefusedError):
            urllib.request.urlopen()
        self.assertEqual(len(calls), 3, f"되걸기가 겹쳤다 ({len(calls)}회)")
