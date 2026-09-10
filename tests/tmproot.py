"""실행 전용 임시 루트 — 테스트가 /tmp 를 흘리지 않게 한다 (REQ-20260829-003).

왜 필요한가. 2026-08-29 부팅 48분 만에 /tmp 최상위가 128개였고 그중 127개가
우리 테스트 것이었다(s9gate-* 98, s9hookstamp-* 11, …). tests/*.py 84개가
`tempfile.mkdtemp` 로 S9_ROOT 를 만들고 한 번도 지우지 않는다. 커밋 검사가
매분 돌면서 하루 2,880개가 쌓이고, /tmp 디렉터리 아이노드는 7.5MB 까지 자랐다
(ext4 디렉터리는 한 번 커지면 줄지 않는다).

그 대가는 부트에서 돌아온다. systemd-tmpfiles-setup 은 `--remove` 로 돌아
부트마다 /tmp 를 통째로 지운다 — 실측 73초. 그동안 sysinit 이 막히고
systemd-logind 가 늦게 떠, WSL 의 10초 사용자 세션 창을 놓친다.

고치는 자리. 파일마다 tearDown 을 84번 심는 대신 러너가 한 곳에서 막는다. 실행마다
전용 루트를 세우고 `tempfile.tempdir` 과 `TMPDIR` 을 그리로 돌리면, 테스트가
무엇을 만들든 그 안에 생기고 끝날 때 통째로 사라진다. 새로 들어올 테스트도
아무것도 안 해도 지켜진다.

거두되 조용히 치우지 않는다 — 포트 회수와 같은 규율이다. 무엇이 남았는지
이름의 접두어로 알린다.
"""
import os
import re
import shutil
import tempfile
import time

# 시스템 임시 디렉토리. 실행 전용 루트로 tempfile.tempdir 을 돌린 뒤에도
# '남의 것/우리 것' 판정과 잔재 청소의 기준은 여기여야 한다.
SYS_TMP = os.path.realpath(tempfile.gettempdir())

# 우리 테스트가 만드는 임시 자리는 전부 이 접두어로 시작한다. 남의 것
# (claude-*, snap-private-tmp, systemd-private-*, .X11-unix)은 건드리지 않는다.
OURS_PREFIX = "s9"
RUN_PREFIX = "s9run-"
STALE_AGE = 3600.0          # 테스트 실행이 한 시간을 넘지는 않는다

# 우리 접두어를 달았지만 **실행 사이에 공유해야 하는** 자리. 포트 락은 동시에
# 도는 실행끼리 나눠 쓰는 것이라 나이로 지우면 안 된다 — 락 파일이 사라지면
# 두 실행이 같은 포트를 제 것이라 믿는다.
KEEP = frozenset({"s9-portpool"})

# 아이노드 바닥 (REQ-20260910-012). 실측 2026-09-10 17:00: /tmp 의 아이노드
# 1,048,576 개가 하나도 남지 않아, bash 도구가 제 출력 파일조차 만들지 못했다 —
# 테스트도 s9 명령도 아무것도 돌지 못했다. 남은 것은 전부 pid 가 이미 없는
# 실행 루트였고(그중 하나가 32,746개), 거두니 35,921 개가 돌아왔다. 한 번의
# 전체 실행이 쓰는 아이노드가 그만큼이라는 뜻이다.
#
# 그래서 두 줄을 긋는다. RUN_NEED 아래면 알리기만 하고(실행은 그대로 돈다),
# FLOOR 아래면 시작하지 않는다 — 바닥난 채로 시작하면 실패가 알 수 없는
# 모습으로 흩어져, 무엇이 문제인지 아무 데도 적히지 않는다.
INODE_RUN_NEED = 50_000
INODE_FLOOR = 10_000

_RUN_RE = re.compile(r"^s9run-(\d+)-")


def is_ours(name):
    return name.startswith(OURS_PREFIX)


def run_root_pid(name):
    """s9run-<pid>-xxxx 에서 pid 를 뽑는다. 실행 루트가 아니면 None."""
    m = _RUN_RE.match(name)
    return int(m.group(1)) if m else None


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def stale_dirs(base=None, now=None, age=STALE_AGE, alive=None, names=None,
               mtime=None):
    """지난 실행이 남긴 우리 자리들.

    남의 것은 이름으로 뺀다. 살아 있는 실행 루트는 pid 로 뺀다 — 동시에 도는
    다른 러너의 자리를 지우면 그 실행이 깨진다.

    **주인이 없는 실행 루트에는 나이를 묻지 않는다** (REQ-20260910-012): pid 가
    없다는 것은 그 실행이 이미 끝났다는 확정이지 짐작이 아니라, 한 시간을
    기다릴 이유가 없다. 기다리는 동안이 바로 사고가 나는 자리였다 — 2026-09-10
    에 아이노드를 바닥낸 여덟 자리는 전부 pid 가 없었고 전부 한 시간이 안
    된 것이었다. 나이 기준은 pid 로 주인을 물을 수 없는 자리(s9gate-* 처럼 옛
    체크아웃의 러너가 흘린 것)에만 남는다.
    """
    base = base or SYS_TMP
    now = time.time() if now is None else now
    alive = _alive if alive is None else alive
    mtime = (lambda p: os.path.getmtime(p)) if mtime is None else mtime
    try:
        names = sorted(os.listdir(base)) if names is None else list(names)
    except OSError:
        return []
    out = []
    for name in names:
        if not is_ours(name) or name in KEEP:
            continue
        pid = run_root_pid(name)
        path = os.path.join(base, name)
        if pid is not None:
            if alive(pid):
                continue        # 지금 도는 실행의 자리다
            out.append(path)    # 주인이 없다 — 나이를 묻지 않는다
            continue
        try:
            if now - mtime(path) < age:
                continue
        except OSError:
            continue
        out.append(path)
    return out


