"""커밋 검사가 담기지 않은 남의 초안에 막히지 않는다 (REQ-20260915-003-62x6).

실사고 2026-09-15. 한 working tree 에서 둘이 나눠 일하는 중, backend-developer 의
`s9 commit -- bin/s9.py tests/…` 가 pre-commit 에서 거부됐다. 실패한 시험은
`test_button_word` 이고 잡힌 자리는 `web/app/notice.js:189`·`web/css/notice.css:21`
— frontend-developer 가 아직 커밋하지 않은 작업 트리 파일이다. `s9 commit` 은 담는
것을 임시 index 로 갈라 놓았지만(REQ-20260913-022-62x6), 저장소의 파일을 모두 읽는
시험 다섯(button_word·no_metaphors·screen_lexicon·stdlib_only·dialog_safe)은
디스크를 본다. 그래서 담지도 않은 파일 때문에 commit 이 거부되고, 옆 사람이 그
낱말을 고칠 때까지 API 계약을 실물로 넘기지 못했다.

낮추는 자리는 좁다 — 실패 출력에서 저장소 경로를 읽을 수 있고, 그 경로가 **전부**
담기지 않은 작업 트리 파일일 때만 경고다. 하나라도 담긴 파일을 가리키면 종전대로 막는다.

실행: python3 tests/ gate_draft_paths
"""
import importlib.machinery
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")

GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_INDEX_VERSION",
                "GIT_QUARANTINE_PATH")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _clean_env():
    e = dict(os.environ)
    for k in GIT_ENV_VARS:
        e.pop(k, None)
    return e


def _git(*argv, cwd):
    return subprocess.run(["git", "-C", cwd, *argv], env=_clean_env(),
                          capture_output=True, text=True, timeout=30)


# 실제 사고의 출력 모양 — 러너는 실패한 시험을 **파일 이름만**으로 찍고,
# 시험은 걸린 자리를 `경로:줄:` 로 찍는다.
FAIL_TEXT = """실패한 샤드: test_button_word.py
FAIL: test_no_danchu_left (test_button_word.NoButtonWord.test_no_danchu_left)
AssertionError: Lists differ: ['web/app/notice.js:189: const label = …',
 'web/css/notice.css:21: /* 옛 낱말 */'] != []
"""


class ReadsThePaths(unittest.TestCase):
    """G1 — 실패 출력에서 저장소 경로를 읽는다."""

    def setUp(self):
        self.guard = _load("s9guard_dp1", GUARD)

    def test_g1_paths_with_line_numbers(self):
        self.assertEqual(self.guard.gate_failure_paths(FAIL_TEXT),
                         {"web/app/notice.js", "web/css/notice.css"})

    def test_g1b_runner_test_names_are_not_paths(self):
        got = self.guard.gate_failure_paths("실패한 샤드: test_button_word.py test_wake.py")
        self.assertEqual(got, set(), "러너가 찍는 시험 파일 이름을 경로로 셌다")

    def test_g1c_traceback_paths_count(self):
        got = self.guard.gate_failure_paths('  File "bin/s9.py", line 12, in main')
        self.assertEqual(got, {"bin/s9.py"})


