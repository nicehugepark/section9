"""agent_type 없는 SubagentStop 은 문서에 붙지 않는다 (REQ-20260914-004-62x6).

실제 사고 2026-09-14 11:22:52: 컨텍스트 압축 요약(<analysis>…<summary>, 12014자)이
`sub:subagent:ac1b5123` 이름으로 REQ-20260914-002-62x6 에 위임 보고로 붙었다. 같은
세션의 typeless 캡처 12건이 전부 Claude Code 가 스스로 띄우는 보조 에이전트의
출력이었다 — 38~53자 명령 설명 문구(「Appending TDD note to …」)와 리드 응답의
복사본. 사람이 Agent 도구로 위임한 에이전트는 agent_type 을 싣는다 — 없으면
위임이 아니다. 압축 요약은 유형이 실려도 붙이지 않는다.
실행: python3 tests/ subagent_typeless
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
    "s9sub_typeless", importlib.machinery.SourceFileLoader(
        "s9sub_typeless", os.path.join(HERE, "..", "bin", "s9-audit-subagent")))
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

BIND = json.dumps({"last_req": "REQ-20260824-001",
                   "active_reqs": ["REQ-20260824-002"]})


def run_hook(payload):
    calls = []

    def fake_run(env, *argv, inp=None):
        calls.append((argv, inp))
        out = ""
        if argv == ("bind",):
            out = BIND
        elif argv[:2] == ("last", "--owns"):
            out = argv[2]
        elif argv[0] == "show":
            out = "id: X\nstatus: in-progress\n"
        return mock.Mock(returncode=0, stdout=out)

    with mock.patch.object(hook, "run", fake_run), \
         mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
        hook.main()
    return calls


def notes(calls):
    return [c for c in calls if c[0][:1] == ("note",)]


def logs(calls):
    return [c[0][1] for c in calls if c[0][:1] == ("log",)]


class TypelessIsNotADelegation(unittest.TestCase):
    # 그날의 사고 — 압축 요약이 붙었다
    def test_the_compaction_summary_does_not_land_on_a_request(self):
        calls = run_hook({"session_id": "s1", "agent_id": "ac1b5123deadbeef",
                          "last_assistant_message":
                          "<analysis>\n… REQ-20260824-002 …\n</analysis>\n<summary>…</summary>"})
        self.assertEqual(notes(calls), [],
                         "압축 요약이 위임 보고로 붙었다 — 2026-09-14 11:22 그 자리")
        self.assertTrue(any("생략" in ln for ln in logs(calls)),
                        "붙이지 않은 것을 세션 로그에도 남기지 않았다")

    # 같은 세션의 다른 열두 건 — 명령 설명 문구
    def test_a_typeless_one_liner_mentioning_a_request_is_skipped(self):
        calls = run_hook({"session_id": "s1", "agent_id": "ad9c9b8e00000000",
                          "last_assistant_message": "Appending TDD note to REQ-20260824-002"})
        self.assertEqual(notes(calls), [], "명령 설명 문구가 위임 보고로 붙었다")

    # 유형이 실렸어도 압축 요약이면 붙이지 않는다
    def test_an_analysis_block_is_skipped_even_with_a_type(self):
        calls = run_hook({"session_id": "s1", "agent_type": "general-purpose",
                          "agent_id": "a1b2c3d4e5f6",
                          "last_assistant_message": "<analysis>\nREQ-20260824-002\n</analysis>"})
        self.assertEqual(notes(calls), [])

    # 회귀 — 진짜 위임은 그대로 붙는다
    def test_a_real_delegation_still_lands(self):
        calls = run_hook({"session_id": "s1", "agent_type": "s9-agnt-designer",
                          "agent_id": "a47f927d18087",
                          "last_assistant_message": "REQ-20260824-002 v2 마크를 실었다"})
        n = notes(calls)
        self.assertEqual(len(n), 1, "진짜 위임 보고가 붙지 않았다")
        self.assertEqual(n[0][0][1], "REQ-20260824-002")
        self.assertIn("sub:designer:a47f927d", n[0][0])


if __name__ == "__main__":
    unittest.main()
