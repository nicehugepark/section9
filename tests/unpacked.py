"""압축을 푼 자리(배포판 모양)를 시험이 만드는 헬퍼 — test_firstrun 과 test_join 이 나눈다.

working tree 를 배포판 모양(.gitattributes 의 export-ignore 적용 · .git 없음)으로 임시 디렉토리에
복사한다. `git archive HEAD` 를 풀지 않는 까닭: HEAD 는 commit 전의 새 코드를 모른다 — commit
검사가 이 시험을 돌릴 때도 HEAD 는 옛 코드다. 그래서 `git archive --worktree-attributes` 와 같은
규칙(export-ignore)을 working tree 에 적용한다(release_shape).

test_ 로 시작하지 않는 tests/*.py 는 서드파티가 아니라 우리 헬퍼다(test_stdlib_only.local_helpers).
"""
import importlib.machinery
import importlib.util
import os
import shutil
import stat
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(cwd, *argv, env=None):
    return subprocess.run(["git", "-C", cwd, *argv], capture_output=True,
                          encoding="utf-8", errors="replace", env=env, timeout=60)


def rmtree(path):
    def _retry(fn, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            fn(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_retry)


def release_shape(dst):
    """working tree 를 배포판 모양으로 dst 에 복사한다 — 담기는 파일은 `git ls-files`
    (추적 + 미추적·비무시)이고, `.gitattributes` 의 export-ignore 가 set 인 것은 뺀다.
    export-ignore 는 디렉토리 패턴(`vault/`)이라 파일 경로로 물으면 unspecified 로
    답한다 — 상위 디렉토리(뒤에 / 를 붙인 것)까지 함께 묻는다. 반환: 복사한 파일 수."""
    ls = subprocess.run(["git", "-C", ROOT, "ls-files", "-z", "-c", "-o", "--exclude-standard"],
                        capture_output=True, check=True).stdout
    paths = [p for p in ls.decode("utf-8", "surrogateescape").split("\0") if p]
    ask = set(paths)
    for p in paths:
        parts = p.split("/")
        for i in range(1, len(parts)):
            ask.add("/".join(parts[:i]) + "/")
    out = subprocess.run(["git", "-C", ROOT, "check-attr", "-z", "--stdin", "export-ignore"],
                         input="\0".join(sorted(ask)).encode("utf-8", "surrogateescape"),
                         capture_output=True, check=True).stdout
    fields = out.decode("utf-8", "surrogateescape").split("\0")
    dropped = {fields[i] for i in range(0, len(fields) - 2, 3) if fields[i + 2] == "set"}

    def _cut(p):
        parts = p.split("/")
        return p in dropped or any("/".join(parts[:i]) + "/" in dropped
                                   for i in range(1, len(parts)))
    n = 0
    for rel in paths:
        if _cut(rel):
            continue
        src = os.path.join(ROOT, *rel.split("/"))
        if not os.path.isfile(src):        # working tree 에서 지운 파일
            continue
        dst_p = os.path.join(dst, *rel.split("/"))
        os.makedirs(os.path.dirname(dst_p), exist_ok=True)
        shutil.copy2(src, dst_p)
        n += 1
    return n


def clean_env():
    """사람의 셸에 가깝게 — 러너·훅이 실은 S9_*·GIT_* 와 git 전역 설정 자리를 걷는다."""
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("S9_", "GIT_")) and k != "XDG_CONFIG_HOME"}
