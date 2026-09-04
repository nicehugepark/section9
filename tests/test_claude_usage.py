"""클로드 계정·사용량 API 테스트 (REQ-20260824-043 서버측 U1~U4).

HOME 오버라이드로 가짜 자격증명, S9_USAGE_URL로 목 업스트림을 주입한다.
격리: S9_ROOT=mktemp + HOME=mktemp. 실행: python3 tests/test_claude_usage.py
"""
import json
import http.server
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

UPSTREAM = {
    "limits": [
        {"kind": "session", "group": "session", "percent": 7,
         "severity": "normal", "scope": None,
         "resets_at": "2026-08-24T14:20:00+00:00"},
        {"kind": "weekly_all", "group": "weekly", "percent": 31,
         "severity": "normal", "scope": None,
         "resets_at": "2026-08-30T11:00:00+00:00"},
        {"kind": "weekly_scoped", "group": "weekly", "percent": 60,
         "severity": "warning",
         "scope": {"model": {"id": None, "display_name": "Fable"},
                   "surface": None},
         "resets_at": "2026-08-30T11:00:00+00:00"},
    ]
}


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class MockUpstream(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):
        MockUpstream.hits.append(self.headers.get("Authorization", ""))
        body = json.dumps(UPSTREAM).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestClaudeUsage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9usage-")
        cls.home = tempfile.mkdtemp(prefix="s9home-")
        os.makedirs(os.path.join(cls.home, ".claude"), exist_ok=True)
        with open(os.path.join(cls.home, ".claude.json"), "w") as f:
            json.dump({"oauthAccount": {"emailAddress": "me@test.dev"}}, f)
        with open(os.path.join(cls.home, ".claude",
                               ".credentials.json"), "w") as f:
            json.dump({"claudeAiOauth": {"accessToken": "tok-secret-123",
                                         "subscriptionType": "team"}}, f)
        cls.upport = free_port()
        cls.upsrv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", cls.upport), MockUpstream)
        threading.Thread(target=cls.upsrv.serve_forever, daemon=True).start()

        cls.port = free_port()
        env = {**os.environ, "S9_ROOT": cls.tmp, "HOME": cls.home,
               "S9_USAGE_URL": f"http://127.0.0.1:{cls.upport}/usage",
               "S9_REWORK_WATCH": "off"}
        env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=env, timeout=15)
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        cls.upsrv.shutdown()

    def get(self, port=None):
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port or self.port}"
                        f"/api/claude/usage", timeout=5) as r:
                    return json.loads(r.read().decode())
            except (ConnectionError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(0.3)

    # U1. 파싱: 이메일·구독·3버킷(모델명 포함), 토큰 비노출
    def test_test_claude_usage(self):
        """TestClaudeUsage 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("u1_parse"):
                d = self.get()
                self.assertTrue(d["ok"], d)
                self.assertEqual(d["email"], "me@test.dev")
                self.assertEqual(d["subscription"], "team")
                kinds = {L["kind"]: L for L in d["limits"]}
                self.assertEqual(kinds["session"]["percent"], 7)
                self.assertEqual(kinds["weekly_all"]["percent"], 31)
                self.assertEqual(kinds["weekly_scoped"]["percent"], 60)
                self.assertEqual(kinds["weekly_scoped"]["scope_name"], "Fable")
                self.assertNotIn("tok-secret-123", json.dumps(d))

            # U2. 60s 캐시: 연속 호출이 업스트림 재타격 없음
        with self.subTest("u2_cache"):
                self.get()
                before = len(MockUpstream.hits)
                self.get()
                self.get()
                self.assertEqual(len(MockUpstream.hits), before)

            # U3. 자격증명 없음 → 200 + ok:false (500 금지)
        with self.subTest("u3_no_credentials"):
                home2 = tempfile.mkdtemp(prefix="s9home2-")
                tmp2 = tempfile.mkdtemp(prefix="s9usage2-")
                port2 = free_port()
                env2 = {**os.environ, "S9_ROOT": tmp2, "HOME": home2,
                        "S9_REWORK_WATCH": "off"}
                env2.pop("S9_SESSION", None)
                subprocess.run([S9, "init"], capture_output=True, env=env2, timeout=15)
                srv2 = subprocess.Popen(
                    [S9, "serve", "--host", "127.0.0.1", "--port", str(port2)],
                    env=env2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    wait_server(port2)
                    d = self.get(port2)
                    self.assertFalse(d["ok"])
                    self.assertIn("자격증명", d.get("error", ""))
                finally:
                    srv2.terminate()
                    srv2.wait(timeout=5)

            # U3b(U6). 서버 생존 중 계정 전환: 자격증명 파일이 바뀌면 TTL 무시하고
            #          즉시 새 계정 반영 (mtime 무효화 — 장수 serve 프로세스 전제)
        with self.subTest("u3b_account_switch_live"):
                d = self.get()
                self.assertEqual(d["email"], "me@test.dev")
                with open(os.path.join(self.home, ".claude.json"), "w") as f:
                    json.dump({"oauthAccount":
                               {"emailAddress": "other@test.dev"}}, f)
                cred = os.path.join(self.home, ".claude", ".credentials.json")
                with open(cred, "w") as f:
                    json.dump({"claudeAiOauth": {"accessToken": "tok-other-456",
                                                 "subscriptionType": "pro"}}, f)
                os.utime(cred, (time.time() + 2, time.time() + 2))  # mtime 확실히 변경
                d = self.get()
                self.assertEqual(d["email"], "other@test.dev", d)
                self.assertEqual(d["subscription"], "pro")
                self.assertNotIn("tok-other-456", json.dumps(d))

            # U4. 업스트림 다운 → 캐시가 있으면 stale 반환 (서버는 계속 응답)
        with self.subTest("u4_upstream_down_stale"):
            self.get()  # 캐시 확보
            MockUpstream.hits.clear()
            cls = type(self)
            cls.upsrv.shutdown()   # 업스트림 다운
            time.sleep(0.2)
            d = self.get()
            # 캐시 TTL 내라 캐시 히트(신선) 또는 stale — 어느 쪽이든 데이터는 있다
            self.assertTrue(d.get("ok") or d.get("stale"), d)
            self.assertTrue(d.get("limits"), d)

if __name__ == "__main__":
    unittest.main(verbosity=2)
