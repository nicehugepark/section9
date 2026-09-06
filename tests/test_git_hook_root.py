"""git 훅은 worktree에서 돌아도 문서를 본 저장소에 쓴다 (REQ-20260828-011 후속).

실사고 2026-08-28 15:07. 무인 작업자가 worktree에서 REQ-20260828-007 을 고치고
커밋했더니, post-commit 훅이 남기는 "커밋 기록" 노트가 **worktree 사본의
vault/** 에 쓰였다. 본 저장소의 문서에는 아무 흔적이 없었다.

원인: 훅이 `git rev-parse --show-toplevel` 로 자리를 정한다. worktree에서 그 값은
worktree다. 코드가 갈리는 것은 의도지만(REQ-20260828-011) **데이터가 갈리는 것은
정확히 그때 막기로 한 것**이다 — 워커가 남긴 노트를 대시보드가 못 보게 된다.

그래서 훅은 스크립트는 제 자리(worktree)의 것을 쓰되 `S9_ROOT` 는 **본 저장소**로
못박는다. 본 저장소는 `--git-common-dir` 의 부모다.

실행: python3 tests/ git_hook_root
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")
HOOKS = ("post-merge", "post-checkout", "pre-commit", "post-commit")

MAIN_EXPR = ('cd "$(dirname "$(git rev-parse --git-common-dir)")" '
             '&& pwd')


def _git(cwd, *a):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for k in list(env):
        if k.startswith("GIT_DIR") or k.startswith("GIT_INDEX"):
            env.pop(k)
    return subprocess.run(["git", *a], cwd=cwd, env=env, capture_output=True,
                          text=True)


class HookRoot(unittest.TestCase):
    def setUp(self):
        self._git_env = {k: v for k, v in os.environ.items()
                         if k.startswith("GIT_")}
        for k in self._git_env:
            os.environ.pop(k, None)
        self.root = tempfile.mkdtemp(prefix="s9hook-")
        # 설치본은 자기 bin/ 을 부른다 — 실제 파일을 놓아 준다.
        shutil.copytree(os.path.join(HERE, "..", "bin"),
                        os.path.join(self.root, "bin"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "config", "user.email", "t@t")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")

    def tearDown(self):
        os.environ.update(self._git_env)
        shutil.rmtree(self.root, ignore_errors=True)

    def _install(self):
        r = subprocess.run(["python3", INSTALL, "--quiet", "--no-claude"],
                           cwd=self.root, capture_output=True, text=True,
                           env={**os.environ, "S9_ROOT": self.root},
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_n1_hooks_pin_root_to_main(self):
        self._install()
        for name in HOOKS:
            p = os.path.join(self.root, ".git", "hooks", name)
            self.assertTrue(os.path.exists(p), f"{name} 훅이 없다")
            body = open(p, encoding="utf-8").read()
            self.assertIn("git-common-dir", body,
                          f"{name}: 자리를 --show-toplevel 로만 정한다 — "
                          f"worktree에서 데이터가 갈린다")
            self.assertIn("S9_ROOT=", body,
                          f"{name}: S9_ROOT 를 본 저장소로 못박지 않는다")

    def test_b1_expression_resolves_to_main_from_worktree(self):
        wt = os.path.join(tempfile.mkdtemp(prefix="s9hookwt-"), "w")
        r = _git(self.root, "worktree", "add", "-q", "--detach", wt)
        if r.returncode != 0 or not os.path.isdir(wt):
            self.skipTest("git worktree 를 만들 수 없는 환경")
        try:
            out = subprocess.run(["sh", "-c", MAIN_EXPR], cwd=wt,
                                 capture_output=True, text=True)
            self.assertEqual(os.path.realpath(out.stdout.strip()),
                             os.path.realpath(self.root),
                             "worktree에서 본 저장소를 못 찾는다")
        finally:
            _git(self.root, "worktree", "remove", "--force", wt)


if __name__ == "__main__":
    unittest.main()
