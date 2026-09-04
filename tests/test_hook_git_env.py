"""훅이 물려받은 git 환경이 자식에게 새지 않는가 (REQ-20260829-005).

2026-08-29 실사고. main 체크아웃에서 `git status` 가 갑자기
"fatal: this operation must be run in a work tree" 로 거부됐다. 파일은 멀쩡했고
증상은 커밋하려는 순간에야 드러났다. `.git/config` 의 core.bare 가 true 로
뒤집혀 있었고, 되돌려도 1분 안에 다시 뒤집혔다.

경로는 이렇다:
  serve 가 주인 떠난 워크트리를 자동 보존하며 `git commit`
  → git 이 pre-commit 훅에 GIT_DIR=<repo>/.git/worktrees/<이름> 을 넘긴다
  → 훅이 스테이지 테스트를 띄운다
  → 테스트가 임시 리포에 `git init` 을 부른다
  → GIT_DIR 이 `-C <임시경로>` 를 이겨 그 워크트리 자리를 다시 init 하고,
    작업 트리가 없다고 판단해 **공용 .git/config 에 core.bare=true** 를 박는다.

그래서 계약 둘을 못박는다: (1) 훅이 자식에게 주는 환경에는 GIT_* 가 없다.
(2) 벗기지 않으면 실제로 뒤집힌다 — 재현으로 그 사실을 고정한다.

실행: python3 tests/ hook_git_env
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")

spec = importlib.util.spec_from_loader(
    "s9guard", SourceFileLoader("s9guard", GUARD))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class CleanEnv(unittest.TestCase):
    def test_clean_env(self):
        """CleanEnv 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("git_vars_are_stripped"):
            dirty = {"PATH": "/usr/bin", "GIT_DIR": "/r/.git/worktrees/w",
                     "GIT_INDEX_FILE": "/r/.git/worktrees/w/index",
                     "GIT_WORK_TREE": "/r/w", "S9_USER": "keep"}
            e = guard.clean_git_env(dirty)
            for k in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
                self.assertNotIn(k, e)
            self.assertEqual(e["S9_USER"], "keep", "다른 환경까지 지우면 안 된다")
            self.assertEqual(e["PATH"], "/usr/bin")
        with self.subTest("every_known_git_var_is_listed"):
            for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                      "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR"):
                self.assertIn(k, guard.GIT_ENV_VARS)
        with self.subTest("source_of_env_defaults_to_process"):
            os.environ["GIT_DIR"] = "/nowhere/.git"
            try:
                self.assertNotIn("GIT_DIR", guard.clean_git_env())
            finally:
                os.environ.pop("GIT_DIR", None)
        with self.subTest("gate_passes_the_clean_env_to_the_test_run"):
            with open(GUARD, encoding="utf-8") as f:
                src = f.read()
            run = src[src.index("def staged_tests_gate"):]
            run = run[:run.index("\ndef ")]
            self.assertIn("env=clean_git_env()", run)

class Reproduction(unittest.TestCase):
    """벗기지 않으면 진짜로 뒤집힌다 — 위험의 크기를 시험으로 고정한다."""

    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("git 없음")
        self.tmp = tempfile.mkdtemp(prefix="s9gitenv-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = os.path.join(self.tmp, "repo")
        self.other = os.path.join(self.tmp, "other")
        os.makedirs(self.repo)
        os.makedirs(self.other)
        self._git("init", "-q", ".")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        with open(os.path.join(self.repo, "a"), "w") as f:
            f.write("a\n")
        self._git("add", "a")
        self._git("commit", "-qm", "i")
        self.wt = os.path.join(self.tmp, "wt1")
        self._git("worktree", "add", "-q", "-b", "wt1", self.wt)

    def _git(self, *argv, cwd=None, env=None):
        return subprocess.run(["git", "-C", cwd or self.repo, *argv],
                              capture_output=True, text=True, timeout=60,
                              env=env or guard.clean_git_env())

    def _bare(self):
        return self._git("config", "core.bare").stdout.strip()

    def test_leaked_git_dir_flips_shared_config_to_bare(self):
        self.assertEqual(self._bare(), "false")
        dirty = guard.clean_git_env()
        dirty["GIT_DIR"] = os.path.join(self.repo, ".git", "worktrees", "wt1")
        subprocess.run(["git", "-C", self.other, "init", "-q"], env=dirty,
                       capture_output=True, text=True, timeout=60)
        self.assertEqual(self._bare(), "true",
                         "이 재현이 깨졌다면 git 동작이 바뀐 것이다 — 확인하라")
        # 그리고 그 상태에서는 본 체크아웃이 못 쓰인다
        r = self._git("status", "--porcelain")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("work tree", r.stderr)

    def test_clean_env_keeps_the_shared_config_intact(self):
        self.assertEqual(self._bare(), "false")
        subprocess.run(["git", "-C", self.other, "init", "-q"],
                       env=guard.clean_git_env(), capture_output=True,
                       text=True, timeout=60)
        self.assertEqual(self._bare(), "false")
        self.assertEqual(self._git("status", "--porcelain").returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
