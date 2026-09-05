"""tests 패키지 실행기 — `python3 tests/ [패턴]` 으로 스위트 실행.

무인(auto-resume) 봉투의 allowlist `Bash(python3 tests/:*)` 는 word-boundary
매칭이라 `python3 tests/test_x.py` 형태를 허용하지 못한다 — 디렉토리 실행
형태(`python3 tests/` + 인자)는 허용되므로 이 러너가 그 진입점이다.

usage:
  python3 tests/                # 전체 (test_*.py discovery)
  python3 tests/ project_assets # 파일명 부분일치 필터
"""
import json
import os
import re
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import portpool  # noqa: E402  (경로를 세운 뒤에 부른다)
import tmproot  # noqa: E402  — portpool 다음에: 포트 락은 /tmp 공용이어야 한다
import jobfile  # noqa: E402  — 긴 실행의 존재를 대시보드에 알린다 (REQ-20260830-022)
import s9cli  # noqa: E402  — 윈도우에서 shebang 을 대신한다 (REQ-20260903-005)

s9cli.install()   # 리눅스·맥에서는 아무것도 하지 않는다 (기준선 불변)


def _reap(label):
    """스위트가 사용자 대시보드 포트에 남긴 서버를 거둔다 (REQ-20260828-001).

    남으면 진짜 서버와 번갈아 응답해 화면이 404 를 내거나, 더 나쁘게는
    테스트 시작 시점의 옛 화면을 내줘 눈으로 하는 검증을 조용히 속인다.
    """
    reaped = portpool.reap_stray_dashboard_servers()
    for p in reaped:
        print(f"[포트 회수/{label}] {portpool.describe_stray(p)}",
              file=sys.stderr)
    return reaped


REPO = os.path.dirname(HERE)
# 스모크 계층 (REQ-20260830-029, quality-assurance 선정): 핵심 계약 12파일,
# 20초대 목표. --smoke 로 부른다. 목록을 고칠 때는 그 REQ 의 근거 노트를 함께.
SMOKE = ("test_state_truth.py", "test_catalog_atomic.py",
         "test_commit_gate.py", "test_note_guard.py", "test_relates_why.py",
         "test_review_point_len.py", "test_changed_select.py",
         "test_jobs_shard.py", "test_stall_trust.py", "test_wake.py",
         "test_closed_no_worker.py", "test_stdlib_only.py")
GREEN_STAMP = os.path.join(REPO, "state", "tests-last-green")
# 이 파일들이 바뀌면 어느 시험이 닿는지 셀 수 없다 — 전체로 물러난다.
COMMON = ("bin/s9", "bin/s9.py", "tests/__main__.py", "tests/portpool.py",
          "tests/tmproot.py", "tests/jobfile.py", "tests/precious.py")


def _git(repo, *a):
    import subprocess
    try:
        # 인코딩을 주변에 맡기지 않는다 (REQ-20260903-005) — `git status` 에는
        # 한글 경로가 섞이고, 윈도우에서 그 바이트를 locale 로 풀다 죽으면
        # 지문이 통째로 없어져 선택이 매번 전체로 물러난다.
        r = subprocess.run(["git", *a], capture_output=True, cwd=repo,
                           timeout=30, encoding="utf-8", errors="replace")
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def changed_selection(repo=None, here=None, stamp=None):
    """--changed 의 선택 (REQ-20260830-027 1단계).

    마지막 전체 green 스탬프 이후 바뀐 파일에 닿는 시험만 고른다 — 같은 날
    전체 스위트를 다섯 번 돌린 낭비가 이 스위치의 존재 이유다.
    반환: None(전체 폴백) · [](돌 것 없음) · [디스커버리 패턴…].
    보수 쪽으로 기운다: 스탬프가 없거나 git 이 안 되면 전체, 미커밋 변경도
    변경으로 센다(더러운 트리에서 놓치는 것보다 다시 도는 게 낫다)."""
    repo = repo or REPO
    here = here or HERE
    stamp = stamp or GREEN_STAMP
    try:
        with open(stamp, encoding="utf-8") as f:
            base = f.read().strip()
    except OSError:
        return None
    if not base:
        return None
    diff = _git(repo, "diff", "--name-only", f"{base}..HEAD")
    porc = _git(repo, "status", "--porcelain")
    if diff is None or porc is None:
        return None      # git 이 안 되면 전체로 물러난다 — 좁게 틀리지 않는다
    files = {ln.strip() for ln in diff.splitlines() if ln.strip()}
    files |= {ln[3:].strip() for ln in porc.splitlines() if len(ln) > 3}
    files.discard("")
    # 문서·상태는 시험을 유발하지 않는다
    files = {f for f in files
             if not f.startswith(("vault/", "state/", "docs/", "projects/",
                                  "users/"))}
    if not files:
        return []
    for f in files:
        if f in COMMON or f.startswith("bin/s9-"):
            return None
    pats, code_basenames = set(), set()
    for f in files:
        b = os.path.basename(f)
        if f.startswith("tests/test_") and f.endswith(".py"):
            pats.add(b)
        else:
            code_basenames.add(b)
    if code_basenames:
        for fn in os.listdir(here):
            if not (fn.startswith("test_") and fn.endswith(".py")):
                continue
            try:
                body = open(os.path.join(here, fn), encoding="utf-8").read()
            except OSError:
                continue
            if any(b in body for b in code_basenames):
                pats.add(fn)
    return sorted(pats)


def write_green_stamp(repo=None, stamp=None):
    """전체 green 만 스탬프를 쓴다 — 부분·실패 실행이 쓰면 --changed 가 거짓말한다."""
    repo = repo or REPO
    stamp = stamp or GREEN_STAMP
    head = (_git(repo, "rev-parse", "HEAD") or "").strip()
    if not head:
        return
    try:
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(head + "\n")
    except OSError:
        pass


# ── 같은 것을 두 번 돌지 않는다 (REQ-20260903-010) ─────────────────────────
# 사용자 지적: "테스트가 너무 오래걸리고 시스템에 부하를 준다 … 동시 요청 작업
# 처리 시 같은 테스트를 스위트라는 명목으로 중복, 중첩 실행되는것을 방지하려는
# 것이다." 실제로 리드와 무인 작업자가 동시에 스위트를 돌린다 — 그러면 같은
# 시험이 두 벌 돌며 서로의 포트·임시자리·CPU 를 뺏는다.
#
# 두 겹으로 막는다.
#   ① **기록** — 선택(패턴 묶음)마다 마지막 green 의 나무 지문을 적어 둔다.
#      지문이 같으면 돌 이유가 없다. 전체 green 스탬프(--changed)의 조카뻘이나,
#      그쪽은 "전체"에만 서고 이쪽은 **어떤 선택에도** 선다.
#   ② **단일비행** — 같은 선택이 이미 돌고 있으면 두 번째는 **기다렸다가 그
#      결과를 받는다.** 새로 돌리지 않는다. 기다림이 끝나면 ①을 다시 보는데,
#      그때 지문이 맞으면 그 실행이 방금 통과시킨 것이라 그대로 쓴다.
#
# 안쪽 실행(S9_TESTS_NESTED)은 둘 다 지나친다 — 바깥이 이미 문을 지났고,
# 여기서 또 잠그면 자기 자신을 기다린다.
_MOD_RE = re.compile(r"\((test_[A-Za-z0-9_]+)\.")
REUSE_DIR = os.path.join(REPO, "state", "tests-green")
RUN_LOCKS = os.path.join(REPO, "state", "jobs")
REUSE_WAIT_SEC = int(os.environ.get("S9_TESTS_WAIT") or 1800)


