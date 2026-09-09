"""요청 → Jira 이슈 (REQ-20260908-073) — 로컬 http.server 스텁이 Jira 노릇을 한다.

문서의 `jira:` 가 진실이고, 만드는 길은 `s9 jira create <REQ>`(사람이 시킨 것)과
outbox 를 비우는 워처 틱 둘이다. 규칙: 사람이 직접 만든 요청만(export_origin human) ·
label s9-<REQ> 로 멱등 · 실패해도 요청은 그대로이고 outbox 로 간다 · 본문은 나가지
않는다.

실행: python3 tests/ jira_create
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
    found = []          # 검색이 돌려줄 key 목록
    fail_post = 0       # POST 를 이만큼 5xx 로
    posts = []          # 받은 POST body
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
        if u.path == "/rest/api/3/search/jql":
            return self._send(200, {"issues": [{"key": k} for k in Stub.found]})
        if u.path.startswith("/rest/api/3/issue/"):
            return self._send(200, {"fields": {"status": {"name": "To Do"}}})
        return self._send(404, {"errorMessages": ["no"]})

    puts = []

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Stub.log.append(("PUT", self.path))
        Stub.puts.append((self.path, body))
        return self._send(204, None)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Stub.log.append(("POST", self.path))
        Stub.posts.append(body)
        if Stub.fail_post > 0:
            Stub.fail_post -= 1
            return self._send(503, {"errorMessages": ["down"]})
        return self._send(201, {"id": "10001", "key": f"MP1-{len(Stub.posts)}"})

    def log_message(self, *a):
        pass


class JiraCreate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.found, Stub.fail_post, Stub.posts, Stub.log = [], 0, [], []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jc-")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        os.environ.pop("S9_SESSION", None)
        name = "s9jc_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.do_project_jira_set("pay", actor="hong", site=f"http://127.0.0.1:{self.port}",
                              project_key="MP1")
        m.do_user_config_set("hong", "jira_site", f"http://127.0.0.1:{self.port}")
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        m.secret_write("hong", m.JIRA_SECRET_KEY, "fake-token-for-the-stub-0123456789")
        self.slept = []

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def new_request(self, origin="human", size="S", title="환불 API"):
        """요청 문서 하나 — cmd_new 를 지나야 훅(outbox)까지 잰다."""
        import contextlib, io, types
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="환불을 돕는다", goal="환불이 된다",
            status="open", size=size, priority=None, user="hong", assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project="pay", project_tag=None, body="비밀스러운 본문 SECRET-BODY-LINE",
            body_file=None, origin=origin, agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def doc(self, doc_id):
        meta, body = self.m.read_doc(self.m.find_path(doc_id))
        return meta, body

    def create(self, doc_id, **kw):
        return self.m.jira_issue_create(doc_id, actor="hong", manual=True,
                                        _sleep=self.slept.append, **kw)

    def test_c1_manual_create_writes_the_block(self):
        rid = self.new_request()
        res = self.create(rid)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["key"], "MP1-1")
        meta, body = self.doc(rid)
        j = meta["jira"]
        self.assertEqual((j["key"], j["status"], j["synced_by"], j["pending"]),
                         ("MP1-1", "To Do", "s9", ""))
        self.assertTrue(j["url"].endswith("/browse/MP1-1"))
        self.assertIn("jira: 이슈 MP1-1 생성", body)
        f = Stub.posts[0]["fields"]
        self.assertEqual(f["project"]["key"], "MP1")
        self.assertEqual(f["labels"], ["s9-" + rid])
        self.assertTrue(f["summary"].startswith(f"[{rid}] "))

    def test_c2_idempotent_by_key_and_by_label(self):
        rid = self.new_request()
        self.create(rid)
        Stub.log = []
        res = self.create(rid)
        self.assertTrue(res["ok"] and res["skipped"])
        self.assertEqual(Stub.log, [], "key 가 있는데 Jira 를 불렀다")
        rid2 = self.new_request(title="두 번째")
        Stub.found = ["MP1-77"]
        res = self.create(rid2)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["key"], "MP1-77")
        self.assertTrue(res.get("adopted"))
        self.assertNotIn(("POST", "/rest/api/3/issue"), Stub.log)

    def test_c3_only_human_requests_by_default(self):
        rid = self.new_request(origin="agent")
        meta, _ = self.doc(rid)
        j, why = self.m.jira_export_wanted(meta)
        self.assertIn("사람이 직접 만든 요청만", why)
        self.assertFalse(self.m.jira_outbox_read(), "agent 요청이 outbox 에 실렸다")
        self.assertTrue(self.create(rid)["ok"], "s9 jira create 는 사람이 시킨 것이라 지나간다")
        self.m.do_project_jira_set("pay", actor="hong", export="size:M+")
        rid_s = self.new_request(size="S", title="작은 것")
        self.assertIn("size:M+", self.m.jira_export_wanted(self.doc(rid_s)[0])[1])
        rid_m = self.new_request(size="M", title="중간 것")
        self.assertEqual(self.m.jira_export_wanted(self.doc(rid_m)[0])[1], "")

    def test_c4_failure_keeps_the_request_and_the_watcher_retries(self):
        Stub.fail_post = 6          # 손 시도 3회 + 첫 틱 3회 전부 5xx, 둘째 틱에서 성공
        rid = self.new_request()
        res = self.create(rid)
        self.assertFalse(res["ok"])
        meta, _ = self.doc(rid)
        self.assertEqual(meta["jira"]["pending"], "create")
        self.assertTrue(meta["jira"]["last_error"])
        rows = self.m.jira_outbox_read()
        self.assertEqual([r["id"] for r in rows], [rid])
        import time
        now = time.time() + 1           # outbox 의 next_at 은 실제 시각이다
        done = self.m.jira_outbox_tick(now=now, _sleep=self.slept.append)
        self.assertEqual(done, [(rid, False)])
        rows = self.m.jira_outbox_read()
        self.assertEqual(rows[0]["attempts"], 1)
        self.assertEqual(rows[0]["next_at"], now + 30)
        self.assertEqual(self.m.jira_outbox_tick(now=now + 10, _sleep=self.slept.append), [],
                         "때가 안 됐는데 다시 시도했다")
        done = self.m.jira_outbox_tick(now=now + 31, _sleep=self.slept.append)
        self.assertEqual(done, [(rid, True)])
        self.assertEqual(self.m.jira_outbox_read(), [])
        meta, _ = self.doc(rid)
        self.assertEqual((meta["jira"]["key"], meta["jira"]["pending"]), ("MP1-7", ""))   # 스텁은 POST 횟수로 번호를 매긴다

    def test_c5_missing_token_calls_nothing(self):
        self.m.secret_remove("hong", self.m.JIRA_SECRET_KEY)
        rid = self.new_request()
        res = self.create(rid)
        self.assertFalse(res["ok"])
        self.assertIn("@hong 의 준비물이 없다", res["error"])
        self.assertIn("API token", res["error"])
        self.assertEqual(Stub.log, [])
        self.assertEqual(self.doc(rid)[0]["jira"]["pending"], "create")

    def test_c6_the_body_never_leaves(self):
        rid = self.new_request()
        self.create(rid)
        sent = json.dumps(Stub.posts[0], ensure_ascii=False)
        self.assertNotIn("SECRET-BODY-LINE", sent)
        self.assertNotIn("fake-token", sent)
        self.assertIn("환불을 돕는다", sent)
        self.assertIn("환불이 된다", sent)

    def test_c7_new_request_hook_queues_without_network(self):
        rid = self.new_request()
        self.assertEqual(Stub.log, [], "요청 생성이 Jira 를 불렀다")
        meta, _ = self.doc(rid)
        self.assertEqual(meta["jira"]["pending"], "create")
        self.assertEqual([r["id"] for r in self.m.jira_outbox_read()], [rid])
        done = self.m.jira_outbox_tick(_sleep=self.slept.append)
        self.assertEqual(done, [(rid, True)])
        self.assertEqual(self.doc(rid)[0]["jira"]["key"], "MP1-1")


class JiraTitleHold(JiraCreate):
    """제목이 정리된 뒤에 이슈가 선다 · 제목이 바뀌면 summary 를 맞춘다 (REQ-20260909-032)."""

    def raw_request(self):
        """훅이 만든 카드처럼 — 제목이 원문 앞 24자 절단(…)이고 auto-audit 표."""
        import contextlib, io, types
        text = "지라 티켓 발행은 잘 되는데 제목이 원문 그대로 올라간다 — 정리된 뒤에 등록되면 좋겠다"
        args = types.SimpleNamespace(
            doc_type="request", title=text[:24] + "…", summary="", goal="정리된 제목으로 이슈",
            status="open", size="S", priority=None, user="hong", assignee=None,
            tag_list=["auto-audit"], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project="pay", project_tag=None, body=text, body_file=None, origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def test_n1_n2_raw_title_waits_for_the_cleaned_title(self):
        rid = self.raw_request()
        self.assertEqual(self.m.jira_outbox_read(), [], "원문 제목인데 outbox 에 실렸다")
        meta, body = self.doc(rid)
        self.assertIn("제목이 원문 그대로", self.m.jira_export_wanted(meta, body=body)[1])
        self.m.do_set(rid, {"title": "이슈 제목 정리"}, actor="hong")
        self.assertEqual([r["kind"] for r in self.m.jira_outbox_read()], ["create"])
        done = self.m.jira_outbox_tick(_sleep=self.slept.append)
        self.assertEqual(done, [(rid, True)])
        self.assertTrue(Stub.posts[-1]["fields"]["summary"].endswith("] 이슈 제목 정리"))
        # description 첫 문단은 완료 기준
        first = Stub.posts[-1]["fields"]["description"]["content"][0]["content"][0]["text"]
        self.assertTrue(first.startswith("완료 기준:"), first)

    def test_n2b_a_raw_title_cannot_even_start(self):
        """전이 규칙(REQ-20260825-042)이 먼저 선다 — 원문 제목은 in-progress 로 못 간다.
        그래서 이슈는 언제나 정리된 제목으로 선다; late 경로는 그 규칙이 풀릴 때의 안전망이다."""
        rid = self.raw_request()
        with self.assertRaises(ValueError) as cm:
            self.m.do_transition(rid, "in-progress", note="착수", user="hong")
        self.assertIn("제목이 원문 그대로", str(cm.exception))
        self.assertEqual(self.m.jira_outbox_read(), [])

    def test_n3_a_changed_title_updates_the_issue_summary(self):
        rid = self.new_request()
        self.create(rid)
        self.m.jira_outbox_write([])          # 생성 훅이 실은 create 는 이미 손으로 만들었다
        Stub.log, Stub.puts = [], []
        self.m.do_set(rid, {"title": "환불 API (개정)"}, actor="hong")
        self.assertEqual([r["kind"] for r in self.m.jira_outbox_read()], ["title"])
        done = self.m.jira_outbox_tick(_sleep=self.slept.append)
        self.assertEqual(done, [(rid, True)])
        self.assertEqual(Stub.puts[-1][1]["fields"]["summary"], f"[{rid}] 환불 API (개정)")
        self.assertIn("제목 맞춤", self.doc(rid)[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
