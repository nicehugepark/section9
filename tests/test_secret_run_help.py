"""`s9 secret run --help` 는 usage 를 내고 traceback 없이 비-0 으로 끝난다 (REQ-20260906-094).

REMAINDER 인자가 `--help` 를 명령으로 쓸어 담아 subprocess 가 '--help' 라는 파일을
찾다 FileNotFoundError 를 내던 결함의 회귀 시험. 도움말 요청은 실행이 아니다."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S9 = os.path.join(ROOT, "bin", "s9")


def run(*args):
    return subprocess.run([sys.executable, S9, "secret", "run", *args],
                          capture_output=True, encoding="utf-8", errors="replace",
                          cwd=ROOT, timeout=60)


class SecretRunHelp(unittest.TestCase):
    def test_help_flag_prints_usage_without_traceback(self):
        for flag in ("--help", "-h"):
            r = run(flag)
            self.assertNotEqual(r.returncode, 0, flag)
            self.assertIn("usage: s9 secret run", r.stderr + r.stdout, flag)
            self.assertNotIn("Traceback", r.stderr + r.stdout, flag)

    def test_no_args_prints_usage(self):
        r = run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage: s9 secret run", r.stderr + r.stdout)

    def test_plain_command_still_runs(self):
        r = run("--", "echo", "hi")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "hi")


if __name__ == "__main__":
    unittest.main()
