"""기록되는 시각이 진짜인가 (REQ-20260826-038-62x6).

옆 파일 `test_response_stamp.py`(REQ-024)는 **규약이 지시되는가**를 본다 —
훅이 매 턴 규칙과 실제 시각을 함께 주는가. 이 파일은 그 다음 질문이다:
**기록에 남는 시각이 진짜인가.** 지시가 아무리 정확해도, 모델이 받은 값은
프롬프트가 도착한 시각이고 답을 마친 시각이 아니다.

사용자 지적: "llm이 추정하는 시각을 출력하는게 아니라 반드시 정확한 시간이
출력되어야 한다."

모델이 쓰는 시각은 언제나 **프롬프트 훅이 주입한 값의 복사본**이다. 턴이 길면
그만큼 과거를 가리키고(도구를 스무 번 부르면 몇 분이 지난다), 주입이 없으면
지어낼 수밖에 없다 — 모델은 자기가 말을 마치는 시각을 알 수 없다.

그러니 정확성을 모델에게 맡기지 않는다. 턴이 끝나는 순간을 아는 것은 Stop
훅이고, 그 훅이 기록되는 텍스트의 도장을 실제 시각으로 바로잡는다. 이름(역할)은
모델이 쓴 것을 그대로 둔다 — 그건 모델만 아는 사실이다.

실행: python3 tests/ stamp_accuracy
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-response")
# 시간대 라벨은 now_str 에 실려 온다 (REQ-20260903-013) — 훅이 `KST` 를
# 상수로 들고 있던 자리를 없앴다.
NOW = "2026-08-26 23:30:00 KST"


def _load():
    spec = importlib.util.spec_from_loader(
        "s9resp", importlib.machinery.SourceFileLoader("s9resp", HOOK))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ResponseStamp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_response_stamp(self):
        """ResponseStamp 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("r1_stale_stamp_is_corrected"):
            text = "`[2026-08-26 23:20:04 KST - lead]`\n\n작업했다."
            fixed, drift = self.m.correct_stamp(text, NOW)
            self.assertTrue(fixed.startswith(f"`[{NOW} - lead]`"), fixed)
            self.assertEqual(drift, 596)
            self.assertIn("작업했다.", fixed)
        with self.subTest("r2_role_name_is_preserved"):
            text = "`[2026-08-26 23:20:04 KST - designer]`\n\n표를 그렸다."
            fixed, _ = self.m.correct_stamp(text, NOW)
            self.assertIn("- designer]`", fixed)
            self.assertNotIn("- lead]`", fixed)
        with self.subTest("r3_missing_stamp_is_added"):
            fixed, drift = self.m.correct_stamp("도장 없이 시작하는 응답", NOW)
            self.assertTrue(fixed.startswith(f"`[{NOW} - lead]`"), fixed)
            self.assertIsNone(drift)
            self.assertIn("도장 없이 시작하는 응답", fixed)
        with self.subTest("r4_accurate_stamp_survives_unchanged"):
            text = f"`[{NOW} - lead]`\n\n본문"
            fixed, drift = self.m.correct_stamp(text, NOW)
            self.assertEqual(fixed, text)
            self.assertEqual(drift, 0)
        with self.subTest("r5_only_the_head_is_a_stamp"):
            text = "설명한다. 형식은 `[2026-08-26 23:20:04 KST - lead]` 이다."
            fixed, drift = self.m.correct_stamp(text, NOW)
            self.assertIn("`[2026-08-26 23:20:04 KST - lead]` 이다.", fixed)
            self.assertIsNone(drift)          # 머리에 없었으니 새로 붙는다
            self.assertTrue(fixed.startswith(f"`[{NOW} - lead]`"), fixed)

if __name__ == "__main__":
    unittest.main()
