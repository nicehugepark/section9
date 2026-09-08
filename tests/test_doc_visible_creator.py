"""문서를 만든 사람이 자기 문서를 본다 (REQ-20260906-009-62x6).

`doc_visible` 의 마지막 갈래(project 없음·정책 부재)는 **담당(user)** 만 보게 했고
함수 설명은 「작성자 본인만」이라 둘이 어긋났다. project 없는 문서를 `s9 assign`
으로 남에게 넘기면 만든 사람(creator)이 대시보드에서 자기 문서를 못 봤다
(두 머신 실측 2026-09-06, tests/p5_live.py 장면 4 S4-e). 이제 담당과 만든 사람
둘 다 본다. admin·프로젝트 멤버 규칙은 그대로다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ doc_visible_creator
"""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9")
MACHINE = "TESTMACH"
ROOT, ALICE, BOB, DAVE = "root", "alice", "bob", "dave"
RE_ID = re.compile(r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?")


class DocVisibleCreator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9dvc-")
        env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": MACHINE,
               "S9_REWORK_WATCH": "off"}
        for k in ("S9_SESSION", "S9_USER", "S9_SYNC"):
            env.pop(k, None)

        def cli(*argv, user=None):
            e = dict(env)
            if user:
                e["S9_USER"] = user
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=e, timeout=20, stdin=subprocess.DEVNULL)
            if r.returncode != 0:
                raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
            return r
        cli("init")
        cli("user", "add", ROOT, "--role", "admin")
        cli("user", "add", ALICE, user=ROOT)
        cli("user", "add", BOB, user=ROOT)
        cli("user", "add", DAVE, user=ROOT)
        # project 없는 문서 — alice 가 만들고 bob 에게 넘긴다 (p5_live 장면 1)
        r = cli("new", "request", "--title", "solo", "--summary", "s", "--goal", "g",
                "--body", "b", user=ALICE)
        cls.solo = RE_ID.search(r.stdout).group(0)
        cli("assign", cls.solo, BOB, "--why", "handoff", user=ALICE)
        # project 문서 — alice 가 만들고 bob 에게 넘긴 뒤 alice 는 멤버에서 빠진다
        cli("project", "add", "px", "--name", "PX", "--user", ROOT)
        cli("project", "member", "px", "add", ALICE, "--user", ROOT)
        cli("project", "member", "px", "add", BOB, "--user", ROOT)
        r = cli("new", "request", "--title", "pxdoc", "--summary", "s", "--goal", "g",
                "--body", "b", "--project", "px", user=ALICE)
        cls.pxdoc = RE_ID.search(r.stdout).group(0)
        cli("assign", cls.pxdoc, BOB, "--why", "handoff", user=ALICE)
        cli("project", "member", "px", "rm", ALICE, "--user", ROOT)

        cls.patch = mock.patch.dict(os.environ, {"S9_ROOT": cls.root,
                                                 "S9_MACHINE": MACHINE})
        cls.patch.start()
        for k in ("S9_SESSION", "S9_USER", "S9_SYNC"):
            os.environ.pop(k, None)
        spec = importlib.util.spec_from_loader(
            "s9mod_dvc", importlib.machinery.SourceFileLoader("s9mod_dvc", S9 + ".py"))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.m.rebuild_index(quiet=True)
        rows = {r["id"]: r for r in cls.m.load_catalog()}
        cls.solo_row = rows[cls.solo]
        cls.px_row = rows[cls.pxdoc]

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_fixture_handoff_is_real(self):
        """전제: 넘긴 뒤 담당은 bob, 만든 사람은 alice 로 남아 있다."""
        self.assertEqual(self.solo_row["user"], BOB)
        self.assertEqual(self.solo_row["creator"], ALICE)

    # S1
    def test_s1_holder_sees(self):
        self.assertTrue(self.m.doc_visible(self.solo_row, BOB))

    # S2 — p5_live S4-e 가 못 보던 자리
    def test_s2_creator_sees_after_handoff(self):
        self.assertTrue(self.m.doc_visible(self.solo_row, ALICE))
        # 카탈로그 행이 아니라 문서 meta 로 물어도 같은 답 (HTTP /api/doc 경로)
        path = self.m.find_path(self.solo)
        meta = self.m.read_doc(path)[0]
        self.assertTrue(self.m.doc_visible(meta, ALICE))

    # S3
    def test_s3_neither_holder_nor_creator_is_denied(self):
        self.assertFalse(self.m.doc_visible(self.solo_row, DAVE))
        with mock.patch.object(self.m, "sync_mode", return_value="remote"):
            self.assertFalse(self.m.doc_visible(self.solo_row, "stranger"))
        with mock.patch.object(self.m, "sync_mode", return_value="local"):
            self.assertTrue(self.m.doc_visible(self.solo_row, "stranger"),
                            "정책 부재(local·미등록)는 기존대로 막지 않는다")

    # S4
    def test_s4_admin_sees(self):
        self.assertTrue(self.m.doc_visible(self.solo_row, ROOT))

    # S5 — 프로젝트 규칙: 멤버, 그리고 **그 문서를 만든 사람**
    #
    # 이 시험은 원래 「creator 여도 멤버가 아니면 못 본다」였다. REQ-20260908-026
    # 이 그 판정을 뒤집었다 — 두 vault 가 만나 같은 slug 가 충돌하고 사람이 한쪽을
    # 택하면 진 쪽 사용자가 멤버에서 빠지는데, 그 사람들 문서는 project 를 그대로
    # 들고 있어 **자기가 쓴 글이 자기 화면에서 사라졌다**. 새는 것은 없다(그 사람이
    # 쓴 글이고 vault 는 git 으로 통째 오간다). 남은 자물쇠 셋(creator 원 필드만 ·
    # PRJ 문서 제외 · 보임≠권한)은 tests/test_project_access_gate.py 가 지킨다.
    def test_s5_project_rule_creator_added(self):
        self.assertEqual(self.px_row["creator"], ALICE)
        self.assertTrue(self.m.doc_visible(self.px_row, BOB))       # 활성 멤버
        self.assertTrue(self.m.doc_visible(self.px_row, ALICE),
                        "만든 사람은 멤버에서 빠져도 자기 문서를 본다 (REQ-20260908-026)")
        self.assertEqual(self.m.doc_access(self.px_row, ALICE), "creator-outside")
        self.assertFalse(self.m.doc_visible(self.px_row, DAVE))     # 남은 남이다

    # S6 — 설명과 판정이 같다
    def test_s6_docstring_matches_verdict(self):
        doc = self.m.doc_visible.__doc__ or ""
        self.assertIn("담당", doc)
        self.assertIn("만든 사람", doc)
        self.assertNotIn("작성자 본인만", doc)

    # S7 — 옛 문서(creator 필드 없음): user 가 곧 creator
    def test_s7_legacy_row_without_creator(self):
        row = {"type": "request", "project": "", "user": BOB}
        self.assertTrue(self.m.doc_visible(row, BOB))
        self.assertFalse(self.m.doc_visible(row, ALICE))
        self.assertFalse(self.m.doc_visible(row, DAVE))


if __name__ == "__main__":
    unittest.main()
