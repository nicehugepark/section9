"""연달아 온 질문이 유실되지 않는다 (REQ-20260827-049-62x6).

실사고 2026-08-27:

    20:25:57  질문 도착 → last_qst = QST-019
    20:25~28  리드의 턴이 길어짐(구현 중)
    20:28:13  다음 질문 도착 → last_qst 가 QST-020 으로 **덮임**
    (그 뒤)   턴이 끝나고 Stop 훅이 020 에만 답을 붙임 → **019 는 영영 미답**

"답할 차례" 표가 한 칸뿐이라, **질문이 답보다 빨리 오면 앞 질문이 지워진다.**
연달아 묻는 대화에서는 반드시 일어난다 — QST-009 도 같은 이유로 잃었다.

REQ-20260827-031 은 이것의 절반만 고쳤다(진행 중 REQ 보다 질문이 우선). 표가 한
칸이라는 것은 그대로였다.

한 답이 여러 질문에 붙는 것이 이상해 보일 수 있지만, 실제로 그 한 응답이 그
질문들을 함께 다룬 것이라 **사실에 맞다.** 붙일 곳이 없어 잃는 것보다 낫다.

실행: python3 tests/ question_queue
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
STOP_HOOK = os.path.join(HERE, "..", "bin", "s9-audit-response")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class QuestionQueue(unittest.TestCase):
    def drive(self, binding, active_req="", note_fail=()):
        """Stop 훅을 한 번 돌리고 (호출목록) 을 준다."""
        stop = _load("s9_qq_" + str(len(binding)), STOP_HOOK)
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append((argv, inp))

            class R:
                returncode = 0
                stdout = ""
            if argv == ("last", "--active"):
                R.stdout = active_req
            elif argv == ("bind",):
                R.stdout = json.dumps(binding)
            elif argv and argv[0] == "note" and argv[1] in note_fail:
                R.returncode = 1
            return R

        tp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8")
        tp.write(json.dumps({"type": "assistant", "message": {
            "model": "opus", "content": [{"type": "text", "text": "답"}]}})
            + "\n")
        tp.close()
        data = {"session_id": "abcd1234", "transcript_path": tp.name, "cwd": ""}
        try:
            with mock.patch.object(stop, "run", fake_run), \
                    mock.patch.object(stop, "mirror_transcript",
                                      lambda *a: None), \
                    mock.patch.object(sys, "stdin",
                                      io.StringIO(json.dumps(data))):
                stop.main()
        finally:
            os.unlink(tp.name)
        return calls

    @staticmethod
    def _answered(calls):
        return [c[0][1] for c in calls
                if c[0][0] == "note" and "answer" in c[0]]

    # N1. 답하기 전에 둘이 오면 둘 다 받는다
    def test_question_queue(self):
        """Stop 훅을 한 번 돌리고 (호출목록) 을 준다."""
        with self.subTest("n1_all_pending_answered"):
                calls = self.drive({"pending_qst": ["QST-A", "QST-B"]})
                self.assertEqual(self._answered(calls), ["QST-A", "QST-B"])

            # N2. 붙인 뒤 목록을 비운다 — 다음 턴 답이 지난 질문에 또 붙지 않게
        with self.subTest("n2_queue_cleared"):
                calls = self.drive({"pending_qst": ["QST-A"]})
                binds = [c[0] for c in calls if c[0][0] == "bind"]
                self.assertIn(("bind", "pending_qst", ""), binds, binds)

            # B1. 목록이 비어 있으면 예전 폴백(last_qst)을 쓴다
        with self.subTest("b1_falls_back_to_last_qst"):
                calls = self.drive({"last_qst": "QST-OLD"})
                self.assertEqual(self._answered(calls), ["QST-OLD"])

            # B2. 하나가 사라졌어도 나머지엔 붙인다 — 하나 때문에 전부 버리지 않는다
        with self.subTest("b2_missing_one_keeps_rest"):
                calls = self.drive({"pending_qst": ["QST-GONE", "QST-OK"]},
                                   note_fail=("QST-GONE",))
                self.assertIn("QST-OK", self._answered(calls))

            # F1. 하나도 성사되지 않으면 진행 중 REQ 로 물러난다 (031 의 폴백 유지)
        with self.subTest("f1_all_fail_falls_back_to_req"):
                calls = self.drive({"pending_qst": ["QST-GONE"]},
                                   active_req="REQ-X", note_fail=("QST-GONE",))
                noted = [c[0] for c in calls if c[0][0] == "note"]
                self.assertTrue(any(a[1] == "REQ-X" and "response" in a
                                    for a in noted), noted)

            # R1. 질문이 하나면 지금과 완전히 같다
        with self.subTest("r1_single_question_unchanged"):
            calls = self.drive({"pending_qst": ["QST-ONE"]})
            self.assertEqual(self._answered(calls), ["QST-ONE"])

if __name__ == "__main__":
    unittest.main()
