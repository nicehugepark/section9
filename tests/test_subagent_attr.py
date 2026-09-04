"""위임 보고 귀속 테스트 (REQ-20260824-023).

SubagentStop 캡처가 stale last_req 대신, 보고가 언급한 REQ(실행 등록 교집합 우선)에
귀속되고, generic 무언급 진행 보고는 노트를 만들지 않는다.
실행: python3 tests/test_subagent_attr.py
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_loader(
    "s9sub", importlib.machinery.SourceFileLoader(
        "s9sub", os.path.join(HERE, "..", "bin", "s9-audit-subagent")))
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

BIND = json.dumps({"last_req": "REQ-20260824-001",
                   "active_reqs": ["REQ-20260824-002", "REQ-20260824-003"]})


OPEN_META = "id: X\nstatus: in-progress\n"


def run_hook(payload, show_rc=0, show_meta=OPEN_META):
    calls = []
    session = str(payload.get("session_id", ""))[:8]
    bind = json.loads(BIND)
    registered = [bind["last_req"], *bind["active_reqs"]]

    def owns(doc_id):
        """`s9 last --owns` 흉내 — 실제 _session_owns와 같은 규칙
        (REQ-20260825-066): 이 세션이 실행 등록한 문서이거나, 문서의 승계
        기록이 없거나(구문서), 승계 기록에 이 세션이 있으면 소유."""
        if doc_id in registered:
            return True
        owners = [l.split(":", 1)[1].strip() for l in show_meta.splitlines()
                  if l.startswith(("session:", "sessions:"))]
        return not owners or any(session[:8] == o[:8] for o in owners)

    def fake_run(env, *argv, inp=None):
        calls.append((argv, inp))
        out, rc = "", 0
        if argv == ("bind",):
            out = BIND
        elif argv[:2] == ("last", "--owns"):
            out = argv[2] if owns(argv[2]) else ""
        elif argv[0] == "show":
            rc, out = show_rc, show_meta
        return mock.Mock(returncode=rc, stdout=out)

    with mock.patch.object(hook, "run", fake_run), \
         mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
        hook.main()
    return calls


class TestAttribution(unittest.TestCase):
    # C1. 보고가 언급한 REQ가 실행 등록에 있으면 last_req 대신 그쪽으로 귀속
    def test_test_attribution(self):
        """TestAttribution 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("c1_mentioned_active_wins"):
                calls = run_hook({"session_id": "s1", "agent_type": "designer",
                                  "last_assistant_message":
                                  "REQ-20260824-002 재작업 완료 보고"})
                notes = [c for c in calls if c[0][0] == "note"]
                self.assertEqual(len(notes), 1, calls)
                self.assertEqual(notes[0][0][1], "REQ-20260824-002", notes)

            # C2. generic 타입 + REQ 무언급 → 노트 생략(log만)
        with self.subTest("c2_generic_unmentioned_skipped"):
                calls = run_hook({"session_id": "s1",
                                  "last_assistant_message": "중간 진행 상황입니다"})
                self.assertFalse([c for c in calls if c[0][0] == "note"], calls)
                self.assertTrue([c for c in calls if c[0][0] == "log"], calls)

            # C3. 역할 명시 에이전트 + 무언급 → 기존대로 last_req 귀속
        with self.subTest("c3_typed_falls_back_to_last"):
                calls = run_hook({"session_id": "s1", "agent_type": "backend-developer",
                                  "last_assistant_message": "결과 요약입니다"})
                notes = [c for c in calls if c[0][0] == "note"]
                self.assertEqual(notes[0][0][1], "REQ-20260824-001", calls)

            # C4. 언급 REQ가 등록에 없어도 "아직 열려 있고 주인이 없으면" 그쪽으로
        with self.subTest("c4_mentioned_open_doc"):
                calls = run_hook({"session_id": "s1", "agent_type": "designer",
                                  "last_assistant_message": "REQ-20260824-009 관련 산출"})
                notes = [c for c in calls if c[0][0] == "note"]
                self.assertEqual(notes[0][0][1], "REQ-20260824-009", calls)

            # C5 (실사고, REQ-20260825-066 후속). 종결된 문서를 언급했다고 거기에 붙이지
            #     않는다 — done 상태의 065에 서브에이전트 보고가 붙어 사용자가 두 번 지적.
        with self.subTest("c5_mentioned_done_doc_rejected"):
                calls = run_hook({"session_id": "s1", "agent_type": "designer",
                                  "last_assistant_message":
                                  "Checking note timestamps in REQ-20260824-065.md"},
                                 show_meta="id: REQ-20260824-065\nstatus: done\n")
                notes = [c for c in calls if c[0][0] == "note"]
                self.assertEqual(notes[0][0][1], "REQ-20260824-001", calls)  # last_req 폴백
                self.assertTrue([c for c in calls if c[0][0] == "log"
                                 and "귀속 거부" in c[0][1]], calls)

            # C6. 다른 세션이 승계한 문서도 거부 — "읽은 문서 ≠ 작업한 문서"
        with self.subTest("c6_other_session_doc_rejected"):
                calls = run_hook({"session_id": "s1", "agent_type": "designer",
                                  "last_assistant_message": "REQ-20260824-009 확인"},
                                 show_meta="status: in-progress\nsession: 104b4fe3\n")
                notes = [c for c in calls if c[0][0] == "note"]
                self.assertEqual(notes[0][0][1], "REQ-20260824-001", calls)

            # C7. 같은 세션이 승계한 문서는 정상 귀속
        with self.subTest("c7_own_session_doc_accepted"):
            calls = run_hook({"session_id": "104b4fe3aaaa", "agent_type": "designer",
                              "last_assistant_message": "REQ-20260824-009 확인"},
                             show_meta="status: in-progress\nsession: 104b4fe3\n")
            notes = [c for c in calls if c[0][0] == "note"]
            self.assertEqual(notes[0][0][1], "REQ-20260824-009", calls)

if __name__ == "__main__":
    unittest.main(verbosity=2)
