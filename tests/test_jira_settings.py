"""Settings 「Jira 연동」 판의 준비 항목 (REQ-20260908-079).

주인 지시 2026-09-08 21:30: 시험을 위해 준비할 것을 항목별로 Settings 에 세워라 —
「jira 연동은 선택사항이지 필수 사항이 아니다」. 서버가 준비 n/4 를 세고, 토큰은
있는지만 말하며(값은 어디에도 안 실린다), 주소는 보드 주소를 붙여 넣어도 호스트만
남긴다.

실행: python3 tests/ jira_settings
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class JiraSettings(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER")}
        self.root = tempfile.mkdtemp(prefix="s9jira-")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        name = "s9jira_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def test_j1_nothing_prepared(self):
        st = self.m.jira_state("hong")
        self.assertEqual((st["ready_n"], st["ready_total"]), (0, 4))
        self.assertEqual(st["ready"], {"site": False, "email": False,
                                       "token": False, "project": False})
        self.assertFalse(st["token"])
        self.assertEqual(self.m.jira_state("")["registered"], False)

    def test_j2_three_of_four_and_the_token_value_never_shows(self):
        m = self.m
        m.do_user_config_set("hong", "jira_site", "https://ex.atlassian.net")
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        m.secret_write("hong", m.JIRA_SECRET_KEY, "ATATT3-very-secret-value")
        st = m.jira_state("hong")
        self.assertEqual(st["ready_n"], 3)
        self.assertTrue(st["token"])
        self.assertEqual(st["token_where"], "internal")
        self.assertNotIn("very-secret", json.dumps(st, ensure_ascii=False),
                         "토큰 값이 응답에 실렸다")

    def test_j3_a_linked_project_fills_the_fourth(self):
        m = self.m
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        path = m.find_path("pay") if hasattr(m, "find_path") else None
        pr = m.load_project("pay")
        meta, body = pr[0], pr[1]
        meta["jira"] = {"site": "https://ex.atlassian.net", "project_key": "MP1"}
        m.write_doc(pr[2] if len(pr) > 2 else m.find_path(meta["id"]), meta, body)
        st = m.jira_state("hong")
        self.assertTrue(st["ready"]["project"])
        self.assertEqual(st["projects"], [{"slug": "pay", "key": "MP1",
                                           "site": "https://ex.atlassian.net",
                                           "direction": "push"}])

    def test_j4_a_board_url_is_trimmed_to_the_site(self):
        m = self.m
        m.do_user_config_set(
            "hong", "jira_site",
            "https://nicehugepark.atlassian.net/jira/software/projects/MP1/boards/1")
        self.assertEqual(m.user_config("hong")["jira_site"],
                         "https://nicehugepark.atlassian.net")
        m.do_user_config_set("hong", "jira_site", "ex.atlassian.net/")
        self.assertEqual(m.user_config("hong")["jira_site"], "https://ex.atlassian.net")
        with self.assertRaises(ValueError):
            m.do_user_config_set("hong", "jira_site", "not a url")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class JiraSettingsLink(unittest.TestCase):
    """Settings 에서 프로젝트를 잇는다 (REQ-20260909-015) — 서버가 고를 수 있는 프로젝트를 준다."""

    def setUp(self):
        self._root = os.environ.get("S9_ROOT")
        self.root = tempfile.mkdtemp(prefix="s9jira-l-")
        os.environ["S9_ROOT"] = self.root
        name = "s9jiral_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.m.do_user_add("vera")
        self.m.do_project_add("pay", name="결제", summary="", actor="hong")

    def tearDown(self):
        if self._root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self._root
        shutil.rmtree(self.root, ignore_errors=True)

    def test_s1_manageable_projects_are_listed_for_the_manager_only(self):
        self.assertEqual([m["slug"] for m in self.m.jira_state("hong")["manageable"]], ["pay"])
        self.assertEqual(self.m.jira_state("vera")["manageable"], [])
        self.m.do_project_jira_set("pay", actor="hong", site="https://ex.atlassian.net",
                                   project_key="MP1", direction="both")
        st = self.m.jira_state("hong")
        self.assertEqual(st["projects"][0]["direction"], "both")
