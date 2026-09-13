#!/usr/bin/env python3
"""GitHub 연동 — 혼자 쓰던 저장소를 GitHub 저장소와 origin 으로 잇는다 (REQ-20260913-008-62x6).

배포판을 풀어 쓰는 사람은 처음에 혼자 쓰는 자리다(`.s9-sync` = local, origin 없음).
여기의 넷이 그 자리를 바꾼다 — 판정과 문장은 이 모듈이 짓고, `bin/s9.py` 는
CLI(`s9 github …`)와 라우트(`/api/github/…`)의 배선만 둔다.

    github_state(root)                     지금 — linked·origin·web_url·sync_mode·auth·can
    github_link(root, url)                 이미 있는 저장소에 잇는다 — 접근 확인 → origin → push → remote
    github_create(root, name, private)     새로 만든 뒤 link 와 같은 절차
    github_unlink(root)                    origin 제거 · local — 문서는 그대로

준비물은 둘 중 하나다: `gh` CLI(로그인됨) 또는 secret `GITHUB_TOKEN`. 키 이름이
대문자인 까닭: 제품이 정한 키는 `JIRA_API_TOKEN` 처럼 환경변수 꼴이고, 개인 장치
이름을 코드에서 막는 시험(test_no_secret_names)이 그 꼴만 제품 키로 본다. 읽을 때는
대소문자를 가리지 않는다(`bin/s9.py` 의 `_github_kwargs`).

**토큰은 argv 에 싣지 않는다.** git 에는 `GIT_CONFIG_*` 환경(Basic 헤더)으로만 건네고
(`ps` 에 남지 않는다), GitHub API 에는 Authorization 헤더로만 간다. 응답·문장·로그
어디에도 값이 실리지 않는다.

이 모듈은 `.s9-sync` 를 직접 읽거나 쓰지 않는다 — 마커의 뜻과 쓰는 길은
`bin/s9.py` 의 `sync_mode()`·`sync_set_mode()` 하나뿐이라, 부르는 쪽이 그 둘을
`mode_get`·`mode_set` 으로 넘긴다. 시험도 같은 함수를 넘긴다.
"""
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
import urllib.error
import urllib.request

GITHUB_SECRET_KEY = "GITHUB_TOKEN"
API_BASE = "https://api.github.com"          # 시험이 로컬 스텁으로 바꾼다
GH_CANDIDATES = (os.path.expanduser("~/.local/bin/gh"),)
JOIN_HINT = "bin/s9 code --join <url>"

GIT_LOCAL_TIMEOUT = 10
GIT_NET_TIMEOUT = 25
GIT_PUSH_TIMEOUT = 90
GH_TIMEOUT = 20
API_TIMEOUT = 15
LOGIN_TTL_SEC = 300          # Settings 판이 열릴 때마다 GitHub 에 묻지 않는다

WHY = {
    "no_repo": "여기는 git 저장소가 아닙니다 — `s9 instance init` 으로 만든 저장소에서만 "
               "GitHub 연동을 합니다.",
    "no_marker": "이 저장소에는 문서 동기화가 없습니다 — `s9 instance init` 으로 만든 "
                 "저장소(.s9-sync 가 있는 곳)에서만 GitHub 연동을 합니다.",
    "no_prep": "준비물이 없습니다 — gh CLI 로그인(`gh auth login`) 또는 secret "
               f"{GITHUB_SECRET_KEY}(`printf %s '<token>' | s9 secret set {GITHUB_SECRET_KEY}`) "
               "중 하나가 필요합니다.",
}

_LOGIN_CACHE = {}


# ── 바깥 프로세스 ───────────────────────────────────────────────────────────────

def _run(argv, cwd=None, timeout=GIT_LOCAL_TIMEOUT, env=None):
    """실패해도 예외가 아니라 결과다 — 시간 초과 124, 실행 불가 127."""
    e = dict(os.environ)
    e["GIT_TERMINAL_PROMPT"] = "0"        # 서버에는 답할 사람이 없다 — 묻지 말고 실패하라
    if env:
        e.update(env)
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=e)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"{timeout}초 안에 답하지 않았습니다")
    except OSError as ex:
        return subprocess.CompletedProcess(argv, 127, "", str(ex))


