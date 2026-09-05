"""전체 스위트는 commit 뒤 배경에서 — 커밋 문은 붉음 라쳇으로 지킨다 (REQ-20260905-010).

실사고 2026-09-05: 라벨 한 줄에 러너 33줄이 딸려 문이 전체 스위트를 요구했고
그 실행이 멈춰 커밋이 한 시간 밀렸다. quality-assurance 실측: commit 전 동기
게이트는 하루 174분, commit 뒤 비동기는 5분 — 12~35배. 문은 막는 대신
**붉음을 기억한다**: 마지막 붉음이 마지막 초록보다 새로우면 code 커밋을 세운다.

실행: python3 tests/ wide_gate_budget
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_guard_ratchet", importlib.machinery.SourceFileLoader("s9_guard_ratchet", GUARD))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class RedRatchet(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.red = {"at": 1000.0, "files": ["test_code_read_gate.py"]}

    def test_t1_red_newer_than_green_blocks(self):
        """T1. 마지막 붉음이 마지막 초록보다 새로우면 막는다 — 초록 없음도 막는다."""
        blocked, files = self.m.red_ratchet(["bin/s9.py"], red=self.red,
                                            green_age=600, now=1500, fix_env="")
        self.assertTrue(blocked)                 # 초록 at=900 < 붉음 1000
        self.assertEqual(files, ["test_code_read_gate.py"])
        self.assertTrue(self.m.red_ratchet(["bin/s9.py"], red=self.red,
                                           green_age=None, now=1500, fix_env="")[0])

    def test_t2_green_after_red_passes(self):
        """T2. 붉음 뒤에 초록이 있었으면 막지 않는다 · 기록이 없어도 막지 않는다."""
        self.assertFalse(self.m.red_ratchet(["bin/s9.py"], red=self.red,
                                            green_age=100, now=1500, fix_env="")[0])
        self.assertFalse(self.m.red_ratchet(["bin/s9.py"], red=None,
                                            green_age=None, now=1500, fix_env="")[0])

    def test_t3_the_fix_and_the_declared_exception_pass(self):
        """T3. 붉은 파일의 시험을 담은 커밋(고치러 온 것)과 S9_FIX_RED 는 지나간다."""
        self.assertFalse(self.m.red_ratchet(
            ["bin/s9.py", "tests/test_code_read_gate.py"], red=self.red,
            green_age=600, now=1500, fix_env="")[0])
        self.assertFalse(self.m.red_ratchet(["bin/s9.py"], red=self.red,
                                            green_age=600, now=1500,
                                            fix_env="REQ-20260905-007-62x6")[0])


if __name__ == "__main__":
    unittest.main()
