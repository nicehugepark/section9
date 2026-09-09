"""Jira content 설정 (REQ-20260909-033) — 프로젝트 jira.content = card(기본) | notes.

card 는 제목·요약·완료 기준·상태, notes 는 card + 노트를 코멘트로. body(원문) 수준은
**없다** — 주인 규칙 「Original/본문은 Jira 로 나가지 않는다」(REQ-20260909-030).
같은 값이 CLI show · Settings(jira_state.projects) · Projects(projects_data) 에 실린다.

실행: python3 tests/ jira_content
"""
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import tempfile
import types
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
WEB = os.path.join(HERE, "..", "web", "app")


class JiraContent(unittest.TestCase):

    def setUp(self):
        self._root = os.environ.get("S9_ROOT")
        self.root = tempfile.mkdtemp(prefix="s9jira-c-")
        os.environ["S9_ROOT"] = self.root
        name = "s9jirac_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.m.do_project_add("pay", name="결제", summary="", actor="hong")

    def tearDown(self):
        if self._root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self._root
        shutil.rmtree(self.root, ignore_errors=True)

    def show(self):
        args = types.SimpleNamespace(action="jira", slug="pay", member_action="show",
                                     user="hong")
        out = io.StringIO()
        with redirect_stdout(out):
            self.m.cmd_project(args)
        return out.getvalue()

    def project_payload(self):
        return next(p for p in self.m.projects_data()["projects"] if p["slug"] == "pay")

    def test_s1_default_is_card_everywhere(self):
        res = self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                         project_key="MP1")
        self.assertEqual(res["jira"]["content"], "card")
        self.assertEqual(self.m.project_jira("pay")["content"], "card")
        self.assertRegex(self.show(), r"content\s+card")
        self.assertEqual(self.m.jira_state("hong")["projects"][0]["content"], "card")
        self.assertEqual(self.project_payload()["jira"]["content"], "card")

    def test_s2_notes_is_stored_and_shown(self):
        self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                   project_key="MP1")
        res = self.m.do_project_jira_set("pay", actor="hong", content="notes")
        self.assertEqual(res["jira"]["content"], "notes")
        self.assertEqual(res["jira"]["direction"], "push", "content 가 다른 칸을 건드렸다")
        meta, _body, _ = self.m.load_project("pay")
        self.assertEqual(meta["jira"]["content"], "notes")
        self.assertRegex(self.show(), r"content\s+notes")
        self.assertEqual(self.m.jira_state("hong")["projects"][0]["content"], "notes")
        self.assertEqual(self.project_payload()["jira"]["content"], "notes")

    def test_s3_unknown_value_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                       project_key="MP1", content="sideways")
        self.assertIn("card | notes", str(cm.exception))

    def test_s4_regression_there_is_no_body_level(self):
        """원문(body)을 내보내는 수준은 만들지 않는다 — 선택지에 없어야 누구도 못 켠다."""
        self.assertNotIn("body", self.m.JIRA_PROJECT_CHOICES["content"])
        with self.assertRaises(ValueError):
            self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                       project_key="MP1", content="body")
        self.assertIsNone(self.m.project_jira("pay"), "거절됐는데 연동이 섰다")

    def test_s5_both_screens_have_the_select_and_the_words_live_in_one_place(self):
        prj = open(os.path.join(WEB, "project.js"), encoding="utf-8").read()
        jira = open(os.path.join(WEB, "jira.js"), encoding="utf-8").read()
        table = re.search(r"const PRJ_TEXT = \{([\s\S]*?)\n\};", prj).group(1)
        self.assertIn('kJiraContent: "내보내는 것"', table)
        self.assertIn('["card", "카드 (제목·요약·완료 기준·상태)"]', table)
        self.assertIn('["notes", "카드 + 노트 (노트를 코멘트로)"]', table)
        self.assertNotIn('"body"', table, "화면에 body 선택지가 있다")
        self.assertIn("data-pjjiracontent", prj)          # Projects 화면 select
        self.assertIn('{content: jcSel.value}', prj)       # 저장은 /api/project/jira 한 길
        self.assertIn('id="j-link-content"', jira)         # Settings › 외부 서비스 폼 select
        self.assertIn("PRJ_TEXT.jiraContents", jira)       # 글자는 표 한 곳
        self.assertIn("{slug, key, direction, content}", jira)


if __name__ == "__main__":
    unittest.main(verbosity=2)
