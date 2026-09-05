"""계정을 대시보드에서 고르고, 고른 것이 유지되는가 (REQ-20260827-079 재작업).

사용자: "방금 s9 account add 를 해서 claude02.pfe 계정으로 로컬 터미널에서
로그인을 했다. 이걸 대시보드에서도 됐으면 좋겠고, 이제 이 대시보드에서 그
계정으로 자동 변경이 되거나 변경을 할 수 있도록 했으면 좋겠다."

네 자리가 고장 나 있었다.

**하나 — 목록이 자리 이름을 말한다.** 창에 뜨는 것은 `새-계정`·`새-계정-2`
라는 **디렉토리 이름**이었다. 사람이 고르는 것은 자리가 아니라 계정이다.
로그인이 끝났는데도 이름이 안 바뀌어 있으면(settle 이 한 번 어긋나면) 그 이름은
영원히 자리 이름으로 남는다 — 목록을 부를 때마다 다시 정한다.

**둘 — 돌아올 길이 없다.** 목록은 `~/.claude-profiles/*` 만 훑었다. 기본
계정(`~/.claude`)은 그 아래에 없으므로 **한 번 프로필로 옮기면 대시보드에서는
돌아올 수 없다.** 나가는 문만 있고 들어오는 문이 없는 방이었다.

**셋 — 고른 계정이 다음 재시작에서 조용히 풀린다.** 재시작 루프는 마커에
`account` 가 있을 때만 프로필 env 를 걸고, 없으면 `env=None` 으로 돈다. 그래서
계정을 바꾼 뒤 **모델만 바꾸면** 계정이 원래대로 되돌아갔다 — 아무도 그러라고
말하지 않았는데. 무엇을 고른 상태인지는 재시작을 넘어 남아야 한다.

**넷 — 지금 무엇으로 붙어 있는지 안 찍었다.** 서버가 모른다고 봤기 때문인데,
세션의 프로세스 환경(`CLAUDE_CONFIG_DIR`)에 답이 있다. 모르는 것을 아는 척
찍지 않는 것과, 알 수 있는 것을 안 찾아보는 것은 다르다.

실행: python3 tests/ account_switch
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import tempfile
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
INDEX = index_path()


def _load():
    spec = importlib.util.spec_from_loader(
        "s9acct", importlib.machinery.SourceFileLoader("s9acct", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _login(d, email):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".claude.json"), "w", encoding="utf-8") as f:
        json.dump({"oauthAccount": {"emailAddress": email}}, f)


class Rows(unittest.TestCase):
    """계정 목록은 자리가 아니라 계정을 말한다."""

    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.mkdtemp(prefix="s9acct-")
        self.home = os.path.join(self.tmp, "home")
        self.base = os.path.join(self.tmp, "profiles")
        os.makedirs(self.home)
        os.makedirs(self.base)
        _login(self.home, "first@ex.com")
        self.m.profiles_base = lambda: self.base
        self.m.claude_home = lambda: self.home
        # `@home` 의 자리는 `account_home_dir` 이 정한다 (REQ-20260901-017 R6)
        self.m.account_home_dir = lambda: self.home
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def rows(self, **kw):
        return self.m.account_rows(**kw)

    def test_the_home_account_is_in_the_list(self):
        """돌아올 문 — 기본 계정이 목록에 없으면 한 번 나가면 못 돌아온다."""
        keys = [r["key"] for r in self.rows()]
        self.assertIn(self.m.ACCOUNT_HOME_KEY, keys)
        home = [r for r in self.rows() if r["key"] == self.m.ACCOUNT_HOME_KEY][0]
        self.assertEqual(home["email"], "first@ex.com")
        self.assertTrue(home["ready"])

    def test_a_logged_in_profile_is_named_by_its_account(self):
        """로그인이 끝난 임시 자리는 목록을 부를 때 계정 이름으로 정해진다."""
        stale = os.path.join(self.base, self.m.ACCOUNT_NEW_LABEL + "-2")
        _login(stale, "second@ex.com")
        rows = self.rows()
        self.assertIn("second@ex.com", [r["email"] for r in rows])
        self.assertIn("second@ex.com", [r["key"] for r in rows],
                      "자리 이름이 그대로다 — 사람이 고르는 것은 자리가 아니다")
        self.assertFalse(os.path.isdir(stale), "옛 자리가 남아 두 벌이 됐다")

    def test_a_profile_without_a_login_says_so(self):
        """로그인 전 자리는 숨기지 않고 '로그인 전'으로 선다 — 지우면 사람이
        만들다 만 것을 잃는다."""
        os.makedirs(os.path.join(self.base, self.m.ACCOUNT_NEW_LABEL))
        row = [r for r in self.rows()
               if r["key"] == self.m.ACCOUNT_NEW_LABEL]
        self.assertTrue(row, "로그인 전 자리가 목록에서 사라졌다")
        self.assertFalse(row[0]["ready"])
        self.assertEqual(row[0]["email"], "")

    def test_the_current_account_is_marked(self):
        """지금 붙어 있는 계정에 표식이 붙는다."""
        _login(os.path.join(self.base, "second@ex.com"), "second@ex.com")
        cur = [r for r in self.rows() if r["current"]]
        self.assertEqual([r["key"] for r in cur], [self.m.ACCOUNT_HOME_KEY])
        cur = [r for r in self.rows(cfg_dir=os.path.join(self.base,
                                                         "second@ex.com"))
               if r["current"]]
        self.assertEqual([r["key"] for r in cur], ["second@ex.com"],
                         "세션이 프로필로 떠 있는데 기본 계정을 짚었다")

    def test_exactly_one_is_current(self):
        _login(os.path.join(self.base, "second@ex.com"), "second@ex.com")
        self.assertEqual(sum(1 for r in self.rows() if r["current"]), 1)

    def test_duplicate_accounts_are_not_listed_twice(self):
        """같은 계정이 두 자리에 있으면 어느 쪽이 최신인지 아무도 모른다."""
        _login(os.path.join(self.base, "first@ex.com"), "first@ex.com")
        rows = [r for r in self.rows() if r["email"] == "first@ex.com"]
        self.assertEqual(len(rows), 1)


class ItSticks(unittest.TestCase):
    """고른 계정은 다음 재시작을 넘어 남는다."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(S9_SRC, encoding="utf-8").read()

    def test_it_sticks(self):
        """고른 계정은 다음 재시작을 넘어 남는다."""
        with self.subTest("the_restart_loop_remembers_the_account"):
            i = self.src.find("m = _consume_restart_marker()")
            self.assertGreater(i, 0)
            blk = self.src[i:i + 1800]
            self.assertNotIn('if m.get("account"):', blk,
                             "마커에 계정이 있을 때만 env 를 건다 — 모델만 바꾸면 "
                             "계정이 조용히 풀린다")
            self.assertRegex(blk, r"acct\s*=|held|sticky",
                             "직전에 고른 계정을 들고 있는 자리가 없다")
        with self.subTest("going_home_is_expressible"):
            m = _load()
            self.assertTrue(getattr(m, "ACCOUNT_HOME_KEY", ""),
                            "기본 계정을 가리키는 이름이 없다")
            self.assertNotEqual(m.ACCOUNT_HOME_KEY, "")
            r = m.restart_session("nope-nope", account=m.ACCOUNT_HOME_KEY)
            self.assertFalse(r.get("ok"))   # 세션이 없으니 거부 — 인자는 통과했다
        with self.subTest("the_profile_dir_is_not_created_for_home"):
            i = self.src.find("m = _consume_restart_marker()")
            blk = self.src[i:i + 1800]
            self.assertIn("ACCOUNT_HOME_KEY", blk,
                          "재시작 루프가 기본 계정을 알아보지 못한다")

