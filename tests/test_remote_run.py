"""전체 스위트를 원격에서 (REQ-20260905-012) — 값은 안 보고, 큰 것은 안 보낸다.

실행: python3 tests/ remote_run
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import remote_run  # noqa: E402


class RemoteRun(unittest.TestCase):
    def test_k1_key_comes_from_argv_then_env_then_file(self):
        """K1. `--remote KEY` > S9_TEST_REMOTE > state/test-remote — 없으면 None."""
        old_file, old_env = remote_run.REMOTE_KEY_FILE, os.environ.pop("S9_TEST_REMOTE", None)
        d = tempfile.mkdtemp(prefix="s9rr-")
        remote_run.REMOTE_KEY_FILE = os.path.join(d, "test-remote")
        try:
            self.assertEqual(remote_run.remote_key(["--remote", "jade"]), "jade")
            self.assertIsNone(remote_run.remote_key([]))
            os.environ["S9_TEST_REMOTE"] = "opal"
            self.assertEqual(remote_run.remote_key([]), "opal")
            self.assertEqual(remote_run.remote_key(["--remote", "jade"]), "jade")
            os.environ.pop("S9_TEST_REMOTE", None)
            remote_run.remember("ruby")
            self.assertEqual(remote_run.remote_key([]), "ruby")
        finally:
            remote_run.REMOTE_KEY_FILE = old_file
            if old_env is not None:
                os.environ["S9_TEST_REMOTE"] = old_env

    def test_k2_the_remote_is_a_clone_that_runs_the_pushed_commit(self):
        """K2. 원격 한 줄: clone(없으면) → refs/ci/<sha7> fetch → 그 커밋 → index → 시험."""
        sha = "0123456789abcdef0123456789abcdef01234567"
        line = remote_run.remote_script("git@github.com:o/r.git", sha, "~/section9-ci/x",
                                        16, ["test_a.py"], user="nicehugepark")
        for part in ("git clone -q", "refs/ci/0123456", "-q -f " + sha,
                     "index rebuild", "user attach 'nicehugepark'", "--jobs 16", "'test_a.py'"):
            self.assertIn(part, line)
        self.assertNotIn("S9_USER=", line, "정체를 환경변수로 강제하면 제 사용자를 만드는 시험이 붉는다")
        for part in ():
            self.assertIn(part, line)
        self.assertNotIn("tar", line, "GitHub 이 축이다 — 보내는 것이 있으면 안 된다")

    def test_k4_full_means_no_pattern_and_jobs_is_not_a_pattern(self):
        """K4. 전체 = 패턴 없음. `--jobs 16` 의 16 과 `--remote jade` 의 jade 는 패턴이 아니다."""
        f = remote_run.is_full_invocation
        self.assertTrue(f([]))
        self.assertTrue(f(["--jobs", "16"]))
        self.assertTrue(f(["--jobs", "16", "--no-reuse", "--remote", "jade"]))
        self.assertFalse(f(["--jobs", "16", "jobs_shard"]))
        self.assertFalse(f(["--smoke", "--jobs", "4"]))
        self.assertFalse(f(["--changed"]))

    def test_k3_the_secret_is_only_ever_substituted(self):
        """K3. 원격 명령은 `s9 secret run` 의 치환({{secret:KEY}})으로만 선다 — 값을 읽는 코드가 없다."""
        src = open(remote_run.__file__, encoding="utf-8").read()
        self.assertIn("{{secret:%s}}", src)
        self.assertNotIn('"secret", "get"', src)
        self.assertEqual(remote_run._sh_quote("a'b"), "'a'\"'\"'b'")


if __name__ == "__main__":
    unittest.main()
