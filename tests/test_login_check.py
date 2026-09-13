"""설치 때 에이전트 로그인을 확인한다 (REQ-20260905-014) — 하네스별 표 하나, 두 벌은 같아야.

실행: python3 tests/ login_check
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

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
        self.assertEqual(d.LOGIN_MARKS, s.LOGIN_MARKS, "s9 code 의 경로가 doctor 와 다른 표를 든다")

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
            # Keychain 항목은 계정의 것이라 **기본 설정 자리(~/.claude)** 에서만
            # 묻는다 — 다른 설정 디렉토리(프로필·시험 자리)에 물려주면 자격증명이
            # 없는 자리가 「로그인됨」이 된다 (REQ-20260906-015, 맥미니 실측: l4 가
            # 임시 자리에서 참을 받았다). 집을 임시 자리로 옮겨 기본 자리를 흉내 낸다.
            fake_home = tempfile.mkdtemp(prefix="s9login5-")
            home = os.path.join(fake_home, ".claude")
            os.makedirs(home)
            with mock.patch("os.path.expanduser",
                            lambda p: p.replace("~", fake_home, 1) if p.startswith("~") else p):
                self.assertTrue(m.login_second_signal("claude", home, platform="darwin", run=run))
                self.assertEqual(calls[0][:3], ["security", "find-generic-password", "-s"])
                self.assertFalse(m.login_second_signal("claude", home, platform="linux", run=run),
                                 "리눅스에서 Keychain 을 묻는다")
                self.assertFalse(m.login_second_signal("codex", home, platform="darwin", run=run))
                other = tempfile.mkdtemp(prefix="s9login5o-")
                n = len(calls)
                self.assertFalse(m.login_second_signal("claude", other, platform="darwin", run=run),
                                 "기본 자리가 아닌 설정 디렉토리에 Keychain 을 물려줬다")
                self.assertEqual(len(calls), n, "다른 자리인데 Keychain 을 물었다")

    def test_l6_the_three_second_signals_are_one(self):
        """L6. 세 벌(s9·install·doctor)의 둘째 신호가 같은 코드다 — 갈리면 설치·진단·s9 code 가 다른 말을 한다."""
        import inspect
        srcs = [inspect.getsource(_load(n, p).login_second_signal)
                for n, p in (("s9_l6", S9), ("s9i_l6", INSTALL), ("s9d_l6", DOCTOR))]
        self.assertEqual(srcs[0], srcs[1]); self.assertEqual(srcs[0], srcs[2])

    def test_l7_login_is_left_to_claude_own_screen(self):
        """L7. 로그인이 없으면 s9 는 안내 한 줄만 내고 지나간다 — 코드 붙여넣기 화면은 claude 의
        것(끝 몇 자만 보이는 마스킹). 따로 `claude auth login` 을 돌리지 않는다(REQ-20260906-072)."""
        import io, sys as _sys
        s = _load("s9_login7", S9)
        calls = []
        st = lambda: {"claude": {"installed": True, "logged_in": False, "how": ""}}
        out = io.StringIO()
        old = _sys.stdout; _sys.stdout = out
        try:
            r = s.ensure_claude_login(run=lambda argv: calls.append(argv), state=st)
        finally:
            _sys.stdout = old
        self.assertEqual(r, "deferred")
        self.assertEqual(calls, [], "s9 가 제 로그인 단계를 또 돌린다")
        self.assertIn("가려진다", out.getvalue())
        self.assertEqual(s.ensure_claude_login(state=lambda: {"claude": {"installed": False}}), "not-installed")

    def test_l8_usage_credentials_come_from_the_keychain_on_mac(self):
        """L8. 사용량 조회의 자격증명도 맥에서는 Keychain 에서 온다 — 파일이 없어도 (REQ-20260906-071)."""
        s = _load("s9_login8", S9)
        # Keychain 은 **활성 계정**(claude_home = CLAUDE_CONFIG_DIR 또는 ~/.claude)의
        # 것으로만 읽는다 (REQ-20260906-014 · REQ-20260910-040) — 프로필로 뜬 세션도
        # 제 계정을 읽어야 하므로 읽는 조건은 claude_home() 이다. home 을 활성 자리로 세운다.
        fake_home = tempfile.mkdtemp(prefix="s9login8-")
        home = os.path.join(fake_home, ".claude")
        os.makedirs(home)
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            # Keychain 은 항목 이름으로 답한다 — 기본 자리의 이름에만 자격증명이 있다
            class R:
                returncode = 0 if argv[3] == "Claude Code-credentials" else 44
                stdout = ('{"claudeAiOauth": {"accessToken": "t", "subscriptionType": "max"}}'
                          if argv[3] == "Claude Code-credentials" else "")
            return R()
        with mock.patch.object(s, "claude_home", lambda: home):
            self.assertIsNone(s.read_claude_oauth(home, platform="linux", run=run))
            got = s.read_claude_oauth(home, platform="darwin", run=run)
            self.assertEqual(got.get("subscriptionType"), "max")
            self.assertEqual(calls[-1][:3], ["security", "find-generic-password", "-s"])
            other = tempfile.mkdtemp(prefix="s9login8o-")
            n = len(calls)
            # 다른 슬롯은 **제 이름**(경로 해시 접미)으로만 묻는다 (REQ-20260910-014-2n7g)
            # — 기본 자리의 항목을 물려받지 않고, 제 항목이 없으면 없는 것이다.
            self.assertIsNone(s.read_claude_oauth(other, platform="darwin", run=run),
                              "활성 계정이 아닌 슬롯이 Keychain 의 자격증명을 물려받았다")
            asked = [c[3] for c in calls[n:]]
            self.assertTrue(asked and all(a.startswith("Claude Code-credentials-") for a in asked),
                            f"다른 슬롯이 기본 자리의 항목 이름으로 물었다: {asked}")
            with open(os.path.join(home, ".credentials.json"), "w", encoding="utf-8") as f:
                f.write('{"claudeAiOauth": {"accessToken": "f", "subscriptionType": "pro"}}')
            self.assertEqual(s.read_claude_oauth(home, platform="darwin", run=run).get("subscriptionType"), "pro")


    def test_l9_native_install_folder_counts_before_path_catches_up(self):
        """L9. PATH 에 없어도 native 설치기의 자리(~/.local/bin/claude 또는 claude.exe)에 있으면
        설치된 것이고, 안내는 그 경로와 PATH 를 말한다 — Windows 실측 2026-09-13 (REQ-20260913-024):
        install.ps1 이 놓은 claude.exe 를 옛 PATH 의 cmd.exe 가 못 봐 「에이전트 CLI 가 없다」였다."""
        s = _load("s9_login9", S9)
        fake_home = tempfile.mkdtemp(prefix="s9login9-")
        cfg = tempfile.mkdtemp(prefix="s9login9c-")
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = cfg          # 로그인 표식은 보지 않는 자리
        nowhere = lambda exe: None
        try:
            with mock.patch("os.path.expanduser",
                            lambda p: p.replace("~", fake_home, 1) if p.startswith("~") else p):
                st = s.login_state(which=nowhere)["claude"]
                self.assertFalse(st["installed"]); self.assertIsNone(st["path"]); self.assertEqual(st["hint"], "")
                os.makedirs(os.path.join(fake_home, ".local", "bin"))
                exe = os.path.join(fake_home, ".local", "bin", "claude.exe")
                open(exe, "w").close()
                st = s.login_state(which=nowhere)["claude"]
                self.assertTrue(st["installed"]); self.assertFalse(st["logged_in"])
                self.assertEqual(st["path"], exe); self.assertFalse(st["on_path"])
                self.assertIn("PATH", st["hint"]); self.assertIn(exe, st["hint"])
                on = s.login_state(which=lambda e: "/usr/bin/claude" if e == "claude" else None)["claude"]
                self.assertTrue(on["on_path"]); self.assertEqual(on["hint"], "", "PATH 에 있는데 PATH 를 말한다")
        finally:
            if old is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old

    def test_l10_the_three_cli_lookups_are_one(self):
        """L10. 세 벌(s9·install·doctor)의 agent_cli_path 가 같은 코드다 — L6 과 같은 결."""
        import inspect
        srcs = [inspect.getsource(_load(n, p).agent_cli_path)
                for n, p in (("s9_l10", S9), ("s9i_l10", INSTALL), ("s9d_l10", DOCTOR))]
        self.assertEqual(srcs[0], srcs[1]); self.assertEqual(srcs[0], srcs[2])
        d = _load("s9d_l10v", DOCTOR)
        li = {"claude": {"installed": True, "logged_in": False, "how": "/login",
                         "hint": "claude 는 PATH 밖에 있다(X)"}}
        self.assertIn("PATH 밖", d.login_verdict(li).get("advice") or "")

    def test_l11_s9_code_launches_the_found_path_when_it_is_off_path(self):
        """L11. PATH 밖에서 찾은 claude 는 s9 code 가 그 전체 경로로 띄우고 안내에 경로를 말한다;
        PATH 에 있으면 이름 그대로다(OS 가 PATHEXT 로 고른다)."""
        import io, sys as _sys
        s = _load("s9_login11", S9)
        fake_home = tempfile.mkdtemp(prefix="s9login11-")
        exe = os.path.join(fake_home, ".local", "bin", "claude")
        os.makedirs(os.path.dirname(exe)); open(exe, "w").close()
        with mock.patch("os.path.expanduser",
                        lambda p: p.replace("~", fake_home, 1) if p.startswith("~") else p):
            self.assertEqual(s.claude_exe(which=lambda e: None), exe)
            self.assertEqual(s.claude_exe(which=lambda e: "/usr/bin/claude"), "claude")
            os.remove(exe)
            self.assertEqual(s.claude_exe(which=lambda e: None), "claude", "없으면 이름 그대로 — 실행 자리가 말한다")
        st = lambda: {"claude": {"installed": True, "logged_in": True, "how": "",
                                 "hint": f"claude 는 PATH 밖에 있다({exe})"}}
        out = io.StringIO(); old = _sys.stdout; _sys.stdout = out
        try:
            r = s.ensure_claude_login(state=st)
        finally:
            _sys.stdout = old
        self.assertEqual(r, "ok"); self.assertIn(exe, out.getvalue()); self.assertIn("PATH", out.getvalue())
