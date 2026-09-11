"""고른 계정이 다음 기동까지 가는가 (REQ-20260911-012).

사용자 보고 2026-09-11 15:29: "왜 자꾸 재시작하면 마지막 사용했던 클로드
계정이 아니라 claude01로 실행되는거지? 토큰이 모자라서 조금 남겨놓고 다른
계정을 쓰는건데 이런식이면 계속 낭비해버리잖아."

원인: 계정은 `CLAUDE_CONFIG_DIR` 환경변수로만 정해지는데, 그 값을 아는 것이
`s9 code` 래퍼 프로세스의 지역 변수뿐이었다. 창을 닫거나 컴퓨터를 껐다 켜면
그 변수와 함께 사라져 기본 자리(`~/.claude`)로 떨어졌다.

여기서 보는 것은 두 자리다 — **남기는 쪽**(`_record_account_choice`)과
**읽어서 거는 쪽**(`code_account_apply`). 계약은 셋이다:
  · 사람이 직접 준 `CLAUDE_CONFIG_DIR` 이 언제나 이긴다,
  · 없으면 이 컴퓨터에서 마지막으로 고른 계정으로 뜬다,
  · 그 프로필이 이 컴퓨터에 없으면 막지 말고 기본 계정으로 뜨되 그 사실을 말한다.

실행: python3 tests/ account_persist
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AccountPersistTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9acct-")
        cls.home = os.path.join(cls.tmp, "home")
        os.makedirs(cls.home, exist_ok=True)
        cls._prev = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_MACHINE", "S9_USER",
                               "S9_SESSION", "S9_REWORK_WATCH", "HOME",
                               "CLAUDE_CONFIG_DIR")}
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "tester"
        os.environ["S9_REWORK_WATCH"] = "off"      # 무인 스폰 차단 (격리)
        os.environ["HOME"] = cls.home              # 프로필 자리를 임시로 옮긴다
        os.environ.pop("S9_SESSION", None)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       timeout=20, stdin=subprocess.DEVNULL)
        subprocess.run([S9, "user", "add", "tester"], capture_output=True,
                       text=True, timeout=20, stdin=subprocess.DEVNULL)
        cls.s9 = _load("s9_mod_acct", S9)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def setUp(self):
        # 매번 빈 선택에서 시작한다 — 시험끼리 값을 물려주지 않는다.
        self.s9.do_user_config_set("tester", "last_account_choice", "",
                                   actor="test reset")

    def profile(self, name):
        """그 계정 프로필이 이 컴퓨터에 있는 자리를 만든다."""
        p = os.path.join(self.home, ".claude-profiles", name)
        os.makedirs(p, exist_ok=True)
        return os.path.abspath(p)

    # A1 — 고른 계정이 남고, 새 기동이 그것으로 뜬다
    def test_choice_survives_new_wrapper(self):
        prof = self.profile("claude04")
        self.s9._record_account_choice("tester", "claude04")
        self.assertEqual(self.s9.code_account_choice("tester"), "claude04")

        env = {}                      # 창을 닫았다 연 자리 — 환경이 비어 있다
        got = self.s9.code_account_apply(env, "tester")
        self.assertEqual(got["account"], "claude04")
        self.assertEqual(got["source"], "last")
        self.assertEqual(env.get("CLAUDE_CONFIG_DIR"), prof)

    # A2 — 그 값은 추적되지 않는 자리(local.json)에 산다
    def test_choice_is_local_only(self):
        self.profile("claude04")
        self.s9._record_account_choice("tester", "claude04")
        local = os.path.join(self.tmp, "users", "tester", "config",
                             "local.json")
        tracked = os.path.join(self.tmp, "users", "tester", "config",
                               "settings.json")
        with open(local, encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("last_account_choice"),
                             "claude04")
        if os.path.exists(tracked):
            with open(tracked, encoding="utf-8") as f:
                self.assertNotIn("last_account_choice", json.load(f))

    # A3 — 사람이 직접 준 환경변수가 이긴다
    def test_explicit_env_wins(self):
        self.profile("claude04")
        self.s9._record_account_choice("tester", "claude04")
        mine = self.profile("claude09")
        env = {"CLAUDE_CONFIG_DIR": mine}
        got = self.s9.code_account_apply(env, "tester")
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], mine)   # 안 덮는다
        self.assertEqual(got["source"], "env")
        self.assertEqual(got["account"], "claude09")

    # A4 — 기본 계정으로 되돌린 것도 선택이라, 옛 프로필로 돌아가지 않는다
    def test_home_choice_returns_home(self):
        self.profile("claude04")
        self.s9._record_account_choice("tester", "claude04")
        self.s9._record_account_choice("tester", self.s9.ACCOUNT_HOME_KEY)
        env = {}
        got = self.s9.code_account_apply(env, "tester")
        self.assertEqual(got["source"], "home")
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)

    # A5 — 기록된 프로필이 이 컴퓨터에 없으면 막지 말고 기본으로, 사실은 말한다
    def test_missing_profile_falls_back(self):
        self.s9._record_account_choice("tester", "claude77")   # 자리 없음
        env = {}
        got = self.s9.code_account_apply(env, "tester")
        self.assertEqual(got["source"], "missing")
        self.assertEqual(got["account"], "claude77")           # 무엇이 없는지
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)

    # A6' — 기동 줄이 어느 계정으로 떴는지 말한다 (사람이 판정할 근거)
    def test_startup_line_names_the_account(self):
        prof = self.profile("claude04")
        line = self.s9.code_account_line(
            {"source": "last", "account": "claude04", "cfg_dir": prof})
        self.assertIn("claude04", line)
        miss = self.s9.code_account_line(
            {"source": "missing", "account": "claude77", "cfg_dir": ""})
        self.assertIn("claude77", miss)
        self.assertIn("기본 계정", miss)
        # 기본 계정으로 뜨는 평소에는 아무 말도 보태지 않는다
        self.assertEqual(self.s9.code_account_line(
            {"source": "home", "account": self.s9.ACCOUNT_HOME_KEY}), "")

    # A6 — 고른 적이 없으면 아무것도 걸지 않는다 (종전 동작 그대로)
    def test_no_choice_is_home(self):
        env = {}
        got = self.s9.code_account_apply(env, "tester")
        self.assertEqual(got["source"], "home")
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)


if __name__ == "__main__":
    unittest.main()
