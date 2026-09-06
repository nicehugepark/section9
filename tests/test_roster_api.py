"""Settings 의 에이전트·스킬 절이 읽고 쓰는 로스터 (REQ-20260906-021).

세 범위 — 공용(생성물, 읽기 전용)·프로젝트·사용자(본인). 공용은 저장을 거부하고
원천(gen_roster.py)을 가리킨다. 이름 규칙은 소문자·숫자·하이픈.

실행: python3 tests/ roster_api
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class RosterApi(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9roster-")
        self.home = tempfile.mkdtemp(prefix="s9roster-home-")
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_SESSION", "CLAUDE_CONFIG_DIR")}
        os.environ["S9_ROOT"] = self.root
        os.environ["CLAUDE_CONFIG_DIR"] = self.home
        os.environ.pop("S9_SESSION", None); os.environ.pop("S9_USER", None)
        env = {**os.environ}
        subprocess.run([S9, "init"], env=env, capture_output=True, check=True)
        subprocess.run([S9, "user", "add", "alice"], env=env, capture_output=True)
        subprocess.run([S9, "user", "add", "bob"], env=env, capture_output=True)
        subprocess.run([S9, "project", "add", "px", "--name", "PX", "--user", "alice"], env=env, capture_output=True)
        # 공용 생성물 흉내
        ag = os.path.join(self.root, "harness", "claude", "agents"); os.makedirs(ag)
        open(os.path.join(ag, "s9-agnt-designer.md"), "w").write("---\nname: s9-agnt-designer\ndescription: 화면\n---\n본문\n")
        os.makedirs(os.path.join(self.home, "agents"))
        os.symlink(os.path.join(ag, "s9-agnt-designer.md"), os.path.join(self.home, "agents", "s9-agnt-designer.md"))
        spec = importlib.util.spec_from_loader(
            "s9_roster_t", importlib.machinery.SourceFileLoader("s9_roster_t", S9))
        self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_r1_three_scopes_and_installed_flag(self):
        """R1. 공용(설치됨·읽기 전용)·프로젝트·사용자가 한 목록에 — 사용자 범위는 본인 것만."""
        os.makedirs(os.path.join(self.root, "users", "alice", "agents"))
        open(os.path.join(self.root, "users", "alice", "agents", "helper.md"), "w").write("---\nname: helper\ndescription: 내 것\n---\n")
        rows = self.m.roster_list("alice")
        common = [r for r in rows if r["scope"] == "common"]
        self.assertEqual([(r["name"], r["installed"], r["editable"]) for r in common],
                         [("s9-agnt-designer", True, False)])
        mine = [r for r in rows if r["scope"] == "user"]
        self.assertEqual([(r["owner"], r["name"], r["installed"], r["editable"]) for r in mine],
                         [("alice", "helper", False, True)])
        self.assertEqual([r for r in self.m.roster_list("bob") if r["scope"] == "user"], [],
                         "남의 것은 목록에 안 나온다")

    def test_r2_common_is_refused_and_points_at_the_source(self):
        """R2. 공용은 저장을 거부하고 gen_roster.py 를 가리킨다."""
        with self.assertRaises(ValueError) as cm:
            self.m.roster_save("common", "agent", "", "s9-agnt-designer", "x", "alice")
        self.assertIn("gen_roster.py", str(cm.exception))

    def test_r3_save_writes_frontmatter_name_and_syncs_project_agents(self):
        """R3. 프로젝트 에이전트 저장 → 파일 + name 보강 + .claude/agents/<slug>--<이름>.md 동기화."""
        res = self.m.roster_save("project", "agent", "px", "reviewer", "본문만 썼다\n", "alice")
        self.assertTrue(res["ok"])
        src = os.path.join(self.root, "projects", "px", "agents", "reviewer.md")
        text = open(src, encoding="utf-8").read()
        self.assertTrue(text.startswith("---\nname: reviewer\n"), text[:60])
        self.assertTrue(os.path.exists(os.path.join(self.root, ".claude", "agents", "px--reviewer.md")))
        self.assertTrue(res["installed"])
        got = self.m.roster_read("project", "agent", "px", "reviewer")
        self.assertIn("본문만 썼다", got["content"])

    def test_r4_name_rule_and_ownership(self):
        """R4. 이름은 소문자·숫자·하이픈만; 남의 사용자 항목은 admin 만; 미등록 프로젝트는 거부."""
        with self.assertRaises(ValueError):
            self.m.roster_save("user", "agent", "alice", "Bad Name", "x", "alice")
        with self.assertRaises(ValueError):
            self.m.roster_save("user", "skill", "alice", "mine", "x", "bob")
        with self.assertRaises(ValueError):
            self.m.roster_save("project", "agent", "nope", "a", "x", "alice")
        res = self.m.roster_save("user", "skill", "alice", "mine", "---\nname: mine\ndescription: d\n---\n# mine\n", "alice")
        self.assertTrue(res["ok"])
        self.assertTrue(os.path.isfile(os.path.join(self.root, "users", "alice", "skills", "mine", "SKILL.md")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
