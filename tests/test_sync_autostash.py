"""걷어 간 작업은 반드시 되돌아온다 (REQ-20260908-051-62x6).

실제 사고 2026-09-08 15:55. 서브에이전트 둘이 `bin/s9.py` 와 `web/` 를 고치고
있는 사이 동기화의 pull 이 돌았다. `git rebase --autostash` 가 **커밋하지 않은
494줄을 보관함으로 걷어 갔고**, rebase 는 곧바로 실패했다
(`cannot rebase: You have unstaged changes`). `.git/rebase-merge/` 에는
`autostash` 파일 하나만 남았다.

그 뒤 세 가지가 한꺼번에 일어났다.

1. 작업 트리에서 494줄이 **조용히** 사라졌다. 두 에이전트의 보고는 「고쳤다」였고
   파일은 되돌아가 있었다 — 시험을 돌려 보고서야 알았다.
2. 그 뒤의 pull 이 전부 섰다(`already a rebase-merge directory`).
3. 복구 장치가 이 모양을 몰랐다. `_sync_abort_rebase()` 는 남은 파일에서
   `orig-head`·`head-name` 을 읽는데 이번에는 없어서 `OSError` 로 그냥 물러났다 —
   남은 파일도 안 비우고 보관함도 안 되돌렸다.

고정하는 계약 넷.
1. 남은 파일이 `autostash` 하나뿐이어도 **작업 트리를 되돌린다.**
2. 되돌린 뒤에는 남은 파일을 **비운다** — 남으면 그 뒤 pull 이 전부 선다.
3. 되돌리지 못하면 **소리를 낸다** — sha 를 `state/sync-stash-orphan.txt` 에
   남기고 doctor 가 세운다. 조용한 유실이 이 사고의 본체다.
4. 다음 회차의 pull 은 남은 파일을 **먼저 치우고** 시작한다.

격리: S9_ROOT=mktemp + 진짜 git 저장소. 실행: python3 tests/ sync_autostash
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


class TheStashComesBack(unittest.TestCase):
    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="s9autostash-")
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "state"))
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "config", "user.email", "t@t")
        self.f = os.path.join(self.root, "code.py")
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write("원래 줄\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_autostash", importlib.machinery.SourceFileLoader("s9_autostash", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stash_away(self, text="남의 미완성 작업\n"):
        """커밋하지 않은 변경을 보관함으로 걷어 간다 — rebase --autostash 가 하는 그 일."""
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(text)
        r = _git(self.root, "stash", "create", "s9-test: 걷어 감")
        sha = (r.stdout or "").strip()
        self.assertTrue(sha, "보관함을 만들지 못했다")
        _git(self.root, "checkout", "-q", "--", "code.py")   # 작업 트리를 되돌린다
        return sha

    def _leftover(self, sha, whole=False):
        """rebase 가 남기고 간 자리를 만든다. whole=False 면 그날의 그 모양이다."""
        rb = os.path.join(self.root, ".git", "rebase-merge")
        os.makedirs(rb, exist_ok=True)
        with open(os.path.join(rb, "autostash"), "w", encoding="utf-8") as fh:
            fh.write(sha + "\n")
        if whole:
            head = _git(self.root, "rev-parse", "HEAD").stdout.strip()
            with open(os.path.join(rb, "orig-head"), "w", encoding="utf-8") as fh:
                fh.write(head + "\n")
            with open(os.path.join(rb, "head-name"), "w", encoding="utf-8") as fh:
                fh.write("refs/heads/main\n")
        return rb

    def _body(self):
        with open(self.f, encoding="utf-8") as fh:
            return fh.read()

    # 정상 — 그날의 그 모양(autostash 하나뿐)
    def test_an_autostash_only_leftover_is_restored(self):
        sha = self._stash_away()
        rb = self._leftover(sha)
        self.assertEqual(self._body(), "원래 줄\n", "준비가 틀렸다")
        self.assertTrue(self.m._sync_abort_rebase())
        self.assertEqual(self._body(), "남의 미완성 작업\n",
                         "걷어 간 작업이 돌아오지 않았다 — 2026-09-08 그 자리")
        self.assertFalse(os.path.isdir(rb),
                         "남은 파일을 안 비웠다 — 그 뒤 pull 이 전부 선다")

    # 경계 — 모양이 온전한 자리에서도 잃지 않는다
    def test_a_whole_leftover_also_keeps_the_work(self):
        sha = self._stash_away("온전한 자리의 작업\n")
        rb = self._leftover(sha, whole=True)
        self.assertTrue(self.m._sync_abort_rebase())
        self.assertEqual(self._body(), "온전한 자리의 작업\n")
        self.assertFalse(os.path.isdir(rb))

    # 실패 — 되돌리지 못하면 소리를 낸다
    def test_a_stash_that_cannot_be_restored_is_recorded(self):
        self._leftover("0" * 40)          # 없는 sha
        self.m._sync_abort_rebase()
        self.assertTrue(os.path.exists(self.m.SYNC_ORPHAN_STASH),
                        "되돌리지 못한 보관함을 아무 데도 안 적었다 — "
                        "조용한 유실이 이 사고의 본체다")
        with open(self.m.SYNC_ORPHAN_STASH, encoding="utf-8") as fh:
            self.assertIn("0" * 40, fh.read())

    # 경계 — 남긴 글자가 sha 가 아니면 손대지 않는다
    def test_garbage_is_not_treated_as_a_sha(self):
        rb = self._leftover("어쩌구저쩌구")
        self.assertEqual(self.m._sync_restore_autostash(rb), "")
        self.assertFalse(os.path.exists(self.m.SYNC_ORPHAN_STASH),
                         "sha 도 아닌 것을 잃은 작업으로 적었다")

    # 회귀 — 다음 pull 은 남은 파일을 먼저 치운다
    def test_the_next_pull_clears_the_leftover_first(self):
        src = open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8").read()
        i = src.find("def _sync_pull_cmd(")
        j = src.find('_sync_git("fetch"', i)
        self.assertGreater(i, 0)
        self.assertIn("_sync_abort_rebase()", src[i:j],
                      "fetch 보다 먼저 치우지 않는다 — 남은 파일이 있으면 "
                      "이번 rebase 도 무조건 선다")


if __name__ == "__main__":
    unittest.main()