def _selection_key(pats):
    import hashlib
    raw = "\n".join(sorted(str(p) for p in pats))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# 지문에 안 세는 자리 — 문서·상태·사람 데이터는 시험 결과를 바꾸지 않는다.
FP_SKIP = ("vault/", "state/", "docs/", "projects/", "users/", "index/",
           ".git/")


def tree_fingerprint(repo=None):
    """지금 나무의 지문 — **파일 내용만으로** 잰다. 못 재면 None(늘 다시 돈다).

    보수 쪽으로 기운다: 모르면 **다시 돈다.** 안 돌고 통과로 세는 것보다
    한 번 더 도는 쪽이 싸다.

    **커밋은 지문을 바꾸지 않는다** (REQ-20260904-005). 예전 지문은
    `HEAD 해시 + 미커밋 변경`이었다. 그런데 커밋은 파일 내용을 하나도 안 바꾸면서
    HEAD 를 바꾸고 그 파일들을 미커밋 목록에서 뺀다 — 즉 **같은 나무인데 지문이
    달라진다.** 실측 2026-09-04: 한 무더기를 셋으로 나눠 커밋했더니, 첫 커밋이
    들어간 순간 방금 만든 전체 초록 기록이 무효가 되어 둘째·셋째가 각각 다시
    시험을 물었다(40초 + 5분). 재사용 계층이 「커밋 한 번에 한 번만」 듣는 셈이라
    쪼개 넣을수록 손해였다.

    그래서 git 의 이름(HEAD·스테이지 여부)을 아예 안 본다. 추적 대상과 추적 안 되는
    새 파일의 **내용**만 센다 — 시험 결과를 정하는 것이 그것뿐이기 때문이다.
    비용은 그 자리에 이미 적혀 있다(`_file_mark`): 300여 파일 6.6MB 를 읽어도 수십 ms.
    """
    import hashlib
    repo = repo or REPO
    # -c 추적 중 · -o 추적 안 되는 새 파일 · --exclude-standard .gitignore 존중.
    listing = _git(repo, "ls-files", "-c", "-o", "--exclude-standard")
    if listing is None:
        return None
    names = sorted({ln.strip() for ln in listing.splitlines() if ln.strip()})
    h = hashlib.sha1(b"s9-tree-v2\n")
    counted = 0
    for f in names:
        q = f.replace("\\", "/")
        if q.startswith(FP_SKIP):
            continue
        h.update(_file_mark(os.path.join(repo, f), q))
        counted += 1
    if not counted:
        return None
    return h.hexdigest()


def _file_mark(path, name):
    """이 파일의 지문 한 조각 — **내용**으로 잰다 (REQ-20260903-012).

    예전엔 mtime 이었다. 그런데 스위트를 돌리는 것만으로 mtime 이 움직이는
    파일이 있었다(내용은 그대로인데 시험이 열었다 닫는 자리 — 실측
    2026-09-04: `tests/test_commit_gate.py`, 해시 동일·mtime 이동). 그러면
    전체가 초록이어도 **끝난 순간 지문이 달라져** 그 초록 기록을 아무도 못
    쓴다. `--is-green` 이 늘 1을 내고, 넓은 변경의 커밋 문은 방금 초록을 본
    사람에게도 「돌려라」만 되풀이한다 — 그런 문은 사람이 뽑는 법부터 배운다.

    내용으로 재면 그 되먹임이 끊긴다. 296개 파일 6.6MB 를 읽어도 수십 ms 라,
    한 번 더 도는 값에 비하면 공짜다. 디렉터리(추적 안 되는 새 폴더)는 읽을
    내용이 없으니 이름과 목록으로 센다.
    """
    try:
        if os.path.isdir(path):
            return f"{name}:dir:{','.join(sorted(os.listdir(path)))}\n".encode("utf-8")
        with open(path, "rb") as fh:
            import hashlib as _hl
            return f"{name}:{_hl.sha1(fh.read()).hexdigest()}\n".encode("utf-8")
    except OSError:
        return f"{name}:gone\n".encode("utf-8")


def _reuse_path(pats):
    return os.path.join(REUSE_DIR, _selection_key(pats) + ".json")


def _green_fp(pats):
    """이 선택의 마지막 green 지문 (없으면 None)."""
    try:
        with open(_reuse_path(pats), encoding="utf-8") as f:
            return json.load(f).get("fingerprint")
    except (OSError, ValueError):
        return None


def green_seen(pats, fp, cover=True):
    """이 선택이 이 지문으로 이미 통과했나.

    **전체가 덮는다** (REQ-20260904-005). 자기 선택의 기록이 없어도, 같은
    지문에서 **전체 스위트가 초록**이었으면 그 안의 어떤 선택도 초록이다 —
    선택은 언제나 `discover(HERE)` 안에서 고른 것이라 전체의 부분집합임이
    구조로 보장된다.

    없으면 어떻게 되나(실측 2026-09-04): 전체 297파일을 초록으로 돌린 **직후**
    커밋 문이 그 안의 234파일을 고르면 `_selection_key` 가 달라 「처음 보는
    조합」이 되고, 방금 통과한 시험을 5분에 걸쳐 다시 돌린다. 재사용 계층이
    있는데도 커밋마다 분 단위를 무는 자리가 여기였다.

    이 규칙이 기대는 전제 하나: **시험은 어떤 조합으로 돌려도 같은 답을 낸다.**
    2026-09-04 하루가 통째로 그 전제가 깨진 자리를 쫓은 날이었으므로
    (포트 판정·래퍼 판정) 적어 둔다 — 조합에 따라 답이 갈리는 시험이 남아 있으면
    이 규칙이 그것을 덮는 뚜껑이 된다. 덮이는 것은 **간섭 결함**뿐이고 코드
    결함은 아니다(같은 나무에서 전체가 초록이었으므로).

    `cover=False` 는 「정확히 이 선택」만 묻는다 — `--is-green` 이 그 길로 온다.
    """
    if not fp:
        return False
    if _green_fp(pats) == fp:
        return True
    if cover:
        full = patterns([])
        if sorted(str(p) for p in pats) != sorted(str(p) for p in full):
            return _green_fp(full) == fp
    return False


def mark_green(pats, fp):
    if not fp:
        return
    try:
        os.makedirs(REUSE_DIR, exist_ok=True)
        with open(_reuse_path(pats), "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fp, "at": time.time(),
                       "n": len(pats)}, f)
    except OSError:
        pass


