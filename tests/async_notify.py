"""백그라운드 전체 실행의 결과가 스스로 도착한다 (REQ-20260906-029).

post-commit 이 띄운 전체 실행은 로그(state/tests-async/<sha7>.log)에만 남았다 —
리드가 Monitor 로 결과를 기다리다 세 번 놓쳤다(2026-09-06). 그래서 전체 판정이
끝나는 자리에서 결과를 **밀어 넣는다**:

① 그 커밋의 REQ 문서에 노트(`s9 note … --label response --agent test-runner`)
② 그 REQ 를 클레임한 세션(없으면 최근 활성 세션 전부)의 수신함에 kind=event 한 줄
③ 실패면 후속 요청(`s9 new request --parent <REQ>`) 자동 등록 — 같은 sha 로는 한 번만
   (state/tests-async/<sha7>.req 표식)

post-commit(백그라운드) 이 넘긴 `S9_TESTS_ASYNC=1` 이 있을 때만 움직인다 — 사람이 터미널에서 손으로
돌린 실행은 이미 눈앞에서 결과를 보고 있으니 조용하다. sha 는 `S9_TESTS_ASYNC_SHA`
로 받는다(HEAD 는 그 사이 문서 커밋으로 바뀌었을 수 있다, REQ-20260906-020).

수신함 줄은 bin/s9.py 의 `chat_send` 로 쓴다 — 전이 통지(chat_notify_transition)와
같은 함수라 줄 형식이 한 벌이다. 후보 고르기도 그 함수의 규칙을 따른다:
클레임(binding_req_ids) 또는 문서의 담당 세션, 살아 있거나 한 시간 안에 활동.
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ENV_FLAG = "S9_TESTS_ASYNC"
ENV_SHA = "S9_TESTS_ASYNC_SHA"
REQ_RE = re.compile(r"REQ-\d{8}-\d{3}(?:-[a-z0-9]+)?")
RED_MARK = "__S9_FULL_RED="       # 러너가 마지막에 찍는 실패한 파일 목록 — 원격 출력에서 걷는다
FRESH_SEC = 3600


def active(env=None):
    return (env if env is not None else os.environ).get(ENV_FLAG) == "1"


def take_env():
    """표식을 환경에서 **걷어** 사본을 돌려준다 — 러너가 띄우는 샤드·안쪽 러너·시험 속
    러너가 물려받아 저마다 알리지 않도록. 알림은 부모 실행 하나가 이 사본으로 한다."""
    snap = dict(os.environ)
    for k in (ENV_FLAG, ENV_SHA):
        os.environ.pop(k, None)
    return snap


def _git(root, *a):
    try:
        r = subprocess.run(["git", "-C", root, *a], capture_output=True, text=True,
                           timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def commit_sha7(root, env=None):
    env = env if env is not None else os.environ
    sha = (env.get(ENV_SHA) or "").strip()
    return sha[:7] if sha else (_git(root, "rev-parse", "--short", "HEAD") or "")[:7]


def commit_req(root, sha):
    """커밋 메시지의 첫 REQ id — 없으면 ''."""
    m = REQ_RE.search(_git(root, "log", "-1", "--format=%B", sha) if sha else "")
    return m.group(0) if m else ""


def _s9_bin(root):
    local = os.path.join(root, "bin", "s9")
    return local if os.path.exists(local) else os.path.join(REPO, "bin", "s9")


def _s9(root, *args, env=None):
    e = dict(env if env is not None else os.environ)
    e["S9_ROOT"] = root
    e.pop("S9_TESTS_NESTED", None)
    try:
        return subprocess.run([sys.executable or "python3", _s9_bin(root), *args],
                              capture_output=True, text=True, timeout=120, env=e, cwd=root)
    except (OSError, subprocess.TimeoutExpired) as e_:
        return subprocess.CompletedProcess(args, 1, "", str(e_))


_S9_MODS = {}


def _load_s9(root):
    """bin/s9.py 를 root 로 묶어 로드한다 — ROOT 는 import 때 S9_ROOT 로 정해진다."""
    if root in _S9_MODS:
        return _S9_MODS[root]
    old = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        name = "s9_async_notify_%d" % len(_S9_MODS)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, _s9_bin(root) + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old
    _S9_MODS[root] = mod
    return mod


def target_sessions(s9, req):
    """받을 세션: req 를 클레임한(또는 문서의 담당) 살아 있는 세션 전부 — 없으면
    한 시간 안에 활동한 이 머신의 세션 전부. 끝난 세션(ended)은 어느 쪽도 아니다."""
    owner = ""
    if req:
        try:
            p = s9.locate(req)
            owner = (s9.read_doc(p)[0] or {}).get("session", "") if p else ""
        except Exception:
            owner = ""
    alias = s9.id_alias()
    canon = s9.canon_id(req, alias) if req else ""
    now = time.time()
    claimed, fresh_all = [], []
    for bp in sorted(glob.glob(s9._local_binding_glob())):
        try:
            with open(bp, encoding="utf-8") as f:
                b = json.load(f)
        except (OSError, ValueError):
            continue
        sid = b.get("session", "")
        if not sid or b.get("ended"):
            continue
        fresh = s9.chat_live(b) or any(now - os.path.getmtime(p) < FRESH_SEC
                                       for p in s9._binding_activity_paths(b))
        if not fresh:
            continue
        fresh_all.append(sid)
        if canon and (canon in s9.binding_req_ids(b, alias) or sid == owner):
            claimed.append(sid)
    return claimed or fresh_all


def _marker(root, sha):
    return os.path.join(root, "state", "tests-async", f"{sha}.req")


def _register_failure(root, sha, req, red, env):
    """실패 후속 요청 — 같은 sha 로는 한 번만. 만든 id 또는 표식에 적힌 id, 없으면 ''."""
    path = _marker(root, sha)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""
    except OSError:
        return ""
    body = "실패 파일:\n" + "\n".join(f"- {f}" for f in red) + \
        f"\n\n로그: state/tests-async/{sha}.log"
    r = _s9(root, "new", "request", "--title", f"전체 테스트 실패: {sha}",
            "--parent", req, "--size", "S",
            "--goal", "실패한 파일이 통과하고 통과 기록이 남는다",
            "--summary", f"{sha} 의 백그라운드 전체 테스트가 실패했다 — {', '.join(red)[:120]}",
            "--body", body, env=env)
    m = REQ_RE.search(r.stdout or "")
    new_id = m.group(0) if (r.returncode == 0 and m) else ""
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(new_id + "\n")
    if not new_id:
        # 못 만들었으면 표식을 남기지 않는다 — 다음 실행이 다시 시도한다
        try:
            os.unlink(path)
        except OSError:
            pass
        print(f"[알림] 후속 요청을 못 만들었다: {(r.stderr or r.stdout).strip()[:200]}",
              file=sys.stderr)
    return new_id


def ran_label(started, ran):
    """알림이 가리킬 커밋 — 시작 커밋과 실제로 돈 커밋이 다르면 **둘 다** 말한다
    (REQ-20260907-064).

    post-commit 훅은 제가 잡은 그 커밋으로 로그 이름을 짓고 sha 를 넘기는데, 러너는
    HEAD 를 새로 읽어 돈다. 그리고 commit 훅이 노트를 자동 커밋하므로 코드 커밋 직후
    HEAD 는 거의 언제나 한 칸 앞이다 — 실측 2026-09-07 18:48, 「3fc7a5e 실패」라
    알린 회차가 실제로는 1초 뒤의 f7230df 를 돌았다. 「3fc7a5e 실패」를 읽은 사람은
    그 커밋을 뒤지지만 결과는 그 뒤 나무의 것이다.

    사람이 알고 싶은 것은 「지금 나무가 성한가」이니 돈 것은 HEAD 가 맞다. 다만
    보고가 어느 커밋의 결과인지는 거짓 없이 말해야 한다. 같으면 하나만 적는다."""
    started = (started or "")[:7]
    ran = (ran or "")[:7]
    if not ran or ran == started:
        return started or ran or "head"
    if not started:
        return ran
    return f"{started} 로 시작 → {ran} 을 돌았다"


def notify_full_result(ok, red=(), took=0.0, n_files=0, where="로컬", root=None,
                       env=None, sha=None, req=None, ran_sha=None):
    """전체 실행의 판정 직후 한 번. 반환: {"sha","req","sessions","new_req"} 또는
    비활성(S9_TESTS_ASYNC 없음)이면 None. 어느 한 갈래가 실패해도 나머지는 간다 —
    알림이 러너의 종료 코드를 바꾸지 않는다.

    `sha` 는 시작 커밋(훅이 넘긴 것), `ran_sha` 는 실제로 돈 커밋(러너의 HEAD).
    로그 파일 이름·후속 요청·REQ 노트는 시작 sha 로 잇는다 — 그것이 훅이 만든 자리다.
    사람이 읽는 문장은 둘이 다르면 둘 다 말한다(ran_label)."""
    env = env if env is not None else os.environ
    if not active(env):
        return None
    root = root or REPO
    red = [f for f in red if f]
    sha = (sha or commit_sha7(root, env) or "head")[:7]
    label = ran_label(sha, ran_sha)
    req = req if req is not None else commit_req(root, sha)
    secs = int(round(took))
    if ok:
        inbox = f"[전체 테스트] {label} 통과 · {n_files}파일 {secs}초"
        note = f"전체 테스트 통과({where} {secs}초) — {label} · {n_files}파일"
    else:
        names = ", ".join(red) if red else "(실패 파일을 못 읽었다 — 로그를 보라)"
        inbox = f"[전체 테스트] {label} 실패 · {names} — 커밋 차단이 걸렸다"
        note = (f"전체 테스트 실패({where} {secs}초) — {label} · 실패: {names} — "
                f"커밋 차단이 걸렸다(state/tests-last-red.json), "
                f"로그 state/tests-async/{sha}.log")
    new_req = ""
    if req and not ok:
        new_req = _register_failure(root, sha, req, red, env)
        if new_req:
            inbox += f" · 후속 요청 {new_req}"
            note += f" · 후속 요청 {new_req}"
    if req:
        r = _s9(root, "note", req, note, "--label", "response", "--agent", "test-runner",
                env=env)
        if r.returncode != 0:
            print(f"[알림] 노트를 못 남겼다({req}): {(r.stderr or r.stdout).strip()[:200]}",
                  file=sys.stderr)
    sent = []
    try:
        s9 = _load_s9(root)
        for sid in target_sessions(s9, req):
            try:
                got = s9.chat_send(inbox, sid8=sid, sender="dashboard", kind="event")
            except ValueError:
                continue
            if got and got not in sent:
                sent.append(got)
    except Exception as e:      # 알림 실패는 판정을 바꾸지 않는다
        print(f"[알림] 수신함에 못 넣었다: {e}", file=sys.stderr)
    print(f"[알림] {inbox} → 세션 {len(sent)}개"
          + (f", 노트 {req}" if req else ", 커밋 메시지에 REQ 없음 — 노트 생략"),
          file=sys.stderr)
    return {"sha": sha, "req": req, "sessions": sent, "new_req": new_req}
