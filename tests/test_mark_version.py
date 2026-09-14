"""마크는 이름 붙은 버전으로 남고, 한 줄로 되돌아온다 (REQ-20260914-002-62x6).

주인(2026-09-14 11:02): 「다시 롤백할 수 있도록 준비하고, 지금부터는 버전을 명시해서
시도해 보자. 그래야 롤백을 하거나 지정할 수 있지.」

마크는 파일 여덟 자리다 — svg 셋 · ico 하나 · png 셋 · 껍데기에 박히는 인라인 조각
하나. 「이전 것으로 되돌려 봐」 한마디가 여덟 자리를 손으로 맞추는 일이 되지 않게
하는 것이 이 계약이다.

  V1 한 버전은 제 디렉토리에 통째로 있다 — 얼굴 일곱 + header.svg + NOTE.md + build.py.
  V2 `use` 가 최상위 일곱을 그 버전과 **바이트까지** 같게 만들고, 껍데기의 마크
     조각을 그 버전의 header.svg 로 갈아 끼운다 — 조각은 하나뿐이고, 갈아 끼운
     뒤에도 눈(g.pupil)이 남아 있다(없으면 mark.js 가 붙을 곳을 잃는다).
  V3 실린 버전이 `web/assets/MARK_VERSION` 에 적히고 `mark ls` 가 그것을 ● 로 가른다.
  V4 되돌리기가 무손실이다 — 다른 버전을 실었다가 되돌리면 일곱도 조각도 처음과 같다.

실행: python3 tests/ mark_version
"""
import filecmp
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load():
    spec = importlib.util.spec_from_file_location(
        "s9_mark", os.path.join(ROOT, "bin", "s9_mark.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


MK = load()


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class AVersionIsWhole(unittest.TestCase):
    """V1. 한 버전은 제 디렉토리에 통째로 있다."""

    def test_v1_every_version_directory_holds_all_ten_files(self):
        names = MK.versions(ROOT)
        self.assertTrue(names, "web/assets/mark/ 아래에 버전이 하나도 없다")
        self.assertIn("v1", names, "되돌아갈 자리(v1)가 없다")
        _, _, store = MK.paths(ROOT)
        for name in names:
            for f in MK.FACES + MK.EXTRA:
                with self.subTest(version=name, file=f):
                    p = os.path.join(store, name, f)
                    self.assertTrue(os.path.isfile(p), "%s/%s 이 없다" % (name, f))
                    self.assertGreater(os.path.getsize(p), 0, "%s/%s 이 비었다" % (name, f))
            with self.subTest(version=name):
                self.assertTrue(MK.note(name, ROOT), "%s 의 NOTE.md 첫 줄이 비었다" % name)


class SwitchingIsExact(unittest.TestCase):
    """V2·V3·V4 — 임시 복사본 위에서만 갈아 끼운다(이 저장소는 건드리지 않는다)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9mark-")
        shutil.copytree(os.path.join(ROOT, "web"), os.path.join(self.tmp, "web"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        _, _, self.store = MK.paths(self.tmp)
        self.assets = os.path.join(self.tmp, "web", "assets")
        self.shell = os.path.join(self.tmp, "web", "index.html")

    def other(self):
        """견주기용 버전 하나 — v1 을 베껴 얼굴 한 장만 달리한다."""
        src, dst = os.path.join(self.store, "v1"), os.path.join(self.store, "vtest")
        shutil.copytree(src, dst)
        with open(os.path.join(dst, "mark.svg"), "a", encoding="utf-8") as f:
            f.write("<!-- vtest -->\n")
        with open(os.path.join(dst, "header.svg"), encoding="utf-8") as f:
            head = f.read().replace('<svg class="mark"', '<svg class="mark" data-v="test"', 1)
        with open(os.path.join(dst, "header.svg"), "w", encoding="utf-8") as f:
            f.write(head)
        return "vtest"

    def test_v2_use_replaces_both_the_faces_and_the_inline_snippet(self):
        other = self.other()
        MK.use(other, self.tmp)
        for f in MK.FACES:
            with self.subTest(f):
                self.assertTrue(
                    filecmp.cmp(os.path.join(self.assets, f),
                                os.path.join(self.store, other, f), shallow=False),
                    "web/assets/%s 가 %s 의 것과 다르다" % (f, other))
        html = read(self.shell)
        found = MK.INLINE_RE.findall(html)
        self.assertEqual(len(found), 1, "껍데기의 마크 조각이 하나가 아니다")
        self.assertEqual(found[0],
                         read(os.path.join(self.store, other, "header.svg")).strip(),
                         "껍데기의 조각이 그 버전의 header.svg 와 다르다")
        self.assertIn('<g class="pupil">', found[0],
                      "갈아 끼운 조각에 눈(g.pupil)이 없다 — mark.js 가 붙을 곳을 잃는다")

    def test_v3_the_installed_name_is_written_down_and_listed(self):
        other = self.other()
        MK.use(other, self.tmp)
        self.assertEqual(MK.installed(self.tmp), other, "MARK_VERSION 이 실린 이름과 다르다")
        rows = MK.table(self.tmp)
        hit = [r for r in rows if r.startswith("●")]
        self.assertEqual(len(hit), 1, "실린 버전 표시(●)가 하나가 아니다: %r" % rows)
        self.assertIn(other, hit[0])

    def test_v4_rolling_back_restores_every_byte(self):
        before = {f: open(os.path.join(self.store, "v1", f), "rb").read()
                  for f in MK.FACES}
        head_before = read(os.path.join(self.store, "v1", "header.svg")).strip()
        MK.use(self.other(), self.tmp)
        MK.use("v1", self.tmp)
        for f in MK.FACES:
            with self.subTest(f):
                self.assertEqual(open(os.path.join(self.assets, f), "rb").read(), before[f],
                                 "되돌린 web/assets/%s 가 v1 의 것과 다르다" % f)
        self.assertEqual(MK.INLINE_RE.findall(read(self.shell))[0], head_before,
                         "되돌린 껍데기의 조각이 v1 의 것과 다르다")
        self.assertEqual(MK.installed(self.tmp), "v1")


class TheShippedCopyMatchesItsVersion(unittest.TestCase):
    """지금 이 저장소에 실려 있는 것이 적힌 버전과 같은가 — 손으로 고치면 여기서 걸린다."""

    def test_v5_the_repo_copy_is_in_sync_with_the_named_version(self):
        name = MK.installed(ROOT)
        self.assertTrue(name, "web/assets/MARK_VERSION 이 없다 — 무엇이 실렸는지 아무 데도 없다")
        _, assets, store = MK.paths(ROOT)
        for f in MK.FACES:
            with self.subTest(f):
                self.assertTrue(
                    filecmp.cmp(os.path.join(assets, f), os.path.join(store, name, f),
                                shallow=False),
                    "web/assets/%s 가 %s 의 것과 다르다 — `bin/s9 mark use %s` 로 맞춘다"
                    % (f, name, name))
        shell = read(os.path.join(ROOT, "web", "index.html"))
        self.assertEqual(MK.INLINE_RE.findall(shell)[0],
                         read(os.path.join(store, name, "header.svg")).strip(),
                         "껍데기의 마크 조각이 %s 의 header.svg 와 다르다" % name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
