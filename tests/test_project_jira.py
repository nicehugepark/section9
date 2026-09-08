"""프로젝트의 Jira 연동 설정 — `s9 project jira <slug> set|show|unset` (REQ-20260908-072).

프로젝트 문서 frontmatter `jira:` 한 덩이가 팀의 연결이고, 비밀(API token)은 여기
오지 않는다. 기본값: direction push · create_on open · export all ·
export_origin human(주인 지시 2026-09-08 21:43 — 사람이 직접 만든 요청만).

실행: python3 tests/ project_jira
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
S9CLI = os.path.join(HERE, "..", "bin", "s9")


class ProjectJira(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER")}
        self.root = tempfile.mkdtemp(prefix="s9pjira-")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_USER", None)
        name = "s9pjira_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.m.do_user_add("vera")
        self.m.do_project_add("pay", name="결제", summary="", actor="hong")
        self.m.do_member_set("pay", "vera", role="viewer", actor="hong") \
            if hasattr(self.m, "do_member_set") else None

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def test_k1_set_writes_the_block_with_defaults_and_history(self):
        res = self.m.do_project_jira_set(
            "pay", actor="hong", site="https://x.atlassian.net", project_key="MP1")
        j = res["jira"]
        self.assertEqual((j["site"], j["project_key"]), ("https://x.atlassian.net", "MP1"))
        self.assertEqual((j["issue_type"], j["direction"], j["create_on"],
                          j["export"], j["export_origin"]),
                         ("Task", "push", "open", "all", "human"))
        meta, body, _ = self.m.load_project("pay")
        self.assertEqual(meta["jira"]["project_key"], "MP1")
        self.assertIn("Jira 연동 설정", body)

    def test_k2_show_reads_it_and_none_means_no_link(self):
        self.assertIsNone(self.m.project_jira("pay"))
        self.m.do_project_jira_set("pay", actor="hong", site="x.atlassian.net", project_key="mp1")
        self.assertEqual(self.m.project_jira("pay")["project_key"], "MP1")
        r = subprocess.run([S9CLI, "project", "jira", "pay", "show"], capture_output=True,
                           text=True, env={**os.environ, "S9_ROOT": self.root, "S9_USER": "hong"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("MP1", r.stdout)
        self.assertIn("export_origin", r.stdout)

    def test_k3_choices_are_enforced(self):
        for k, bad in (("direction", "sideways"), ("export", "some"),
                       ("export_origin", "robots"), ("create_on", "done")):
            with self.assertRaises(ValueError, msg=k):
                self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                           project_key="MP1", **{k: bad})
        res = self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                         project_key="MP1", direction="both",
                                         export="size:M+", export_origin="all")
        self.assertEqual((res["jira"]["direction"], res["jira"]["export"],
                          res["jira"]["export_origin"]), ("both", "size:M+", "all"))

    def test_k4_site_is_trimmed_and_key_shape_is_checked(self):
        res = self.m.do_project_jira_set(
            "pay", actor="hong",
            site="https://nicehugepark.atlassian.net/jira/software/projects/MP1/boards/1",
            project_key="MP1")
        self.assertEqual(res["jira"]["site"], "https://nicehugepark.atlassian.net")
        with self.assertRaises(ValueError):
            self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                       project_key="not a key")

    def test_k5_no_secret_lands_in_the_project_document(self):
        with self.assertRaises(ValueError):
            self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                       project_key="MP1", api_token="ATATT3" + "x" * 30)   # 소스에 진짜 꼴을 두면 guard 가 commit 을 막는다
        with self.assertRaises(ValueError):
            self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                       project_key="MP1", issue_type="ATATT3" + "x" * 30)
        self.assertIsNone(self.m.project_jira("pay"))

    def test_k6_only_maintainers_change_it(self):
        with self.assertRaises(ValueError):
            self.m.do_project_jira_set("pay", actor="vera", site="https://x.atlassian.net",
                                       project_key="MP1")

    def test_k7_settings_state_sees_the_link(self):
        self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                   project_key="MP1")
        st = self.m.jira_state("hong")
        self.assertTrue(st["ready"]["project"])
        self.assertEqual(st["projects"][0]["key"], "MP1")

    def test_k8_unset_removes_it(self):
        self.m.do_project_jira_set("pay", actor="hong", site="https://x.atlassian.net",
                                   project_key="MP1")
        self.assertTrue(self.m.do_project_jira_unset("pay", actor="hong")["changed"])
        self.assertIsNone(self.m.project_jira("pay"))
        self.assertFalse(self.m.do_project_jira_unset("pay", actor="hong")["changed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
