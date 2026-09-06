"""프롬프트가 요청 문서가 될 때 어느 프로젝트에 붙는가 (REQ-20260906-052).

판정은 cmd_new 의 resolve_project 한 곳에서만 한다. 우선순위 = ① 명시 --project
② 프롬프트 첫 줄 표기 `[프로젝트: slug]`(훅이 --project-tag 로 넘긴다) ③ 세션
바인딩 project(`s9 code --project` · `s9 bind project`) ④ 사용자가 contribute 할 수
있는 프로젝트가 하나뿐이면 그것 ⑤ 빈 값 + 후보 한 줄. 자동 신호(②③④)는 권한이
없으면 die 하지 않고 다음 단계로 내려간다. 어느 경로였는지 project_source 에 남는다.

실행: python3 tests/ --local --no-reuse project_resolve
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"
HOOK_PROMPT = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
HOOK_SESSION = os.path.join(HERE, "..", "bin", "s9-audit-session")

HINT = "프로젝트 미정 — 후보:"


class ProjectResolve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9projres-")
        cls.base = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_USER",
                  "S9_PROJECT"):
            cls.base.pop(k, None)
        cls.cli("init")
        for u in ("alice", "bob"):
            cls.cli("user", "add", u)
        # alice: pa·pb 둘의 owner / bob: pc 하나의 owner
        cls.cli("project", "add", "pa", "--name", "PA", "--user", "alice")
        cls.cli("project", "add", "pb", "--name", "PB", "--user", "alice")
        cls.cli("project", "add", "pc", "--name", "PC", "--user", "bob")
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader(
            "s9_projres", importlib.machinery.SourceFileLoader("s9_projres", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, *argv, env=None):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env={**cls.base, **(env or {})},
                              stdin=subprocess.DEVNULL, timeout=30)

    def new(self, *extra, user, session="", expect_ok=True):
        env = {"S9_SESSION": session} if session else {}
        r = self.cli("new", "request", "--title", "t", "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b",
                     "--user", user, *extra, env=env)
        if not expect_ok:
            return r, None
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rid = r.stdout.split()[0]
        return r, self.m.read_doc(self.m.locate(rid))[0]

    def bind(self, session, key, value):
        r = self.cli("bind", key, value, env={"S9_SESSION": session})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # S1. 표기가 세션을 이긴다 (② > ③)
    def test_s1_tag_beats_session_binding(self):
        self.bind("sess1", "project", "pb")
        _, meta = self.new("--project-tag", "pa", user="alice", session="sess1")
        self.assertEqual(meta["project"], "pa")
        self.assertEqual(meta.get("project_source"), "tag")

    # S2. 세션 바인딩 → session
    def test_s2_session_binding(self):
        self.bind("sess2", "project", "pb")
        _, meta = self.new(user="alice", session="sess2")
        self.assertEqual(meta["project"], "pb")
        self.assertEqual(meta.get("project_source"), "session")

    # S3. 둘 다 없음 → 빈 값 + 후보 한 줄
    def test_s3_blank_lists_candidates(self):
        r, meta = self.new(user="alice", session="sess3")
        self.assertEqual(meta.get("project", ""), "")
        self.assertNotIn("project_source", meta)
        hint = [l for l in r.stdout.splitlines() if HINT in l]
        self.assertEqual(len(hint), 1, r.stdout)
        self.assertIn("후보: pa, pb", hint[0])
        self.assertIn(f"s9 set {meta['id']} project=<slug>", hint[0])

    # S4. 권한 없는 표기(비멤버·미등록) → 빈 값, die 하지 않는다
    def test_s4_unauthorized_tag_falls_to_blank(self):
        for tag in ("pc", "zzz"):
            with self.subTest(tag=tag):
                r, meta = self.new("--project-tag", tag, user="alice")
                self.assertEqual(meta.get("project", ""), "")
                self.assertNotIn("project_source", meta)

    # S5. 1프로젝트 사용자 → only (현행 유지)
    def test_s5_only_project_user(self):
        r, meta = self.new(user="bob")
        self.assertEqual(meta["project"], "pc")
        self.assertEqual(meta.get("project_source"), "only")
        self.assertFalse([l for l in r.stdout.splitlines() if HINT in l])

    # S6. 명시 --project 가 표기를 이긴다 → explicit
    def test_s6_explicit_beats_tag(self):
        _, meta = self.new("--project", "pb", "--project-tag", "pa", user="alice")
        self.assertEqual(meta["project"], "pb")
        self.assertEqual(meta.get("project_source"), "explicit")

    # S7. 회귀: 명시 --project 에 권한 없으면 여전히 die
    def test_s7_explicit_unauthorized_dies(self):
        r, _ = self.new("--project", "pc", user="alice", expect_ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("권한 없음", r.stderr + r.stdout)

    # S8. 훅: 첫 줄 표기 → --project-tag, 제목에서 표기를 뗀다, 후보 줄을 싣는다
    def test_s8_hook_passes_tag_and_candidate_line(self):
        spec = importlib.util.spec_from_loader(
            "s9_projres_hook",
            importlib.machinery.SourceFileLoader("s9_projres_hook", HOOK_PROMPT))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            if argv[:2] == ("new", "request"):
                return mock.Mock(returncode=0, stdout=(
                    "REQ-20260906-999-test  vault/requests/x.md\n"
                    f"◌ {HINT} pa, pb → s9 set REQ-20260906-999-test project=<slug>\n"))
            return mock.Mock(returncode=0, stdout="")

        prompt = ("[프로젝트: pa] 결제 API 의 재시도 정책을 멱등 키 기준으로 다시 "
                  "설계하고 구현해 줘 — 실패 모드와 회귀 테스트까지 포함해서.")
        payload = json.dumps({"prompt": prompt, "session_id": "c0ffee1234"})
        with mock.patch.object(hook, "run", fake_run), \
                mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            hook.main()
        new = [a for a in calls if a[:2] == ("new", "request")]
        self.assertEqual(len(new), 1, calls)
        argv = list(new[0])
        self.assertIn("--project-tag", argv)
        self.assertEqual(argv[argv.index("--project-tag") + 1], "pa")
        title = argv[argv.index("--title") + 1]
        self.assertFalse(title.startswith("["), title)
        self.assertTrue(title.startswith("결제 API"), title)
        printed = out.getvalue()
        self.assertIn(HINT, printed)
        self.assertIn("s9 set REQ-20260906-999-test project=<slug>", printed)
        # 표기가 없으면 --project-tag 도 없다
        calls.clear()
        payload = json.dumps({"prompt": prompt.split("] ", 1)[1],
                              "session_id": "c0ffee1234"})
        with mock.patch.object(hook, "run", fake_run), \
                mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            hook.main()
        new = [a for a in calls if a[:2] == ("new", "request")]
        self.assertNotIn("--project-tag", new[0])

    # S9. s9 code --project / ROOT 추론 → S9_PROJECT → 세션 훅이 bind project
    def test_s9_code_project_and_root_inference(self):
        m = self.m
        # 명시가 이긴다
        self.assertEqual(m.code_project("pa"), "pa")
        # projects/ 밑 등록 slug 가 셋(pa·pb·pc) → 추론 불가
        self.assertEqual(m.code_project(None), "")
        one = tempfile.mkdtemp(prefix="s9projres-one-")
        try:
            os.makedirs(os.path.join(one, "pb"))
            os.makedirs(os.path.join(one, "not-a-project"))
            with mock.patch.object(m, "PROJECT_SPACE", one):
                self.assertEqual(m.code_project(None), "pb")
        finally:
            shutil.rmtree(one, ignore_errors=True)
        # 미등록 slug 를 명시하면 거부
        with self.assertRaises(SystemExit):
            m.code_project("zzz")
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('os.environ["S9_PROJECT"]', src)
        with open(HOOK_SESSION, encoding="utf-8") as f:
            self.assertIn('"bind", "project"', f.read())

    # S10. 세션 바인딩의 slug 에 권한이 없으면 ④ 로 내려간다
    def test_s10_unauthorized_binding_falls_through(self):
        self.bind("sess10", "project", "pa")
        _, meta = self.new(user="bob", session="sess10")
        self.assertEqual(meta["project"], "pc")
        self.assertEqual(meta.get("project_source"), "only")


if __name__ == "__main__":
    unittest.main()
