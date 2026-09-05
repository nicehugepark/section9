"""테스트의 네트워크 규율 — 호스트 동적 포트 고갈을 만들지 않는다 (REQ-20260825-100).

## 무엇이 실제로 포트를 먹는가 (2026-08-26 실측, 이 머신 / WSL virtioproxy)

`s9 doctor` 가 세는 윈도우 Bound 소켓을 기준으로 하나씩 갈라 재봤다.

| 행동                                   | Bound 증가 |
|----------------------------------------|-----------|
| 리눅스에서 localhost 로 TCP 연결 30개  | **+30** (3회 재현) |
| 리스너 10개를 2초씩 공개(포트 새로 씀) | +1        |
| 순간 bind/listen/close 200회           | +0        |
| 윈도우(curl.exe) → WSL 짧은 요청 30개  | +0        |
| WSL → 외부 인터넷 연결 50개            | +0        |
| 아무것도 안 함 30~90초                 | -13 ~ +13 |

(오래 붙들고 있는 연결 — 대시보드 SSE, 고아 헤드리스 브라우저 — 은 이 표와
다른 경로다. 그쪽은 REQ-20260826-002 에서 다룬다.)

즉 **비용은 포트 번호가 아니라 "우리가 여는 localhost 커넥션 수"** 다.
커넥션 하나당 WSL 중계(DllHost COM 대리)가 윈도우 동적 포트 하나를 잡는다.
측정 시점의 점유도 그 모습이었다 — Bound 555개 중 541개가 그 중계 프로세스,
전부 동적 범위(49152~)의 서로 다른 포트. 다만 영구 누수는 아니다: 몇 분 뒤
수백 개가 한꺼번에 반환되는 것도 관측했다. 여는 속도가 반환 속도를 오래
넘어서면 16,384개가 마르고, 그때 나오는 게 2026-08-25 사고다(96% 점유,
브라우저 ERR_NO_BUFFER_SPACE, 테스트 29건 connection refused).

## 그래서 규율 두 가지

1. **두드리는 횟수를 아낀다** — `wait_server()` 의 지수 백오프. 예전 대기
   루프는 0.1초 간격 400회였다. 호스트가 말라 공개가 늦어지는 바로 그때
   파일마다 400회씩 두드려 고갈을 가속했다(스위트 14파일 = 최대 5,600
   커넥션). 고장이 부하를 키우는 되먹임을 끊는 것이 첫째다.
2. **포트는 고정 풀에서 돌려쓴다** — 윈도우 동적 범위(49152~)와 커널 임시
   범위(32768~) **아래**의 128개(18800~18927). 리스너를 동적 범위 안에 두면
   중계가 쓰려던 포트와 부딪히고, 임시 범위 안에 두면 남의 아웃바운드 연결과
   부딪힌다. 번호가 예측 가능해야 고아 서버 회수도 쉽다.

두 규율 모두 tests/test_port_pool.py 가 강제한다(범위 검사 · 임시 포트 직접
bind 적발 · 촘촘한 재시도 루프 적발).

사용:
    from portpool import free_port          # 포트 번호만 필요할 때
    from portpool import pool_socket        # 포트를 잡은 채 넘겨야 할 때
    from portpool import wait_server        # 서버가 뜰 때까지 (백오프)
"""
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

try:
    import fcntl
except ImportError:      # 윈도우 — 슬롯 잠금 없이 pid 로만 나눈다
    fcntl = None

# 18800~18927 — 윈도우 동적 범위(49152~65535)와 커널 임시 범위(32768~60999)
# 양쪽 모두의 아래. 대시보드 기본 포트(9909)와 그 스캔 대역(9910~9950)도 피한다.
POOL_BASE = int(os.environ.get("S9_TEST_PORT_BASE", "18800"))

