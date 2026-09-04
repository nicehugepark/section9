"""프로젝트 멤버관리 API 테스트 (REQ-20260823-073, 신원 모델은 REQ-20260824-027).

actor는 서버 파생 whoami — 클라이언트 user 파라미터는 무시된다. 테스트는
admin(boss) whoami 서버에서 "as" 대리 지정으로 각 사용자의 권한을 검증한다
(권한 거부·가시성 의미는 구모델 테스트와 동일하게 보존).

격리: S9_ROOT=mktemp — 라이브 vault를 건드리지 않는다.
실행: python3 tests/test_project_member_api.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class TestMemberApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9test-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp}
        cls.env.pop("S9_SESSION", None)

        def cli(*argv, expect=0):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=15)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "boss", "--role", "admin")
        for u in ("alice", "bob", "carol", "dan"):
            cli("user", "add", u)
        cli("project", "add", "demo", "--name", "Demo", "--user", "alice")
        cli("project", "member", "demo", "add", "bob",
            "--role", "maintainer", "--user", "alice")
        cli("project", "member", "demo", "add", "carol",
            "--role", "contributor", "--user", "alice")

        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**cls.env, "S9_USER": "boss"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    @classmethod
    def post(cls, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{cls.port}{path}",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())
            except (ConnectionError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(0.3)

    @classmethod
    def members(cls):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{cls.port}/api/projects", timeout=5) as r:
            data = json.loads(r.read().decode())
        proj = next(p for p in data["projects"] if p["slug"] == "demo")
        return {m["user"]: m for m in proj["members"]}

    # M1. maintainer가 멤버 추가
    def test_test_member_api(self):
        """TestMemberApi 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("m1_maintainer_adds_member"):
                code, res = self.post("/api/project/member",
                                      {"as": "bob", "slug": "demo", "member": "dan",
                                       "role": "contributor"})
                self.assertEqual(code, 200, res)
                self.assertTrue(res.get("ok"), res)
                self.assertEqual(self.members()["dan"]["role"], "contributor")

            # M2. upsert 부분 갱신: position만 → role/until 불변
        with self.subTest("m2_partial_update"):
                code, res = self.post("/api/project/member",
                                      {"as": "bob", "slug": "demo", "member": "carol",
                                       "position": "designer"})
                self.assertEqual(code, 200, res)
                m = self.members()["carol"]
                self.assertEqual(m["role"], "contributor")
                self.assertEqual(m["position"], "designer")
                self.assertEqual(m.get("until", ""), "")

            # M3. contributor는 멤버 변경 불가
        with self.subTest("m3_contributor_denied"):
                code, res = self.post("/api/project/member",
                                      {"as": "carol", "slug": "demo", "member": "dan",
                                       "role": "viewer"})
                self.assertEqual(code, 400, res)
                self.assertFalse(res.get("ok"))

            # M4. owner 지정은 owner만 (maintainer 불가)
        with self.subTest("m4_owner_grant_needs_own"):
                code, res = self.post("/api/project/member",
                                      {"as": "bob", "slug": "demo", "member": "carol",
                                       "role": "owner"})
                self.assertEqual(code, 400, res)

            # M5. 마지막 활성 owner 강등/제거 차단
        with self.subTest("m5_last_owner_guard"):
                code, res = self.post("/api/project/member",
                                      {"as": "alice", "slug": "demo", "member": "alice",
                                       "role": "maintainer"})
                self.assertEqual(code, 400, res)
                code, res = self.post("/api/project/member/rm",
                                      {"as": "alice", "slug": "demo", "member": "alice"})
                self.assertEqual(code, 400, res)
                self.assertEqual(self.members()["alice"]["role"], "owner")

            # M6. 미등록 as 거부 (admin 이라도 대리 대상은 등록 사용자만)
        with self.subTest("m6_unregistered_actor"):
                code, res = self.post("/api/project/member",
                                      {"as": "ghost", "slug": "demo", "member": "dan",
                                       "role": "viewer"})
                self.assertEqual(code, 400, res)

            # M6b. 구모델 user 파라미터는 무시 — carol(contributor) 대리 중 user:alice
            #      (owner) 스푸핑을 얹어도 actor 는 carol → 거부 (REQ-20260824-027 W3)
        with self.subTest("m6b_user_param_ignored"):
                code, res = self.post("/api/project/member",
                                      {"as": "carol", "user": "alice", "slug": "demo",
                                       "member": "dan", "role": "viewer"})
                self.assertEqual(code, 400, res)
                self.assertFalse(res.get("ok"))

            # M7. 제거 정상 경로
        with self.subTest("m7_remove_member"):
                self.post("/api/project/member",
                          {"as": "bob", "slug": "demo", "member": "dan",
                           "role": "contributor"})
                code, res = self.post("/api/project/member/rm",
                                      {"as": "bob", "slug": "demo", "member": "dan"})
                self.assertEqual(code, 200, res)
                self.assertNotIn("dan", self.members())

            # M8. 회귀: CLI 경로 불변 (추출 후에도 동작·거부 동일)
        with self.subTest("m8_cli_regression"):
            r = self.cli("project", "member", "demo", "ls", expect=0)
            self.assertIn("alice", r.stdout)
            r = self.cli("project", "member", "demo", "add", "dan",
                         "--role", "viewer", "--user", "carol", expect=None)
            self.assertNotEqual(r.returncode, 0)  # contributor 거부

if __name__ == "__main__":
    unittest.main(verbosity=2)
