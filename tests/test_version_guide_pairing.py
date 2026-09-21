"""VERSION 과 가이드의 짝을 커밋 검사가 본다 (REQ-20260921-010-62x6).

실제 사고 2026-09-21: commit ff1ff60e3(09:32)이 VERSION 을 0.9.3 으로 올렸는데
docs/guide-windows.md 머리는 「기준 버전 0.9.2」 그대로였다. 커밋 검사는 그것을
보지 못하고 지나갔고, 어긋남은 한 시간 뒤 백그라운드 전체 실행(9822b20bf, 10:26)
에서야 드러나 커밋 차단이 걸렸다(REQ-20260921-008-62x6).

원인은 `bin/s9-guard` 의 `select_related_tests` 가 담긴 파일 이름을 후보로 쓸 때
bin/·web/·harness/ 로 한정하고 .md·.txt 를 뺀 것이었다 — VERSION 은 어느 갈래에도
없고 docs/guide-windows.md 는 .md 라 빠져서, 그 둘의 짝을 보는
`tests/test_release_guide_match.py` 가 한 번도 불리지 않았다.

고친 자리는 좁다: VERSION 과 docs/ 의 파일을 이름 후보로 들인다. 스모크에 넣지
않은 이유는 판 내는 절차(DOC-20260918-001)다 — VERSION 을 올리고 가이드를 뒤에
손보는 걸음에서 스모크는 그 사이의 **모든** 커밋을 막는다. 이름 후보로 들이면
짝을 어긋나게 담은 그 커밋 하나만 막힌다.

실행: python3 tests/ version_guide_pairing
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
GUARD = os.path.join(ROOT, "bin", "s9-guard")
PAIR_TEST = "test_release_guide_match.py"


def _load(name):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, GUARD))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _diff(path, minus=(), plus=()):
    """-U0 꼴의 가짜 diff 한 파일분."""
    out = [f"diff --git a/{path} b/{path}", f"--- a/{path}", f"+++ b/{path}",
           f"@@ -1,{len(minus)} +1,{len(plus)} @@"]
    out += [f"-{ln}" for ln in minus] + [f"+{ln}" for ln in plus]
    return "\n".join(out) + "\n"


class TheReleasePairIsPickedInThisRepo(unittest.TestCase):
    """저장소의 실제 tests/ 로 잰다 — 고른 결과가 진짜 시험 파일을 가리켜야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.g = _load("s9guard_version_pair")

    def select(self, staged, diff_text):
        return self.g.select_related_tests(staged, diff_text)

    def picked(self, sel):
        return {fn for fn, _ in sel["picked"]}

    def test_a1_a_version_bump_alone_calls_the_pair_test(self):
        """정상 ① — VERSION 만 담아도 짝을 보는 시험이 불린다."""
        sel = self.select(["VERSION"], _diff("VERSION", minus=["0.9.2"], plus=["0.9.3"]))
        self.assertIn("VERSION", sel["names"], "VERSION 이 이름 후보에 없다")
        self.assertIn(PAIR_TEST, self.picked(sel),
                      f"뽑힘: {sorted(self.picked(sel))} / 밖: {sel['dropped']}")

    def test_a2_the_guide_alone_calls_the_pair_test(self):
        """정상 ② — 가이드만 담아도 같은 시험이 불린다."""
        sel = self.select(["docs/guide-windows.md"],
                          _diff("docs/guide-windows.md", plus=["기준 버전 0.9.3"]))
        self.assertIn("guide-windows.md", sel["names"])
        self.assertIn(PAIR_TEST, self.picked(sel),
                      f"뽑힘: {sorted(self.picked(sel))} / 밖: {sel['dropped']}")

    def test_a3_the_incident_commit_would_have_been_caught(self):
        """정상 ③ — 사고 커밋 ff1ff60e3 이 담은 것(VERSION · docs/RELEASE-NOTES.md)."""
        staged = ["VERSION", "docs/RELEASE-NOTES.md"]
        sel = self.select(staged, _diff("VERSION", minus=["0.9.2"], plus=["0.9.3"]))
        self.assertIn(PAIR_TEST, self.picked(sel),
                      "이 짝이 불리지 않아 어긋남이 한 시간 뒤에야 드러났다")

    def test_a4_the_pick_stays_inside_the_cap_and_budget(self):
        """경계 ④ — 상한 밖으로 밀리지 않는다 (짧은 것부터 담으므로 늘 든다)."""
        sel = self.select(["VERSION"], _diff("VERSION", minus=["0.9.2"], plus=["0.9.3"]))
        self.assertLessEqual(len(sel["picked"]), self.g.RELATED_CAP)
        self.assertLessEqual(sel["seconds"], self.g.RELATED_BUDGET_SEC)
        self.assertIn(PAIR_TEST, self.picked(sel))

    def test_a5_the_pair_test_really_reads_both(self):
        """이 시험이 딛는 전제 — 짝을 보는 시험이 두 이름을 실제로 담는다."""
        with open(os.path.join(HERE, PAIR_TEST), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("VERSION", src)
        self.assertIn("guide-windows.md", src)


class TheOldContractStands(unittest.TestCase):
    """임시 tests/ 와 가짜 diff — 넓힌 자리가 다른 자리를 건드리지 않았는가."""

    @classmethod
    def setUpClass(cls):
        cls.g = _load("s9guard_version_pair_tmp")
        cls.tmp = tempfile.mkdtemp(prefix="s9pair-")
        cls.tdir = os.path.join(cls.tmp, "tests")
        os.makedirs(cls.tdir)
        files = {
            "test_reads_protocol.py": 'open("harness/common/PROTOCOL.md").read()\n',
            "test_reads_guide.py": 'open("docs/guide-windows.md").read()\n',
            "test_unrelated.py": "def test_x(self): pass\n",
        }
        for fn, body in files.items():
            with open(os.path.join(cls.tdir, fn), "w", encoding="utf-8") as f:
                f.write(body)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def select(self, staged, diff_text):
        return self.g.select_related_tests(staged, diff_text, tests_dir=self.tdir, times={})

    def test_b1_markdown_under_harness_is_still_not_a_name(self):
        """경계 ⑤ — bin/·web/·harness/ 의 .md 는 여전히 후보가 아니다."""
        sel = self.select(["harness/common/PROTOCOL.md"],
                          _diff("harness/common/PROTOCOL.md", plus=["한 줄 더"]))
        self.assertEqual(sel["names"], [])
        self.assertEqual(sel["picked"], [])

    def test_b2_a_docs_file_no_test_names_picks_nothing(self):
        """실패 ⑥ — 오탐 없음: 아무 시험도 이름을 담지 않은 문서는 아무것도 안 부른다."""
        sel = self.select(["docs/99-없는문서.md"], _diff("docs/99-없는문서.md", plus=["x"]))
        self.assertEqual(sel["names"], ["99-없는문서.md"])
        self.assertEqual(sel["picked"], [])

    def test_b3_the_docs_name_picks_only_the_test_that_reads_it(self):
        sel = self.select(["docs/guide-windows.md"],
                          _diff("docs/guide-windows.md", plus=["x"]))
        self.assertEqual({fn for fn, _ in sel["picked"]}, {"test_reads_guide.py"})
        self.assertIn("파일 이름 guide-windows.md", dict(sel["picked"])["test_reads_guide.py"])

    def test_b4_the_same_name_is_probed_once(self):
        """같은 이름이 두 번 들어와도 이유가 겹쳐 적히지 않는다."""
        sel = self.select(["docs/guide-windows.md", "docs/guide-windows.md"],
                          _diff("docs/guide-windows.md", plus=["x"]))
        self.assertEqual(sel["names"].count("guide-windows.md"), 1)


if __name__ == "__main__":
    unittest.main()
