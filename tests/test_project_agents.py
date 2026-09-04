"""프로젝트 에이전트 체계 테스트 (REQ-20260824-038).

projects/<slug>/agents/*.md → .claude/agents/<slug>--이름.md 멱등 동기화
(매니페스트 기반 정리, 수동 에이전트 불가침) + 무인 워커 스폰 프롬프트에
프로젝트 worker.md 봉투 주입 + 스캐폴드/안내.

격리: S9_ROOT=mktemp. 실행: python3 tests/test_project_agents.py
"""
import importlib.machinery
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-session")


class TestProjectAgents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9agents-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "alice"}
        cls.env.pop("S9_SESSION", None)

        def cli(*argv, expect=0):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=15,
                               stdin=subprocess.DEVNULL)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "alice")
        cli("project", "add", "alpha", "--name", "Alpha", "--user", "alice")
        cli("project", "add", "beta", "--name", "Beta", "--user", "alice")

    def adir(self, slug):
        return os.path.join(self.tmp, "projects", slug, "agents")

    def dst(self, name):
        return os.path.join(self.tmp, ".claude", "agents", name)

    def write_agent(self, slug, fn, body):
        os.makedirs(self.adir(slug), exist_ok=True)
        with open(os.path.join(self.adir(slug), fn), "w") as f:
            f.write(body)

    def sync(self):
        return self.cli("project", "agents", "sync").stdout

    # A1+A4. 동기화·네임스페이스: 두 프로젝트 동명 에이전트가 slug 접두로 미러
    def test_test_project_agents(self):
        """TestProjectAgents 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_a4_sync_and_namespace"):
                self.write_agent("alpha", "reviewer.md", "# alpha reviewer\nA규정")
                self.write_agent("beta", "reviewer.md", "# beta reviewer\nB규정")
                out = self.sync()
                self.assertIn("alpha--reviewer.md", out)
                self.assertIn("beta--reviewer.md", out)
                with open(self.dst("alpha--reviewer.md")) as f:
                    self.assertIn("A규정", f.read())
                with open(self.dst("beta--reviewer.md")) as f:
                    self.assertIn("B규정", f.read())

            # A2. 멱등·갱신: 무변경 no-op, 원본 변경 시만 재복사
        with self.subTest("a2_idempotent_update"):
                self.write_agent("alpha", "fixer.md", "v1")
                self.sync()
                out = self.sync()  # 무변경 재실행
                self.assertNotIn("+ alpha--fixer.md", out)
                self.write_agent("alpha", "fixer.md", "v2")
                out = self.sync()
                self.assertIn("+ alpha--fixer.md", out)
                with open(self.dst("alpha--fixer.md")) as f:
                    self.assertEqual(f.read(), "v2")

            # A3. 정리 격리: 원본 삭제 → 관리 파일만 제거, 수동 파일 불가침
        with self.subTest("a3_prune_managed_only"):
                self.write_agent("alpha", "temp.md", "x")
                self.sync()
                self.assertTrue(os.path.exists(self.dst("alpha--temp.md")))
                manual = self.dst("hand--made.md")
                os.makedirs(os.path.dirname(manual), exist_ok=True)
                with open(manual, "w") as f:
                    f.write("수동 에이전트")
                os.remove(os.path.join(self.adir("alpha"), "temp.md"))
                out = self.sync()
                self.assertIn("- alpha--temp.md", out)
                self.assertFalse(os.path.exists(self.dst("alpha--temp.md")))
                self.assertTrue(os.path.exists(manual))  # 매니페스트 밖 — 불가침

            # A5. 훅 연동: SessionStart가 sync 수행
        with self.subTest("a5_hook_syncs"):
                self.write_agent("beta", "hooked.md", "훅 동기화 대상")
                r = subprocess.run([HOOK, "start"],
                                   input=json.dumps({"session_id": "agenthook-x",
                                                     "source": "startup"}),
                                   capture_output=True, text=True,
                                   env={**self.env, "S9_PORT": "1"}, timeout=20)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(os.path.exists(self.dst("beta--hooked.md")))

            # A6. 워커 봉투: 프로젝트 worker.md 가 반려 스폰 프롬프트 서두에 주입,
            #     프로젝트 무관 REQ는 미주입
        with self.subTest("a6_worker_preamble"):
                self.write_agent("alpha", "worker.md", "알파 전용 워커 규정: 신중히.")
                loader = importlib.machinery.SourceFileLoader("s9agmod", S9)
                env_bak = {k: os.environ.get(k) for k in
                           ("S9_ROOT", "S9_MACHINE", "S9_USER")}
                os.environ.update({"S9_ROOT": self.tmp, "S9_MACHINE": "testbox",
                                   "S9_USER": "alice"})
                try:
                    mod = loader.load_module()
                    pre = mod._project_agent_preamble("alpha")
                    self.assertIn("알파 전용 워커 규정", pre)
                    # REQ-20260902-044: 서두 규정은 출처 봉투 안의 데이터로 실린다
                    self.assertIn("프로젝트 지침(projects/alpha/agents/worker.md)", pre)
                    self.assertTrue(pre.startswith(mod.ENVELOPE_WARNING), pre[:80])
                    self.assertEqual(mod._project_agent_preamble(""), "")
                    self.assertEqual(mod._project_agent_preamble("beta"), "")  # 파일 없음
                    # 스폰 통합: _spawn_rework 프롬프트에 봉투 포함
                    self.cli("user", "config", "alice", "auto_resume", "on")
                    r = self.cli("new", "request", "--title", "봉투 대상",
                                 "--summary", "s", "--goal", "g", "--size", "S",
                                 "--project", "alpha", "--user", "alice",
                                 "--body", "b")
                    rid = r.stdout.split()[0]
                    path = mod.locate(rid)
                    meta, _ = mod.read_doc(path)
                    calls = []
                    with mock.patch("subprocess.Popen",
                                    side_effect=lambda argv, **kw:
                                    (calls.append(argv), mock.Mock())[1]):
                        mod._spawn_rework(rid, meta, "반려 노트")
                    self.assertTrue(calls, "spawn 미발생")
                    prompt = calls[0][2]
                    self.assertTrue(prompt.startswith(mod.ENVELOPE_WARNING), prompt[:120])
                    self.assertIn("<<by ", prompt[:200])
                    self.assertIn("알파 전용 워커 규정", prompt)
                finally:
                    for k, v in env_bak.items():
                        if v is None:
                            os.environ.pop(k, None)
                        else:
                            os.environ[k] = v

            # A7. 스캐폴드·안내: scaffold가 agents/ 생성, context_guide에 개수 표시
        with self.subTest("a7_scaffold_and_guide"):
                self.cli("project", "scaffold", "alpha")
                self.assertTrue(os.path.isdir(self.adir("alpha")))
                self.write_agent("alpha", "guide-check.md", "x")
                r = self.cli("new", "request", "--title", "안내 확인", "--summary", "s",
                             "--goal", "g", "--size", "S", "--project", "alpha",
                             "--user", "alice", "--body", "b")
                self.assertIn("프로젝트 에이전트", r.stdout)
                self.assertIn("projects/alpha/agents/", r.stdout)

            # A8-보조. ls 출력
        with self.subTest("a8_ls"):
            self.write_agent("alpha", "lslist.md", "x")
            r = self.cli("project", "agents", "ls")
            self.assertIn("alpha--lslist.md", r.stdout)

if __name__ == "__main__":
    unittest.main(verbosity=2)
