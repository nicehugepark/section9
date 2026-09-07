"""사람이 누른 손잡이는 한 곳에서만 갈린다 (REQ-20260907-038).

예전엔 `reason == "wake"` 라는 문자열 비교가 bin/s9.py 다섯 자리에 흩어져
있었다. 손잡이를 하나 더하면서 그중 하나를 빠뜨리면 그 손잡이는 워처의 자동
예산을 갉아먹고, 사람이 누른 것이 워처를 굶긴다 — tests/test_wake.py W4 가
붙잡았던 사고가 그것이다.

고정하는 계약 셋.
1. 판정은 `is_human_reason` 하나다. 손잡이를 더하는 사람이 고칠 자리는
   `HUMAN_REASONS` 한 줄이다.
2. 「답 찾기」(`answer`)도 사람 예산을 쓴다 — wake 와 같은 대접.
3. 모르는 reason 은 기계다 — 모를 때 사람 예산을 주면 예산이 새는 쪽이다.

실행: python3 tests/ human_reasons
"""
import ast
import importlib.machinery
import importlib.util
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
SRC = os.path.join(HERE, "..", "bin", "s9.py")

TMP = tempfile.mkdtemp(prefix="s9-humanreason-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_hr", importlib.machinery.SourceFileLoader("s9_mod_hr", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class Judgement(unittest.TestCase):
    def test_wake_is_human(self):
        self.assertTrue(mod.is_human_reason("wake"))

    def test_answer_is_human(self):
        # 「답 찾기」 손잡이 (REQ-20260907-041)
        self.assertTrue(mod.is_human_reason("answer"))

    def test_watcher_is_not_human(self):
        self.assertFalse(mod.is_human_reason("watcher"))

    def test_unknown_reason_is_machine(self):
        # 모를 때 사람 예산을 주면 예산이 새는 쪽이다 — 좁은 쪽이 안전하다
        for r in ("", None, "resume", "rework"):
            self.assertFalse(mod.is_human_reason(r), r)


class SingleSourceOfTruth(unittest.TestCase):
    def test_no_scattered_string_comparison(self):
        """흩어진 `reason == "wake"` 비교가 남아 있으면 안 된다.

        글자 찾기가 아니라 **구문 나무**로 본다 — 주석과 docstring 에는 이
        결함의 경위가 남아 있어야 하고, 그것까지 잡으면 시험이 기록을 지우라고
        시키는 셈이 된다. 잡을 것은 실제로 도는 비교뿐이다.
        """
        tree = ast.parse(open(SRC, encoding="utf-8").read())
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not (isinstance(node.left, ast.Name) and node.left.id == "reason"):
                continue
            for op, cmp in zip(node.ops, node.comparators):
                if (isinstance(op, (ast.Eq, ast.NotEq))
                        and isinstance(cmp, ast.Constant) and cmp.value == "wake"):
                    bad.append(node.lineno)
        self.assertEqual(bad, [], f"is_human_reason 을 쓰지 않은 줄: {bad}")

    def test_budget_keys_follow_the_judgement(self):
        """예산 칸 선택이 판정을 따른다 — wake 와 answer 가 같은 칸을 쓴다."""
        src = open(SRC, encoding="utf-8").read()
        # 예산 칸을 고르는 자리는 전부 is_human_reason 으로 갈린다
        self.assertIn('if is_human_reason(reason):\n        keys = ("wake_day_count"', src)


if __name__ == "__main__":
    unittest.main()
