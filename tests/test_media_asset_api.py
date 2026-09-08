"""산출물을 내주고 미디어를 받는 **서버 쪽** (REQ-20260908-047 · -048).

화면 쪽 시험은 `test_media_asset.py` 에 있다. 이 파일은 그 뒤의 문 — 라우트·
가시성·Range·상한 — 만 잰다.

사용자 지적 둘. ① "그렇게 만들어진 산출물이 요청 문서에서 경로가 표시되긴 한데,
대시보드에서 직접 다운로드나 열어보기가 되지 않는다." ② "음악, 영상 등 미디어
파일도 다양하게 등록이 되어야 할 것 같다."

막고 있던 것은 타입 검사가 아니었다 — 잰 사실 셋이다.
- `projects/<slug>/assets/` 를 내주는 문이 **없었다**. 문서 첨부만 `/api/asset`
  으로 나갔고, 요청으로 만든 산출물은 본문에 적힌 글자로만 남았다.
- `_send_asset` 이 `Range` 를 몰랐다. 영상은 seek 이 없으면 못 쓰고, Safari 는
  206 을 못 받으면 재생을 시작조차 하지 않는다.
- 상한 30MB 는 1080p 영상 1분 언저리다 — 영상이 안 붙는 실제 벽이 그 숫자였다.

서버가 도는 자리(라우트)는 소스의 계약으로, 스스로 판정하는 자리(함수)는 직접
불러서 본다 — 시험 하나가 프로세스를 띄우지 않게(빠른 테스트 규칙,
REQ-20260830-027).

실행: python3 tests/ media_asset_api
"""
import importlib.machinery
import importlib.util
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
S9_SRC = S9 + ".py"


