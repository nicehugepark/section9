"""우리 → Jira 상태 push (REQ-20260908-075) — 로컬 http.server 스텁.

전이 경로는 네트워크를 타지 않는다: do_transition 이 outbox 에 싣고 워처가 보낸다.
Jira 는 상태를 직접 쓰지 못하므로 transition 을 고른다 — 이름(status_map) 먼저,
없으면 카테고리(new · indeterminate · done). pull 이 일으킨 전이는 되쏘지 않는다.

실행: python3 tests/ jira_push
"""
import http.server
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")

TRANSITIONS = [
    {"id": "11", "name": "To Do", "to": {"name": "To Do", "statusCategory": {"key": "new"}}},
    {"id": "21", "name": "In Progress", "to": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}},
    {"id": "22", "name": "In Review", "to": {"name": "In Review", "statusCategory": {"key": "indeterminate"}}},
    {"id": "31", "name": "Done", "to": {"name": "Done", "statusCategory": {"key": "done"}}},
]


class Stub(http.server.BaseHTTPRequestHandler):
    status = {"name": "To Do", "statusCategory": {"key": "new"}}
    transitions = TRANSITIONS
    fail_post = 0
    posts = []
    log = []

    def _send(self, st, body):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlsplit(self.path)
        Stub.log.append(("GET", u.path))
        if u.path.endswith("/transitions"):
            return self._send(200, {"transitions": Stub.transitions})
        if u.path.startswith("/rest/api/3/issue/"):
            return self._send(200, {"fields": {"status": Stub.status}})
        return self._send(404, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Stub.log.append(("POST", urlsplit(self.path).path))
        Stub.posts.append(body)
        if Stub.fail_post > 0:
            Stub.fail_post -= 1
            return self._send(503, {"errorMessages": ["down"]})
        # 코멘트는 201 + 본문, 전이는 204 — Jira 가 그렇게 답한다. 전이마다 코멘트가
        # 함께 가게 된 뒤로(REQ-20260912-001) 이 갈림이 필요해졌다.
        if urlsplit(self.path).path.endswith("/comment"):
            return self._send(201, {"id": "10001"})
        return self._send(204, None)

    def log_message(self, *a):
        pass


class JiraPush(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.status = {"name": "To Do", "statusCategory": {"key": "new"}}
        Stub.transitions, Stub.fail_post, Stub.posts, Stub.log = TRANSITIONS, 0, [], []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION", "S9_SYNC")}
        self.root = tempfile.mkdtemp(prefix="s9jp-")
        os.environ["S9_ROOT"] = self.root
        for k in ("S9_USER", "S9_SESSION"):
            os.environ.pop(k, None)
        os.environ["S9_SYNC"] = "off"
        name = "s9jp_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.do_project_jira_set("pay", actor="hong", site=f"http://127.0.0.1:{self.port}", project_key="MP1")
        m.do_user_config_set("hong", "jira_site", f"http://127.0.0.1:{self.port}")
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        m.secret_write("hong", m.JIRA_SECRET_KEY, "fake-token-for-the-stub-0123456789")
        self.slept = []
        self.rid = self.new_request()
        m._jira_write(self.rid, {"site": f"http://127.0.0.1:{self.port}", "key": "MP1-7",
                                 "url": "x", "status": "To Do", "pending": ""}, "")
        m.jira_outbox_write([])          # 생성 훅이 실은 것은 이 시험의 관심이 아니다

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def new_request(self):
        import contextlib, io, types
        args = types.SimpleNamespace(
            doc_type="request", title="환불 API", summary="s", goal="g", status="open", size="S",
            priority=None, user="hong", assignee=None, tag_list=[], parent=None, derived_from=None,
            relates=None, why="", ref_doc=None, ref_link=None, ref_file=None, needs_os="",
            from_chat="", project="pay", project_tag=None, body="본문", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def jira(self):
        return self.m.read_doc(self.m.find_path(self.rid))[0]["jira"]

    def tick(self):
        return self.m.jira_outbox_tick(now=time.time() + 1, _sleep=self.slept.append)

    def test_t1_transition_queues_and_the_tick_moves_the_issue(self):
        self.m.do_transition(self.rid, "in-progress", note="착수", user="hong")
        self.assertEqual(Stub.log, [], "전이가 Jira 를 불렀다")
        self.assertEqual(self.jira()["pending"], "push")
        # 상태가 먼저, 그 까닭(코멘트)이 다음 — 전이마다 둘이 실린다
        # (REQ-20260912-001: 「상태마다 코멘트도 같이 남겨야하고」).
        self.assertEqual([(r["id"], r["kind"]) for r in self.m.jira_outbox_read()],
                         [(self.rid, "push"), (self.rid, "result")])
        self.assertEqual(self.tick(), [(self.rid, True), (self.rid, True)])
        posts = [p for p in Stub.posts if "transition" in p]
        self.assertEqual(posts[-1], {"transition": {"id": "21"}})
        said = " ".join(json.dumps(p, ensure_ascii=False) for p in Stub.posts
                        if "body" in p)
        self.assertIn("착수", said, "전이의 까닭이 코멘트로 안 갔다")
        j = self.jira()
        self.assertEqual((j["status"], j["pending"], j["synced_by"]), ("In Progress", "", "s9"))
        self.assertEqual(self.m.jira_outbox_read(), [])

    def test_t2_status_map_name_wins_over_category(self):
        self.m.do_project_jira_set("pay", actor="hong")            # 값 유지
        meta, body, path = self.m.load_project("pay")
        meta["jira"]["status_map"] = {"review": "In Review"}
        self.m.write_doc(path, meta, body)
        self.m.do_transition(self.rid, "in-progress", note="착수", user="hong")
        self.m.jira_outbox_write([])
        Stub.status = {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}
        res = self.m.jira_status_push(self.rid, actor="hong", _sleep=self.slept.append)
        self.assertTrue(res["ok"] and res["skipped"], "카테고리가 같은데 다시 보냈다")
        self.m.do_transition(self.rid, "review", note="확인", user="hong", force=True)
        res = self.m.jira_status_push(self.rid, actor="hong", _sleep=self.slept.append)
        self.assertTrue(res["ok"], res)
        self.assertEqual(Stub.posts[-1], {"transition": {"id": "22"}}, "이름 매핑을 무시했다")

    def test_t3_already_there_means_no_transition(self):
        # 코멘트는 전이마다 가므로(REQ-20260912-001) 「POST 가 하나도 없다」가
        # 아니라 **상태를 옮기는 POST 가 없다**가 계약이다.
        Stub.status = {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}
        self.m.do_transition(self.rid, "in-progress", note="착수", user="hong")
        self.assertEqual(self.tick(), [(self.rid, True), (self.rid, True)])
        self.assertEqual([p for p in Stub.log
                          if p[0] == "POST" and p[1].endswith("/transitions")], [])
        self.assertEqual(self.jira()["status"], "In Progress")

    def test_t4_a_pull_made_transition_is_not_echoed(self):
        self.m.do_transition(self.rid, "in-progress", note="jira: MP1-7 → In Progress", user="hong", auto=True)
        self.assertEqual(self.m.jira_outbox_read(), [], "Jira 발 전이를 되쏘았다")
        self.assertEqual(self.jira().get("pending", ""), "")

    def test_t5_failure_backs_off_and_then_succeeds(self):
        Stub.fail_post = 3      # jira_http 가 스스로 몇 번 다시 걸어 본다
        self.m.do_transition(self.rid, "in-progress", note="착수", user="hong")
        # 상태와 코멘트는 **따로 간다** (REQ-20260912-001) — 하나가 넘어져도
        # 다른 하나는 간다. 넘어진 것만 물러났다 다시 온다.
        res = self.tick()
        self.assertEqual(res[0], (self.rid, False), res)
        j = self.jira()
        self.assertEqual(j["pending"], "push")
        self.assertTrue(j["last_error"])
        rows = [r for r in self.m.jira_outbox_read() if r["kind"] == "push"]
        self.assertEqual((rows[0]["kind"], rows[0]["attempts"]), ("push", 1))
        done = self.m.jira_outbox_tick(now=rows[0]["next_at"] + 1, _sleep=self.slept.append)
        self.assertIn((self.rid, True), done)
        self.assertEqual(self.jira()["status"], "In Progress")

    def test_t6_direction_pull_no_key_and_no_matching_transition(self):
        self.m.do_project_jira_set("pay", actor="hong", direction="pull")
        self.m.do_transition(self.rid, "in-progress", note="착수", user="hong")
        self.assertEqual(self.m.jira_outbox_read(), [])
        self.m.do_project_jira_set("pay", actor="hong", direction="push")
        rid2 = self.new_request()
        self.m.jira_outbox_write([])
        self.m.do_transition(rid2, "in-progress", note="착수", user="hong")
        self.assertEqual(self.m.jira_outbox_read(), [], "key 없는 요청을 실었다")
        Stub.transitions = [TRANSITIONS[0]]              # 갈 곳이 To Do 뿐
        res = self.m.jira_status_push(self.rid, actor="hong", _sleep=self.slept.append)
        self.assertFalse(res["ok"])
        self.assertIn("맞는 transition 이 없다", res["error"])
        self.assertEqual([p for p in Stub.log if p[0] == "POST"], [], "우회해서 보냈다")
        self.assertIn("status_map", self.jira()["last_error"])

    def test_t7_manual_push_sends_now(self):
        self.m.do_transition(self.rid, "done", note="끝", user="hong", force=True)
        res = self.m.jira_status_push(self.rid, actor="hong", _sleep=self.slept.append)
        self.assertTrue(res["ok"], res)
        self.assertEqual(Stub.posts[-1], {"transition": {"id": "31"}})
        self.assertEqual(self.jira()["status"], "Done")


if __name__ == "__main__":
    unittest.main(verbosity=2)
