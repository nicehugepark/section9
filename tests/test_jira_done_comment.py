"""닫는 전이의 처리 결과 → Jira 코멘트 (REQ-20260909-092) — 로컬 http.server 스텁이 Jira 노릇.

주인: 「Jira 의 상태가 done 으로 변경될 때는 처리 결과 역시 Jira 에 업데이트되어야 한다.」
done·cancelled 전이는 상태 push 행 다음에 result 행을 outbox 에 싣고, tick 이 전이 노트를
「완료: …」/「취소: …」 코멘트 한 건으로 보낸다. content=card 여도(상태 동기화의 일부),
멱등 키는 전이 시각(jira.result_ts → result_sent_ts), 비밀 모양은 안 보내고 last_error.

실행: python3 tests/ jira_done_comment
"""
import http.server
import importlib.machinery
import importlib.util
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
    posts = []
    comments = []

    def _send(self, st, body):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlsplit(self.path)
        if u.path == "/rest/api/3/search/jql":
            return self._send(200, {"issues": []})
        if u.path.endswith("/transitions"):
            return self._send(200, {"transitions": [
                {"id": "31", "name": "Done", "to": {"name": "Done", "statusCategory": {"key": "done"}}},
                {"id": "21", "name": "In Progress",
                 "to": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}}]})
        if u.path.startswith("/rest/api/3/issue/"):
            return self._send(200, {"fields": {"status": {"name": "To Do",
                                                          "statusCategory": {"key": "new"}}}})
        return self._send(404, {"errorMessages": ["no"]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Stub.posts.append((self.path, body))
        if self.path.endswith("/comment"):
            Stub.comments.append(body)
            return self._send(201, {"id": str(9000 + len(Stub.comments))})
        if self.path.endswith("/transitions"):
            return self._send(204, None)
        return self._send(201, {"id": "10001", "key": f"MP1-{len(Stub.posts)}"})

    def log_message(self, *a):
        pass


def adf_texts(body):
    return [c.get("text", "") for para in body["body"]["content"] for c in para.get("content", [])]


class JiraDoneComment(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.posts, Stub.comments = [], []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jdc-")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        os.environ.pop("S9_SESSION", None)
        name = "s9jdc_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.do_project_jira_set("pay", actor="hong", site=f"http://127.0.0.1:{self.port}",
                              project_key="MP1", content="card")      # card 가 기본 — D2
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

    def issued(self, title="환불 API"):
        import contextlib, io
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="환불을 돕는다", goal="환불이 된다",
            status="open", size="S", priority=None, user="hong", assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project="pay", project_tag=None, body="원문 SECRET-BODY-LINE 은 나가지 않는다",
            body_file=None, origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        rid = out.getvalue().split()[0]
        res = self.m.jira_issue_create(rid, actor="hong", manual=True, _sleep=self.slept.append)
        self.assertTrue(res["ok"], res)
        self.m.jira_outbox_write([])
        self.m.do_transition(rid, "in-progress", note="착수", user="hong")
        self.m.jira_outbox_write([])
        Stub.posts, Stub.comments = [], []
        return rid, res["key"]

    def go(self, rid, status, note, **kw):
        self.m.do_transition(rid, status, note=note, user="hong", **kw)

    def tick(self, **kw):
        return self.m.jira_outbox_tick(_sleep=self.slept.append, **kw)

    def doc(self, rid):
        return self.m.read_doc(self.m.find_path(rid))

    def test_d1_done_sends_the_transition_note_as_one_comment(self):
        rid, key = self.issued()
        self.go(rid, "done", "환불 API 가 붙었다 — 시험 5건 통과")
        self.assertEqual([r["kind"] for r in self.m.jira_outbox_read()], ["push", "result"])
        self.assertEqual(self.tick(), [(rid, True), (rid, True)])
        paths = [p for p, _ in Stub.posts]
        self.assertEqual(paths, [f"/rest/api/3/issue/{key}/transitions",
                                 f"/rest/api/3/issue/{key}/comment"], "상태가 먼저, 결과가 다음")
        texts = adf_texts(Stub.comments[0])
        self.assertEqual(texts[0], "완료: 환불 API 가 붙었다 — 시험 5건 통과")
        self.assertTrue(texts[-1].startswith("— section9 · "), texts)
        meta, body = self.doc(rid)
        ts = meta["jira"]["result_ts"]
        self.assertEqual(meta["jira"]["result_sent_ts"], ts)
        self.assertIn(f"jira: {key} 처리 결과 코멘트 (완료, ts {ts})", body)
        self.assertEqual(self.m.jira_outbox_read(), [])

    def test_d2_content_card_still_sends_the_result(self):
        rid, key = self.issued()
        self.assertEqual(self.m.project_jira("pay").get("content", "card"), "card")
        self.go(rid, "done", "card 프로젝트의 완료 근거")
        self.tick()
        self.assertEqual(len(Stub.comments), 1)
        self.assertEqual(adf_texts(Stub.comments[0])[0], "완료: card 프로젝트의 완료 근거")
        sent = json.dumps(Stub.comments[0], ensure_ascii=False)
        self.assertNotIn("SECRET-BODY-LINE", sent, "원문이 코멘트로 나갔다")

    def test_d3_the_same_done_goes_once_a_new_done_goes_again(self):
        rid, key = self.issued()
        self.go(rid, "done", "첫 완료")
        self.tick()
        self.assertEqual(len(Stub.comments), 1)
        self.assertTrue(self.m.jira_outbox_add(rid, "result"), "행을 다시 실어도")
        self.assertEqual(self.tick(), [(rid, True)])
        self.assertEqual(len(Stub.comments), 1, "같은 done 이 두 번 나갔다")
        # 되돌렸다가 다시 done — 새 시각이라 새 코멘트
        self.go(rid, "in-progress", "되돌림", force=True)
        real = self.m.now_iso
        self.m.now_iso = lambda: "2099-01-01T00:00:00+09:00"
        try:
            self.go(rid, "done", "두 번째 완료")
        finally:
            self.m.now_iso = real
        self.tick()
        self.assertEqual(len(Stub.comments), 2)
        self.assertEqual(adf_texts(Stub.comments[1])[0], "완료: 두 번째 완료")
        self.assertEqual(adf_texts(Stub.comments[1])[-1], "— section9 · 2099-01-01T00:00:00+09:00")

    def test_d4_mark_off_drops_the_signature(self):
        rid, key = self.issued()
        self.m.do_project_jira_set("pay", actor="hong", mark="off")
        self.go(rid, "done", "서명 없는 완료")
        self.tick()
        self.assertEqual(adf_texts(Stub.comments[0]), ["완료: 서명 없는 완료"])

    def test_d5_pull_direction_sends_nothing(self):
        rid, key = self.issued()
        self.m.do_project_jira_set("pay", actor="hong", direction="pull")
        # 앞선(push 이던) 전이가 남긴 표는 그대로다 — 여기서 보는 것은 **이번
        # 전이가 아무것도 싣지 않는다**이다 (REQ-20260912-001: 코멘트가 모든
        # 전이로 넓어진 뒤로 이 칸은 처음부터 비어 있지 않다).
        was = (self.doc(rid)[0].get("jira") or {}).get("result_ts", "")
        self.go(rid, "done", "pull 인 프로젝트의 완료")
        self.assertEqual(self.m.jira_outbox_read(), [])
        self.assertEqual(self.tick(), [])
        self.assertEqual(Stub.comments, [])
        self.assertEqual((self.doc(rid)[0].get("jira") or {}).get("result_ts", ""),
                         was, "pull 인데 이번 전이가 보낼 것을 실었다")

    def test_d6_a_secret_shape_is_held_back_with_a_reason(self):
        rid, key = self.issued()
        self.go(rid, "done", "토큰은 " + "ghp_" + "x" * 24 + " 입니다")
        self.assertEqual(self.tick(), [(rid, True), (rid, True)])
        self.assertEqual(Stub.comments, [], "비밀 모양이 나갔다")
        meta, body = self.doc(rid)
        self.assertIn("비밀 모양이 있어 보내지 않았다", meta["jira"]["last_error"])
        self.assertIn("처리 결과 안 보냄", body)
        self.assertEqual(self.m.jira_outbox_read(), [], "다시 시도한다 — 그 전이는 처리된 것이다")

    def test_d7_cancelled_is_symmetric(self):
        rid, key = self.issued()
        self.go(rid, "cancelled", "다른 요청이 이미 이뤘다")
        self.tick()
        self.assertEqual(len(Stub.comments), 1)
        self.assertEqual(adf_texts(Stub.comments[0])[0], "취소: 다른 요청이 이미 이뤘다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
