"""신원 파생(whoami) 테스트 (REQ-20260824-027).

선택 → 파생 전환: 서버가 신원을 파생한다 (대시보드는 127.0.0.1 전용 —
브라우저 사용자 = 서버 기동 OS 계정). 클라이언트 자기신고(user/?me=)는 무시.
- GET /api/whoami: resolve_user() 폴백을 users/ 프로필과 매칭 (이름 직접 →
  os_accounts 포함), 미매칭이면 registered:false
- s9 user add: 현재 OS 계정을 os_accounts에 자동 기록
- s9 user attach <name>: 현 OS계정+머신을 프로필에 연결 (로밍 1회)
- 쓰기 actor = 서버 whoami (클라이언트 user 파라미터 무시), admin만 as 대리
- ?as=/as: admin만 시점 전환·대리 조작, 비admin 거부

격리: S9_ROOT=mktemp + S9_MACHINE 고정. 실행: python3 tests/test_whoami.py
"""
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
MACHINE = "TESTMACH"


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class TestWhoami(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9who-")
        cls.base_env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": MACHINE,
                        "S9_REWORK_WATCH": "off"}
        cls.base_env.pop("S9_SESSION", None)
        cls.base_env.pop("S9_USER", None)

        def cli(*argv, user=None, expect=0):
            env = dict(cls.base_env)
            if user:
                env["S9_USER"] = user
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=env, timeout=15)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "boss", "--role", "admin", user="boss")
        cli("user", "add", "alice", user="alice")
        cli("user", "add", "bob", user="bob")
        # W2b: add 시 현재 OS 계정(S9_USER 폴백) 자동 기록 확인용
        cli("user", "add", "carol", user="carolacct")
        # W2: 로밍 — osacct9 라는 OS 계정을 alice 프로필에 1회 연결
        cli("user", "attach", "alice", user="osacct9")

        cli("project", "add", "px", "--name", "PX", "--user", "alice")
        r = cli("new", "request", "--title", "px doc", "--summary", "px",
                "--goal", "t", "--project", "px", "--user", "alice",
                "--body", "tok-px")
        cls.px_doc = re.search(r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?", r.stdout).group(0)
        r = cli("new", "request", "--title", "solo doc", "--summary", "solo",
                "--goal", "t", "--user", "bob", "--body", "tok-solo")
        cls.solo_doc = re.search(r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?", r.stdout).group(0)

        # 서버 4대 — whoami는 서버 프로세스 S9_USER 로 통제한다
        cls.srv = {}
        cls.port = {}
        for key, s9user in (("boss", "boss"), ("alice", "alice"),
                            ("stranger", "stranger77"), ("roam", "osacct9")):
            port = free_port()
            env = dict(cls.base_env)
            env["S9_USER"] = s9user
            p = subprocess.Popen(
                [S9, "serve", "--host", "127.0.0.1", "--port", str(port)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cls.srv[key] = p
            cls.port[key] = port
        for port in cls.port.values():
            wait_server(port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def tearDownClass(cls):
        for p in cls.srv.values():
            p.terminate()
        for p in cls.srv.values():
            p.wait(timeout=5)

    @staticmethod
    def _open(req):
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())
            except (ConnectionError, urllib.error.URLError):
                # 기동 직후 loopback RST 플레이크 (WSL2) — 짧게 재시도
                if attempt == 2:
                    raise
                time.sleep(0.3)

    @classmethod
    def get(cls, srv, path, **params):
        qs = urllib.parse.urlencode(params)
        return cls._open(f"http://127.0.0.1:{cls.port[srv]}{path}"
                         + (f"?{qs}" if qs else ""))

    @classmethod
    def post(cls, srv, path, payload):
        # 주의: POST 재시도는 멱등이 아닐 수 있으나 여기선 상태 전이 결과를
        # 별도 GET 으로 검증하므로 허용
        return cls._open(urllib.request.Request(
            f"http://127.0.0.1:{cls.port[srv]}{path}",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"}))

    def catalog_ids(self, srv, **params):
        code, rows = self.get(srv, "/api/catalog", **params)
        self.assertEqual(code, 200)
        return {r["id"] for r in rows}

    def profile(self, name):
        with open(os.path.join(self.tmp, "users", name, "profile.md"),
                  encoding="utf-8") as f:
            return f.read()

    # W1. whoami 파생: 등록 계정 매칭 / 미등록 표시
    def test_test_whoami(self):
        """TestWhoami 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("w1_whoami_derivation"):
                code, d = self.get("alice", "/api/whoami")
                self.assertEqual(code, 200)
                self.assertEqual(d["user"], "alice")
                self.assertTrue(d["registered"])
                self.assertEqual(d["role"], "member")
                self.assertEqual(d["machine"], MACHINE)
                code, d = self.get("boss", "/api/whoami")
                self.assertEqual(d["user"], "boss")
                self.assertEqual(d["role"], "admin")
                code, d = self.get("stranger", "/api/whoami")
                self.assertEqual(code, 200)
                self.assertEqual(d["user"], "stranger77")
                self.assertFalse(d["registered"])
                self.assertEqual(d["role"], "")

            # W2. attach 로밍: os_accounts 추가 후 그 OS 계정이 alice 로 파생
        with self.subTest("w2_attach_roaming"):
                self.assertIn("osacct9", self.profile("alice"))
                self.assertIn(MACHINE, self.profile("alice"))
                code, d = self.get("roam", "/api/whoami")
                self.assertEqual(code, 200)
                self.assertEqual(d["user"], "alice")
                self.assertTrue(d["registered"])

            # W2b. user add 시 현재 OS 계정 자동 기록
        with self.subTest("w2b_add_records_os_account"):
                self.assertIn("carolacct", self.profile("carol"))
                # 미등록 계정 attach 는 거부
                r = self.cli("user", "attach", "ghost", user="osacct9", expect=None)
                self.assertNotEqual(r.returncode, 0)

            # W3. 쓰기 actor 는 서버 whoami — 클라이언트 user 파라미터 무시
        with self.subTest("w3_write_actor_ignores_client_user"):
                # alice 서버에 user:boss 스푸핑 → History 는 alice 로 기록
                code, res = self.post("alice", "/api/status",
                                      {"id": self.px_doc, "to": "in-progress",
                                       "note": "spoof-check", "user": "boss"})
                self.assertEqual(code, 200, res)
                code, d = self.get("boss", "/api/doc", id=self.px_doc)
                line = [l for l in d["body"].splitlines() if "spoof-check" in l][0]
                self.assertIn("(by alice)", line)
                self.assertNotIn("boss", line)
                # 인가에도 스푸핑 불가: px 멤버 조작을 user:alice(owner) 로 위장해도
                # actor=stranger77(미등록) 기준으로 거부
                code, res = self.post("stranger", "/api/project/member",
                                      {"slug": "px", "member": "bob",
                                       "role": "viewer", "user": "alice"})
                self.assertEqual(code, 400, res)

            # W4. as 대리/미리보기 — admin 만
        with self.subTest("w4_admin_as"):
                # GET: admin 서버에서 as=bob → bob 시점 (solo 보임, px 숨김)
                ids = self.catalog_ids("boss", **{"as": "bob"})
                self.assertIn(self.solo_doc, ids)
                self.assertNotIn(self.px_doc, ids)
                # GET: 비admin 의 as 는 무시 — alice 시점 유지 (solo 안 보임)
                ids = self.catalog_ids("alice", **{"as": "bob"})
                self.assertNotIn(self.solo_doc, ids)
                # GET: 구모델 ?me= 는 무시 — alice 서버에서 me=boss 로도 solo 비가시
                ids = self.catalog_ids("alice", me="boss")
                self.assertNotIn(self.solo_doc, ids)
                # POST: admin as=alice → actor 는 alice 로 기록
                code, res = self.post("boss", "/api/status",
                                      {"id": self.px_doc, "to": "review",
                                       "note": "proxy-check", "as": "alice"})
                self.assertEqual(code, 200, res)
                code, d = self.get("boss", "/api/doc", id=self.px_doc)
                line = [l for l in d["body"].splitlines() if "proxy-check" in l][0]
                self.assertIn("(by alice)", line)
                # POST: 비admin 의 as 는 400
                code, res = self.post("alice", "/api/status",
                                      {"id": self.px_doc, "to": "done",
                                       "as": "boss"})
                self.assertEqual(code, 400, res)
                # POST: 미등록 as 는 admin 이라도 400
                code, res = self.post("boss", "/api/status",
                                      {"id": self.px_doc, "to": "done",
                                       "as": "ghost"})
                self.assertEqual(code, 400, res)

            # W5. 격리·개인화가 whoami 기준 — 미등록 whoami(정책 부재)는 비강제 유지
        with self.subTest("w5_whoami_based_isolation"):
            ids = self.catalog_ids("alice")
            self.assertIn(self.px_doc, ids)       # 멤버 가시
            self.assertNotIn(self.solo_doc, ids)  # 무소속 타인 문서 비가시
            self.assertIn(self.solo_doc, self.catalog_ids("boss"))  # admin 전부
            # 미등록 서버 계정 = 정책 부재 → 비강제 (기존 원칙 유지)
            self.assertIn(self.px_doc, self.catalog_ids("stranger"))
            # 개인화 쓰기: alice 서버에서 타인(bob) 설정 변경은 거부, 본인은 허용
            code, res = self.post("alice", "/api/user/config",
                                  {"name": "bob", "key": "ui_skin", "value": "glass"})
            self.assertEqual(code, 400, res)
            code, res = self.post("alice", "/api/user/config",
                                  {"name": "alice", "key": "ui_skin", "value": "glass"})
            self.assertEqual(code, 200, res)

if __name__ == "__main__":
    unittest.main(verbosity=2)
