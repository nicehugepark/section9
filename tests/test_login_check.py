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
            li = d.login_info(which=which)
            self.assertTrue(li["claude"]["installed"]); self.assertFalse(li["claude"]["logged_in"])
            v = d.login_verdict(li)
            self.assertEqual(v["level"], "warn")
            self.assertIn("/login", v.get("advice") or "")
            open(os.path.join(home, ".credentials.json"), "w").write("{}")
            v = d.login_verdict(d.login_info(which=which))
            self.assertEqual(v["level"], "ok")
        finally:
            if old is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old
