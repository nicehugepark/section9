"""원격 전체 테스트의 집계 — 「돌지 않은 파일이 있으면 통과라고 하지 않는다」.

실제 사고 2026-09-07 (REQ-20260907-047): `state/tests-async/cd166ccb.log` 가
「전체 통과 · 356파일 97초」로 끝났는데, 같은 커밋 cd166cc 의
`tests/test_wake_handle.py` 는 실제로는 실패하는 상태였고 로그에 그 파일은
한 줄도 없었다. 원인은 둘이다.

① 준비 단계의 실패가 실행을 멈추지 않았다. 원격에서 도는 한 줄이
   `cd $D && git fetch … && … ;` 였는데, `set -e` 는 AND-OR 리스트의 **마지막이
   아닌** 명령의 실패를 건너뛴다. 커밋 받기가 실패해도 셸은 다음 줄로 가서,
   원격에 이미 펴져 있던 **옛 커밋**으로 시험을 돌고 종료 코드 0 을 냈다.
   (REQ-20260907-049: 그 받기가 왜 늘 실패했는지는 원격의 키가 다른 저장소의
   deploy key 였기 때문이고, 이제 커밋은 GitHub 을 거치지 않고 ssh 통로로 오는
   bundle 로 곧장 온다 — 아래 시험은 그 통로에서 같은 계약을 잰다.)
② 무엇이 실제로 돌았는지 아무도 세지 않았다. 원격에는 파일 이름을 패턴으로
   넘기는데, 원격 tree에 없는 이름은 조용히 빠진다. 그런데 병렬 갈래에는
   「고르지 못한 패턴」검사가 없었고, 이 머신이 보고한 「356파일」은 원격이 돈
   수가 아니라 **이 머신의 목록 길이**였다.

실행: python3 tests/test_remote_accounting.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import remote_run  # noqa: E402

SHA = "cd166cc" + "0" * 33
FAKE_GIT = """#!/bin/sh
case "$1" in
  fetch)
    if [ -n "$FAKE_FETCH_FAIL" ]; then
      echo "fatal: '$2' does not look like a v2 bundle file" >&2
      exit 128
    fi
    exit 0 ;;
  rev-parse) echo "${FAKE_HEAD}" ; exit 0 ;;
  *) exit 0 ;;
esac
"""
# 시험 명령까지 갔는지만 잡는 가짜 — `tests/` 인자가 보이면 표식 파일에 한 줄.
FAKE_PY = """#!/bin/sh
for a in "$@"; do
  if [ "$a" = "tests/" ]; then echo ran >> "$FAKE_MARK"; fi
