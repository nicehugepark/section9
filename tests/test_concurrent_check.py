"""커밋을 걸지 않고 동시 작업 검사를 미리 본다 (REQ-20260907-070).

`concurrent_gate` 는 커밋할 때만 답한다. 그래서 리드가 그 검사가 막는지
보려고 `git commit -m probe` 를 두 번 걸었고, 막지 않은 회차의 probe 는
그대로 커밋됐다(REQ-20260907-062 의 재발). 커밋을 걸어야만 답이 나오는
검사는 사람을 진짜 커밋으로 밀어낸다.

`concurrent_report` 는 같은 것을 보되 아무것도 막지 않고 커밋도 만들지 않는다.
표(token)는 여전히 **목록과 함께만** 나온다 — 목록을 보지 않고 표만 얻는
길을 새로 열면 이 검사가 받는 증거가 다시 주장으로 돌아간다
(DOC-20260907-004).

실행: python3 tests/ concurrent_check
"""
import importlib.machinery
import importlib.util
import io
import os
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")

TMP = tempfile.mkdtemp(prefix="s9-ccheck-")
_prev = os.environ.get("S9_ROOT")
os.environ["S9_ROOT"] = TMP
try:
    spec = importlib.util.spec_from_loader(
        "s9_guard_cc", importlib.machinery.SourceFileLoader("s9_guard_cc", GUARD))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
finally:
    if _prev is None:
        os.environ.pop("S9_ROOT", None)
    else:
        os.environ["S9_ROOT"] = _prev

WORKERS = ("REQ-x (백그라운드 작업자 pid 1, 1분째)",)


class TheQuery(unittest.TestCase):
    """`concurrent_report` 를 실제로 부른다 — 소스 글자를 대조하지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-ccheck-root-")
        self.f = "tests/남의것.py"
        self.p = os.path.join(self.root, self.f)
        os.makedirs(os.path.dirname(self.p), exist_ok=True)
        open(self.p, "w").close()      # 방금 만든 파일 = 방금 바뀐 파일

    def _report(self, workers=WORKERS, paths=None):
        buf = io.StringIO()
        with mock.patch.object(g, "ROOT", self.root), \
                mock.patch.object(g, "live_workers", lambda: list(workers)):
            rc = g.concurrent_report(paths if paths is not None else [self.f], out=buf)
        return rc, buf.getvalue()

    def test_it_shows_the_files_and_the_token(self):
        rc, text = self._report()
        self.assertEqual(rc, 0)
        self.assertIn(self.f, text, "무엇이 걸리는지를 안 보여 준다")
        self.assertIn(g.concurrent_token([(self.f, 0)]), text, "표가 없다")

    def test_the_token_it_shows_actually_passes_the_check(self):
        """조회가 준 표로 검사가 통과해야 한다 — 아니면 조회는 거짓말이다."""
        _, text = self._report()
        tok = g.concurrent_token([(self.f, 0)])
        self.assertIn(tok, text)
        with mock.patch.object(g, "ROOT", self.root), \
                mock.patch.object(g, "live_workers", lambda: list(WORKERS)), \
                mock.patch.dict(os.environ, {g.OVERRIDE: tok}, clear=False):
            self.assertIsNone(g.concurrent_gate([self.f]))

    def test_no_worker_no_token(self):
        rc, text = self._report(workers=())
        self.assertEqual(rc, 0)
        self.assertNotIn(g.concurrent_token([(self.f, 0)]), text,
                         "막지도 않을 자리에서 표를 나눠 주면 표가 증거가 아니게 된다")

    def test_no_fresh_file_no_token(self):
        old = time.time() - (g.FRESH_SEC + 60)
        os.utime(self.p, (old, old))
        rc, text = self._report()
        self.assertEqual(rc, 0)
        self.assertNotIn(g.concurrent_token([(self.f, 0)]), text)

    def test_the_token_never_comes_without_the_list(self):
        """표만 단독으로 얻는 길이 없다 (DOC-20260907-004)."""
        _, text = self._report()
        tok = g.concurrent_token([(self.f, 0)])
        self.assertLess(text.index(self.f), text.index(tok),
                        "표가 목록보다 먼저 나오면 목록을 안 읽고 복사한다")

    def test_it_never_refuses(self):
        """조회는 검사가 아니다 — 어느 경우에도 0 으로 끝난다."""
        for workers in ((), WORKERS):
            with self.subTest(workers=bool(workers)):
                self.assertEqual(self._report(workers=workers)[0], 0)

    def test_it_does_not_raise_systemexit(self):
        try:
            self._report()
        except SystemExit:                       # pragma: no cover
            self.fail("조회가 커밋을 막았다")


class TheEntryPoint(unittest.TestCase):
    """`s9-guard --concurrent` 가 커밋 경로를 타지 않는다."""

    def test_it_reports_and_skips_the_commit_gates(self):
        mark = mock.Mock()
        gates = mock.Mock()
        report = mock.Mock(return_value=0)
        with mock.patch.object(g, "sys") as fake_sys, \
                mock.patch.object(g, "commit_mark_set", mark), \
                mock.patch.object(g, "_pre_commit_gates", gates), \
                mock.patch.object(g, "concurrent_report", report), \
                mock.patch.object(g, "staged_now", lambda: ["a.py"]):
            fake_sys.argv = ["s9-guard", "--concurrent"]
            rc = g.main()
        self.assertEqual(rc, 0)
        report.assert_called_once_with(["a.py"])
        mark.assert_not_called()
        gates.assert_not_called()

    def test_extra_paths_are_used_instead_of_the_index(self):
        report = mock.Mock(return_value=0)
        with mock.patch.object(g, "sys") as fake_sys, \
                mock.patch.object(g, "commit_mark_set", mock.Mock()), \
                mock.patch.object(g, "_pre_commit_gates", mock.Mock()), \
                mock.patch.object(g, "concurrent_report", report), \
                mock.patch.object(g, "staged_now", lambda: ["담긴것.py"]):
            fake_sys.argv = ["s9-guard", "--concurrent", "골라준것.py"]
            g.main()
        report.assert_called_once_with(["골라준것.py"])


class TheCommitPathIsUnchanged(unittest.TestCase):
    """조회를 붙이면서 커밋 검사의 차례가 바뀌면 안 된다 (REQ-20260904-003)."""

    def test_the_gates_still_run_in_order(self):
        body = open(GUARD, encoding="utf-8").read()
        i = body.index("def _pre_commit_gates")
        rest = body[i:]
        self.assertLess(rest.index("staged_compile_gate(staged)"),
                        rest.index("concurrent_gate(staged)"))
        self.assertLess(rest.index("concurrent_gate(staged)"),
                        rest.index("wide_change_verdict(staged)"))


if __name__ == "__main__":
    unittest.main()