class CountsTheDrafts(unittest.TestCase):
    """G7 — 담기지 않은 작업 트리 파일을 실제 저장소에서 센다."""

    def setUp(self):
        self.guard = _load("s9guard_dp2", GUARD)
        self.repo = tempfile.mkdtemp(prefix="s9draft-")
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        _git("init", "-q", cwd=self.repo)
        _git("config", "user.email", "t@t", cwd=self.repo)
        _git("config", "user.name", "t", cwd=self.repo)
        for name in ("staged.py", "theirs.js", "moved.css"):
            with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
                f.write("x\n")
        _git("add", "-A", cwd=self.repo)
        _git("commit", "-q", "-m", "first", "--no-verify", cwd=self.repo)

    def _write(self, name, text):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_g7_staged_out_drafts_in(self):
        self._write("staged.py", "mine\n")
        _git("add", "staged.py", cwd=self.repo)
        self._write("theirs.js", "theirs\n")            # 담기지 않은 수정
        self._write("new.css", "untracked\n")           # 아직 track 되지 않음
        _git("mv", "moved.css", "renamed.css", cwd=self.repo)   # 담긴 옮김
        with mock.patch.object(self.guard, "ROOT", self.repo):
            got = self.guard.others_draft_paths(["staged.py"])
        self.assertIn("theirs.js", got, "담기지 않은 수정을 못 셌다")
        self.assertIn("new.css", got, "untracked 파일을 못 셌다")
        self.assertNotIn("staged.py", got, "담은 파일을 남의 초안으로 셌다")
        self.assertNotIn("renamed.css", got, "담긴 옮김을 초안으로 셌다")
        self.assertNotIn("moved.css", got, "옮김의 옛 이름을 초안으로 셌다")

    def test_g7b_clean_tree_has_no_drafts(self):
        with mock.patch.object(self.guard, "ROOT", self.repo):
            self.assertEqual(self.guard.others_draft_paths([]), set())

    # G8 — 실사고 그대로: 실제 저장소 상태에 실제 실패 출력을 대 본다(흉내 없이).
    def test_g8_the_real_incident(self):
        os.makedirs(os.path.join(self.repo, "web", "app"))
        os.makedirs(os.path.join(self.repo, "bin"))
        self._write(os.path.join("web", "app", "notice.js"), "theirs\n")   # 남의 초안
        self._write(os.path.join("bin", "tool.py"), "mine\n")              # 내가 담는 것
        _git("add", "bin/tool.py", cwd=self.repo)
        text = ("FAIL: test_no_danchu_left (test_button_word.NoButtonWord)\n"
                "AssertionError: ['web/app/notice.js:189: …'] != []\n")
        err = io.StringIO()
        with mock.patch.object(self.guard, "ROOT", self.repo):
            self.assertTrue(self.guard.draft_only_failure(["bin/tool.py"], text, err),
                            "담기지 않은 web/ 초안의 실패를 낮추지 않았다")
            self.assertFalse(
                self.guard.draft_only_failure(["bin/tool.py"], text + "bin/tool.py:3: …\n", err),
                "담은 파일의 실패까지 낮췄다")
        self.assertIn("web/app/notice.js", err.getvalue())


class TheGateDowngrades(unittest.TestCase):
    """G2~G6 — 검사의 갈래. 시험 스위트는 한 번도 돌지 않는다."""

    def setUp(self):
        self.guard = _load("s9guard_dp3", GUARD)
        self.root = tempfile.mkdtemp(prefix="s9gate-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _run(self, rc=1, text=FAIL_TEXT, drafts=("web/app/notice.js", "web/css/notice.css"),
             staged=("bin/s9.py",)):
        """검사를 한 번 돌리고 (SystemExit 코드 또는 None, stderr)."""
        def fake(argv, **kw):
            return subprocess.CompletedProcess(argv, rc, text, "")

        err = io.StringIO()
        code = None
        with mock.patch.object(self.guard.subprocess, "run", fake), \
                mock.patch.object(self.guard, "ROOT", self.root), \
                mock.patch.object(self.guard, "others_draft_paths",
                                  lambda _staged: set(drafts)), \
                mock.patch.object(sys, "stderr", err):
            try:
                self.guard.staged_tests_gate(list(staged))
            except SystemExit as e:
                code = e.code
        return code, err.getvalue()

    # G2. 실패한 자리가 전부 담기지 않은 파일이면 경고로 낮춘다.
    def test_g2_draft_only_failure_is_a_warning(self):
        code, err = self._run()
        self.assertIsNone(code, "담지도 않은 파일 때문에 커밋을 막았다")
        self.assertIn("담기지 않은", err, "왜 지나가는지 말하지 않았다")
        self.assertIn("web/app/notice.js", err, "어느 파일인지 말하지 않았다")

    # G3. 담긴 파일을 하나라도 가리키면 종전대로 막는다.
    def test_g3_a_staged_file_still_blocks(self):
        code, err = self._run(text=FAIL_TEXT + "FAIL: bin/s9.py:42: …\n")
        self.assertEqual(code, 1, "담은 파일의 실패까지 경고로 낮췄다")
        self.assertIn("커밋을 멈춥니다", err)

    # G4. 경로를 하나도 못 읽으면 막는다 — 보수적 기본값.
    def test_g4_unreadable_failure_blocks(self):
        code, _err = self._run(text="Segmentation fault\n")
        self.assertEqual(code, 1, "무엇이 실패했는지 모르는데 지나갔다")

    # G5. 담기지 않은 변경이 없으면 낮추지 않는다.
    def test_g5_clean_tree_blocks(self):
        code, _err = self._run(drafts=())
        self.assertEqual(code, 1, "작업 트리가 깨끗한데도 남 탓으로 지나갔다")

    # G6. 통과는 종전대로 조용하다.
    def test_g6_pass_is_silent(self):
        code, err = self._run(rc=0)
        self.assertIsNone(code)
        self.assertEqual(err, "", "통과했는데 무언가 찍었다")


if __name__ == "__main__":
    unittest.main()
