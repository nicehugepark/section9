"""미등록 운영체제 계정은 조용히 사용자가 되지 않는다 (REQ-20260906-008).

jade 실사고 2026-09-06: 계정 sjpark 이 os_accounts 에 없어 「sjpark」이 사용자로 서고
users/sjpark 이 생겨 동기화까지 됐다. git 은 user.name=nicehugepark 을 알고 있었다.

실행: python3 tests/ os_account_fallback
"""
import getpass
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class OsAccountFallback(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9osacct-")
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION")}
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        os.environ.pop("S9_SESSION", None)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        spec = importlib.util.spec_from_loader(
            "s9_osacct", importlib.machinery.SourceFileLoader("s9_osacct", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self._register("alice", github="al", emails=["alice@example.com"])

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _register(self, name, github="", emails=()):
        d = os.path.join(self.root, "users", name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "profile.md"), "w", encoding="utf-8") as f:
            # 프론트매터의 목록은 json 이다(fm_dump 와 같은 문법) — 파이썬 repr 이 아니다
            f.write(f"---\nname: {name}\nrole: member\ngithub: {github}\n"
                    f"emails: {json.dumps(list(emails))}\n---\n")

    def _git(self, *a):
        subprocess.run(["git", "-C", self.root, *a], check=True, capture_output=True)

    def test_u1_git_name_matches_a_registered_user(self):
        """U1. git user.name 이 등록 사용자의 github 와 같으면 그 사용자다 — 계정 이름을 지어내지 않는다."""
        self._git("config", "user.name", "al")
        self._git("config", "user.email", "nobody@example.invalid")
        self.assertEqual(self.m.resolve_user(None, with_source=True), ("alice", "os-account"))

    def test_u2_git_email_matches_a_registered_user(self):
        """U2. 이름은 안 맞아도 user.email 이 profile 의 emails 에 있으면 그 사용자다(대소문자 무시)."""
        self._git("config", "user.name", "someone")
        self._git("config", "user.email", "Alice@Example.com")
        self.assertEqual(self.m.resolve_user(None), "alice")

    def test_u3_no_match_falls_back_but_creates_nothing(self):
        """U3. 아무 증거도 없으면 종전대로 계정 이름이되, 등록부(users/<계정>/)는 만들지 않는다."""
        self._git("config", "user.name", "someone")
        self._git("config", "user.email", "someone@example.invalid")
        acct = getpass.getuser()
        self.assertEqual(self.m.resolve_user(None), acct)
        self.assertIsNone(self.m.machine_register("t8rc", name=acct))
        self.assertFalse(os.path.exists(os.path.join(self.root, "users", acct)),
                         "미등록 계정의 디렉토리가 생겼다 — 그것이 곧 「저절로 등록」이다")
        # 등록 사용자에게는 종전대로 적는다
        self.assertEqual(self.m.machine_register("t8rc", name="alice")["hostname"],
                         self.m.current_machine())


if __name__ == "__main__":
    unittest.main(verbosity=2)
