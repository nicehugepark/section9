"""에이전트·스킬은 s9- 이름 공간에 선다 (REQ-20260906-017, 주인 결정 2026-09-06).

범용 역할 이름(designer·tdd …)은 남의 설치와 반드시 겹친다 — 에이전트는 s9-agnt-<역할>,
스킬은 s9-skl-<스킬>. 역할명은 보고·귀속에 그대로 쓰고, 훅이 접두를 벗겨 적는다.

실행: python3 tests/ agent_namespace
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
AG = os.path.join(REPO, "harness", "claude", "agents")
SK = os.path.join(REPO, "harness", "claude", "skills")
S9 = os.path.join(REPO, "bin", "s9")


def _frontmatter_name(path):
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("name:"):
                return ln.split(":", 1)[1].strip()
    return ""


class Namespace(unittest.TestCase):
    def test_n1_every_generated_agent_and_skill_carries_the_namespace(self):
        """N1. 생성된 에이전트 파일·frontmatter name 은 전부 s9-agnt-, 스킬 디렉토리·name 은 전부 s9-."""
        agents = [f for f in os.listdir(AG) if f.endswith(".md") and f != "README.md"]
        self.assertGreaterEqual(len(agents), 20)
        for f in agents:
            self.assertTrue(f.startswith("s9-agnt-"), f)
            self.assertEqual(_frontmatter_name(os.path.join(AG, f)), f[:-3])
        skills = [d for d in os.listdir(SK) if os.path.isdir(os.path.join(SK, d))]
        self.assertGreaterEqual(len(skills), 10)
        for d in skills:
            self.assertTrue(d.startswith("s9-"), d)
            self.assertEqual(_frontmatter_name(os.path.join(SK, d, "SKILL.md")), d)

    def test_n2_agents_load_skills_by_namespaced_name(self):
        """N2. 에이전트가 로드하라는 스킬 목록은 이름 공간 이름이다 — 접두 없는 스킬은 목록에 없다."""
        body = open(os.path.join(AG, "s9-agnt-designer.md"), encoding="utf-8").read()
        listed = [ln[4:-2] for ln in body.splitlines() if ln.startswith("- **") and ln.endswith("**")]
        self.assertIn("s9-skl-browser-verify", listed)
        for name in listed:
            self.assertTrue(name.startswith("s9-"), name)
            self.assertTrue(os.path.isdir(os.path.join(SK, name)), f"{name} 스킬이 없다")

    def test_n3_hook_attribution_strips_the_namespace(self):
        """N3. 훅의 actor 는 sub:<역할>:<id> — s9-agnt-designer 가 아니라 designer."""
        spec = importlib.util.spec_from_loader(
            "s9_audit_agent_ns", importlib.machinery.SourceFileLoader(
                "s9_audit_agent_ns", os.path.join(REPO, "bin", "s9-audit-agent")))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        self.assertEqual(m.actor_for("s9-agnt-designer", "abc12345xyz"), "sub:designer:abc12345")
        self.assertEqual(m.actor_for("designer", "abc12345xyz"), "sub:designer:abc12345")

    def test_n4_actor_normalizer_strips_the_namespace(self):
        """N4. `--agent s9-agnt-designer` 는 문서에 sub:designer 로 남는다(normalize_actor)."""
        root = tempfile.mkdtemp(prefix="s9ns-")
        old = os.environ.get("S9_ROOT"); os.environ["S9_ROOT"] = root
        try:
            spec = importlib.util.spec_from_loader(
                "s9_ns_mod", importlib.machinery.SourceFileLoader("s9_ns_mod", S9))
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        finally:
            if old is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = old
        self.assertEqual(m.normalize_actor("s9-agnt-designer"), "sub:designer")
        self.assertEqual(m.normalize_actor("sub:s9-agnt-designer:abc12345"), "sub:designer:abc12345")
        self.assertEqual(m.normalize_actor("designer"), "sub:designer")

    def test_n5_protocol_names_the_namespaced_delegation_target(self):
        """N5. 규약이 위임 대상 이름(s9-agnt-designer)과 스킬 이름(s9-skl-…)을 말한다."""
        proto = open(os.path.join(REPO, "harness", "common", "PROTOCOL.md"), encoding="utf-8").read()
        self.assertIn("s9-agnt-designer", proto)
        self.assertIn("s9-skl-", proto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
