"""전체 스위트를 원격 머신에서 (REQ-20260905-012).

이 머신(WSL)에서 전체를 돌리면 4~13분이 걸리고 중계 계열 간헐 실패(REQ-20260905-007)
가 절반을 붉게 한다. 원격 리눅스(48코어)라면 둘 다 없다. 접속 정보는 외부 비밀
`jade` 같은 **ssh 연결 명령어**이고, 값은 여기서 읽지 않는다 — `s9 secret run` 의
`{{secret:KEY}}` 치환으로만 쓴다(값은 프로세스 인자로만 지나가고 기록에 남지 않는다).

흐름(동기화의 축은 GitHub 이다 — 사용자 지적 2026-09-05): ① 이 머신의 HEAD 를
`refs/ci/<sha7>` 로 origin 에 push 한다 ② 원격은 같은 origin 의 clone(없으면 만든다)
에서 그 ref 를 받아 그 커밋을 펴고 `python3 tests/ --jobs N` 을 돌린다 — 출력은
그대로 흘려보낸다 ③ 종료 코드가 0 이고 이 머신에 미커밋 변경이 없었으면 HEAD 의
나무 지문으로 초록 기록을 남긴다 — 커밋 문·재사용이 그대로 인정한다. 미커밋
변경은 원격에 실리지 않는다(돌긴 돌되 초록 기록은 안 남긴다).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
REMOTE_DIR = "~/section9-ci"
REMOTE_KEY_FILE = os.path.join(REPO, "state", "test-remote")
# 이 머신에서만 도는 것 — 원격의 환경이 답을 바꾸는 시험(시간대 목록·ps 판정·큰 자산).
# 원격 실행이 끝난 뒤 이 머신이 마저 돈다. 목록은 짧아야 한다 — 길어지면 원격이
# 「전체」가 아니다.
LOCAL_ONLY = ("test_timezone_pick.py", "test_platform_live.py", "test_pdf_text.py",
              "test_commit_gate.py")      # 이 머신의 git 훅 설치 상태를 본다


def remote_key(argv=None):
    """`--remote KEY` > 환경 S9_TEST_REMOTE > state/test-remote 파일. 없으면 None."""
    argv = sys.argv[1:] if argv is None else argv
    if "--remote" in argv:
        i = argv.index("--remote")
        if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            return argv[i + 1]
        return None
    k = (os.environ.get("S9_TEST_REMOTE") or "").strip()
    if k:
        return k
    try:
        with open(REMOTE_KEY_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def is_full_invocation(argv):
    """이 호출이 「전체」인가 — 패턴이 없고 스모크·게이트·변경 선택이 아니다.

    `--jobs N`·`--remote KEY` 의 값은 패턴이 아니다(실측 2026-09-05: `--jobs 16` 의
    16 을 패턴으로 세어 전체 실행이 원격으로 안 갔다).
    """
    rest = []
    skip = False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in ("--jobs", "--remote"):
            skip = True
            continue
        rest.append(a)
    if any(f in rest for f in ("--smoke", "--gate", "--changed")):
        return False
    return not [a for a in rest if not a.startswith("-")]


def remember(key):
    os.makedirs(os.path.dirname(REMOTE_KEY_FILE), exist_ok=True)
    with open(REMOTE_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip() + "\n")


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO,
                          timeout=120)


def head_state():
    """(sha, 미커밋 변경 수) — 원격은 **commit 된 나무**를 돈다. 미커밋 변경은 안 실린다."""
    sha = _git("rev-parse", "HEAD").stdout.strip()
    dirty = [ln for ln in _git("status", "--porcelain", "--untracked-files=no").stdout.splitlines()
             if ln.strip()]
    return sha, len(dirty)


def remote_script(url, sha, dest, jobs, pats_argv, user=""):
    """원격에서 돌 한 줄 — clone(없으면) → ci ref fetch → 그 커밋으로 → index → 시험.

    GitHub 이 동기화의 축이다(사용자 지적 2026-09-05): 이 머신은 HEAD 를
    `refs/ci/<sha7>` 로 push 하고, 원격은 같은 origin 에서 그것을 받아 그 커밋을
    편다 — 보내고 말고가 없고, 원격은 언제나 진짜 git 저장소다.
    """
    short = sha[:7]
    # 정체는 환경변수로 강제하지 않는다 — S9_USER 를 실행 전체에 걸면 제 사용자를
    # 만드는 시험 30여 건이 그 값을 물려받아 붉는다(실측 2026-09-05, 34건). 대신
    # 원격 OS 계정을 이 머신의 사용자에게 **attach** 해 둔다 — 그러면 whoami 가
    # os-account 로 그 사람을 찾고, 관리자만 보는 손잡이를 재는 시험도 선다.
    attach = (f"S9_ROOT=$D python3 bin/s9 user attach {_sh_quote(user)} >/dev/null 2>&1 || true; "
              if user else "")
    pats = " ".join(_sh_quote(a) for a in pats_argv)
    return (f"set -e; D={dest}; [ -d $D/.git ] || git clone -q {_sh_quote(url)} $D; "
            f"cd $D && git fetch -q origin +refs/ci/{short}:refs/ci/{short} "
            f"&& git checkout -q -f {sha} && git clean -qfd; "
            f"S9_ROOT=$D python3 bin/s9 index rebuild >/dev/null 2>&1 || true; "
            f"{attach}S9_MAX_JOBS={jobs} S9_TEST_REMOTE= python3 tests/ --jobs {jobs} "
            f"--no-reuse {pats}")


RC_MARK = "__S9_REMOTE_RC="


def _ssh(key, remote_cmd, stdin=None, stream=True, timeout=None):
    """원격에서 remote_cmd 를 돈다 — 비밀은 치환으로만.

    종료 코드는 **원격이 마지막 줄에 찍는 표식**으로 받는다. `s9 secret run` 과
    ssh 를 거치며 코드가 0 으로 뭉개진 실측(2026-09-05: 원격 FAILED 가 초록으로
    보고됨)이 있어, 파이프의 반환값을 믿지 않는다. 출력은 그대로 흘려보낸다.
    """
    marked = f"({remote_cmd}); echo {RC_MARK}$?"
    script = "{{secret:%s}} %s" % (key, _sh_quote(marked))
    argv = [S9, "secret", "run", "--", "sh", "-c", script]
    p = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    rc = None
    for raw in p.stdout:
        line = raw.decode("utf-8", "replace")
        if line.startswith(RC_MARK):
            try:
                rc = int(line[len(RC_MARK):].strip())
            except ValueError:
                rc = 1
            continue
        if stream:
            sys.stdout.write(line); sys.stdout.flush()
    p.wait(timeout=timeout)
    return subprocess.CompletedProcess(argv, p.returncode if rc is None else rc)


def _local_user():
    u = (os.environ.get("S9_USER") or "").strip()
    if u:
        return u
    try:
        out = subprocess.run([S9, "user", "current"], capture_output=True, text=True,
                             timeout=20).stdout.strip().split()
        name = out[0] if out else ""
        import re as _re
        return name if _re.fullmatch(r"[A-Za-z0-9_.\-]+", name) else ""
    except Exception:
        return ""


def _sh_quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


def run_remote(key, pats_argv, jobs=16, name=None, fingerprint=None, on_green=None,
               on_red=None):
    """push(ci ref) → 원격이 받아 실행 → 기록. 반환: 원격 종료 코드.

    미커밋 변경이 있으면 돌리되 **초록 기록은 남기지 않는다** — 그 지문은 원격이
    돈 나무의 것이 아니다.
    """
    name = name or os.path.basename(REPO)
    dest = f"{REMOTE_DIR}/{name}"
    url = _git("remote", "get-url", "origin").stdout.strip()
    sha, dirty = head_state()
    if not url or not sha:
        print("[원격] origin 이나 HEAD 가 없다 — git 저장소에서만 원격으로 간다", file=sys.stderr)
        return 1
    if dirty:
        print(f"[원격] 미커밋 변경 {dirty}개는 원격에 실리지 않는다 — HEAD {sha[:7]} 를 돈다. "
              f"초록 기록은 남기지 않는다(commit 뒤 다시 돌면 남는다)", file=sys.stderr)
    t0 = time.time()
    r = _git("push", "-q", "-f", "origin", f"HEAD:refs/ci/{sha[:7]}")
    if r.returncode != 0:
        print(f"[원격] push 실패: {r.stderr.strip()[:200]}", file=sys.stderr)
        return 1
    print(f"[원격] {key}: {sha[:7]} 을 refs/ci 로 push 했다 ({time.time() - t0:.0f}초). "
          f"원격이 받아 돈다: python3 tests/ --jobs {jobs} {' '.join(pats_argv)[:80]}",
          file=sys.stderr)
    r = _ssh(key, remote_script(url, sha, dest, jobs, pats_argv, user=_local_user()),
             stream=True, timeout=3600)
    took = time.time() - t0
    if r.returncode == 0:
        print(f"[원격] 초록 ({took:.0f}초)", file=sys.stderr)
        if on_green and not dirty:
            on_green(fingerprint)
    else:
        print(f"[원격] 붉음 rc={r.returncode} ({took:.0f}초)", file=sys.stderr)
        if on_red:
            on_red()
    return r.returncode
