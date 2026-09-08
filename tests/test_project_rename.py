"""프로젝트 이름 바꾸기 — s9 project rename (REQ-20260908-023).

slug 는 네 자리에 굳는다: vault/projects/<slug>.md · projects/<slug>/ ·
모든 문서의 `project:` · 에이전트 미러 이름 .claude/agents/<slug>--<이름>.md.
이 시험은 넷이 **한 번에** 옮겨지는지와, 한 건이라도 못 쓰면 **아무 것도 안
바뀌는지**(부분 적용 금지)를 잰다. 실 저장소가 아니라 임시 vault 에서 돈다.

실행: python3 tests/ --local --no-reuse project_rename
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class ProjectRename(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9rename-")
        self.addCleanup(self._cleanup)
        self.base = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                     "S9_USER": "me", "S9_ORIGIN": "aaaa"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_PROJECT"):
            self.base.pop(k, None)
        self.cli("init")
        self.cli("user", "add", "me")
        self.cli("init")
        self.cli("project", "add", "alpha", "--name", "Alpha")

    def _cleanup(self):
        for dp, dirs, files in os.walk(self.root):      # 0444 로 막아 둔 것 해제
            for fn in files:
                try:
                    os.chmod(os.path.join(dp, fn), 0o644)
                except OSError:
                    pass
        shutil.rmtree(self.root, ignore_errors=True)

    def cli(self, *argv, env=None, check=True):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env={**self.base, **(env or {})},
                           stdin=subprocess.DEVNULL, timeout=60)
        if check:
            self.assertEqual(r.returncode, 0,
                             " ".join(argv) + "\n" + r.stdout + r.stderr)
        return r

    # ── 자 ──────────────────────────────────────────────────────────────
    def pdoc(self, slug):
        return os.path.join(self.root, "vault", "projects", slug + ".md")

    def meta_of(self, path):
        text = open(path, encoding="utf-8").read()
        fm = text.split("---", 2)[1] if text.startswith("---") else ""
        out = {}
        for line in fm.splitlines():
            m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("'\"")
        return out

    def new_req(self, project):
        r = self.cli("new", "request", "--title", "t", "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b",
                     "--project", project)
        rid = r.stdout.split()[0]
        hit = glob.glob(os.path.join(self.root, "vault", "requests", "**", "*.md"),
                        recursive=True)
        for p in hit:
            if self.meta_of(p).get("id") == rid:
                return p
        self.fail("만든 요청 문서를 못 찾았다: " + r.stdout + r.stderr)

    def index_text(self):
        out = []
        for p in glob.glob(os.path.join(self.root, "index", "*")):
            try:
                out.append(open(p, encoding="utf-8").read())
            except (OSError, UnicodeDecodeError):
                pass
        return "\n".join(out)

    # ── S1. 문서 파일·slug 칸·에셋 공간·문서의 project 가 한 번에 옮겨진다 ──
    def test_s1_moves_four_places(self):
        req = self.new_req("alpha")
        self.assertEqual(self.meta_of(req)["project"], "alpha")
        r = self.cli("project", "rename", "alpha", "beta")
        self.assertIn("alpha -> beta", r.stdout)
        self.assertTrue(os.path.exists(self.pdoc("beta")))
        self.assertFalse(os.path.exists(self.pdoc("alpha")))
        self.assertEqual(self.meta_of(self.pdoc("beta"))["slug"], "beta")
        self.assertTrue(os.path.isdir(os.path.join(self.root, "projects", "beta")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "projects", "alpha")))
        self.assertEqual(self.meta_of(req)["project"], "beta")
        # 본문 글자는 건드리지 않는다 — frontmatter 의 project 칸만
        self.assertTrue(os.path.exists(
            os.path.join(self.root, "projects", "beta", "CONTEXT.md")))

    # ── S2. 에이전트 미러 이름도 따라 옮겨진다 ────────────────────────────
    def test_s2_agent_mirror_follows(self):
        adir = os.path.join(self.root, "projects", "alpha", "agents")
        os.makedirs(adir, exist_ok=True)
        open(os.path.join(adir, "worker.md"), "w", encoding="utf-8").write("# w\n")
        self.cli("project", "agents", "sync")
        mirror = os.path.join(self.root, ".claude", "agents")
        self.assertTrue(os.path.exists(os.path.join(mirror, "alpha--worker.md")))
        self.cli("project", "rename", "alpha", "beta")
        self.assertTrue(os.path.exists(os.path.join(mirror, "beta--worker.md")))
        self.assertFalse(os.path.exists(os.path.join(mirror, "alpha--worker.md")))

    # ── S3. History 에 이름 변경 한 줄 ───────────────────────────────────
    def test_s3_history_line(self):
        self.cli("project", "rename", "alpha", "beta")
        body = open(self.pdoc("beta"), encoding="utf-8").read()
        self.assertIn("이름 변경 alpha -> beta", body)
        self.assertIn("by me", body.split("## History")[-1])

    # ── S4. 거부: 없는 slug · 이미 있는 slug · 허용 문자 밖 · 같은 이름 ────
    def test_s4_rejections(self):
        self.cli("project", "add", "gamma")
        for old, new, why in (("nosuch", "beta", "없는 slug"),
                              ("alpha", "gamma", "이미 있는 slug"),
                              ("alpha", "a b", "허용 문자 밖"),
                              ("alpha", "a/b", "경로 구분자"),
                              ("alpha", "alpha", "같은 이름")):
            r = self.cli("project", "rename", old, new, check=False)
            self.assertEqual(r.returncode, 1, why + "\n" + r.stdout + r.stderr)
            self.assertTrue(os.path.exists(self.pdoc("alpha")), why)
            self.assertTrue(os.path.exists(self.pdoc("gamma")), why)

    # ── S5. 부분 적용 금지: 한 건이라도 못 쓰면 전부 원래대로 ─────────────
    def test_s5_no_partial_apply(self):
        keep, blocked = self.new_req("alpha"), self.new_req("alpha")
        before = open(keep, encoding="utf-8").read()
        pbefore = open(self.pdoc("alpha"), encoding="utf-8").read()
        os.chmod(blocked, 0o444)
        r = self.cli("project", "rename", "alpha", "beta", check=False)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(self.pdoc("alpha")))
        self.assertFalse(os.path.exists(self.pdoc("beta")))
        self.assertTrue(os.path.isdir(os.path.join(self.root, "projects", "alpha")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "projects", "beta")))
        self.assertEqual(open(keep, encoding="utf-8").read(), before)
        self.assertEqual(open(self.pdoc("alpha"), encoding="utf-8").read(), pbefore)
        self.assertEqual(self.meta_of(blocked)["project"], "alpha")

    # ── S6. 색인이 새 이름을 가리킨다 ────────────────────────────────────
    def test_s6_index_updated(self):
        self.new_req("alpha")
        self.cli("project", "rename", "alpha", "beta")
        text = self.index_text()
        self.assertIn("beta", text)
        self.assertNotIn('"project": "alpha"', text)
        self.assertNotIn('"project":"alpha"', text)

    # ── S7. 다른 프로젝트에는 아무 일도 일어나지 않는다 ───────────────────
    def test_s7_other_projects_untouched(self):
        self.cli("project", "add", "gamma")
        other = self.new_req("gamma")
        gbefore = open(self.pdoc("gamma"), encoding="utf-8").read()
        self.new_req("alpha")
        self.cli("project", "rename", "alpha", "beta")
        self.assertEqual(self.meta_of(other)["project"], "gamma")
        self.assertEqual(open(self.pdoc("gamma"), encoding="utf-8").read(), gbefore)
        self.assertTrue(os.path.isdir(os.path.join(self.root, "projects", "gamma")))


if __name__ == "__main__":
    unittest.main()
