"""프로젝트 에셋 공간 1단계 테스트 (REQ-20260824-033, 설계 DOC-20260824-001).

스캐폴드(projects/<slug>/CONTEXT.md + assets/) 자동 생성, CONTEXT.md 검색 인덱싱,
프로젝트 확정 시 CONTEXT 경로 안내를 검증한다.

격리: S9_ROOT=mktemp — 라이브 vault를 건드리지 않는다.
실행: python3 tests/test_project_assets.py
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class TestProjectAssets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9test-")
        self.env = {**os.environ, "S9_ROOT": self.tmp}
        self.env.pop("S9_SESSION", None)
        self.env.pop("S9_USER", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *argv, expect=0, inp=None):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           input=inp, env=self.env, timeout=15)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                 f"{r.stdout}{r.stderr}")
        return r

    def ctx_path(self, slug):
        return os.path.join(self.tmp, "projects", slug, "CONTEXT.md")

    # S1. project add 시 스캐폴드 자동 생성 + 경로 안내
    def test_add_scaffolds_asset_space(self):
        r = self.cli("project", "add", "demo", "--name", "Demo",
                     "--user", "alice")
        self.assertTrue(os.path.isfile(self.ctx_path("demo")))
        self.assertTrue(os.path.isdir(
            os.path.join(self.tmp, "projects", "demo", "assets")))
        self.assertIn("projects/demo/", r.stdout)
        # 템플릿에 slug/제목과 진입점 안내가 있다
        with open(self.ctx_path("demo"), encoding="utf-8") as f:
            tpl = f.read()
        self.assertIn("Demo", tpl)

    # S2. 기존 프로젝트에 scaffold 명령 — slug/PRJ id 양쪽으로 도달
    def test_scaffold_existing_project_by_slug_and_id(self):
        self.cli("project", "add", "web", "--user", "alice")
        # 에셋 공간을 지워 '기존 프로젝트(스캐폴드 없음)' 상태를 만든다
        shutil.rmtree(os.path.join(self.tmp, "projects", "web"))
        self.cli("project", "scaffold", "web")
        self.assertTrue(os.path.isfile(self.ctx_path("web")))

        shutil.rmtree(os.path.join(self.tmp, "projects", "web"))
        prj_id = self.cli("project", "show", "web", "--meta").stdout
        prj_id = [l.split(":", 1)[1].strip() for l in prj_id.splitlines()
                  if l.startswith("id:")][0]
        self.cli("project", "scaffold", prj_id)  # id로도 같은 디렉토리
        self.assertTrue(os.path.isfile(self.ctx_path("web")))

    # S3. 멱등 — 사용자가 수정한 CONTEXT.md를 덮어쓰지 않는다
    def test_scaffold_preserves_existing_context(self):
        self.cli("project", "add", "demo", "--user", "alice")
        with open(self.ctx_path("demo"), "w", encoding="utf-8") as f:
            f.write("# 커스텀 내용 zebra9\n")
        self.cli("project", "scaffold", "demo")
        with open(self.ctx_path("demo"), encoding="utf-8") as f:
            self.assertIn("zebra9", f.read())

    # S4. CONTEXT.md 검색 인덱싱 — 본문 키워드·slug 질의 모두 도달
    def test_search_body_hits_context_md(self):
        self.cli("project", "add", "demo", "--name", "Demo", "--user", "alice")
        with open(self.ctx_path("demo"), "a", encoding="utf-8") as f:
            f.write("\n결제 검사웨이는 xyzzykey 를 쓴다\n")
        r = self.cli("search", "xyzzykey", "--body")
        self.assertIn("projects/demo/CONTEXT.md", r.stdout)
        self.assertIn("xyzzykey", r.stdout)
        # slug를 함께 질의해도 같은 곳에 도달
        r2 = self.cli("search", "demo", "xyzzykey", "--body")
        self.assertIn("projects/demo/CONTEXT.md", r2.stdout)

    # S5. 프로젝트 확정 시 경로 안내 (상한 있는 요약 포함, 없으면 침묵)
    def test_set_project_prints_context_guide(self):
        self.cli("project", "add", "demo", "--user", "alice")
        rid = self.cli("new", "request", "--title", "t", "--user", "alice",
                       inp="본문").stdout.split()[0]
        r = self.cli("set", rid, "--project", "demo")
        self.assertIn("projects/demo/CONTEXT.md", r.stdout)

        # CONTEXT.md가 없으면 안내하지 않는다 (잡음 금지)
        shutil.rmtree(os.path.join(self.tmp, "projects", "demo"))
        rid2 = self.cli("new", "request", "--title", "t2", "--user", "alice",
                        inp="본문").stdout.split()[0]
        r2 = self.cli("set", rid2, "--project", "demo")
        self.assertNotIn("CONTEXT.md", r2.stdout)

    # S6. digest에 내 프로젝트 CONTEXT 경로 섹션
    def test_digest_lists_my_project_contexts(self):
        self.cli("project", "add", "demo", "--name", "Demo", "--user", "alice")
        r = self.cli("digest", "--user", "alice")
        self.assertIn("projects/demo/CONTEXT.md", r.stdout)
        # 멤버가 아닌 사용자에게는 안 보인다
        self.cli("user", "add", "bob")
        r2 = self.cli("digest", "--user", "bob")
        self.assertNotIn("projects/demo/CONTEXT.md", r2.stdout)

    # S7. 미존재 프로젝트 scaffold 거부
    def test_scaffold_unknown_project_fails(self):
        r = self.cli("project", "scaffold", "nope", expect=1)
        self.assertIn("not found", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
