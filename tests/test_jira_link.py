"""이미 있는 Jira 이슈를 만들지 않고 잇는다 (REQ-20260909-036) — 로컬 http.server
스텁이 Jira 노릇을 한다.

주인 요구 2026-09-09 11:11: 「수동으로 JIRA 티켓 번호를 카드나 문서에서 추가를 한 후에
작동을 하게 되는거면 모를까」. 길은 do_set 하나(`s9 set --jira-key` · /api/doc/set).
규칙: 프로젝트에 연동이 있어야 하고 · 키의 접두가 project_key 와 같아야 하고 · 그
사람의 토큰으로 GET /issue/{key} 가 200 이어야 한다. 통과하면 문서 jira 블록이 서고
라벨 s9-<id> 를 그 이슈에 붙인다(실패해도 연결은 유지). 끊기는 문서만 비운다.

실행: python3 tests/ jira_link
"""
import http.server
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class Stub(http.server.BaseHTTPRequestHandler):
    exists = {}         # key -> (status name, category)
    fail_put = 0        # PUT 을 이만큼 5xx 로
    log = []            # (method, path)
    puts = []           # (path, body)

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
        if u.path.startswith("/rest/api/3/issue/"):
            key = u.path.rsplit("/", 1)[1]
            if key in Stub.exists:
                name, cat = Stub.exists[key]
                return self._send(200, {"key": key, "fields": {
                    "summary": "저쪽 제목", "status": {"name": name, "statusCategory": {"key": cat}}}})
            return self._send(404, {"errorMessages": ["Issue does not exist or you do not have permission to see it."]})
        return self._send(404, {"errorMessages": ["no"]})

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Stub.log.append(("PUT", self.path))
        Stub.puts.append((self.path, body))
        if Stub.fail_put > 0:
            Stub.fail_put -= 1
            return self._send(503, {"errorMessages": ["down"]})
        return self._send(204, None)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        Stub.log.append(("POST", self.path))
        return self._send(201, {"id": "10001", "key": "MP1-999"})

    def log_message(self, *a):
        pass