# 스위트가 동시에 여러 개 돌 수 있다(무인 감사 세션 병렬) — 풀을 슬롯으로 갈라
# 프로세스마다 다른 구간을 쓰게 한다. 같은 포트를 동시에 노려 서로 밀어내는
# 사고(테스트가 서버를 띄우기 직전에 남이 채감)를 구조적으로 없앤다.
#
# **칸 수는 샤드 수를 따라간다** (REQ-20260905-001). 4 로 못박혀 있었는데,
# 그것이 곧 병렬의 천장이었다 — 다섯째 샤드부터는 자기 칸이 없어 pid 로 나눠
# 쓰며 같은 포트를 두고 다툰다. 실측 2026-09-05: 4·6·10 샤드가 각각 525·518·
# 520초로 **평평했다**. 코어는 83% 놀고 있었다. 칸을 맞춘 뒤 6→343 · 8→317 ·
# 10→295초 — 그래서 상한 표(S9_MAX_JOBS)의 기본도 4 에서 8 로 올렸다. 러너가 `--jobs` 를 그대로
# 넘겨주고, 칸마다 32포트를 유지하도록 풀 폭도 함께 넓힌다(18800~ 대역은
# 커널 임시 범위 32768 아래라 여유가 크다).
POOL_SLOTS = max(1, int(os.environ.get("S9_TEST_PORT_SLOTS", "4")))
# 풀의 꼭대기 — bin/s9-doctor 의 POOL_HI 와 같은 값이어야 한다. 회수는 그 대역
# 안에서만 도니, 풀이 그 위로 자라면 거기 남은 서버·감시자는 아무도 거두지
# 않는다 (실사고 2026-09-05, REQ-20260905-005: 칸 8 → 19056 까지 자라 19089 의
# 감시자 둘이 남았다). 프로브 자리(19990~)도 그 위다. 칸이 많아 꼭대기를 넘으면
# 칸을 좁히지 않고 풀을 접는다 — 칸마다 8포트는 남는다.
POOL_TOP = 19989
POOL_SIZE = int(os.environ.get("S9_TEST_PORT_SIZE", str(max(128, POOL_SLOTS * 32))))
POOL_SIZE = min(POOL_SIZE, POOL_TOP + 1 - POOL_BASE)
SLOT_SIZE = max(8, POOL_SIZE // POOL_SLOTS)
LOCK_DIR = os.path.join(tempfile.gettempdir(), "s9-portpool")

WIN_DYNAMIC_START = 49152          # 윈도우 기본 동적 포트 시작
EPHEMERAL_FALLBACK = (32768, 60999)  # /proc 을 못 읽을 때의 리눅스 기본값

# 사람이 보는 대시보드가 사는 대역(기본 9909 + 스캔 9910~9950). 테스트는 이
# 대역에 **절대** 서버를 띄우지 않는다 — 띄우면 사용자 화면을 뺏는다.
DASHBOARD_PORT = 9909
DASHBOARD_PORTS = range(9909, 9951)

_lock = threading.Lock()
_slot = None        # 이 프로세스가 잡은 슬롯 번호
_slot_fd = None     # 프로세스가 살아 있는 동안 유지되는 잠금 fd
_cursor = 0


def ephemeral_range():
    """커널 임시 포트 범위 (lo, hi). 읽을 수 없으면 리눅스 기본값."""
    try:
        with open("/proc/sys/net/ipv4/ip_local_port_range") as f:
            lo, hi = f.read().split()[:2]
        return int(lo), int(hi)
    except (OSError, ValueError):
        return EPHEMERAL_FALLBACK


def pool_ports(base=None, size=None):
    base = POOL_BASE if base is None else base
    size = POOL_SIZE if size is None else size
    return [base + i for i in range(size)]


def _claim_slot():
    """이 프로세스 몫의 슬롯을 잡는다 — 다른 스위트와 포트 구간이 겹치지 않게.

    슬롯 파일에 flock 을 걸고 프로세스가 끝날 때까지 들고 있는다. 슬롯이
    전부 차 있으면(스위트 5개 이상 동시 실행) pid 로 나눠 공유한다 — 그때도
    bind 확인이 있으니 실패가 아니라 경합만 조금 늘어난다.
    """
    global _slot, _slot_fd
    if _slot is not None:
        return _slot
    order = [(os.getpid() + i) % POOL_SLOTS for i in range(POOL_SLOTS)]
    if fcntl is not None:
        try:
            os.makedirs(LOCK_DIR, exist_ok=True)
            for cand in order:
                fd = os.open(os.path.join(LOCK_DIR, f"slot{cand}.lock"),
                             os.O_CREAT | os.O_RDWR, 0o644)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    os.close(fd)
                    continue
                _slot, _slot_fd = cand, fd
                return _slot
        except OSError:
            pass
    _slot = order[0]
    return _slot


def slot_ports():
    """이 프로세스가 쓸 포트 구간."""
    slot = _claim_slot()
    return [POOL_BASE + slot * SLOT_SIZE + i for i in range(SLOT_SIZE)]


def _reclaim_orphans():
    """주인 잃은 테스트 서버 회수 — 판단·실행은 bin/s9-doctor 한 곳에만 둔다."""
    tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "bin", "s9-doctor")
    if not os.path.exists(tool):
        return
    try:
        subprocess.run([sys.executable, tool, "--sweep", "--json"],
                       capture_output=True, timeout=90)
        time.sleep(0.5)          # SIGTERM 이 실제로 포트를 놓을 틈
    except Exception:
        pass


