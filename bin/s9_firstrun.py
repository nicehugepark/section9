#!/usr/bin/env python3
"""압축을 풀어 처음 실행한 자리에 저장소를 세운다 (REQ-20260913-007).

사람은 GitHub 릴리스의 tar.gz/zip 을 받아 풀고 `bin/s9 code` 만 친다(Windows 는
`bin\\s9.cmd code` — 같은 함수를 지난다). 그 자리에는 `.git` 도 `state/` 도 없는데,
대시보드·훅·sync 는 전부 git 저장소를 전제한다: `sync_mode()` 는 .git 이 없으면 ""
이고, s9-install 은 .git/hooks 에 훅을 놓는다. 그래서 그 둘보다 먼저 여기가 선다.

    git init(main) → 인스턴스 .gitignore → `.s9-sync` local(아직 고르지 않음)
    → 신원이 없으면 저장소 로컬 임시 신원 → 첫 commit 「section9 첫 실행」

결과는 **혼자 쓰는 상태**다 — 문서 이벤트마다 로컬 commit 만 하고 GitHub 연동은
없다(잇는 길은 대시보드 Settings › 저장소). 이미 저장소면 아무것도 하지 않는다(멱등).

부르는 자리는 둘이고 같은 결과다: `s9 code`(대시보드를 띄우기 전) · `s9-install`
(git 훅을 놓기 전). 실측 2026-09-13: 그 전의 s9-install 은 .git 이 없어도 실패하지
않았다 — 「git repo 아님 — git hooks 생략」으로 지나가고(exit 0) 저장소 없이 끝났고,
그 뒤 `s9 code` 가 저장소를 세워도 claude 훅이 이미 있어 설치가 다시 돌지 않아
git 훅이 영영 없었다.

이 모듈은 **기계만** 안다. 저장소의 모양(.gitignore 본문·`.s9-sync` 본문)은 부르는
쪽이 넘긴다 — 원천은 bin/s9.py 의 INSTANCE_TRACK_GITIGNORE 와 sync_marker_body() 다.
갈랐던 길 둘: ① 본문을 여기로 옮기고 s9.py 가 여기서 읽는다 — 동기화 정책의 줄
(SYNC_UNCHOSEN_LINE)이 정책 코드에서 떨어져 나가고 s9.py 의 상수 자리 둘을 옮겨야
한다. ② 여기서 s9.py 를 실어 읽는다 — s9.py 가 이 모듈을 부르므로 서로 부르는
모양이 된다. 넘겨받으면 둘 다 없다; s9.py 를 모르는 s9-install 은 s9.py 를 모듈로
실어 그 둘을 꺼내 넘긴다(첫 실행 한 번뿐이다).

경로는 os.path.join 으로만 짓고 셸 문자열을 만들지 않는다 — Windows 도 같은 길이다.
"""
import base64
import getpass
import ntpath
import os
import re
import shutil
import stat
import subprocess

FIRST_COMMIT_SUBJECT = "section9 첫 실행"
DEFAULT_BRANCH = "main"

# git 이 훅에 넘기는 환경은 벗긴다 (bin/s9-install 의 같은 이유, REQ-20260829-005):
# 훅 아래에서 물려받은 GIT_DIR 로 `git init` 을 부르면 `-C <경로>` 를 이기고 **그
# 저장소**를 다시 init 한다. 신원과 설정(GIT_CONFIG_GLOBAL·GIT_AUTHOR_*)은 남긴다.
GIT_SCOPE_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                  "GIT_PREFIX", "GIT_OBJECT_DIRECTORY",
                  "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE")


def is_code_root(root):
    """이 자리에 하네스 코드가 있나 — 압축을 푼 자리의 표식은 bin/s9.py 다.

    시험은 S9_ROOT 를 데이터만 있는 임시 디렉토리로 돌린다. 그런 자리에 저장소를
    세우면 훅이 부를 `$TOP/bin/s9` 가 없고, `s9 code` 를 부르는 시험마다 git
    저장소가 하나씩 선다. 코드가 없는 자리는 압축을 푼 자리가 아니다."""
    return os.path.isfile(os.path.join(root, "bin", "s9.py"))


def os_account():
    try:
        return getpass.getuser() or "user"
    except Exception:          # 계정 정보가 없는 컨테이너 — getpass 가 KeyError 를 낸다
        return "user"


