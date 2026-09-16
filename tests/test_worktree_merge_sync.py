"""가지를 거둔 뒤의 첫 sync 가 사람 손 없이 지나간다 (REQ-20260916-013-62x6).

실제 사고 2026-09-16 09:29~10:00. `s9 worktree merge` 가 충돌을 내 사람이 풀고
병합 commit 을 만들었다. 그 뒤 `s9 sync` 가 **10회 연속** 졌다 — 원격 위에 로컬
commit 을 **평평하게** 다시 얹는 rebase 라, 병합 안의 해결이 버려지고 가지
commit 이 하나씩 다시 replay 되며 같은 충돌이 되살아난다. 로컬 commit 16개가
원격에 못 갔고, 워처가 REQ-20260916-012-62x6 을 올렸다.

고정하는 계약 둘.
1. 병합 안의 해결을 지킨 채 다시 얹는다 — 거둔 뒤의 첫 pull 이 그냥 지나간다.
2. 병합이 없는 회차에는 **아무 차이가 없다** — 이 판의 이력은 거의 곧은 줄이다.

격리: mktemp 에 진짜 git 저장소 둘(원격·로컬). 실행: python3 tests/ worktree_merge_sync
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


class TheFirstPullAfterAMergeGoesThrough(unittest.TestCase):

    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="s9wtsync-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.remote = os.path.join(self.tmp, "remote.git")
        self.root = os.path.join(self.tmp, "work")
        _git(self.tmp, "init", "-q", "--bare", "-b", "main", self.remote)
        os.makedirs(os.path.join(self.root, "state"))
        for a in (("init", "-q", "-b", "main"), ("config", "user.name", "t"),
                  ("config", "user.email", "t@t"),
                  ("remote", "add", "origin", self.remote)):
            _git(self.root, *a)
        self.f = os.path.join(self.root, "shared.txt")
        self.write("첫 줄\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")
        _git(self.root, "push", "-q", "-u", "origin", "main")
        os.environ["S9_ROOT"] = self.root
        self.addCleanup(os.environ.pop, "S9_ROOT", None)
        spec = importlib.util.spec_from_loader(
            "s9_wtsync", importlib.machinery.SourceFileLoader("s9_wtsync", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def write(self, text):
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, text, msg):
        self.write(text)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", msg)

    def remote_moves(self):
        """다른 컴퓨터가 원격에 자료 commit 하나를 올린다 — 이 파일은 안 건드린다."""
        side = os.path.join(self.tmp, "side")
        _git(self.tmp, "clone", "-q", self.remote, side)
        _git(side, "config", "user.name", "u")
        _git(side, "config", "user.email", "u@u")
        with open(os.path.join(side, "note.md"), "w", encoding="utf-8") as fh:
            fh.write("남의 컴퓨터가 올린 줄\n")
        _git(side, "add", "-A")
        _git(side, "commit", "-qm", "recv-beat")
        _git(side, "push", "-q", "origin", "main")

    def make_resolved_merge(self):
        """가지에서 같은 줄을 고치고, 본줄에서도 고치고, 풀어서 거둔다.

        거두는 법은 `worktree_merge` 가 하는 그대로다 — 가지를 main 위에
        **얹고**(그 자리에서 한 번 풀고) 본줄은 앞으로 감는다. 병합 commit 을
        만들지 않는 것이 이 고침의 전부다.
        """
        base = _git(self.root, "rev-parse", "HEAD").stdout.strip()
        _git(self.root, "checkout", "-q", "-b", "wt/w-1", base)
        self.commit("가지가 고친 줄\n", "가지의 고침")
        _git(self.root, "checkout", "-q", "main")
        self.commit("본줄이 고친 줄\n", "본줄의 고침")
        r = _git(self.root, "rebase", "main", "wt/w-1")
        self.assertNotEqual(0, r.returncode, "충돌이 나야 이 시험이 뜻이 있다")
        self.write("사람이 푼 줄 — 둘 다 살렸다\n")          # 사람의 해결
        _git(self.root, "add", "-A")
        env = dict(os.environ, GIT_EDITOR="true")
        subprocess.run(["git", "rebase", "--continue"], cwd=self.root,
                       capture_output=True, text=True, env=env)
        _git(self.root, "checkout", "-q", "main")
        r = _git(self.root, "merge", "--ff-only", "wt/w-1")
        self.assertEqual(0, r.returncode, "앞으로 감지 못했다: " + (r.stderr or ""))

    # 정상 — 거둔 뒤의 첫 pull 이 그냥 지나간다 (그날의 그 자리)
    def test_the_pull_after_a_resolved_merge_succeeds(self):
        self.make_resolved_merge()
        self.remote_moves()
        r = self.m._sync_pull_cmd(timeout=60)
        self.assertEqual(0, r.returncode,
                         "거둔 뒤의 첫 pull 이 졌다 — 병합 안의 해결이 버려졌다:\n"
                         + (r.stderr or ""))
        self.assertEqual(0, len(os.listdir(
            os.path.join(self.root, ".git", "rebase-merge"))
            if os.path.isdir(os.path.join(self.root, ".git", "rebase-merge")) else []),
            "rebase 가 남은 파일을 두고 갔다 — 그다음 pull 이 전부 선다")

    # 정상 — 사람이 푼 그 줄이 살아남는다
    def test_the_human_resolution_survives_the_pull(self):
        self.make_resolved_merge()
        self.remote_moves()
        self.m._sync_pull_cmd(timeout=60)
        with open(self.f, encoding="utf-8") as fh:
            self.assertEqual("사람이 푼 줄 — 둘 다 살렸다\n", fh.read())

    # 정상 — 원격의 것도 함께 들어온다
    def test_the_remote_commit_comes_in_too(self):
        self.make_resolved_merge()
        self.remote_moves()
        self.m._sync_pull_cmd(timeout=60)
        self.assertTrue(os.path.exists(os.path.join(self.root, "note.md")),
                        "원격의 commit 이 안 들어왔다")

    # 회귀 — 병합이 없는 곧은 줄에서는 아무 차이가 없다
    def test_a_straight_history_still_rebases(self):
        self.commit("이 컴퓨터가 고친 줄\n", "이 컴퓨터의 고침")
        self.remote_moves()
        r = self.m._sync_pull_cmd(timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.root, "note.md")))
        with open(self.f, encoding="utf-8") as fh:
            self.assertEqual("이 컴퓨터가 고친 줄\n", fh.read())

    # 경계 — 당길 것이 없으면 rebase 를 아예 안 건다 (REQ-20260914-003 계약)
    def test_nothing_to_pull_does_not_rebase(self):
        r = self.m._sync_pull_cmd(timeout=60)
        self.assertEqual(0, r.returncode, r.stderr)


class TheCollectorDoesNotMakeAMerge(unittest.TestCase):
    """거두는 코드가 실제로 그 길을 쓴다 (REQ-20260916-013-62x6).

    위 시험은 **방법**이 sync 를 지나간다는 것을 보인다. 이 시험은 `s9 worktree
    merge` 가 그 방법을 쓴다는 것을 본다 — 둘이 갈리면 시험은 통과하는데 사람이
    쓰는 명령은 옛길로 간다.
    """

    def setUp(self):
        with open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8") as f:
            src = f.read()
        i = src.index("def worktree_merge(")
        self.seg = src[i:i + 4000]

    def test_it_replays_the_branch_onto_the_base(self):
        self.assertIn('"rebase", base, st["branch"]', self.seg,
                      "가지를 본줄 위에 얹지 않는다")

    def test_it_fast_forwards_instead_of_merging(self):
        self.assertIn('"merge", "--ff-only"', self.seg,
                      "앞으로 감지 않는다")
        self.assertNotIn('"merge", "--no-ff"', self.seg,
                         "병합 commit 을 만든다 — 그 안의 해결을 다음 sync 가 버린다")

    def test_a_failed_replay_says_where_to_resolve_it(self):
        self.assertIn("rebase --abort", self.seg.replace('", "', " "),
                      "얹기가 지면 그 자리를 치우지 않는다")
        self.assertIn("풀고 다시 불러라", self.seg,
                      "어디서 어떻게 풀라는 말이 없다")


if __name__ == "__main__":
    unittest.main()