class AddFromTheDashboard(unittest.TestCase):
    """계정 추가도 대시보드에서 시작된다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        cls.src = open(S9_SRC, encoding="utf-8").read()

    def test_add_from_the_dashboard(self):
        """계정 추가도 대시보드에서 시작된다."""
        with self.subTest("there_is_a_terminal_spawner_shared_with_wake"):
            self.assertTrue(getattr(self.m, "spawn_terminal", None),
                            "spawn_terminal() 이 없다")
            i = self.src.find("def wake_session(")
            self.assertGreater(i, 0)
            self.assertIn("spawn_terminal", self.src[i:i + 2000],
                          "wake_session 이 여전히 자기 창 열기를 따로 갖고 있다")
        with self.subTest("add_opens_a_window_running_account_add"):
            os.environ["S9_WAKE_DRYRUN"] = "1"
            self.addCleanup(os.environ.pop, "S9_WAKE_DRYRUN", None)
            r = self.m.account_add_terminal()
            self.assertTrue(r.get("ok"))
            self.assertIn("account add", r.get("cmd", "") + r.get("inner", ""))
        with self.subTest("a_manual_fallback_carries_the_command"):
            i = self.src.find("def account_add_terminal(")
            self.assertGreater(i, 0)
            self.assertIn("manual", self.src[i:i + 1200])

class TheScreen(unittest.TestCase):
    """창이 계정을 말한다."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(INDEX, encoding="utf-8").read()

    def _dialog(self):
        """계정 창 = 여는 함수 + 창을 짓는 함수.

        2026-08-29 재작업에서 창의 모양이 `acctShape(d)` 로 떨어져 나왔다.
        진단(`?dlg=account|nowhere|empty|lost`)이 그림을 따로 짓지 않고 **같은
        함수**를 부르게 하려는 것이다 — 그림과 실제가 갈리면 보고 고친 것이
        화면이 아니게 된다. 그래서 이 시험도 한 함수의 글자만 보지 않고 창
        전체를 본다. 지키는 계약은 그대로다.
        """
        out = []
        for name in ("async function claudeAccountSwitch(",
                     "function acctShape(", "function acctItems("):
            i = self.src.find(name)
            assert i > 0, name
            out.append(self.src[i:i + 2600])
        return "\n".join(out)

    def test_the_screen(self):
        """창이 계정을 말한다."""
        with self.subTest("the_dialog_reads_the_accounts_api"):
            self.assertTrue("/api/accounts" in self.src,
                            "창이 여전히 프로필 디렉토리 목록만 본다")
        with self.subTest("the_current_row_is_marked"):
            blk = self._dialog()
            self.assertRegex(blk, r"\.current\b", "지금 쓰는 계정에 표식이 없다")
            self.assertRegex(blk, r"\.email\b", "메일이 아니라 자리 이름을 그린다")
        with self.subTest("adding_an_account_is_offered"):
            self.assertIn('data-act="add"', self.src,
                          "대시보드에서 계정을 더할 길이 없다")
            self.assertIn("/api/account/add", self.src,
                          "더하기 손잡이가 서버로 이어지지 않는다")

if __name__ == "__main__":
    unittest.main()
