"""설치자가 worktree에서도 훅을 심는다 (REQ-20260829-035 에서 건진 조각).

worktree의 `.git` 은 디렉토리가 아니라 파일이다. `<repo>/.git/hooks` 를 지어내면
없는 자리를 가리키고, 설치자는 그것을 "저장소 아님"으로 오판해 훅을 **말없이**
심지 않았다. 무인 작업자는 worktree에서 돌므로 그 자리에 훅이 없으면 커밋
검사도 커밋 기록도 없다.

같은 판정이 `bin/s9-doctor` 에 이미 있었다 — 시험은 고쳤는데 설치자는 안 고친
반쪽이었고, 그 조각이 worktree에 20시간 갇혀 있었다.
"""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


def _load():
    import importlib.util
    spec = importlib.util.spec_from_loader("s9install", None)
    m = importlib.util.module_from_spec(spec)
    m.__dict__["__file__"] = os.path.abspath(INSTALL)
    src = open(INSTALL, encoding="utf-8").read()
    exec(compile(src, INSTALL, "exec"), m.__dict__)
    return m


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, timeout=30)


class InstallHooksPath(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_h1_asks_git_instead_of_building_the_path(self):
        """경로를 짓지 않고 git 에게 묻는다 — 지어내면 worktree에서 틀린다."""
        src = open(INSTALL, encoding="utf-8").read()
        self.assertIn("--git-path", src)
        self.assertNotIn('os.path.join(ROOT, ".git", "hooks")', src)

    def test_h2_plain_repo_gets_the_normal_place(self):
        with tempfile.TemporaryDirectory() as d:
            _git(d, "init", "-q")
            got = self.m.git_hooks_dir(d)
            self.assertTrue(got)
            self.assertEqual(os.path.realpath(got),
                             os.path.realpath(os.path.join(d, ".git", "hooks")))

    def test_h3_worktree_gets_a_real_place_not_a_made_up_one(self):
        """worktree에서도 빈 문자열이 아니라 실재하는 자리를 준다."""
        with tempfile.TemporaryDirectory() as d:
            main = os.path.join(d, "main")
            os.makedirs(main)
            _git(main, "init", "-q")
            _git(main, "config", "user.email", "t@t")
            _git(main, "config", "user.name", "t")
            open(os.path.join(main, "f"), "w").write("x")
            _git(main, "add", "-A")
            _git(main, "commit", "-qm", "init")
            wt = os.path.join(d, "wt")
            _git(main, "worktree", "add", "-q", wt)
            self.assertTrue(os.path.isfile(os.path.join(wt, ".git")),
                            "worktree의 .git 은 파일이어야 이 시험이 뜻을 가진다")
            got = self.m.git_hooks_dir(wt)
            self.assertTrue(got, "worktree에서 빈 자리를 주면 훅을 말없이 안 심는다")
            self.assertTrue(os.path.isabs(got))

    def test_h4_outside_a_repo_is_still_empty(self):
        """저장소가 아니면 빈 문자열 — 그 판정 자체는 살아 있어야 한다."""
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.m.git_hooks_dir(d), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
