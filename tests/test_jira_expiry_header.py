"""만료가 다가온 Jira token 은 막히기 전에 머리에 선다 (REQ-20260914-015-62x6).

주인 물음 2026-09-15 09:28: 「지라 토큰 만료 관련 경고는 어디서 확인할 수 있는 거야?」
— 그때까지 만료 임박은 Settings › 외부 서비스 › Jira 의 「token 만료일」 줄과
`s9 jira ping` 의 출력에만 있었다. 열어 보지 않으면 모르는 자리다(어제 만료를
모른 채 닷새를 보낸 자리와 같다). 계약: whoami 가 `jira_expiry` 를 실으면 화면 머리가
계정 줄 옆에 그 문장을 그린다 — 7일 안(soon)·만료 뒤(expired)에만, 발신함이 막혀
`jira_block` 이 서 있으면 그쪽이 이긴다(둘을 같이 싣지 않는다).
실행: python3 tests/ jira_expiry_header
"""
import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import os
import shutil
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
NOTICE = os.path.join(HERE, "..", "web", "app", "notice.js")


class ExpiryReachesTheHeader(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_USER", "S9_AUTO_RESUME", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jx-")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_USER"] = "hong"
        for k in ("S9_AUTO_RESUME", "S9_SESSION"):
            os.environ.pop(k, None)
        name = "s9jx_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.chat_target = lambda sid8=None, user=None: {"session": "sid00000"}
        m._inbox_watch_alive = lambda sid: bool(sid)
        m.do_project_jira_set("pay", actor="hong", site="https://ex.atlassian.net",
                              project_key="MP1")
        m.do_user_config_set("hong", "jira_site", "https://ex.atlassian.net")
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        m.secret_write("hong", m.JIRA_SECRET_KEY, "fake-token-for-tests-0123456789")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def new_request(self, title):
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="환불을 돕는다", goal="환불이 된다",
            status="open", size="S", priority=None, user="hong", assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project="pay", project_tag=None, body="본문", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def in_days(self, n):
        return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()

    # 정상 — 사흘 뒤 만료면 머리에 선다
    def test_soon_is_carried_by_whoami(self):
        self.m.do_user_config_set("hong", "jira_token_expires", self.in_days(3))
        w = self.m.whoami_info()
        self.assertIn("jira_expiry", w, "만료가 다가왔는데 whoami 가 싣지 않았다")
        self.assertEqual(w["jira_expiry"]["days"], 3)
        self.assertEqual(w["jira_expiry"]["level"], "soon")
        self.assertIn("3일 뒤", w["jira_expiry"]["line"])
        self.assertNotIn("jira_block", w)

    # 경계 — 멀리 남았으면 조용하다
    def test_far_expiry_is_silent(self):
        self.m.do_user_config_set("hong", "jira_token_expires", self.in_days(90))
        self.assertNotIn("jira_expiry", self.m.whoami_info())

    # 경계 — 만료가 지났고 발신함은 비어 있으면 「만료됐습니다」로 선다
    def test_expired_with_empty_outbox_still_speaks(self):
        self.m.do_user_config_set("hong", "jira_token_expires", self.in_days(-1))
        w = self.m.whoami_info()
        self.assertIn("jira_expiry", w)
        self.assertEqual(w["jira_expiry"]["level"], "expired")
        self.assertIn("만료됐습니다", w["jira_expiry"]["line"])

    # 회귀 — 발신함이 막혀 있으면 jira_block 이 이기고 jira_expiry 는 싣지 않는다
    def test_block_wins_over_expiry(self):
        self.m.do_user_config_set("hong", "jira_token_expires", self.in_days(-1))
        self.new_request("환불 API")                   # 만료된 token → 발신함에 막힌 채 남는다
        w = self.m.whoami_info()
        self.assertIn("jira_block", w)
        self.assertNotIn("jira_expiry", w, "막힘과 임박을 둘 다 실었다 — 머리에 경고가 둘 선다")

    # 화면 — notice.js 가 그 키를 읽는다
    def test_notice_reads_the_key(self):
        with open(NOTICE, encoding="utf-8") as f:
            js = f.read()
        self.assertIn("jira_expiry", js)
        self.assertIn("je.line", js)


if __name__ == "__main__":
    unittest.main()
