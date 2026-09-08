"""백그라운드 작업자의 Jira 옵트인·감사 (REQ-20260908-077) 와 토큰 만료 (REQ-20260909-002).

실행: python3 tests/ jira_worker
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
S9CLI = os.path.join(HERE, "..", "bin", "s9")


class JiraWorkerAndExpiry(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_AUTO_RESUME", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jw-")
        os.environ["S9_ROOT"] = self.root
        for k in ("S9_USER", "S9_AUTO_RESUME", "S9_SESSION"):
            os.environ.pop(k, None)
        name = "s9jw_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.m.do_user_config_set("hong", "jira_site", "https://ex.atlassian.net")
        self.m.do_user_config_set("hong", "jira_email", "hong@example.com")
        self.m.secret_write("hong", self.m.JIRA_SECRET_KEY, "fake-token-for-tests-0123456789")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def cli(self, *a, env=None):
        e = {**os.environ, "S9_ROOT": self.root, "S9_USER": "hong", **(env or {})}
        return subprocess.run([S9CLI, "jira", *a], capture_output=True, text=True, env=e, timeout=20)

    # -- 077 ----------------------------------------------------------------
    def test_w1_a_worker_is_refused_by_default(self):
        r = self.cli("pull", env={"S9_AUTO_RESUME": "1", "S9_SESSION": "abcd1234"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("백그라운드 작업자는", r.stderr)
        self.assertIn("Jira 쓰게 하기", r.stderr)
        denied, actor = self.m.jira_worker_actor("hong")
        self.assertEqual((denied, actor), ("", "hong"), "사람의 셸은 그대로다")

    def test_w2_opt_in_lets_the_worker_through_with_a_worker_actor(self):
        self.m.do_user_config_set("hong", "auto_resume_jira", "on")
        os.environ["S9_AUTO_RESUME"] = "1"
        os.environ["S9_SESSION"] = "abcd1234-full"
        denied, actor = self.m.jira_worker_actor("hong")
        self.assertEqual((denied, actor), ("", "worker:abcd1234"))
        r = self.cli("pull", env={"S9_AUTO_RESUME": "1", "S9_SESSION": "abcd1234"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_w3_watcher_actor_is_recorded(self):
        """워처가 남기는 actor·via 가 문서에 있다 — 073 의 _jira_write 계약을 못박는다."""
        self.m.do_project_add("pay", name="결제", summary="", actor="hong")
        import contextlib, io, types
        args = types.SimpleNamespace(
            doc_type="request", title="t", summary="s", goal="g", status="open", size="S",
            priority=None, user="hong", assignee=None, tag_list=[], parent=None, derived_from=None,
            relates=None, why="", ref_doc=None, ref_link=None, ref_file=None, needs_os="",
            from_chat="", project="pay", project_tag=None, body="b", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        rid = out.getvalue().split()[0]
        self.m._jira_write(rid, {"key": "MP1-1", "actor": "watcher", "via": "watcher"}, "이슈 MP1-1 생성 by watcher")
        meta, body = self.m.read_doc(self.m.find_path(rid))
        self.assertEqual((meta["jira"]["actor"], meta["jira"]["via"]), ("watcher", "watcher"))
        self.assertIn("jira: 이슈 MP1-1 생성 by watcher", body)

    def test_w5_the_guard_knows_the_token_shape(self):
        blob = "x = '" + "ATATT3" + "x" * 40 + "'"
        hits = [name for pat, name in self.m.TOKEN_PATTERNS if pat.search(blob)]
        self.assertEqual(hits, ["Atlassian API token(ATATT3)"])

    # -- 002 ----------------------------------------------------------------
    def test_e1_expiry_levels(self):
        today = datetime.date(2026, 9, 9)
        self.assertEqual(self.m.jira_token_expiry("hong", today)[2], "")
        self.m.do_user_config_set("hong", "jira_token_expires", "2026-12-31")
        exp, left, level, line = self.m.jira_token_expiry("hong", today)
        self.assertEqual((exp, left, level, line), ("2026-12-31", 113, "ok", ""))
        self.m.do_user_config_set("hong", "jira_token_expires", "2026-09-14")
        exp, left, level, line = self.m.jira_token_expiry("hong", today)
        self.assertEqual((left, level), (5, "soon"))
        self.assertIn("5일 뒤", line)
        self.m.do_user_config_set("hong", "jira_token_expires", "2026-09-01")
        self.assertEqual(self.m.jira_token_expiry("hong", today)[2], "expired")
        st = self.m.jira_state("hong")
        self.assertEqual((st["token_expires"], st["expiry_level"]), ("2026-09-01", "expired"))
        self.assertIn("만료됐습니다", st["expiry_line"])

    def test_e2_bad_dates_are_refused_and_empty_clears(self):
        with self.assertRaises(ValueError):
            self.m.do_user_config_set("hong", "jira_token_expires", "내년쯤")
        self.m.do_user_config_set("hong", "jira_token_expires", "2026-12-31")
        self.m.do_user_config_set("hong", "jira_token_expires", "")
        self.assertEqual(self.m.jira_token_expiry("hong")[0], "")

    def test_e3_e4_an_expired_token_is_never_sent(self):
        self.m.do_user_config_set("hong", "jira_token_expires", "2000-01-01")
        auth, missing = self.m.jira_auth_header("hong")
        self.assertIsNone(auth)
        self.assertEqual(missing, ["API token(만료됨 — 재발급)"])
        res = self.m.jira_ping("hong")
        self.assertFalse(res["ok"])
        self.assertIn("만료됨", res["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