def _git(root, *argv, timeout=GIT_LOCAL_TIMEOUT, env=None):
    return _run(["git", "-C", root, *argv], timeout=timeout, env=env)


def _fail_line(r):
    for ln in (r.stderr or "").splitlines() + (r.stdout or "").splitlines():
        ln = ln.strip()
        if ln:
            return ln
    return f"exit {r.returncode}"


def find_gh():
    p = shutil.which("gh")
    if p:
        return p
    for c in GH_CANDIDATES:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return ""


def _gh_auth(gh):
    """(로그인됐나, 토큰) — `gh auth token` 은 네트워크 없이 답한다."""
    if not gh:
        return False, ""
    r = _run([gh, "auth", "token"], timeout=GH_TIMEOUT)
    tok = (r.stdout or "").strip()
    return (r.returncode == 0 and bool(tok)), (tok if r.returncode == 0 else "")


def _gh_protocol(gh):
    r = _run([gh, "config", "get", "git_protocol"], timeout=GH_TIMEOUT)
    v = (r.stdout or "").strip().lower()
    return "ssh" if v == "ssh" else "https"


def _token_value(token):
    return (token() if callable(token) else (token or "")) or ""


# ── URL ────────────────────────────────────────────────────────────────────────

_URL_RE = re.compile(r"^(?P<scheme>https?|ssh|git)://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<path>.+)$",
                     re.I)
_SCP_RE = re.compile(r"^(?:[\w.-]+@)?(?P<host>[\w-]+(?:\.[\w-]+)+):(?P<path>[^/].*)$")
_BARE_RE = re.compile(r"^(?P<host>[\w-]+(?:\.[\w-]+)+)/(?P<path>[^/]+/.+)$")


def parse_remote(url):
    """https·ssh·scp 꼴·스킴 없는 꼴을 한 모양으로 — web_url 은 https://<host>/<o>/<r>.

    URL 이 아닌 것(로컬 경로)은 빈 값으로 둔다 — origin 은 그대로 쓸 수 있고 web_url 만 없다.
    윈도우 드라이브(`C:\\…`)가 scp 꼴로 읽히지 않게 호스트에는 점이 있어야 한다."""
    u = (url or "").strip()
    out = {"input": u, "host": "", "owner": "", "repo": "", "web_url": "",
           "https_url": "", "ssh_url": ""}
    m = _URL_RE.match(u) or _SCP_RE.match(u) or _BARE_RE.match(u)
    if not m:
        return out
    host = m.group("host").strip().lower()
    path = m.group("path").strip().strip("/")
    if path.endswith(".git"):
        path = path[:-4].rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2 or not host:
        return out
    out.update({"host": host, "owner": parts[-2], "repo": parts[-1],
                "web_url": f"https://{host}/{path}",
                "https_url": f"https://{host}/{path}.git",
                "ssh_url": f"git@{host}:{path}.git"})
    return out


