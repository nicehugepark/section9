"""post-commit 은 자기 sha 를 본다 (REQ-20260906-020).

훅이 도는 사이 sync(remote) 가 문서 커밋을 얹으면 HEAD 는 남의 커밋이다 — 실측 2026-09-06:
code 커밋 셋에 배경 전체 실행이 한 번도 뜨지 않았다.

실행: python3 tests/ after_commit_sha
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GUARD = os.path.join(REPO, "bin", "s9-guard")
INSTALL = os.path.join(REPO, "bin", "s9-install")


class AfterCommitSha(unittest.TestCase):
    def test_a1_wide_check_uses_the_given_sha_not_head(self):
        """A1. code 커밋 뒤에 문서 커밋이 얹혀도, 그 code 커밋의 sha 로 물으면 「넓다」다."""
        root = tempfile.mkdtemp(prefix="s9acs-")
        def git(*a):
            return subprocess.run(["git", "-C", root, *a], capture_output=True, text=True, check=True).stdout.strip()
        git("init", "-q", "-b", "main")
        for p, body in (("bin/s9.py", "x = 1\n"), ("vault/x.md", "a\n")):
            os.makedirs(os.path.join(root, os.path.dirname(p)), exist_ok=True)
            open(os.path.join(root, p), "w").write(body)
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
        open(os.path.join(root, "bin", "s9.py"), "a").write("y = 2\n")
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "code")
        code_sha = git("rev-parse", "HEAD")
        open(os.path.join(root, "vault", "x.md"), "a").write("note\n")
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "s9 sync: note")
        old = os.environ.get("S9_ROOT"); os.environ["S9_ROOT"] = root
        try:
            spec = importlib.util.spec_from_loader(
                "s9guard_acs", importlib.machinery.SourceFileLoader("s9guard_acs", GUARD))
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            m.ROOT = root                 # s9-guard 의 ROOT 는 제 파일 위치다 — 임시 저장소로 돌린다
        finally:
            if old is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = old
        self.assertEqual(m.head_touches_wide(code_sha), ["bin/s9.py"])
        self.assertEqual(m.head_touches_wide(), [], "HEAD 는 문서 커밋이라 넓지 않다")

    def test_a2_installed_hook_hands_its_own_sha(self):
        """A2. 설치가 놓는 post-commit 훅은 commit-note 전에 sha 를 잡아 --after-commit 에 넘긴다."""
        src = open(INSTALL, encoding="utf-8").read()
        self.assertIn('SHA="$(git rev-parse HEAD)"', src)
        self.assertIn('--after-commit "$SHA"', src)
        i_sha = src.index('SHA="$(git rev-parse HEAD)"'); i_note = src.index('commit-note ', i_sha)
        self.assertLess(i_sha, i_note, "sha 는 commit-note 보다 먼저 잡는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
