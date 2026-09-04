"""실행 권위를 갖는 텍스트도 코드다 (REQ-20260902-032).

`projects/<slug>/agents/*.md` 는 워커 프롬프트 서두에 주입되고 `.claude/agents` 로
미러된다. `users/<u>/skills|agents` 는 `~/.claude` 에 symlink 된다. 데이터 경로에
산다는 이유로 s9-guard·CODEOWNERS 보호 밖이었다. 역할(role:) 변경과 토큰 모양의
값도 같은 게이트에서 막는다.

실행: python3 tests/ guard_protected
"""
import importlib.machinery
import importlib.util
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class GuardProtected(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load("s9guard_prot", os.path.join(ROOT, "bin", "s9-guard"))
        cls.m = _load("s9_prot", os.path.join(ROOT, "bin", "s9"))

    # G1. 실행 권위 텍스트는 보호 경로다
    def test_guard_protected(self):
        """GuardProtected 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("g1_executable_text_is_protected"):
                staged = ["projects/acme/agents/worker.md",
                          "projects/acme/agents/reviewer.md",
                          "users/bora/skills/deploy/SKILL.md",
                          "users/bora/agents/helper.md",
                          "bin/s9"]
                self.assertEqual(self.g.protected_hits(staged), staged)

            # G2. 데이터는 종전처럼 보호 밖
        with self.subTest("g2_data_paths_stay_open"):
                staged = ["projects/acme/assets/spec.md", "projects/acme/CONTEXT.md",
                          "vault/requests/2026/09/REQ-x.md", "users/bora/profile.md",
                          "users/bora/config/settings.json"]
                self.assertEqual(self.g.protected_hits(staged), [])

            # G3. role: 줄이 바뀌면 역할 변경, 다른 줄만 바뀌면 아니다
        with self.subTest("g3_role_line_change_is_detected"):
                staged = ["users/bora/profile.md", "users/chan/profile.md"]
                diff = ("diff --git a/users/bora/profile.md b/users/bora/profile.md\n"
                        "--- a/users/bora/profile.md\n+++ b/users/bora/profile.md\n"
                        "@@ -3 +3 @@\n-role: member\n+role: admin\n"
                        "diff --git a/users/chan/profile.md b/users/chan/profile.md\n"
                        "--- a/users/chan/profile.md\n+++ b/users/chan/profile.md\n"
                        "@@ -7 +7 @@\n-machine_accounts: []\n+machine_accounts: [{\"m\": 1}]\n")
                self.assertEqual(self.g.role_change_hits(staged, diff),
                                 ["users/bora/profile.md"])
                self.assertEqual(self.g.role_change_hits(["vault/x.md"], diff), [])
                self.assertEqual(self.g.role_change_hits(staged, ""), [])

            # G4. 토큰 모양의 값은 내용에서 잡는다
        with self.subTest("g4_token_patterns_are_caught"):
                blob = "+  token = 'ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4'\n"
                hits = self.m.secret_leak([], blob, root=ROOT, user="__none__")
                self.assertTrue(any("ghp_" in h for h in hits), hits)
                blob = "+ key: sk-ant-" + "api03-" + "x" * 40
                hits = self.m.secret_leak([], blob, root=ROOT, user="__none__")
                self.assertTrue(any("sk-ant-" in h for h in hits), hits)
                blob = "+ url: github_pat_" + "Z" * 30
                hits = self.m.secret_leak([], blob, root=ROOT, user="__none__")
                self.assertTrue(any("github_pat_" in h for h in hits), hits)
                # 흔한 글자는 잡지 않는다
                self.assertEqual(self.m.secret_leak([], "+ ghp_short\n+ sk-ant\n",
                                                    root=ROOT, user="__none__"), [])

            # G5. CODEOWNERS 도 같은 경로를 안다
        with self.subTest("g5_codeowners_lists_the_paths"):
            with open(os.path.join(ROOT, ".github", "CODEOWNERS"),
                      encoding="utf-8") as f:
                txt = f.read()
            for p in ("/projects/*/agents/", "/users/*/skills/", "/users/*/agents/"):
                self.assertIn(p, txt, f"CODEOWNERS 에 {p} 가 없다")

if __name__ == "__main__":
    unittest.main()
