"""이름 공간 안에서 겹치는 스킬·에이전트 (REQ-20260905-026 → REQ-20260906-017).

우리 항목은 전부 s9-agnt-·s9-skl- 이름 공간에 있어 남의 범용 이름(designer·tdd)과 겹치지
않는다. 그 이름 공간 안에 사용자가 일부러 지은 같은 이름이 있으면 덮어쓰지도 조용히
빠지지도 않는다 — 사용자의 것은 바이트 그대로, 우리 것은 놓지 않고 완료 화면에 말한다.
옛 판이 접두 없이 놓았던 우리 링크(designer.md)는 다음 설치가 걷는다.
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
        os.makedirs(self.src_agents); os.makedirs(os.path.join(self.src_skills, "s9-skl-tdd"))
        open(os.path.join(self.src_agents, "s9-agnt-designer.md"), "w").write(
            "---\nname: s9-agnt-designer\ndescription: 우리 디자이너\n---\n본문\n")
        open(os.path.join(self.src_agents, "s9-agnt-architect.md"), "w").write(
            "---\nname: s9-agnt-architect\ndescription: 우리 아키텍트\n---\n본문\n")
        open(os.path.join(self.src_skills, "s9-skl-tdd", "SKILL.md"), "w").write(
            "---\nname: s9-skl-tdd\ndescription: 우리 tdd\n---\n본문\n")
        self.dst_agents = os.path.join(self.home, "agents")
        self.dst_skills = os.path.join(self.home, "skills")
        os.makedirs(self.dst_agents); os.makedirs(os.path.join(self.dst_skills, "tdd"))
        # 사용자의 범용 이름 — 우리와 겹치지 않는다
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

    def test_c1_generic_names_never_collide(self):
        """C1. 사용자의 designer.md·tdd/ 는 바이트 그대로이고 우리 것은 제 이름 공간에 나란히 선다 — 겹침 0."""
        self._install()
        self.assertEqual(open(os.path.join(self.dst_agents, "designer.md")).read(), self.theirs)
        self.assertTrue(os.path.islink(os.path.join(self.dst_agents, "s9-agnt-designer.md")))
        self.assertTrue(os.path.islink(os.path.join(self.dst_skills, "s9-skl-tdd")))
        self.assertEqual(self.m.COLLIDED, [])

    def test_c2_theirs_inside_our_namespace_is_kept_and_reported(self):
        """C2. 사용자가 일부러 s9-agnt-designer 를 지어 두었으면 덮어쓰지 않고 놓지 않으며 알린다."""
        mine = "---\nname: s9-agnt-designer\ndescription: 내 것\n---\n내 본문\n"
        open(os.path.join(self.dst_agents, "s9-agnt-designer.md"), "w").write(mine)
        self._install()
        self.assertEqual(open(os.path.join(self.dst_agents, "s9-agnt-designer.md")).read(), mine)
        self.assertEqual([c["name"] for c in self.m.COLLIDED], ["s9-agnt-designer"])
        self.assertTrue(os.path.islink(os.path.join(self.dst_agents, "s9-agnt-architect.md")))

    def test_c3_reinstall_is_idempotent_and_manifest_lists_it(self):
        """C3. 다시 설치해도 하나뿐이고 매니페스트가 놓은 것을 안다."""
        self._install(); self._install()
        names = sorted(n for n in os.listdir(self.dst_agents))
        self.assertEqual(names, ["designer.md", "s9-agnt-architect.md", "s9-agnt-designer.md"])
        man = json.load(open(os.path.join(self.home, ".section9-install.json")))
        placed = {e["name"]: e["how"] for e in man["placed"]}
        self.assertEqual(placed.get("s9-agnt-designer.md"), "link")
        self.assertEqual(placed.get("s9-skl-tdd"), "link")

    def test_c4_old_unprefixed_links_of_ours_are_swept(self):
        """C4. 옛 판이 접두 없이 놓은 우리 링크(architect.md → 저장소)는 다음 설치가 걷는다 — 남의 것은 남는다."""
        old = os.path.join(self.dst_agents, "architect.md")
        os.symlink(os.path.join(self.src_agents, "s9-agnt-architect.md"), old)
        man = {"placed": [{"kind": "agent", "name": "architect.md", "path": old, "how": "link"}],
               "collided": []}
        json.dump(man, open(os.path.join(self.home, ".section9-install.json"), "w"))
        self._install()
        self.assertFalse(os.path.lexists(old), "옛 이름이 남으면 architect 가 둘이 된다")
        self.assertTrue(os.path.exists(os.path.join(self.dst_agents, "designer.md")), "남의 것은 그대로")
        self.assertTrue(os.path.islink(os.path.join(self.dst_agents, "s9-agnt-architect.md")))


if __name__ == "__main__":
    unittest.main()
