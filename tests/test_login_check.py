"""설치 때 에이전트 로그인을 확인한다 (REQ-20260905-014) — 하네스별 표 하나, 두 벌은 같아야.

실행: python3 tests/ login_check
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(name, path):
    spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class LoginCheck(unittest.TestCase):
    def test_l1_the_two_tables_are_one(self):
        """L1. doctor 와 install 의 LOGIN_MARKS 가 같다 — 갈리면 설치 안내와 진단이 다른 말을 한다."""
        d = _load("s9doc_login", DOCTOR)
        i = _load("s9inst_login", INSTALL)
        s = _load("s9_login", S9)
        self.assertEqual(d.LOGIN_MARKS, i.LOGIN_MARKS)
        self.assertEqual(d.LOGIN_MARKS, s.LOGIN_MARKS, "s9 code 의 문이 doctor 와 다른 표를 든다")

    def test_l2_installed_but_not_logged_in_is_a_warning_with_the_way_in(self):
        """L2. 실행 파일은 있는데 흔적이 없으면 warn 이고 로그인하는 길을 말한다; 있으면 ok."""
        d = _load("s9doc_login2", DOCTOR)
        home = tempfile.mkdtemp(prefix="s9login-")
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = home
        try:
            which = lambda exe: "/usr/bin/claude" if exe == "claude" else None
            no2 = lambda n, h: False          # 둘째 신호(맥 Keychain·.claude.json)는 L4·L5 가 잰다
            li = d.login_info(which=which, second=no2)
            self.assertTrue(li["claude"]["installed"]); self.assertFalse(li["claude"]["logged_in"])
            v = d.login_verdict(li)
            self.assertEqual(v["level"], "warn")
            self.assertIn("/login", v.get("advice") or "")
            open(os.path.join(home, ".credentials.json"), "w").write("{}")
            v = d.login_verdict(d.login_info(which=which, second=no2))
            self.assertEqual(v["level"], "ok")
        finally:
            if old is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old

    def test_l4_oauth_account_in_claude_json_counts_as_logged_in(self):
        """L4. 자격증명 파일이 없어도 설정 디렉토리의 .claude.json 에 oauthAccount 가 있으면 로그인이다."""
        s = _load("s9_login4", S9)
        home = tempfile.mkdtemp(prefix="s9login4-")
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = home
        try:
            which = lambda exe: "/usr/bin/claude" if exe == "claude" else None
            self.assertFalse(s.login_state(which=which)["claude"]["logged_in"])
            with open(os.path.join(home, ".claude.json"), "w", encoding="utf-8") as f:
                f.write('{"oauthAccount": {"emailAddress": "x@y"}}')
            self.assertTrue(s.login_state(which=which)["claude"]["logged_in"])
            self.assertEqual(s.ensure_claude_login(state=lambda: s.login_state(which=which)), "ok")
        finally:
            if old is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old

    def test_l5_mac_keychain_is_the_credential_store(self):
        """L5. 맥의 Claude Code 는 자격증명을 Keychain 에 둔다 — 파일이 없어도 항목이 있으면
        로그인이고, 값은 읽지 않는다(맥미니 실제 발생 2026-09-06 13:32, REQ-20260906-070)."""
        for path, name in ((S9, "s9_login5"), (INSTALL, "s9i_login5"), (DOCTOR, "s9d_login5")):
            m = _load(name, path)
            calls = []

            def run(argv, **kw):
                calls.append(argv)
                class R: returncode = 0
                return R()
            home = tempfile.mkdtemp(prefix="s9login5-")
            self.assertTrue(m.login_second_signal("claude", home, platform="darwin", run=run))
            self.assertEqual(calls[0][:3], ["security", "find-generic-password", "-s"])
            self.assertFalse(m.login_second_signal("claude", home, platform="linux", run=run),
                             "리눅스에서 Keychain 을 묻는다")
            self.assertFalse(m.login_second_signal("codex", home, platform="darwin", run=run))

    def test_l6_the_three_second_signals_are_one(self):
        """L6. 세 벌(s9·install·doctor)의 둘째 신호가 같은 코드다 — 갈리면 설치·진단·s9 code 가 다른 말을 한다."""
        import inspect
        srcs = [inspect.getsource(_load(n, p).login_second_signal)
                for n, p in (("s9_l6", S9), ("s9i_l6", INSTALL), ("s9d_l6", DOCTOR))]
        self.assertEqual(srcs[0], srcs[1]); self.assertEqual(srcs[0], srcs[2])
