"""pre-commit 이 담긴(index 의) 파이썬 소스를 컴파일한다 (REQ-20260907-004).

작업 트리가 아니라 index 의 본을 봐야 한다 — hunk 를 갈라 담은 commit 이 작업
트리는 멀쩡한 채 HEAD 만 깨뜨린 사고(fc3011a, DOC-20260907-001)의 회귀 시험."""
import importlib.machinery
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "bin", "s9-guard")


def load_guard():
    loader = importlib.machinery.SourceFileLoader("s9guard_t", GUARD)
    spec = importlib.util.spec_from_loader("s9guard_t", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class StagedCompileGate(unittest.TestCase):
    def setUp(self):
        self.g = load_guard()

    def test_broken_source_is_named_with_line(self):
        err = self.g.staged_source_error("bin/x.py", "def f(:\n    pass\n")
        self.assertIsNotNone(err)
        self.assertTrue(err.startswith("bin/x.py:1:"), err)

    def test_good_source_passes(self):
        self.assertIsNone(self.g.staged_source_error("bin/x.py", "def f():\n    return 1\n"))

    def test_python_script_without_py_suffix_is_checked(self):
        self.assertTrue(self.g._is_python_source("bin/s9", "#!/usr/bin/env python3\nx = 1\n"))
        self.assertFalse(self.g._is_python_source("bin/s9.cmd", "@echo off\n"))

    def test_gate_runs_first_in_pre_commit(self):
        with open(GUARD, encoding="utf-8") as f:
            src = f.read()
        i = src.index("def _pre_commit_gates")
        body = src[i:]
        self.assertLess(body.index("staged_compile_gate(staged)"), body.index("concurrent_gate(staged)"))


if __name__ == "__main__":
    unittest.main()