def _try_bind(port):
    """실제로 잡을 수 있는 포트인지 확인 — 잡히면 bind+listen 된 소켓을 준다.

    SO_REUSEADDR 를 쓰는 이유: 테스트 서버가 요청을 처리하고 내려가면 그
    리스닝 포트가 TIME_WAIT 로 60초쯤 남는다. 실제 서버(HTTPServer)는
    allow_reuse_address 로 그 포트를 다시 잡으므로, 판정도 같은 기준이어야
    한다. 아니면 방금 쓴 포트가 1분간 '사용 중'으로 보여 풀이 헛되이 마른다.
    """
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(8)
        return s
    except OSError:
        s.close()
        return None


def pool_socket(base=None, size=None):
    """풀에서 하나를 잡아 bind+listen 상태의 소켓으로 돌려준다.

    포트를 놓지 않고 그대로 넘겨야 하는 테스트(가짜 서버 등)용. 닫는 책임은
    호출자에게 있다.
    """
    global _cursor
    ports = slot_ports() if base is None and size is None else pool_ports(base, size)
    n = len(ports)

    def _grab():
        global _cursor
        with _lock:
            start = _cursor % n
            for i in range(n):
                s = _try_bind(ports[(start + i) % n])
                if s is not None:
                    _cursor = (start + i + 1) % n
                    return s
        return None

    s = _grab()
    if s is not None:
        return s
    # 풀이 다 찼다면 십중팔구 주인 잃은 서버가 칸을 물고 있는 것이다 —
    # 사람에게 회수를 안내하고 실패하는 대신 **먼저 회수하고 다시 시도한다**.
    # 안내만 하면 그 스위트는 어차피 깨지고, 다음 실행도 같은 자리에서 깨진다.
    _reclaim_orphans()
    s = _grab()
    if s is not None:
        return s
    raise RuntimeError(
        f"테스트 포트 풀 소진: {ports[0]}~{ports[-1]} {n}개가 모두 사용 중이다. "
        "회수를 시도했는데도 비지 않았다 — 살아 있는 서버가 실제로 그만큼 "
        "있다는 뜻이다. `s9 doctor` 로 확인하라.")


def free_port(base=None, size=None):
    """풀에서 지금 비어 있는 포트 번호 하나. 곧 서버가 잡을 것이라고 가정한다."""
    s = pool_socket(base, size)
    try:
        return s.getsockname()[1]
    finally:
        s.close()


# 대기 파라미터 — 40초까지 기다리되 두드리는 횟수는 30회 이하로 (백오프).
WAIT_TIMEOUT = 40.0
WAIT_FIRST = 0.05
WAIT_MAX = 2.0
WAIT_GROWTH = 1.7


