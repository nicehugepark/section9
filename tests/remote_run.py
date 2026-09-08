"""전체 스위트를 원격 머신에서 (REQ-20260905-012 · REQ-20260907-049).

이 머신(WSL)에서 전체를 돌리면 4~13분이 걸리고 중계 계열 간헐 실패(REQ-20260905-007)
가 절반을 실패로 만든다. 원격 리눅스(48코어)라면 둘 다 없다. 접속 정보는 외부 비밀
(**ssh 연결 명령어**)이고 값은 여기서 읽지 않는다 — `s9 secret run` 의
`{{secret:KEY}}` 치환으로만 쓴다(값은 프로세스 인자로만 지나가고 기록에 남지 않는다).

흐름: ① 원격이 이미 가진 커밋을 묻는다 ② 그 뒤부터 HEAD 까지의 증분을 `git bundle`
로 만들어 **ssh 통로로 곧장** 건넨다 ③ 원격은 그것을 받아 그 커밋을 펴고, 편 커밋이
요청한 커밋인지 되물어 확인한 뒤 `python3 tests/ --jobs N` 을 돈다 — 출력은 그대로
흘려보낸다 ④ 종료 코드가 0 이고, 원격이 센 파일 수가 요청한 수와 같고, 이 머신에
미커밋 변경이 없었으면 HEAD 의 tree 지문으로 통과 기록을 남긴다. 미커밋 변경은
원격에 실리지 않는다(돌긴 돌되 통과 기록은 안 남긴다).

**GitHub 을 거치지 않는다** (REQ-20260907-049 에서 바뀐 자리). 원래는 이 머신이
`refs/ci/<sha7>` 로 origin 에 push 하고 원격이 같은 origin 에서 그것을 받았다
(「동기화의 축은 GitHub」, 2026-09-05). 그런데 원격의 키는 **다른 저장소의 deploy
key** 라 GitHub 이 `ERROR: Repository not found.` 로 답했고 — 권한 없는 키에는
없는 저장소처럼 답한다 — 원격 작업자리는 2026-09-06 14:46 커밋에 하루 내내 멈춰
있었다. 이 머신은 이미 그 커밋을 갖고 있으니 남을 거쳐 다시 받을 이유가 없다.
저장소 자체의 GitHub 동기화는 그대로다; 바뀐 것은 **시험용 커밋 전달 통로** 하나다.
"""
import os
import subprocess
import sys
import tempfile
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
    """이 호출이 「전체」인가 — 패턴이 없고 스모크·검사·변경 선택이 아니다.

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


# 지문에 안 세는 자리 — 문서·상태·사람 데이터는 시험 결과를 바꾸지 않는다.
# tests/__main__.py 의 tree_fingerprint 와 **같은 표**다 (거기서 이것을 가져다 쓴다).
FP_SKIP = ("vault/", "state/", "docs/", "projects/", "users/", "index/",
           ".git/")


def head_state(repo=None, skip=FP_SKIP):
    """(sha, 지문에 드는 미커밋 변경 수) — 원격은 **commit 된 tree**를 돈다.

    skip 아래(문서·상태)의 변경은 지문에도 안 들고 시험 결과도 안 바꾸니 세지
    않는다. 실측 2026-09-06: commit 훅이 그 commit 을 REQ 문서에 노트로 붙이므로
    commit 직후의 tree는 **언제나** vault/ 한 파일이 더러웠고, 그래서 post-commit
    배경 실행이 통과 기록을 한 번도 남기지 못했다(「미커밋 변경 1개 …」).
    """
    repo = repo or REPO
    sha = _git("-C", repo, "rev-parse", "HEAD").stdout.strip()
    dirty = []
    for ln in _git("-C", repo, "status", "--porcelain", "--untracked-files=no").stdout.splitlines():
        if not ln.strip():
            continue
        path = ln[3:].split(" -> ")[-1].strip().strip('"').replace("\\", "/")
        if path.startswith(tuple(skip)):
            continue
        dirty.append(path)
    return sha, len(dirty)


def probe_script(dest):
    """원격이 이미 가진 커밋을 한 줄로 묻는다 — 증분 bundle 을 만들 재료."""
    return (f"D={dest}; "
            f'if [ -d "$D/.git" ]; then '
            f'echo "{HAVE_MARK}$(git -C "$D" rev-parse HEAD 2>/dev/null || echo none)"; '
            f'else echo "{HAVE_MARK}none"; fi')


def remote_script(sha, dest, jobs, pats_argv, *, user=""):
    # user 는 이름으로만 받는다 (REQ-20260907-050): 인자가 넷이라 자리를 하나
    # 더 밀어 넣으면 `user` 에 엉뚱한 값이 얹혔고, 오류가 「user 에 값이 둘」로
    # 나와 **무엇이 밀렸는지**를 가렸다. 이름만 받으면 「자리 인자가 하나 많다」로
    # 곧장 드러난다.
    """원격에서 돌 한 줄 — bundle 받기 → 그 커밋으로 펴기 → 확인 → 시험.

    **GitHub 을 거치지 않는다** (REQ-20260907-049). 예전에는 이 머신이 HEAD 를
    `refs/ci/<sha7>` 로 origin 에 push 하고 원격이 같은 origin 에서 그것을 받았는데,
    원격의 키는 **다른 저장소의 deploy key** 라 GitHub 이 `ERROR: Repository not
    found.` 로 답했다(권한 없는 키에는 없는 저장소처럼 답한다). 실측 2026-09-07:
    원격 작업자리는 2026-09-06 14:46 의 커밋(시험 338개)에 **하루 내내 멈춰** 있었고,
    준비 실패가 실행을 멈추지 못하던 때에는 그 옛 tree의 결과가 「전체 통과」로 나왔다.
    이 머신은 이미 그 커밋을 갖고 있다 — 남을 거쳐 다시 받을 이유가 없다. 커밋은
    ssh 통로로 bundle 을 흘려 **직접** 건넨다(하루치 증분 20MB, 전체는 첫 회만).

    준비 단계는 `|| exit` 로 하나씩 막는다 — `set -e` 는 AND-OR 리스트의 마지막이
    아닌 명령의 실패를 건너뛴다(REQ-20260907-047). 편 뒤에는 HEAD 를 되물어 확인한다.
    """
    short = sha[:7]
    # 정체는 환경변수로 강제하지 않는다 — S9_USER 를 실행 전체에 걸면 제 사용자를
    # 만드는 시험 30여 건이 그 값을 물려받아 실패한다(실측 2026-09-05, 34건). 대신
    # 원격 OS 계정을 이 머신의 사용자에게 **attach** 해 둔다.
    attach = (f"S9_ROOT=$D python3 bin/s9 user attach {_sh_quote(user)} >/dev/null 2>&1 || true; "
              if user else "")
    pats = " ".join(_sh_quote(a) for a in pats_argv)
    return (f"set -e; D={dest}; B=$D.s9ci-{short}.bundle; "
            f'mkdir -p "$(dirname "$D")" || exit 90; '
            f'cat > "$B" || exit 90; '
            f'if [ ! -d "$D/.git" ]; then git init -q "$D" || exit 91; fi; '
            f'cd "$D" || exit 92; '
            f'git fetch -q "$B" HEAD:refs/ci/{short} || exit 93; '
            f'rm -f "$B"; '
            f"git checkout -q -f {sha} || exit 94; "
            f"git clean -qfd || exit 95; "
            f'have=$(git rev-parse HEAD 2>/dev/null); '
            f'if [ "$have" != {_sh_quote(sha)} ]; then '
            f'echo "[원격] 편 커밋이 다르다: 요청 {short} · 실제 $have" 1>&2; exit 96; fi; '
            f"S9_ROOT=$D python3 bin/s9 index rebuild >/dev/null 2>&1 || true; "
            f"{attach}S9_MAX_JOBS={jobs} S9_TEST_REMOTE= S9_TEST_WORKER=1 python3 tests/ --jobs {jobs} "
            f"--no-reuse {pats}")


RC_MARK = "__S9_REMOTE_RC="
RED_MARK = "__S9_FULL_RED="       # 원격 러너가 끝에 찍는 실패 파일 목록 (async_notify 와 같은 글자)
FLAKY_MARK = "__S9_FLAKY="        # 원격이 찍는 「실패 → 통과로 뒤집힌 파일」 (REQ-20260908-006)
RAN_MARK = "__S9_RAN="            # 원격 러너가 끝에 찍는 **셈에 든 파일 수** (돈 것 + 격리한 것)
HAVE_MARK = "__S9_HAVE="          # 원격이 이미 가진 커밋 (증분 bundle 의 기준점)
PREP_RC = {90: "커밋 꾸러미(bundle)를 못 받음", 91: "작업자리를 못 만듦",
           92: "작업자리로 못 들어감", 93: "커밋 꾸러미에서 못 받음",
           94: "펴기 실패", 95: "clean 실패", 96: "편 커밋이 요청과 다름"}
LAST_RED = []                     # 마지막 run_remote 가 걷은 실패 파일
LAST_FLAKY = []                   # 마지막 run_remote 가 걷은 간헐 실패 파일
LAST_RAN = None                   # 원격이 실제로 센 파일 수 (표식을 못 받았으면 None)
LAST_HAVE = None                  # 원격이 이미 가진 커밋 (probe 가 채운다)
LAST_TOOK = 0.0                   # 마지막 run_remote 의 소요(초)
LAST_SHA = ""                     # 마지막 run_remote 가 **실제로 보낸** 커밋 (REQ-20260907-064)


def _ssh(key, remote_cmd, stdin=None, stream=True, timeout=None):
    """원격에서 remote_cmd 를 돈다 — 비밀은 치환으로만.

    종료 코드는 **원격이 마지막 줄에 찍는 표식**으로 받는다. `s9 secret run` 과
    ssh 를 거치며 코드가 0 으로 뭉개진 실측(2026-09-05: 원격 FAILED 가 통과로
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
        if line.startswith(RED_MARK):
            LAST_RED[:] = line[len(RED_MARK):].split()
            continue
        if line.startswith(FLAKY_MARK):
            LAST_FLAKY[:] = line[len(FLAKY_MARK):].split()
            continue
        if line.startswith(HAVE_MARK):
            global LAST_HAVE
            LAST_HAVE = line[len(HAVE_MARK):].strip() or None
            continue
        if line.startswith(RAN_MARK):
            global LAST_RAN
            try:
                LAST_RAN = int(line[len(RAN_MARK):].strip())
            except ValueError:
                LAST_RAN = None
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
    """원격이 가진 커밋을 묻고 → 증분 bundle 을 ssh 로 건네고 → 원격이 돈다.

    반환: 원격 종료 코드 (준비 실패는 PREP_RC 의 코드로 구분된다).

    미커밋 변경이 있으면 돌리되 **통과 기록은 남기지 않는다** — 그 지문은 원격이
    돈 tree의 것이 아니다.
    """
    global LAST_RAN, LAST_HAVE
    LAST_RED[:] = []
    LAST_FLAKY[:] = []
    LAST_RAN = None
    LAST_HAVE = None
    name = name or os.path.basename(REPO)
    dest = f"{REMOTE_DIR}/{name}"
    sha, dirty = head_state()
    # 알림이 「어느 커밋의 결과인가」를 거짓 없이 말하려면 보낸 커밋을 알아야 한다.
    # 훅이 넘긴 시작 sha 와 이것이 다르면 알림이 둘 다 적는다 (REQ-20260907-064).
    global LAST_SHA
    LAST_SHA = sha
    if not sha:
        print("[원격] HEAD 가 없다 — git 저장소에서만 원격으로 간다", file=sys.stderr)
        return 1
    if dirty:
        print(f"[원격] 미커밋 변경 {dirty}개는 원격에 실리지 않는다 — HEAD {sha[:7]} 를 돈다. "
              f"통과 기록은 남기지 않는다(commit 뒤 다시 돌면 남는다)", file=sys.stderr)
    t0 = time.time()
    # ① 원격이 이미 가진 커밋을 묻는다 → ② 그 뒤부터의 증분만 bundle 로 만든다.
    _ssh(key, probe_script(dest), stream=False, timeout=180)
    base = LAST_HAVE if (LAST_HAVE and LAST_HAVE != "none") else None
    if base and _git("cat-file", "-e", base + "^{commit}").returncode != 0:
        base = None                       # 이 머신이 모르는 커밋이면 기준점으로 못 쓴다
    bundle = os.path.join(tempfile.gettempdir(), f"s9ci-{sha[:7]}-{os.getpid()}.bundle")
    args = ["bundle", "create", bundle, "HEAD"] + ([f"^{base}"] if base else [])
    b = _git(*args)
    if b.returncode != 0 or not os.path.exists(bundle):
        print(f"[원격] 커밋 꾸러미(bundle)를 못 만들었다: {b.stderr.strip()[:200]}",
              file=sys.stderr)
        return 1
    size_mb = os.path.getsize(bundle) / 1e6
    print(f"[원격] {key}: {sha[:7]} 을 ssh 로 곧장 건넨다 "
          f"({'증분 ' + base[:7] + '→' if base else '전체 '}{size_mb:.0f}MB). "
          f"원격이 받아 돈다: python3 tests/ --jobs {jobs} {' '.join(pats_argv)[:80]}",
          file=sys.stderr)
    try:
        with open(bundle, "rb") as fh:
            r = _ssh(key, remote_script(sha, dest, jobs, pats_argv, user=_local_user()),
                     stdin=fh, stream=True, timeout=3600)
    finally:
        try:
            os.remove(bundle)
        except OSError:
            pass
    took = time.time() - t0
    global LAST_TOOK
    LAST_TOOK = took
    rc = r.returncode
    # 「돌지 않은 파일이 있으면 통과라고 하지 않는다」 (REQ-20260907-047).
    # 원격이 제 tree에서 고른 파일 수를 표식으로 찍는다. 요청한 수보다 적으면
    # 원격 tree가 이 머신과 다르다는 뜻이니 — 통과가 아니라 **집계 실패**다.
    # 표식이 아예 없어도 통과로 치지 않는다: 셈을 못 했으면 통과를 증명하지 못한다.
    want = len(pats_argv)
    if rc == 0 and want:
        if LAST_RAN is None:
            print(f"[원격] 통과라고 말하지 않는다 — 원격이 몇 파일을 셌는지 표식"
                  f"({RAN_MARK})이 오지 않았다 (요청 {want}개)", file=sys.stderr)
            rc = 97
        elif LAST_RAN < want:
            print(f"[원격] 통과라고 말하지 않는다 — 요청 {want}개인데 원격이 센 것은 "
                  f"{LAST_RAN}개다 ({want - LAST_RAN}개가 원격 tree에 없었다)",
                  file=sys.stderr)
            rc = 98
    if rc == 0:
        print(f"[원격] 통과 ({took:.0f}초 · {LAST_RAN}파일)", file=sys.stderr)
        if on_green and not dirty:
            on_green(fingerprint)
    else:
        why = PREP_RC.get(rc)
        print(f"[원격] 실패 rc={rc}{' — ' + why if why else ''} ({took:.0f}초)",
              file=sys.stderr)
        if on_red:
            on_red()
    return rc
