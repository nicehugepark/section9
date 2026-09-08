"""산출물은 같은 검색으로 찾는다 (REQ-20260908-046-62x6).

주인 물음 2026-09-08 15:38: 「검색은 어떻게 하나?」

확인한 사실: 「하나도 없다」는 아니었다. 문서에 붙은 첨부는 `--body` 로 파일명이
찾히고(ingest 가 본문에 `assets/<문서ID>/<파일명>` 을 적어 둔다), pdf·txt·py 는
추출 본문 사이드카로 내용까지 찾힌다. 없던 축은 **종류**다 — 「그때 만든 그 영상」을
찾을 길이 없었다.

**다른 검색 명령을 내지 않는다.** 이 하네스에서 산출물의 정체성은 그것을 만든
요청이고, 두 번째 인덱스는 원본과 어긋날 수 있는 두 번째 진실이 된다 — 이 저장소는
같은 이유로 첨부 본문을 catalog 에서 빼고 index/ 를 gitignore 하는 판정을 이미
두 번 내렸다. 그래서 같은 명령에 **면(facet)만** 더하고, 그 값은 물을 때
파일시스템에서 센다.

- `s9 search <말> --attach`            첨부를 가진 문서만
- `s9 search <말> --attach-type video` 그 종류의 첨부를 가진 문서만

이름이 `--type` 이 아닌 까닭: 그 이름은 이미 **문서의 종류**(request·knowledge…)를
뜻한다. 같은 것에 이름은 하나다(규약 2조 ⑤).

실행: python3 tests/ asset_search
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

FM = """---
id: {id}
type: request
title: {title}
summary: {title}
status: open
user: alice
project: section9
tags: []
created: 2026-09-08T10:00:00+09:00
updated: 2026-09-08T10:00:00+09:00
---

## Original

{title}
"""


class AssetFacets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9asearch-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_USER": "alice"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], env=cls.env, capture_output=True)
        d = os.path.join(cls.root, "vault", "requests", "2026", "09")
        os.makedirs(d, exist_ok=True)
        cls.docs = {
            "REQ-20260908-901": "영상이 붙은 것",
            "REQ-20260908-902": "그림만 있는 것",
            "REQ-20260908-903": "아무것도 없는 것",
        }
        for i, t in cls.docs.items():
            with open(os.path.join(d, i + ".md"), "w", encoding="utf-8") as f:
                f.write(FM.format(id=i, title=t))
        for i, names in (("REQ-20260908-901", ["clip.mp4", "tone.wav"]),
                         ("REQ-20260908-902", ["shot.png"])):
            a = os.path.join(d, "assets", i)
            os.makedirs(a, exist_ok=True)
            for n in names:
                with open(os.path.join(a, n), "wb") as f:
                    f.write(b"\0" * 16)
            os.makedirs(os.path.join(a, ".text"), exist_ok=True)
            with open(os.path.join(a, ".text", "x.txt"), "w") as f:
                f.write("사이드카")
        subprocess.run([S9, "index", "rebuild"], env=cls.env,
                       capture_output=True)
        prev = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = cls.root
        try:
            spec = importlib.util.spec_from_loader(
                "s9_asearch", importlib.machinery.SourceFileLoader(
                    "s9_asearch", S9))
            cls.m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.m)
        finally:
            if prev is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = prev

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def _search(self, *extra):
        r = subprocess.run([S9, "search", "것", *extra], env=self.env,
                           capture_output=True, encoding="utf-8")
        return r.stdout or ""

    # ---------- 세는 자리 ----------

    def test_it_counts_what_is_actually_there(self):
        d = os.path.join(self.root, "vault", "requests", "2026", "09")
        got = self.m.doc_attachments(os.path.join(d, "REQ-20260908-901.md"),
                                     "REQ-20260908-901")
        self.assertEqual(sorted(n for n, _e in got), ["clip.mp4", "tone.wav"])

    def test_the_sidecar_is_not_an_attachment(self):
        # 추출 본문(.text/)은 검색을 위한 파생물이다 — 첨부로 세면 두 번 센다
        d = os.path.join(self.root, "vault", "requests", "2026", "09")
        got = self.m.doc_attachments(os.path.join(d, "REQ-20260908-902.md"),
                                     "REQ-20260908-902")
        self.assertEqual([n for n, _e in got], ["shot.png"])

    def test_a_document_without_attachments_counts_zero(self):
        d = os.path.join(self.root, "vault", "requests", "2026", "09")
        self.assertEqual(
            self.m.doc_attachments(os.path.join(d, "REQ-20260908-903.md"),
                                   "REQ-20260908-903"), [])

    def test_the_group_comes_from_the_one_table(self):
        self.assertEqual(self.m.asset_group(".mp4"), "video")
        self.assertEqual(self.m.asset_group(".wav"), "audio")
        self.assertEqual(self.m.asset_group(".png"), "image")
        self.assertEqual(self.m.asset_group(".zzz"), "")

    # ---------- 같은 명령의 면 ----------

    def test_without_the_facet_everything_still_shows(self):
        out = self._search()
        for i in self.docs:
            self.assertIn(i, out, "면을 안 걸었는데 결과가 줄었다")

    def test_attach_keeps_only_documents_that_have_one(self):
        out = self._search("--attach")
        self.assertIn("REQ-20260908-901", out)
        self.assertIn("REQ-20260908-902", out)
        self.assertNotIn("REQ-20260908-903", out,
                         "첨부가 없는 문서가 남았다")

    def test_a_kind_narrows_further(self):
        out = self._search("--attach-type", "video")
        self.assertIn("REQ-20260908-901", out)
        self.assertNotIn("REQ-20260908-902", out, "그림뿐인 문서가 영상으로 잡혔다")
        self.assertNotIn("REQ-20260908-903", out)

    def test_it_says_which_file_matched(self):
        out = self._search("--attach-type", "video")
        self.assertIn("clip.mp4", out,
                      "무엇이 맞았는지 안 보이면 답이 반쪽이다")
        self.assertNotIn("tone.wav", out,
                         "영상을 물었는데 소리 파일까지 적었다")

    def test_a_kind_implies_attach(self):
        # `--attach-type` 만 주어도 첨부 없는 문서는 빠져야 한다 — 사람이 두 손잡이를
        # 함께 눌러야 하는 것은 손잡이가 아니라 함정이다.
        self.assertNotIn("REQ-20260908-903", self._search("--attach-type", "image"))

    def test_an_empty_kind_finds_nothing_rather_than_everything(self):
        out = self._search("--attach-type", "slides")
        for i in self.docs:
            self.assertNotIn(i, out, "없는 종류를 물었는데 전부 나왔다")

    # ---------- 회귀 ----------

    def test_the_document_type_filter_keeps_its_name(self):
        # `--type` 은 여전히 문서의 종류다 (규약 2조 ⑤ — 같은 것에 이름은 하나)
        r = subprocess.run([S9, "search", "것", "--type", "request"],
                           env=self.env, capture_output=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REQ-20260908-901", r.stdout)

    def test_the_catalog_is_not_asked_to_carry_attachments(self):
        # 두 번째 인덱스를 만들지 않는다 — 물을 때 파일시스템에서 센다
        cat = os.path.join(self.root, "index", "catalog.jsonl")
        with open(cat, encoding="utf-8") as f:
            body = f.read()
        self.assertNotIn("clip.mp4", body,
                         "첨부가 catalog 에 실렸다 — 대시보드가 폴링마다 전량을 "
                         "받는 파일이고, 어긋날 수 있는 두 번째 진실이 된다")


if __name__ == "__main__":
    unittest.main()
