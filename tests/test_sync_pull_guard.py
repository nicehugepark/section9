"""당길 것이 없으면 걷지 않고, 걷었으면 반드시 되돌린다 (REQ-20260914-003-62x6).

실제 사고 2026-09-14 01:27·11:17. designer 가 마크 파일(web/assets 일곱·index.html)을
굽는 사이 동기화의 `rebase --autostash` 가 돌았다. rebase 는 성공했는데 마지막
단계의 되돌리기(`stash apply`)가 그 사이 바뀐 파일에 막혀 실패했고, git 은
보관함을 `autostash` 이름으로 남기고 **returncode 0** 으로 끝났다 — stderr 의
「Applying autostash resulted in conflicts」 한 줄은 아무도 읽지 않았다. 작업
트리의 추적 파일은 HEAD 로 돌아가 있었고, 두 번 다 사람이 다시 만들었다.
`git stash list` 에는 그런 autostash 가 다섯 남아 있었다(09-06 ~ 09-14).

고정하는 계약 셋.
1. 원격에 새 commit 이 없으면 rebase 를 걸지 않는다 — 걷었다 되돌리는 일 자체가 없다.
2. rebase 가 끝났는데 보관함이 남았으면 곧바로 작업 트리에 되돌리고 보관함을 비운다.
3. 되돌리지 못하면 소리를 낸다 — sync.log 와 state/sync-stash-orphan.txt 에 sha 를
   적고, 보관함은 그대로 둔다(잃지 않는다). 남이 그 사이 쓴 파일은 덮지 않는다.

재현 장치: post-rewrite 훅이 「그 사이 다른 작업자가 같은 파일을 쓴」 일을 한다 —
git 은 commit 재생을 마친 뒤 그 훅을 부르고 나서 보관함을 되돌리므로, 되돌리기가
그 파일에 막힌다(git 2.43 실측 — returncode 0, stash@{0}: autostash).
격리: S9_ROOT=mktemp + 진짜 git 저장소(origin bare + peer). 실행: python3 tests/ sync_pull_guard
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


class PullDoesNotLoseTheTree(unittest.TestCase):
    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="s9pullguard-")
        origin = os.path.join(self.tmp, "origin.git")
        _git(self.tmp, "init", "-q", "--bare", origin)
        self.root = os.path.join(self.tmp, "work")
        _git(self.tmp, "clone", "-q", origin, self.root)
        os.makedirs(os.path.join(self.root, "state"))
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "config", "user.email", "t@t")
        self.f = os.path.join(self.root, "code.py")
        self._write("원래 줄\n")
        with open(os.path.join(self.root, "other.txt"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")
        _git(self.root, "branch", "-q", "-M", "main")
        r = _git(self.root, "push", "-q", "-u", "origin", "main")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.peer = os.path.join(self.tmp, "peer")
        _git(self.tmp, "clone", "-q", origin, self.peer)
        _git(self.peer, "config", "user.name", "p")
        _git(self.peer, "config", "user.email", "p@p")
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_pullguard", importlib.machinery.SourceFileLoader("s9_pullguard", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, text):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _body(self):
        with open(self.f, encoding="utf-8") as fh:
            return fh.read()

    def _peer_pushes(self):
        with open(os.path.join(self.peer, "other.txt"), "a", encoding="utf-8") as fh:
            fh.write("y\n")
        _git(self.peer, "commit", "-qam", "peer")
        r = _git(self.peer, "push", "-q", "origin", "HEAD:main")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _stash_list(self):
        return [ln for ln in _git(self.root, "stash", "list").stdout.splitlines() if ln.strip()]

    def _log(self):
        p = os.path.join(self.root, "state", "sync.log")
        if not os.path.exists(p):
            return ""
        with open(p, encoding="utf-8") as fh:
            return fh.read()

    # 계약 1 — 당길 것이 없으면 걷지 않는다
    def test_nothing_to_pull_means_no_stash_at_all(self):
        self._write("고친 줄\n")
        reflog_before = _git(self.root, "reflog").stdout
        r = self.m._sync_pull_cmd()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._body(), "고친 줄\n", "당길 것도 없는데 작업 트리를 건드렸다")
        self.assertEqual(self._stash_list(), [], "당길 것도 없는데 보관함을 만들었다")
        self.assertEqual(_git(self.root, "reflog").stdout, reflog_before,
                         "당길 것도 없는데 rebase 를 걸었다")

    # 계약 1 의 반대편 — 당길 것이 있으면 여전히 당긴다
    def test_a_real_pull_still_lands(self):
        self._peer_pushes()
        self._write("고친 줄\n")
        r = self.m._sync_pull_cmd()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.root, "other.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "x\ny\n", "원격의 commit 을 당기지 않았다")
        self.assertEqual(self._body(), "고친 줄\n", "당기면서 작업 트리의 변경을 잃었다")
        self.assertEqual(self._stash_list(), [])

    # 계약 2 — 남은 보관함은 곧바로 되돌아온다
    def test_a_leftover_autostash_is_put_back(self):
        self._write("고친 줄\n")
        sha = _git(self.root, "stash", "create").stdout.strip()
        self.assertTrue(sha, "보관함을 만들지 못했다")
        _git(self.root, "checkout", "-q", "--", "code.py")        # 되돌리기에 실패한 뒤의 모양
        _git(self.root, "stash", "store", "-m", "autostash", "-q", sha)   # git 이 남기는 그 이름
        self.assertEqual(self._body(), "원래 줄\n", "준비가 틀렸다")
        self.assertEqual(self.m._sync_reclaim_autostash(""), sha)
        self.assertEqual(self._body(), "고친 줄\n", "남은 보관함을 되돌리지 않았다 — 그날 그 자리")
        self.assertEqual(self._stash_list(), [], "되돌린 보관함을 비우지 않았다")
        self.assertIn("↺", self._log())

    # 경계 — 사람이 손수 넣은 보관함은 건드리지 않는다
    def test_a_hand_made_stash_is_left_alone(self):
        self._write("손수 보관\n")
        _git(self.root, "stash", "push", "-q", "-m", "내가 넣은 것")
        self.assertEqual(self.m._sync_reclaim_autostash(""), "")
        self.assertEqual(len(self._stash_list()), 1, "남의 보관함을 지웠다")
        self.assertEqual(self._body(), "원래 줄\n", "남의 보관함을 멋대로 얹었다")

    # 계약 3 — 그날의 일을 끝까지 재현: 되돌리지 못하면 소리를 내고, 아무것도 잃지 않는다
    @unittest.skipIf(os.name == "nt", "sh 훅으로 재현한다")
    def test_the_real_incident_is_loud_and_loses_nothing(self):
        self._peer_pushes()
        with open(os.path.join(self.root, "mine.txt"), "w", encoding="utf-8") as fh:
            fh.write("z\n")
        _git(self.root, "add", "mine.txt")
        _git(self.root, "commit", "-qm", "local ahead")
        self._write("고친 줄\n")
        hook = os.path.join(self.root, ".git", "hooks", "post-rewrite")
        with open(hook, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\necho "다른 작업자가 쓴 줄" > code.py\n')
        os.chmod(hook, 0o755)
        r = self.m._sync_pull_cmd()
        self.assertEqual(r.returncode, 0,
                         "git 은 이 실패를 0 으로 끝낸다 — 재현 장치가 틀렸다: " + (r.stderr or ""))
        self.assertIn("autostash", "\n".join(self._stash_list()),
                      "재현 장치가 틀렸다 — 보관함이 남지 않았다")
        self.assertEqual(self._body(), "다른 작업자가 쓴 줄\n", "남이 그 사이 쓴 파일을 덮었다")
        self.assertTrue(os.path.exists(self.m.SYNC_ORPHAN_STASH),
                        "되돌리지 못한 보관함을 아무 데도 안 적었다 — 조용한 유실이 이 사고의 본체다")
        sha = _git(self.root, "rev-parse", "refs/stash").stdout.strip()
        with open(self.m.SYNC_ORPHAN_STASH, encoding="utf-8") as fh:
            self.assertIn(sha, fh.read())
        self.assertIn("⚠", self._log())
        self.assertEqual(len(self._stash_list()), 1, "보관함을 잃었다")
        self.assertIn("고친 줄", _git(self.root, "stash", "show", "-p", "stash@{0}").stdout,
                      "보관함에 그 변경이 없다")


if __name__ == "__main__":
    unittest.main()
