"""다른 기계에서 해야 할 요청은 그 기계의 세션이 s9 next 로 먼저 본다 (REQ-20260906-080).

Remote Control 없이도 GitHub 동기화만으로 닿는 길: 요청에 needs_os 를 적어 두면 그 판의
세션이 기동 turn 의 s9 next 에서 「이 기계에서 해야 할 요청」으로 받는다.

실행: python3 tests/ needs_os
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class NeedsOs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9needs-")
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        cls.env.update({"S9_ROOT": cls.root, "S9_MACHINE": "testbox", "S9_USER": "tester"})
        cls.cli("init"); cls.cli("user", "add", "tester")
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader("s9_needs", importlib.machinery.SourceFileLoader("s9_needs", S9))
        cls.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True, env=cls.env,
                              stdin=subprocess.DEVNULL, timeout=30)

    def new(self, title, *extra):
        r = self.cli("new", "request", "--title", title, "--summary", "s", "--size", "S",
                     "--goal", "g", "--body", "b", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.split()[0]

    # N1. --needs-os 가 프론트매터와 catalog 에 남고 set 으로 바뀐다
    def test_n1_needs_os_is_stored_and_settable(self):
        rid = self.new("맥에서 잴 것", "--needs-os", "macOS")
        meta, _ = self.m.read_doc(self.m.locate(rid))
        self.assertEqual(meta["needs_os"], "macOS")
        row = next(r for r in self.m.load_catalog() if r["id"] == rid)
        self.assertEqual(row["needs_os"], "macOS")
        r = self.cli("set", rid, "--needs-os", "Windows")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.m.read_doc(self.m.locate(rid))[0]["needs_os"], "Windows")

    # N2. 판별 — Linux 요구는 WSL 도 만족, macOS 요구는 리눅스에서 안 보인다, 닫힌 것은 빠진다
    def test_n2_here_requests_filter_by_platform(self):
        a = self.new("맥 것", "--needs-os", "macOS")
        b = self.new("리눅스 것", "--needs-os", "Linux")
        c = self.new("판 무관")
        d = self.new("끝난 맥 것", "--needs-os", "macOS")
        self.cli("status", d, "in-progress", "--note", "x"); self.cli("status", d, "done", "--note", "goal 충족", "--force")
        ids = lambda rows: {r["id"] for r in rows}
        mine = {a, b, c, d}
        self.assertEqual(ids(self.m.here_requests("macOS")) & mine, {a})
        self.assertEqual(ids(self.m.here_requests("WSL")) & mine, {b})
        self.assertEqual(ids(self.m.here_requests("Linux")) & mine, {b})
        self.assertEqual(ids(self.m.here_requests("Windows")) & mine, set())

    # N3. s9 next 가 이 기계의 것을 먼저 보이고 --json 에 here 가 든다
    def test_n4_the_watcher_does_not_spawn_on_the_wrong_platform(self):
        """워처는 needs_os 가 이 판과 다른 요청의 작업자를 띄우지 않는다 (REQ-20260909-071,
        실측 2026-09-09 14:34: 맥용 검증 요청의 정체 후속 작업자가 WSL 에 떴다)."""
        rid = self.new("맥에서 볼 것", "--needs-os", "macOS")
        meta = self.m.read_doc(self.m.locate(rid))[0]
        real = subprocess.Popen

        def no_popen(*a, **kw):
            raise AssertionError("무인 워커를 실제로 띄웠다")
        subprocess.Popen = no_popen
        out = {}
        try:
            with mock.patch.object(self.m, "os_platform", return_value="WSL"):
                ok = self.m._spawn_worker(rid, meta, "p", "stalled", out=out)
        finally:
            subprocess.Popen = real
        self.assertFalse(ok)
        self.assertEqual(out.get("blocked"), "needs_os", out)
        self.assertIn("macOS", out.get("why", ""))
        # 판이 맞으면 이 검사는 지나간다(뒤의 다른 검사에 걸리더라도 needs_os 는 아니다)
        self.assertTrue(self.m.needs_os_matches("macOS", platform="macOS"))
        self.assertTrue(self.m.needs_os_matches("Linux", platform="WSL"))
        self.assertFalse(self.m.needs_os_matches("Windows", platform="WSL"))

    # M1. 담당 머신: 부르는 이름으로 적으면 머신값으로 풀려 문서·catalog 에 남고,
    #     머신값 그대로도 받고, 빈 값으로 지워진다 (REQ-20260910-016)
    def test_m1_needs_machine_is_resolved_stored_and_cleared(self):
        self.cli("peer", "set", "맥", "--machine", "macbox", "--os", "macOS")
        rid = self.new("담당 머신이 있는 것", "--needs-machine", "맥")
        self.assertEqual(self.m.read_doc(self.m.locate(rid))[0]["needs_machine"], "macbox")
        row = next(r for r in self.m.load_catalog() if r["id"] == rid)
        self.assertEqual(row["needs_machine"], "macbox")
        r = self.cli("set", rid, "--needs-machine", "testbox")   # 머신값 그대로도 받는다
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.m.read_doc(self.m.locate(rid))[0]["needs_machine"], "testbox")
        r = self.cli("set", rid, "--needs-machine", "")          # 지우기
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # 빈 값은 프론트매터에서 아예 빠진다 — 없는 것과 같은 뜻이다
        self.assertEqual(self.m.read_doc(self.m.locate(rid))[0].get("needs_machine", ""), "")

    # M2. 모르는 이름은 거절하고 아는 머신을 보여 준다 — 문서는 만들어지지 않는다
    def test_m2_unknown_machine_name_is_refused(self):
        before = {r["id"] for r in self.m.load_catalog()}
        r = self.cli("new", "request", "--title", "모르는 머신", "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b",
                     "--needs-machine", "없는머신")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("아는 머신", r.stdout + r.stderr)
        self.assertIn("testbox", r.stdout + r.stderr)
        self.assertEqual({r2["id"] for r2 in self.m.load_catalog()} - before, set())

    # M3. 집기: 머신과 담당자가 **둘 다** 맞을 때만 집는다
    def test_m3_here_requests_need_both_machine_and_user(self):
        self.cli("user", "add", "other")
        mine = self.new("내 머신 내 것", "--needs-machine", "testbox")
        theirs = self.new("내 머신 남의 것", "--needs-machine", "testbox", "--user", "other")
        far = self.new("다른 머신 내 것", "--needs-machine", "macbox")
        ids = lambda rows: {r["id"] for r in rows}
        all3 = {mine, theirs, far}
        got = ids(self.m.here_requests(platform="WSL", machine="testbox", user="tester"))
        self.assertEqual(got & all3, {mine})
        # 담당 머신이 꺼져 있어도 다른 머신은 영영 집지 않는다 (시한·폴백 없음)
        got = ids(self.m.here_requests(platform="macOS", machine="otherbox", user="tester"))
        self.assertEqual(got & all3, set())

    # M4. 둘 다 적혀 있으면 담당 머신이 이긴다
    def test_m4_needs_machine_beats_needs_os(self):
        a = self.new("판은 맞고 머신은 다르다", "--needs-machine", "macbox", "--needs-os", "Linux")
        b = self.new("판은 다르고 머신은 맞다", "--needs-machine", "testbox", "--needs-os", "macOS")
        ids = lambda rows: {r["id"] for r in rows}
        got = ids(self.m.here_requests(platform="WSL", machine="testbox", user="tester"))
        self.assertEqual(got & {a, b}, {b})

    # M5. 막기: 담당 머신이 아니면 어떤 경로로도 작업자를 띄우지 않는다
    def test_m5_no_worker_spawns_off_the_assigned_machine(self):
        rid = self.new("담당 머신에서만", "--needs-machine", "macbox")
        meta = self.m.read_doc(self.m.locate(rid))[0]
        real = subprocess.Popen

        def no_popen(*a, **kw):
            raise AssertionError("무인 워커를 실제로 띄웠다")
        subprocess.Popen = no_popen
        out = {}
        try:
            with mock.patch.object(self.m, "current_machine", return_value="testbox"):
                ok = self.m._spawn_worker(rid, meta, "p", "stalled", out=out)
        finally:
            subprocess.Popen = real
        self.assertFalse(ok)
        self.assertEqual(out.get("blocked"), "needs_machine", out)
        self.assertIn("macbox", out.get("why", ""))
        self.assertIn("testbox", out.get("why", ""))

    def test_n3_next_lists_requests_for_this_machine(self):
        rid = self.new("윈도우에서 잴 것", "--needs-os", "Windows")
        with mock.patch.object(self.m, "os_platform", lambda: "Windows"), \
                mock.patch.object(sys, "stdout", new_callable=io.StringIO) as out:
            self.m.cmd_next(type("A", (), {"user": None, "all": False, "json": False})())
        self.assertIn("이 기계(Windows)에서 해야 할 요청", out.getvalue())
        self.assertIn(rid, out.getvalue())
        with mock.patch.object(self.m, "os_platform", lambda: "Windows"), \
                mock.patch.object(sys, "stdout", new_callable=io.StringIO) as out:
            self.m.cmd_next(type("A", (), {"user": None, "all": False, "json": True})())
        d = json.loads(out.getvalue())
        self.assertIn(rid, [h["id"] for h in d["here"]])


if __name__ == "__main__":
    unittest.main()
