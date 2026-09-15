"""`s9 commit` — 한 working tree 에서 여럿이 commit 하는 정식 길 (REQ-20260913-022-62x6).

실측 2026-09-13, 작업자 9명이 한 working tree 에서 commit 하며 겪은 넷:
① 공유 index 에 남의 `git add` 가 섞여 「내 것만」 commit 을 가를 수 없었다.
② 각자 지어낸 임시 index(GIT_INDEX_FILE) commit 은 `.git/index.lock` 을 잡지 않아 sync 회차가
   훅 실행 중 HEAD 를 옮겼고 `cannot lock ref HEAD` 로 두 번 실패했다.
③ `git add <경로>` 는 그 파일의 지금 상태를 담아 남의 미완성 hunk 를 함께 실었다.
④ 동시 작업 표는 공유 index 가 바뀔 때마다 바뀌어 사람이 두세 번 다시 걸어야 했다.

그리고 임시 index 절차(DOC-20260913-004-62x6)에 없던 다섯째: commit 뒤 공유 index 의 그 경로는
옛 HEAD blob 그대로라 `git diff --cached` 가 내 변경의 역방향을 담긴 것으로 보이고, 다음
사람의 pathspec 없는 commit 이 내 변경을 되돌린다 (scratch 저장소 실측).

여기서는 `s9 commit` 이 그 다섯을 닫는지 임시 저장소(S9_ROOT=mktemp)에서 잰다. 훅은 이
시험이 심는 작은 셸 스크립트다 — 진짜 guard 의 검사는 그 시험(commit_gate·wide_gate)이 잰다;
여기서 재는 것은 「훅이 임시 index 아래에서 실행되고 거부가 상태를 남기지 않는다」다.

실행: python3 tests/ s9_commit
"""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_INDEX_VERSION",
                "GIT_QUARANTINE_PATH")
BASE_FILES = ("a.txt", "b.txt", "g.txt", "h_mine.txt", "h_other.txt", "m5.txt",
              "w8.txt", "zz_unchanged.txt")


