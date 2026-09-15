"""프로젝트를 버릴 때 딸려 가는 것 (REQ-20260915-063-62x6).

slug 는 네 자리에 굳는다: `vault/projects/<slug>.md` · 작업 폴더
`projects/<slug>/` · 모든 문서의 `project:` · 주소. 그런데 버리는 손은 여태
**첫 자리만** 보았다 — 문서 한 장만 휴지통으로 가고, 작업 폴더는 아무도
가리키지 않는 채 제자리에 남았으며, 그 프로젝트를 가리키던 요청들은 없는
이름을 가리킨 채 남았다 (REQ-20260910-006 designer 검토 「어긋난 곳 C」).

여기서 잠그는 계약은 셋이다.
  ① 버리면 작업 폴더도 `projects/.trash/` 로 함께 간다.
  ② 되돌리면 함께 돌아오고, 갈 자리가 막혀 있으면 **아무것도 옮기지 않고** 거부한다
     — 반만 돌아온 프로젝트는 돌아오지 않은 것보다 나쁘다.
  ③ 확인 창이 읽을 수(그 프로젝트를 가리키는 요청·문서 수)를 `/api/projects` 가 싣는다.

실행: python3 tests/ --local --no-reuse project_trash
"""
import glob
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class ProjectTrash(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9prjtrash-")
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.base = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                     "S9_USER": "me", "S9_ORIGIN": "aaaa", "S9_AUDIT": "off"}
        for k in ("S9_SESSION", "S9_PORT", "S9_AUTO_RESUME", "S9_JOB_REQ",
                  "S9_PROJECT"):
            self.base.pop(k, None)
        self.cli("init")
        self.cli("user", "add", "me")
        self.cli("project", "add", "alpha", "--name", "Alpha")

    # ── 자 ──────────────────────────────────────────────────────────────
    def cli(self, *argv, check=True):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.base, stdin=subprocess.DEVNULL, timeout=90)
        if check:
            self.assertEqual(r.returncode, 0,
                             " ".join(argv) + "\n" + r.stdout + r.stderr)
        return r

    def mod(self):
        """s9 를 모듈로 들여온다 — projects_data 같은 내부 계약을 직접 부른다."""
        os.environ["S9_ROOT"] = self.root
        name = "s9prjtrash_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def pdoc(self, slug):
        return os.path.join(self.root, "vault", "projects", slug + ".md")

    def tdoc(self, slug):
        return os.path.join(self.root, "vault", "projects", ".trash", slug + ".md")

    def wdir(self, slug):
        return os.path.join(self.root, "projects", slug)

    def wtrash(self, name):
        return os.path.join(self.root, "projects", ".trash", name)

    def meta_of(self, path):
        text = open(path, encoding="utf-8").read()
        fm = text.split("---", 2)[1] if text.startswith("---") else ""
        out = {}
        for line in fm.splitlines():
            m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("'\"")
        return out

    def prj_id(self, slug="alpha"):
        return self.meta_of(self.pdoc(slug))["id"]

    def new_req(self, project="alpha"):
        r = self.cli("new", "request", "--title", "t", "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b",
                     "--project", project)
        return r.stdout.split()[0]

    # ── S1·S2. 버리면 작업 폴더도 함께 가고, 간 자리가 문서에 적힌다 ─────
    def test_s1_workdir_follows_to_trash(self):
        self.assertTrue(os.path.isdir(self.wdir("alpha")))
        self.cli("rm", self.prj_id(), "--reason", "t")
        self.assertFalse(os.path.exists(self.wdir("alpha")),
                         "작업 폴더가 제자리에 남았다")
        self.assertTrue(os.path.isdir(self.wtrash("alpha")))
        self.assertTrue(os.path.exists(
            os.path.join(self.wtrash("alpha"), "CONTEXT.md")),
            "폴더 안의 것까지 통째로 가야 한다")
        # S2 — 되돌릴 때 읽을 자리가 문서에 적힌다
        self.assertEqual(self.meta_of(self.tdoc("alpha")).get("trashed_workdir"),
                         "projects/.trash/alpha")

    # ── S3·R2. 되돌리면 함께 돌아오고 자취는 남지 않는다 ────────────────
    def test_s3_restore_brings_workdir_back(self):
        pid = self.prj_id()
        self.cli("rm", pid, "--reason", "t")
        self.cli("restore", pid)
        self.assertTrue(os.path.isdir(self.wdir("alpha")))
        self.assertTrue(os.path.exists(
            os.path.join(self.wdir("alpha"), "CONTEXT.md")))
        self.assertFalse(os.path.exists(self.wtrash("alpha")))
        meta = self.meta_of(self.pdoc("alpha"))
        for k in ("trashed", "trashed_by", "trashed_how", "trashed_workdir"):
            self.assertNotIn(k, meta, f"되돌아온 문서에 {k} 가 남았다")

    # ── S4. 확인 창이 읽을 수를 /api/projects 가 싣는다 ─────────────────
    def test_s4_projects_carry_counts(self):
        self.new_req("alpha")
        self.new_req("alpha")
        m = self.mod()
        p = [x for x in m.projects_data()["projects"] if x["slug"] == "alpha"][0]
        self.assertEqual(p["reqs"], 2)
        self.assertEqual(p["docs"], 2)
        self.assertTrue(p["workdir"])
        # 프로젝트 문서 자신은 세지 않는다 — 자기를 가리키는 것이 아니다
        self.assertNotIn("project", [r.get("type") for r in m.load_catalog()
                                     if r.get("project") == "alpha"
                                     and r.get("type") == "project"][:1] or [])

    # ── B1. 작업 폴더가 없는 프로젝트도 조용히 간다 ─────────────────────
    def test_b1_no_workdir_is_fine(self):
        shutil.rmtree(self.wdir("alpha"))
        pid = self.prj_id()
        self.cli("rm", pid, "--reason", "t")
        self.assertTrue(os.path.exists(self.tdoc("alpha")))
        self.assertNotIn("trashed_workdir", self.meta_of(self.tdoc("alpha")))
        self.cli("restore", pid)
        self.assertTrue(os.path.exists(self.pdoc("alpha")))

    # ── B2. 이름이 겹치면 덮지 않고 비켜선다 ────────────────────────────
    def test_b2_name_clash_steps_aside(self):
        os.makedirs(self.wtrash("alpha"), exist_ok=True)
        open(os.path.join(self.wtrash("alpha"), "옛것.txt"), "w",
             encoding="utf-8").write("먼저 버린 것\n")
        self.cli("rm", self.prj_id(), "--reason", "t")
        self.assertTrue(os.path.exists(
            os.path.join(self.wtrash("alpha"), "옛것.txt")),
            "먼저 버린 폴더가 지워졌다")
        self.assertTrue(os.path.isdir(self.wtrash("alpha-2")))
        self.assertEqual(self.meta_of(self.tdoc("alpha")).get("trashed_workdir"),
                         "projects/.trash/alpha-2")

    # ── F1. 갈 자리가 막혀 있으면 아무것도 옮기지 않는다 ────────────────
    def test_f1_blocked_restore_moves_nothing(self):
        pid = self.prj_id()
        self.cli("rm", pid, "--reason", "t")
        os.makedirs(self.wdir("alpha"), exist_ok=True)   # 같은 이름이 다시 생겼다
        r = self.cli("restore", pid, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("작업 폴더", r.stdout + r.stderr)
        # 문서도 폴더도 휴지통에 그대로 — 반만 돌아온 자리가 없다
        self.assertTrue(os.path.exists(self.tdoc("alpha")))
        self.assertFalse(os.path.exists(self.pdoc("alpha")))
        self.assertTrue(os.path.isdir(self.wtrash("alpha")))

    # ── F2. 완전히 지우면 휴지통의 작업 폴더도 함께 사라진다 ────────────
    def test_f2_purge_takes_workdir(self):
        pid = self.prj_id()
        self.cli("rm", pid, "--reason", "t")
        self.assertTrue(os.path.isdir(self.wtrash("alpha")))
        self.cli("purge", pid, "--yes")
        self.assertFalse(os.path.exists(self.wtrash("alpha")))
        self.assertFalse(os.path.exists(self.tdoc("alpha")))

    # ── R1. 프로젝트가 아닌 문서는 종전 그대로다 ────────────────────────
    def test_r1_plain_doc_unchanged(self):
        rid = self.new_req("alpha")
        self.cli("rm", rid, "--reason", "t")
        self.assertFalse(os.path.exists(os.path.join(self.root, "projects",
                                                     ".trash")),
                         "요청 하나 버렸는데 작업 폴더 휴지통이 생겼다")
        self.assertTrue(os.path.isdir(self.wdir("alpha")))
        self.cli("restore", rid)
        hit = [p for p in glob.glob(os.path.join(self.root, "vault", "requests",
                                                 "**", "*.md"), recursive=True)
               if ".trash" not in p and self.meta_of(p).get("id") == rid]
        self.assertEqual(len(hit), 1, "요청이 제자리로 돌아오지 않았다")


if __name__ == "__main__":
    unittest.main()
