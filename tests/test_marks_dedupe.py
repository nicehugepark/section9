"""겹친 자국을 유실로 알리지 않는다 (REQ-20260914-001-2n7g).

실제 사고 2026-09-14 12:39: 동기화 병합이 같은 노트를 두 번 붙였다가 뒤에 하나로
접었는데, 벌수로 맞대던 유실 감사가 「기록 2건이 사라졌다」고 알렸다 — 사라진 것은
없고 겹친 것이 걷힌 것이다. 거짓 경보를 내는 탐지기는 꺼진 탐지기다.
글자로 맞대지도 않는다 — 다시쓰기는 유실이 아니다(REQ-20260901-004 의 첫 교훈).

실행: python3 tests/ marks_dedupe
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_md", importlib.machinery.SourceFileLoader("s9_md", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


N1 = "### 2026-09-14T10:30:38+09:00 response (agent: lead:x, by hong)\n\n본문\n"
N2 = "### 2026-09-14T10:49:31+09:00 response (agent: sub:designer, by hong)\n\n본문\n"
N1B = "### 2026-09-14T10:30:38+09:00 response (agent: sub:designer, by hong)\n\n다른 노트\n"


class MarksDedupe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def _lost(self, snap, live):
        m = self.m
        return m._marks_lost(m._append_only_marks(snap), m._append_only_marks(live))

    def test_d1_duplicated_note_folded_to_one_is_not_a_loss(self):
        """핵심 — 뜬 것에 같은 노트가 두 번, 문서에 한 번이면 유실이 아니다."""
        self.assertEqual(self._lost(N1 + N1 + N2 + N2, N1 + N2), [])

    def test_d2_a_real_loss_is_still_found(self):
        """회귀 — 문서에서 노트 하나가 통째로 사라진 것은 여전히 잡는다."""
        gone = self._lost(N1 + N2, N1)
        self.assertEqual(len(gone), 1)
        self.assertIn("10:49:31", gone[0])

    def test_d3_two_distinct_notes_in_one_second_count_separately(self):
        """경계 — 같은 시각에 글자가 다른 두 노트 중 하나가 사라지면 잡는다."""
        gone = self._lost(N1 + N1B, N1)
        self.assertEqual(len(gone), 1)

    def test_d4_a_rewrite_is_not_a_loss(self):
        """경계 — 같은 시각의 줄이 글자만 바뀐 것(이름 바꾸기 등)은 유실이 아니다."""
        self.assertEqual(self._lost(N1, N1.replace("by hong", "by nicehugepark")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
