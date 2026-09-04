"""사용자 프로필 확장 테스트 (REQ-20260824-055 E1~E6).

회사 이메일 N개(emails)·개인/조직 GitHub 분리 저장 + 미기재 촉구(digest).
격리: S9_ROOT=mktemp. 실행: python3 tests/test_user_profile_ext.py
"""
import json
import os
import subprocess
import tempfile
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)


class TestProfileExt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9prof-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox"}
        cls.env.pop("S9_SESSION", None)

        def cli(*argv, expect=0):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=15,
                               stdin=subprocess.DEVNULL)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)
        cli("init")

    def meta(self, name):
        import re
        with open(os.path.join(self.tmp, "users", name, "profile.md"),
                  encoding="utf-8") as f:
            txt = f.read()
        m = {}
        for line in txt.split("\n---\n")[0].splitlines():
            mm = re.match(r"(\w+): (.*)$", line)
            if mm:
                k, v = mm.group(1), mm.group(2)
                try:
                    m[k] = json.loads(v)
                except ValueError:
                    m[k] = v
        return m

    # E1. add: 이메일 복수 + github 2종 저장
    def test_e1_add_fields(self):
        self.cli("user", "add", "alice",
                 "--emails", "a@corp.com,a2@corp.com",
                 "--github", "@alice-gh", "--github-org", "corp-team")
        m = self.meta("alice")
        self.assertEqual(m["emails"], ["a@corp.com", "a2@corp.com"])
        self.assertEqual(m["github"], "alice-gh")     # @ 접두 제거 저장
        self.assertEqual(m["github_org"], "corp-team")

    # E2. update: emails 전체 교체·개별 갱신·형식 거부
    def test_e2_update(self):
        self.cli("user", "add", "bob", "--emails", "b@corp.com")
        r = self.cli("user", "update", "bob",
                     "--emails", "b@corp.com,b2@corp.com",
                     "--github", "bob-gh")
        self.assertIn("emails(2)", r.stdout)
        m = self.meta("bob")
        self.assertEqual(len(m["emails"]), 2)
        self.assertEqual(m["github"], "bob-gh")
        r = self.cli("user", "update", "bob", "--emails", "잘못된메일",
                     expect=None)
        self.assertNotEqual(r.returncode, 0)
        r = self.cli("user", "update", "bob", "--github", "no spaces!",
                     expect=None)
        self.assertNotEqual(r.returncode, 0)

    # E4. API: update 반영 + /api/users 노출
    def test_e4_api(self):
        import socket, time
        port = free_port()
        srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(port)],
            env={**self.env, "S9_USER": "alice", "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_server(port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/user/update",
                data=json.dumps({"name": "alice",
                                 "emails": ["x@corp.com"],
                                 "github_org": "new-org"}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"})
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=5) as r:
                        d = json.loads(r.read().decode())
                    break
                except (ConnectionError, urllib.error.URLError):
                    time.sleep(0.3)
            self.assertTrue(d.get("ok"), d)
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/users?scope=machine",
                    timeout=5) as r:
                users = json.loads(r.read().decode())["users"]
            al = next(u for u in users if u["name"] == "alice")
            self.assertEqual(al["emails"], ["x@corp.com"])
            self.assertEqual(al["github_org"], "new-org")
        finally:
            srv.terminate()
            srv.wait(timeout=5)

    # E5. 미기재 촉구: 필드 없는 사용자 digest에 ⚠ 프로필 미완성
    def test_e5_digest_nag(self):
        self.cli("user", "add", "carol")           # 아무 필드 없음
        r = self.cli("digest", "--user", "carol")
        self.assertIn("프로필 미완성", r.stdout)
        self.assertIn("GitHub", r.stdout)
        # 전부 채우면 촉구 사라짐
        self.cli("user", "update", "carol", "--emails", "c@corp.com",
                 "--github", "carol-gh", "--github-org", "corp-team")
        r = self.cli("digest", "--user", "carol")
        self.assertNotIn("프로필 미완성", r.stdout)

    # E6. 하위 호환: 기존 email 단수 필드만 있어도 이메일 촉구는 없음
    def test_e6_legacy_email(self):
        self.cli("user", "add", "dan", "--email", "d@corp.com")
        r = self.cli("digest", "--user", "dan")
        self.assertNotIn("회사 이메일", r.stdout)
        self.assertIn("GitHub", r.stdout)          # github은 여전히 촉구


