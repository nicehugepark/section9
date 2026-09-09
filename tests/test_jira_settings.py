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
                                           "direction": "push", "content": "card", "mark": "on"}])

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


class JiraEnabledSwitch(unittest.TestCase):
    """사람이 Jira 를 끌 수 있다 (REQ-20260909-080) — 판정은 jira_enabled_for 한 곳이고
    화면(enabled)·내보내기(jira_export_wanted)·되받기(jira_pull_targets) 셋이 그것을 본다."""

    SITE = "https://ex.atlassian.net"

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9jira-e-")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        os.environ.pop("S9_SESSION", None)
        name = "s9jirae_" + os.path.basename(self.root)
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

    def link_project(self, direction="push"):
        self.m.do_project_add("pay", name="결제", summary="", actor="hong")
        self.m.do_project_jira_set("pay", actor="hong", site=self.SITE,
                                   project_key="MP1", direction=direction)

    def new_request(self, user="hong", title="환불 API"):
        import contextlib
        import io as _io
        import types
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="환불을 돕는다", goal="환불이 된다",
            status="open", size="M", priority=None, user=user, assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project="pay", project_tag=None, body="환불이 안 된다", body_file=None,
            origin="human", agent="")
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def test_e1_an_explicit_switch_wins_over_everything(self):
        m = self.m
        self.assertIs(m.jira_state("hong")["enabled"], False)   # S3 아무것도 없으면 꺼짐
        self.assertIs(m.jira_state("")["enabled"], False)
        m.do_user_config_set("hong", "jira_enabled", "on")      # S1 명시가 이긴다
        self.assertIs(m.jira_state("hong")["enabled"], True)
        m.do_user_config_set("hong", "jira_enabled", "off")
        m.do_user_config_set("hong", "jira_site", self.SITE)
        self.link_project()
        self.assertIs(m.jira_state("hong")["enabled"], False,
                      "파생 조건이 다 갖춰져도 명시한 off 가 이겨야 한다")

    def test_e2_users_who_already_use_jira_stay_on(self):
        m = self.m                                             # S2 회귀
        m.do_user_config_set("hong", "jira_site", self.SITE)
        self.assertIs(m.jira_state("hong")["enabled"], True)
        m.do_user_config_set("hong", "jira_site", "")           # 주소를 지워도
        self.assertIs(m.jira_state("hong")["enabled"], False)
        self.link_project()                                    # 이은 프로젝트가 있으면 켜짐
        self.assertIs(m.jira_state("hong")["enabled"], True)

    def test_e3_off_stops_the_export_but_never_the_hand(self):
        m = self.m
        self.link_project()
        rid = self.new_request()
        meta, _ = m.read_doc(m.find_path(rid))
        self.assertEqual(m.jira_export_wanted(meta)[1], "", "켜진 동안은 종전대로 나간다")
        m.do_user_config_set("hong", "jira_enabled", "off")
        j, why = m.jira_export_wanted(meta)                    # S4
        self.assertIsNone(j)
        self.assertIn("꺼져 있다", why)
        self.assertEqual(m.jira_export_wanted(meta, manual=True)[1], "",
                         "s9 jira create 는 사람이 그 자리에서 시킨 것이라 막지 않는다")  # S5
        meta_nouser = dict(meta, user="")                      # S6
        self.assertEqual(m.jira_export_wanted(meta_nouser)[1], "")

    def test_e4_pull_skips_the_requests_of_a_disabled_owner(self):
        m = self.m                                             # S7
        self.link_project(direction="both")
        rid = self.new_request()
        path = m.find_path(rid)
        meta, body = m.read_doc(path)
        meta["jira"] = {"key": "MP1-1", "site": self.SITE}
        m.write_doc(path, meta, body)
        m.rebuild_index(quiet=True)
        self.assertEqual(m.jira_pull_targets(), {"pay": {"MP1-1": rid}})
        m.do_user_config_set("hong", "jira_enabled", "off")
        self.assertEqual(m.jira_pull_targets(), {})
        m.do_user_config_set("hong", "jira_enabled", "on")
        self.assertEqual(m.jira_pull_targets(), {"pay": {"MP1-1": rid}})


if __name__ == "__main__":
    unittest.main(verbosity=2)
