"""넓게 닿는 파일이 담긴 커밋은 전체 green 기록을 묻는다 (REQ-20260903-012).

실사고 2026-09-03. `bin/s9` 한 줄(REQ-20260902-017 `_local_binding_glob` —
바인딩을 이 머신 것만 보게 한 것)이 **커밋에 담기지 않은 시험 18건**을
깨뜨렸다. 커밋 게이트(`staged_tests_gate`)는 담긴 시험과 스모크 12파일만
보는데, 깨진 여덟 파일은 그 열둘과 하나도 겹치지 않았다 — 게이트는 초록을
보고 통과시켰고 커밋은 붉은 채로 들어갔다.

고치는 방향은 「매 커밋에 전체를 돌린다」가 아니다(분 단위라 규율이 먼저
죽는다). **돌리지 않고 묻는다**: 지금 이 나무 지문으로 전체가 초록이었던
기록이 있나. 있으면 비용 0으로 지나가고, 없을 때만 막는다.

실행: python3 tests/ wide_gate
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
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")
RUNNER = os.path.join(HERE, "__main__.py")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class WideListIsOneList(unittest.TestCase):
    """W1 — 두 목록이 갈리면 문이 엉뚱한 파일을 지킨다."""

    def test_w1_guard_mirrors_the_runner(self):
        guard = _load("s9guard_w", GUARD)
        runner = _load("s9runner_w", RUNNER)
        self.assertEqual(tuple(guard.WIDE), tuple(runner.COMMON),
                         "가드의 WIDE 와 러너의 COMMON 이 갈렸다 — 한쪽만 "
                         "고치면 문이 지키는 파일과 러너가 전체로 물러나는 "
                         "파일이 달라진다")


class TheGateAsks(unittest.TestCase):
    """W2~W5 — 묻는 자리의 갈래. 스위트는 한 번도 돌지 않는다."""

    def setUp(self):
        self.guard = _load("s9guard_g", GUARD)

    def _run(self, staged, rc=0, boom=False):
        """게이트를 한 번 돌리고 (SystemExit 코드 또는 None, stderr, 물었나)."""
        calls = []

        def fake(argv, **kw):
            calls.append(argv)
            if boom:
                raise OSError("no python")
            return subprocess.CompletedProcess(argv, rc, "", "")

        err = io.StringIO()
        code = None
        with mock.patch.object(self.guard.subprocess, "run", fake), \
                mock.patch.object(sys, "stderr", err):
            try:
                self.guard.wide_change_gate(staged)
            except SystemExit as e:
                code = e.code
        return code, err.getvalue(), bool(calls)

    # W2. 좁은 커밋에는 아무것도 묻지 않는다 — 문이 길을 막지 않는다.
    def test_w2_narrow_commit_is_not_asked(self):
        code, _err, asked = self._run(["web/app/card.js", "docs/guide.md"])
        self.assertIsNone(code)
        self.assertFalse(asked, "넓지 않은 커밋에까지 기록을 묻는다")

    # W3. 넓은 파일 + 기록 없음 = 막고, 돌릴 명령을 그대로 보인다.
    def test_w3_wide_without_a_record_is_refused(self):
        code, err, asked = self._run(["bin/s9", "web/app/card.js"], rc=1)
        self.assertTrue(asked, "묻지도 않고 지나갔다")
        self.assertEqual(code, 1)
        self.assertIn("bin/s9", err, "무엇이 걸렸는지 안 말한다")
        self.assertIn("python3 tests/", err,
                      "막기만 하고 무엇을 하면 되는지 안 알려 준다")

    # W4. 넓은 파일 + 기록 있음 = 그냥 지나간다 (비용 0).
    def test_w4_wide_with_a_record_passes(self):
        code, _err, asked = self._run(["bin/s9"], rc=0)
        self.assertTrue(asked)
        self.assertIsNone(code, "초록 기록이 있는데도 막았다")

    # W5. 문이 고장 나도 커밋을 막지 않는다 — 막으면 그날로 문이 뽑힌다.
    def test_w5_a_broken_gate_never_blocks(self):
        code, _err, _asked = self._run(["bin/s9"], boom=True)
        self.assertIsNone(code, "게이트 고장이 커밋을 막았다")

    # W5b. 경로 구분자가 역슬래시여도 같은 파일이다 (윈도우).
    def test_w5b_backslash_paths_count(self):
        code, _err, asked = self._run(["bin\\s9"], rc=1)
        self.assertTrue(asked, "윈도우 경로로 오면 넓은 파일을 못 알아본다")
        self.assertEqual(code, 1)


class TheAnswerIsARecord(unittest.TestCase):
    """W6~W8 — `--is-green` 은 기록 하나를 볼 뿐이다."""

    def setUp(self):
        self.runner = _load("s9runner_a", RUNNER)
        self.tmp = tempfile.mkdtemp(prefix="s9wide-")
        self.runner.REUSE_DIR = self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, fp):
        pats = self.runner.patterns([])
        with open(self.runner._reuse_path(pats), "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fp, "at": 0, "n": len(pats)}, f)

    # W6. 기록이 없으면 「모른다」 — 초록으로 세지 않는다.
    def test_w6_no_record_is_not_green(self):
        with mock.patch.object(self.runner, "tree_fingerprint",
                               lambda *_a: "abc"):
            self.assertFalse(self.runner.full_suite_green())

    # W7. 같은 지문의 기록이 있으면 초록이다.
    def test_w7_matching_record_is_green(self):
        self._write("abc")
        with mock.patch.object(self.runner, "tree_fingerprint",
                               lambda *_a: "abc"):
            self.assertTrue(self.runner.full_suite_green())

    # W7b. 나무가 바뀌면(지문이 다르면) 그 기록은 이 나무의 것이 아니다.
    def test_w7b_a_changed_tree_drops_the_record(self):
        self._write("abc")
        with mock.patch.object(self.runner, "tree_fingerprint",
                               lambda *_a: "zzz"):
            self.assertFalse(self.runner.full_suite_green())

    # W8. 지문을 못 재면(git 밖 등) 모른다고 답한다 — 모르는 것은 초록이 아니다.
    def test_w8_no_fingerprint_is_not_green(self):
        self._write("abc")
        with mock.patch.object(self.runner, "tree_fingerprint",
                               lambda *_a: None):
            self.assertFalse(self.runner.full_suite_green())

    # W9. 묻는 갈래는 시험을 한 건도 돌지 않는다 — 임시 루트조차 안 만든다.
    def test_w9_the_question_runs_no_tests(self):
        with mock.patch.object(sys, "argv", ["tests", "--is-green"]), \
                mock.patch.object(self.runner, "full_suite_green",
                                  lambda *_a: True), \
                mock.patch.object(self.runner.tmproot, "make_run_root",
                                  mock.Mock(side_effect=AssertionError(
                                      "묻기만 하는데 실행 자리를 만들었다"))):
            self.assertEqual(self.runner.main(), 0)


if __name__ == "__main__":
    unittest.main()