def sweep_stale(base=None, now=None, age=STALE_AGE, alive=None):
    """잔재를 거두고 거둔 경로들을 돌려준다."""
    gone = []
    for path in stale_dirs(base, now=now, age=age, alive=alive):
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except OSError:
            continue
        gone.append(path)
    return gone


def inode_free(base=None, statvfs=None):
    """임시 자리를 담은 파일시스템의 (남은 아이노드, 전체 아이노드).

    세지 않는 파일시스템(tmpfs·btrfs 처럼 아이노드가 미리 정해지지 않은 것)은
    전체를 0 으로 보고한다 — 그때는 (None, None) 이다. 모르는 것을 아는 척해
    실행을 막지 않는다.
    """
    base = base or SYS_TMP
    st = (os.statvfs if statvfs is None else statvfs)
    try:
        s = st(base)
    except OSError:
        return (None, None)
    total = getattr(s, "f_files", 0) or 0
    free = getattr(s, "f_favail", 0) or 0
    if total <= 0:
        return (None, None)
    return (int(free), int(total))


def inode_verdict(free, total, need=INODE_RUN_NEED, floor=INODE_FLOOR,
                  base=None):
    """('ok'|'unknown'|'warn'|'stop', 사람이 읽을 한 줄 또는 None).

    stop 은 「지금 시작하면 아이노드가 바닥나 실패가 알 수 없는 모습으로
    흩어진다」는 뜻이다. 한 줄에는 남은 수와 여는 방법이 함께 있어야 한다 —
    무엇이 막았는지만 알려 주고 나가는 길을 안 적으면 사람이 다시 막힌다.
    """
    where = base or SYS_TMP
    if free is None or not total:
        return ("unknown", None)
    # 바닥을 먼저 본다 — 두 줄은 따로 움직일 수 있고(환경으로 옮긴다),
    # 넉넉함을 먼저 물으면 바닥이 위로 올라온 자리에서 판정이 뒤집힌다.
    if free < floor:
        return ("stop",
                f"[임시자리] {where} 의 아이노드가 {free:,}개뿐이다"
                f"(전체 {total:,}) — 이대로 시작하면 임시 파일을 못 만들어 "
                f"실패가 흩어진다. `s9 doctor --fix` 로 거두거나, TMPDIR 을 "
                f"여유 있는 자리로 두고 다시 불러라. 그래도 돌리려면 "
                f"S9_TMP_ANYWAY=1.")
    if free < need:
        return ("warn",
                f"[임시자리] {where} 의 아이노드가 {free:,}개 남았다"
                f"(전체 {total:,}) — 전체 실행 한 번이 약 {need:,}개를 쓴다. "
                f"`s9 doctor --fix` 로 거두거나 TMPDIR 을 다른 파일시스템으로 "
                f"두어라.")
    return ("ok", None)


def inode_gate(base=None, env=None, statvfs=None):
    """실행 직전 판정 — (돌려도 되는가, 알릴 한 줄).

    문턱은 환경으로 옮길 수 있다(S9_TMP_INODE_FLOOR·S9_TMP_INODE_NEED). 사람이
    S9_TMP_ANYWAY=1 로 지나가면 말은 그대로 하고 막지는 않는다 — 판정을 지우는
    것이 아니라 사람이 알고 지나가는 것이다.
    """
    env = os.environ if env is None else env

    def _num(key, default):
        try:
            return int(env[key])
        except (KeyError, ValueError):
            return default

    free, total = inode_free(base, statvfs=statvfs)
    level, line = inode_verdict(free, total,
                                need=_num("S9_TMP_INODE_NEED", INODE_RUN_NEED),
                                floor=_num("S9_TMP_INODE_FLOOR", INODE_FLOOR),
                                base=base)
    if level != "stop":
        return (True, line)
    if env.get("S9_TMP_ANYWAY") == "1":
        return (True, line + " (S9_TMP_ANYWAY=1 — 그대로 돈다)")
    return (False, line)


def make_run_root(base=None, pid=None):
    """이번 실행 전용 루트를 세우고 tempfile·TMPDIR 을 그리로 돌린다.

    반환: (루트 경로, 되돌리기용 이전 TMPDIR 값 또는 None)
    """
    base = base or SYS_TMP
    pid = os.getpid() if pid is None else pid
    root = tempfile.mkdtemp(prefix=f"{RUN_PREFIX}{pid}-", dir=base)
    prev = os.environ.get("TMPDIR")
    tempfile.tempdir = root
    os.environ["TMPDIR"] = root     # 하위 프로세스(s9 CLI)도 같은 자리를 쓴다
    return root, prev


def leftovers(root):
    try:
        return sorted(os.listdir(root))
    except OSError:
        return []


def drop_run_root(root, prev_tmpdir=None):
    """루트를 통째로 지우고, 안에 남아 있던 최상위 이름들을 돌려준다."""
    left = leftovers(root)
    tempfile.tempdir = None
    if prev_tmpdir is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = prev_tmpdir
    shutil.rmtree(root, ignore_errors=True)
    return left
