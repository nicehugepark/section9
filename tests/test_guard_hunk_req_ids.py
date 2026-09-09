"""commit-msg 훅이 담긴 + 줄의 요청 id 를 커밋 메시지와 대조한다 (REQ-20260909-058).

같은 파일을 동시에 고치던 작업자들의 hunk 가 남의 커밋에 섞였다 — ff6fba57 은
036 작업자가 `git add bin/s9.py` 로 파일의 지금 상태를 담아 033/034 의 hunk
(주석에 그 id 가 적혀 있었다)가 딸려갔다. 막지 않고 **보이게** 한다: 커밋
메시지에 없는 id 가 담긴 + 줄에 있으면 그 id 와 줄 수를 경고로 찍는다.

실행: python3 tests/ guard_hunk_req_ids
"""
import importlib.machinery
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_INDEX_VERSION",
                "GIT_QUARANTINE_PATH")
MINE = "REQ-20260909-058-62x6"
OTHER = "REQ-20260909-033-62x6"


def _load():
    loader = importlib.machinery.SourceFileLoader("s9guard_hunk", GUARD)
    spec = importlib.util.spec_from_loader("s9guard_hunk", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _git(cwd, *a):
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    r = subprocess.run(["git", *a], cwd=cwd, env=env, capture_output=True,
                       text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(a)}: {r.stderr}")
    return r.stdout


class HunkReqIds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()
        cls.repo = tempfile.mkdtemp(prefix="s9hunk-")
        _git(cls.repo, "init", "-q")
        for rel in ("bin/tool.py", "vault/requests/doc.md", "docs/guide.md"):
            os.makedirs(os.path.dirname(os.path.join(cls.repo, rel)), exist_ok=True)
            with open(os.path.join(cls.repo, rel), "w", encoding="utf-8") as f:
                f.write("base\n")
        _git(cls.repo, "add", "-A")
        _git(cls.repo, "commit", "-q", "-m", "base")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.repo, ignore_errors=True)

    def _stage(self, rel, text):
        with open(os.path.join(self.repo, rel), "w", encoding="utf-8") as f:
            f.write(text)
        _git(self.repo, "add", rel)
        self.addCleanup(_git, self.repo, "reset", "-q", "--hard", "HEAD")

    def _msg(self, text):
        p = os.path.join(self.repo, "COMMIT_EDITMSG")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_same_id_is_quiet(self):
        """S1. 담긴 + 줄의 id 가 메시지(짧은 꼴)에 있으면 경고 없음."""
        self._stage("bin/tool.py", f"base\n# {MINE}\nx = 1\n")
        err = io.StringIO()
        with redirect_stderr(err):
            got = self.g.commit_msg_hunk_ids(self._msg("058 guard (REQ-20260909-058)\n"),
                                             cwd=self.repo)
        self.assertEqual(got, {})
        self.assertEqual(err.getvalue(), "")

    def test_other_id_is_warned_not_blocked(self):
        """S2. 메시지에 없는 id 는 id 와 줄 수를 경고로 찍고, 막지 않는다."""
        self._stage("bin/tool.py",
                    f"base\n# {OTHER}\ny = 2  # {OTHER}\n# {MINE}\n")
        err = io.StringIO()
        with redirect_stderr(err):
            got = self.g.commit_msg_hunk_ids(self._msg(f"058 guard ({MINE})\n"),
                                             cwd=self.repo)
        self.assertEqual(got, {OTHER: 2})
        self.assertIn(f"커밋 메시지에 없는 요청 id: {OTHER} (2줄)", err.getvalue())

    def test_documents_are_skipped(self):
        """S3. vault/·docs/·.md 의 + 줄은 세지 않는다 — 코드의 것만 센다."""
        self._stage("vault/requests/doc.md", f"base\n{OTHER}\n{OTHER}\n")
        self._stage("docs/guide.md", f"base\n{OTHER}\n")
        self._stage("bin/tool.py", f"base\n# {OTHER}\n")
        err = io.StringIO()
        with redirect_stderr(err):
            got = self.g.commit_msg_hunk_ids(self._msg("no id here\n"), cwd=self.repo)
        self.assertEqual(got, {OTHER: 1})

    def test_removed_lines_are_not_counted(self):
        """S4. 지워진(- 줄) id 는 세지 않는다."""
        self._stage("bin/tool.py", f"base\n# {OTHER}\n")
        _git(self.repo, "commit", "-q", "-m", "seed")
        self._stage("bin/tool.py", "base\n")
        got = self.g.commit_msg_hunk_ids(self._msg("remove\n"), cwd=self.repo)
        self.assertEqual(got, {})


if __name__ == "__main__":
    unittest.main()
