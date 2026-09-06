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