class TestRoleChangeIsAdminOnly(unittest.TestCase):
    """R1~R5 (REQ-20260902-029) — `s9 user role` 은 admin 만. 대시보드에는 있던
    검사가 CLI 에 없어 누구나 자신을 admin 으로 올릴 수 있었다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9role-")
        cls.base = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox"}
        cls.base.pop("S9_SESSION", None)
        cls.base.pop("S9_USER", None)
        cls.cli("init")

    @classmethod
    def cli(cls, *argv, user=None, expect=0):
        env = dict(cls.base)
        if user:
            env["S9_USER"] = user
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, timeout=15, stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                 f"{r.stdout}{r.stderr}")
        return r

    def role_of(self, name):
        return self.cli("user", "role", name).stdout.strip()

    def test_r4_bootstrap_without_any_admin_is_allowed(self):
        # 등록된 admin 이 하나도 없는 **새 설치** — 첫 admin 을 세울 길은 열려 있어야
        # 한다. 다른 케이스가 root 를 admin 으로 세우므로 여기는 제 루트를 쓴다.
        fresh = tempfile.mkdtemp(prefix="s9role0-")
        saved = self.base
        try:
            type(self).base = {**saved, "S9_ROOT": fresh}
            self.cli("init")
            self.cli("user", "add", "first")
            self.cli("user", "role", "first", "admin", user="first")
            self.assertIn("admin", self.role_of("first"))
        finally:
            type(self).base = saved

    def test_r1_r2_member_cannot_change_roles(self):
        self.cli("user", "add", "root", expect=None)
        self.cli("user", "role", "root", "admin", user="root", expect=None)
        self.cli("user", "add", "mallory")
        self.cli("user", "add", "victim")
        # R2 자기 승격
        r = self.cli("user", "role", "mallory", "admin", user="mallory", expect=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("admin 만", r.stdout + r.stderr)
        self.assertIn("member", self.role_of("mallory"))
        # R1 남의 역할
        r = self.cli("user", "role", "victim", "viewer", user="mallory", expect=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("member", self.role_of("victim"))

    def test_r3_admin_changes_role_with_audit(self):
        self.cli("user", "add", "root", expect=None)
        self.cli("user", "role", "root", "admin", user="root", expect=None)
        self.cli("user", "add", "carol")
        self.cli("user", "role", "carol", "viewer", user="root")
        self.assertIn("viewer", self.role_of("carol"))
        with open(os.path.join(self.tmp, "users", "carol", "profile.md"),
                  encoding="utf-8") as f:
            self.assertIn("role=viewer", f.read())     # Notes audit (do_user_update)

    def test_r5_reading_a_role_needs_no_admin(self):
        self.cli("user", "add", "root", expect=None)
        self.cli("user", "role", "root", "admin", user="root", expect=None)
        # 등록은 admin 이 한다 — 앞선 케이스가 남긴 관찰 계정(viewer)이 기본
        # 사용자로 잡히면 등록 자체가 막힌다. 이 케이스가 묻는 것은 **읽기**다.
        self.cli("user", "add", "dave", user="root")
        r = self.cli("user", "role", "root", user="dave")
        self.assertIn("admin", r.stdout)


class TestProfileWarnScope(unittest.TestCase):
    """프로필 경고 범위 (REQ-20260825-046): 조직 GitHub은 비필수(사용자 확정,
    REQ-038) — 헤더 ⚠ 배지·"필수" 문구 경로에서 제외돼야 한다."""
    def setUp(self):
        import os as _os
        here = _os.path.dirname(_os.path.abspath(__file__))
        with open(index_path(),
                  encoding="utf-8") as f:
            self.html = f.read()
        with open(_os.path.join(here, "..", "bin", "s9"),
                  encoding="utf-8") as f:
            self.s9 = f.read()

    def test_w1_badge_excludes_org(self):
        import re as _re
        m = _re.search(r"function profileMissing[\s\S]{0,400}?\n\}", self.html)
        self.assertIsNotNone(m)
        self.assertNotIn('miss.push("조직 GitHub")', m.group(0))

    def test_w2_no_contradictory_wording(self):
        self.assertNotIn("필수 권장", self.html)   # "필수"와 "권장"은 모순

    def test_w3_digest_nag_excludes_org(self):
        # digest 촉구(REQ-038 수복)와 대시보드가 같은 정책을 유지한다
        import re as _re
        seg = self.s9.split("프로필 필수 권장 필드 촉구")[-1][:800]             if "프로필" in self.s9 else self.s9
        self.assertNotIn('missing.append("조직 GitHub', seg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
