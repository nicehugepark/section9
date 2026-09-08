"""프로젝트에 출처를 남긴다 — 만든 사람·만든 머신 (REQ-20260908-024).

문서 id 는 머신 지문을 달아 두 머신이 안 부딪히는데, 프로젝트 문서의 파일
이름은 slug 라 그 장치가 없었다. 같은 slug 가 두 설치에서 만나면 「다른 설치가
만든 다른 것」임을 보여 줄 근거가 필요하다. 이미 있는 문서에는 소급하지 않는다.

실행: python3 tests/ --local --no-reuse project_origin
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class ProjectOrigin(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9porigin-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.base = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                     "S9_USER": "me", "S9_ORIGIN": "aaaa"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_PROJECT"):
            self.base.pop(k, None)
        self.cli("init")
        self.cli("user", "add", "me")
        self.cli("init")

    def cli(self, *argv, env=None, check=True):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env={**self.base, **(env or {})},
                           stdin=subprocess.DEVNULL, timeout=60)
        if check:
            self.assertEqual(r.returncode, 0,
                             " ".join(argv) + "\n" + r.stdout + r.stderr)
        return r

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

    # ── S1. 새 프로젝트 문서에 만든 사람·머신 ────────────────────────────
    def test_s1_new_project_records_origin(self):
        self.cli("project", "add", "alpha", "--name", "Alpha")
        meta = self.meta_of(self.pdoc("alpha"))
        self.assertEqual(meta["creator"], "me")
        self.assertEqual(meta["machine"], "testbox")
        self.assertTrue(re.fullmatch(r"[0-9a-z]{4}", meta["machine_fp"]),
                        meta.get("machine_fp"))

    # ── S2. 소급 없음: 그 칸이 없는 옛 문서도 그대로 읽힌다 ───────────────
    def test_s2_no_backfill_on_old_docs(self):
        self.cli("project", "add", "alpha")
        path = self.pdoc("alpha")
        text = open(path, encoding="utf-8").read()
        text = "\n".join(l for l in text.splitlines()
                         if not l.startswith(("creator:", "machine:", "machine_fp:")))
        open(path, "w", encoding="utf-8").write(text + "\n")
        r = self.cli("project", "ls")
        row = [l for l in r.stdout.splitlines() if "(alpha)" in l]
        self.assertEqual(len(row), 1, r.stdout)
        self.assertNotIn("만든 곳", row[0])       # 없는 칸은 그냥 안 붙는다
        self.cli("project", "show", "alpha")
        # 읽었다고 칸이 새로 써지지는 않는다
        self.assertNotIn("machine_fp:", open(path, encoding="utf-8").read())

    # ── S3. 같은 slug 의 둘을 ls 에서 사람이 가른다 ───────────────────────
    def test_s3_ls_distinguishes_same_slug(self):
        self.cli("project", "add", "alpha", "--name", "Alpha")
        mine = open(self.pdoc("alpha"), encoding="utf-8").read()
        # 다른 설치가 만든 같은 slug 의 문서가 pull 로 들어온 판
        theirs = (mine.replace("machine: testbox", "machine: otherbox")
                      .replace("machine_fp: aaaa", "machine_fp: bbbb")
                      .replace("creator: me", "creator: you")
                      .replace("PRJ-", "PRJ2-"))
        open(os.path.join(self.root, "vault", "projects", "alpha-other.md"),
             "w", encoding="utf-8").write(theirs)
        out = self.cli("project", "ls").stdout
        self.assertIn("만든 곳:testbox(aaaa)", out)
        self.assertIn("만든 곳:otherbox(bbbb)", out)
        self.assertIn("만든이:you", out)

    # ── S4. rename 은 출처를 바꾸지 않는다 ───────────────────────────────
    def test_s4_rename_keeps_origin(self):
        self.cli("project", "add", "alpha")
        before = self.meta_of(self.pdoc("alpha"))
        self.cli("project", "rename", "alpha", "beta")
        after = self.meta_of(self.pdoc("beta"))
        for k in ("creator", "machine", "machine_fp", "id"):
            self.assertEqual(after[k], before[k], k)
        self.assertEqual(after["slug"], "beta")


if __name__ == "__main__":
    unittest.main()
