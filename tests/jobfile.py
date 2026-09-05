"""잡 파일 — 러너가 자기 존재를 대시보드에 알린다 (REQ-20260830-022).

테스트 스위트는 몇 분씩 무출력으로 돌고, 그동안 화면에는 아무것도 없어
"모든 것이 멈춘 것처럼" 보였다 (사용자 2026-08-30 15:03). 다각 검토 합의:
러너가 시작할 때 state/jobs/ 에 한 파일을 쓰고, 진행 수를 갱신하고, 끝나면
거둔다. 읽는 쪽(bin/s9 jobs_running)이 pid 생존·명령줄 대조·시작 상한으로
검증하므로 급사한 러너의 파일은 거짓말하지 못한다.

**이 디렉토리는 러너의 내부 관례다** — 범용 잡 API·새 s9 명령으로 일반화하지
않는다 (product-owner 조건: 이 장치가 커진다면 바로 그 문에서 커진다).

시험이 S9_ROOT 를 격리해도 잡 파일은 **실제 repo** 의 state/ 로 간다 —
화면이 읽는 곳이 거기다. 안쪽 실행(S9_TESTS_NESTED=1)은 아무것도 쓰지 않는다.
"""
import atexit
import json
import os
import time

_NOOP = (lambda n: None, lambda: None)


def start(total, root=None, name="테스트", hint="tests", args="", kind=""):
    """잡 파일을 쓴다. 반환 (bump(n), clear) — 어떤 실패도 러너를 못 죽인다.

    파일 이름에 pid 가 들어간다 (REQ-20260830-022 반려 재작업): 이름이 하나면
    동시 실행 둘이 서로 덮어쓰고, 먼저 끝난 쪽의 정리가 다른 쪽 표시까지
    지운다 — 리드와 무인 작업자는 실제로 동시에 테스트를 돌린다. 죽은 실행이
    남긴 파일은 읽는 쪽 pid 대조가 무시하고 7일 sweep 이 거둔다."""
    if os.environ.get("S9_TESTS_NESTED") == "1":
        return _NOOP
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, "state", "jobs")
    path = os.path.join(d, f"tests-{os.getpid()}.json")
    state = {"name": name, "hint": hint, "pid": os.getpid(),
             "started": time.time(),
             "session": (os.environ.get("S9_SESSION") or "")[:8],
             "req": (os.environ.get("S9_JOB_REQ") or "")[:40],
             "args": str(args or "")[:120],
             # 이 실행이 어떤 종류인가 (REQ-20260905-006) — full·smoke·targeted.
             # **러너만 아는 사실이다**: 명령줄에는 `--changed` 가 고른 파일도,
             # 게이트가 전체로 물러난 사정도 안 적혀 있다. 여기 적어 두면 읽는
             # 쪽이 문자열을 되짚어 다시 알아낼 일이 없다.
             "kind": str(kind or "")[:16],
             "total": int(total or 0), "done": 0}

    def sweep():
        """죽은 실행이 남긴 형제 파일을 거둔다 — clear 는 kill -9 를 못 만나고,
        읽는 쪽은 무시만 하지 지우지 않는다. 7일이면 어떤 잡도 무신호다."""
        try:
            for fn in os.listdir(d):
                fp = os.path.join(d, fn)
                if fn.startswith("tests-") and \
                        time.time() - os.path.getmtime(fp) > 7 * 86400:
                    os.unlink(fp)
        except OSError:
            pass

    def write():
        try:
            os.makedirs(d, exist_ok=True)
            for fn in os.listdir(d):   # 7일 고아 회수 — 워처 없는 환경의 안전망
                fp = os.path.join(d, fn)
                if fn.startswith("tests-") and \
                        time.time() - os.path.getmtime(fp) > 7 * 86400:
                    os.unlink(fp)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(state, ensure_ascii=False))
            os.replace(tmp, path)
        except OSError:
            pass

    last = [0.0]

    def bump(n):
        """테스트 하나 끝날 때마다 부르되, 실제 쓰기는 1초에 한 번이다 —
        mtime 이 곧 '마지막 신호' 시계라 너무 자주 쓰면 낭비, 안 쓰면 잠잠."""
        state["done"] = int(n)
        now = time.time()
        if now - last[0] >= 1.0:
            last[0] = now
            write()

    def clear():
        try:
            os.unlink(path)
        except OSError:
            pass

    try:
        write()
        sweep()
        atexit.register(clear)
    except Exception:
        return _NOOP
    return bump, clear
