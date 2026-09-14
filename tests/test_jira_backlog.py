"""준비물이 돌아오면 밀린 발신함은 곧바로 나간다 (REQ-20260914-015-62x6).

실측 2026-09-14 21:45. 시험용으로 짧게 둔 token 만료일(09-12)을 내일로 고쳐
`s9 jira ping` 은 바로 「연동됐습니다」였는데, 발신함 26건은 실패 52번 뒤의
backoff(최대 1시간) 때문에 `next_at` 22:13 까지 기다렸다 — 경보 문구는 「준비물이
채워지면 발신함은 스스로 다시 나간다」인데 실제로는 한 시간 뒤였다. 리드가
`next_at` 을 손으로 0 으로 돌리고 일곱 틱을 돌려서야 비웠다.

계약: 준비물(token 만료·없음)로 막혔던 항목은 준비물이 돌아온 틱에서 `next_at`
을 기다리지 않는다. 다른 까닭(HTTP 오류 등)으로 미뤄진 항목은 그대로 기다린다.
실행: python3 tests/ jira_backlog
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class BacklogLeavesWhenCredentialsReturn(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_USER", "S9_AUTO_RESUME", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jb-")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_USER"] = "hong"
        for k in ("S9_AUTO_RESUME", "S9_SESSION"):
            os.environ.pop(k, None)
        name = "s9jb_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.chat_target = lambda sid8=None, user=None: {"session": "sid00000"}
        m._inbox_watch_alive = lambda sid: bool(sid)
        m.do_project_jira_set("pay", actor="hong", site="https://ex.atlassian.net",
                              project_key="MP1")
        m.do_user_config_set("hong", "jira_site", "https://ex.atlassian.net")
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        m.secret_write("hong", m.JIRA_SECRET_KEY, "fake-token-for-tests-0123456789")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def new_request(self, title):
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="환불을 돕는다", goal="환불이 된다",
            status="open", size="S", priority=None, user="hong", assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project="pay", project_tag=None, body="본문", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    # 계약 — 만료로 막혔다가 만료일을 고치면, 다음 틱에서 next_at 을 기다리지 않는다
    def test_expired_then_refilled_goes_out_at_once(self):
        m = self.m
        m.do_user_config_set("hong", "jira_token_expires", "2000-01-01")
        for i in range(3):
            self.new_request(f"환불 API {i}")
        t0 = time.time()
        m.jira_outbox_tick(now=t0)                     # 준비물 없음 → 실패, next_at = t0 + 30
        rows = m.jira_outbox_read()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(float(r["next_at"]) > t0 + 1 for r in rows), "실패가 backoff 를 안 남겼다")
        self.assertTrue(all("준비물" in r["last_error"] for r in rows), rows)

        m.jira_outbox_tick(now=t0 + 1)                 # 아직 막혀 있다 — 때도 아니다
        self.assertEqual([int(r["attempts"]) for r in m.jira_outbox_read()], [1, 1, 1],
                         "때가 안 됐는데 시도했다")

        m.do_user_config_set("hong", "jira_token_expires", "2099-12-31")   # 준비물이 돌아왔다
        sent = []
        m.jira_issue_create = lambda doc_id, **kw: (sent.append(doc_id) or {"ok": True})
        m.jira_outbox_tick(now=t0 + 2)                 # next_at(t0+30) 전인데도 나간다
        self.assertEqual(len(sent), 3, "준비물이 돌아왔는데 backoff 를 기다렸다 — 그날 그 자리")
        self.assertEqual(m.jira_outbox_read(), [], "나간 항목이 발신함에 남았다")

    # 경계 — 준비물이 아닌 까닭으로 미뤄진 항목은 그대로 기다린다
    def test_other_failures_still_wait_their_turn(self):
        m = self.m
        m.do_user_config_set("hong", "jira_token_expires", "2099-12-31")
        rid = self.new_request("환불 API 4")
        rows = m.jira_outbox_read()
        self.assertEqual(len(rows), 1)
        t0 = time.time()
        rows[0]["next_at"] = t0 + 600
        rows[0]["attempts"] = 3
        rows[0]["last_error"] = "HTTP 503 — Jira 가 잠시 답하지 않는다"
        m.jira_outbox_write(rows)
        sent = []
        m.jira_issue_create = lambda doc_id, **kw: (sent.append(doc_id) or {"ok": True})
        m.jira_outbox_tick(now=t0 + 2)
        self.assertEqual(sent, [], "준비물과 무관한 backoff 를 무시했다")
        self.assertEqual(len(m.jira_outbox_read()), 1)
        self.assertEqual(rid, m.jira_outbox_read()[0]["id"])


if __name__ == "__main__":
    unittest.main()