class JiraLink(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.exists, Stub.fail_put, Stub.log, Stub.puts = {}, 0, [], []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION", "S9_SYNC")}
        self.root = tempfile.mkdtemp(prefix="s9jl-")
        os.environ["S9_ROOT"] = self.root
        for k in ("S9_USER", "S9_SESSION"):
            os.environ.pop(k, None)
        os.environ["S9_SYNC"] = "off"
        name = "s9jl_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        site = f"http://127.0.0.1:{self.port}"
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.do_project_jira_set("pay", actor="hong", site=site, project_key="MP1",
                              direction="both", export="manual")
        m.do_project_add("docs", name="문서", summary="", actor="hong")   # 연동 없음
        m.do_user_config_set("hong", "jira_site", site)
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        m.secret_write("hong", m.JIRA_SECRET_KEY, "fake-token-for-the-stub-0123456789")
        self.rid = self.new_request()
        m.jira_outbox_write([])
        Stub.log = []

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def new_request(self, project="pay", title="환불 API"):
        import contextlib, io, types
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="환불을 돕는다", goal="환불이 된다",
            status="open", size="S", priority=None, user="hong", assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project=project, project_tag=None, body="본문", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def doc(self, doc_id):
        return self.m.read_doc(self.m.find_path(doc_id))

    def link(self, key, doc_id=None):
        return self.m.do_set(doc_id or self.rid, {"jira_key": key}, actor="hong", via="test")

    def test_l1_link_writes_block_and_labels_the_issue(self):
        Stub.exists["MP1-7"] = ("진행 중", "indeterminate")
        res = self.link("MP1-7")
        self.assertTrue(res["ok"], res)
        self.assertIn("jira_key", res["changed"])
        meta, body = self.doc(self.rid)
        j = meta["jira"]
        self.assertEqual((j["key"], j["status"], j["status_category"], j["synced_by"]),
                         ("MP1-7", "진행 중", "indeterminate", "hong"))
        self.assertEqual(j["url"], f"http://127.0.0.1:{self.port}/browse/MP1-7")
        self.assertTrue(j["synced_at"])
        self.assertIn("jira: MP1-7 연결 (by hong", body)
        self.assertIn(("GET", "/rest/api/3/issue/MP1-7"), Stub.log)
        self.assertEqual([p for p, _ in Stub.puts], ["/rest/api/3/issue/MP1-7"])
        self.assertEqual(Stub.puts[0][1], {"update": {"labels": [{"add": "s9-" + self.rid}]}})
        self.assertNotIn("POST", [mth for mth, _ in Stub.log], "이슈를 만들면 안 된다")

    def test_l2_404_rejects_and_leaves_the_doc(self):
        with self.assertRaises(ValueError) as cm:
            self.link("MP1-404")
        self.assertIn("404", str(cm.exception))
        self.assertIn("Issue does not exist", str(cm.exception))
        meta, body = self.doc(self.rid)
        self.assertFalse((meta.get("jira") or {}).get("key"))
        self.assertNotIn("연결", body)
        self.assertEqual(Stub.puts, [])

    def test_l3_prefix_must_match_project_key(self):
        Stub.exists["ZZ-3"] = ("To Do", "new")
        with self.assertRaises(ValueError) as cm:
            self.link("ZZ-3")
        self.assertIn("MP1", str(cm.exception))
        self.assertEqual(Stub.log, [], "접두가 다른데 Jira 를 불렀다")
        with self.assertRaises(ValueError):
            self.link("not a key")
        self.assertEqual(Stub.log, [])

    def test_l4_project_without_jira_is_rejected(self):
        rid = self.new_request(project="docs")
        with self.assertRaises(ValueError) as cm:
            self.link("MP1-7", doc_id=rid)
        self.assertIn("이 프로젝트에 Jira 연동이 없습니다", str(cm.exception))
        self.assertIn("Settings › 외부 서비스", str(cm.exception))
        self.assertEqual(Stub.log, [])

    def test_l5_unlink_clears_the_block_without_calling_jira(self):
        Stub.exists["MP1-7"] = ("To Do", "new")
        self.link("MP1-7")
        Stub.log, Stub.puts = [], []
        res = self.link("")
        self.assertTrue(res["ok"], res)
        meta, body = self.doc(self.rid)
        self.assertFalse((meta.get("jira") or {}).get("key"))
        self.assertFalse((meta.get("jira") or {}).get("url"))
        self.assertIn("jira: MP1-7 연결 끊음 (by hong", body)
        self.assertEqual(Stub.log, [], "끊기가 Jira 를 불렀다")
        self.assertNotIn(self.rid, [k for keys in self.m.jira_pull_targets().values() for k in keys.values()])

    def test_l6_linked_key_is_a_pull_target(self):
        Stub.exists["MP1-7"] = ("To Do", "new")
        self.link("MP1-7")
        self.assertEqual(self.m.jira_pull_targets().get("pay"), {"MP1-7": self.rid})

    def test_l7_label_failure_keeps_the_link(self):
        Stub.exists["MP1-8"] = ("To Do", "new")
        Stub.fail_put = 10
        res = self.m.do_set(self.rid, {"jira_key": "MP1-8"}, actor="hong", via="test",
                            jira_kw={"_sleep": lambda s: None})
        self.assertTrue(res["ok"], res)
        meta, _ = self.doc(self.rid)
        self.assertEqual(meta["jira"]["key"], "MP1-8")
        self.assertIn("s9-" + self.rid, meta["jira"]["last_error"])

    def test_l8_key_is_normalised_to_upper_case(self):
        Stub.exists["MP1-9"] = ("To Do", "new")
        self.link(" mp1-9 ")
        self.assertEqual(self.doc(self.rid)[0]["jira"]["key"], "MP1-9")


if __name__ == "__main__":
    unittest.main()
