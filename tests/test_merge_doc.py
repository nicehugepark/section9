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


PROFILE_META = {"name": "alice", "registered": "2026-09-01T10:00:00+09:00",
                "role": "admin", "os_accounts": ["alice"],
                "machine_accounts": [
                    {"machine": "linux-box", "os": "Linux", "account": "alice",
                     "first": "2026-09-01T10:00:00+09:00",
                     "last": "2026-09-10T10:00:00+09:00", "takes": True},
                    {"machine": "macmini", "os": "macOS", "account": "alice",
                     "first": "2026-09-02T10:00:00+09:00",
                     "last": "2026-09-10T10:00:00+09:00"}],
                "machines": ["linux-box", "macmini"]}
PROFILE_BODY = ("\n## Notes\n"
                "- 2026-09-01T10:00:00+09:00 config auto_resume=on (by alice)\n")


class MergeProfile(unittest.TestCase):
    """프로필 줄을 의미로 합친다 (REQ-20260910-006-t8rc).

    users/*/profile.md 의 machine_accounts 는 프론트매터 한 줄이라, 두 컴퓨터가
    제 줄을 같은 때에 고치면 줄 단위 3-way 가 갈린다. 이 문서에는 id 가 없어
    병합기가 손도 대지 않았고, 목록을 JSON 그대로 합집합하면 같은 컴퓨터의 옛
    줄과 새 줄이 둘 다 남았다.

    실행: python3 tests/ merge_doc
    """

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def prof(self, rows=None, body=None, **over):
        meta = dict(PROFILE_META)
        meta.update(over)
        if rows is not None:
            meta["machine_accounts"] = rows
        return self.m.fm_dump(meta) + "\n" + (PROFILE_BODY if body is None else body)

    def rows(self, merged):
        return {(r.get("machine"), r.get("account")): r
                for r in self.m.fm_parse(merged)[0]["machine_accounts"]}

    def test_profile_merge(self):
        base = self.prof()
        b_rows = PROFILE_META["machine_accounts"]

        # S1. 두 컴퓨터가 각자 제 줄의 last 를 고쳤다 — 받고, 둘 다 제 새것으로
        with self.subTest("s1_each_machine_own_row"):
            ours = self.prof([dict(b_rows[0], last="2026-09-10T16:00:00+09:00"),
                              dict(b_rows[1])])
            theirs = self.prof([dict(b_rows[0]),
                                dict(b_rows[1], last="2026-09-10T16:01:00+09:00")])
            merged = self.m.merge_doc(base, ours, theirs)
            self.assertIsNotNone(merged)
            rows = self.rows(merged)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[("linux-box", "alice")]["last"],
                             "2026-09-10T16:00:00+09:00")
            self.assertEqual(rows[("macmini", "alice")]["last"],
                             "2026-09-10T16:01:00+09:00")

        # S2. 같은 짝을 양쪽이 고쳤다 — 한 줄, last 는 늦은 쪽, first 는 이른 쪽
        with self.subTest("s2_same_pair_one_row"):
            ours = self.prof([dict(b_rows[0], last="2026-09-10T16:00:00+09:00"),
                              dict(b_rows[1])])
            theirs = self.prof([dict(b_rows[0], first="2026-08-30T09:00:00+09:00",
                                     last="2026-09-10T16:02:00+09:00"),
                                dict(b_rows[1])])
            rows = self.rows(self.m.merge_doc(base, ours, theirs))
            self.assertEqual(len(rows), 2)
            row = rows[("linux-box", "alice")]
            self.assertEqual(row["last"], "2026-09-10T16:02:00+09:00")
            self.assertEqual(row["first"], "2026-08-30T09:00:00+09:00")

        # S3. 받기 기록은 last 를 고치지 않는다 — 옛 줄의 last_recv·takes 가 산다
        with self.subTest("s3_recv_beat_survives"):
            ours = self.prof([dict(b_rows[0], last_recv="2026-09-10T15:59:00+09:00"),
                              dict(b_rows[1])])
            theirs = self.prof([{"machine": "linux-box", "os": "Linux",
                                 "account": "alice",
                                 "first": "2026-09-01T10:00:00+09:00",
                                 "last": "2026-09-10T16:05:00+09:00"},
                                dict(b_rows[1])])
            row = self.rows(self.m.merge_doc(base, ours, theirs))[("linux-box", "alice")]
            self.assertEqual(row["last"], "2026-09-10T16:05:00+09:00")
            self.assertEqual(row["last_recv"], "2026-09-10T15:59:00+09:00")
            self.assertIs(row["takes"], True)

        # S4. 한쪽에만 있는 새 컴퓨터 줄은 남는다
        with self.subTest("s4_new_machine_kept"):
            new = {"machine": "wsl-box", "os": "WSL", "account": "alice",
                   "first": "2026-09-10T16:00:00+09:00",
                   "last": "2026-09-10T16:00:00+09:00"}
            ours = self.prof([dict(b_rows[0], last="2026-09-10T16:00:00+09:00"),
                              dict(b_rows[1])])
            theirs = self.prof(list(b_rows) + [new])
            rows = self.rows(self.m.merge_doc(base, ours, theirs))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[("wsl-box", "alice")]["os"], "WSL")

        # S5. 짝지을 것이 없으면 None — git 기본 충돌로 떨어진다
        with self.subTest("s5_no_identity_is_none"):
            self.assertIsNone(self.m.merge_doc(base, self.prof(),
                                               self.prof(name="bob")))
            noname = self.m.fm_dump({"role": "admin"}) + "\n본문\n"
            self.assertIsNone(self.m.merge_doc(noname, noname, noname))

        # S6. 프로필 Notes 는 줄 목록이다 — 양쪽 줄이 모두, 시각순으로
        with self.subTest("s6_profile_notes_are_lines"):
            ours = self.prof(body=PROFILE_BODY
                             + "- 2026-09-10T16:00:00+09:00 config ui_skin=soft (by alice)\n")
            theirs = self.prof(body=PROFILE_BODY
                               + "- 2026-09-10T15:00:00+09:00 config ui_tone=paper (by alice)\n")
            body = self.m.fm_parse(self.m.merge_doc(base, ours, theirs))[1]
            self.assertIn("ui_skin=soft", body)
            self.assertIn("ui_tone=paper", body)
            self.assertLess(body.index("ui_tone=paper"), body.index("ui_skin=soft"))
            self.assertEqual(body.count("auto_resume=on"), 1)

    # S8. 실사 — 두 클론이 같은 프로필을 고치고 pull --rebase
    def test_s8_profile_rehearsal(self):
        m = self.m
        base = tempfile.mkdtemp(prefix="s9mp-")
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
            rel = os.path.join("users", "alice", "profile.md")
            os.makedirs(os.path.join(A, "users", "alice"))
            with open(os.path.join(A, rel), "w", encoding="utf-8") as f:
                f.write(self.prof())
            with open(os.path.join(A, ".gitattributes"), "w") as f:
                f.write("users/*/profile.md merge=s9doc\n")
            subprocess.run(["git", "add", "-A"], cwd=A, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=A, check=True)
            subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=A, check=True, capture_output=True)
            subprocess.run(["git", "pull", "-q", "origin", "main"], cwd=B, check=True, capture_output=True)
            subprocess.run(["git", "branch", "-q", "--set-upstream-to=origin/main"], cwd=B, check=True)
            b_rows = PROFILE_META["machine_accounts"]
            # B: 제 줄(macmini)을 고치고 push
            with open(os.path.join(B, rel), "w", encoding="utf-8") as f:
                f.write(self.prof([dict(b_rows[0]),
                                   dict(b_rows[1], last="2026-09-10T16:01:00+09:00")]))
            subprocess.run(["git", "commit", "-q", "-am", "mac"], cwd=B, check=True)
            subprocess.run(["git", "push", "-q"], cwd=B, check=True, capture_output=True)
            # A: 제 줄(linux-box)을 고치고 pull --rebase
            with open(os.path.join(A, rel), "w", encoding="utf-8") as f:
                f.write(self.prof([dict(b_rows[0], last="2026-09-10T16:00:00+09:00",
                                        last_recv="2026-09-10T15:59:00+09:00"),
                                   dict(b_rows[1])]))
            subprocess.run(["git", "commit", "-q", "-am", "linux"], cwd=A, check=True)
            r = subprocess.run(["git", "pull", "--rebase", "-q"], cwd=A, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(os.path.join(A, rel), encoding="utf-8") as f:
                rows = self.rows(f.read())
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[("linux-box", "alice")]["last_recv"],
                             "2026-09-10T15:59:00+09:00")
            self.assertEqual(rows[("macmini", "alice")]["last"],
                             "2026-09-10T16:01:00+09:00")
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
