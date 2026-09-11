"""컴퓨터 하나에 묶인 일감을 세고, 컴퓨터째 옮긴다 (REQ-20260910-013-t8rc).

`s9 next` 는 「이 컴퓨터에서 할 일」만 냈다 — 「저 컴퓨터에 묶인 일」을 세는
자리가 없어, 컴퓨터 하나가 빠질 때 needs_machine 과 lease 를 vault 전체에
grep 해 손으로 표를 만들어야 했다. 이 시험은 그 두 자리(`s9 handoff --of`,
`s9 handoff --from ... --to ...`)를 잰다.

가장 중요한 한 줄은 M5 다: **신선한 점유는 옮기면서도 풀지 않는다.** 저쪽이
지금 그 문서를 만지고 있다는 뜻이라, 여기서 풀면 두 컴퓨터가 같은 문서를 쓴다.

실행: python3 tests/ machine_handoff
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


class MachineHandoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9handoff-")
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        cls.env.update({"S9_ROOT": cls.root, "S9_MACHINE": "oldbox",
                        "S9_USER": "tester"})
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls.cli("peer", "set", "새것", "--machine", "newbox", "--os", "Linux")
        # 안에서 부르는 함수들도 CLI 와 같은 자리에 서야 한다 — 이 자리의
        # 컴퓨터 이름이 없으면 아는 컴퓨터 표에 oldbox 가 없다
        os.environ.update({"S9_ROOT": cls.root, "S9_MACHINE": "oldbox",
                           "S9_USER": "tester"})
        spec = importlib.util.spec_from_loader(
            "s9_handoff",
            importlib.machinery.SourceFileLoader("s9_handoff", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        for k in ("S9_ROOT", "S9_MACHINE", "S9_USER"):
            os.environ.pop(k, None)
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=cls.env, stdin=subprocess.DEVNULL, timeout=60)

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
        """그 문서를 <machine> 이 <ago_sec> 초 전부터 쥔 것으로."""
        path = self.m.locate(rid)
        meta, body = self.m.read_doc(path)
        ts = (datetime.datetime.now().astimezone()
              - datetime.timedelta(seconds=ago_sec)).isoformat(timespec="seconds")
        meta["lease"] = {"user": user, "machine": machine, "session": "ssss1111",
                         "since": ts, "renewed": ts}
        self.m.write_doc(path, meta, body)
        self.m.rebuild_index(quiet=True)

    def bound(self, machine):
        return {r["id"] for r in self.m.machine_bound_requests(machine)}

    def needs_machine(self, rid):
        meta, _body = self.m.read_doc(self.m.locate(rid))
        return str(meta.get("needs_machine") or "")

    # M1. 담당 컴퓨터로 지정된 미완 요청이 그 컴퓨터의 표에 오른다
    def test_m1_needs_machine_is_counted(self):
        rid = self.new("저 컴퓨터의 일", "--needs-machine", "oldbox")
        r = self.cli("handoff", "--of", "oldbox")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(rid, r.stdout)
        self.assertIn("담당 컴퓨터로 지정", r.stdout)

    # M2. 부르는 이름으로 물어도 같은 표가 나온다 — hostname 을 외울 이유가 없다
    def test_m2_call_name_resolves(self):
        rid = self.new("새 컴퓨터의 일", "--needs-machine", "newbox")
        r = self.cli("handoff", "--of", "새것")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(rid, r.stdout)

    # M3. 담당이 안 적혀 있어도 그 컴퓨터가 지금 쥐고 있으면 그 컴퓨터의 것이다
    def test_m3_fresh_lease_counts(self):
        rid = self.new("점유만 있는 일", status="in-progress")
        self.set_lease(rid, "oldbox")
        self.assertIn(rid, self.bound("oldbox"))
        # 만료되면 아무 컴퓨터의 것도 아니다
        self.set_lease(rid, "oldbox", ago_sec=self.m.DOC_LEASE_TTL + 60)
        self.assertNotIn(rid, self.bound("oldbox"))

    # M4. 옮기면 담당 컴퓨터가 바뀌고 History 에 한 줄이 남는다
    # M9(회귀). 옮긴 뒤 그 요청이 받는 컴퓨터의 목록(here_requests)에 오른다
    def test_m4_move_changes_owner_machine_and_leaves_a_line(self):
        rid = self.new("옮길 일", "--needs-machine", "oldbox")
        r = self.cli("handoff", "--from", "oldbox", "--to", "새것")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(rid, r.stdout)
        self.assertEqual(self.needs_machine(rid), "newbox")
        _meta, body = self.m.read_doc(self.m.locate(rid))
        self.assertIn("needs_machine: oldbox -> newbox", body)
        self.assertIn("via handoff", body)
        here = {x["id"] for x in self.m.here_requests(platform="Linux",
                                                      machine="newbox",
                                                      user="tester")}
        self.assertIn(rid, here)

    # M5. 만료된 점유는 정리하고, 신선한 점유는 그대로 두고 보고만 한다 —
    #     저쪽이 지금 만지는 문서를 여기서 풀면 두 컴퓨터가 같은 문서를 쓴다
    def test_m5_stale_lease_released_fresh_lease_kept(self):
        old = self.new("자국만 남은 일", "--needs-machine", "oldbox",
                       status="in-progress")
        self.set_lease(old, "oldbox", ago_sec=self.m.DOC_LEASE_TTL + 60)
        live = self.new("지금 하는 일", "--needs-machine", "oldbox",
                        status="in-progress")
        self.set_lease(live, "oldbox")
        res = self.m.machine_handoff("oldbox", "newbox", actor="tester")
        self.assertIn(old, res["released"])
        self.assertIn(live, res["held"])
        self.assertEqual({}, self.m.doc_lease(
            self.m.read_doc(self.m.locate(old))[0]))
        self.assertEqual("oldbox", self.m.doc_lease(
            self.m.read_doc(self.m.locate(live))[0]).get("machine"))
        # 담당은 둘 다 옮겨진다 — 점유는 시한부라 저쪽이 멈추면 저절로 풀린다
        self.assertEqual(self.needs_machine(live), "newbox")

    # M6. 끝난 요청은 세지도 옮기지도 않는다
    def test_m6_finished_requests_are_not_bound(self):
        rid = self.new("끝난 일", "--needs-machine", "oldbox")
        self.cli("status", rid, "in-progress", "--note", "착수")
        r = self.cli("status", rid, "done", "--note", "goal 충족", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(rid, self.bound("oldbox"))
        self.m.machine_handoff("oldbox", "newbox", actor="tester")
        self.assertEqual(self.needs_machine(rid), "oldbox")

    # M7. 모르는 컴퓨터 이름은 문서를 건드리지 않고 거절한다 —
    #     오타 하나가 영영 아무 컴퓨터에도 닿지 않는 요청을 만든다
    def test_m7_unknown_machine_is_refused(self):
        rid = self.new("남는 일", "--needs-machine", "oldbox")
        r = self.cli("handoff", "--of", "없는것")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        r = self.cli("handoff", "--from", "oldbox", "--to", "없는것")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.needs_machine(rid), "oldbox")

    # M8. 한쪽만 준 이관은 거절한다 — 어디로 보낼지 모르는 이관은 이관이 아니다
    def test_m8_from_without_to_is_refused(self):
        r = self.cli("handoff", "--from", "oldbox")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("--to", r.stdout + r.stderr)

    # M9b(회귀). 인자 없는 `s9 handoff` 는 세션 축 그대로다
    def test_m9_bare_handoff_still_reports_the_session_axis(self):
        r = self.cli("handoff")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