def temp_identity(account=None):
    """신원이 없을 때 저장소 로컬에 두는 임시 신원 — (이름, 메일).

    commit 이 신원 부재로 거부되지 않게 하는 값이지 사람의 이름이 아니다 — 사람은
    나중에 `git config user.name/user.email` 로 바꾼다."""
    account = account or os_account()
    return (f"s9 {account}", f"{account}@local")


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _rmtree(path):
    """Windows 의 git 개체 파일은 읽기 전용이라 그대로는 지워지지 않는다."""
    def _retry(fn, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            fn(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_retry)


def ensure_repo(root, gitignore, sync_marker, env=None, account=None, git="git", run=None):
    """`.git` 이 없으면 저장소를 세운다. 무엇을 했는지 dict 로 돌려준다.

        created   True 면 이번 호출이 저장소를 세웠다
        did       한 일의 차례 — "init" "gitignore" "sync-marker" "identity" "commit"
        commit    첫 commit 의 sha
        skipped   안 한 이유 — "repo"(이미 저장소) · "no-code"(코드가 없는 자리)
        error     실패 사유 한 줄 — 예외를 밖으로 내지 않는다; 부르는 쪽은 안내 한 줄 뒤 계속한다

    실패하면 이번에 만든 .git 과 표식을 되돌린다 — 반쯤 선 저장소가 남으면 다음
    호출이 「이미 저장소」로 읽어 첫 commit 없이 sync 가 돈다.
    """
    root = os.path.abspath(root)
    out = {"created": False, "did": [], "commit": "", "skipped": "", "error": ""}
    if os.path.exists(os.path.join(root, ".git")):      # 디렉토리든 worktree 의 파일이든
        out["skipped"] = "repo"
        return out
    if not is_code_root(root):
        out["skipped"] = "no-code"
        return out
    _git = _git_runner(root, env=env, git=git, run=run)
    git_dir = os.path.join(root, ".git")
    made_marker = ""
    try:
        # ① init — 가지는 언제나 main (_init_main)
        _init_main(_git)
        out["did"].append("init")
        # ② 인스턴스 .gitignore — 배포판에 실린 것은 업스트림 개발용이다
        _write(os.path.join(root, ".gitignore"), gitignore)
        out["did"].append("gitignore")
        # ③ 동기화 표식 — 있으면 사람이 둔 것이니 그대로 (배포판에는 실리지 않는다)
        marker = os.path.join(root, ".s9-sync")
        if not os.path.exists(marker):
            _write(marker, sync_marker)
            made_marker = marker
            out["did"].append("sync-marker")
        # ④ 신원 — 전역·시스템에 없으면 저장소 로컬에 임시 신원: 첫 commit 도, 그 뒤
        #    sync 가 거는 commit 도 신원 부재로 거부되지 않게
        if _ensure_identity(_git, account):
            out["did"].append("identity")
        # ⑤ 첫 commit — 갓 세운 저장소라 담을 것은 이 자리 전부이고, 담기지 않을 것은
        #    방금 쓴 .gitignore 가 가른다(state/·index/·.claude/ …). 서명은 이 한 번만
        #    끈다 — 키 없는 머신의 전역 gpgsign 설정이 첫 commit 을 거부하지 않게.
        _git("add", "-A")
        _git("-c", "commit.gpgsign=false", "commit", "-q", "-m", FIRST_COMMIT_SUBJECT)
        out["commit"] = _git("rev-parse", "HEAD").stdout.strip()
        out["did"].append("commit")
        out["created"] = True
    except (OSError, subprocess.SubprocessError, RuntimeError) as e:
        out["error"] = str(e) or e.__class__.__name__
        if os.path.isdir(git_dir):
            _rmtree(git_dir)
        if made_marker:
            try:
                os.remove(made_marker)
            except OSError:
                pass
        out["did"].append("rolled-back")
    return out


def _git_runner(root, env=None, git="git", run=None):
    """이 자리(root)를 향한 git 호출 하나 — ensure_repo 와 join_repo 가 같은 것을 쓴다.

    실패는 RuntimeError 한 줄(마지막 stderr 줄)이다. 훅이 물려주는 GIT_DIR 류는 벗긴다."""
    base = dict(os.environ if env is None else env)
    for k in GIT_SCOPE_VARS:
        base.pop(k, None)
    run = run or subprocess.run

    def _git(*argv, check=True, timeout=120):
        r = run([git, "-C", root, *argv], capture_output=True, encoding="utf-8",
                errors="replace", env=base, timeout=timeout)
        if check and r.returncode != 0:
            lines = (r.stderr or r.stdout or "").strip().splitlines()
            raise RuntimeError(f"git {argv[0]}: {lines[-1] if lines else 'rc=' + str(r.returncode)}")
        return r
    return _git


def _init_main(_git):
    """가지는 언제나 main. init.defaultBranch 가 없는 머신은 master 를 만들고,
    옛 git(< 2.28)에는 -b 가 없다."""
    r = _git("init", "-q", "-b", DEFAULT_BRANCH, check=False)
    if r.returncode != 0:
        _git("init", "-q")
        _git("symbolic-ref", "HEAD", "refs/heads/" + DEFAULT_BRANCH)


def _ensure_identity(_git, account=None):
    """전역·시스템에 신원이 없으면 저장소 로컬에 임시 신원 — 했으면 True."""
    have = all(_git("config", k, check=False).stdout.strip()
               for k in ("user.name", "user.email"))
    if have:
        return False
    name, mail = temp_identity(account)
    _git("config", "user.name", name)
    _git("config", "user.email", mail)
    return True


# ── 초대 명령의 첫 실행 (REQ-20260913-013-62x6) ──────────────────────────────
# 초대 메일의 한 줄 `bin/s9 code --join <url> --project <slug>` 은 압축을 푼 자리를
# **팀 저장소**에 잇는다 — ensure_repo 가 세우는 혼자 쓰는 저장소 대신이다. 받는 것은
# 문서(vault/)·사람(users/)·프로젝트·`.s9-sync` 전부이고, 코드가 원격과 다르면(배포판
# 판이 다름) 원격 코드가 이긴다.
#
# 작업 트리를 원격으로 맞추는 길은 `git read-tree -u --reset origin/<가지>` +
# `update-ref` + `symbolic-ref` 다. `git checkout -B`/`-f` 나 `reset --hard` 를 쓰지
# 않는 까닭: 이 저장소의 gate(bin/s9-git-gate)가 작업 트리를 되돌리는 명령으로 막는
# 꼴이고, 그 규율의 뜻(남의 미commit 작업을 지우지 않는다)은 여기서도 지킨다 — 그래서
# **사람의 문서가 있는 자리는 거부한다**(has_documents). 코드만 있는 새 자리에서는
# 지울 것이 없고, 원격에 없는 파일(새 배포판이 더 실은 것)은 미추적으로 남는다.

DOC_DIRS = ("vault", "users")


def has_documents(root):
    """사람의 문서가 있나 — vault/·users/ 아래 파일 하나라도(빈 디렉토리는 아니다).

    `s9 init` 은 빈 디렉토리를 먼저 만든다 — 그것만으로 「문서가 있다」고 읽으면
    설치만 하고 아직 아무것도 안 적은 자리가 합류를 거부당한다."""
    for d in DOC_DIRS:
        for _dp, _dirs, files in os.walk(os.path.join(root, d)):
            if files:
                return True
    return False


def norm_url(url):
    """같은 저장소인가를 재는 꼴 — 끝의 `/` 와 `.git` 은 같은 곳이다."""
    u = (url or "").strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    return u


def join_repo(root, url, gitignore="", sync_marker="", env=None, account=None,
              git="git", run=None):
    """이 자리를 팀 저장소 `url` 에 잇는다. ensure_repo 와 같은 dict 에 둘을 더한다.

        created   True 면 이번 호출이 합류했다(origin·가지·작업 트리가 원격과 같다)
        did       "init" "remote" "fetch" "checkout" "gitignore" "sync-marker" "identity"
        commit    받은 가지 끝의 sha
        skipped   "joined"(같은 origin 이 이미 있다 — 아무 일도 없다) · "no-code"
        error     사유 한 줄 — 문서가 있는 자리 · origin 이 다른 곳 · fetch 실패 …
        origin    잇고 난 origin URL
        branch    받은 가지 이름(main, 없으면 master)

    순서: 코드만 있는 자리인지 → .git 없으면 init(main) → remote add origin → fetch →
    원격 가지를 이 자리의 가지로(작업 트리 포함) → .gitignore·.s9-sync 는 원격 것이
    있으면 그대로, 없으면 넘겨받은 본문 → 신원. commit 은 하지 않는다(HEAD 가 곧 원격).
    실패하면 이번에 만든 .git(또는 이번에 더한 origin)과 표식을 되돌린다."""
    root = os.path.abspath(root)
    out = {"created": False, "did": [], "commit": "", "skipped": "", "error": "",
           "origin": "", "branch": ""}
    url = (url or "").strip()
    if not url:
        out["error"] = "합류할 저장소 주소가 비어 있다 — s9 code --join <url>"
        return out
    if not is_code_root(root):
        out["skipped"] = "no-code"
        return out
    _git = _git_runner(root, env=env, git=git, run=run)
    git_dir = os.path.join(root, ".git")
    had_git = os.path.exists(git_dir)
    if had_git:
        cur = _git("remote", "get-url", "origin", check=False)
        cur_url = cur.stdout.strip() if cur.returncode == 0 else ""
        if cur_url:
            if norm_url(cur_url) == norm_url(url):
                out["skipped"] = "joined"
                out["origin"] = cur_url
                out["branch"] = _git("symbolic-ref", "--short", "HEAD", check=False).stdout.strip()
                return out
            out["error"] = (f"origin 이 이미 다른 저장소를 가리킨다({cur_url}) — "
                            f"이 자리에서는 바꾸지 않는다; 새로 압축을 푼 자리에서 --join")
            return out
    if has_documents(root):
        out["error"] = ("이 자리에 이미 문서가 있다(vault/·users/) — 합류는 새로 압축을 푼 "
                        "자리에서 한다(있는 문서를 원격으로 덮지 않는다)")
        return out
    made_remote = False
    made_marker = ""
    try:
        if not had_git:
            _init_main(_git)
            out["did"].append("init")
        _git("remote", "add", "origin", url)
        made_remote = True
        out["did"].append("remote")
        _git("fetch", "-q", "origin", timeout=600)
        out["did"].append("fetch")
        branch = ""
        for cand in (DEFAULT_BRANCH, "master"):
            if _git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{cand}",
                    check=False).returncode == 0:
                branch = cand
                break
        if not branch:
            raise RuntimeError(f"원격에 {DEFAULT_BRANCH} 가지가 없다: {url}")
        remote_ref = f"refs/remotes/origin/{branch}"
        _git("read-tree", "-u", "--reset", remote_ref)
        _git("update-ref", f"refs/heads/{branch}", remote_ref)
        _git("symbolic-ref", "HEAD", f"refs/heads/{branch}")
        _git("config", f"branch.{branch}.remote", "origin")
        _git("config", f"branch.{branch}.merge", f"refs/heads/{branch}")
        out["did"].append("checkout")
        if gitignore and not os.path.exists(os.path.join(root, ".gitignore")):
            _write(os.path.join(root, ".gitignore"), gitignore)
            out["did"].append("gitignore")
        marker = os.path.join(root, ".s9-sync")
        if sync_marker and not os.path.exists(marker):
            _write(marker, sync_marker)
            made_marker = marker
            out["did"].append("sync-marker")
        if _ensure_identity(_git, account):
            out["did"].append("identity")
        out["commit"] = _git("rev-parse", "HEAD").stdout.strip()
        out["origin"] = url
        out["branch"] = branch
        out["created"] = True
    except (OSError, subprocess.SubprocessError, RuntimeError) as e:
        out["error"] = str(e) or e.__class__.__name__
        if not had_git and os.path.isdir(git_dir):
            _rmtree(git_dir)
        elif made_remote:
            _git("remote", "remove", "origin", check=False)
        if made_marker:
            try:
                os.remove(made_marker)
            except OSError:
                pass
        out["did"].append("rolled-back")
    return out