done
exit 0
"""


class RemoteScriptStopsOnPrepFailure(unittest.TestCase):
    """준비(fetch·펴기)가 실패하면 시험까지 가지 않는다 — cd166cc 재현."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9remote-")
        cls.bin = os.path.join(cls.tmp, "bin")
        os.makedirs(os.path.join(cls.tmp, "clone", ".git"))
        os.makedirs(cls.bin)
        for name, body in (("git", FAKE_GIT), ("python3", FAKE_PY)):
            path = os.path.join(cls.bin, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            os.chmod(path, 0o755)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _run(self, **env_extra):
        mark = os.path.join(self.tmp, "mark-%s" % len(os.listdir(self.tmp)))
        env = dict(os.environ)
        env["PATH"] = self.bin + os.pathsep + env["PATH"]
        env["FAKE_MARK"] = mark
        env["FAKE_HEAD"] = SHA
        env.update(env_extra)
        script = remote_run.remote_script(
            SHA, os.path.join(self.tmp, "clone"), 16, ["test_a.py"])
        p = subprocess.run(["sh", "-c", script], env=env, capture_output=True,
                           text=True, timeout=60, input="fake bundle bytes")
        return p, os.path.exists(mark)

    def test_receiving_the_commit_fails_and_never_reaches_the_tests(self):
        """R1. 커밋을 못 받으면 시험이 아예 시작되지 않고 종료 코드가 남는다."""
        p, ran = self._run(FAKE_FETCH_FAIL="1")
        self.assertFalse(ran, "커밋을 못 받았는데 옛 tree로 시험을 돌았다 "
                              "— cd166cc 가 「전체 통과」라고 말한 그 경로다")
        self.assertNotEqual(p.returncode, 0, "준비 실패가 종료 코드 0 으로 나왔다")
        self.assertEqual(p.returncode, 93, "받기 실패는 93 으로 구분된다")

    def test_checked_out_commit_is_verified(self):
        """R2. 편 커밋이 요청한 커밋이 아니면 시험까지 가지 않는다."""
        p, ran = self._run(FAKE_HEAD="deadbee" + "0" * 33)
        self.assertFalse(ran, "요청과 다른 커밋으로 시험을 돌았다")
        self.assertEqual(p.returncode, 96)
        self.assertIn("편 커밋이 다르다", p.stderr)

    def test_the_commit_never_travels_through_github(self):
        """R3b. 커밋 전달에 GitHub 이 끼지 않는다 — 원격은 표준 입력으로 받는다."""
        script = remote_run.remote_script(SHA, "/tmp/x", 16, ["test_a.py"])
        self.assertNotIn("github", script.lower())
        self.assertNotIn("origin", script)
        self.assertIn("cat > ", script)

    def test_healthy_preparation_reaches_the_tests(self):
        """R3. 대조군 — 준비가 정상이면 시험 명령까지 간다."""
        p, ran = self._run()
        self.assertTrue(ran, "준비가 정상인데 시험이 시작되지 않았다")
        self.assertEqual(p.returncode, 0)


class RunRemoteCountsWhatActuallyRan(unittest.TestCase):
    """요청한 파일 수와 원격이 센 수가 다르면 통과가 아니다."""

    def _run_remote(self, files, ran_mark, rc=0):
        """`_ssh` 만 가짜로 갈아 끼워 run_remote 의 판정만 잰다."""
        calls = {}

        def fake_ssh(key, cmd, stdin=None, stream=True, timeout=None):
            if ran_mark is not None:
                remote_run.LAST_RAN = ran_mark
            return subprocess.CompletedProcess([], rc)

        def fake_git(*args):
            # `-C <repo>` 가 앞에 붙는 호출이 있어 동사를 찾아 가른다.
            out = ""
            if "bundle" in args:
                with open(args[2], "wb") as f:   # bundle create <경로> …
                    f.write(b"fake")
            elif "rev-parse" in args:
                out = SHA
            return subprocess.CompletedProcess([], 0, out, "")

        real_ssh, real_git = remote_run._ssh, remote_run._git
        remote_run._ssh, remote_run._git = fake_ssh, fake_git
        try:
            calls["rc"] = remote_run.run_remote("k", files, jobs=4)
        finally:
            remote_run._ssh, remote_run._git = real_ssh, real_git
        return calls["rc"]

    def test_missing_file_is_not_a_pass(self):
        """R4. 요청 3개 · 원격이 센 것 2개 — 통과라고 말하지 않는다."""
        rc = self._run_remote(["a.py", "b.py", "c.py"], ran_mark=2)
        self.assertNotEqual(rc, 0, "한 파일이 빠졌는데 통과로 나왔다 "
                                   "— cd166cc 가 test_wake_handle.py 를 놓친 자리다")

    def test_absent_mark_is_not_a_pass(self):
        """R5. 몇 개를 셌는지 표식이 아예 없으면 통과를 증명하지 못한다."""
        rc = self._run_remote(["a.py", "b.py"], ran_mark=None)
        self.assertNotEqual(rc, 0)

    def test_full_count_is_a_pass(self):
        """R6. 대조군 — 요청 수와 센 수가 같고 원격이 0 이면 통과다."""
        rc = self._run_remote(["a.py", "b.py"], ran_mark=2)
        self.assertEqual(rc, 0)

    def test_remote_failure_stays_a_failure(self):
        """R7. 원격이 실패를 냈으면 수가 맞아도 실패다."""
        rc = self._run_remote(["a.py", "b.py"], ran_mark=2, rc=1)
        self.assertEqual(rc, 1)


class ParallelRunRejectsUnmatchedPattern(unittest.TestCase):
    """병렬 갈래에도 「고르지 못한 패턴」검사가 있다 — 원격은 언제나 이 갈래다."""

    def test_unmatched_pattern_fails_the_run(self):
        env = dict(os.environ)
        env["S9_TESTS_NESTED"] = ""
        env.pop("S9_TESTS_NESTED", None)
        p = subprocess.run(
            [sys.executable, HERE, "--local", "--no-reuse", "--jobs", "2",
             "test_jobfile.py", "test_this_file_does_not_exist_zz.py"],
            capture_output=True, text=True, timeout=180, env=env,
            stdin=subprocess.DEVNULL)
        self.assertNotEqual(p.returncode, 0,
                            "없는 파일을 패턴으로 줬는데 실행이 0 을 냈다")
        self.assertIn("고르지 못한 패턴", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
