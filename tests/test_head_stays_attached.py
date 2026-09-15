"""HEAD 는 가지에서 떨어진 채 남지 않는다 (REQ-20260916-002-62x6).

실제 사고 2026-09-16 08:17:05. 동기화의 rebase 복구가 `rebase --quit` 뒤에 친
`checkout -B main <orig>` 가 실패했는데, 그 반환값을 아무도 보지 않아 바로 다음
줄이 「되돌렸다」를 기록했다. HEAD 는 어느 가지도 가리키지 않는 자리에 남았고,
그 뒤 **26분 · commit 29건**이 거기 쌓였다. pull·push 는 전부
`fatal: HEAD does not point to a branch` 로 섰지만 commit 은 계속 되므로 겉으로는
아무 일도 없어 보였고, `s9 doctor` 는 `rev-parse --abbrev-ref HEAD` 가 주는 문자열
"HEAD" 를 가지 이름으로 찍어 **「✓ 저장소: HEAD」**를 내고 있었다.

고정하는 계약 셋.
1. 되돌리기(checkout)가 실패하면 **가지를 지금 HEAD 자리로 옮겨 붙인다** —
   되돌리지는 못해도 떨어진 채로 두지 않고 commit 도 하나도 잃지 않는다.
2. 원인이 무엇이든, 당기기 전에 떨어진 HEAD 를 보면 되붙인다.
3. doctor 는 떨어진 HEAD 를 ✓ 가 아니라 critical 로 말한다.

격리: S9_ROOT=mktemp + 진짜 git 저장소. 실행: python3 tests/ head_stays_attached
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
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class HeadStaysAttached(unittest.TestCase):

    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="s9head-")
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "state"))
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "config", "user.email", "t@t")
        self.f = os.path.join(self.root, "code.py")
        for n in ("첫 줄\n", "둘째 줄\n"):
            with open(self.f, "w", encoding="utf-8") as fh:
                fh.write(n)
            _git(self.root, "add", "-A")
            _git(self.root, "commit", "-qm", n.strip())
        os.environ["S9_ROOT"] = self.root
        self.m = _load("s9_head", S9)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _detach(self):
        """가지에서 떼어 낸 뒤 그 자리에 commit 하나를 더 쌓는다 — 그날의 그 모양."""
        _git(self.root, "checkout", "-q", "--detach", "HEAD")
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write("떨어진 자리에서 한 일\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "떨어진 자리의 commit")
        return _git(self.root, "rev-parse", "HEAD").stdout.strip()

    def _attached(self):
        r = _git(self.root, "symbolic-ref", "-q", "HEAD")
        return (r.stdout or "").strip()

    # 정상 — 떨어져 있으면 지금 자리에 붙인다
    def test_a_detached_head_is_reattached_where_it_stands(self):
        sha = self._detach()
        self.assertFalse(self._attached(), "준비가 틀렸다 — 떨어져 있어야 한다")
        self.assertTrue(self.m._sync_reattach_head("main"))
        self.assertEqual(self._attached(), "refs/heads/main")
        self.assertEqual(_git(self.root, "rev-parse", "HEAD").stdout.strip(), sha,
                         "붙이면서 commit 을 잃었다")

    # 정상 — 떨어진 자리의 commit 이 가지에 그대로 들어온다
    def test_the_commits_made_while_detached_are_kept(self):
        self._detach()
        self.m._sync_reattach_head("main")
        log = _git(self.root, "log", "--oneline", "main").stdout
        self.assertIn("떨어진 자리의 commit", log)

    # 경계 — 이미 붙어 있으면 떨어졌다고 하지 않는다
    def test_an_attached_head_is_not_reported_as_detached(self):
        self.assertFalse(self.m._sync_head_detached())
        self._detach()
        self.assertTrue(self.m._sync_head_detached())

    # 실패 — 되돌리기가 실패해도 떨어진 채 남기지 않는다 (사고의 본체)
    def test_a_failed_checkout_does_not_leave_the_head_detached(self):
        sha = self._detach()
        rb = os.path.join(self.root, ".git", "rebase-merge")
        os.makedirs(rb, exist_ok=True)
        # orig-head 를 있지도 않은 sha 로 적어 checkout -B 를 반드시 실패시킨다
        with open(os.path.join(rb, "orig-head"), "w", encoding="utf-8") as fh:
            fh.write("0" * 40 + "\n")
        with open(os.path.join(rb, "head-name"), "w", encoding="utf-8") as fh:
            fh.write("refs/heads/main\n")
        self.m._sync_abort_rebase()
        self.assertEqual(self._attached(), "refs/heads/main",
                         "되돌리기가 실패한 뒤 떨어진 채 남았다 — 2026-09-16 그 자리")
        self.assertEqual(_git(self.root, "rev-parse", "HEAD").stdout.strip(), sha,
                         "붙이면서 commit 을 잃었다")

    # 회귀 — doctor 는 떨어진 HEAD 를 ✓ 로 말하지 않는다
    def test_the_doctor_calls_a_detached_head_critical(self):
        d = _load("s9_doctor_head", DOCTOR)
        v = d.repo_verdict({"is_bare": False, "worktree_ok": True,
                            "detached": True, "head": "deadbee",
                            "branch": "HEAD", "code_dirty": [], "worktrees": 1})
        self.assertEqual(v.get("level"), "critical", v)
        self.assertNotIn("저장소: HEAD ·", v.get("line", ""),
                         "떨어진 HEAD 를 가지 이름으로 찍고 있다")

    def test_the_doctor_still_says_ok_when_attached(self):
        d = _load("s9_doctor_head2", DOCTOR)
        v = d.repo_verdict({"is_bare": False, "worktree_ok": True,
                            "detached": False, "head": "deadbee",
                            "branch": "main", "code_dirty": [], "worktrees": 1})
        self.assertEqual(v.get("level"), "ok", v)


if __name__ == "__main__":
    unittest.main()
