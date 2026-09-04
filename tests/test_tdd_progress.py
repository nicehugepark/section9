"""TDD 카운터 라벨 dedup 테스트 (REQ-20260824-001).

_tdd_progress: 개정된 체크리스트가 세대별로 쌓여도 시나리오 라벨(S1/V8/M3...)로
병합해 현행 커버리지를 센다. 실행: python3 tests/test_tdd_progress.py
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader(
    "s9tdd", importlib.machinery.SourceFileLoader(
        "s9tdd", os.path.join(HERE, "..", "bin", "s9")))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestTddProgress(unittest.TestCase):
    # T1. V-라벨 두 세대 → 라벨 병합, 완료 우선
    def test_test_tdd_progress(self):
        """TestTddProgress 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("t1_v_label_generations_merge"):
                body = "\n".join([
                    "- [x] V1. 구세대 문구 A",
                    "- [x] V2. 구세대 문구 B",
                    "- [ ] V3. 구세대 문구 C",
                    "- [x] V1. 신세대 문구 A'",
                    "- [x] V2. 신세대 문구 B'",
                    "- [ ] V3. 신세대 문구 C'",
                ])
                self.assertEqual(mod._tdd_progress(body), {"passed": 2, "total": 3})

            # T2. 회귀: S-라벨 병합 불변
        with self.subTest("t2_s_label_regression"):
                body = "- [ ] S1. 미완\n- [x] S1. 완료판\n- [x] S2. 완료"
                self.assertEqual(mod._tdd_progress(body), {"passed": 2, "total": 2})

            # T3. 라벨 없으면 줄 텍스트 dedup
        with self.subTest("t3_unlabeled_by_text"):
                body = "- [ ] 라벨 없는 항목 하나\n- [x] 라벨 없는 항목 하나\n- [ ] 다른 항목"
                self.assertEqual(mod._tdd_progress(body), {"passed": 1, "total": 2})

            # T4. 'REQ-20260823-001' 같은 접두는 라벨로 오인하지 않는다 (텍스트 dedup 유지)
        with self.subTest("t4_req_id_not_label"):
                body = "- [ ] REQ-20260823-001 의존 대기\n- [x] REQ-20260823-002 의존 해소"
                self.assertEqual(mod._tdd_progress(body), {"passed": 1, "total": 2})

            # T5. tdd 노트 섹션이 여러 세대면 마지막 섹션만 (REQ-20260824-010)
        with self.subTest("t5_last_tdd_section_only"):
            body = "\n".join([
                "## Notes", "",
                "### 2026-08-23T10:00:00+09:00 tdd (agent: a, by u)",
                "- [ ] G1. 구세대 하나", "- [ ] G2. 구세대 둘", "",
                "### 2026-08-23T11:00:00+09:00 response (by u)",
                "- [x] 응답 속 체크박스(카운트 제외 대상)", "",
                "### 2026-08-24T09:00:00+09:00 tdd (agent: b, by u)",
                "- [x] D1. 현행 하나", "- [x] D2. 현행 둘", "- [ ] D3. 현행 셋",
            ])
            self.assertEqual(mod._tdd_progress(body), {"passed": 2, "total": 3})

if __name__ == "__main__":
    unittest.main(verbosity=2)