def _load():
    spec = importlib.util.spec_from_loader(
        "s9mediaapi", importlib.machinery.SourceFileLoader("s9mediaapi", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _route(src, path):
    """한 라우트의 본문 — 다음 `parsed.path ==` 까지."""
    i = src.find(f'parsed.path == "{path}"')
    if i < 0:
        return ""
    j = src.find("parsed.path ==", i + 10)
    return src[i:j if j > 0 else i + 4000]


class Kinds(unittest.TestCase):
    """종류·상한·표기가 확장자 목록 **한 벌**에서 온다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_kinds(self):
        m = self.m
        with self.subTest("s6_media_extensions_are_known"):
            for e in (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac",
                      ".opus"):
                self.assertEqual(m.asset_kind("x" + e), "audio", e)
            for e in (".mp4", ".m4v", ".webm", ".mov", ".mkv", ".avi"):
                self.assertEqual(m.asset_kind("x" + e), "video", e)
            self.assertEqual(m.asset_kind("a.png"), "image")
            self.assertEqual(m.asset_kind("a.zzz"), "file")

        with self.subTest("s3_marks_name_the_media"):
            self.assertEqual(m.asset_mark("a/b.mp3"), "[Audio: a/b.mp3]")
            self.assertEqual(m.asset_mark("a/b.mp4"), "[Video: a/b.mp4]")
            self.assertEqual(m.asset_mark("a/b.png"), "[Image: a/b.png]")
            self.assertEqual(m.asset_mark("a/b.csv"), "[File: a/b.csv]")

        with self.subTest("s3_the_pattern_catches_all_marks"):
            for kind in ("Image", "Audio", "Video", "File", "Attach"):
                got = m.ASSET_RE.findall(f"[{kind}: assets/X/a.bin]")
                self.assertEqual(got, [(kind, "assets/X/a.bin")], kind)

        with self.subTest("s2_the_cap_splits_by_kind"):
            self.assertEqual(m.attach_max_for("a.mp3"),
                             m.ATTACH_MAX_MEDIA_BYTES)
            self.assertEqual(m.attach_max_for("a.mp4"),
                             m.ATTACH_MAX_MEDIA_BYTES)
            self.assertEqual(m.attach_max_for("a.png"), m.ATTACH_MAX_BYTES)
            self.assertEqual(m.attach_max_for("a.pdf"), m.ATTACH_MAX_BYTES)
            # 영상 상한은 저장소 무게를 여는 값이 아니다 (REQ-20260908-045):
            # 30MB 보다는 크고, 스트리밍 업로드 없이 감당할 선 안에 있다.
            self.assertGreater(m.ATTACH_MAX_MEDIA_BYTES, m.ATTACH_MAX_BYTES)
            self.assertLessEqual(m.ATTACH_MAX_MEDIA_BYTES, 128 * 1024 * 1024)

        with self.subTest("s6_the_mime_is_what_a_player_expects"):
            for name, want in (("a.mp3", "audio/mpeg"), ("a.mp4", "video/mp4"),
                               ("a.webm", "video/webm"),
                               ("a.mov", "video/quicktime")):
                self.assertEqual(m.asset_ctype(name), want, name)
        with self.subTest("s7_text_keeps_its_charset"):
            self.assertIn("charset=utf-8", m.asset_ctype("a.md"))
            self.assertIn("charset=utf-8", m.asset_ctype("a.json"))
            self.assertNotIn("charset", m.asset_ctype("a.png"))

        with self.subTest("s6_playable_is_narrower_than_media"):
            self.assertTrue(m.asset_playable("a.mp4"))
            self.assertTrue(m.asset_playable("a.mp3"))
            # 컨테이너는 미디어지만 브라우저가 못 연다 — 재생기를 세우면
            # 사람은 검은 칸을 본다. 붙는 것과 재생되는 것은 다른 물음이다.
            self.assertFalse(m.asset_playable("a.mkv"))
            self.assertFalse(m.asset_playable("a.avi"))
            self.assertFalse(m.asset_playable("a.png"))


class ProjectAssetPath(unittest.TestCase):
    """산출물의 경로 판정 — 모양만 본다. 밖은 전부 ""."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        cls.dir = os.path.join(ROOT, "projects", "section9", "assets")

    def test_project_asset_path(self):
        m = self.m
        if not os.path.isdir(self.dir):
            self.skipTest("projects/section9/assets 가 없다")
        with tempfile.NamedTemporaryFile(dir=self.dir, suffix=".mp3",
                                         delete=False) as f:
            f.write(b"ID3" + b"\0" * 100)
            made = f.name
        self.addCleanup(os.remove, made)
        rel = "projects/section9/assets/" + os.path.basename(made)

        with self.subTest("s1_a_real_output_resolves"):
            self.assertEqual(m.project_asset_path(rel),
                             os.path.realpath(made))
        with self.subTest("s4_traversal_is_refused"):
            for bad in ("projects/section9/assets/../../users/a/secrets/k",
                        "projects/../bin/s9.py",
                        "/etc/passwd",
                        "projects/section9/assets/",
                        "vault/requests/2026/09/x.md",
                        "projects/section9/CONTEXT.md",
                        "projects//assets/a.mp3",
                        ""):
                self.assertEqual(m.project_asset_path(bad), "", bad)
        with self.subTest("s4_a_missing_file_is_not_a_path"):
            self.assertEqual(
                m.project_asset_path("projects/section9/assets/nope.nope"), "")
        with self.subTest("s2_the_body_must_name_it"):
            self.assertTrue(m.doc_refs_path(f"산출물: {rel} 참고", rel))
            self.assertFalse(m.doc_refs_path("다른 이야기", rel))
            self.assertFalse(m.doc_refs_path("", rel))
        with self.subTest("s2_naming_the_place_names_what_is_in_it"):
            # 실물 문서는 파일이 아니라 자리를 적는다 (2026-09-08 실측:
            # vault 안의 산출물 참조는 전부 디렉토리로 적혀 있다).
            deep = "projects/section9/assets/014-sync-design/a.mp4"
            self.assertTrue(m.doc_refs_path(
                "산출물: projects/section9/assets/014-sync-design/", deep))
            # 그러나 `assets/` 하나로는 열리지 않는다 — 그 문서 하나가
            # 프로젝트의 산출물 전부를 여는 문이 되면 안 된다.
            self.assertFalse(m.doc_refs_path(
                "projects/section9/assets/", deep))
            self.assertFalse(m.doc_refs_path(
                "projects/section9/assets/다른자리/", deep))


class Routes(unittest.TestCase):
    """문은 하나, 검사도 하나 — 소스의 계약으로 잰다."""

    @classmethod
    def setUpClass(cls):
        with open(S9_SRC, encoding="utf-8") as f:
            cls.src = f.read()
        cls.asset = _route(cls.src, "/api/asset")
        cls.info = _route(cls.src, "/api/asset-info")

    def test_routes(self):
        with self.subTest("s6_the_info_route_exists"):
            self.assertTrue(self.info, "/api/asset-info 를 찾지 못했다")
        with self.subTest("s3_both_routes_ask_the_same_gate"):
            for frag in ("me = viewer_of(qs)", "doc_visible(meta_a, me)"):
                self.assertIn(frag, self.asset, frag)
            self.assertIn("asset_full(qs", self.asset)
            self.assertIn("asset_full(qs", self.info)
        with self.subTest("s3_denial_and_absence_look_the_same"):
            self.assertIn('self._send(404, "text/plain", b"not found")',
                          self.info)
            self.assertNotIn("403", self.info)
        with self.subTest("s5_download_is_a_flag_on_the_same_door"):
            self.assertIn('qs.get("dl", [""])[0] == "1"', self.asset)
        with self.subTest("s6_the_info_carries_what_a_player_needs"):
            for key in ('"kind"', '"mime"', '"size"', '"playable"',
                        '"url"', '"download_url"'):
                self.assertIn(key, self.info, key)
        with self.subTest("s2_the_upload_cap_comes_from_one_place"):
            up = _route(self.src, "/api/chat/upload")
            self.assertIn("attach_max_for(name)", up)
            self.assertNotIn("(30MB 한도)", up)

    def test_send_asset_contract(self):
        """`_send_asset` 이 재생기·내려받기가 요구하는 것을 낸다."""
        i = self.src.find("def _send_asset(")
        self.assertGreater(i, 0, "_send_asset 이 없다")
        body = self.src[i:i + 4000]
        with self.subTest("s5_seek_is_advertised"):
            self.assertIn('self.send_header("Accept-Ranges", "bytes")', body)
        with self.subTest("s4_partial_content"):
            self.assertIn("self.send_response(206 if rng else 200)", body)
            self.assertIn('"Content-Range"', body)
            self.assertIn("self.send_response(416)", body)
        with self.subTest("s5_disposition_is_set"):
            self.assertIn('"Content-Disposition"', body)
        with self.subTest("s4_it_does_not_read_the_whole_file"):
            # 64MB 영상을 구간마다 통째로 읽으면 아끼려던 것을 도로 쓴다.
            self.assertNotIn("data = f.read()", body)
            self.assertIn("f.seek(start)", body)
        with self.subTest("s4_range_wins_over_revalidation"):
            # 재생기는 If-None-Match 와 Range 를 함께 보낸다 — 304 를 먼저
            # 내주면 그 부분 요청은 답을 못 받는다.
            self.assertLess(
                body.find("rng = self._range_of(size)"),
                body.find('self.headers.get("If-None-Match")'))


class RangeParsing(unittest.TestCase):
    """`Range:` 한 줄을 구간으로 — 함수를 직접 불러서 본다."""

    @classmethod
    def setUpClass(cls):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        i = src.find("        def _range_of(self, size):")
        assert i > 0, "_range_of 이 없다"
        j = src.find("\n        def ", i + 10)
        block = src[i:j]
        block = "\n".join(ln[8:] if ln.startswith(" " * 8) else ln
                          for ln in block.splitlines())
        ns = {"re": re}
        exec(compile(block, "<range>", "exec"), ns)      # noqa: S102
        cls.fn = staticmethod(ns["_range_of"])

    def _call(self, hdr, size):
        class H:
            headers = type("D", (), {"get": staticmethod(
                lambda k, d=None: (hdr if k == "Range" else d))})()
        return self.fn(H(), size)

    def test_range_parsing(self):
        with self.subTest("s5_no_range_is_the_whole_thing"):
            self.assertIsNone(self._call(None, 100))
            self.assertIsNone(self._call("", 100))
            self.assertIsNone(self._call("items=0-1", 100))
        with self.subTest("s4_a_closed_range"):
            self.assertEqual(self._call("bytes=0-99", 1000), (0, 99))
            self.assertEqual(self._call("bytes=10-19", 1000), (10, 19))
        with self.subTest("s4_an_open_range_runs_to_the_end"):
            self.assertEqual(self._call("bytes=5-", 100), (5, 99))
        with self.subTest("s4_a_suffix_range_counts_back"):
            self.assertEqual(self._call("bytes=-10", 100), (90, 99))
            self.assertEqual(self._call("bytes=-500", 100), (0, 99))
        with self.subTest("s4_past_the_end_is_unsatisfiable"):
            self.assertIs(self._call("bytes=100-200", 100), False)
            self.assertIs(self._call("bytes=50-10", 100), False)
            self.assertIs(self._call("bytes=-0", 100), False)
        with self.subTest("s4_an_over_long_end_is_clamped"):
            self.assertEqual(self._call("bytes=90-500", 100), (90, 99))
        with self.subTest("s4_multiple_ranges_fall_back_to_the_whole"):
            # 안 쓰는 갈래를 구현하면 시험할 수 없는 코드가 남는다.
            self.assertIsNone(self._call("bytes=0-9,20-29", 100))


if __name__ == "__main__":
    unittest.main()
