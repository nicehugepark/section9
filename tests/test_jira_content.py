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
        self.assertIn('sel("j-link-content"', jira)      # Settings › 외부 서비스 폼 select (061 뒤 sel() 헬퍼)
        self.assertIn("PRJ_TEXT.jiraContents", jira)       # 글자는 표 한 곳
        self.assertIn("{slug, key, direction, content, mark}", jira)   # mark 는 REQ-20260909-049

    # ---- 원문에서 「선행 대화」를 뺀다 (REQ-20260910-010) -------------------
    # 채팅으로 온 말이 요청이 될 때, 아직 문서가 없는 직전 메시지들이 원문 앞에
    # 목록으로 접혀 들어간다. 그것은 이 저장소 안에서 맥락을 잇는 장치이지 티켓을
    # 읽는 사람에게 줄 말이 아니다 — 주인 지시 2026-09-10 08:37.
    def _doc(self, original):
        return "---\nid: REQ-1\n---\n\n## Original\n\n" + original + "\n\n## Notes\n"

    def test_s6_the_lead_in_never_reaches_the_ticket(self):
        """앞에 접힌 선행 대화 묶음은 원문에서 걷힌다 — 사람이 한 말만 남는다."""
        head = self.m.CHAT_LEAD_IN_HEAD
        body = self._doc(head + "\n- (08:12) 앞에 한 말\n- (08:13) 또 한 말\n\n"
                         "지라 티켓 본문에 원문을 넣을 때 선행대화는 제외해라.")
        got = self.m.jira_original_of(body)
        self.assertEqual(got, "지라 티켓 본문에 원문을 넣을 때 선행대화는 제외해라.")
        self.assertNotIn("앞에 한 말", got)
        self.assertNotIn(head, got)
        # description 문단에도 실리지 않는다
        lines = self.m.jira_original_lines(body)
        self.assertEqual(lines[0], "원문:")
        self.assertNotIn(head, "\n".join(lines))

    def test_s6b_plain_original_is_untouched(self):
        """묶음이 없으면 원문은 한 글자도 바뀌지 않는다."""
        body = self._doc("그냥 한 말\n\n둘째 문단")
        self.assertEqual(self.m.jira_original_of(body), "그냥 한 말\n\n둘째 문단")

    def test_s6c_a_body_that_is_only_the_lead_in_stays(self):
        """묶음뿐이면 걷지 않는다 — 티켓 본문을 통째로 비우느니 그대로 싣는다."""
        only = self.m.CHAT_LEAD_IN_HEAD + "\n- (08:12) 앞에 한 말"
        self.assertEqual(self.m.jira_original_of(self._doc(only)), only)

    def test_s6d_the_head_line_lives_in_one_place(self):
        """쓰는 쪽과 걷어내는 쪽이 같은 글자를 본다 — 두 벌이면 한쪽만 바뀐다."""
        src = open(os.path.join(HERE, "..", "bin", "s9.py"),
                   encoding="utf-8").read()
        self.assertEqual(src.count('"[선행 대화 — 직전 미문서화 메시지]"'), 1,
                         "머리말 글자가 두 곳 이상에 적혀 있다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
