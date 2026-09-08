"""이름 없는 실패는 막지 않는다 (REQ-20260908-058-62x6).

실제 사고 2026-09-08. 전체 테스트 실패 기록(`state/tests-last-red.json`)의
`files` 가 `["(원격 머신)"]` 이었다 — 실패한 파일 이름이 아니다. 그러면 두 가지가
한꺼번에 막힌다.

1. **못 고친다.** 커밋 차단이 말하는 「그 파일을 고쳐 담으라」를 따를 수 없다.
2. **못 지운다.** 원격 러너는 미커밋 변경이 있는 동안 통과 기록을 남기지 않으므로,
   손으로 `python3 tests/` 를 돌려도 기록이 안 지워진다. 지우려면 커밋해야 하는데
   커밋은 그 기록이 막는다.

남는 길이 `S9_FIX_RED` 뿐이었고 리드가 하루에 세 번 썼다 — **매번 쓰는 비상구는
검사가 아니다.**

그리고 그날의 실패 자체가 실체가 없었다: 원격 러너에게 **아직 커밋되지 않은 새
시험 파일**을 목록으로 넘겨 「고르지 못한 패턴」으로 rc=1 이 났다. 원격은 커밋
꾸러미를 받아 도니 그 파일이 없는 것이 당연하다.

고정하는 계약 둘.
1. 이름을 담지 못한 실패 기록은 **커밋을 막지 않는다** (기록은 남고, 다음 전체
   실행이 덮는다).
2. 그 커밋에 없는 파일은 **원격에 보내지 않는다** — 「고르지 못한 패턴」이 아니라
   「아직 커밋되지 않았다」로 말한다.

실행: python3 tests/ red_named
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUARD = os.path.join(ROOT, "bin", "s9-guard")


def _guard():
    spec = importlib.util.spec_from_loader(
        "s9_guard_red", importlib.machinery.SourceFileLoader("s9_guard_red", GUARD))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class UnnamedRedDoesNotBlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _guard()

    def setUp(self):
        self._fix = os.environ.pop("S9_FIX_RED", None)

    def tearDown(self):
        if self._fix is not None:
            os.environ["S9_FIX_RED"] = self._fix

    def _red(self, files):
        return {"at": 2000.0, "files": files}

    # ── 이름을 담았나 ────────────────────────────────────────
    def test_a_placeholder_is_not_a_name(self):
        self.assertTrue(self.g._red_unnamed(self._red(["(원격 머신)"])),
                        "자리표시를 파일 이름으로 읽었다 — 2026-09-08 그 자리")

    def test_an_empty_list_is_not_a_name(self):
        self.assertTrue(self.g._red_unnamed(self._red([])))
        self.assertTrue(self.g._red_unnamed(self._red(["", "  "])))

    def test_a_real_file_is_a_name(self):
        self.assertFalse(self.g._red_unnamed(self._red(["test_x.py"])))

    def test_one_real_name_among_placeholders_counts(self):
        self.assertFalse(self.g._red_unnamed(
            self._red(["(원격 머신)", "test_x.py"])),
            "고칠 수 있는 이름이 하나라도 있으면 그것으로 막아야 한다")

    # ── 막나 ────────────────────────────────────────────────
    def test_it_does_not_block_when_it_cannot_name_a_file(self):
        stop, files = self.g.red_ratchet(["bin/s9.py"], red=self._red(["(원격 머신)"]),
                                         green_age=None, now=3000.0, fix_env="")
        self.assertFalse(stop, "이름 없는 기록이 커밋을 막았다 — 따를 수 있는 "
                               "지시가 없는 차단은 비상구만 쓰게 만든다")
        self.assertEqual(files, [])

    def test_it_still_blocks_when_it_can(self):
        stop, files = self.g.red_ratchet(["bin/s9.py"], red=self._red(["test_x.py"]),
                                         green_age=None, now=3000.0, fix_env="")
        self.assertTrue(stop, "이름이 있는데 안 막았다")
        self.assertEqual(files, ["test_x.py"])

    def test_staging_the_failing_test_still_passes(self):
        stop, _ = self.g.red_ratchet(["tests/test_x.py"], red=self._red(["test_x.py"]),
                                     green_age=None, now=3000.0, fix_env="")
        self.assertFalse(stop, "고치러 온 커밋을 막았다 (기존 계약)")

    def test_a_pass_after_the_failure_still_clears_it(self):
        stop, _ = self.g.red_ratchet([], red=self._red(["test_x.py"]),
                                     green_age=500.0, now=3000.0, fix_env="")
        self.assertFalse(stop, "실패 뒤의 통과를 못 알아본다 (기존 계약)")


class UncommittedFilesAreNotSent(unittest.TestCase):
    """그 커밋에 없는 파일은 원격에 보내지 않는다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9red-")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "tests"))
        def git(*a):
            return subprocess.run(["git", *a], cwd=self.repo, capture_output=True,
                                  text=True)
        git("init", "-q", "-b", "main")
        git("config", "user.name", "t")
        git("config", "user.email", "t@t")
        with open(os.path.join(self.repo, "tests", "test_old.py"), "w") as f:
            f.write("# 담긴 것\n")
        git("add", "-A")
        git("commit", "-qm", "init")
        self.sha = git("rev-parse", "HEAD").stdout.strip()
        # 아직 담기지 않은 파일
        with open(os.path.join(self.repo, "tests", "test_new.py"), "w") as f:
            f.write("# 아직 안 담긴 것\n")
        sys.path.insert(0, HERE)
        import remote_run
        self.rr = remote_run
        self._repo_prev = remote_run.REPO
        remote_run.REPO = self.repo

    def tearDown(self):
        self.rr.REPO = self._repo_prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_it_keeps_what_the_commit_has(self):
        keep, missing = self.rr._split_uncommitted(self.sha, ["test_old.py"])
        self.assertEqual(keep, ["test_old.py"])
        self.assertEqual(missing, [])

    def test_it_holds_back_what_the_commit_lacks(self):
        keep, missing = self.rr._split_uncommitted(
            self.sha, ["test_old.py", "test_new.py"])
        self.assertEqual(keep, ["test_old.py"])
        self.assertEqual(missing, ["test_new.py"],
                         "아직 커밋되지 않은 파일을 원격에 보냈다 — 원격에는 "
                         "그 파일이 없으니 「고르지 못한 패턴」으로 진다")

    def test_flags_pass_through(self):
        keep, missing = self.rr._split_uncommitted(self.sha, ["--jobs", "16"])
        self.assertEqual(keep, ["--jobs", "16"])
        self.assertEqual(missing, [])

    def test_without_a_sha_nothing_is_held_back(self):
        keep, missing = self.rr._split_uncommitted("", ["test_new.py"])
        self.assertEqual(keep, ["test_new.py"])
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
