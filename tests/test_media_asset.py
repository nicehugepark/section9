"""산출물을 열고 미디어를 재생한다 (REQ-20260908-047 · REQ-20260908-048).

주인 지적 2026-09-08: 「산출물이 요청 문서에 경로로 표시되긴 하는데 대시보드에서
열거나 내려받을 수 없다」, 「이미지가 그려지듯 음악·영상도 실행이 되어야 한다」.

그때 화면이 하던 일은 이랬다 — 그림만 그려졌고(`[Image:]`·맨 경로), 그림이 아닌
첨부는 📎 칩 하나(새 탭)뿐이었으며, **표기 없이 맨 경로로 적힌 그림 아닌 산출물은
아무 손잡이도 없는 글자**였다. 소리·영상은 그 칩으로 떨어져 문서 안에서 재생되지
않았다.

이 시험이 재는 것 셋:
  ① 그림이 아닌 맨 경로도 규칙(BARE_FILE_RE)이 집는가 — 백틱 안은 빼고.
  ② 소리·영상이 그 자리의 재생기로 서는가 — 자동 재생 없이, 못 그리는 형식이면
     빈 자리 대신 내려받는 길로.
  ③ 화면의 확장자 목록이 서버 TYPE_GROUPS 와 글자 그대로 같은가 — 두 벌이
     어긋나면 그 확장자만 조용히 맨 글자가 된다(그림 목록이 실제로 그랬다).

규칙은 JS 로 화면에 있고 이 시험은 파이썬이다. 그래서 정규식·상수를 화면에서
**꺼내 와** 실제 문자열에 대 본다 — 두 벌을 손으로 적으면 언젠가 한 벌만 고쳐진다.

실행: python3 tests/ media_asset
"""
import os
import re
import unittest

from webasset import index_path   # 브라우저가 받는 한 장을 본다 (REQ-20260829-027)

INDEX = index_path()
DID = "REQ-20260908-047-62x6"


def js_template_to_py(tmpl, consts):
    """화면의 템플릿 문자열을 파이썬 정규식으로 (test_bare_asset_path 와 같은 손)."""
    for k, v in consts.items():
        tmpl = tmpl.replace("${%s}" % k, v)
    return tmpl.replace("\\\\", "\\").replace("\\/", "/")


