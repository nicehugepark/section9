"""Jira 에 section9 표를 남길지 (REQ-20260909-049) — 로컬 http.server 스텁이 Jira 노릇을 한다.

프로젝트 jira.mark=on(기본)|off. 표는 넷 — 생성 라벨 s9-<id> · description 의
「section9 요청 <id>」 줄 · 코멘트 끝 「— section9 · ts」 · 잇기 때 붙이는 라벨. off 면 넷 다
나가지 않고, 라벨로 기존 이슈를 찾는 검색(jira_find_issue)도 하지 않는다(문서의 jira.key 가
곧 기록). 판정은 jira_mark_on(j) 한 곳.

실행: python3 tests/ jira_mark
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
import types
import unittest
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class Stub(http.server.BaseHTTPRequestHandler):
    log = []            # (method, path)
    posts = []          # (path, body)
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
        if u.path == "/rest/api/3/search/jql":
            return self._send(200, {"issues": []})
        if u.path.startswith("/rest/api/3/issue/"):
            return self._send(200, {"key": u.path.rsplit("/", 1)[1], "fields": {
                "summary": "저쪽 제목", "status": {"name": "To Do", "statusCategory": {"key": "new"}}}})
        return self._send(404, {"errorMessages": ["no"]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Stub.log.append(("POST", self.path))
        Stub.posts.append((self.path, body))
        if self.path.endswith("/comment"):
            return self._send(201, {"id": str(9000 + len(Stub.posts))})
        return self._send(201, {"id": "10001", "key": f"MP1-{len(Stub.posts)}"})

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Stub.log.append(("PUT", self.path))
        Stub.puts.append((self.path, body))
        return self._send(204, None)

    def log_message(self, *a):
        pass


def adf_texts(adf):
    return [c.get("text", "") for para in adf["content"] for c in para.get("content", [])]


class JiraMark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.log, Stub.posts, Stub.puts = [], [], []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jmk-")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        os.environ.pop("S9_SESSION", None)
        name = "s9jmk_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        self.site = f"http://127.0.0.1:{self.port}"
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.do_project_jira_set("pay", actor="hong", site=self.site, project_key="MP1",
                              content="notes", export="manual")
        m.do_user_config_set("hong", "jira_site", self.site)
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

    # ── 도우미 ──────────────────────────────────────────────────────────────
    def mark(self, value):
        self.m.do_project_jira_set("pay", actor="hong", mark=value)

    def new_request(self, title="환불 API"):
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="환불을 돕는다", goal="환불이 된다",
            status="open", size="S", priority=None, user="hong", assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project="pay", project_tag=None, body="원문은 나가지 않는다", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        rid = out.getvalue().split()[0]
        self.m.jira_outbox_write([])
        Stub.log, Stub.posts, Stub.puts = [], [], []
        return rid

    def create(self, rid):
        return self.m.jira_issue_create(rid, actor="hong", manual=True, _sleep=self.slept.append)

    def note(self, rid, text):
        args = types.SimpleNamespace(id=rid, text=text, file=None, attach=[], label="response",
                                     user="hong", agent="", item="", result="", transcript="",
                                     started="", anchor="")
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_note(args)

    def doc(self, rid):
        return self.m.read_doc(self.m.find_path(rid))

    def issue_fields(self):
        posts = [b for p, b in Stub.posts if p == "/rest/api/3/issue"]
        self.assertEqual(len(posts), 1, Stub.log)
        return posts[0]["fields"]

    def comment_texts(self):
        cs = [b for p, b in Stub.posts if p.endswith("/comment")]
        self.assertEqual(len(cs), 1, Stub.log)
        return adf_texts(cs[0]["body"])

    # ── 시나리오 ────────────────────────────────────────────────────────────
    def test_s1_default_on_keeps_label_line_and_signature(self):
        self.assertEqual(self.m.project_jira("pay")["mark"], "on")
        self.assertTrue(self.m.jira_mark_on(self.m.project_jira("pay")))
        rid = self.new_request()
        res = self.create(rid)
        self.assertTrue(res["ok"], res)
        self.assertIn(("GET", "/rest/api/3/search/jql"), Stub.log, "라벨 검색을 먼저 한다")
        f = self.issue_fields()
        self.assertEqual(f["labels"], ["s9-" + rid])
        texts = adf_texts(f["description"])
        self.assertIn(f"section9 요청 {rid}", texts)
        self.assertEqual(texts[0], "완료 기준: 환불이 된다")
        self.note(rid, "구현을 마쳤습니다.")
        self.assertEqual(self.m.jira_outbox_tick(_sleep=self.slept.append), [(rid, True)])
        texts = self.comment_texts()
        self.assertEqual(texts[0], "구현을 마쳤습니다.")
        self.assertTrue(texts[-1].startswith("— section9 · "), texts)

    def test_s2_off_sends_no_label_and_no_section9_line(self):
        self.mark("off")
        self.assertFalse(self.m.jira_mark_on(self.m.project_jira("pay")))
        rid = self.new_request()
        res = self.create(rid)
        self.assertTrue(res["ok"], res)
        f = self.issue_fields()
        self.assertNotIn("labels", f, f)
        texts = adf_texts(f["description"])
        self.assertFalse(any("section9" in t for t in texts), texts)
        self.assertFalse(any(rid in t for t in texts), texts)
        self.assertEqual(texts, ["완료 기준: 환불이 된다", "요약: 환불을 돕는다",
                                 "담당: hong · 크기: S · 상태: open"])
        self.assertEqual(f["summary"], "환불 API")
        meta, _ = self.doc(rid)
        self.assertEqual(meta["jira"]["key"], "MP1-1", "문서의 jira.key 가 곧 기록이다")

    def test_s3_off_comment_has_no_signature(self):
        self.mark("off")
        rid = self.new_request()
        self.assertTrue(self.create(rid)["ok"])
        Stub.posts = []
        self.note(rid, "구현을 마쳤습니다.\n시험 5건 통과.")
        self.assertEqual(self.m.jira_outbox_tick(_sleep=self.slept.append), [(rid, True)])
        texts = self.comment_texts()
        self.assertEqual(texts, ["구현을 마쳤습니다.", "시험 5건 통과."])
        self.assertFalse(any("section9" in t for t in texts), texts)

    def test_s4_off_link_puts_no_label(self):
        rid = self.new_request()
        res = self.m.do_set(rid, {"jira_key": "MP1-7"}, actor="hong", via="test")
        self.assertTrue(res["ok"], res)
        self.assertEqual([p for p, _ in Stub.puts], ["/rest/api/3/issue/MP1-7"], "on 이면 라벨을 붙인다")
        self.mark("off")
        rid2 = self.new_request(title="두 번째")
        res = self.m.do_set(rid2, {"jira_key": "MP1-8"}, actor="hong", via="test")
        self.assertTrue(res["ok"], res)
        self.assertEqual(Stub.puts, [], "off 인데 라벨 PUT 이 나갔다")
        self.assertIn(("GET", "/rest/api/3/issue/MP1-8"), Stub.log, "이슈 존재 확인은 그대로 한다")
        meta, _ = self.doc(rid2)
        self.assertEqual(meta["jira"]["key"], "MP1-8")
        self.assertEqual(meta["jira"]["last_error"], "")

    def test_s5_off_skips_the_label_search(self):
        self.mark("off")
        rid = self.new_request()
        meta, _ = self.doc(rid)
        j = self.m.project_jira("pay")
        self.assertEqual(self.m.jira_find_issue("hong", j, rid), (200, ""))
        self.assertEqual(Stub.log, [], "off 인데 검색을 했다")
        res = self.create(rid)
        self.assertTrue(res["ok"], res)
        self.assertFalse(res.get("adopted"))
        self.assertNotIn(("GET", "/rest/api/3/search/jql"), Stub.log)
        self.assertIn(("POST", "/rest/api/3/issue"), Stub.log, "키가 없으니 새로 만든다")
        Stub.log = []
        res = self.create(rid)
        self.assertTrue(res["ok"] and res["skipped"], res)
        self.assertEqual(Stub.log, [], "키가 있으면 Jira 를 부르지 않는다")

    def test_s6_value_is_validated_and_carried(self):
        with self.assertRaises(ValueError) as cm:
            self.mark("maybe")
        self.assertIn("mark", str(cm.exception))
        self.assertIn("on | off", str(cm.exception))
        self.assertEqual(self.m.project_jira("pay")["mark"], "on", "거절은 값을 남기지 않는다")
        self.mark("off")
        self.assertEqual(self.m.project_jira("pay")["mark"], "off")
        st = self.m.jira_state("hong")
        self.assertEqual([p["mark"] for p in st["projects"]], ["off"])
        payload = self.m.projects_data()
        pay = [p for p in payload["projects"] if p["slug"] == "pay"][0]
        self.assertEqual(pay["jira"]["mark"], "off")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_project(types.SimpleNamespace(
                action="jira", slug="pay", member_action="show", user="hong"))
        self.assertRegex(out.getvalue(), r"mark\s+off")

    # S7(화면 글자 검사)은 뺐다 — 소스 글자 계약은 시험 예산이 막는다(REQ-20260909-051);
    # 화면 사전은 test_project_screen 이, select 의 동작은 맥 Safari 검증이 잰다.



if __name__ == "__main__":
    unittest.main()
