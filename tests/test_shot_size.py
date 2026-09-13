"""s9 shot --size 는 768x1024 와 768,1024 를 모두 받는다 (REQ-20260913-005-2n7g).

맥 검증 중 발견 2026-09-13: browser-verify 스킬의 본보기 `--size 768x1024` 를 그대로
치면 Playwright 러너가 int 변환에 실패해 파이썬 추적 정보를 그대로 냈다 — 받는 쪽은
쉼표꼴만 알았다. x 꼴이 브라우저 도구의 관례라 문서를 고치는 대신 받는 쪽을 넓혔다.

실행: python3 tests/ shot_size
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
SRC = open(S9 + ".py", encoding="utf-8").read()


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_shotsize", importlib.machinery.SourceFileLoader("s9_shotsize", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ShotSize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_z1_both_forms_normalize_to_comma(self):
        """정상 — x·X·쉼표 꼴이 모두 쉼표꼴 하나로 선다."""
        for raw in ("768x1024", "768X1024", "768,1024", " 768 x 1024 "):
            self.assertEqual(self.m._shot_size(raw), "768,1024", raw)

    def test_z2_bad_size_is_one_line_exit_2(self):
        """실패 — 알 수 없는 꼴은 추적 정보가 아니라 사실 한 줄과 exit 2."""
        for raw in ("768", "axb", "0x10", "10x", ""):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                self.m._shot_size(raw)
            self.assertEqual(cm.exception.code, 2, raw)
            self.assertNotIn("Traceback", err.getvalue())
            self.assertIn("--size", err.getvalue())

    def test_z3_cmd_shot_normalizes_before_default_compare(self):
        """회귀 — cmd_shot 이 기본값 비교·엔진 갈래보다 먼저 정규화한다."""
        i = SRC.index("def cmd_shot(")
        body = SRC[i:i + 4000]
        norm = body.index("args.size = _shot_size(args.size)")
        self.assertLess(norm, body.index("args.size == SHOT_SIZE_DEFAULT"))
        self.assertLess(norm, body.index("_shot_webkit(url, args.size"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