def wait_server(port, host="127.0.0.1", timeout=WAIT_TIMEOUT, _connect=None):
    """서버가 뜰 때까지 기다린다 — 지수 백오프로 **연결 시도 횟수**를 아낀다.

    왜 횟수가 비용인가: 실측(2026-08-26) 결과 WSL 안에서 localhost 로 여는 TCP
    커넥션 하나가 윈도우 중계(DllHost)의 동적 포트 하나를 잡는다 — 30개 연결에
    Bound +30 이 재현됐다. 반면 리스닝 포트를 새로 공개하는 것(+0~1)이나 윈도우
    브라우저에서 WSL 로 들어오는 요청(+0)은 거의 비용이 없었다. 즉 고갈을
    만드는 것은 포트 번호가 아니라 **우리가 여는 커넥션 수**다.

    예전 대기 루프는 0.1초 간격 400회였다. 평시엔 두세 번에 끝나지만, 호스트가
    말라 공개가 늦어지는 바로 그 순간에는 파일마다 400회씩 두드린다 — 스위트
    14개 파일이면 최대 5,600 커넥션이 고갈에 기름을 붓는다. 고장이 부하를 키우는
    되먹임을 끊으려고 백오프로 바꿨다(40초 대기 시 30회 이하).

    반환: 성공까지 걸린 시도 횟수. 실패하면 RuntimeError.
    """
    def _default():
        # **연결됨 ≠ 준비됨.** WSL virtioproxy 에서는 아무도 듣지 않는 포트에도
        # connect 가 성공한다 — 중계가 대신 받고 곧 RST 를 던진다. 그래서
        # connect 만으로 판정하면 서버가 뜨기 전에 루프를 빠져나가고, 뒤이은
        # 요청이 ConnectionReset 으로 깨진다(terminal_api·agent_relay·live_signal
        # 앞쪽 테스트가 그렇게 흔들렸다). 응답의 첫 바이트까지 봐야 진짜다.
        with socket.create_connection((host, port), 1.0) as c:
            c.sendall(f"GET / HTTP/1.0\r\nHost: {host}:{port}\r\n\r\n"
                      .encode())
            c.settimeout(2.0)
            head = c.recv(5)
        if not head.startswith(b"HTTP/"):
            raise OSError(f"{host}:{port} — 연결은 됐지만 HTTP 응답이 없다 "
                          f"(중계가 받아준 가짜 연결)")

    connect = _connect or _default
    deadline = time.monotonic() + timeout
    delay = WAIT_FIRST
    attempts = 0
    while True:
        attempts += 1
        try:
            connect()
            return attempts
        except OSError:
            left = deadline - time.monotonic()
            if left <= 0:
                raise RuntimeError(
                    f"server did not start on {host}:{port} — "
                    f"{timeout:.0f}초 동안 {attempts}회 시도")
            time.sleep(min(delay, left))
            delay = min(delay * WAIT_GROWTH, WAIT_MAX)


# ---------------------------------------------------------------------------
# 실서비스 포트를 뺏은 테스트 서버 회수 (REQ-20260828-001)
#
# 스위트가 끝난 뒤 `/tmp/...` 작업공간의 `s9 serve` 가 9909 를 물고 살아남은
# 일이 있었다. 진짜 서버(cwd `~/section9`)와 번갈아 응답해 사용자 화면이
# 새로고침마다 정상/404 를 오갔고, 더 나쁘게는 **테스트 시작 시점의
# web/index.html 사본**을 내줘 화면 검증이 조용히 옛 화면을 통과시켰다.
#
# 회수 기준은 두 가지를 함께 본다 — ① 대시보드 대역(9909~9950) 포트,
# ② 작업공간(S9_ROOT 또는 cwd)이 임시 디렉토리. 진짜 서버는 작업공간이
# 저장소라 걸리지 않고, 풀 포트(18800~)를 쓰는 정상적인 테스트 서버도
# 걸리지 않는다(그쪽 회수는 s9-doctor --sweep 의 몫이다).
#
# `--supervise` 라 자식만 죽이면 되살아난다 — 감시자를 먼저 죽이고 몇 바퀴
# 돌며 확인한다.
# ---------------------------------------------------------------------------

