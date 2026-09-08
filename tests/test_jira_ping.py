"""`s9 jira ping` — 연결 확인 (REQ-20260908-071).

로컬 http.server 스텁이 Jira 노릇을 한다. 재는 것: 준비가 모자라면 부르지 않는다 ·
200 이면 이름을 돌려준다 · 401 은 한 번만 · 429 는 Retry-After 뒤 한 번 더 ·
5xx 는 backoff 로 세 번 · bearer 분기 · 토큰이 어디에도 안 실린다.

실행: python3 tests/ jira_ping
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

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
TOKEN = "fake-token-value-for-the-stub-1234567890"   # 진짜 꼴(ATATT3…)이면 guard 의 비밀 검사가 commit 을 막는다 — 맞는 일이다


class Stub(http.server.BaseHTTPRequestHandler):
    plan = []          # 순서대로 낼 (status, body|None, headers)
    seen = []          # (path, Authorization)

    def do_GET(self):
        Stub.seen.append((self.path, self.headers.get("Authorization", "")))
        st, body, hdr = Stub.plan.pop(0) if Stub.plan else (200, {"displayName": "홍길동", "emailAddress": "hong@example.com"}, {})
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(st)
        for k, v in hdr.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


class JiraPing(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.plan, Stub.seen = [], []
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER")}
        self.root = tempfile.mkdtemp(prefix="s9jping-")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        name = "s9jping_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.slept = []

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def ready(self, auth=None):
        m = self.m
        m.do_user_config_set("hong", "jira_site", f"http://127.0.0.1:{self.port}")
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        if auth:
            m.do_user_config_set("hong", "jira_auth", auth)
        m.secret_write("hong", m.JIRA_SECRET_KEY, TOKEN)

    def ping(self):
        return self.m.jira_ping("hong", _sleep=self.slept.append)

    def test_p1_ok_returns_the_name(self):
        self.ready()
        res = self.ping()
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["name"], "홍길동")
        self.assertEqual(Stub.seen[0][0], "/rest/api/3/myself")
        self.assertTrue(Stub.seen[0][1].startswith("Basic "))

    def test_p2_missing_pieces_are_named_and_nothing_is_called(self):
        self.m.do_user_config_set("hong", "jira_site", f"http://127.0.0.1:{self.port}")
        res = self.ping()
        self.assertFalse(res["ok"])
        self.assertEqual(res["missing"], ["Atlassian 이메일", "API token"])
        self.assertEqual(Stub.seen, [])

    def test_p3_401_is_asked_once_and_guides(self):
        self.ready()
        Stub.plan = [(401, {"errorMessages": ["x"]}, {})]
        res = self.ping()
        self.assertFalse(res["ok"])
        self.assertEqual(len(Stub.seen), 1, "401 인데 다시 물었다")
        self.assertIn("재시도하지 않습니다", res["error"])

    def test_p4_429_waits_and_5xx_backs_off_three_times(self):
        self.ready()
        Stub.plan = [(429, None, {"Retry-After": "3"})]
        res = self.ping()
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.slept, [3])
        Stub.plan, Stub.seen, self.slept[:] = [(503, None, {})] * 5, [], []
        res = self.ping()
        self.assertFalse(res["ok"])
        self.assertEqual(len(Stub.seen), self.m.JIRA_RETRY_MAX)
        self.assertEqual(self.slept, [1, 2])

    def test_p5_bearer_for_data_center(self):
        self.ready(auth="bearer")
        res = self.ping()
        self.assertTrue(res["ok"], res)
        self.assertEqual(Stub.seen[0][1], "Bearer " + TOKEN)

    def test_p6_the_token_never_shows(self):
        self.ready()
        Stub.plan = [(401, None, {}), (500, None, {}), (500, None, {}), (500, None, {})]
        for _ in range(2):
            res = self.ping()
            self.assertNotIn(TOKEN, json.dumps(res, ensure_ascii=False))
        self.assertNotIn(TOKEN, json.dumps(self.m.jira_state("hong"), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
