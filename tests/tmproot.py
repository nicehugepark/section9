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
    다른 러너의 자리를 지우면 그 실행이 깨진다. 나이 기준은 그 둘을 통과한
    것에만 적용한다.
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
        if pid is not None and alive(pid):
            continue            # 지금 도는 실행의 자리다
        path = os.path.join(base, name)
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