_PORT_ARG = re.compile(r"^--port(?:=(\d+))?$")


def _argv_port(argv):
    """`--port 9909` / `--port=9909` 에서 포트 번호. 없으면 None."""
    for i, a in enumerate(argv):
        m = _PORT_ARG.match(a)
        if not m:
            continue
        if m.group(1):
            return int(m.group(1))
        if i + 1 < len(argv) and argv[i + 1].isdigit():
            return int(argv[i + 1])
    return None


# 시스템 임시 디렉토리를 **불러올 때 한 번** 못박는다 (REQ-20260829-003).
# 러너가 실행 전용 임시 루트로 tempfile.tempdir 을 돌리는데, 회수 판정의 기준은
# 그 루트가 아니라 /tmp 전체여야 한다 — 옛 실행이 남긴 서버는 그 밖에 있다.
SYS_TMP = os.path.realpath(tempfile.gettempdir())


def _under_tmp(path):
    if not path:
        return False
    path = path.replace(" (deleted)", "")
    tmp = SYS_TMP
    try:
        real = os.path.realpath(path)
    except OSError:
        real = path
    return real == tmp or real.startswith(tmp + os.sep)


def is_stray_dashboard_server(info):
    """이 프로세스가 '사용자 포트를 뺏은 테스트 서버' 인가.

    info: {"argv": [...], "cwd": str, "root": str(S9_ROOT)}
    """
    argv = list(info.get("argv") or [])
    if "serve" not in argv:
        return False
    if not any(os.path.basename(a) == "s9" for a in argv):
        return False
    if _argv_port(argv) not in DASHBOARD_PORTS:
        return False
    return _under_tmp(info.get("root")) or _under_tmp(info.get("cwd"))


def _proc_snapshot():
    """지금 살아 있는 프로세스의 argv·cwd·S9_ROOT. /proc 이 없으면 빈 목록."""
    out = []
    if not os.path.isdir("/proc"):
        return out
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/cmdline", "rb") as f:
                argv = [a.decode("utf-8", "replace")
                        for a in f.read().split(b"\0") if a]
        except OSError:
            continue
        if not argv:
            continue
        try:
            cwd = os.readlink(f"/proc/{name}/cwd")
        except OSError:
            cwd = ""
        root = ""
        try:
            with open(f"/proc/{name}/environ", "rb") as f:
                for kv in f.read().split(b"\0"):
                    if kv.startswith(b"S9_ROOT="):
                        root = kv[8:].decode("utf-8", "replace")
                        break
        except OSError:
            pass
        out.append({"pid": int(name), "argv": argv, "cwd": cwd, "root": root})
    return out


def stray_dashboard_servers(snapshot=None):
    procs = _proc_snapshot() if snapshot is None else snapshot
    return [p for p in procs if is_stray_dashboard_server(p)]


def reap_stray_dashboard_servers(rounds=3, snapshot=None, kill=None,
                                 sleep=None):
    """대시보드 대역을 물고 있는 임시 작업공간 서버를 거둔다.

    반환: 거둔 프로세스 정보 목록(같은 pid 는 한 번만). 아무것도 없으면 [].
    """
    kill = kill or os.kill
    sleep = sleep or time.sleep
    reaped, seen = [], set()
    for _ in range(max(1, rounds)):
        strays = stray_dashboard_servers(
            snapshot() if callable(snapshot) else snapshot)
        if not strays:
            break
        # 감시자 먼저 — 자식만 죽이면 감시자가 곧바로 되살린다
        strays.sort(key=lambda p: 0 if "--supervise" in p["argv"] else 1)
        for p in strays:
            try:
                kill(p["pid"], signal.SIGKILL)
            except OSError:
                pass
            if p["pid"] not in seen:
                seen.add(p["pid"])
                reaped.append(p)
        sleep(1.0)          # 포트를 실제로 놓을 틈
    return reaped


