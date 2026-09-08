"""Jira → 우리 상태 pull (REQ-20260908-076) — 로컬 http.server 스텁.

폴링이다. direction pull|both 인 프로젝트의 이슈 키를 모아 JQL 한 번, 카테고리가
바뀐 이슈의 요청을 검사를 지나는 do_transition 으로 옮긴다. 걸리면 값만 적는다.

실행: python3 tests/ jira_pull
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
from urllib.parse import urlsplit, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


def issue(key, name, cat):
    return {"key": key, "fields": {"status": {"name": name, "statusCategory": {"key": cat}}}}


class Stub(http.server.BaseHTTPRequestHandler):
    issues = []
    log = []

    def do_GET(self):
        u = urlsplit(self.path)
        Stub.log.append(("GET", u.path, parse_qs(u.query).get("jql", [""])[0]))
        if u.path == "/rest/api/3/search/jql":
            body = {"issues": Stub.issues}
        else:
            body = {"errorMessages": ["no"]}
        raw = json.dumps(body).encode()
        self.send_response(200 if u.path == "/rest/api/3/search/jql" else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


class JiraPull(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.issues, Stub.log = [], []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION", "S9_SYNC")}
        self.root = tempfile.mkdtemp(prefix="s9jpl-")
        os.environ["S9_ROOT"] = self.root
        for k in ("S9_USER", "S9_SESSION"):
            os.environ.pop(k, None)
        os.environ["S9_SYNC"] = "off"
        name = "s9jpl_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.do_project_jira_set("pay", actor="hong", site=f"http://127.0.0.1:{self.port}",
                              project_key="MP1", direction="both")
        m.do_user_config_set("hong", "jira_site", f"http://127.0.0.1:{self.port}")
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        m.secret_write("hong", m.JIRA_SECRET_KEY, "fake-token-for-the-stub-0123456789")
        self.rid = self.new_request()
        m._jira_write(self.rid, {"site": f"http://127.0.0.1:{self.port}", "key": "MP1-7", "url": "x",
                                 "status": "To Do", "status_category": "new", "pending": ""}, "")
        m.jira_outbox_write([])
        self.slept = []

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

    def doc(self):
        return self.m.read_doc(self.m.find_path(self.rid))[0]

    def pull(self, **kw):
        return self.m.jira_pull_tick(now=time.time(), force=True, _sleep=self.slept.append, **kw)

    def test_l1_a_changed_issue_moves_the_request(self):
        Stub.issues = [issue("MP1-7", "In Progress", "indeterminate")]
        res = self.pull()
        self.assertEqual([(d, r["transitioned"], r.get("to")) for d, r in res],
                         [(self.rid, True, "in-progress")])
        m = self.doc()
        self.assertEqual(m["status"], "in-progress")
        self.assertEqual((m["jira"]["status"], m["jira"]["synced_by"]), ("In Progress", "jira"))
        self.assertIn("key in (MP1-7)", Stub.log[0][2])
        self.assertIn("jira: MP1-7 → In Progress", self.m.read_doc(self.m.find_path(self.rid))[1])

    def test_l2_same_category_only_updates_the_value(self):
        Stub.issues = [issue("MP1-7", "Backlog", "new")]
        res = self.pull()
        self.assertEqual([(r["transitioned"], r["ok"]) for _, r in res], [(False, True)])
        m = self.doc()
        self.assertEqual((m["status"], m["jira"]["status"]), ("open", "Backlog"))

    def test_l3_a_refused_transition_only_records_the_difference(self):
        self.m.do_transition(self.rid, "done", note="끝", user="hong", force=True)
        self.m.jira_outbox_write([])
        Stub.issues = [issue("MP1-7", "In Progress", "indeterminate")]
        res = self.pull()
        self.assertEqual([r["transitioned"] for _, r in res], [False])
        m = self.doc()
        self.assertEqual(m["status"], "done", "끝난 문서를 되살렸다")
        self.assertEqual(m["jira"]["status_category"], "indeterminate")
        self.assertTrue(self.m.jira_card_block(m)["differs"])

    def test_l4_a_pulled_transition_is_not_pushed_back(self):
        Stub.issues = [issue("MP1-7", "In Progress", "indeterminate")]
        self.pull()
        self.assertEqual(self.m.jira_outbox_read(), [], "pull 이 일으킨 전이를 되쏘았다")

    def test_l5_direction_push_projects_are_not_asked_and_the_window_is_remembered(self):
        self.m.do_project_jira_set("pay", actor="hong", direction="push")
        self.assertEqual(self.pull(), [])
        self.assertEqual(Stub.log, [])
        self.m.do_project_jira_set("pay", actor="hong", direction="pull")
        Stub.issues = []
        now = time.time()
        self.m.jira_pull_tick(now=now, force=True, _sleep=self.slept.append)
        self.assertEqual(len(Stub.log), 1)
        self.assertEqual(self.m.jira_pull_tick(now=now + 10, _sleep=self.slept.append), [],
                         "60초가 안 됐는데 또 물었다")
        self.assertEqual(len(Stub.log), 1)
        self.m.jira_pull_tick(now=now + 61, _sleep=self.slept.append)
        self.assertEqual(len(Stub.log), 2)

    def test_l6_network_failure_writes_nothing(self):
        self.m.do_user_config_set("hong", "jira_site", "http://127.0.0.1:1")
        self.m.do_project_jira_set("pay", actor="hong", site="http://127.0.0.1:1")
        before = self.doc()["jira"]
        self.assertEqual(self.pull(), [])
        self.assertEqual(self.doc()["jira"], before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