def join_project(ns, slug, user, email="", via=" (s9 code --join)"):
    """합류한 사람을 초대받은 프로젝트에 세운다 — 한 일과 화면 줄을 dict 로.

    ns 는 bin/s9.py 의 globals() 다 — 문서를 읽고 쓰는 헬퍼(load_project·write_doc·
    do_user_attach·do_user_update·do_user_config_set …)는 그쪽 한 벌만 쓴다.

        attached  이 컴퓨터의 OS 계정·이름이 프로필에 붙었다(do_user_attach)
        renamed   초대(REQ-20260913-010)가 이메일로 적어 둔 멤버 키를 사용자명으로 바꿨다
        added     멤버가 아니어서 contributor 로 넣었다
        emails    초대 이메일(git user.email)을 프로필 emails 에 더했다
        default   이 사람의 기본 프로젝트(config default_project)를 slug 로 두었다
        lines     사람에게 낼 줄

    거부는 ValueError(없는 프로젝트). 신원이 등록되지 않은 사람이면 아무것도 쓰지 않고
    안내 한 줄만 돌려준다 — 멤버 키를 누구로 바꿔야 할지 모른다."""
    h = ns.__getitem__
    out = {"member": "", "role": "", "attached": False, "renamed": False, "added": False,
           "emails": False, "default": False, "lines": []}
    slug = (slug or "").strip()
    if not slug:
        return out
    pr = h("load_project")(slug)
    if not pr:
        raise ValueError(f"등록되지 않은 프로젝트: {slug} — 초대 명령의 --project 를 확인한다 "
                         f"(목록: s9 project ls)")
    meta, body, path = pr
    slug = meta.get("slug") or slug
    if not (user and h("user_role")(user)):
        out["lines"].append(
            f"◌ 이 컴퓨터의 계정을 section9 의 사람에 잇지 못해 프로젝트 {slug} 참여를 미뤘다 — "
            f"`s9 user attach <이름>` 뒤 다시 `s9 code --join <url> --project {slug}`")
        return out
    _acct, _machine, out["attached"] = h("do_user_attach")(user)
    email = (email or "").strip().lower()
    valid_email = bool(email) and bool(re.fullmatch(h("EMAIL_RE"), email))
    prof = h("user_profile")(user) or {}
    have = prof.get("emails") or []
    have = [str(e) for e in (have if isinstance(have, list) else [have]) if e]
    mine = {e.strip().lower() for e in have}
    if prof.get("email"):
        mine.add(str(prof["email"]).strip().lower())
    if valid_email:
        mine.add(email)
    members = list(meta.get("members") or [])
    now = h("now_iso")()
    me = next((m for m in members if m.get("user") == user), None)
    if me is None:
        keyed = next((m for m in members
                      if "@" in str(m.get("user") or "")
                      and str(m["user"]).strip().lower() in mine), None)
        if keyed is not None:
            old = keyed["user"]
            keyed["user"] = user
            me = keyed
            out["renamed"] = True
            body = body.rstrip("\n") + f"\n- {now} member {old} → {user} (초대 이메일로 합류{via})\n"
        else:
            me = {"user": user, "role": "contributor", "since": h("today_date")(),
                  "until": "", "position": ""}
            members.append(me)
            out["added"] = True
            body = body.rstrip("\n") + f"\n- {now} member add {user} role=contributor (초대 명령으로 합류{via})\n"
        meta["members"] = members
        meta["updated"] = now
        h("acquire_lock")()
        try:
            h("write_doc")(path, meta, body)
            h("rebuild_index")(quiet=True)
        finally:
            h("release_lock")()
    out["member"] = user
    out["role"] = me.get("role", "")
    if valid_email and email not in {e.strip().lower() for e in have}:
        h("do_user_update")(user, emails=have + [email], actor=user)
        out["emails"] = True
    cfg = h("user_config")(user) or {}
    if str(cfg.get("default_project") or "").strip() != slug:
        h("do_user_config_set")(user, "default_project", slug, actor=user)
        out["default"] = True
    if out["renamed"] or out["added"] or out["default"]:
        out["lines"].append(f"◌ 프로젝트 {slug} 에 참여했다 — 요청·문서가 그 프로젝트에 붙는다")
    return out


