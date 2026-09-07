"""catalog 가 없어도 문서를 id 로 찾는다 (REQ-20260907-060).

`locate()` 는 catalog 가 낡았을 때 vault 를 훑는데, 파일 이름이 `<id>.md` 인지만
봤다. 프로젝트 문서는 이름이 slug(`section9.md`)라 그 규칙에 안 걸리고, 그래서
프로젝트를 id 로 여는 길이 catalog 한 벌뿐이었다 — catalog 가 없는 자리에서는
문서가 있어도 「찾을 수 없습니다」였다.

고정하는 계약 넷.
1. 이름에 id 가 없는 문서도 프론트매터 `id:` 로 찾는다 — 진실은 파일 안이다.
2. 이름이 id 꼴인 파일은 열지 않는다 — 비용을 늘리지 않는다.
3. 같은 id 가 둘이면 None — 모호함은 catalog 갈래와 같은 답이다.
4. 프론트매터가 없는 파일은 건너뛴다 — 죽지 않는다.

실행: python3 tests/ locate_by_id
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-locate-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_locate", importlib.machinery.SourceFileLoader("s9_mod_locate", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

PRJ = "PRJ-20260823-001"
REQ = "REQ-20260907-001-abcd"


def doc(doc_id, body="\n## Notes\n"):
    return f"---\nid: {doc_id}\ntype: project\ntitle: t\nstatus: active\n---\n{body}"


class WithoutACatalog(unittest.TestCase):
    """catalog 가 없는 자리 — vault 만 있다. `locate` 는 fallback 으로만 답한다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-locate-root-")
        self.vault = os.path.join(self.root, "vault")
        os.makedirs(os.path.join(self.vault, "projects"))
        os.makedirs(os.path.join(self.vault, "requests", "2026", "09"))
        self._p = [mock.patch.object(mod, "ROOT", self.root),
                   mock.patch.object(mod, "VAULT", self.vault),
                   mock.patch.object(mod, "resolve_id", lambda _id: [])]
        for p in self._p:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._p])

    def _write(self, rel, text):
        p = os.path.join(self.vault, rel)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_a_slug_named_project_is_found_by_its_id(self):
        p = self._write("projects/section9.md", doc(PRJ))
        self.assertEqual(mod.locate(PRJ), p,
                         "이름이 slug 인 문서를 id 로 못 찾는다 — catalog 한 벌에만 기댄다")

    def test_an_id_named_doc_is_still_found_by_name(self):
        p = self._write(f"requests/2026/09/{REQ}.md", doc(REQ))
        self.assertEqual(mod.locate(REQ), p)

    def test_id_named_files_are_not_opened(self):
        """이름이 id 꼴인 파일은 읽지 않는다 — fallback 의 비용을 늘리지 않는다."""
        self._write(f"requests/2026/09/{REQ}.md", doc(REQ))
        self._write("projects/section9.md", doc(PRJ))
        opened = []
        real = mod._frontmatter_id

        def spy(path, *a, **k):
            opened.append(os.path.basename(path))
            return real(path, *a, **k)

        with mock.patch.object(mod, "_frontmatter_id", spy):
            mod.locate(PRJ)
        self.assertNotIn(f"{REQ}.md", opened, "이름에 id 가 있는 파일을 열었다")
        self.assertIn("section9.md", opened)

    def test_two_files_with_the_same_id_is_ambiguous(self):
        self._write("projects/a.md", doc(PRJ))
        self._write("projects/b.md", doc(PRJ))
        self.assertIsNone(mod.locate(PRJ), "복제된 id 를 첫 것으로 집었다 — 모호함은 None 이다")

    def test_a_file_without_frontmatter_is_skipped(self):
        self._write("projects/notes.md", "# 그냥 메모\n본문\n")
        self._write("projects/section9.md", doc(PRJ))
        self.assertTrue(mod.locate(PRJ).endswith("section9.md"))

    def test_unknown_id_is_none(self):
        self._write("projects/section9.md", doc(PRJ))
        self.assertIsNone(mod.locate("PRJ-19700101-999"))


class FrontmatterId(unittest.TestCase):
    def _tmp(self, text):
        p = os.path.join(TMP, f"fm-{abs(hash(text))}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_reads_the_id(self):
        self.assertEqual(mod._frontmatter_id(self._tmp(doc(PRJ))), PRJ)

    def test_quoted_id(self):
        self.assertEqual(mod._frontmatter_id(self._tmp(f'---\nid: "{PRJ}"\n---\n')), PRJ)

    def test_no_frontmatter(self):
        self.assertEqual(mod._frontmatter_id(self._tmp("# 제목\n")), "")

    def test_missing_file(self):
        self.assertEqual(mod._frontmatter_id(os.path.join(TMP, "없다.md")), "")


if __name__ == "__main__":
    unittest.main()
