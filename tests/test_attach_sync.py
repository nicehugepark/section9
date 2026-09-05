"""동기화 모드는 스위치가 아니라 판정 (REQ-20260905-013).

두 번째 머신이 붙는 순간(같은 사람의 두 번째 OS 계정·머신 attach · origin 있음 ·
아직 표식 없음)이 곧 「여럿·바깥과 오간다」다 — attach 가 표식(.s9-sync, remote)을
세우고 한 줄로 알린다. clone 만 한 사람(머신 하나)에게는 어떤 git 쓰기도 없다.

실행: python3 tests/ attach_sync
"""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class AttachIsTheVerdict(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9att-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_USER": "alice",
                    "S9_MACHINE": "alpha"}
        self.env.pop("S9_SESSION", None)
        subprocess.run(["git", "init", "-q", self.root], check=True, timeout=30)
        self.s9("init"); self.s9("user", "add", "alice")

    def s9(self, *argv, **env):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env={**self.env, **env}, timeout=60, stdin=subprocess.DEVNULL)

    def marker(self):
        p = os.path.join(self.root, ".s9-sync")
        return open(p, encoding="utf-8").read() if os.path.exists(p) else ""

    def test_a1_first_machine_writes_nothing(self):
        """A1. 머신 하나·origin 있어도 attach 는 표식을 만들지 않는다 — clone 만 한 사람이다."""
        subprocess.run(["git", "-C", self.root, "remote", "add", "origin", "git@example:o/r.git"],
                       check=True, timeout=30)
        r = self.s9("user", "attach", "alice")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.marker(), "")

    def test_a2_second_machine_with_origin_turns_remote_on_and_says_so(self):
        """A2. 두 번째 머신 + origin → 표식 remote 가 서고 한 줄로 알린다."""
        subprocess.run(["git", "-C", self.root, "remote", "add", "origin", "git@example:o/r.git"],
                       check=True, timeout=30)
        self.s9("user", "attach", "alice")
        r = self.s9("user", "attach", "alice", S9_MACHINE="beta")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("remote", self.marker(), "두 번째 머신인데 동기화가 안 켜졌다")
        self.assertIn("바깥과 오간다", r.stdout, "켜졌다는 말이 없다")
        out = self.s9("sync", "--status").stdout
        self.assertIn("remote", out)

    def test_a3_no_origin_means_no_verdict(self):
        """A3. origin 이 없으면 두 번째 머신이어도 표식을 만들지 않는다 — 오갈 곳이 없다."""
        self.s9("user", "attach", "alice")
        r = self.s9("user", "attach", "alice", S9_MACHINE="beta")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.marker(), "")


if __name__ == "__main__":
    unittest.main()
