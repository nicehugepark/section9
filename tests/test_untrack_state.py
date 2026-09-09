"""추적된 채 남은 기계 살림을 index 에서 뺀다 — s9 doctor --untrack-state (REQ-20260909-024).

격리 저장소(bare origin + 클론 둘)로 잰다: 멱등 · 백업 · working tree 보존 · 같은 untrack 이
먼저 올라와 있으면 drop · 수정 vs 삭제 충돌(DU) 자동 해소 · guard 가 state/ staged 를 막는다.

실행: python3 tests/ untrack_state
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


class UntrackState(unittest.TestCase):

    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self._root = os.environ.get("S9_ROOT")
        self.tmp = tempfile.mkdtemp(prefix="s9untrack-")
        self.bare = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", self.bare)
        self.a = self.clone("a")
        # 옛 커밋에 추적된 살림 파일 둘 + .gitignore state/*
        os.makedirs(os.path.join(self.a, "state", "sessions"))
        with open(os.path.join(self.a, "state", "sessions", "approvals_seen.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(self.a, "state", "sessions", "M__1.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(self.a, ".gitignore"), "w") as f:
            f.write("state/*\n")
        git(self.a, "add", "-A"); git(self.a, "add", "-f", "state"); git(self.a, "commit", "-qm", "옛 추적")
        git(self.a, "push", "-q", "-u", "origin", "main")
        self.b = self.clone("b")
        os.environ["S9_ROOT"] = self.a
        name = "s9untrack_" + os.path.basename(self.tmp)
        spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def clone(self, name):
        p = os.path.join(self.tmp, name)
        if os.path.exists(os.path.join(self.bare, "refs", "heads", "main")):
            git(self.tmp, "clone", "-q", self.bare, p)
        else:
            os.makedirs(p); git(p, "init", "-q", "-b", "main"); git(p, "remote", "add", "origin", self.bare)
        git(p, "config", "user.email", "t@example.com"); git(p, "config", "user.name", name)
        return p

    def tearDown(self):
        if self._root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self._root
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tracked(self, cwd):
        return [l for l in git(cwd, "ls-files", "-ci", "--exclude-standard").stdout.splitlines() if l]

    def test_u3_idempotent_backup_and_working_tree_kept(self):
        m = self.m
        self.assertEqual(len(self.tracked(self.a)), 2)
        with open(os.path.join(self.a, "state", "sessions", "approvals_seen.json"), "w") as f:
            f.write('{"mine": 1}')          # 로컬 변경 — 그대로 남아야 한다
        res = m.untrack_state(root=self.a, out=lambda *a: None)
        self.assertEqual((res["tracked"], res["committed"], res["pushed"]), (2, True, True), res)
        self.assertEqual(self.tracked(self.a), [])
        self.assertTrue(os.path.exists(os.path.join(self.a, "state", "sessions", "M__1.json")), "working tree 파일이 지워졌다")
        with open(os.path.join(self.a, "state", "sessions", "approvals_seen.json")) as f:
            self.assertEqual(f.read(), '{"mine": 1}')
        self.assertTrue(os.path.isdir(res["backup"]))
        again = m.untrack_state(root=self.a, out=lambda *a: None)
        self.assertEqual((again["tracked"], again["committed"]), (0, False), "멱등이 아니다")

    def test_u3b_second_clone_drops_its_own_untrack_and_keeps_files(self):
        m = self.m
        m.untrack_state(root=self.a, out=lambda *a: None)           # a 가 먼저 올렸다
        with open(os.path.join(self.b, "state", "sessions", "approvals_seen.json"), "w") as f:
            f.write('{"b": 1}')                                      # b 도 로컬 변경 (b) 상태
        res = m.untrack_state(root=self.b, out=lambda *a: None)
        self.assertTrue(res["committed"], res)
        self.assertEqual(self.tracked(self.b), [])
        with open(os.path.join(self.b, "state", "sessions", "approvals_seen.json")) as f:
            self.assertEqual(f.read(), '{"b": 1}', "b 의 파일이 사라지거나 덮였다")
        self.assertEqual(git(self.b, "status", "--porcelain").stdout.strip(), "", "rebase 가 남았다")
        self.assertEqual(git(self.b, "rev-parse", "HEAD").stdout, git(self.b, "rev-parse", "origin/main").stdout)

    def test_u3c_modify_delete_conflict_is_resolved(self):
        m = self.m
        # b 가 그 파일을 고쳐 commit 해 둔 (d) 상태에서 a 의 untrack 이 먼저 올라간다
        with open(os.path.join(self.b, "state", "sessions", "approvals_seen.json"), "w") as f:
            f.write('{"b": 2}')
        git(self.b, "commit", "-qam", "b 가 고침")
        m.untrack_state(root=self.a, out=lambda *a: None)
        res = m.untrack_state(root=self.b, out=lambda *a: None)
        self.assertNotEqual(res["note"], "rebase stuck", res)
        self.assertEqual(self.tracked(self.b), [])
        self.assertEqual(git(self.b, "status", "--porcelain").stdout.strip(), "")
        with open(os.path.join(self.b, "state", "sessions", "approvals_seen.json")) as f:
            self.assertEqual(f.read(), '{"b": 2}')

    def test_u5_guard_refuses_added_state_but_not_deletions(self):
        """더하는 것(A/M)은 막고, untrack 의 삭제(D)는 지나간다 — 맥 실측 2026-09-09."""
        spec = importlib.util.spec_from_loader("s9guard_t", importlib.machinery.SourceFileLoader("s9guard_t", GUARD))
        g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
        g.ROOT = self.a
        os.makedirs(os.path.join(self.a, "state", "x"), exist_ok=True)
        with open(os.path.join(self.a, "state", "x", "new.json"), "w") as f:
            f.write("{}")
        git(self.a, "add", "-f", "state/x/new.json")
        with self.assertRaises(SystemExit):
            g.state_gate(["state/x/new.json"])
        git(self.a, "reset", "-q", "state/x/new.json")
        git(self.a, "rm", "-r", "-q", "--cached", "state/sessions")        # untrack 의 모양(D)
        g.state_gate(["state/sessions/approvals_seen.json", "state/sessions/M__1.json"])   # 지나간다
        g.state_gate(["bin/s9.py", "vault/x.md"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
