"""문서는 의미로 합친다 (REQ-20260902-024, DOC-20260902-001 D8).

같은 문서를 두 머신이 고치면 줄 단위 3-way 는 3/3 충돌한다(`updated:` 한 줄·같은
삽입 지점). 형식을 아는 병합기: 스칼라는 늦은 쪽, 목록은 합집합, Notes·History 는
타임스탬프 단위 합집합·시각순, status 는 늦은 전이 + 두 줄 보존 + doubled 표식.

실행: python3 tests/ merge_doc
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.abspath(os.path.join(HERE, "..", "bin", "s9"))


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_merge", importlib.machinery.SourceFileLoader("s9_merge", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BASE_META = {"id": "REQ-20260902-001-aaaa", "type": "request", "title": "t",
             "status": "review", "user": "alice", "agents": ["lead:x"],
             "priority": 50, "created": "2026-09-02T10:00:00+09:00",
             "updated": "2026-09-02T10:00:00+09:00"}
BASE_BODY = ("\n## Original\n\n원문\n\n## Notes\n\n"
             "### 2026-09-02T10:00:00+09:00 tdd (by alice)\n\n- [x] S1\n\n"
             "## History\n- 2026-09-02T09:00:00+09:00 created by alice (status: open)\n"
             "- 2026-09-02T10:00:00+09:00 status: in-progress -> review (by alice) — 확인\n")


class MergeDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def doc(self, meta_over=None, body=None):
        meta = dict(BASE_META)
        meta.update(meta_over or {})
        return self.m.fm_dump(meta) + "\n" + (body if body is not None else BASE_BODY)

    def parse(self, text):
        return self.m.fm_parse(text)

    # M1. note(A) + 전이(B)
    def test_merge_doc(self):
        """MergeDoc 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("m1_note_plus_transition"):
                base = self.doc()
                ours = self.doc({"updated": "2026-09-02T11:00:00+09:00"},
                                BASE_BODY.replace("- [x] S1\n\n", "- [x] S1\n\n"
                                                  "### 2026-09-02T11:00:00+09:00 response (by alice)\n\n고쳤다\n\n"))
                theirs = self.doc({"status": "in-progress", "status_since": "2026-09-02T11:05:00+09:00",
                                   "updated": "2026-09-02T11:05:00+09:00"},
                                  BASE_BODY + "- 2026-09-02T11:05:00+09:00 status: review -> in-progress (by bob) — 반려\n")
                merged = self.m.merge_doc(base, ours, theirs)
                self.assertIsNotNone(merged)
                meta, body = self.parse(merged)
                self.assertEqual(meta["status"], "in-progress")
                self.assertEqual(meta["updated"], "2026-09-02T11:05:00+09:00")
                self.assertIn("고쳤다", body)
                self.assertIn("review -> in-progress (by bob)", body)
                self.assertNotIn("doubled", meta)

            # M2. note + note — 둘 다, 시각순, 중복 하나
        with self.subTest("m2_note_plus_note"):
                base = self.doc()
                a = BASE_BODY.replace("## History", "### 2026-09-02T11:10:00+09:00 response (by alice)\n\nA 노트\n\n## History")
                b = BASE_BODY.replace("## History", "### 2026-09-02T11:02:00+09:00 response (by bob)\n\nB 노트\n\n## History")
                merged = self.m.merge_doc(base, self.doc({"updated": "2026-09-02T11:10:00+09:00"}, a),
                                          self.doc({"updated": "2026-09-02T11:02:00+09:00"}, b))
                meta, body = self.parse(merged)
                self.assertLess(body.index("B 노트"), body.index("A 노트"))
                self.assertEqual(body.count("B 노트"), 1)
                # 같은 노트가 양쪽에 있으면 하나
                merged2 = self.m.merge_doc(base, self.doc({"updated": "2026-09-02T11:10:00+09:00"}, a),
                                           self.doc({"updated": "2026-09-02T11:10:00+09:00"}, a))
                self.assertEqual(self.parse(merged2)[1].count("A 노트"), 1)

            # M3. note + set(priority)
        with self.subTest("m3_note_plus_priority"):
                base = self.doc()
                a = BASE_BODY.replace("## History", "### 2026-09-02T11:10:00+09:00 response (by alice)\n\n노트\n\n## History")
                merged = self.m.merge_doc(base, self.doc({"updated": "2026-09-02T11:10:00+09:00"}, a),
                                          self.doc({"priority": 80, "updated": "2026-09-02T11:11:00+09:00"}))
                meta, body = self.parse(merged)
                self.assertEqual(str(meta["priority"]), "80")
                self.assertIn("노트", body)

            # M4. status 양쪽 다르게 — 늦은 쪽 + 둘 다 남김 + doubled
        with self.subTest("m4_double_transition"):
                base = self.doc()
                ours = self.doc({"status": "done", "updated": "2026-09-02T11:20:00+09:00"},
                                BASE_BODY + "- 2026-09-02T11:20:00+09:00 status: review -> done (by carol) — 승인\n")
                theirs = self.doc({"status": "in-progress", "updated": "2026-09-02T11:21:00+09:00"},
                                  BASE_BODY + "- 2026-09-02T11:21:00+09:00 status: review -> in-progress (by bob) — 반려\n")
                meta, body = self.parse(self.m.merge_doc(base, ours, theirs))
                self.assertEqual(meta["status"], "in-progress")       # 늦은 전이
                self.assertEqual(len(meta["doubled"]), 2)
                self.assertIn("review -> done (by carol)", body)
                self.assertIn("review -> in-progress (by bob)", body)

            # M5. 목록·dict 합집합, lease 는 renewed 가 늦은 쪽
        with self.subTest("m5_lists_and_dicts"):
                base = self.doc()
                ours = self.doc({"agents": ["lead:x", "sub:designer"], "tags": ["a"],
                                 "lease": {"user": "alice", "machine": "m1", "renewed": "2026-09-02T11:00:00+09:00"},
                                 "contributions": [{"actor": "lead:x", "started": "1", "item": "a"}],
                                 "updated": "2026-09-02T11:00:00+09:00"})
                theirs = self.doc({"agents": ["lead:x", "worker:rework"], "tags": ["b"],
                                   "lease": {"user": "alice", "machine": "m2", "renewed": "2026-09-02T11:30:00+09:00"},
                                   "contributions": [{"actor": "lead:x", "started": "1", "item": "a"},
                                                     {"actor": "worker:rework", "started": "2", "item": "b"}],
                                   "updated": "2026-09-02T11:30:00+09:00"})
                meta, _ = self.parse(self.m.merge_doc(base, ours, theirs))
                self.assertEqual(meta["agents"], ["lead:x", "sub:designer", "worker:rework"])
                self.assertEqual(sorted(meta["tags"]), ["a", "b"])
                self.assertEqual(meta["lease"]["machine"], "m2")
                self.assertEqual(len(meta["contributions"]), 2)

            # M6. 못 합치는 것은 None
        with self.subTest("m6_unmergeable_is_none"):
                self.assertIsNone(self.m.merge_doc("", self.doc(), self.doc()))
                self.assertIsNone(self.m.merge_doc("plain", "plain a", "plain b"))
                other = self.doc({"id": "REQ-20260902-002-aaaa"})
                self.assertIsNone(self.m.merge_doc(self.doc(), self.doc(), other))

            # M7. 설치 — attributes·드라이버·명령
        with self.subTest("m7_install_wiring"):
            root = os.path.dirname(HERE)
            with open(os.path.join(root, ".gitattributes"), encoding="utf-8") as f:
                attrs = f.read()
            self.assertIn("vault/**/*.md merge=s9doc", attrs)
            with open(os.path.join(root, "bin", "s9-install"), encoding="utf-8") as f:
                self.assertIn("merge.s9doc.driver", f.read())
            tmp = tempfile.mkdtemp(prefix="s9md-")
            try:
                paths = []
                for name, text in (("base", self.doc()),
                                   ("ours", self.doc({"updated": "2026-09-02T11:00:00+09:00"},
                                                     BASE_BODY.replace("## History", "### 2026-09-02T11:00:00+09:00 response (by alice)\n\nx\n\n## History"))),
                                   ("theirs", self.doc({"priority": 70, "updated": "2026-09-02T11:01:00+09:00"}))):
                    p = os.path.join(tmp, name)
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(text)
                    paths.append(p)
                r = subprocess.run([S9, "merge-doc", *paths], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                with open(paths[1], encoding="utf-8") as f:
                    meta, body = self.m.fm_parse(f.read())
                self.assertEqual(str(meta["priority"]), "70")
                self.assertIn("### 2026-09-02T11:00:00+09:00 response", body)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

class MergeRehearsal(unittest.TestCase):
    """M8 — bare origin + 클론 둘에서 실제 pull --rebase 가 사람 손 없이 합쳐진다."""

    def test_m8_pull_rebase_merges_note_and_transition(self):
        m = _load()
        base = tempfile.mkdtemp(prefix="s9mr-")
        try:
            bare = os.path.join(base, "o.git")
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
            clones = []
            for n in ("A", "B"):
                d = os.path.join(base, n)
                subprocess.run(["git", "clone", "-q", bare, d], check=True, capture_output=True)
                for c in (["git", "config", "user.name", n], ["git", "config", "user.email", f"{n}@t"],
                          ["git", "config", "merge.s9doc.driver", f"{S9} merge-doc %O %A %B"]):
                    subprocess.run(c, cwd=d, check=True)
                clones.append(d)
            A, B = clones
            docdir = os.path.join(A, "vault", "requests", "2026", "09")
            os.makedirs(docdir)
            doc = os.path.join(docdir, "REQ-20260902-001-aaaa.md")
            with open(doc, "w", encoding="utf-8") as f:
                f.write(m.fm_dump(BASE_META) + "\n" + BASE_BODY)
            with open(os.path.join(A, ".gitattributes"), "w") as f:
                f.write("vault/**/*.md merge=s9doc\n")
            subprocess.run(["git", "add", "-A"], cwd=A, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=A, check=True)
            subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=A, check=True, capture_output=True)
            subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=B, check=True, capture_output=True)
            subprocess.run(["git", "branch", "-q", "--set-upstream-to=origin/main"], cwd=B, check=True)
            # B: 전이 + History, push
            rel = os.path.relpath(doc, A)
            meta = dict(BASE_META, status="in-progress", updated="2026-09-02T11:05:00+09:00")
            with open(os.path.join(B, rel), "w", encoding="utf-8") as f:
                f.write(m.fm_dump(meta) + "\n" + BASE_BODY
                        + "- 2026-09-02T11:05:00+09:00 status: review -> in-progress (by bob) — 반려\n")
            subprocess.run(["git", "commit", "-q", "-am", "reject"], cwd=B, check=True)
            subprocess.run(["git", "push", "-q"], cwd=B, check=True, capture_output=True)
            # A: 노트 + updated, 그리고 pull --rebase
            meta = dict(BASE_META, updated="2026-09-02T11:00:00+09:00")
            with open(doc, "w", encoding="utf-8") as f:
                f.write(m.fm_dump(meta) + "\n" + BASE_BODY.replace(
                    "## History", "### 2026-09-02T11:00:00+09:00 response (by alice)\n\n고쳤다\n\n## History"))
            subprocess.run(["git", "commit", "-q", "-am", "note"], cwd=A, check=True)
            r = subprocess.run(["git", "pull", "--rebase", "-q"], cwd=A, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(doc, encoding="utf-8") as f:
                meta2, body2 = m.fm_parse(f.read())
            self.assertEqual(meta2["status"], "in-progress")
            self.assertIn("고쳤다", body2)
            self.assertIn("review -> in-progress (by bob)", body2)
            self.assertEqual(meta2["updated"], "2026-09-02T11:05:00+09:00")
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
