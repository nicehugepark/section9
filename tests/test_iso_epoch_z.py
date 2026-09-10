"""시각 파싱은 `Z` 접미를 3.9 에서도 푼다 (REQ-20260910-012-2n7g).

Claude 의 대화 기록(jsonl)은 시각을 `2026-09-07T00:01:00.000Z` 로 적는다.
`datetime.fromisoformat` 이 `Z` 를 받는 것은 3.11 부터라, 맥 기본 파이썬(3.9)
에서는 모든 응답 시각이 0.0 으로 떨어져 토큰 창 합산(transcript_usage)이
통째로 None 이었다 — 맥에서 닫힌 요청에는 토큰이 하나도 안 적혔다.

실행: python3 tests/ iso_epoch_z
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_iso", importlib.machinery.SourceFileLoader("s9_iso", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class IsoEpochZ(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_z1_z_equals_utc_offset(self):
        """핵심 — `Z` 는 `+00:00` 과 같은 시각이다(밀리초가 있어도)."""
        f = self.m.iso_epoch
        self.assertEqual(f("2026-09-07T00:01:00.000Z"), f("2026-09-07T00:01:00+00:00"))
        self.assertEqual(f("2026-09-07T00:01:00Z"), f("2026-09-07T00:01:00+00:00"))
        self.assertGreater(f("2026-09-07T00:01:00.000Z"), 0.0, "Z 시각이 0.0 으로 떨어졌다")

    def test_z2_offset_form_is_untouched(self):
        """경계 — 오프셋 표기는 종전 그대로."""
        self.assertEqual(self.m.iso_epoch("2026-09-07T09:00:00+09:00"), 1788739200.0)

    def test_z3_garbage_is_still_zero(self):
        """경계 — 못 푸는 값은 여전히 0.0(아주 오래된 것)."""
        for v in ("", None, "어제", "2026-13-45T00:00:00Z"):
            self.assertEqual(self.m.iso_epoch(v), 0.0, v)


if __name__ == "__main__":
    unittest.main(verbosity=2)