def describe_stray(p):
    port = _argv_port(p.get("argv") or [])
    where = p.get("root") or p.get("cwd") or "?"
    return f"pid {p.get('pid')} port {port} 작업공간 {where}"


def urlopen_retry(target, timeout=5.0, tries=3, pause=0.3):
    """붙자마자 끊기는 갈래를 여기서 한 번만 다시 건다 (REQ-20260904-003).

    이 환경에는 연결이 서자마자 끊기는 갈래가 낮은 비율로 있다 — 윈도우 쪽
    중계가 같은 자리를 함께 듣기 때문이다(REQ-20260902-006 이 지목했다).
    `http.client` 는 그것을 `RemoteDisconnected` 로 올리는데, 그 예외는
    `ConnectionResetError` 의 자식이라 아래 한 줄에 함께 걸린다.

    **왜 파일마다가 아니라 여기인가.** 2026-09-04 하루에 같은 모양으로 셋이
    넘어졌다(project_api · dashboard_chat · stream_live_ended). 셋 다 POST 에는
    되걸기가 있고 GET 에는 없었다 — 비대칭이 매번 다른 파일을 넘어뜨렸다.
    되걸기가 나뉘어 있으면 한쪽만 고쳐지고, 그 한쪽이 다음 사고가 된다.

    반환: (status, 본문 문자열). HTTPError 는 되걸지 않는다 — 서버가 답을 준
    것이라 다시 걸어도 같은 답이고, 그 답이 곧 시험이 보려던 것일 수 있다.
    """
    import urllib.error
    import urllib.request
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(target, timeout=timeout) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
        except (ConnectionError, urllib.error.URLError):
            if attempt == tries - 1:
                raise
            time.sleep(pause)


_URLOPEN_WRAPPED = False


def install_urlopen_retry(tries=5, pause=0.3):
    """`urllib.request.urlopen` 에 되걸기를 한 번 입힌다 (REQ-20260904-003).

    **왜 파일마다가 아니라 여기인가.** WSL2 virtioproxy 에서는 중계가 연결을
    대신 받고 곧 RST 를 던지는 갈래가 낮은 비율로 있다(`wait_server` 머리말의
    그 관찰이고, REQ-20260902-006 이 9909 에서 지목한 것과 같은 뿌리다).
    그래서 로컬 서버에 요청하는 시험은 부하가 걸릴 때 낮은 비율로 넘어진다.

    2026-09-04 하루에 **네 파일이 차례로** 같은 모양으로 넘어졌다
    (project_api → dashboard_chat → stream_live_ended → priority_handle).
    실행마다 희생자가 바뀌니 파일을 하나씩 고치는 것은 끝이 없다 — 훑어보니
    되걸기 없이 로컬 서버를 두드리는 시험이 **15개**였다. 그래서 자리를 하나로
    한다.

    `HTTPError` 는 되걸지 않는다 — 서버가 답을 준 것이고, 그 답이 곧 시험이
    보려던 것일 수 있다(`URLError` 의 자식이라 순서가 중요하다). 서버가 정말
    없으면 세 번 두드린 뒤 같은 예외가 그대로 오른다 — 판정은 안 바뀌고
    조금 늦어질 뿐이다.
    """
    global _URLOPEN_WRAPPED
    if _URLOPEN_WRAPPED:
        return
    import urllib.error
    import urllib.request
    real = urllib.request.urlopen

    def retrying(*a, **kw):
        for attempt in range(tries):
            try:
                return real(*a, **kw)
            except urllib.error.HTTPError:
                raise                      # 서버가 준 답이다 — 다시 걸지 않는다
            except (ConnectionError, urllib.error.URLError):
                if attempt == tries - 1:
                    raise
                # 물러서며 기다린다 — `wait_server` 와 같은 규율이다. 고장이
                # 났을 때 같은 간격으로 계속 두드리면 그 두드림이 고장을
                # 키운다(DOC-20260826-008 의 되먹임).
                time.sleep(pause * (2 ** attempt))

    urllib.request.urlopen = retrying
    _URLOPEN_WRAPPED = True
