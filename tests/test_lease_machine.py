"""담당 컴퓨터가 다른 요청은 전이해도 이 세션이 점유(lease)하지 않고, open 으로
되돌리면 점유가 걷힌다 (REQ-20260913-028).

실제 사고 2026-09-13 18:17: 리드가 WSL 세션에서 맥 담당 요청(020)을 in-progress 로
전이하자 그 전이가 WSL 세션의 점유를 만들었고, 18:43 open 으로 되돌릴 때 점유가
남아 맥 보드에는 「DESKTOP 이 잡아 둔 채 진전 없음」, WSL 보드에는 「담당 컴퓨터 맥을
기다리는 중」이 함께 섰다 — 한 요청을 두 컴퓨터가 쥔 꼴.

실행: python3 tests/ lease_machine
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


class LeaseFollowsTheMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9leasemachine-")
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        cls.env.update({"S9_ROOT": cls.root, "S9_MACHINE": "testbox",
                        "S9_USER": "tester", "S9_SESSION": "abcd1234"})
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls.cli("peer", "set", "저쪽", "--machine", "otherbox", "--os", "Linux")
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader(
            "s9_leasemachine", importlib.machinery.SourceFileLoader("s9_leasemachine", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=cls.env, stdin=subprocess.DEVNULL, timeout=30)

    def new(self, *extra):
        r = self.cli("new", "request", "--title", "t", "--summary", "s", "--size", "S",
                     "--goal", "g", "--body", "b", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.split()[0]

    def lease(self, rid):
        return self.m.read_doc(self.m.locate(rid))[0].get("lease")

    def test_l1_other_machines_request_is_not_leased_by_this_session(self):
        """정상: 담당이 otherbox 인 요청을 이 세션이 in-progress 로 전이해도 점유가 생기지 않는다."""
        rid = self.new("--needs-machine", "otherbox")
        r = self.cli("status", rid, "in-progress", "--note", "저쪽 몫을 열었다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsNone(self.lease(rid), "담당 컴퓨터가 다른 요청에 이 세션의 점유가 생겼다")
        self.assertIn("담당 컴퓨터", r.stderr + r.stdout)

    def test_l2_open_drops_the_lease(self):
        """정상: 이 컴퓨터 몫으로 쥔 점유도 open 으로 되돌리면 걷힌다."""
        rid = self.new("--any-machine")
        r = self.cli("status", rid, "in-progress", "--note", "착수")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.lease(rid) or {}).get("machine"), "testbox")   # 회귀: 내 몫은 쥔다
        r = self.cli("status", rid, "open", "--force", "--note", "되돌림")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsNone(self.lease(rid), "open 으로 되돌렸는데 점유가 남았다")
        body = self.m.read_doc(self.m.locate(rid))[1]
        self.assertIn("lease release", body)


if __name__ == "__main__":
    unittest.main()
