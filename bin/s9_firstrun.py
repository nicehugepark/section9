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


# ── 신원의 사다리 (REQ-20260921-011-62x6) ────────────────────────────────────
# 기계가 호스트명으로 지어 붙이는 메일 꼬리 — 이 컴퓨터 안에서만 닿는 주소라 어느
# 계정에도 등록할 수 없다. **이 목록의 자리는 여기 하나다**: 신원을 세우는 쪽(아래
# 사다리)과 진단하는 쪽(bin/s9-doctor 의 「git 이름」)이 같은 목록을 본다. 두 벌로
# 두면 한쪽에 꼬리를 더한 날 다른 쪽이 그 주소를 멀쩡한 것으로 읽는다.
IDENT_DEAD_MAIL = (".local", ".localdomain", ".lan", ".home", "(none)")

# GitHub 이 계정마다 내주는 주소. 비밀이 아니고 사람에게 묻지 않아도 되는데 GitHub 이
# 실제로 그 계정에 이어 준다 — 사다리의 둘째 칸이 이것인 까닭이다.
GITHUB_NOREPLY = "users.noreply.github.com"

# 메일 꼴 — 프로필에 잘못 적힌 값(빈 칸·이름만·꺾쇠째)을 신원으로 세우지 않는다.
_MAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
# GitHub 계정 이름 — 영숫자와 붙임표, 39자까지. 이 꼴이 아닌 값으로 noreply 주소를
# 지으면 보내지지도 이어지지도 않는 메일이 commit 에 박힌다.
_GITHUB_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")


def is_dead_mail(email):
    """이 컴퓨터 안에서만 닿는 주소인가 — IDENT_DEAD_MAIL 을 읽는 단 하나의 판정."""
    low = str(email or "").strip().lower()
    return bool(low) and any(low.endswith(tail) for tail in IDENT_DEAD_MAIL)


def profile_mails(profile=None):
    """프로필에 적힌 쓸 수 있는 메일들 — 적힌 차례 그대로, 죽은 주소와 헛것은 뺀다."""
    prof = profile or {}
    raw = prof.get("emails") or prof.get("email") or []
    if not isinstance(raw, list):
        raw = [raw]
    out = []
    for m in raw:
        m = str(m or "").strip()
        if m and _MAIL_RE.fullmatch(m) and not is_dead_mail(m) and m not in out:
            out.append(m)
    return out


def pick_identity(profile=None, account=None, user=""):
    """신원이 아무 데도 없는 자리에 세울 (이름, 메일, 갈래) — 사다리로 고른다.

    칸은 셋이고 위에서부터 본다 (REQ-20260921-004-62x6 의 설계):

        profile   프로필에 적힌 회사·개인 메일 — 그 사람이 이미 정해 둔 주소다
        noreply   `<github>@users.noreply.github.com` — 묻지 않아도 GitHub 이 이어 준다
        temp      `s9 <계정>` / `<계정>@local` — 물을 수 없는 자리의 마지막 칸

    임시값을 첫 칸으로 두지 않는 까닭: 그 값은 이 컴퓨터 밖에서 아무 계정에도 안
    붙고, 한 번 원격 이력에 박히면 빼는 길이 이력 재작성뿐이다. 프로필이 없거나
    아무것도 못 고르면 지금까지대로 임시값이다(temp_identity 와 같은 값).

    이름은 그 사람이 GitHub 에서 불리는 글자(github)를 먼저 쓰고, 없으면 section9 의
    id 다. 임시 칸만 `s9 <계정>` 꼴을 지킨다 — `s9 doctor` 가 그 모양으로 「우리가
    넣은 값」을 가른다(REQ-20260921-006-62x6).
    """
    prof = profile or {}
    account = account or os_account()
    github = str(prof.get("github") or "").strip()
    if not _GITHUB_RE.fullmatch(github):
        github = ""
    name = github or str(user or "").strip()
    mails = profile_mails(prof)
    if mails:
        return (name or account, mails[0], "profile")
    if github:
        return (github, f"{github}@{GITHUB_NOREPLY}", "noreply")
    return temp_identity(account) + ("temp",)


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


