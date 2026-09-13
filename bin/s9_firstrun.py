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
import getpass
import os
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
    base = dict(os.environ if env is None else env)
    for k in GIT_SCOPE_VARS:
        base.pop(k, None)
    run = run or subprocess.run

    def _git(*argv, check=True):
        r = run([git, "-C", root, *argv], capture_output=True, encoding="utf-8",
                errors="replace", env=base, timeout=120)
        if check and r.returncode != 0:
            lines = (r.stderr or r.stdout or "").strip().splitlines()
            raise RuntimeError(f"git {argv[0]}: {lines[-1] if lines else 'rc=' + str(r.returncode)}")
        return r

    git_dir = os.path.join(root, ".git")
    made_marker = ""
    try:
        # ① init — 가지는 언제나 main. init.defaultBranch 가 없는 머신은 master 를
        #    만들고, 옛 git(< 2.28)에는 -b 가 없다.
        r = _git("init", "-q", "-b", DEFAULT_BRANCH, check=False)
        if r.returncode != 0:
            _git("init", "-q")
            _git("symbolic-ref", "HEAD", "refs/heads/" + DEFAULT_BRANCH)
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
        have = all(_git("config", k, check=False).stdout.strip()
                   for k in ("user.name", "user.email"))
        if not have:
            name, mail = temp_identity(account)
            _git("config", "user.name", name)
            _git("config", "user.email", mail)
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
