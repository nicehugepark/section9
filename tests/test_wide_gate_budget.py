"""넓게 닿는 파일의 **작은** 변경은 전체 스위트를 기다리지 않는다 (REQ-20260905-009).

실사고 2026-09-05: 라벨 한 줄(REQ-20260905-006)에 러너·서버 33줄이 딸려
커밋 문이 전체 스위트를 요구했고, 그 실행이 멈춰 커밋이 한 시간 밀렸다.
문은 「모르는 것을 막는다」이지 「매번 전체를 돌린다」가 아니다.

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
        "s9_guard_budget", importlib.machinery.SourceFileLoader("s9_guard_budget", GUARD))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class SmallWideChangeDoesNotWait(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_g1_small_and_fresh_passes(self):
        """G1. 작은 변경 + 신선한 전체 초록 = 세우지 않는다."""
        self.assertTrue(self.m.wide_small_and_fresh(["bin/s9.py"], lines=33, age=3600))

    def test_g2_big_change_still_blocks(self):
        """G2. 큰 변경은 종전대로 — 상한을 넘으면 신선해도 막는다."""
        self.assertFalse(self.m.wide_small_and_fresh(
            ["bin/s9.py"], lines=self.m.WIDE_SMALL_LINES + 1, age=60))

    def test_g3_stale_green_still_blocks(self):
        """G3. 전체 초록이 낡았으면(상한 초과) 작은 변경도 막는다 · 없으면 막는다."""
        self.assertFalse(self.m.wide_small_and_fresh(
            ["bin/s9.py"], lines=1, age=self.m.WIDE_FRESH_SEC + 1))
        self.assertFalse(self.m.wide_small_and_fresh(["bin/s9.py"], lines=1, age=None))

    def test_g4_unknown_size_blocks(self):
        """G4. 변경 크기를 못 재면 막는다 — 모르는 것은 통과가 아니다."""
        self.assertFalse(self.m.wide_small_and_fresh(["bin/s9.py"], lines=10**6, age=1))


if __name__ == "__main__":
    unittest.main()
