"""이름이 겹치는 스킬·에이전트 (REQ-20260905-026).

설치가 ~/.claude/agents·skills 에 우리 것을 놓을 때 사용자의 같은 이름이 이미 있으면
덮어쓰지도, 조용히 빠지지도 않는다 — 사용자의 것은 바이트 그대로 남고 우리 것은
`s9-<이름>` 으로 비켜 선다(frontmatter name 도 같이). 다시 설치해도 하나뿐이다.
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


def _load(root):
    old = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            "s9install_coll", importlib.machinery.SourceFileLoader("s9install_coll", INSTALL))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old


class Collision(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9coll-root-")
        self.home = tempfile.mkdtemp(prefix="s9coll-home-")
        self.src_agents = os.path.join(self.root, "harness", "claude", "agents")
        self.src_skills = os.path.join(self.root, "harness", "claude", "skills")
        os.makedirs(self.src_agents); os.makedirs(os.path.join(self.src_skills, "tdd"))
        open(os.path.join(self.src_agents, "designer.md"), "w").write(
            "---\nname: designer\ndescription: 우리 디자이너\n---\n본문\n")
        open(os.path.join(self.src_agents, "architect.md"), "w").write(
            "---\nname: architect\ndescription: 우리 아키텍트\n---\n본문\n")
        open(os.path.join(self.src_skills, "tdd", "SKILL.md"), "w").write(
            "---\nname: tdd\ndescription: 우리 tdd\n---\n본문\n")
        self.dst_agents = os.path.join(self.home, "agents")
        self.dst_skills = os.path.join(self.home, "skills")
        os.makedirs(self.dst_agents); os.makedirs(os.path.join(self.dst_skills, "tdd"))
        self.theirs = "---\nname: designer\ndescription: 내 디자이너\n---\n내 본문\n"
        open(os.path.join(self.dst_agents, "designer.md"), "w").write(self.theirs)
        open(os.path.join(self.dst_skills, "tdd", "SKILL.md"), "w").write("---\nname: tdd\n---\n내 tdd\n")
        self.m = _load(self.root)
        self.m.PLACED.clear(); self.m.COLLIDED.clear()
        self.m.say = lambda *a, **k: None

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True); shutil.rmtree(self.home, ignore_errors=True)

    def _install(self):
        self.m.PLACED.clear(); self.m.COLLIDED.clear()
        self.m.link_into(self.src_agents, self.dst_agents, "agent(공용)")
        self.m.link_into(self.src_skills, self.dst_skills, "skill(공용)")
        self.m._write_placed(self.home)

    def test_c1_theirs_stays_ours_steps_aside_with_renamed_frontmatter(self):
        """C1. 사용자의 designer.md 는 바이트 그대로, 우리 것은 s9-designer.md 로 서고 name 도 s9-designer 다."""
        self._install()
        self.assertEqual(open(os.path.join(self.dst_agents, "designer.md")).read(), self.theirs)
        alt = os.path.join(self.dst_agents, "s9-designer.md")
        self.assertTrue(os.path.isfile(alt) and not os.path.islink(alt))
        body = open(alt).read()
        self.assertIn("name: s9-designer\n", body); self.assertIn("우리 디자이너", body)
        # 겹치지 않는 것은 제 이름의 링크
        self.assertTrue(os.path.islink(os.path.join(self.dst_agents, "architect.md")))
        self.assertFalse(os.path.exists(os.path.join(self.dst_agents, "s9-architect.md")))

    def test_c2_skill_directory_collides_the_same_way(self):
        """C2. 스킬 디렉토리도 같다 — 내 tdd 는 그대로, 우리 것은 s9-tdd/ 이고 SKILL.md name 이 s9-tdd."""
        self._install()
        self.assertEqual(open(os.path.join(self.dst_skills, "tdd", "SKILL.md")).read(), "---\nname: tdd\n---\n내 tdd\n")
        sk = os.path.join(self.dst_skills, "s9-tdd", "SKILL.md")
        self.assertTrue(os.path.isfile(sk)); self.assertIn("name: s9-tdd\n", open(sk).read())
        self.assertTrue(os.path.exists(os.path.join(self.dst_skills, "s9-tdd", ".section9-copy")))

    def test_c3_reinstall_is_idempotent_and_manifest_lists_it(self):
        """C3. 두 번 설치해도 하나뿐이고 목록 파일이 겹침을 적는다 — uninstall 이 이것만 걷는다."""
        self._install(); self._install()
        names = sorted(os.listdir(self.dst_agents))
        self.assertEqual(names, ["architect.md", "designer.md", "s9-designer.md"])
        man = json.load(open(self.m.placed_manifest_path(self.home)))
        self.assertEqual([c["name"] for c in man["collided"] if c["kind"] == "agent"], ["designer"])
        placed = {e["name"]: e["how"] for e in man["placed"]}
        self.assertEqual(placed.get("s9-designer"), "copy"); self.assertEqual(placed.get("architect.md"), "link")

    def test_c4_when_theirs_is_removed_ours_takes_its_own_name_back(self):
        """C4. 사용자가 제 것을 치우면 다음 설치에서 우리 것이 제 이름으로 서고 비켜 선 사본은 걷힌다."""
        self._install()
        os.remove(os.path.join(self.dst_agents, "designer.md"))
        self._install()
        self.assertTrue(os.path.islink(os.path.join(self.dst_agents, "designer.md")))
        self.assertFalse(os.path.exists(os.path.join(self.dst_agents, "s9-designer.md")),
                         "비켜 선 사본이 남으면 designer 가 둘이 된다")


if __name__ == "__main__":
    unittest.main()