def ensure_repo(root, gitignore, sync_marker, env=None, account=None, git="git", run=None,
                profile=None, user=""):
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
        # ④ 신원 — 전역·시스템에 없으면 저장소 로컬에 사다리가 고른 신원: 첫 commit 도,
        #    그 뒤 sync 가 거는 commit 도 신원 부재로 거부되지 않게
        if _ensure_identity(_git, account, profile, user):
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


IDENT_KEYS = ("user.name", "user.email")


def _identity_scope(_git):
    """신원이 어디에 있나 — "global"(전역·시스템) · "local"(이 저장소) · ""(아무 데도 없다).

    `git config user.name` 한 번으로는 가를 수 없다: `.git` 이 이미 있는 자리에서는
    로컬도 함께 읽혀 「전역에 정해 두었다」와 「이 저장소에 박혀 있다」가 한 값이 된다
    (REQ-20260921-003-62x6). ensure_repo 는 갓 만든 빈 `.git` 에서만 이것을 물어 그
    차이가 드러나지 않았는데, clone 으로 온 자리를 같은 함수가 지나면서 뜻이 갈렸다.

    `--local` 은 저장소 밖에서 rc≠0 이고, `--system` 은 없으면 빈 값이다 — 둘 다
    check=False 로 읽어 빈 문자열로 받는다. 이름은 로컬에 메일은 전역에 있는
    섞인 자리는 "global" 로 본다(임시 신원을 박을 까닭이 없다는 뜻만 쓰인다)."""
    def _has(*scope):
        return all(_git("config", *scope, "--get", k, check=False).stdout.strip()
                   for k in IDENT_KEYS)
    if not _has():
        return ""
    return "local" if _has("--local") else "global"


# section9 이 제 손으로 박은 값이라는 표 (REQ-20260921-012-62x6). 이것이 없으면
# **section9 이 쓴 값을 section9 이 되읽는 고리**가 생긴다: `_user_by_git_identity` 와
# `user_name_from_src` 는 git 신원을 「이 사람의 증거」로 읽는데, 그 값이 우리가 방금
# 지어낸 것이면 증거가 아니라 메아리다. architect 와 security-engineer 가 부모 요청
# (REQ-20260921-004-62x6)에서 서로 모르는 채 같은 고리를 짚었다.
#
# 표는 값의 모양이 아니라 사실을 적는다 — 사다리가 프로필 메일을 골라 사람 것과
# 똑같이 생긴 값이 박혀도, 그것을 **고른 것은 우리**다.
IDENT_MARK = ("section9.identity", "auto")


def _set_identity(_git, profile=None, account=None, user=""):
    """저장소 로컬에 신원을 박고, 우리가 박았다는 표를 함께 남긴다."""
    name, mail, src = pick_identity(profile, account, user)
    _git("config", "user.name", name)
    _git("config", "user.email", mail)
    _git("config", *IDENT_MARK, check=False)
    return name, mail, src


def is_auto_identity(_git):
    """이 저장소의 신원을 section9 이 박았나 — 표 한 줄로 판정한다."""
    key, val = IDENT_MARK
    return _git("config", "--local", "--get", key, check=False).stdout.strip() == val


def _ensure_identity(_git, account=None, profile=None, user=""):
    """신원이 아무 데도 없으면 저장소 로컬에 사다리가 고른 신원 — 했으면 True."""
    if _identity_scope(_git):
        return False
    _set_identity(_git, profile, account, user)
    return True


