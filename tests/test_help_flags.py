"""--help 는 아무것도 실행하지 않는다 (REQ-20260906-041).

README 를 쓰다가 `python3 tests/ --help` 가 원격 전체 실행을 띄우고, `bin/s9-install --help` 가
설치를 한 번 더 실행했다(2026-09-06). 사용법만 찍고 0 으로 끝나야 한다.

실행: python3 tests/ help_flags
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


class HelpFlags(unittest.TestCase):
    def test_h1_runner_help_runs_nothing(self):
        """H1. 러너 --help: 사용법 출력·종료 0·임시 루트도 원격 실행도 없다."""
        env = {**os.environ, "S9_TESTS_NESTED": "1", "S9_TEST_REMOTE": "nonexistent-key"}
        r = subprocess.run([sys.executable, HERE, "--help"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("usage: python3 tests/", r.stdout)
        self.assertNotIn("[원격]", r.stdout + r.stderr)

    def test_h2_install_help_installs_nothing(self):
        """H2. s9-install --help: 사용법 출력·종료 0·설치 표식이 생기지 않는다."""
        root = tempfile.mkdtemp(prefix="s9help-")
        home = tempfile.mkdtemp(prefix="s9help-home-")
        env = {**os.environ, "S9_ROOT": root, "CLAUDE_CONFIG_DIR": home}
        r = subprocess.run([os.path.join(REPO, "bin", "s9-install"), "--help"], capture_output=True, text=True,
                           env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("usage: s9-install", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(home, ".section9-install.json")), "설치가 실행됐다")
        self.assertFalse(os.path.exists(os.path.join(root, "state", "installed_at")), "설치가 실행됐다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
