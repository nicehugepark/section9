"""게이트가 나를 알아보는가 (REQ-20260829-010-62x6).

harness 경로를 커밋하려 하면 `s9-guard` 가 역할을 본다. 그런데 그 게이트는
운영체제 계정 이름(`getpass.getuser()`)을 그대로 썼다 — 그러면 계정 이름과
하네스의 사용자 이름이 다른 사람은 **늘 '미등록'** 이고, admin 이어도 막힌다.

`bin/s9` 는 이미 그 매칭을 한다: 프로필의 `os_accounts` 에 적힌 운영체제
계정을 등록 사용자로 잇는다(REQ-20260827-060 — 그때는 CLI 와 화면의 판정이
갈려 "자기 문서가 하나도 안 보이는" 결과가 났다). 이번엔 CLI 와 **게이트**의
판정이 갈렸다.

한 사람을 두 이름으로 보면 게이트가 스스로를 무력화한다. 권한 있는 사람이
막히면 `S9_USER=<admin> git commit` 을 손에 익히게 되고, 그 습관은 게이트가
정말 막아야 할 때도 그대로 나온다.

실행: python3 tests/ guard_user_alias
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import textwrap
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9guard_alias", importlib.machinery.SourceFileLoader(
            "s9guard_alias", GUARD))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PROFILE = textwrap.dedent("""\
    ---
    name: bora
    role: admin
    os_accounts: ["os-bora"]
    ---

    ## Notes
    """)


class GuardUserAlias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        cls.root = tempfile.mkdtemp(prefix="s9guardu-")
        os.makedirs(os.path.join(cls.root, "users", "bora"))
        with open(os.path.join(cls.root, "users", "bora", "profile.md"),
                  "w", encoding="utf-8") as f:
            f.write(PROFILE)
        # 별칭이 없는 등록 사용자 하나 — 이름이 그대로 계정인 흔한 경우
        os.makedirs(os.path.join(cls.root, "users", "chan"))
        with open(os.path.join(cls.root, "users", "chan", "profile.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\nname: chan\nrole: member\n---\n")

    def _as(self, account, env=None):
        e = {k: v for k, v in os.environ.items() if k != "S9_USER"}
        e.update(env or {})
        with mock.patch.object(self.m, "ROOT", self.root), \
             mock.patch.dict(os.environ, e, clear=True), \
             mock.patch("getpass.getuser", return_value=account):
            return self.m.current_user()

    def test_guard_user_alias(self):
        """GuardUserAlias 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("os_account_is_matched_to_the_registered_user"):
            self.assertEqual(self._as("os-bora"), "bora")
        with self.subTest("the_matched_user_carries_their_role"):
            with mock.patch.object(self.m, "ROOT", self.root):
                self.assertEqual(self.m.role_of(self._as("os-bora")), "admin")
        with self.subTest("a_plain_account_still_works"):
            self.assertEqual(self._as("chan"), "chan")
        with self.subTest("an_unknown_account_stays_unknown"):
            self.assertEqual(self._as("nobody"), "nobody")
            with mock.patch.object(self.m, "ROOT", self.root):
                self.assertEqual(self.m.role_of("nobody"), "")
        with self.subTest("explicit_env_still_wins"):
            self.assertEqual(self._as("os-bora", {"S9_USER": "chan"}), "chan")
        with self.subTest("a_broken_profile_does_not_break_the_commit"):
            bad = os.path.join(self.root, "users", "zzz")
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, "profile.md"), "w", encoding="utf-8") as f:
                f.write('---\nos_accounts: {not: "a list"}\n---\n')
            self.addCleanup(os.remove, os.path.join(bad, "profile.md"))
            self.assertEqual(self._as("os-bora"), "bora")

if __name__ == "__main__":
    unittest.main()