class MediaAsset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.consts = {}
        for name in ("DOC_ID_PREFIX", "DOC_ID_TAIL", "IMAGE_EXTS",
                     "AUDIO_EXTS", "VIDEO_EXTS"):
            m = re.search(r'const %s = "(.*)";' % name, cls.src)
            assert m, "%s 를 찾지 못했다" % name
            cls.consts[name] = m.group(1).replace("\\\\", "\\")
        # OTHER_EXTS 는 조각을 이어 붙인 배열이다 — 조각을 모아 하나로 만든다
        m = re.search(r"const OTHER_EXTS = \[([\s\S]+?)\]\.join\(\"\|\"\);", cls.src)
        assert m, "OTHER_EXTS 를 찾지 못했다"
        pieces = []
        for tok in re.findall(r'"([^"]+)"|(\bAUDIO_EXTS\b|\bVIDEO_EXTS\b)',
                              m.group(1)):
            pieces.append(cls.consts[tok[1]] if tok[1] else tok[0])
        cls.consts["OTHER_EXTS"] = "|".join(pieces)
        # 맨 경로 규칙을 꺼내 온다
        rm = re.search(r"const BARE_FILE_RE = new RegExp\(\s*"
                       r"([\s\S]+?),\s*\"([gimsuy]*)\"\);", cls.src)
        assert rm, ("BARE_FILE_RE 가 없다 — 그림이 아닌 산출물은 여전히 "
                    "손잡이 없는 글자다")
        parts = re.findall(r"`([^`]*)`", rm.group(1))
        assert parts, "템플릿 조각을 찾지 못했다"
        cls.flags = rm.group(2)
        cls.re = re.compile(js_template_to_py("".join(parts), cls.consts),
                            re.IGNORECASE if "i" in rm.group(2) else 0)

    # ---------- ① 그림이 아닌 맨 경로 (REQ-047) ----------

    def test_a_bare_document_path_is_picked_up(self):
        """S2. 산출물이 흔히 적히는 모양 — 저장소 상대경로에 pdf."""
        for txt, why in [
            (f"산출물: vault/requests/2026/09/assets/{DID}/report.pdf", "pdf"),
            (f"assets/{DID}/summary.md 에 적었다", "md"),
            (f"(표: vault/requests/2026/09/assets/{DID}/rows.csv)", "괄호 안 csv"),
            (f"vault/requests/2026/09/assets/{DID}/theme.mp3", "소리"),
            (f"vault/requests/2026/09/assets/{DID}/clip.MP4", "대문자 확장자"),
        ]:
            with self.subTest(why=why):
                self.assertIsNotNone(self.re.search(txt),
                                     "%s — 규칙이 집지 못한다" % why)

    def test_paths_that_must_stay_plain(self):
        """S3·S4. 백틱 안과 그림은 이 규칙이 집지 않는다."""
        # 그림은 그림 규칙(BARE_ASSET_RE)이 맡는다 — 여기서 겹쳐 집으면 재시도와
        # 못 받은 자리가 붙지 않은 두 번째 그림이 생긴다.
        self.assertIsNone(self.re.search(f"assets/{DID}/shot.png"),
                          "그림까지 집는다 — 두 규칙이 겹친다")
        self.assertIsNone(self.re.search("vault/requests/2026/09/%s.md" % DID),
                          "assets/ 없는 문서 경로를 집는다")

    def test_backticks_are_left_alone(self):
        """S3. 백틱 판정은 정규식이 아니라 치환부가 offset 으로 본다."""
        body = self._body("BARE_FILE_RE")
        self.assertIn("offset", body, "앞뒤 글자를 보지 않는다")
        self.assertIn('"`"', body, "백틱을 무엇으로 알아보는지가 없다")
        self.assertIn("catFind", body, "축약 id 를 풀지 않는다")

    def test_the_rule_is_global(self):
        """한 문단에 산출물이 둘일 수 있다 — 첫 하나만 집으면 안 된다."""
        self.assertIn("g", self.flags, "g 플래그가 없다")

    def test_one_place_decides_what_a_file_becomes(self):
        """표기든 맨 경로든 attAny 한 곳으로 모인다 — 갈리면 자리마다 다르게 선다."""
        self.assertIn("function attAny(did, f)", self.src, "가르는 곳이 없다")
        self.assertIn("hold(attAny(did, f))", self.src,
                      "[File:] 표기가 그 곳을 쓰지 않는다")
        self.assertIn("hold(attAny(r ? r.id : did, f))", self.src,
                      "맨 경로가 그 곳을 쓰지 않는다")

    # ---------- ② 열고 내려받는 손잡이 (REQ-047) ----------

    def test_a_file_gets_a_chip_and_a_download_handle(self):
        """S1·S5. 이미 있는 칩 어휘에 「내려받기」가 한 덩이로 붙는다."""
        body = self._fn("attFileChip")
        self.assertIn('class="attfile"', body, "있던 칩 어휘를 쓰지 않는다")
        self.assertIn("/api/asset?doc=", self._fn("attAssetUrl"),
                      "문서 가시성을 상속하는 라우트로 내야 한다")
        self.assertIn("attAssetUrl(did, f)", body, "그 라우트를 쓰지 않는다")
        self.assertIn("data-adoc=", body, "첨부 본문이 읽는 자리가 사라졌다")
        self.assertIn("내려받기", body, "내려받는 길이 없다")
        self.assertIn("download=", body, "download 속성이 없다 — 새 탭만 열린다")
        self.assertIn('class="atta"', body,
                      "두 손잡이가 한 덩이가 아니다 — 좁은 폭에서 갈라진다")

    # ---------- ③ 그 자리의 재생기 (REQ-048) ----------

    def test_media_plays_in_place_and_never_starts_by_itself(self):
        """S1·S2. `<audio>`·`<video>` 가 서고, 자동 재생 속성은 없다."""
        body = self._fn("attMedia")
        self.assertIn('vid ? "video" : "audio"', body,
                      "소리와 영상을 가르지 않는다")
        self.assertIn('controls preload="none"', body,
                      "손잡이가 없거나 문서를 여는 것만으로 파일을 받는다")
        self.assertIn("playsinline", body,
                      "playsinline 이 없다 — 휴대기기에서 전체 화면으로 튄다")
        self.assertNotIn("autoplay", body, "자동 재생이 켜져 있다")
        self.assertIn("내려받기", body, "재생기 옆에 내려받는 길이 없다")

    def test_a_format_the_browser_cannot_draw_falls_back(self):
        """S3. 못 그리는 형식은 빈 자리가 아니라 칩과 내려받기로 떨어진다."""
        body = self._fn("attMedia")
        self.assertIn("if (!attCanPlay(ext)) return attFileChip(did, f);", body,
                      "못 그리는 형식에 빈 재생기를 세운다")
        can = self._fn("attCanPlay")
        self.assertIn("canPlayType", can,
                      "브라우저에 묻지 않는다 — 목록으로 못 박으면 Safari 에서 갈린다")

    def test_a_player_that_fails_leaves_a_way_out(self):
        """S4. 재생기가 못 받으면 자리가 비지 않는다."""
        body = self._fn("attMedFail")
        self.assertIn("내려받기", body, "실패한 자리에 나갈 길이 없다")
        self.assertIn("새 탭에서 열기", body, "있던 손잡이 어휘를 안 쓴다")
        self.assertIn('contains("attmed")', self.src,
                      "재생기의 error 를 잡는 손이 없다")

    # ---------- ④ 두 벌이 아닌 한 벌 ----------

    def test_the_extension_lists_match_the_server(self):
        """S6. 화면의 소리·영상·그 밖 목록이 서버 TYPE_GROUPS 와 같다.

        어긋나면 그 확장자만 재생기가 서지 않거나 손잡이 없는 글자로 남는다 —
        그림 목록에서 실제로 벌어졌던 일이다(REQ-20260829-015).
        """
        s9 = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "s9.py")
        with open(s9, encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"TYPE_GROUPS = \{([\s\S]+?)\n\}", src)
        self.assertIsNotNone(m, "서버 TYPE_GROUPS 를 찾지 못했다")
        groups = {}
        for gm in re.finditer(r'"(\w+)":\s*\{([^}]+)\}', m.group(1)):
            groups[gm.group(1)] = {e.strip().strip('"').lstrip(".")
                                   for e in gm.group(2).split(",") if e.strip()}
        self.assertEqual(set(self.consts["AUDIO_EXTS"].split("|")),
                         groups["audio"], "소리 목록이 서버와 다르다")
        self.assertEqual(set(self.consts["VIDEO_EXTS"].split("|")),
                         groups["video"], "영상 목록이 서버와 다르다")
        want = set()
        for g, exts in groups.items():
            if g != "image":
                want |= exts
        self.assertEqual(set(self.consts["OTHER_EXTS"].split("|")), want,
                         "그림 아닌 확장자 목록이 서버와 다르다")

    # ---------- 손 ----------

    def _fn(self, name):
        m = re.search(r"function %s\([^)]*\)\{([\s\S]{0,1600}?)\n\}" % name,
                      self.src)
        self.assertIsNotNone(m, "%s 를 찾지 못했다" % name)
        return m.group(1)

    def _body(self, rename):
        m = re.search(r"\.replace\(%s,([\s\S]{0,600}?)\n      \}\)" % rename,
                      self.src)
        self.assertIsNotNone(m, "%s 치환부를 찾지 못했다" % rename)
        return m.group(1)


if __name__ == "__main__":
    unittest.main()