def hold_run_lock(pats):
    """이 선택의 실행권. (파일, 기다렸나) — 기다렸으면 호출자가 기록을 다시 본다.

    윈도우처럼 `fcntl` 이 없는 판에서는 잠그지 않고 그냥 돈다 — 겹침을 막는
    것이 목적이지, 그 판에서 시험을 못 돌게 하는 것이 목적이 아니다.
    """
    try:
        import fcntl
    except ImportError:
        return None, False
    try:
        os.makedirs(RUN_LOCKS, exist_ok=True)
        f = open(os.path.join(RUN_LOCKS,
                              f"tests-{_selection_key(pats)}.lock"), "a+")
    except OSError:
        return None, False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f, False
    except OSError:
        pass
    # 「최대 0분」이라고 말하지 않는다 — 짧은 기다림을 분으로 적으면 0 이 되고,
    # 0 은 「안 기다린다」로 읽힌다.
    how_long = (f"{REUSE_WAIT_SEC // 60}분" if REUSE_WAIT_SEC >= 60
                else f"{REUSE_WAIT_SEC}초")
    print("같은 시험이 이미 돌고 있다 — 새로 돌리지 않고 그 결과를 기다린다 "
          f"(최대 {how_long}, S9_TESTS_WAIT 로 조절).", file=sys.stderr)
    end = time.time() + REUSE_WAIT_SEC
    while time.time() < end:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f, True
        except OSError:
            time.sleep(2.0)
    print("기다림이 끝났다 — 앞 실행이 안 끝나 그냥 돈다.", file=sys.stderr)
    return None, True


def drop_run_lock(fh):
    if fh is None:
        return
    try:
        fh.close()
    except OSError:
        pass


# 공유 상태(실제 repo state/·9909 포트·포트 슬롯 자체)를 만지는 시험 — 병렬
# 본대에 넣으면 서로(또는 자식들의 포트 슬롯을) 밟는다. 부모가 직렬로 돈다.
SERIAL = ("test_jobfile.py", "test_runner_patterns.py", "test_tmp_hygiene.py",
          "test_port_pool.py", "test_install_hooks_path.py",
          "test_doctor_system.py",
          # 계정 전환 live 시험 — 계정 전역 상태를 만져 병렬에서만 흔들린다
          # (2026-08-30 19:26 실측: 단독 4회 green, --jobs 에서 1회 red).
          "test_claude_usage.py",
          # 실서버(이 저장소 뿌리) + 실브라우저를 함께 띄운다 — 실제 repo state/
          # 를 만지고 루프백에 짐을 얹는 쪽이라 본대와 나눠 돈다
          # (REQ-20260831-026). 이웃이 무너지던 건은 그 시험이 연결 오류를
          # 다시 걸게 고쳤다 — 이 줄은 그 대증요법이 아니라 위 규칙의 적용이다.
          "test_project_tab.py",
          # 감시자를 **떼어 놓고** 돌린다 — 그 프로세스는 어느 세션에도 안
          # 매달려 있어, 이웃 갈래의 포트 회수(`--sweep`)가 고아로 보고 거둔다
          # (2026-09-03 실측: 단독 46건 green, --jobs 4 에서 s5 red · s5b 는
          # "감시자가 외부 회수에 거둬졌다"로 skip). 위 규칙의 적용이다.
          "test_serve_guard.py",
          # 성능 벤치 — 1000건과 4000건의 **ms 를 재서** 증분이 직선에서
          # 떨어지는지 본다. 옆에서 샤드 셋이 CPU 를 채우는 동안에는 그 숫자가
          # 무엇을 뜻하는지 알 수 없다(실측 2026-09-04: 15.53 vs 문턱 14.97,
          # 4% 차로 붉었다). 이건 우회가 아니라 **분류**다 — 시계로 재는 시험은
          # 조용한 자리에서만 뜻이 있다. 직렬 꼬리는 본대가 끝난 뒤에 도니
          # 그 자리가 맞다.
          "test_index_incremental.py",
          # 루프백에 **동시 연결 8개**를 한꺼번에 건다. WSL2 에는 동시 연결
          # 벼랑이 있고(DOC-20260827-004), 본대가 이미 짐을 얹은 상태에서는 그
          # 벼랑이 앞당겨져 되걸기로도 못 넘는다. 위 test_project_tab·
          # test_serve_guard 와 같은 규칙의 적용이다.
          "test_streams_scan.py")


TIMES_FILE = os.path.join(REPO, "state", "test-times.json")
TIMES_DIR = os.path.join(REPO, "state", "test-times")


