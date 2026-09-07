"""질문에 답이 붙었는가 — 판정 규칙 (REQ-20260907-040 · -043).

이 값은 상태가 아니라 **파생**이다(DOC-20260826-011): 진실은 문서 본문과 관계
하나뿐이고, 카탈로그의 `answered` 는 언제든 다시 만들 수 있는 사본이다. 상태축을
따로 두면 「답했는데 답 없음」이라는 두 번째 진실이 생긴다.

고정하는 계약 셋.
1. 사람이 단 답(`answer`·`response` 라벨)이 있으면 답한 것이다.
2. 그 질문에서 갈라져 나간 문서가 있으면 답한 것이다 — 물음이 곧바로 일이 되면
   사람은 그 일을 하고 질문 문서에 같은 말을 옮겨 적지 않는다.
3. **`agent-answer` 는 답이 아니다** — 에이전트가 뒤늦게 찾아 온 답은 사람이
   확정하기 전까지 답이 아니다. 라벨 이름을 잘못 지으면 이 선이 조용히 무너진다.

실행: python3 tests/ answered
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-answered-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_answered", importlib.machinery.SourceFileLoader("s9_mod_answered", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def note(label):
    return f"## Notes\n\n### 2026-09-07T14:00:00+09:00 {label} (by tester)\n답이다.\n"


class HumanAnswer(unittest.TestCase):
    def test_answer_label_counts(self):
        self.assertTrue(mod._answered(note("answer")))

    def test_response_label_counts(self):
        # Stop 훅 폴백·수동 기록이 이 라벨로 들어온다
        self.assertTrue(mod._answered(note("response")))

    def test_other_labels_do_not_count(self):
        for lab in ("tdd", "subagent", "recap"):
            self.assertFalse(mod._answered(note(lab)), lab)

    def test_empty_body(self):
        self.assertFalse(mod._answered(""))
        self.assertFalse(mod._answered(None))


class AgentAnswerIsNotAnAnswer(unittest.TestCase):
    """에이전트가 찾은 답은 사람이 확정하기 전까지 답이 아니다 (REQ-20260907-040)."""

    def test_agent_answer_does_not_count(self):
        self.assertFalse(mod._answered(note("agent-answer")))

    def test_the_naming_trap(self):
        """라벨을 `answer-` 로 시작하면 그대로 답으로 세어진다 — 짓지 마라.

        이 시험은 통과를 지키는 것이 아니라 **함정을 문서로 박아 두는 것**이다.
        나중에 누가 `answer-recap` 같은 이름을 고르면 답 없는 질문이 조용히
        사라진다(답 없는 것보다 나쁘다).
        """
        self.assertTrue(mod._answered(note("answer-recap")),
                        "정규식이 바뀌었다면 이 시험의 경고문도 함께 고쳐라")
        self.assertFalse(mod._answered(note("agent-answer")))


class DerivedWorkIsAnAnswer(unittest.TestCase):
    """갈라져 나간 일도 답이다 (REQ-20260907-043)."""

    def test_children_count_as_answered(self):
        self.assertTrue(mod._answered("", {"children": ["REQ-20260907-033-62x6"]}))

    def test_no_children_is_not_answered(self):
        self.assertFalse(mod._answered("", {"children": []}))
        self.assertFalse(mod._answered("", {}))
        self.assertFalse(mod._answered("", None))

    def test_body_answer_still_wins_without_meta(self):
        # meta 를 안 넘기는 옛 호출부가 있어도 동작이 안 바뀐다
        self.assertTrue(mod._answered(note("answer")))


if __name__ == "__main__":
    unittest.main()
