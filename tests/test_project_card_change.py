"""카드에서 프로젝트 바꾸기는 한 경로를 지난다 (REQ-20260906-053).

`s9 set <id> --project <slug>` 와 `POST /api/doc/set` 이 do_set 하나를 부른다 —
등록 프로젝트에 contribute 할 수 있는 사람만, History 한 줄, project_source=manual.

실행: python3 tests/ project_card_change
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


class ProjectCardChange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9pcc-")
        cls.base = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_USER", "S9_PROJECT"):
            cls.base.pop(k, None)
        cls.cli("init")
        for u in ("alice", "bob"):
            cls.cli("user", "add", u)
        cls.cli("project", "add", "pa", "--name", "PA", "--user", "alice")
        cls.cli("project", "add", "pb", "--name", "PB", "--user", "alice")
        cls.cli("project", "add", "pc", "--name", "PC", "--user", "bob")
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "testbox"
        spec = importlib.util.spec_from_loader(
            "s9_pcc", importlib.machinery.SourceFileLoader("s9_pcc", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        os.environ.pop("S9_MACHINE", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, *argv, user=None):
        env = dict(cls.base)
        if user:
            env["S9_USER"] = user
        return subprocess.run([S9, *argv], capture_output=True, text=True, env=env,
                              stdin=subprocess.DEVNULL, timeout=30)

    def new(self, user="alice"):
        r = self.cli("new", "request", "--title", "t", "--summary", "s", "--size", "S",
                     "--goal", "g", "--body", "b", "--user", user)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.split()[0]

    def meta(self, rid):
        return self.m.read_doc(self.m.locate(rid))

    # P1. 멤버가 바꾸면 project·project_source=manual·History 한 줄
    def test_p1_member_changes_project_with_history(self):
        rid = self.new()
        res = self.m.do_set(rid, {"project": "pb"}, actor="alice", via="dashboard")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["changed"], ["project"])
        meta, body = self.meta(rid)
        self.assertEqual(meta["project"], "pb")
        self.assertEqual(meta["project_source"], "manual")
        self.assertIn("project: ", body)
        self.assertIn("-> pb (by alice via dashboard)", body)

    # P2. 멤버가 아니면 거절 — 문서는 그대로
    def test_p2_non_member_is_refused(self):
        rid = self.new()
        with self.assertRaises(ValueError) as cm:
            self.m.do_set(rid, {"project": "pc"}, actor="alice")
        self.assertIn("권한", str(cm.exception))
        self.assertEqual(self.meta(rid)[0].get("project", ""), "")

    # P3. 없는 프로젝트는 거절 — 오타를 문서에 남기지 않는다
    def test_p3_unknown_project_is_refused(self):
        rid = self.new()
        with self.assertRaises(ValueError) as cm:
            self.m.do_set(rid, {"project": "zzz"}, actor="alice")
        self.assertIn("zzz", str(cm.exception))

    # P4. 빈 값으로 되돌릴 수 있다 — 같은 값이면 바뀐 것 없음
    def test_p4_clear_and_same_value(self):
        rid = self.new()
        self.m.do_set(rid, {"project": "pa"}, actor="alice")
        res = self.m.do_set(rid, {"project": "pa"}, actor="alice")
        self.assertEqual(res["changed"], [])
        res = self.m.do_set(rid, {"project": ""}, actor="alice")
        self.assertEqual(res["changed"], ["project"])
        self.assertEqual(self.meta(rid)[0].get("project", ""), "")

    # P5. CLI 도 같은 경로 — s9 set --project 가 거절하고 종료 코드로 말한다
    def test_p5_cli_uses_the_same_path(self):
        rid = self.new()
        r = self.cli("set", rid, "--project", "pc", user="alice")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("권한", r.stdout + r.stderr)
        r = self.cli("set", rid, "--project", "pb", user="alice")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("updated project", r.stdout)
        self.assertEqual(self.meta(rid)[0]["project"], "pb")


if __name__ == "__main__":
    unittest.main()
