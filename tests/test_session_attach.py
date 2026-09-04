"""세션 이중 접속 경고 테스트 (REQ-20260824-031).

같은 sid에 살아있는 기존 attach가 있으면 resume 시작 컨텍스트에 경고를 주입한다.
격리: S9_ROOT=mktemp. 실행: python3 tests/test_session_attach.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-session")
S9 = os.path.join(HERE, "..", "bin", "s9")


def run_hook(env, payload):
    r = subprocess.run([HOOK, "start"], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, timeout=20)
    return r.stdout


class TestDualAttach(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9att-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_PORT": "1"}  # ensure_serve가 실서버를 띄우지 않게 무효 포트…
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env, timeout=15)

    # A1. 최초 접속: 경고 없음 + attach_pid 기록
    def test_test_dual_attach(self):
        """TestDualAttach 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_first_attach_no_warn"):
                out = run_hook(self.env, {"session_id": "dualtest1", "source": "startup"})
                self.assertNotIn("이중 접속", out)
                b = json.loads(subprocess.run(
                    [S9, "bind"], capture_output=True, text=True,
                    env={**self.env, "S9_SESSION": "dualtest"}, timeout=10).stdout)
                self.assertTrue(b.get("attach_pid"))

            # A2. 기존 attach가 살아있는 상태의 resume → 경고 주입
        with self.subTest("a2_live_prev_attach_warns"):
                env = {**self.env, "S9_SESSION": "dualtes2"}
                # 살아있는 다른 pid(1 = init, 항상 생존)를 기존 attach로 기록
                # (테스트 프로세스 pid는 훅의 부모라 self로 간주됨)
                subprocess.run([S9, "bind", "attach_pid", "1"],
                               capture_output=True, env=env, timeout=10)
                out = run_hook(self.env, {"session_id": "dualtes2x", "source": "resume"})
                self.assertIn("이미 활성", out)
                self.assertIn("이중 접속", out)
                self.assertIn("digest로 승계", out)

            # A3. 기존 attach가 죽어 있으면 경고 없음 (정상 재개)
        with self.subTest("a3_dead_prev_attach_silent"):
            env = {**self.env, "S9_SESSION": "dualtes3"}
            subprocess.run([S9, "bind", "attach_pid", "999999999"],
                           capture_output=True, env=env, timeout=10)
            out = run_hook(self.env, {"session_id": "dualtes3x", "source": "resume"})
            self.assertNotIn("이중 접속", out)

if __name__ == "__main__":
    unittest.main(verbosity=2)