def ensure_identity(root, env=None, account=None, git="git", run=None,
                    profile=None, user="", upgrade=False):
    """이 자리의 git 이 누구로 commit 할지 정해져 있게 한다 (REQ-20260921-003-62x6).

    세 입구(압축을 푼 배포판 · git clone · 초대 합류)가 이 한 자리를 지난다. 그전에는
    임시 신원이 ensure_repo 와 join_repo 안에만 있어, **clone 으로 온 자리**는 어느
    갈래도 타지 않았다 — `.git` 이 이미 있어 ensure_repo 가 skipped=repo 로 빠지고
    `--join` 도 아니다. 그 컴퓨터에 user.name 이 없으면 문서 commit 이 통째로 거부되고
    `s9 doctor` 가 「git 이름」을 ✗ 로 짚는다(실측 2026-09-21).

    사람이 정해 둔 값은 덮지 않고(멱등), `~/.gitconfig` 는 건드리지 않는다 — 폭발
    반경이 이 저장소 밖이라 도구가 말없이 고칠 자리가 아니다.

    박을 값은 사다리가 고른다(pick_identity, REQ-20260921-011-62x6) — `profile` 로
    그 사람의 프로필(emails·github)을 넘기면 프로필 메일 → GitHub noreply → 임시값
    차례로 내려간다. 안 넘기면 임시값이다.

        set       True 면 이번 호출이 저장소 로컬에 신원을 박았다
        name/mail 박은 값 (set 일 때만)
        source    어느 칸을 썼나 — "profile" · "noreply" · "temp" (set 일 때만)
        scope     신원이 있는 자리 — "global" · "local"(이번에 박은 것 포함)
        auto      지금 선 값을 section9 이 박았나 (IDENT_MARK 표)
        skipped   안 한 이유 — "no-repo"(.git 이 없다) · "global" · "local" · "same"
        error     실패 사유 한 줄 — 예외를 밖으로 내지 않는다

    `upgrade=True` 는 **다시 재라**는 뜻이다 (REQ-20260921-012-62x6): 우리가 박은
    값이면 사다리를 다시 돌려 더 높은 칸이 나왔는지 본다. 사람이 등록하거나 프로필에
    메일·github 를 적은 순간이 그 자리다 — 그전에는 사다리에 재료가 없어 임시값으로
    내려갔을 뿐이고, 재료가 생겼는데도 옛 값을 그대로 두면 「나중에 고치세요」가
    영영 안 고쳐진다(실제 사고 2026-09-20: commit 166건).
    사람이 손으로 정한 값은 `upgrade` 로도 덮지 않는다.
    """
    root = os.path.abspath(root)
    out = {"set": False, "name": "", "email": "", "source": "", "scope": "",
           "skipped": "", "error": "", "auto": False}
    if not os.path.exists(os.path.join(root, ".git")):
        out["skipped"] = "no-repo"          # 저장소가 없으면 로컬에 쓸 자리도 없다
        return out
    _git = _git_runner(root, env=env, git=git, run=run)
    try:
        scope = _identity_scope(_git)
        out["auto"] = bool(scope) and is_auto_identity(_git)
        if scope and not (upgrade and out["auto"]):
            # 사람이 정해 둔 값은 덮지 않는다. 우리가 박은 값만, 그것도 다시 재라고
            # 부른 자리(upgrade)에서만 갱신한다 — 등록·프로필 수정으로 사다리의
            # 재료가 늘어난 순간이 그 자리다 (REQ-20260921-012-62x6).
            out["scope"] = out["skipped"] = scope
            return out
        if scope:
            # 다시 재기: 사다리가 같은 값을 고르면 아무것도 쓰지 않는다 — 쓰면
            # `.git/config` 의 mtime 만 흔들려 동시 작업 검사가 남의 것을 본 것처럼 군다.
            name, mail, src = pick_identity(profile, account, user)
            cur = [_git("config", "--local", "--get", k, check=False).stdout.strip()
                   for k in IDENT_KEYS]
            if cur == [name, mail]:
                out["scope"] = "local"
                out["skipped"] = "same"
                out["name"], out["email"], out["source"] = name, mail, src
                return out
        out["name"], out["email"], out["source"] = _set_identity(_git, profile, account, user)
        out["set"] = True
        out["auto"] = True
        out["scope"] = "local"
    except (OSError, subprocess.SubprocessError, RuntimeError) as e:
        out["error"] = str(e) or e.__class__.__name__
    return out


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
              git="git", run=None, profile=None, user=""):
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
        if _ensure_identity(_git, account, profile, user):
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
    # 이 컴퓨터 안에서만 닿는 주소는 프로필로 옮기지 않는다 (REQ-20260921-011-62x6):
    # 넘어오는 값은 이 컴퓨터의 `git config user.email` 인데, 신원이 없던 자리에서는
    # 그 값이 방금 우리가 박은 임시 주소(`<계정>@local`)다. 그것을 프로필에 적으면
    # 기계가 지어낸 주소가 사람의 회사 메일 옆에 영영 남고, 뒤에 서는 사다리가 그것을
    # 「그 사람이 정해 둔 주소」로 읽는다. 목록은 is_dead_mail 한 자리에 있다.
    valid_email = (bool(email) and bool(re.fullmatch(h("EMAIL_RE"), email))
                   and not is_dead_mail(email))
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
    아이콘은 web/assets/favicon.ico(마크). 없는 상위 폴더는 만든다(시험의 임시 바탕화면).
    쓴 것은 경로를 한 줄씩 찍는다 — 부르는 쪽이 무엇을 만들었는지 그 줄로 안다.

    **이미 있는 것은 대상이 살아 있을 때만 둔다** (REQ-20260918-008-62x6, 실제 사고
    2026-09-18): 바탕화면의 「section9」이 9/15 시험 때 푼 Downloads 폴더를 가리킨 채
    남아 있었고 그 폴더는 지워져 있었다 — 두 번 눌러도 아무 일이 나지 않는다. 「이미
    있으면 다시 만들지 않는다」의 뜻은 **사람이 지운 것을 되살리지 않는다**이지 죽은
    것을 그대로 둔다가 아니다. 그래서 가르는 물음은 하나다 — 그 대상이 실제로 있는가.
    있으면(다른 폴더의 section9 이어도) 사람의 것이니 두고, 없으면 지금 폴더로 고친다.
    읽지 못하는 파일은 건드리지 않는다 — 모르는 것을 덮어쓰지 않는다."""
    target = os.path.join(root, LAUNCHER)
    icon = os.path.join(root, *ICON_REL) + ",0"
    lines = ["$ErrorActionPreference = 'Stop'",
             "$sh = New-Object -ComObject WScript.Shell",
             "foreach ($p in @(" + ", ".join(_ps_quote(p) for p in paths) + ")) {",
             "  if (Test-Path -LiteralPath $p) {",
             "    $keep = $true",
             "    try { $t = $sh.CreateShortcut($p).TargetPath;"
             " if (-not $t -or -not (Test-Path -LiteralPath $t)) { $keep = $false } }"
             " catch { $keep = $true }",
             "    if ($keep) { continue }",
             "  }",
             "  $d = Split-Path -Parent $p",
             "  if (-not (Test-Path -LiteralPath $d)) {"
             " New-Item -ItemType Directory -Path $d -Force | Out-Null }",
             "  $s = $sh.CreateShortcut($p)",
             "  $s.TargetPath = " + _ps_quote(target),
             "  $s.WorkingDirectory = " + _ps_quote(root),
             "  $s.IconLocation = " + _ps_quote(icon),
             "  $s.Description = 'section9'",
             "  $s.Save()",
             "  Write-Output $p",
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
    if not want:
        res["skipped"] = "exists"
        return res
    # 부르기 전에 있던 것 — 「PowerShell 은 끝났는데 파일이 없다」 를 가리는 기준선이다.
    before = {p for _, p in want if os.path.isfile(p)}
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
    # 무엇을 썼는지는 PowerShell 이 찍은 줄로 안다 — 파일이 있는지로는 「내가 방금
    # 만든 것」과 「원래 있던 것」을 가를 수 없다(REQ-20260918-008-62x6).
    wrote = {ln.strip() for ln in (r.stdout or b"").decode("utf-8", "replace").splitlines()
             if ln.strip()}
    made = [(label, p) for label, p in want if p in wrote]
    res["created"] = [label for label, _ in made]
    res["paths"] = [p for _, p in made]
    # 없던 자리가 부른 뒤에도 비어 있으면 PowerShell 이 조용히 아무것도 안 한 것이다 —
    # 쓴 것을 찍게 해 두었으니 「찍지도 않고 만들지도 않았다」가 곧 그 신호다.
    missing = [p for _, p in want if p not in before and not os.path.isfile(p)]
    missing += [p for _, p in made if os.path.isfile(p) is False and p not in missing]
    if missing:
        res["error"] = "powershell 은 끝났는데 파일이 없다: " + ", ".join(sorted(set(missing)))
        return res
    if not made:
        res["skipped"] = "exists"
    return res
