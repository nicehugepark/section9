"""질문이 걸려 있으면 답은 질문 문서로 간다 (REQ-20260827-031-62x6).

사용자 질문: "질문 문서에서 대답은 언제 달리는거야? 운에 맡기는건가?"

운이 아니었다 — 규칙인데 그 규칙에 구멍이 있었다. Stop 훅은 `last_qst` 를
**진행 중인 REQ 가 없을 때만** 봤다:

    req = run(env, "last", "--active").stdout.strip()
    if not req:                       # ← 여기
        req, label = last_question(env), "answer"

터미널로 물으면 프롬프트 훅이 질문 턴에 캡처를 멈춰(`last --pause`) `last --active`
가 비므로 폴백이 산다. **대시보드로 물으면 그 훅을 안 탄다**(수신함 Monitor 경로).
캡처를 멈추는 사람이 없으니 세션이 붙들던 REQ 가 그대로 나오고, 답은 그 REQ 의
response 노트로 갔다. 질문 문서는 비어 있는 채 남았다 — 실제로 미답 5건이 전부
대시보드 질문이었다. 사용자는 주로 대시보드로 말하므로, 질문의 **기본 경로가
통째로 막혀 있었다.**

고침: 질문이 걸려 있으면 그 답은 질문 문서로 간다. 요청의 작업 보고는 규약상
리드가 직접 남기는 것이 1순위이고(CLAUDE.md 6항) 자동 캡처는 안전망이다 —
안전망이 질문의 답을 삼켜서는 안 된다.

실행: python3 tests/ answer_precedence
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


class AnswerPrecedence(unittest.TestCase):
    def drive(self, active_req, last_qst, text="답이다", note_rc=0):
        """Stop 훅을 한 번 돌리고 (호출목록) 을 준다."""
        stop = _load("s9_stop_prec_" + str(len(active_req) + len(last_qst)),
                     STOP_HOOK)
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append((argv, inp))

            class R:
                returncode = 0
                stdout = ""
            if argv == ("last", "--active"):
                R.stdout = active_req
            elif argv == ("bind",):
                R.stdout = json.dumps({"last_qst": last_qst})
            elif argv and argv[0] == "note":
                R.returncode = note_rc
            return R

        tp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8")
        tp.write(json.dumps({"type": "assistant", "message": {
            "model": "opus", "content": [{"type": "text", "text": text}]}})
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
    def _notes(calls):
        return [c for c in calls if c[0][0] == "note"]

    # N1. 진행 중 REQ 가 있어도 질문이 걸려 있으면 답은 질문 문서로
    def test_answer_precedence(self):
        """Stop 훅을 한 번 돌리고 (호출목록) 을 준다."""
        with self.subTest("n1_question_wins_over_active_req"):
                calls = self.drive("REQ-20260826-017-62x6", "QST-20260826-001-zz99")
                noted = self._notes(calls)
                self.assertEqual(len(noted), 1, noted)
                self.assertEqual(noted[0][0][1], "QST-20260826-001-zz99", noted)
                self.assertIn("answer", noted[0][0], noted)

            # N2. 붙인 뒤 포인터를 비운다 — 다음 턴 응답이 지난 질문에 붙지 않게
        with self.subTest("n2_pointer_consumed"):
                calls = self.drive("REQ-20260826-017-62x6", "QST-20260826-001-zz99")
                self.assertIn(("bind", "last_qst", ""), [c[0] for c in calls])

            # B1. 질문이 없으면 예전 그대로 — 진행 중 REQ 에 response
        with self.subTest("b1_no_question_keeps_request_capture"):
                calls = self.drive("REQ-20260826-017-62x6", "")
                noted = self._notes(calls)
                self.assertEqual(len(noted), 1, noted)
                self.assertEqual(noted[0][0][1], "REQ-20260826-017-62x6", noted)
                self.assertIn("response", noted[0][0], noted)

            # B2. 질문만 있고 REQ 가 없는 터미널 질문 턴도 예전 그대로
        with self.subTest("b2_question_only_unchanged"):
                calls = self.drive("", "QST-20260826-001-zz99")
                noted = self._notes(calls)
                self.assertEqual(noted[0][0][1], "QST-20260826-001-zz99", noted)
                self.assertIn("answer", noted[0][0], noted)

            # B3. 질문 문서가 사라졌으면(삭제 등) 진행 중 REQ 로 물러난다 —
            #     붙일 곳이 없다고 답을 통째로 버리면 지금 고치는 것과 같은 실패다
        with self.subTest("b3_dead_question_falls_back_to_req"):
                calls = self.drive("REQ-20260826-017-62x6", "QST-20260826-999-zz99",
                                   note_rc=1)
                noted = self._notes(calls)
                self.assertEqual(len(noted), 2, noted)
                self.assertEqual(noted[1][0][1], "REQ-20260826-017-62x6", noted)
                self.assertIn("response", noted[1][0], noted)

            # R1. 붙일 곳이 아무것도 없으면 예전대로 조용히 물러난다
        with self.subTest("r1_nothing_to_attach"):
            calls = self.drive("", "")
            self.assertEqual(self._notes(calls), [])

if __name__ == "__main__":
    unittest.main()