# ── Windows 바로 가기 (REQ-20260915-006-62x6) ────────────────────────────────
# 주인 물음 2026-09-15: 「윈도우 native 버전에서는 cmd 를 사용하지 않고 윈도우 탐색기에서
# 실행할 수 있는 환경을 만들어 주는 건 어떤가?」 zip 을 푼 폴더 맨 위의 section9.cmd 가
# 두 번 눌러 시작하는 파일이고, 첫 실행이 그것을 가리키는 바로 가기(.lnk)를 바탕화면과
# 시작 메뉴에 둔다. .lnk 는 Python 만으로는 못 만든다 — PowerShell 의 WScript.Shell COM
# 을 한 번 부른다. 실패해도 첫 실행을 막지 않고(부르는 쪽이 경고 한 줄), 이미 있으면
# 다시 만들지 않는다(사람이 지운 것을 되살리지 않는다).
LAUNCHER = "section9.cmd"
SHORTCUT_NAME = "section9.lnk"
ICON_REL = ("web", "assets", "favicon.ico")
# 바탕화면·시작 메뉴의 자리는 레지스트리(User Shell Folders)가 말한다 — OneDrive 가
# 바탕화면을 옮긴 계정에서는 %USERPROFILE%\Desktop 이 보이는 바탕화면이 아니다. 값은
# REG_EXPAND_SZ(`%USERPROFILE%\Desktop`)라 환경으로 편다: 시험이 USERPROFILE 을 임시로
# 돌리면 그대로 따라온다(실측 2026-09-15: 두 값 모두 %USERPROFILE% 로 시작). 못 읽으면 기본값.
SHELL_FOLDERS = (
    ("바탕화면", "Desktop", r"%USERPROFILE%\Desktop"),
    ("시작 메뉴", "Programs", r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
)
SHELL_FOLDERS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"


def shell_folder(name, default):
    """사용자 셸 폴더 하나 — 레지스트리 값(없으면 기본값)을 환경변수로 편 경로."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS_KEY) as k:
            val = winreg.QueryValueEx(k, name)[0]
    except (ImportError, OSError):
        val = default
    return ntpath.expandvars(val)


def shortcut_dirs():
    """[(라벨, 디렉토리)] — 바로 가기가 놓일 자리 둘."""
    return [(label, shell_folder(name, default)) for label, name, default in SHELL_FOLDERS]


def _ps_quote(text):
    """PowerShell 작은따옴표 문자열 — 안의 ' 는 '' 로."""
    return "'" + str(text).replace("'", "''") + "'"


def shortcut_script(root, paths):
    """바로 가기를 만드는 PowerShell 본문. 대상은 <root>/section9.cmd, 작업 폴더는 <root>,
    아이콘은 web/assets/favicon.ico(마크). 없는 상위 폴더는 만든다(시험의 임시 바탕화면)."""
    target = os.path.join(root, LAUNCHER)
    icon = os.path.join(root, *ICON_REL) + ",0"
    lines = ["$ErrorActionPreference = 'Stop'",
             "$sh = New-Object -ComObject WScript.Shell",
             "foreach ($p in @(" + ", ".join(_ps_quote(p) for p in paths) + ")) {",
             "  $d = Split-Path -Parent $p",
             "  if (-not (Test-Path -LiteralPath $d)) {"
             " New-Item -ItemType Directory -Path $d -Force | Out-Null }",
             "  $s = $sh.CreateShortcut($p)",
             "  $s.TargetPath = " + _ps_quote(target),
             "  $s.WorkingDirectory = " + _ps_quote(root),
             "  $s.IconLocation = " + _ps_quote(icon),
             "  $s.Description = 'section9'",
             "  $s.Save()",
             "}"]
    return "\n".join(lines) + "\n"


def remove_shortcut_script(root, paths):
    """바로 가기를 걷는 PowerShell 본문 — **이 저장소를 가리키는 것만**.

    지운 경로를 한 줄씩 찍는다. 다른 폴더의 section9(배포판을 둘 둔 컴퓨터)이 만든
    같은 이름의 바로 가기는 대상이 아니다 — 설치가 놓은 것만 걷는다는 규율이 여기서도
    같다. 없는 파일·읽을 수 없는 파일은 조용히 지나간다(걷기가 지우기를 막지 않는다)."""
    target = os.path.join(root, LAUNCHER)
    lines = ["$ErrorActionPreference = 'Stop'",
             "$sh = New-Object -ComObject WScript.Shell",
             "foreach ($p in @(" + ", ".join(_ps_quote(p) for p in paths) + ")) {",
             "  if (-not (Test-Path -LiteralPath $p)) { continue }",
             "  try { $s = $sh.CreateShortcut($p) } catch { continue }",
             "  if ($s.TargetPath -ne " + _ps_quote(target) + ") { continue }",
             "  Remove-Item -LiteralPath $p -Force",
             "  Write-Output $p",
             "}"]
    return "\n".join(lines) + "\n"


def remove_shortcuts(root, run=None, is_windows=None, dirs=None, timeout=60):
    """바탕화면·시작 메뉴의 section9.lnk 를 걷는다 — uninstall 이 부른다.

    ensure_shortcuts 의 대칭이다(REQ-20260915-006-62x6, 주인 지적 2026-09-15 13:11:
    「끄는 법, 삭제하는 법 등에 대해서는 가이드가 없는 것 같다」). 설치가 놓은 것을
    걷지 않으면 폴더를 지운 뒤 바탕화면에 아무 데도 닿지 않는 바로 가기가 남는다.

    돌려주는 것: {"removed": [지운 경로…], "skipped": 사유, "error": 한 줄}.
    skipped: not-windows · none(지울 것이 없다). 예외를 밖으로 내지 않는다."""
    res = {"removed": [], "skipped": "", "error": ""}
    win = (os.name == "nt") if is_windows is None else bool(is_windows)
    if not win:
        res["skipped"] = "not-windows"
        return res
    have = [p for p in (os.path.join(d, SHORTCUT_NAME) for _, d in (dirs or shortcut_dirs()))
            if os.path.isfile(p)]
    if not have:
        res["skipped"] = "none"
        return res
    argv = powershell_argv(remove_shortcut_script(root, have))
    run = run or subprocess.run
    try:
        r = run(argv, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except FileNotFoundError:
        res["error"] = "powershell 이 없다"
        return res
    except subprocess.TimeoutExpired:
        res["error"] = f"powershell 이 {timeout}초 안에 끝나지 않았다"
        return res
    except (OSError, ValueError) as e:
        res["error"] = str(e)
        return res
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        res["error"] = f"powershell rc={r.returncode}" + (f": {err[-1].strip()}" if err else "")
        return res
    out = (r.stdout or b"").decode("utf-8", "replace")
    res["removed"] = [ln.strip() for ln in out.splitlines() if ln.strip()]
    # 남은 것은 다른 저장소를 가리키는 바로 가기다 — 지우지 않은 사실을 말한다.
    res["kept"] = [p for p in have if os.path.isfile(p)]
    if not res["removed"]:
        res["skipped"] = "none"
    return res


def powershell_argv(script):
    """따옴표·한글 경로를 셸에 맡기지 않는다 — 본문을 UTF-16LE base64 로 넘긴다(-EncodedCommand)."""
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", enc]


def ensure_shortcuts(root, run=None, is_windows=None, dirs=None, timeout=60):
    """바탕화면·시작 메뉴에 section9.lnk 를 둔다 — Windows 에서만, 없는 것만, 한 번의 PowerShell 로.

    돌려주는 것: {"created": [라벨…], "paths": [만든 .lnk 경로…], "skipped": 사유, "error": 한 줄}.
    skipped: not-windows(다른 판) · no-launcher(최상위 section9.cmd 가 없는 자리 — 옛 배포판) ·
    exists(둘 다 이미 있다). 예외를 밖으로 내지 않는다 — 부르는 쪽은 첫 실행을 잇는다.
    """
    res = {"created": [], "paths": [], "skipped": "", "error": ""}
    win = (os.name == "nt") if is_windows is None else bool(is_windows)
    if not win:
        res["skipped"] = "not-windows"
        return res
    if not os.path.isfile(os.path.join(root, LAUNCHER)):
        res["skipped"] = "no-launcher"
        return res
    want = [(label, os.path.join(d, SHORTCUT_NAME)) for label, d in (dirs or shortcut_dirs())]
    want = [(label, p) for label, p in want if not os.path.isfile(p)]
    if not want:
        res["skipped"] = "exists"
        return res
    argv = powershell_argv(shortcut_script(root, [p for _, p in want]))
    run = run or subprocess.run
    try:
        r = run(argv, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except FileNotFoundError:
        res["error"] = "powershell 이 없다"
        return res
    except subprocess.TimeoutExpired:
        res["error"] = f"powershell 이 {timeout}초 안에 끝나지 않았다"
        return res
    except (OSError, ValueError) as e:
        res["error"] = str(e)
        return res
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        res["error"] = f"powershell rc={r.returncode}" + (f": {err[-1].strip()}" if err else "")
        return res
    made = [(label, p) for label, p in want if os.path.isfile(p)]
    res["created"] = [label for label, _ in made]
    res["paths"] = [p for _, p in made]
    missing = [p for label, p in want if not os.path.isfile(p)]
    if missing:
        res["error"] = "powershell 은 끝났는데 파일이 없다: " + ", ".join(missing)
    return res
