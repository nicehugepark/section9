"""문서에만 남은 jira.pending 을 outbox 로 되돌린다 (REQ-20260911-009).

실제 사고 2026-09-11: 문서는 done 인데 Jira 는 「진행 중」인 요청 셋. API token 을
못 읽는 순간의 실패가 `skipped` 로 돌아와 outbox 에서 빠졌고, 문서의 pending 을
다시 읽는 자리가 없었다. 고침은 둘 — 준비물 없음은 다시 시도할 실패이고,
쓸기가 이미 새어 나간 것을 같은 자리로 되돌린다.

실행: python3 tests/ jira_pending_sweep
"""
import contextlib
import http.server
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import tempfile
import threading
import time
import types
import unittest
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")

TRANSITIONS = [
    {"id": "11", "name": "To Do", "to": {"name": "To Do", "statusCategory": {"key": "new"}}},
    {"id": "21", "name": "In Progress", "to": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}},
    {"id": "31", "name": "Done", "to": {"name": "Done", "statusCategory": {"key": "done"}}},
]


class Stub(http.server.BaseHTTPRequestHandler):
    status = {"name": "To Do", "statusCategory": {"key": "new"}}
    posts = []

    def _send(self, st, body):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlsplit(self.path)
        if u.path.endswith("/transitions"):
            return self._send(200, {"transitions": TRANSITIONS})
        if u.path.startswith("/rest/api/3/issue/"):
            return self._send(200, {"fields": {"status": Stub.status}})
        return self._send(404, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if urlsplit(self.path).path.rstrip("/") == "/rest/api/3/issue":
            return self._send(201, {"key": "MP1-9"})
        Stub.posts.append(body)
        # 코멘트는 201 + 본문, 전이는 204 — Jira 가 그렇게 답한다. 전이마다
        # 코멘트가 함께 가게 된 뒤로(REQ-20260912-001) 이 갈림이 필요해졌다.
        if urlsplit(self.path).path.endswith("/comment"):
            return self._send(201, {"id": "10001"})
        return self._send(204, None)

    def log_message(self, *a):
        pass


class JiraPendingSweep(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.status, Stub.posts = {"name": "To Do", "statusCategory": {"key": "new"}}, []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION", "S9_SYNC")}
        self.root = tempfile.mkdtemp(prefix="s9jsw-")
        os.environ["S9_ROOT"] = self.root
        for k in ("S9_USER", "S9_SESSION"):
            os.environ.pop(k, None)
        os.environ["S9_SYNC"] = "off"
        name = "s9jsw_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        self.site = f"http://127.0.0.1:{self.port}"
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.do_project_jira_set("pay", actor="hong", site=self.site, project_key="MP1")
        m.do_user_config_set("hong", "jira_site", self.site)
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        self.token_on()
        self.slept = []
        self.rid = self.new_request()
        m._jira_write(self.rid, {"site": self.site, "key": "MP1-7", "url": "x",
                                 "status": "To Do", "status_category": "new",
                                 "pending": ""}, "")
        m.jira_outbox_write([])       # 생성 훅이 실은 것은 이 시험의 관심이 아니다

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def token_on(self):
        self.m.secret_write("hong", self.m.JIRA_SECRET_KEY, "fake-token-for-the-stub-0123456789")

    def token_off(self):
        """준비물이 잠깐 없는 순간 — API token 만 사라진다."""
        self.m.secret_remove("hong", self.m.JIRA_SECRET_KEY)

    def new_request(self, title="환불 API"):
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="s", goal="g", status="open", size="S",
            priority=None, user="hong", assignee=None, tag_list=[], parent=None, derived_from=None,
            relates=None, why="", ref_doc=None, ref_link=None, ref_file=None, needs_os="",
            from_chat="", project="pay", project_tag=None, body="본문", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def jira_of(self, did=None):
        return self.m.read_doc(self.m.find_path(did or self.rid))[0].get("jira") or {}

    def outbox(self):
        return [(r["id"], r.get("kind")) for r in self.m.jira_outbox_read()]

    def tick(self, at=None):
        return self.m.jira_outbox_tick(now=at or time.time() + 1, _sleep=self.slept.append)

    # ── 정상 ─────────────────────────────────────────────────────────────
    def test_t1_missing_token_keeps_the_push_in_the_outbox(self):
        """준비물이 없어 실패한 push 는 건너뜀이 아니라 다시 시도할 실패다."""
        # 전이마다 상태와 코멘트가 함께 실린다 (REQ-20260912-001) — 여기서
        # 보는 것은 **준비물이 없을 때 push 가 남는가**다.
        self.m.do_transition(self.rid, "in-progress", note="착수", user="hong")
        self.assertEqual(self.outbox(), [(self.rid, "push"), (self.rid, "result")])
        self.token_off()
        self.assertEqual(self.tick()[0], (self.rid, False))
        self.assertIn((self.rid, "push"), self.outbox(), "준비물 공백에 outbox 에서 빠졌다")
        row = [r for r in self.m.jira_outbox_read() if r["kind"] == "push"][0]
        self.assertEqual(int(row["attempts"]), 1)
        self.assertIn("준비물", row.get("last_error", ""))
        self.assertEqual(self.jira_of()["pending"], "push")

    def test_t2_token_back_the_next_tick_completes_the_push(self):
        """준비물이 돌아오면 다음 때에 보내지고 pending 이 빈다."""
        self.m.do_transition(self.rid, "in-progress", note="착수", user="hong")
        self.token_off()
        self.tick()
        self.token_on()
        later = max(r["next_at"] for r in self.m.jira_outbox_read()) + 1
        self.assertIn((self.rid, True), self.tick(at=later))
        self.assertIn({"transition": {"id": "21"}}, Stub.posts)
        self.assertEqual(self.jira_of()["pending"], "")
        self.assertEqual(self.outbox(), [])

    # ── 경계 ─────────────────────────────────────────────────────────────
    def test_t3_real_skips_still_leave_the_outbox(self):
        """이슈가 없는 문서는 종전대로 건너뛰어 outbox 에서 빠진다."""
        other = self.new_request("이슈 없는 요청")
        self.m._jira_write(other, {"pending": "", "key": ""}, "")
        self.m.jira_outbox_write([])
        self.m.jira_outbox_add(other, "push")
        self.assertEqual(self.tick(), [(other, False)])
        self.assertEqual(self.outbox(), [], "진짜 건너뜀이 outbox 에 남았다")

    # ── 실패 ─────────────────────────────────────────────────────────────
    def test_t4_sweep_reloads_a_pending_that_left_the_outbox(self):
        """문서에만 남은 pending(push·create)을 쓸기가 다시 싣는다."""
        self.m._jira_write(self.rid, {"pending": "push"}, "")
        second = self.new_request("이슈가 안 선 요청")
        self.m._jira_write(second, {"pending": "create"}, "")
        self.m.jira_outbox_write([])          # 둘 다 outbox 밖 — 사고 당시의 모습
        got = self.m.jira_pending_sweep(force=True)
        self.assertEqual(sorted(got), sorted([(self.rid, "push"), (second, "create")]))
        self.assertEqual(sorted(self.outbox()), sorted([(self.rid, "push"), (second, "create")]))

    def test_t5_sweep_does_not_double_load_what_the_outbox_already_has(self):
        self.m._jira_write(self.rid, {"pending": "push"}, "")
        self.m.jira_outbox_write([])
        self.m.jira_outbox_add(self.rid, "push")
        self.assertEqual(self.m.jira_pending_sweep(force=True), [])
        self.assertEqual(self.outbox(), [(self.rid, "push")])

    # ── 회귀 ─────────────────────────────────────────────────────────────
    def test_t6_sweep_leaves_a_settled_document_alone(self):
        """pending 이 비고 상태도 맞는 문서는 싣지 않는다."""
        self.assertEqual(self.jira_of()["pending"], "")
        self.m._jira_write(self.rid, {"status_category": "new"}, "")   # open ↔ new
        self.m.jira_outbox_write([])
        self.assertEqual(self.m.jira_pending_sweep(force=True), [])
        self.assertEqual(self.outbox(), [])

    def test_t7_sweep_waits_ten_minutes_between_runs(self):
        """매 틱 카탈로그를 훑지 않는다 — 10분에 한 번."""
        now = time.time()
        self.m._jira_write(self.rid, {"pending": "push"}, "")
        self.m.jira_outbox_write([])
        self.assertEqual(self.m.jira_pending_sweep(now=now), [(self.rid, "push")])
        self.m.jira_outbox_write([])
        self.assertEqual(self.m.jira_pending_sweep(now=now + 60), [], "10분 안에 또 훑었다")
        self.assertEqual(self.m.jira_pending_sweep(now=now + self.m.JIRA_SWEEP_SEC + 1),
                         [(self.rid, "push")])

    def test_t8_a_late_issue_follows_the_document_status(self):
        """이미 옮겨 간 문서에 이슈가 늦게 서면 상태를 뒤따라 보낸다."""
        late = self.new_request("늦게 서는 이슈")
        self.m.do_transition(late, "in-progress", note="착수", user="hong")
        self.m.do_transition(late, "done", note="goal 충족", user="hong", force=True)
        self.m._jira_write(late, {"pending": "create", "key": ""}, "")
        self.m.jira_outbox_write([])
        res = self.m.jira_issue_create(late, actor="hong", _sleep=self.slept.append)
        self.assertTrue(res["ok"], res)
        self.assertIn((late, "push"), self.outbox(), "done 문서인데 상태를 뒤따르지 않았다")

    def test_t9_sweep_catches_a_drifted_status_with_no_pending(self):
        """pending 이 비었어도 문서와 이슈가 어긋나 있으면 싣는다 — 늦게 선 이슈."""
        self.m._jira_write(self.rid, {"pending": "", "status": "To Do",
                                      "status_category": "new"}, "")
        self.m.do_transition(self.rid, "in-progress", note="착수", user="hong")
        self.m.jira_outbox_write([])          # 전이가 실은 것을 지운다 — 사고 당시의 모습
        self.assertEqual(self.m.jira_pending_sweep(force=True), [(self.rid, "push")])

    def test_t10_sweep_leaves_a_matching_status_alone(self):
        """이름·카테고리가 이미 맞으면 싣지 않는다 — 10분마다 도는 왕복을 만들지 않는다."""
        self.m._jira_write(self.rid, {"pending": "", "status": "To Do",
                                      "status_category": "new"}, "")
        self.m.jira_outbox_write([])
        self.assertEqual(self.m.jira_pending_sweep(force=True), [])

    def test_t11_the_watch_tick_runs_the_sweep(self):
        """워처 한 틱이 쓸기를 함께 세운다 — 손으로 부르는 길만 있으면 낫지 않는다."""
        Stub.status = {"name": "Done", "statusCategory": {"key": "done"}}
        self.m._jira_write(self.rid, {"pending": "push"}, "")
        self.m.jira_outbox_write([])
        self.m._jira_sweep_write({"at": 0})
        self.m.jira_watch_tick()
        self.assertEqual(self.jira_of()["pending"], "", "틱이 쓸기를 부르지 않았다")
        self.assertEqual(Stub.posts[-1], {"transition": {"id": "11"}})


if __name__ == "__main__":
    unittest.main()