def _first_url(text):
    """gh 가 찍은 것 중 저장소 주소 — URL 꼴이 있으면 그것, 없으면 마지막 줄(시험의 로컬 경로)."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for ln in lines:
        if re.match(r"^(https?://|ssh://|git@)", ln):
            return ln
    return lines[-1] if lines else ""


# ── 자격 ────────────────────────────────────────────────────────────────────────

def git_auth_env(host, token):
    """git 한 번에만 주는 자격 — 환경으로 건네는 설정(git ≥ 2.31). argv 에도 파일에도 남지 않는다."""
    if not (host and token):
        return {}
    n = 0
    try:
        n = int(os.environ.get("GIT_CONFIG_COUNT") or 0)
    except ValueError:
        n = 0
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {"GIT_CONFIG_COUNT": str(n + 1),
            f"GIT_CONFIG_KEY_{n}": f"http.https://{host}/.extraheader",
            f"GIT_CONFIG_VALUE_{n}": "Authorization: Basic " + basic}


def credential_helper_value(gh_path, s9_bin):
    """그 뒤의 동기화(commit→pull→push)가 쓸 자격 — 저장소 안 .git/config(비추적)에만 둔다.
    gh 면 gh 의 helper, 토큰이면 s9 의 secret 저장소에서 그때그때 읽는다(값을 적지 않는다)."""
    if gh_path:
        return f"!{shlex.quote(gh_path)} auth git-credential"
    return ("!f() { if [ \"$1\" = get ]; then printf 'username=x-access-token\\npassword=%s\\n' "
            f"\"$({shlex.quote(s9_bin)} secret get {GITHUB_SECRET_KEY})\"; fi; }}; f")


def _helper_key(host):
    return f"credential.https://{host}.helper"


def _is_our_helper(value):
    return (" auth git-credential" in value) or (f"secret get {GITHUB_SECRET_KEY}" in value)


def _install_helper(root, host, gh_path, have_secret):
    if not host or not (gh_path or have_secret):
        return ""
    # 그 뒤의 동기화를 돌릴 s9 는 **이 모듈 옆의 것**이다 — root 가 임시 인스턴스여도 같다.
    s9_bin = os.path.join(os.path.dirname(os.path.realpath(__file__)), "s9")
    val = credential_helper_value(gh_path, s9_bin)
    r = _git(root, "config", "--local", _helper_key(host), val)
    return val if r.returncode == 0 else ""


def _remove_helper(root, host):
    if not host:
        return
    r = _git(root, "config", "--local", "--get-all", _helper_key(host))
    vals = [v for v in (r.stdout or "").splitlines() if v.strip()]
    if vals and all(_is_our_helper(v) for v in vals):
        _git(root, "config", "--local", "--unset-all", _helper_key(host))


# ── GitHub API (표준 라이브러리만) ──────────────────────────────────────────────

def _api(method, path, token, body=None):
    url = API_BASE.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "section9-s9"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
            st, raw = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        st, raw = e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, {"message": f"GitHub API 에 닿지 못했습니다 — {getattr(e, 'reason', e)}"}
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError:
        parsed = {"message": raw[:200]}
    return st, parsed if isinstance(parsed, dict) else {"data": parsed}


def _api_error(st, body):
    msg = str(body.get("message") or "")
    errs = body.get("errors")
    if isinstance(errs, list):
        det = "; ".join(str(e.get("message") or e.get("code") or e) if isinstance(e, dict) else str(e)
                        for e in errs)
        if det:
            msg = f"{msg} ({det})" if msg else det
    return f"{st or '연결 실패'} {msg}".strip()


def github_login(gh="", token="", now=None):
    """로그인 이름 — gh 가 있으면 `gh api user`, 아니면 토큰으로 GET /user. 5분 캐시(실패도)."""
    if gh:
        key = "gh:" + gh
    elif token:
        key = "tok:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    else:
        return ""
    now = now or time.time()
    hit = _LOGIN_CACHE.get(key)
    if hit and now - hit[0] < LOGIN_TTL_SEC:
        return hit[1]
    login = ""
    if gh:
        r = _run([gh, "api", "user"], timeout=GH_TIMEOUT)
        if r.returncode == 0:
            try:
                login = str(json.loads(r.stdout).get("login") or "")
            except (ValueError, AttributeError):
                login = ""
    else:
        st, body = _api("GET", "/user", token)
        if st == 200:
            login = str(body.get("login") or "")
    _LOGIN_CACHE[key] = (now, login)
    return login


# ── 저장소 ──────────────────────────────────────────────────────────────────────

def _origin(root):
    r = _git(root, "remote", "get-url", "origin")
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def _branch(root):
    r = _git(root, "symbolic-ref", "--short", "HEAD")
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def _has_commit(root):
    return _git(root, "rev-parse", "--verify", "-q", "HEAD").returncode == 0


def _precheck(root, need_marker=True):
    if not os.path.isdir(os.path.join(root, ".git")):
        return WHY["no_repo"]
    if need_marker and not os.path.exists(os.path.join(root, ".s9-sync")):
        return WHY["no_marker"]
    return ""


def _no(error, **extra):
    return {"ok": False, "error": error, **extra}


def _remote_is_ours(root, ls_out, branch):
    """비어 있지 않아도 **우리 이력**이면 잇는다 — 끊었다 다시 잇는 자리. 원격의 그 가지
    끝이 HEAD 의 조상이면(같거나 앞선 commit) 남의 저장소가 아니라 우리가 보낸 것이다."""
    want = f"refs/heads/{branch}"
    for ln in (ls_out or "").splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[1] == want:
            return _git(root, "merge-base", "--is-ancestor", parts[0], "HEAD").returncode == 0
    return False


def github_state(root, mode_get=None, token="", deny_why="", ask_login=True):
    """계약 A 의 state — 화면(REQ-009)은 이 필드 이름을 그대로 그린다.

    deny_why: 부르는 쪽(서버)이 신원으로 막는 사유 — 있으면 can 둘 다 그 문장으로 잠긴다.
    ask_login: 이름을 GitHub 에 묻는가(캐시 5분) — 준비물이 없으면 묻지 않는다."""
    repo = os.path.isdir(os.path.join(root, ".git"))
    marker = repo and os.path.exists(os.path.join(root, ".s9-sync"))
    origin = _origin(root) if repo else ""
    gh = find_gh()
    gh_ok, gh_tok = _gh_auth(gh)
    secret = _token_value(token)
    login = ""
    if ask_login and (gh_ok or secret):
        login = github_login(gh if gh_ok else "", gh_tok if gh_ok else secret)
    if not repo:
        base = {"ok": False, "why": WHY["no_repo"]}
        can = {"link": dict(base), "create": dict(base)}
    elif not marker:
        base = {"ok": False, "why": WHY["no_marker"]}
        can = {"link": dict(base), "create": dict(base)}
    elif deny_why:
        can = {"link": {"ok": False, "why": deny_why}, "create": {"ok": False, "why": deny_why}}
    else:
        can = {"link": {"ok": True, "why": ""},
               "create": ({"ok": True, "why": ""} if (gh_ok or secret)
                          else {"ok": False, "why": WHY["no_prep"]})}
    info = parse_remote(origin) if origin else {}
    return {"linked": bool(origin), "origin": origin,
            "web_url": info.get("web_url", "") if origin else "",
            "sync_mode": (mode_get() if (mode_get and repo) else "") or "",
            "branch": _branch(root) if repo else "",
            "auth": {"gh": gh_ok, "token": bool(secret), "login": login},
            "token_key": GITHUB_SECRET_KEY,
            "can": can}


def github_link(root, url, mode_set=None, token=""):
    """접근 확인(ls-remote) → 비어 있지 않으면 거부(우리 이력이면 통과) → origin → push -u → remote."""
    url = (url or "").strip()
    if not url:
        return _no("저장소 URL 이 비어 있습니다.")
    why = _precheck(root)
    if why:
        return _no(why)
    info = parse_remote(url)
    gh = find_gh()
    gh_ok, gh_tok = _gh_auth(gh)
    secret = _token_value(token)
    env = git_auth_env(info["host"], gh_tok or secret) if url.lower().startswith("https://") else {}
    branch = _branch(root)
    if not branch or not _has_commit(root):
        return _no("이 저장소에 commit 이 하나도 없습니다 — 문서가 하나라도 담겨야 push 할 수 있습니다.")
    r = _git(root, "ls-remote", url, timeout=GIT_NET_TIMEOUT, env=env)
    if r.returncode != 0:
        return _no(f"그 저장소에 닿지 않거나 권한이 없습니다 — {_fail_line(r)}")
    if (r.stdout or "").strip() and not _remote_is_ours(root, r.stdout, branch):
        return _no(f"비어 있지 않은 저장소입니다 — 팀 저장소에 합류하려면 {JOIN_HINT}")
    old = _origin(root)
    r = _git(root, "remote", "set-url" if old else "add", "origin", url)
    if r.returncode != 0:
        return _no(f"origin 을 등록하지 못했습니다 — {_fail_line(r)}")
    if env:
        _install_helper(root, info["host"], gh if gh_ok else "", bool(secret))
    r = _git(root, "push", "-u", "origin", branch, timeout=GIT_PUSH_TIMEOUT, env=env)
    if r.returncode != 0:
        # 되돌린다 — origin 은 있는데 보낸 적이 없는 어중간한 자리를 남기지 않는다.
        if old:
            _git(root, "remote", "set-url", "origin", old)
        else:
            _git(root, "remote", "remove", "origin")
        if env:
            _remove_helper(root, info["host"])
        return _no(f"push 하지 못했습니다 — {_fail_line(r)}. 준비물: https 는 gh 로그인 또는 "
                   f"secret {GITHUB_SECRET_KEY}, ssh 는 이 컴퓨터의 ssh 키.")
    mode = mode_set("remote") if mode_set else ""
    web = info["web_url"] or url
    return {"ok": True, "origin": url, "web_url": info["web_url"], "branch": branch,
            "sync_mode": mode or "",
            "said": f"연결했습니다 — {web} 에 {branch} 를 push 했고, 이제 문서 이벤트마다 "
                    f"origin 과 주고받습니다(remote)."}


def github_create(root, name, private=True, org="", mode_set=None, token=""):
    """gh 가 있으면 `gh repo create [org/]name --private|--public`, 없고 토큰이 있으면 API.
    만든 뒤에는 link 와 같은 절차 — 실패해도 만든 사실은 응답에 남긴다(created)."""
    name = (name or "").strip()
    org = (org or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
        return _no("저장소 이름은 영숫자와 . _ - 만 쓸 수 있습니다(100자 이내).")
    if org and not re.fullmatch(r"[A-Za-z0-9-]{1,39}", org):
        return _no("조직 이름은 영숫자와 - 만 쓸 수 있습니다(39자 이내).")
    why = _precheck(root)
    if why:
        return _no(why)
    gh = find_gh()
    gh_ok, gh_tok = _gh_auth(gh)
    secret = _token_value(token)
    web = ""
    if gh_ok:
        full = f"{org}/{name}" if org else name
        r = _run([gh, "repo", "create", full, "--private" if private else "--public"],
                 timeout=GH_TIMEOUT)
        if r.returncode != 0:
            return _no(f"gh 가 저장소를 만들지 못했습니다 — {_fail_line(r)}")
        made = _first_url(r.stdout)
        if not made:
            login = github_login(gh, gh_tok)
            made = f"https://github.com/{org or login}/{name}"
        info = parse_remote(made)
        web = info["web_url"] or made
        url = (info["ssh_url"] if _gh_protocol(gh) == "ssh" and info["ssh_url"]
               else (info["https_url"] or made))
    elif secret:
        path = f"/orgs/{org}/repos" if org else "/user/repos"
        st, body = _api("POST", path, secret, {"name": name, "private": bool(private)})
        if st != 201:
            return _no(f"GitHub API 가 저장소를 만들지 못했습니다 — {_api_error(st, body)}")
        url = str(body.get("clone_url") or "").strip()
        web = str(body.get("html_url") or "").strip() or parse_remote(url)["web_url"]
        if not url:
            return _no("GitHub API 응답에 clone_url 이 없습니다.")
    else:
        return _no(WHY["no_prep"])
    res = github_link(root, url, mode_set=mode_set, token=token)
    res["created"] = web
    if res.get("ok"):
        res["said"] = (f"만들고 연결했습니다 — {web} ({'비공개' if private else '공개'}). "
                       f"이제 문서 이벤트마다 origin 과 주고받습니다(remote).")
    else:
        res["error"] = (f"저장소는 만들었지만 잇지 못했습니다({web}) — {res['error']} "
                        f"다시 하려면: s9 github link {url}")
    return res


def github_unlink(root, mode_set=None):
    """origin 제거 · local. 문서는 그대로다. origin 이 없어도 ok(멱등)."""
    why = _precheck(root, need_marker=False)
    if why:
        return _no(why)
    origin = _origin(root)
    if origin:
        _remove_helper(root, parse_remote(origin)["host"])
        r = _git(root, "remote", "remove", "origin")
        if r.returncode != 0:
            return _no(f"origin 을 지우지 못했습니다 — {_fail_line(r)}")
    mode = (mode_set("local") if (mode_set and os.path.exists(os.path.join(root, ".s9-sync")))
            else "")
    return {"ok": True, "origin": "", "web_url": "", "sync_mode": mode or "",
            "said": ("끊었습니다 — origin 을 지웠고 이제 commit 만 하고 내보내지 않습니다(local). "
                     "문서는 그대로입니다." if origin
                     else "이미 끊겨 있습니다 — origin 이 없습니다.")}
