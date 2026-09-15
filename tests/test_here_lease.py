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
        # 담당을 안 말한 요청은 이 시험에서 「어느 컴퓨터에서나」다 (REQ-20260911-004-2n7g:
        # 기본값이 세운 컴퓨터로 바뀌어 그 뜻은 --any-machine 으로 적는다)
        anyw = () if any(a in ("--needs-machine", "--needs-os") for a in extra) else ("--any-machine",)
        r = self.cli("new", "request", "--title", title, "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b", *anyw, *extra)
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

    def here_as(self, session, alive, machine="testbox", user="tester"):
        """세션 <session> 의 자리에서 본 목록. `alive` 는 **리스를 쥔 세션이**
        이 컴퓨터에서 실행 중인가 — 그 판정(_session_alive_here)은 바인딩 파일과
        수신 대기를 읽으므로 시험에서는 그 한 함수만 갈아 끼운다."""
        import contextlib
        real_facts = self.m.local_facts

        def facts(u=None):
            d = dict(real_facts(u))
            d["session"] = session
            return d

        with contextlib.ExitStack() as st:
            st.callback(setattr, self.m, "local_facts", real_facts)
            st.callback(setattr, self.m, "_session_alive_here",
                        self.m._session_alive_here)
            self.m.local_facts = facts
            self.m._session_alive_here = lambda sid: bool(alive)
            return {r["id"] for r in self.m.here_requests(
                platform="Linux", machine=machine, user=user)}

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

    # H7. 같은 컴퓨터의 다른 세션이 쥐고 있으면 오르지 않는다 (REQ-20260915-004-2n7g)
    #     실제 사고 2026-09-15: A 가 13:42 에 집은 요청을 13:58 에 같은 맥의 B 가
    #     이 줄을 보고 집어, 두 세션이 같은 파일을 고쳤다.
    def test_h7_live_session_on_this_machine_holds_it(self):
        rid = self.new("옆 세션이 쥔 것", status="in-progress")
        self.set_lease(rid, "testbox")          # 리스의 세션은 ssss1111
        self.assertNotIn(rid, self.here_as("dddd2222", alive=True))

    # H8. 쥔 세션 자신에게는 그대로 보인다 — 제 일이 목록에서 사라지면 안 된다
    def test_h8_the_holder_still_sees_its_own(self):
        rid = self.new("내 세션이 쥔 것", status="in-progress")
        self.set_lease(rid, "testbox")
        self.assertIn(rid, self.here_as("ssss1111", alive=True))

    # H9. 쥔 세션이 죽었으면 같은 담당자의 다른 세션에 다시 오른다(takeover-local)
    def test_h9_dead_holder_returns_to_the_same_user(self):
        rid = self.new("죽은 세션이 쥔 것", status="in-progress")
        self.set_lease(rid, "testbox")
        self.assertIn(rid, self.here_as("dddd2222", alive=False))

    # H10. 같은 컴퓨터라도 담당자가 다른 사람이면 오르지 않는다(busy-user)
    def test_h10_another_user_on_this_machine(self):
        rid = self.new("남이 쥔 것", status="in-progress")
        self.set_lease(rid, "testbox", user="somebody")
        self.assertNotIn(rid, self.here_as("dddd2222", alive=False))

    # H6. 회귀 — 리스가 없는 open 요청은 여전히 담당자의 아무 컴퓨터에나 오른다
    #     (REQ-20260910-009 ③ 가 이 한 줄 때문에 좁아지면 안 된다)
    def test_h6_unleased_open_request_still_shows_everywhere(self):
        rid = self.new("담당 없는 것")
        for machine in ("testbox", "otherbox", "winbox"):
            self.assertIn(rid, self.here(machine=machine), machine)


if __name__ == "__main__":
    unittest.main()