def load_times():
    """파일별 실측 소요 (없으면 {}). 못 읽으면 조용히 빈 값 — 크기로 물러난다."""
    try:
        with open(TIMES_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return {k: float(v) for k, v in d.items() if isinstance(v, (int, float))}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _weights(files):
    """샤딩 무게 — **잰 시간이 있으면 시간**, 없으면 크기 (REQ-20260905-001).

    종전 무게는 `os.path.getsize` 였다. 「큰 파일이 오래 걸린다」는 가정인데
    이 저장소에서 거짓이다 — 서버를 띄우는 작은 파일 하나가 큰 grep 시험 열
    개보다 비싸다. 실측 2026-09-05: 43파일 선택이 297파일 전체보다 오래
    걸렸다(757초 vs 514초). 무엇을 도느냐는 안 바뀌고 **어느 빈에 넣느냐**만
    바뀌므로 위험이 없다.

    아는 값이 절반도 안 되면(첫 실행·새 기계) 크기로 물러난다 — 없는 값으로
    판단하지 않는다. 아는 값이 충분한데 그중 빠진 파일은 **중앙값**으로 친다:
    0 으로 치면 새 파일이 전부 한 빈에 몰린다.
    """
    times = load_times()
    known = [times[f] for f in files if f in times]
    if len(known) * 2 < len(files):
        return {f: os.path.getsize(os.path.join(HERE, f)) for f in files}
    mid = sorted(known)[len(known) // 2] if known else 1.0
    return {f: times.get(f, mid) for f in files}


def shard(files, n):
    """파일들을 무게 내림차순 greedy 로 N 빈에 — 느린 것부터 자리 잡아야
    꼬리가 짧다 (REQ-20260830-027 2단계). 무게는 `_weights` 가 정한다
    (실측 시간 > 크기, REQ-20260905-001). 반환: 빈 리스트들(빈 빈 제외)."""
    w = _weights(files)
    bins = [[0, []] for _ in range(max(1, n))]
    for f in sorted(files, key=lambda x: -w.get(x, 0)):
        b = min(bins, key=lambda x: x[0])
        b[0] += w.get(f, 0)
        b[1].append(f)
    return [b[1] for b in bins if b[1]]


def record_times(per_file):
    """이 실행이 잰 것을 pid 별 파일로 남긴다 — 부모가 합친다.

    한 파일에 바로 쓰면 병렬 샤드 넷이 서로를 덮는다(B4). 재는 것은 자식들이고
    합치는 것은 부모다.
    """
    if not per_file:
        return
    try:
        os.makedirs(TIMES_DIR, exist_ok=True)
        with open(os.path.join(TIMES_DIR, f"{os.getpid()}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(per_file, f)
    except OSError:
        pass


def merge_times():
    """pid 별 기록을 한 파일로 합친다 (부모만). 새 값이 이긴다 — 시험은 바뀐다."""
    merged = load_times()
    try:
        names = os.listdir(TIMES_DIR)
    except OSError:
        return
    got = False
    for fn in names:
        fp = os.path.join(TIMES_DIR, fn)
        try:
            with open(fp, encoding="utf-8") as f:
                merged.update({k: float(v) for k, v in json.load(f).items()})
            os.unlink(fp)
            got = True
        except (OSError, ValueError, TypeError, AttributeError):
            try:
                os.unlink(fp)
            except OSError:
                pass
    if not got:
        return
    try:
        tmp = TIMES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f)
        os.replace(tmp, TIMES_FILE)
    except OSError:
        pass


def matched_files(pats):
    """디스커버리 패턴들이 고르는 시험 파일 목록 (파일 단위 샤딩용)."""
    import fnmatch
    out = []
    for fn in sorted(os.listdir(HERE)):
        if fn.startswith("test_") and fn.endswith(".py") and                 any(fnmatch.fnmatch(fn, p) for p in pats):
            out.append(fn)
    return out


def _started_in(pending, state):
    """아직 도는 샤드들에서 **시작된 시험 파일 수** (REQ-20260904-004).

    자식은 unittest 를 verbose 로 돌리므로 줄마다 `(test_모듈.클래스.시험)` 이
    찍힌다. 거기서 모듈 이름만 모으면 「이 샤드가 몇 번째 파일까지 왔나」가
    나온다 — 자식에게 따로 보고 배선을 넣지 않고도 진행이 흐른다.

    **새로 늘어난 만큼만 읽는다.** 처음엔 매번 파일을 통째로 읽었는데, 출력이
    수 MB 로 자라는 후반에는 그것이 초당 두 번씩 수십 MB 를 읽고 정규식을 다시
    거는 일이 됐다 — 진행 표시가 샤드에게서 CPU 를 뺏어 **스위트가 420초에서
    585초 밖으로 밀렸다**(실측 2026-09-04, 같은 나무에서 두 번 시간 초과).
    표시를 위해 재는 값이 재려는 대상을 느리게 만들면 그 표시는 거짓말이 된다.
    `state` 는 파일마다 (다음에 읽을 자리, 지금까지 본 모듈)을 들고 있다.
    경계에 걸려 잘린 이름을 놓치지 않도록 200자만 겹쳐 읽는다.

    읽기가 실패해도(파일이 사라졌든 인코딩이 깨졌든) 그 샤드는 세지 않는다.
    진행 표시 때문에 시험 실행이 죽는 것은 본말전도다.
    """
    seen = 0
    for _pr, out, group in pending:
        st = state.setdefault(out.name, [0, set()])
        try:
            with open(out.name, encoding="utf-8", errors="replace") as fh:
                fh.seek(st[0])
                chunk = fh.read()
                st[0] = max(0, fh.tell() - 200)
        except (OSError, ValueError):
            continue
        if chunk:
            st[1].update(_MOD_RE.findall(chunk))
        seen += min(len(st[1]), len(group))
    return seen


def jobs_cap():
    """--jobs 의 상한 — 값은 bin/s9 의 CONCURRENCY 한 표에서 온다.

    환경변수(S9_MAX_JOBS)가 있으면 그것, 없으면 **표의 기본값을 소스에서
    읽는다.** 여기 숫자를 또 적으면 갈린다 — 실측 2026-09-05: 표를 8 로 올렸는데
    러너가 제 몫 4 로 묶어, 「8샤드 최종 실행」이 실은 4샤드였다(410초).
    bin/s9 를 import 하지 않는 이유는 그것이 무겁고 부작용이 있어서다 — 글자
    하나를 읽는 데 만 팔천 줄을 실행할 이유가 없다. 표가 갈리는지는
    test_concurrency 가 지킨다.
    """
    try:
        cap = int((os.environ.get("S9_MAX_JOBS") or "").strip())
        if cap > 0:
            return cap
    except ValueError:
        pass
    try:
        src = open(os.path.join(REPO, "bin", "s9.py"), encoding="utf-8").read()
        m = re.search(r'"test_jobs":\s*int\(_envnum\("S9_MAX_JOBS",\s*(\d+)', src)
        if m:
            return int(m.group(1))
    except OSError:
        pass
    return 4


FLAKY_FILE = os.path.join(REPO, "state", "test-flaky.jsonl")
# 샤드·직렬 꼬리의 시간 상한 (REQ-20260905-021). 러너는 **절대 멈추지 않는다** —
# 실측 2026-09-05: 배경 전체 실행이 304/305 에서 20분 정지(서버 무응답 계열)했고
# 그 뒤에 선 러너·커밋 문이 30분을 기다렸다. 넘기면 죽이고 그 파일들을 붉음으로 적는다.
SHARD_TIMEOUT_SEC = float(os.environ.get("S9_SHARD_TIMEOUT", "900"))


def overdue(started, now, limit=None):
    """이 샤드가 상한을 넘겼나."""
    limit = SHARD_TIMEOUT_SEC if limit is None else limit
    return limit > 0 and (now - started) > limit
LAST_RUN_RED = []            # 마지막 병렬 실행의 붉은 파일 (record_last_red 재료)
RETRY_MAX_FILES = 3


def red_files_from(text):
    """샤드 출력에서 붉은 시험의 **파일**을 뽑는다 — `FAIL: name (test_mod.Class.name)`."""
    out = []
    for m in re.finditer(r"^(?:FAIL|ERROR): \S+ \((test_[A-Za-z0-9_]+)\.", text, re.M):
        f = m.group(1) + ".py"
        if f not in out:
            out.append(f)
    return out


def should_retry(red):
    """붉은 파일이 적을 때만(≤3) 그것만 한 번 더 돈다 — 넷 이상은 코드 결함이다.

    실사고 2026-09-05 (REQ-20260905-009): 전체 스위트 20회 중 10회가 간헐 붉음
    (매번 다른 서버 시험 1~3건, 단독 재실행은 초록)이었고, 그때마다 전체를
    다시 돌려 하루 1시간 45분을 기다렸다. 규약 17조가 말한 대로 **붉은 것만
    좁혀서** 다시 돈다 — 붉은 파일 하나는 수초, 전체는 5~13분이다.
    `S9_TEST_NO_RETRY=1` 이면 재실행하지 않는다(러너 자신을 재는 시험용).
    """
    if os.environ.get("S9_TEST_NO_RETRY") == "1":
        return False
    return 0 < len(red) <= RETRY_MAX_FILES


def record_flaky(files, note):
    """단독 재실행에서 초록으로 바뀐 파일을 남긴다 — 간헐의 증거이자 격리의 재료."""
    try:
        os.makedirs(os.path.dirname(FLAKY_FILE), exist_ok=True)
        with open(FLAKY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "files": files, "note": note},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def run_sharded(pats, jobs, bump=None):
    """병렬 본대 + 직렬 꼬리 (REQ-20260830-027 2단계).

    자식은 `python3 tests/ <파일…>` + S9_TESTS_NESTED=1 — reap·잡파일·바깥
    sweep 을 건드리지 않고 tmproot 는 pid 별로 저절로 격리된다. 실패한 자식의
    원출력은 그대로 재생한다 — 병렬 뒤에 실패가 숨으면 이 구조 전체가 거짓이
    된다. 반환: (ok, 돈 파일 수)."""
    import subprocess
    import tempfile
    files = matched_files(pats)
    body = [f for f in files if f not in SERIAL]
    tail = [f for f in files if f in SERIAL]
    procs = []
    # 포트 칸 수를 샤드 수에 맞춘다 (REQ-20260905-001) — 칸이 넷으로 못박혀
    # 있으면 다섯째 샤드부터 자기 자리가 없어 같은 포트를 두고 다툰다. 실측:
    # 칸이 4 로 못박혔을 때 4·6·10 샤드가 525·518·520초로 평평했고 코어는 83%
    # 놀았다. 칸을 맞춘 뒤 6→343 · 8→317 · 10→295초 (2026-09-05, 14코어).
    env = {**os.environ, "S9_TESTS_NESTED": "1",
           "S9_TEST_PORT_SLOTS": str(max(4, jobs))}
    t_start = time.time()
    for group in shard(body, jobs):
        out = tempfile.NamedTemporaryFile(mode="w+", suffix=".shard",
                                          delete=False)
        # **stdin 을 끊어서 넘긴다** (REQ-20260903-012). 안 끊으면 자식이 부모의
        # stdin 을 물려받는데, 커밋 훅 아래에서 그것은 EOF 가 오지 않는 소켓이다.
        # 그러면 시험이 부른 `s9` 가 입력을 기다리며 **영원히 선다** — 실측
        # 2026-09-04: `s9 new request` 하나가 1시간 41분을 그렇게 서 있었고,
        # 게이트가 통째로 멈춰 커밋이 끝나지 않았다. 실패보다 나쁘다: 실패는
        # 보이는데 멈춤은 「오래 걸리나 보다」로 보인다.
        #
        # 자식마다 고치는 대신 여기서 한 번 끊는다 — 시험이 stdin 을 물려주는
        # 것을 잊어도 EOF 를 즉시 받아 제 갈 길을 간다.
        pr = subprocess.Popen(
            [sys.executable, HERE, *group],
            stdin=subprocess.DEVNULL,
            stdout=out, stderr=subprocess.STDOUT, env=env)
        procs.append((pr, out, group))
    ok = True
    done_files = 0
    red = []                 # 붉은 파일 — 적으면 그것만 한 번 더 돈다
    import time as _time
    pending = list(procs)
    seen_state = {}          # 샤드 출력의 {이름: [다음에 읽을 자리, 본 모듈]}
    while pending:
        _time.sleep(0.5)
        # **도는 중을 도는 것으로 보이게 한다** (REQ-20260904-004). 예전엔
        # 샤드가 하나 끝날 때만 진행을 올렸다 — 샤드 하나가 5분 넘게 도니 그
        # 동안 잡 파일의 mtime 이 멈췄고, 화면은 그 mtime 으로 「N초 잠잠」을
        # 그렸다. 멀쩡히 도는 것이 멈춘 것과 똑같이 보이면, 진짜로 멈춘 날에
        # 아무도 알아채지 못한다 — 2026-09-04 에 리드가 그 착각으로 1시간
        # 41분을 기다렸다.
        if bump:
            bump(done_files + _started_in(pending, seen_state))
        still = []
        for pr, out, group in pending:
            if pr.poll() is None:
                if overdue(t_start, _time.time()):
                    # 상한 초과 — 죽이고 붉음으로 센다. 무엇이 멈췄는지는 그 샤드의
                    # 출력(마지막 줄)이 말한다.
                    try:
                        pr.kill()
                    except OSError:
                        pass
                    pr.wait(timeout=10)
                    ok = False
                    red.extend(f for f in group if f not in red)
                    print(f"[상한] 샤드가 {int(SHARD_TIMEOUT_SEC)}초를 넘겨 죽였다: "
                          f"{' '.join(group)}", file=sys.stderr)
                    done_files += len(group)
                    continue
                still.append((pr, out, group))
                continue
            done_files += len(group)
            if bump:
                bump(done_files + _started_in(still, seen_state))
            if pr.returncode != 0:
                ok = False
                out.flush()
                try:
                    text = open(out.name, encoding="utf-8", errors="replace").read()
                except OSError:
                    text = ""
                sys.stderr.write(text)
                found = red_files_from(text)
                red.extend(f for f in (found or list(group)) if f not in red)
                print(f"실패한 샤드: {' '.join(group)}", file=sys.stderr)
        pending = still
    for pr, out, _g in procs:
        try:
            out.close()
            os.unlink(out.name)
        except OSError:
            pass
    for f in tail:      # 직렬 꼬리 — 부모 프로세스에서, 공유 상태를 독점하고
        try:
            r = subprocess.run([sys.executable, HERE, f], env=env,
                               stdin=subprocess.DEVNULL,   # 꼬리도 같은 규칙
                               timeout=SHARD_TIMEOUT_SEC or None)
        except subprocess.TimeoutExpired:
            print(f"[상한] 직렬 꼬리 {f} 가 {int(SHARD_TIMEOUT_SEC)}초를 넘겨 죽였다",
                  file=sys.stderr)
            ok = False
            if f not in red:
                red.append(f)
            done_files += 1
            if bump:
                bump(done_files)
            continue
        done_files += 1
        if bump:
            bump(done_files)
        if r.returncode != 0:
            ok = False
            if f not in red:
                red.append(f)
    LAST_RUN_RED[:] = red
    if not ok and should_retry(red):
        print(f"[좁혀서 다시] 붉은 파일 {len(red)}개만 단독으로 한 번 더 돈다: "
              f"{' '.join(red)}", file=sys.stderr)
        r = subprocess.run([sys.executable, HERE, "--no-reuse", *red], env=env,
                           stdin=subprocess.DEVNULL)
        if r.returncode == 0:
            ok = True
            record_flaky(red, "샤드에서 붉음 · 단독 초록")
            print(f"[좁혀서 다시] 단독 초록 — 간헐로 기록했다 ({FLAKY_FILE}). "
                  f"두 번째 보이면 격리하고 REQ 로 세워라.", file=sys.stderr)
    return ok, done_files


def patterns(argv):
    """인자들을 discovery 패턴으로 바꾼다 (REQ-20260829-006).

    커밋 게이트는 담긴 테스트 이름을 **여럿** 넘긴다. 예전에는 sys.argv[1] 만
    써서 두 번째부터는 아무 말 없이 안 돌았고, 게이트는 그걸 통과로 읽었다.

    'x' · 'test_x' · 'tests/test_x.py' 세 형태를 모두 받는다.
    """
    out = []
    for a in argv:
        raw = (a or "").strip().removeprefix("tests/")
        # 정확한 파일명은 넓히지 않는다 (REQ-20260830-029): --smoke·--changed 가
        # 고른 test_wake.py 를 test_*wake*.py 로 넓히면 wake 계열 전부가
        # 끌려와 계층·선택의 뜻이 사라진다. 사람이 치는 조각(wake)만 넓힌다.
        if raw.startswith("test_") and raw.endswith(".py"):
            out.append(raw)
            continue
        frag = raw.removesuffix(".py").removeprefix("test_")
        if frag:
            out.append(f"test_*{frag}*.py")
    return out or ["test_*.py"]


def flatten(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from flatten(t)
        else:
            yield t


# ---------- 파일 사이의 환경 격리 (REQ-20260904-002) ----------
#
# `os.environ` 은 **프로세스 전체의 것**인데 순차 실행은 297개 파일을 한
# 프로세스에서 돈다. 그래서 앞 파일이 `setUpClass` 에서 놓고 간 값을 뒤 파일이
# 전부 물려받는다 — 실측으로 `S9_USER` 하나가 test_jobfile 의 귀속 시험을
# 넘어뜨렸고(문서 순서 15·33·48 → 114), 전체 실행마다 붉은 파일의 **조합이
# 달라졌다**. 홀로는 초록이라 사람이 「알 수 없는 흔들림」으로 넘기게 되고,
# 그러면 스위트가 붉은 채로 굳는다.
#
# 되돌리는 자리를 하나로 둔다: **클래스가 바뀔 때만** S9_* 를 기준선으로
# 되돌린다. 클래스 안에서는 그 클래스가 세운 값이 그대로 산다 — 격리를 주는
# 것이지 빼앗는 것이 아니다.
#
# 기준선을 **discovery 뒤**에 뜨는 까닭: unittest 은 모든 모듈을 먼저 import
# 하므로 모듈 최상위에서 세운 값은 그 시점에 이미 들어와 있다. 그것까지
# 기준선으로 인정해야 지금 도는 파일들이 그대로 돈다.

ENV_PREFIX = "S9_"


def env_baseline():
    """되돌릴 기준선 — 지금의 S9_* 전부."""
    return {k: v for k, v in os.environ.items() if k.startswith(ENV_PREFIX)}


def env_restore(base):
    """S9_* 만 기준선으로. 다른 변수는 손대지 않는다(PATH·HOME·TMPDIR…)."""
    for k in [k for k in os.environ if k.startswith(ENV_PREFIX)]:
        if k not in base:
            del os.environ[k]
    for k, v in base.items():
        if os.environ.get(k) != v:
            os.environ[k] = v


class EnvIsolatingSuite(unittest.TestSuite):
    """클래스 경계에서 환경을 되돌리는 스위트.

    `_handleClassSetUp` 은 매 시험마다 불리지만 클래스가 그대로면 곧 돌아
    나온다. 그 판정과 **같은 조건**(result._previousTestClass)으로 되돌림을
    건다 — 조건을 따로 세우면 언젠가 둘이 갈린다.
    """

    baseline = None

    def _handleClassSetUp(self, test, result):
        if self.baseline is not None and \
                getattr(result, "_previousTestClass", None) is not test.__class__:
            env_restore(self.baseline)
        super()._handleClassSetUp(test, result)


def discover(pats):
    """패턴마다 모아 합친다. 반환: (스위트, 아무것도 못 고른 패턴들).

    같은 파일이 두 패턴에 걸리면 테스트 id 로 한 번만 담는다 — 두 번 도는 것은
    낭비이고, 상태를 쓰는 테스트에서는 두 번째가 첫 번째의 잔재를 본다.
    """
    seen, cases, empty = set(), [], []
    for pat in pats:
        picked = 0
        for t in flatten(unittest.defaultTestLoader.discover(HERE,
                                                             pattern=pat)):
            picked += 1
            tid = t.id()
            if tid in seen:
                continue
            seen.add(tid)
            cases.append(t)
        if picked == 0:
            empty.append(pat)
    return EnvIsolatingSuite(cases), empty


def full_suite_green(repo=None):
    """지금 이 나무에서 **전체 스위트**가 초록이었던 적이 있나 (REQ-20260903-012).

    스위트를 돌리지 않는다 — 기록 하나를 볼 뿐이다. 커밋 게이트가 이것을 묻는다:
    전체를 매번 돌리면 규율이 먼저 죽고, 아무것도 안 보면 붉은 채로 들어간다.
    지문을 못 재면(git 밖 등) **모른다고 답한다** — 모르는 것을 초록으로 세면
    이 문이 있으나 마나다.
    """
    fp = tree_fingerprint(repo)
    # cover=False: 「전체가 초록이었나」는 전체 기록으로만 답한다 — 부분집합
    # 기록으로 그렇다고 답하면 넓은 변경의 커밋 문이 거짓 초록을 본다.
    return bool(fp) and green_seen(patterns([]), fp, cover=False)


LAST_RED = os.path.join(REPO, "state", "tests-last-red.json")


def record_last_red(files, fp=None):
    """전체 실행이 붉었다는 기록 — 커밋 문의 **붉음 라쳇** 재료 (REQ-20260905-010).

    전체 스위트는 commit 뒤 배경에서 돈다. 그래서 붉음은 막는 대신 **남겨야**
    한다: 마지막 붉음이 마지막 초록보다 새로우면 다음 code 커밋을 세운다.
    """
    try:
        os.makedirs(os.path.dirname(LAST_RED), exist_ok=True)
        with open(LAST_RED, "w", encoding="utf-8") as f:
            json.dump({"at": time.time(), "fingerprint": fp or "",
                       "files": list(files)}, f, ensure_ascii=False)
    except OSError:
        pass


def last_red():
    """마지막 전체 붉음 기록 또는 None."""
    try:
        with open(LAST_RED, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def full_green_age(repo=None):
    """마지막 **전체 스위트** 초록 기록의 나이(초) — 나무가 달라도 센다. 없으면 None.

    넓게 닿는 파일의 작은 변경을 커밋할 때 게이트가 묻는다 (REQ-20260905-009):
    지금 나무의 전체 초록은 없어도, 몇 시간 안에 전체가 초록이었고 스모크∪변경이
    지금 초록이면 커밋을 세우지 않는다 — 전체는 뒤에 한 번 돌려 두면 된다.
    """
    try:
        with open(_reuse_path(patterns([])), encoding="utf-8") as f:
            at = float(json.load(f).get("at") or 0)
    except (OSError, ValueError, TypeError):
        return None
    return max(0.0, time.time() - at) if at else None


def main():
    # 돌리지 않고 묻기만 하는 갈래 (REQ-20260903-012) — 커밋 게이트가 쓴다.
    # 임시 루트도 만들지 않는다: 이 갈래는 시험을 한 건도 돌지 않는다.
    if "--is-green" in sys.argv[1:]:
        return 0 if full_suite_green() else 1
    if "--full-green-age" in sys.argv[1:]:
        age = full_green_age()
        print("none" if age is None else int(age))
        return 0
    # 원격에서 돌린다 (REQ-20260905-012) — `--remote KEY` · S9_TEST_REMOTE · state/test-remote.
    # 이 머신은 보내고 기다리고 기록만 한다. `--remember` 는 KEY 를 파일에 남겨
    # 다음부터 `python3 tests/` 만 쳐도 원격으로 간다(--local 로 한 번 끈다).
    import remote_run
    argv0 = sys.argv[1:]
    explicit = "--remote" in argv0
    # 기억된 원격은 **전체 실행**에만 쓴다 — 스모크·게이트·표적·--changed 는 이
    # 머신의 작업 나무(미커밋 포함)를 재야 하는 자리라 여기서 돈다. 실측 2026-09-05:
    # 기억시키자 커밋 문의 스모크까지 원격으로 가서 게이트가 넘어졌다.
    wants_full = remote_run.is_full_invocation(argv0)
    rkey = None if "--local" in argv0 else (remote_run.remote_key() if (explicit or wants_full) else None)
    if rkey and os.environ.get("S9_TESTS_NESTED") != "1":
        raw = [a for a in sys.argv[1:] if a not in ("--remember", "--local")]
        if "--remote" in raw:
            i = raw.index("--remote"); raw = raw[:i] + raw[i + 2:]
        if "--remember" in sys.argv[1:]:
            remote_run.remember(rkey)
        jobs = 16
        if "--jobs" in raw:
            i = raw.index("--jobs"); jobs = int(raw[i + 1]); raw = raw[:i] + raw[i + 2:]
        pats_argv = [a for a in raw if a not in ("--no-reuse",)]
        fp = tree_fingerprint()
        full = not [a for a in pats_argv if not a.startswith("--")]
        # 원격이 못 도는 것(LOCAL_ONLY)은 갈라 이 머신이 마저 돈다
        selected = matched_files(patterns([a for a in pats_argv if not a.startswith("--")]))
        local_part = [f for f in selected if f in remote_run.LOCAL_ONLY]
        remote_part = [f for f in selected if f not in remote_run.LOCAL_ONLY]
        rc = remote_run.run_remote(rkey, remote_part, jobs=jobs, fingerprint=fp)
        _sha, dirty = remote_run.head_state()
        if local_part:
            print(f"[원격] 이 머신에서 마저 돈다: {' '.join(local_part)}", file=sys.stderr)
            r2 = subprocess.run([sys.executable, HERE, "--local", "--no-reuse", *local_part],
                                stdin=subprocess.DEVNULL)
            rc = rc or r2.returncode
        if rc == 0 and full and fp and not dirty:
            mark_green(patterns([]), fp)
            print("[원격] 전체 초록 — 이 나무의 초록 기록을 남겼다", file=sys.stderr)
        elif rc != 0 and full:
            record_last_red(["(원격)"], fp)
        return rc
    # 스위트 안에서 러너를 또 띄우는 시험이 있다(test_runner_patterns·
    # test_tmp_hygiene). 그 안쪽 실행이 바깥 실행의 세계를 청소하면 안 된다 —
    # 포트 회수는 '임시 작업공간에서 뜬 대시보드 서버'를 죽이는데, 그게 바로
    # 바깥 스위트가 지금 쓰고 있는 서버일 수 있다. 안쪽은 제 임시 루트만 챙긴다.
    nested = os.environ.get("S9_TESTS_NESTED") == "1"
    if not nested:
        _reap("시작 전")      # 지난 실행의 잔재는 이번 실행의 책임이 아니다
        stale = tmproot.sweep_stale()
        if stale:
            print(f"[임시자리 회수/시작 전] 지난 실행 잔재 {len(stale)}개",
                  file=sys.stderr)
    # 이 실행이 만드는 임시 자리는 전부 여기 안에 생기고 끝나면 함께 사라진다
    # (REQ-20260829-003). 84개 파일에 tearDown 을 심는 대신 문을 여기서 닫는다.
    #
    # **discovery 보다 먼저** 세운다. discovery 는 테스트 모듈을 import 하는데,
    # 여럿이 모듈 수준에서 `TMP = tempfile.mkdtemp(...)` 를 부른다(test_tags,
    # test_session_wake, test_link_integrity, …). 루트를 나중에 세우면 그것들이
    # 문 밖에 생겨 그대로 남는다 — 전체 스위트 1회에 22개가 그렇게 샜다.
    tmp_root, prev_tmpdir = tmproot.make_run_root()
    ok, empty, leaked, ran = False, [], [], False
    pats, fp, lock_fh = [], None, None
    try:
        # 원격 손잡이는 여기서 걷는다 — 패턴으로 읽히면 「고르지 못한 패턴」이 된다
        raw = [a for a in sys.argv[1:] if a not in ("--local", "--remember")]
        jobs = 0
        if "--jobs" in raw:
            i = raw.index("--jobs")
            jobs = int(raw[i + 1]) if i + 1 < len(raw) else 4
            raw = raw[:i] + raw[i + 2:]
            # **동시 최고치가 곧 비용이다** (REQ-20260903-004). 갈래 하나가
            # 서버·브라우저·연결을 함께 여니, 병렬 수는 그 전부의 곱이 된다.
            # 상한은 bin/s9 · bin/s9-doctor 의 CONCURRENCY 한 표에서 오고
            # (S9_MAX_JOBS), 여기서는 그 값으로 묶기만 한다 — 판정을 두 벌로
            # 들지 않는다. 사용자가 짚은 자리가 이것이다: "동시에 여러 요청
            # 작업을 할 때 테스트가 몰리면".
            cap = jobs_cap()
            if jobs > cap:
                print(f"--jobs {jobs} → {cap} 로 묶는다 (동시 상한, "
                      f"S9_MAX_JOBS 로 올릴 수 있다)", file=sys.stderr)
                jobs = cap
        # --smoke: 핵심 계약 12파일 · --gate: 스모크 ∪ --changed (커밋 게이트용,
        # QA 판정: --changed 단독은 bin/s9 변경이 전체 폴백이라 게이트로 부족)
        smoke = "--smoke" in raw or "--gate" in raw
        if "--gate" in raw and "--changed" not in raw:
            raw.append("--changed")
        argv = [a for a in raw
                if a not in ("--changed", "--smoke", "--gate", "--no-reuse")]
        full_requested = not argv and not smoke
        sel = None
        if "--changed" in raw:
            sel = changed_selection()
            if sel == [] and not smoke:
                print("변경 없음 — 마지막 전체 green 이후 시험에 닿는 파일이 "
                      "바뀌지 않았다. 아무것도 돌리지 않는다.", file=sys.stderr)
                return 0
            if sel is not None:
                argv = sel          # 파일명 자체가 부분일치 패턴으로 먹힌다
                full_requested = False
            elif smoke:
                argv = []           # --gate 에서 전체 폴백이면 스모크 ∪ 전체 = 전체
                smoke_full_fallback = True
            # None 이면 전체 폴백 — argv 그대로(비어 있음 = 전체)
        if smoke and not (sel is None and "--gate" in sys.argv[1:]):
            argv = sorted(set(argv) | set(SMOKE))
            full_requested = False
        pats = patterns(argv)
        # 이 실행이 **어떤 종류인가** (REQ-20260905-006 2차). 사용자가 물은 것은
        # 1차와 같다: 얼마나 기다리나. 같은 「14/211건」이라도 전체 스위트(4분+)
        # 와 스모크(20초대)는 기다림의 성격이 다르다.
        #
        # **판정은 여기 한 줄뿐이다.** 잡 파일의 `args` 로 되짚을 수도 있었지만
        # 그것은 이미 아는 값을 문자열에서 다시 알아내려는 두 번째 판정이고,
        # 실제로 틀린다: `args` 는 `sys.argv[1:4]` 라 네 번째 낱말부터 잘리고
        # (`--no-reuse --jobs 8 foo` 는 전체로 읽힌다), `--changed` 는 명령줄에
        # 고른 파일이 아예 안 적혀 있어 되짚을 길이 없다. 여기서는 **고르기가
        # 끝난 뒤의 argv** 를 보므로 그 갈래가 전부 제자리에 온다:
        # 빈 argv = 전체(게이트가 전체로 물러난 경우 포함) · smoke = 스모크 ·
        # 그 밖(패턴·`--changed` 가 고른 파일) = 표적.
        job_kind = "full" if not argv else ("smoke" if smoke else "targeted")
        # **같은 것을 두 번 돌지 않는다** (REQ-20260903-010).
        # ① 이 선택이 지금 나무 지문으로 이미 통과했으면 그대로 쓴다.
        # ② 같은 선택이 돌고 있으면 기다렸다가 그 결과를 받는다.
        # `--no-reuse` 로 둘 다 건너뛴다(정말 다시 돌려야 할 때).
        # **잠금은 언제나, 재사용은 고를 수 있게.** `--no-reuse` 는 "기록을
        # 믿지 말고 다시 돌라"는 뜻이지 "남과 겹쳐 돌아도 된다"가 아니다 —
        # 처음에 그렇게 짰다가 둘이 나란히 도는 것을 실측으로 봤다.
        reuse = ("--no-reuse" not in sys.argv[1:]) and not nested
        fp = tree_fingerprint() if not nested else None
        if reuse and green_seen(pats, fp):
            # 무엇이 덮었는지 말한다 — 「안 돌았다」만 보이면 사람이 문을
            # 의심한다 (REQ-20260904-005).
            why = ("이 선택이 방금 통과했다" if _green_fp(pats) == fp
                   else "이 나무에서 전체 스위트가 이미 초록이다")
            print(f"바뀐 것이 없다 — {why}. 다시 돌지 않는다 "
                  "(`--no-reuse` 로 강제).", file=sys.stderr)
            return 0
        if not nested:
            lock_fh, waited = hold_run_lock(pats)
            if waited and reuse:
                fp = tree_fingerprint()
                if green_seen(pats, fp):
                    print("앞 실행이 같은 것을 통과시켰다 — 그 결과를 쓴다.",
                          file=sys.stderr)
                    drop_run_lock(lock_fh)
                    return 0
        if jobs > 1 and not nested:
            files = matched_files(pats)
            if not files:
                print(f"no tests matched: {', '.join(pats)}", file=sys.stderr)
                return 1
            bump, clear = jobfile.start(len(files), kind=job_kind,
                                        args=" ".join(sys.argv[1:4]))
            try:
                ran = True
                ok, _n = run_sharded(pats, jobs, bump=bump)
            finally:
                clear()
                # 샤드 자식들이 남긴 소요를 여기서 합친다 (REQ-20260905-001).
                # 병렬 경로는 이 함수의 아래쪽 순차 블록을 아예 안 지나므로,
                # 합치는 자리가 거기에만 있으면 **재고도 안 쓰는** 기록이 된다
                # (실측: 첫 실행이 297파일을 돌고 4파일만 남겼다).
                merge_times()
            if ok:
                mark_green(pats, fp)
            elif full_requested:
                record_last_red(LAST_RUN_RED, fp)
                if full_requested:
                    write_green_stamp()
            drop_run_lock(lock_fh)
            return 0 if ok else 1
        # 로컬 서버에 두드리는 시험 전부에 되걸기를 입힌다 (REQ-20260904-003) —
        # 되걸기 없이 두드리는 파일이 15개였고, 실행마다 희생자가 바뀌었다.
        try:
            import portpool as _pp
            _pp.install_urlopen_retry()
        except Exception:
            pass                    # 되걸기가 없어도 시험은 돌아야 한다
        suite, empty = discover(pats)
        # 기준선은 discovery(=모든 모듈 import) **뒤**에 뜬다 — 위 주석 참조.
        EnvIsolatingSuite.baseline = env_baseline()
        for p in empty:
            print(f"no tests matched: {p}", file=sys.stderr)
        if suite.countTestCases() == 0:
            return 1
        # 잡 파일 (REQ-20260830-022): 이 실행이 도는 동안 화면 헤더 칩과 카드가
        # "테스트 N분째 · M건" 을 그린다. 안쪽 실행(S9_TESTS_NESTED)은 안 쓴다.
        bump, clear = jobfile.start(suite.countTestCases(), kind=job_kind,
                                    args=" ".join(sys.argv[1:4]))

        # 파일별 소요를 잰다 (REQ-20260905-001) — 샤딩 무게의 원천이다.
        #
        # **시험 하나의 실행만 재면 비싼 것이 0 으로 보인다.** 처음엔
        # startTest~stopTest 를 쟀는데, 이 저장소의 비용은 대부분 `setUpClass`
        # 에 있다(서버를 띄우고 `s9 init` 을 돌린다) — 그 자리는 그 사이에
        # 없다. 실측 2026-09-05: `test_live_worker_scope` 가 기록 0.0초인데
        # 실제 3.3초, 「합 0.29초」인 60파일이 벽시계로 60.8초였다. 그 무게로
        # 샤딩하면 가장 비싼 파일을 가장 가볍다고 믿는다.
        #
        # 그래서 **직전 시험이 끝난 뒤부터 이 시험이 끝날 때까지**를 이 시험의
        # 모듈에 얹는다. 클래스 준비·정리에 든 시간이 그 사이에 통째로 들어와,
        # 파일별 합이 벽시계에 맞는다.
        per_file = {}
        last_ts = [time.time()]

        class _Result(unittest.TextTestResult):
            def stopTest(self, test):
                super().stopTest(test)
                now = time.time()
                mod = getattr(test, "__module__", "") or ""
                if mod.startswith("test_"):
                    per_file[mod + ".py"] = round(
                        per_file.get(mod + ".py", 0.0) + (now - last_ts[0]), 3)
                last_ts[0] = now
                bump(self.testsRun)
        try:
            ran = True
            res = unittest.TextTestRunner(verbosity=2,
                                          resultclass=_Result).run(suite)
        finally:
            clear()
            record_times(per_file)
            if not nested:
                merge_times()
        ok = res.wasSuccessful()
    finally:
        left = tmproot.drop_run_root(tmp_root, prev_tmpdir)
        if left:
            # 거두되 조용히 치우지 않는다 — 접두어가 범인을 가리킨다.
            head = ", ".join(left[:8]) + (" …" if len(left) > 8 else "")
            print(f"[임시자리 회수/끝난 뒤] 테스트가 남긴 {len(left)}개를 "
                  f"거뒀다: {head}", file=sys.stderr)
        leaked = [] if nested else _reap("끝난 뒤")
        if ran and not nested:
            # 이 실행이 남긴 풀 서버·감시자는 이 실행이 거둔다 (REQ-20260905-005).
            # 실행 루트를 지운 **뒤**여야 한다 — doctor 는 살아 있는 실행 루트가
            # 있으면 풀의 재양육 서버를 시험 중인 것으로 보고 미룬다. 아무것도
            # 안 돈 호출(재사용·변경 없음)에는 걸지 않는다 — 그 호출은 게이트가
            # 자주 부르고, 2초를 얹으면 「즉시」라는 계약이 깨진다.
            portpool._reclaim_orphans()
    if leaked:
        # 거뒀더라도 실패로 센다 — 조용히 치우면 다음에 또 생긴다.
        print(f"실패: 테스트가 사용자 대시보드 포트에 서버 {len(leaked)}개를 "
              f"남겼다(거뒀다). 세션 훅을 돌리는 테스트는 S9_PORT 로 격리하라.",
              file=sys.stderr)
        return 1
    if empty:
        # 고른 것이 다 통과해도 실패다 — 커밋 게이트는 "담긴 테스트가
        # 통과했다"고 판정하는데, 안 돈 것이 통과로 보이면 그 판정이 거짓이 된다.
        print(f"실패: 고르지 못한 패턴 {len(empty)}개 — {', '.join(empty)}",
              file=sys.stderr)
        return 1
    if ok and not nested:
        mark_green(pats, fp)    # 이 선택은 이 지문으로 통과했다
        if full_requested:
            write_green_stamp()  # 전체 green 만 --changed 의 기준점이 된다
    drop_run_lock(lock_fh)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
