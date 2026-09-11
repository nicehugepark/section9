"""요청은 세운 컴퓨터가 맡는다 (REQ-20260911-004-2n7g, 주인 결정 2026-09-11 10:16).

담당 컴퓨터가 비어 있으면 「노는 컴퓨터가 집는다」 규칙이 돌아, 맥에서 세운 요청을
리눅스의 워처가 13초 만에 가져갔다 — 세운 세션이 막 착수하려던 일이다. 기본값은
세운 컴퓨터, 바꾸는 길은 대시보드의 「담당 컴퓨터 바꾸기」와 사람의 프롬프트 지시,
어느 컴퓨터여도 되는 일만 `--any-machine`.

실행: python3 tests/ new_request_machine
"""
import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
PROTOCOL = os.path.join(HERE, "..", "harness", "common", "PROTOCOL.md")


class NewRequestMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9nrm-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init"); cls.cli("user", "add", "tester")

    @classmethod
    def cli(cls, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True, env=cls.env,
                           timeout=30, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    def _new(self, *extra):
        out = self.cli("new", "request", "--title", "담당 기본값", "--summary", "s",
                       "--goal", "g", "--body", "b", *extra)
        rid = re.search(r"REQ-\d{8}-\d{3}-[0-9a-z]+", out).group(0)
        meta = self.cli("show", rid, "--meta")
        m = re.search(r"^needs_machine: (.*)$", meta, re.M)
        return rid, (m.group(1).strip() if m else "")

    def test_m1_default_is_the_creating_machine(self):
        """핵심 — 아무 말 없이 세운 요청의 담당은 세운 컴퓨터다."""
        _rid, nm = self._new()
        self.assertEqual(nm, "testbox", "담당이 비어 다른 컴퓨터의 워처가 집어 간다")

    def test_m2_any_machine_leaves_it_open(self):
        """경계 — 어느 컴퓨터여도 되는 일은 --any-machine 으로 비운다."""
        _rid, nm = self._new("--any-machine")
        self.assertIn(nm, ("", "''", '""'), nm)

    def test_m3_explicit_machine_wins(self):
        """회귀 — 사람이 지시한 담당은 그대로다."""
        _rid, nm = self._new("--needs-machine", "testbox")
        self.assertEqual(nm, "testbox")

    def test_m4_the_rule_is_in_the_protocol(self):
        """재발 방지 — 규약이 주인 결정을 적고 있다."""
        src = open(PROTOCOL, encoding="utf-8").read()
        self.assertIn("요청은 세운 컴퓨터가 맡는다", src)
        self.assertIn("--any-machine", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