def _env(root, **extra):
    e = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    e.update(S9_ROOT=root, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
             GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    e.pop("S9_ALLOW_CONCURRENT", None)
    e.update(extra)
    return e


class S9Commit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in cls._genv:
            os.environ.pop(k, None)
        cls._root_env = os.environ.get("S9_ROOT")
        cls.tmp = tempfile.mkdtemp(prefix="s9commit-t-")
        cls.repo = os.path.join(cls.tmp, "work")
        os.makedirs(os.path.join(cls.repo, "vault"))
        cls._git("init", "-q", "-b", "main")
        cls._git("config", "user.name", "t")
        cls._git("config", "user.email", "t@t")
        for name in BASE_FILES:
            cls._write(name, name.split(".")[0] + "\n")
        cls._write("f.txt", "".join(f"{i}\n" for i in range(1, 21)))
        cls._write("vault/seed.md", "seed\n")
        cls._write(".s9-sync", "local\n")
        cls._git("add", "-A")
        cls._git("commit", "-q", "-m", "base")
        os.environ["S9_ROOT"] = cls.repo
        spec = importlib.util.spec_from_loader(
            "s9_for_commit", importlib.machinery.SourceFileLoader("s9_for_commit", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        if cls._root_env is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = cls._root_env
        os.environ.update(cls._genv)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- 살림
    @classmethod
    def _git(cls, *a):
        r = subprocess.run(["git", "-C", cls.repo, *a], env=_env(cls.repo),
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise AssertionError(f"git {' '.join(a)}: {r.stderr}")
        return r.stdout

    @classmethod
    def _write(cls, rel, text):
        p = os.path.join(cls.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def _s9(self, *a, timeout=60):
        return subprocess.run([sys.executable, S9, "commit", *a], cwd=self.repo,
                              env=_env(self.repo), capture_output=True, text=True,
                              timeout=timeout)

    def _head(self):
        return self._git("rev-parse", "HEAD").strip()

    def _head_files(self):
        return sorted(n for n in self._git("diff-tree", "-r", "--no-commit-id",
                                           "--name-only", "HEAD").splitlines() if n)

    def _staged(self):
        return sorted(n for n in self._git("diff", "--cached", "--name-only").splitlines() if n)

    def _index_blob(self, rel):
        out = self._git("ls-files", "-s", "--", rel).split()
        return out[1] if len(out) >= 2 else None

    def _hook(self, body):
        d = os.path.join(self.repo, ".git", "hooks")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "pre-commit")
        with open(p, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n" + body)
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
        self.addCleanup(lambda: os.path.exists(p) and os.remove(p))

    # ---------------------------------------------------------------- C1·C2
    def test_c1_c2_paths_only_and_shared_index_reconciled(self):
        """C1 경로 한정 · C2 공유 index 반영 (남이 담은 항목은 그대로)."""
        old = self._head()
        self._write("a.txt", "a2\n")
        self._write("b.txt", "b2\n")
        self._git("add", "--", "b.txt")               # 남이 담아 둔 것
        other_blob = self._index_blob("b.txt")
        r = self._s9("-m", "c1: a 만", "--", "a.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with self.subTest("c1_commit_has_only_named_path"):
            self.assertEqual(self._git("rev-parse", "HEAD~1").strip(), old)
            self.assertEqual(self._head_files(), ["a.txt"])
            self.assertEqual(self._git("show", "HEAD:a.txt"), "a2\n")
            self.assertEqual(self._git("show", "HEAD:b.txt"), "b\n", "남의 담긴 변경이 실렸다")
        with self.subTest("c1_others_staged_entry_untouched"):
            self.assertIn("b.txt", self._staged())
            self.assertEqual(self._index_blob("b.txt"), other_blob)
            with open(os.path.join(self.repo, "b.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "b2\n", "working tree 가 바뀌었다")
        with self.subTest("c2_shared_index_matches_new_head_for_my_path"):
            # 맞추지 않으면 index 는 옛 HEAD blob 이라 역방향(-a2 +a)이 담긴 것으로 보인다
            self.assertNotIn("a.txt", self._staged())
            self.assertEqual(self._index_blob("a.txt"),
                             self._git("rev-parse", "HEAD:a.txt").strip())
        with self.subTest("c2_others_staged_same_path_is_kept"):
            self._write("a.txt", "aX\n")
            self._git("add", "--", "a.txt")            # 남이 같은 경로를 담아 둠
            theirs = self._index_blob("a.txt")
            self._write("a.txt", "aY\n")
            r = self._s9("-m", "c1b", "--", "a.txt")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self._git("show", "HEAD:a.txt"), "aY\n")
            self.assertEqual(self._index_blob("a.txt"), theirs,
                             "남이 담아 둔 항목을 새 HEAD 로 덮었다")

    # ---------------------------------------------------------------- C3
    def test_c3_hunks_only_and_patch_scope(self):
        """--hunks: patch 의 hunk 만 · patch 가 지정 밖 경로를 건드리면 exit 2."""
        lines = [f"{i}\n" for i in range(1, 21)]
        lines[1] = "2x\n"
        lines[18] = "19x\n"
        self._write("f.txt", "".join(lines))
        diff = self._git("diff", "--", "f.txt")
        parts = re.split(r"(?m)^(?=@@ )", diff)          # [머리, 첫 hunk, 둘째 hunk]
        self.assertEqual(len(parts), 3, diff)
        patch = os.path.join(self.tmp, "c3.patch")
        with open(patch, "w", encoding="utf-8") as f:
            f.write(parts[0] + parts[1])
        old = self._head()
        r = self._s9("-m", "c3: hunk 하나", "--hunks", patch, "--", "f.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with self.subTest("only_first_hunk_committed"):
            body = self._git("show", "HEAD:f.txt")
            self.assertIn("2x\n", body)
            self.assertNotIn("19x\n", body, "둘째 hunk 까지 실렸다")
            self.assertEqual(self._head_files(), ["f.txt"])
        with self.subTest("working_tree_keeps_both_hunks"):
            with open(os.path.join(self.repo, "f.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "".join(lines))
            self.assertNotIn("f.txt", self._staged(), "공유 index 가 새 HEAD 와 다르다")
            self.assertIn("19x", self._git("diff", "--", "f.txt"))
        with self.subTest("patch_outside_named_paths_is_refused"):
            self._write("g.txt", "g2\n")
            gp = os.path.join(self.tmp, "c3g.patch")
            with open(gp, "w", encoding="utf-8") as f:
                f.write(self._git("diff", "--", "g.txt"))
            before = self._head()
            r = self._s9("-m", "x", "--hunks", gp, "--", "f.txt")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("g.txt", r.stderr)
            self.assertEqual(self._head(), before)
        self.assertNotEqual(self._head(), old)

    # ---------------------------------------------------------------- C4
    def test_c4_hook_runs_on_temp_index_and_rejection_cleans_up(self):
        """훅이 임시 index 아래에서 돈다(지정 경로만 본다) · 훅 거부는 상태를 남기지 않는다."""
        saw = os.path.join(self.tmp, "hook-saw.txt")
        idx = os.path.join(self.tmp, "hook-idx.txt")
        self._hook(f'git diff --cached --name-only > "{saw}"\n'
                   f'printf "%s" "$GIT_INDEX_FILE" > "{idx}"\n')
        self._write("h_other.txt", "other2\n")
        self._git("add", "--", "h_other.txt")          # 공유 index 의 남의 항목
        self._write("h_mine.txt", "mine2\n")
        r = self._s9("-m", "c4", "--", "h_mine.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with self.subTest("hook_saw_only_my_path"):
            with open(saw, encoding="utf-8") as f:
                self.assertEqual(f.read().split(), ["h_mine.txt"])
            with open(idx, encoding="utf-8") as f:
                got = f.read()
            self.assertIn("s9commit-", got, "훅이 공유 index 를 봤다")
            self.assertFalse(os.path.exists(got), "임시 index 가 남았다")
        with self.subTest("hook_rejection_leaves_nothing_behind"):
            self._hook('echo "guard: 거부" >&2\nexit 1\n')
            self._write("h_mine.txt", "mine3\n")
            before = self._head()
            r = self._s9("-m", "c4b", "--", "h_mine.txt")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("거부", r.stderr)
            self.assertEqual(self._head(), before)
            st = os.path.join(self.repo, "state")
            self.assertFalse(os.path.exists(os.path.join(st, "s9-commit-in-progress")))
            self.assertFalse(os.path.exists(os.path.join(st, ".sync.lock")))
            left = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith("s9commit-")
                    and not d.startswith("s9commit-t-")]
            self.assertEqual(left, [], "임시 index 디렉토리가 남았다")

    # ---------------------------------------------------------------- C5
    def test_c5_sync_round_is_deferred_while_commit_runs(self):
        """훅이 도는 동안 sync_run 은 busy 를 돌려주고 HEAD 를 옮기지 않는다."""
        flag = os.path.join(self.tmp, "in-hook")
        if os.path.exists(flag):
            os.remove(flag)
        self._hook(f'touch "{flag}"\nsleep 1.5\n')
        self._write("m5.txt", "m5-2\n")
        self._write("vault/c5.md", "doc\n")            # sync 가 담고 싶어 할 문서
        old = self._head()
        p = subprocess.Popen([sys.executable, S9, "commit", "-m", "c5", "--", "m5.txt"],
                             cwd=self.repo, env=_env(self.repo),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            t0 = time.time()
            while not os.path.exists(flag) and time.time() - t0 < 15:
                time.sleep(0.05)
            self.assertTrue(os.path.exists(flag), "훅이 시작되지 않았다")
            self.assertEqual(self.m._sync_commit_busy(), "s9-commit")
            self.assertEqual(self.m.sync_run("c5"), "busy", "sync 회차가 commit 중에 들어갔다")
            self.assertEqual(self._head(), old, "sync 가 훅 실행 중 HEAD 를 옮겼다")
        finally:
            out = p.communicate(timeout=60)[0]
        self.assertEqual(p.returncode, 0, out)
        self.assertEqual(self._git("rev-parse", "HEAD~1").strip(), old)
        self.assertEqual(self._head_files(), ["m5.txt"])
        self.assertIn("?? vault/c5.md", self._git("status", "--porcelain"))
        # 잠금·표식이 걷힌 뒤에는 회차가 그대로 들어간다
        self.assertEqual(self.m.sync_run("c5-after"), "local")
        self.assertEqual(self._head_files(), ["vault/c5.md"])

    # ---------------------------------------------------------------- C6
    def test_c6_mark_contract(self):
        """표식: pid 가 살아 있으면 busy, 죽었으면 무시 · poll 과 lease pull 도 그 표식을 본다."""
        mark = self.m._S9_COMMIT_MARK
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        self.addCleanup(lambda: os.path.exists(mark) and os.remove(mark))
        with open(mark, "w", encoding="utf-8") as f:
            f.write(f"pid {os.getpid()} now\n")
        self.assertEqual(self.m._sync_commit_busy(), "s9-commit")
        with mock.patch.object(self.m, "sync_mode", return_value="remote"), \
             mock.patch.object(self.m, "_sync_poll_once") as po, \
             mock.patch.object(self.m, "_sync_pull_cmd") as pc:
            self.assertEqual(self.m.sync_poll(), "none")
            po.assert_not_called()
            self.m._pull_if_stale()
            pc.assert_not_called()
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        with open(mark, "w", encoding="utf-8") as f:
            f.write(f"pid {dead.pid} now\n")
        self.assertEqual(self.m._sync_commit_busy(), "", "죽은 s9 commit 의 표식이 회차를 세운다")

    # ---------------------------------------------------------------- C7
    def test_c7_rejections(self):
        """경로 없음 · 변경 없음 · 메시지 없음 · 없는 경로 → exit 2, commit 없음."""
        before = self._head()
        for label, argv, word in (
                ("no_paths", ("-m", "x"), "경로"),
                ("unchanged", ("-m", "x", "--", "zz_unchanged.txt"), "변경이 없다"),
                ("no_message", ("--", "zz_unchanged.txt"), "메시지"),
                ("missing_path", ("-m", "x", "--", "nope.txt"), "nope.txt")):
            with self.subTest(label):
                r = self._s9(*argv)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(word, r.stderr)
                self.assertEqual(self._head(), before)

    # ---------------------------------------------------------------- C8
    def test_c8_waits_for_sync_lock(self):
        """신선한 state/.sync.lock 이 있으면 --wait 안에 못 잡고 exit 3; 사라지면 성공."""
        lock = os.path.join(self.repo, "state", ".sync.lock")
        os.makedirs(os.path.dirname(lock), exist_ok=True)
        with open(lock, "w"):
            pass
        self.addCleanup(lambda: os.path.exists(lock) and os.remove(lock))
        self._write("w8.txt", "w8-2\n")
        before = self._head()
        t0 = time.time()
        r = self._s9("--wait", "1", "-m", "c8", "--", "w8.txt")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertGreaterEqual(time.time() - t0, 1.0)
        self.assertEqual(self._head(), before)
        self.assertTrue(os.path.exists(lock), "남의 잠금을 지웠다")
        os.remove(lock)
        r = self._s9("-m", "c8", "--", "w8.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._head_files(), ["w8.txt"])


class Worktree(unittest.TestCase):
    """worktree 안에서도 `s9 commit` 이 돈다 (REQ-20260915-022-62x6).

    ROOT 는 **데이터**의 자리이고 worktree 는 코드만 가른다(`s9 worktree add` 가
    S9_ROOT 를 본 저장소로 못박는다). 그런데 담을 것을 ROOT 에서 세는 바람에
    worktree 안에서는 늘 「HEAD 대비 변경이 없다」였고, 작업자는 임시 index 도
    sync 잠금도 없는 plain git 으로 밀려났다.
    """

    @classmethod
    def setUpClass(cls):
        cls._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in cls._genv:
            os.environ.pop(k, None)
        cls.tmp = tempfile.mkdtemp(prefix="s9commit-wt-")
        cls.repo = os.path.join(cls.tmp, "work")
        os.makedirs(os.path.join(cls.repo, "vault"))
        for a in (("init", "-q", "-b", "main"), ("config", "user.name", "t"),
                  ("config", "user.email", "t@t")):
            cls._git(cls.repo, *a)
        for rel, body in (("a.txt", "a\n"), ("vault/seed.md", "seed\n")):
            cls._write(cls.repo, rel, body)
        cls._git(cls.repo, "add", "-A")
        cls._git(cls.repo, "commit", "-q", "-m", "base")
        cls.wt = os.path.join(cls.tmp, "wt-one")
        cls._git(cls.repo, "worktree", "add", "-q", "-b", "wt/one", cls.wt)
        # 같은 저장소가 아닌 자리 — 옮기지 않는 것을 재는 대조군
        cls.other = os.path.join(cls.tmp, "other")
        os.makedirs(cls.other)
        for a in (("init", "-q", "-b", "main"), ("config", "user.name", "t"),
                  ("config", "user.email", "t@t")):
            cls._git(cls.other, *a)
        cls._write(cls.other, "z.txt", "z\n")
        cls._git(cls.other, "add", "-A")
        cls._git(cls.other, "commit", "-q", "-m", "base")

    @classmethod
    def tearDownClass(cls):
        os.environ.update(cls._genv)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _git(cls, where, *a):
        r = subprocess.run(["git", "-C", where, *a], env=_env(where),
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise AssertionError(f"git {' '.join(a)}: {r.stderr}")
        return r.stdout

    @classmethod
    def _write(cls, where, rel, text):
        p = os.path.join(where, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def _s9(self, cwd, *a, timeout=90):
        """S9_ROOT 는 늘 본 저장소다 — worktree 가 데이터를 가르지 않는다."""
        return subprocess.run([sys.executable, S9, "commit", *a], cwd=cwd,
                              env=_env(self.repo), capture_output=True, text=True,
                              timeout=timeout)

    def test_it_commits_in_the_worktree_i_stand_in(self):
        main_head = self._git(self.repo, "rev-parse", "HEAD").strip()
        self._write(self.wt, "a.txt", "worktree 에서 고쳤다\n")
        r = self._s9(self.wt, "-m", "wt: a.txt", "--", "a.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with self.subTest("그 worktree 의 branch 에 담겼다"):
            self.assertEqual(self._git(self.wt, "show", "HEAD:a.txt"),
                             "worktree 에서 고쳤다\n")
            self.assertEqual(self._git(self.wt, "rev-parse", "--abbrev-ref", "HEAD").strip(),
                             "wt/one")
        with self.subTest("본 저장소의 HEAD 는 그대로다"):
            self.assertEqual(self._git(self.repo, "rev-parse", "HEAD").strip(), main_head)
        with self.subTest("그 worktree 의 index 가 새 HEAD 에 맞춰졌다"):
            self.assertEqual(
                [n for n in self._git(self.wt, "diff", "--cached", "--name-only").splitlines() if n],
                [], "역방향이 담긴 것으로 보인다 — 다음 commit 이 되돌린다")

    def test_an_absolute_path_resolves_against_that_worktree(self):
        self._write(self.wt, "a.txt", "절대 경로로\n")
        r = self._s9(self.wt, "-m", "wt: 절대 경로", "--",
                     os.path.join(self.wt, "a.txt"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._git(self.wt, "show", "HEAD:a.txt"), "절대 경로로\n")

    def test_in_the_main_repo_nothing_changes(self):
        """회귀: 본 저장소에서 부르면 종전대로 본 저장소에 담는다."""
        self._write(self.repo, "a.txt", "본 저장소에서\n")
        r = self._s9(self.repo, "-m", "main: a.txt", "--", "a.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._git(self.repo, "show", "HEAD:a.txt"), "본 저장소에서\n")

    def test_another_repository_is_not_touched(self):
        """남의 저장소 안에서 불러도 그 저장소는 안 건드린다 — ROOT 에서 담는다."""
        other_head = self._git(self.other, "rev-parse", "HEAD").strip()
        self._write(self.other, "z.txt", "남의 것\n")
        self._write(self.repo, "a.txt", "ROOT 에서 담긴다\n")
        r = self._s9(self.other, "-m", "other 에서 불렀다", "--", "a.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._git(self.other, "rev-parse", "HEAD").strip(), other_head,
                         "남의 저장소에 commit 했다")
        self.assertEqual(self._git(self.repo, "show", "HEAD:a.txt"), "ROOT 에서 담긴다\n")


if __name__ == "__main__":
    unittest.main()