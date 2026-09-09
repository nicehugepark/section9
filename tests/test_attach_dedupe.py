"""같은 첨부는 한 벌만 (REQ-20260909-045-62x6).

실측 2026-09-09: 맥 세션이 캡처를 `vault/…/assets/<id>/` 에 바로 저장한 뒤 그
절대경로로 `s9 note --attach` 했다. `ingest_assets` 는 「그 이름이 이미 있다」만 보고
`-2` 사본을 만들어 본문을 그쪽으로 고쳐 썼다 — 원본이 제 자리에서 제 이름과
겹친 것이다(REQ-031 1장, REQ-040 4장, 크기 동일). 이름이 겹쳐도 **내용이 같으면**
그 파일을 가리켜야 한다; 내용이 다를 때만 `-2` 다.

함수 단위로 잰다 — `cmd_note`·`ingest_assets` 를 임시 S9_ROOT 에서 직접 부른다.
실행: python3 tests/ attach_dedupe
"""
import argparse
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9.py")

PNG_A = b"\x89PNG\r\n\x1a\n" + b"A" * 64
PNG_B = b"\x89PNG\r\n\x1a\n" + b"B" * 64      # 같은 크기, 다른 내용


def load(root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        name = "s9_attdedupe_%d" % abs(hash(root))
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


class SameAttachmentStaysOne(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9-attdedupe-")
        cls.src_dir = tempfile.mkdtemp(prefix="s9-attdedupe-src-")
        for k in ("S9_SESSION",):
            os.environ.pop(k, None)
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "tester"
        env = dict(os.environ)
        # 문서 하나는 CLI 로 한 번만 만든다 — 나머지는 함수 직접 호출이다.
        out = subprocess.run(
            [sys.executable, S9, "new", "request", "--title", "첨부 중복",
             "--summary", "s", "--goal", "g", "--size", "S", "--body", "x"],
            capture_output=True, encoding="utf-8", env=env, timeout=60)
        assert out.returncode == 0, out.stderr
        cls.did = out.stdout.split()[0]
        cls.m = load(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        shutil.rmtree(cls.src_dir, ignore_errors=True)

    # -- 도우미 -------------------------------------------------------------
    def _write(self, name, data):
        p = os.path.join(self.src_dir, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def _note(self, *attach):
        self.m.cmd_note(argparse.Namespace(
            id=self.did, text="캡처", file=None, attach=list(attach), user=None,
            agent=None, label="", item="", result="", transcript="",
            started="", anchor=""))

    def _asset_dir(self):
        return self.m.doc_asset_dir(self.did)

    def _files(self, stem):
        d = self._asset_dir()
        return sorted(f for f in os.listdir(d)
                      if f.startswith(stem) and f.endswith(".png"))

    def _marks(self, stem):
        _meta, body = self.m.read_doc(self.m.locate(self.did))
        return [ln for ln in body.splitlines()
                if ln.startswith("[Image: ") and stem in ln]

    # -- 시나리오 -----------------------------------------------------------
    def test_s1_same_file_twice_is_one_file(self):
        """정상 — 같은 파일을 두 번 붙여도 assets 에는 하나, `-2` 없음."""
        src = self._write("s1.png", PNG_A)
        self._note(src)
        self._note(src)
        self.assertEqual(self._files("s1"), ["s1.png"])

    def test_s2_same_name_different_content_gets_minus_two(self):
        """경계 — 이름은 같고 내용이 다르면 덮어쓰지 않고 `-2` 가 선다."""
        src = self._write("s2.png", PNG_A)
        self._note(src)
        self._write("s2.png", PNG_B)
        self._note(src)
        self.assertEqual(self._files("s2"), ["s2-2.png", "s2.png"])
        with open(os.path.join(self._asset_dir(), "s2.png"), "rb") as f:
            self.assertEqual(f.read(), PNG_A, "먼저 붙인 것이 덮였다")

    def test_s3_source_already_inside_assets_is_not_copied(self):
        """회귀(실측 재현) — 원본이 이미 assets/<id>/ 안에 제 이름으로 있으면
        복사하지 않고 상대경로로만 고쳐 쓴다. 맥에서 `-2` 가 선 바로 그 경우다."""
        adir = self.m.doc_asset_dir(self.did, make=True)
        inside = os.path.join(adir, "s3.png")
        with open(inside, "wb") as f:
            f.write(PNG_A)
        self._note(inside)
        self.assertEqual(self._files("s3"), ["s3.png"])
        self.assertEqual(self._marks("s3"),
                         [f"[Image: assets/{self.did}/s3.png]"])

    def test_s4_marks_point_at_the_same_file(self):
        """회귀 — 두 번 붙인 뒤 본문의 첨부 줄은 모두 같은 파일 하나를 가리킨다."""
        src = self._write("s4.png", PNG_A)
        self._note(src)
        self._note(src)
        marks = self._marks("s4")
        self.assertTrue(marks, "첨부 줄이 없다")
        self.assertEqual(set(marks), {f"[Image: assets/{self.did}/s4.png]"})

    def test_same_content_helper(self):
        """판정은 크기+sha256 — 같은 크기의 다른 내용은 다르다."""
        a = self._write("h-a.png", PNG_A)
        a2 = self._write("h-a2.png", PNG_A)
        b = self._write("h-b.png", PNG_B)
        self.assertTrue(self.m._same_content(a, a2))
        self.assertTrue(self.m._same_content(a, a))
        self.assertFalse(self.m._same_content(a, b))
        self.assertFalse(self.m._same_content(a, a + ".none"))


if __name__ == "__main__":
    unittest.main()
