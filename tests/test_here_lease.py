"""이 자리의 목록은 남이 쥐고 있는 문서를 내지 않는다 (REQ-20260910-011).

`here_requests` 에 ③ 「담당 머신도 판도 안 적혔으면 담당자가 같은 아무
컴퓨터에나」가 들어오면서(REQ-20260910-009), 다른 컴퓨터가 지금 쥐고 있는
in-progress 문서까지 이 컴퓨터의 `s9 next` 에 「착수하라」로 올랐다. 스폰은
문서 리스가 막지만 목록은 사람이 손으로 집는 자리다 — 같은 검사가 목록에도
서야 두 컴퓨터가 한 문서를 만지지 않는다.

두 머신 왕복의 끝단 시험은 tests/test_two_machine.py (S5b)다. 이 파일은 그
판정 한 줄을 갈래마다 잰다.

실행: python3 tests/ here_lease
"""
import datetime
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class HereLease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9herelease-")
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        cls.env.update({"S9_ROOT": cls.root, "S9_MACHINE": "testbox",
                        "S9_USER": "tester"})
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls.cli("peer", "set", "저쪽", "--machine", "otherbox", "--os", "Linux")
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader(
            "s9_herelease",
            importlib.machinery.SourceFileLoader("s9_herelease", S9))
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

    def new(self, title, *extra, status=None):
        r = self.cli("new", "request", "--title", title, "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rid = r.stdout.split()[0]
        if status:
            r = self.cli("status", rid, status, "--note", "착수")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return rid

    def set_lease(self, rid, machine, ago_sec=0, user="tester"):
        """그 문서의 리스를 <machine> 이 <ago_sec> 초 전부터 쥔 것으로."""
        path = self.m.locate(rid)
        meta, body = self.m.read_doc(path)
        ts = (datetime.datetime.now().astimezone()
              - datetime.timedelta(seconds=ago_sec)).isoformat(timespec="seconds")
        meta["lease"] = {"user": user, "machine": machine, "session": "ssss1111",
                         "since": ts, "renewed": ts}
        self.m.write_doc(path, meta, body)
        self.m.rebuild_index(quiet=True)

    def here(self, machine="testbox", platform="Linux", user="tester"):
        return {r["id"] for r in self.m.here_requests(platform=platform,
                                                      machine=machine, user=user)}

    # H1. 다른 컴퓨터가 지금 쥐고 있으면 이 자리의 목록에 오르지 않는다
    def test_h1_fresh_lease_elsewhere_is_not_here(self):
        rid = self.new("저쪽이 쥔 것", status="in-progress")
        self.set_lease(rid, "otherbox")
        self.assertNotIn(rid, self.here())

    # H2. 리스가 이 컴퓨터의 것이면 그대로 오른다 — 제 자리의 일을 지우면 안 된다
    def test_h2_own_lease_stays_here(self):
        rid = self.new("내가 쥔 것", status="in-progress")
        self.set_lease(rid, "testbox")
        self.assertIn(rid, self.here())

    # H3. 리스가 만료됐으면(TTL 초과) 다시 오른다 — 저쪽이 꺼진 자리다
    def test_h3_expired_lease_comes_back(self):
        rid = self.new("저쪽이 놓은 것", status="in-progress")
        self.set_lease(rid, "otherbox", ago_sec=self.m.DOC_LEASE_TTL + 60)
        self.assertIn(rid, self.here())

    # H4. 담당 머신이 이 컴퓨터라도 저쪽이 쥐고 있으면 지금 집을 것은 아니다
    def test_h4_needs_machine_branch_honors_the_lease(self):
        rid = self.new("담당은 여기, 쥔 것은 저쪽", "--needs-machine", "testbox",
                       status="in-progress")
        self.set_lease(rid, "otherbox")
        self.assertNotIn(rid, self.here())
        self.set_lease(rid, "testbox")
        self.assertIn(rid, self.here())

    # H5. needs_os 갈래도 같은 검사를 지난다
    def test_h5_needs_os_branch_honors_the_lease(self):
        rid = self.new("이 판의 것", "--needs-os", "Linux", status="in-progress")
        self.set_lease(rid, "otherbox")
        self.assertNotIn(rid, self.here())

    # H6. 회귀 — 리스가 없는 open 요청은 여전히 담당자의 아무 컴퓨터에나 오른다
    #     (REQ-20260910-009 ③ 가 이 한 줄 때문에 좁아지면 안 된다)
    def test_h6_unleased_open_request_still_shows_everywhere(self):
        rid = self.new("담당 없는 것")
        for machine in ("testbox", "otherbox", "winbox"):
            self.assertIn(rid, self.here(machine=machine), machine)


if __name__ == "__main__":
    unittest.main()
