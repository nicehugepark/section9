"""Jira 발신함은 같은 문서의 순서를 지킨다 — 상태가 먼저, 코멘트가 뒤 (REQ-20260915-007-62x6).

실제 발생 2026-09-15 11:24. REQ-20260915-001 이 review→done 되자 발신함에 push(상태)
와 result(코멘트)가 그 순서로 실렸는데, 상태 push 가 미뤄진 사이 코멘트가 먼저 가서
11:24:52 부터 11:26:53 까지 Jira 는 「상태 판정 · 코멘트 완료: 승인」이었다. 주인은
그것을 「연동이 제대로 안 되는 것 같다」로 읽었다.

계약: 한 틱 안에서 같은 문서의 앞 항목(push)이 못 나갔으면(때가 아니거나 실패)
그 문서의 뒤 항목(result·comment)은 보내지 않는다. 다른 문서는 서로 막지 않는다.
실행: python3 tests/ jira_order
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class StatusBeforeComment(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jo-")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_USER"] = "hong"
        os.environ.pop("S9_SESSION", None)
        name = "s9jo_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.m.jira_block_info = lambda now=None: None      # 준비물 판정은 이 시험의 관심이 아니다
        self.m.jira_block_notify = lambda info, now=None: None

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def queue(self, *rows):
        self.m.jira_outbox_write([{"id": i, "kind": k, "at": 0, "next_at": 0, "attempts": 0,
                                   "last_error": ""} for i, k in rows])

    # 계약 — 상태 push 가 실패하면 같은 문서의 코멘트는 이번 틱에 나가지 않는다
    def test_comment_waits_for_the_status(self):
        m = self.m
        self.queue(("REQ-A", "push"), ("REQ-A", "result"))
        calls = []
        m.jira_status_push = lambda doc_id, **kw: (calls.append(("push", doc_id)) or {"ok": False, "error": "transition 목록을 읽지 못했다"})
        m.jira_result_push = lambda doc_id, **kw: (calls.append(("result", doc_id)) or {"ok": True})
        t0 = time.time()
        m.jira_outbox_tick(now=t0)
        self.assertEqual(calls, [("push", "REQ-A")], "상태가 못 나갔는데 코멘트를 보냈다 — 그날 그 자리")
        rows = m.jira_outbox_read()
        self.assertEqual([r["kind"] for r in rows], ["push", "result"], "둘 다 발신함에 남아야 한다")
        # 상태가 나가면 그 다음 틱에 코멘트가 따라간다
        m.jira_status_push = lambda doc_id, **kw: (calls.append(("push", doc_id)) or {"ok": True})
        m.jira_outbox_tick(now=t0 + 3600)
        self.assertEqual(calls[1:], [("push", "REQ-A"), ("result", "REQ-A")])
        self.assertEqual(m.jira_outbox_read(), [])

    # 계약 — 상태 push 의 때가 아직이면(backoff) 코멘트도 기다린다
    def test_comment_waits_while_status_is_backed_off(self):
        m = self.m
        t0 = time.time()
        m.jira_outbox_write([
            {"id": "REQ-A", "kind": "push", "at": 0, "next_at": t0 + 600, "attempts": 2, "last_error": "HTTP 503"},
            {"id": "REQ-A", "kind": "result", "at": 0, "next_at": 0, "attempts": 0, "last_error": ""}])
        calls = []
        m.jira_status_push = lambda doc_id, **kw: (calls.append("push") or {"ok": True})
        m.jira_result_push = lambda doc_id, **kw: (calls.append("result") or {"ok": True})
        m.jira_outbox_tick(now=t0)
        self.assertEqual(calls, [], "상태의 때가 아닌데 코멘트가 먼저 갔다")
        self.assertEqual(len(m.jira_outbox_read()), 2)

    # 회귀 — 다른 문서는 서로 막지 않는다
    def test_other_documents_are_not_held(self):
        m = self.m
        self.queue(("REQ-A", "push"), ("REQ-B", "result"))
        calls = []
        m.jira_status_push = lambda doc_id, **kw: (calls.append(("push", doc_id)) or {"ok": False, "error": "x"})
        m.jira_result_push = lambda doc_id, **kw: (calls.append(("result", doc_id)) or {"ok": True})
        m.jira_outbox_tick(now=time.time())
        self.assertEqual(calls, [("push", "REQ-A"), ("result", "REQ-B")])
        self.assertEqual([r["id"] for r in m.jira_outbox_read()], ["REQ-A"])


if __name__ == "__main__":
    unittest.main()
