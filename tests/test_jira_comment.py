"""notes → Jira 코멘트 (REQ-20260909-034) — 로컬 http.server 스텁이 Jira 노릇을 한다.

프로젝트 jira.content=notes 일 때만, 보내는 label(JIRA_COMMENT_LABELS: response·빈 label)의
노트가 outbox(kind=comment)를 지나 POST /rest/api/3/issue/{key}/comment 로 간다. 멱등 키는
노트 ts(+본문 지문), 코멘트 끝에 「— section9」. 비밀 모양은 안 보내고 last_error 에 사유,
자취는 문서 History 한 줄 + state/jira/outbound.jsonl(내용 없이 식별자만).

실행: python3 tests/ jira_comment
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
    posts = []          # (path, body)
    comments = []       # 받은 코멘트 body
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
            return self._send(200, {"issues": []})
        if u.path.startswith("/rest/api/3/issue/"):
            return self._send(200, {"fields": {"status": {"name": "To Do"}}})
        return self._send(404, {"errorMessages": ["no"]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        Stub.log.append(("POST", self.path))
        Stub.posts.append((self.path, body))
        if self.path.endswith("/comment"):
            Stub.comments.append(body)
            return self._send(201, {"id": str(9000 + len(Stub.comments))})
        return self._send(201, {"id": "10001", "key": f"MP1-{len(Stub.posts)}"})

    def log_message(self, *a):
        pass


def adf_texts(body):
    return [c.get("text", "") for para in body["body"]["content"] for c in para.get("content", [])]


class JiraComment(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.posts, Stub.comments, Stub.log = [], [], []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jcm-")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        os.environ.pop("S9_SESSION", None)
        name = "s9jcm_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.do_project_jira_set("pay", actor="hong", site=f"http://127.0.0.1:{self.port}",
                              project_key="MP1", content="notes")
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

    def new_request(self, title="환불 API"):
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
        return out.getvalue().split()[0]

    def issued(self, title="환불 API"):
        """이슈까지 선 요청 — 생성 훅이 실은 create 행은 손으로 만들었으니 비운다."""
        rid = self.new_request(title)
        res = self.m.jira_issue_create(rid, actor="hong", manual=True, _sleep=self.slept.append)
        self.assertTrue(res["ok"], res)
        self.m.jira_outbox_write([])
        Stub.posts, Stub.log = [], []
        return rid, res["key"]

    def note(self, rid, text, label="response"):
        import contextlib, io
        args = types.SimpleNamespace(id=rid, text=text, file=None, attach=[], label=label,
                                     user="hong", agent="", item="", result="", transcript="",
                                     started="", anchor="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_note(args)
        return out.getvalue()

    def tick(self, **kw):
        return self.m.jira_outbox_tick(_sleep=self.slept.append, **kw)

    def doc(self, rid):
        return self.m.read_doc(self.m.find_path(rid))

    def test_s1_a_response_note_becomes_one_comment(self):
        rid, key = self.issued()
        self.note(rid, "구현을 마쳤습니다.\n시험 5건 통과.")
        self.assertEqual(Stub.log, [], "노트가 Jira 를 바로 불렀다 — outbox 를 지나야 한다")
        self.assertEqual([(r["id"], r["kind"]) for r in self.m.jira_outbox_read()], [(rid, "comment")])
        done = self.tick()
        self.assertEqual(done, [(rid, True)])
        self.assertEqual(Stub.log, [("POST", f"/rest/api/3/issue/{key}/comment")])
        texts = adf_texts(Stub.comments[0])
        self.assertEqual(texts[:2], ["구현을 마쳤습니다.", "시험 5건 통과."])
        self.assertTrue(texts[-1].startswith("— section9"), texts)
        meta, _ = self.doc(rid)
        ts = self.m.jira_notes_of(self.doc(rid)[1])[-1][0]
        self.assertEqual(meta["jira"]["commented_ts"], ts)
        self.assertEqual(self.m.jira_outbox_read(), [])

    def test_s2_the_same_note_is_never_sent_twice(self):
        rid, key = self.issued()
        self.note(rid, "첫 보고")
        self.tick()
        self.assertEqual(len(Stub.comments), 1)
        self.tick()
        self.assertTrue(self.m.jira_outbox_add(rid, "comment"), "행을 다시 실어도")
        self.assertEqual(self.tick(), [(rid, True)])
        self.assertEqual(len(Stub.comments), 1, "같은 노트가 두 번 나갔다")
        # 새 노트는 나간다 — 커서가 앞의 것만 막는다
        self.note(rid, "두 번째 보고")
        self.tick()
        self.assertEqual(len(Stub.comments), 2)
        self.assertEqual(adf_texts(Stub.comments[1])[0], "두 번째 보고")

    def test_s3_a_secret_shape_is_held_back_with_a_reason(self):
        rid, key = self.issued()
        self.note(rid, "토큰은 " + "ghp_" + "x" * 24 + " 입니다")
        self.assertEqual(self.tick(), [(rid, True)])
        self.assertEqual(Stub.comments, [], "비밀 모양이 나갔다")
        meta, body = self.doc(rid)
        self.assertIn("비밀 모양이 있어 보내지 않았다", meta["jira"]["last_error"])
        self.assertIn("코멘트 안 보냄", body)
        self.assertEqual(self.tick(), [], "다시 시도했다 — 그 노트는 처리된 것이다")

    def test_s4_boundaries_label_content_and_missing_key(self):
        rid, key = self.issued()
        with self.subTest("machine_labels_stay_home"):
            for label in ("tdd", "subagent", "audit"):
                self.note(rid, f"{label} 기록 - [ ] S1", label=label)
            self.assertEqual(self.m.jira_outbox_read(), [])
            self.tick()
            self.assertEqual(Stub.comments, [])
        with self.subTest("a_plain_human_note_goes"):
            self.note(rid, "사람이 그냥 적은 메모", label="")
            self.assertEqual(self.tick(), [(rid, True)])
            self.assertEqual(len(Stub.comments), 1)
        with self.subTest("content_card_sends_nothing"):
            self.m.do_project_jira_set("pay", actor="hong", content="card")
            self.note(rid, "card 인 동안의 보고")
            self.assertEqual(self.m.jira_outbox_read(), [])
            self.m.do_project_jira_set("pay", actor="hong", content="notes")
        with self.subTest("no_key_yet_is_deferred_not_dropped"):
            Stub.comments = []
            rid2 = self.new_request("두 번째")          # 훅이 pending=create 로 실었다
            self.m.jira_outbox_write([])                 # 생성이 아직 안 된 상태를 만든다
            self.assertEqual(self.doc(rid2)[0]["jira"]["pending"], "create")
            self.note(rid2, "이슈보다 먼저 온 보고")
            rows = self.m.jira_outbox_read()
            self.assertEqual([r["kind"] for r in rows], ["comment"])
            import time
            now = time.time() + 1
            self.assertEqual(self.tick(now=now), [(rid2, False)])
            rows = self.m.jira_outbox_read()
            self.assertEqual((rows[0]["kind"], rows[0]["attempts"]), ("comment", 1))
            self.assertIn("이슈가 아직 없다", rows[0]["last_error"])
            self.assertEqual(Stub.comments, [])
            res = self.m.jira_issue_create(rid2, actor="hong", manual=True, _sleep=self.slept.append)
            self.assertTrue(res["ok"], res)
            self.assertEqual(self.tick(now=now + 31), [(rid2, True)])
            self.assertEqual(len(Stub.comments), 1)
            self.assertEqual(adf_texts(Stub.comments[0])[0], "이슈보다 먼저 온 보고")

    def test_s5_regression_the_trail_is_written_without_the_content(self):
        rid, key = self.issued()
        self.note(rid, "자취를 남길 보고 TRAIL-BODY")
        self.tick()
        meta, body = self.doc(rid)
        ts = meta["jira"]["commented_ts"]
        self.assertIn(f"jira: {key} 코멘트 (ts {ts})", body)
        path = os.path.join(self.root, "state", "jira", "outbound.jsonl")
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(ln) for ln in f if ln.strip()]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["doc"], rows[0]["key"], rows[0]["kind"], rows[0]["note_ts"]),
                         (rid, key, "comment", ts))
        self.assertNotIn("TRAIL-BODY", open(path, encoding="utf-8").read())
        sent = json.dumps(Stub.comments[0], ensure_ascii=False)
        self.assertNotIn("SECRET-BODY-LINE", sent, "원문이 코멘트로 나갔다")

    def test_s6_regression_the_note_survives_a_broken_hook(self):
        rid, key = self.issued()
        self.m.project_jira = lambda slug: (_ for _ in ()).throw(RuntimeError("boom"))
        out = self.note(rid, "훅이 실패해도 남는 노트")
        self.assertIn("note appended", out)
        self.assertIn("훅이 실패해도 남는 노트", self.doc(rid)[1])
        self.assertEqual(self.m.jira_outbox_read(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
