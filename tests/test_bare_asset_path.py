"""맨 경로로 적힌 첨부도 그림이 되는가 (REQ-20260829-008-62x6).

문서 뷰어는 `[Image: assets/<문서id>/<파일>]` 표기를 그림으로 낸다. 그런데
글을 쓰다 보면 표기 없이 경로만 적는 일이 잦다 — "스크린샷:
vault/requests/2026/08/assets/REQ-…/….png" 처럼. 그러면 독자에게는 그림이
있어야 할 자리에 긴 경로 한 줄만 남는다. 사용자가 그것을 보고 "문서 내의
이미지가 경로로만 노출된다" 고 보고했다.

표기를 쓰라고 사람에게 미루는 것은 답이 아니다 — 그 사람은 다음에도 경로를
적는다. 화면이 알아보면 된다.

다만 **모든 경로가 그림이 되어서는 안 된다**. 백틱으로 감싼 경로는 그 경로
자체를 보여주려고 쓴 것이고(이 저장소의 노트에 그런 줄이 많다), 이미지가
아닌 첨부는 그림이 될 수 없다. 그래서 이 시험은 무엇을 집는가만큼 **무엇을
집지 않는가**를 잰다.

규칙은 JS 로 화면에 있고 이 시험은 파이썬이다. 그래서 정규식 리터럴을
화면에서 **꺼내 와** 실제 문자열에 대 본다 — 두 벌을 손으로 적으면 언젠가
한 벌만 고쳐진다(이 저장소가 되풀이해 배운 것).

실행: python3 tests/ bare_asset_path
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

DID = "REQ-20260829-008-62x6"

HIT = [
    (f"스크린샷: vault/requests/2026/08/assets/{DID}/20260829T092333-image.png",
     "본문에 흔히 적히는 모양 — 저장소 상대경로"),
    (f"assets/{DID}/shot.png 를 보라",
     "prefix 없이 assets/ 로 시작해도"),
    (f"(캡처: vault/requests/2026/08/assets/{DID}/a-b_c.JPEG)",
     "괄호 안, 대문자 확장자, 하이픈·밑줄 파일명"),
    (f"vault/requests/2026/08/assets/REQ-20260829-008/shot.webp",
     "축약 id — 카탈로그에서 풀린다(B2)"),
]

MISS = [
    (f"`vault/requests/2026/08/assets/{DID}/shot.png` 를 열어라",
     "백틱 안 — 경로를 보여주려고 쓴 자리다(B3)"),
    (f"assets/{DID}/notes.md 에 적었다",
     "이미지가 아닌 첨부(B4)"),
    (f"[Image: assets/{DID}/shot.png]",
     "표기가 먼저 집는다 — 두 번 집으면 안 된다(B5)"),
    ("vault/requests/2026/08/REQ-20260829-008-62x6.md",
     "assets/ 가 없는 문서 경로"),
    ("web/index.html 의 md2html 을 고쳤다",
     "그냥 소스 파일 경로"),
]


def js_template_to_py(tmpl, consts):
    """화면의 템플릿 문자열을 파이썬 정규식으로.

    JS 문자열 리터럴 안이라 역슬래시가 두 겹이다. `${DOC_ID_PREFIX}` 같은
    자리는 화면에서 읽어 온 상수로 채운다 — 규칙을 여기에 다시 적으면 화면과
    갈리고, 갈린 것을 아무도 모른다."""
    for k, v in consts.items():
        tmpl = tmpl.replace("${%s}" % k, v)
    return tmpl.replace("\\\\", "\\").replace("\\/", "/")


class BareAssetPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        m = re.search(r"const BARE_ASSET_RE = new RegExp\(\s*"
                      r"([\s\S]+?),\s*\"([gimsuy]*)\"\);", cls.src)
        # 건너뛰지 않는다 — 규칙이 없으면 **없다고 말해야** 한다. 없는 것을
        # 조용히 통과시키는 시험은 시험이 아니다 (REQ-20260829-001 이 검사
        # 쪽에서 걷어낸 것과 같은 조용한 성공이다).
        assert m, "BARE_ASSET_RE 가 없다 — 맨 경로는 여전히 글자로만 뜬다"
        cls.flags = m.group(2)
        # 백틱으로 이어 붙인 조각들을 하나로
        parts = re.findall(r"`([^`]*)`", m.group(1))
        assert parts, "템플릿 조각을 찾지 못했다"
        consts = {}
        # IMAGE_EXTS 가 여기 끼는 것은 2026-08-29 부터다 (REQ-20260829-015 반려):
        # "무엇이 그림인가"를 화면 세 곳이 각자 들고 있었고 실제로 어긋나 있어
        # (heic 를 모르는 쪽, 서버가 모르는 avif 를 아는 쪽) 한 상수로 모았다.
        for name in ("DOC_ID_PREFIX", "DOC_ID_TAIL", "IMAGE_EXTS"):
            c = re.search(r'const %s = "(.*)";' % name, cls.src)
            assert c, "%s 를 찾지 못했다" % name
            consts[name] = c.group(1).replace("\\\\", "\\")
        lit = js_template_to_py("".join(parts), consts)
        cls.lit = lit
        cls.re = re.compile(lit, re.IGNORECASE if "i" in cls.flags else 0)

    # ---------- 규칙이 있는가 ----------

    def test_the_rule_exists_and_is_global(self):
        """한 문단에 그림이 둘일 수 있다 — 첫 하나만 집으면 안 된다."""
        self.assertIn("g", self.flags, "g 플래그가 없다 — 첫 경로만 그림이 된다")

    def test_it_reuses_the_marker_rendering(self):
        """표기와 **같은 함수**로 그림을 낸다 — 두 벌을 적으면 한 벌만 고쳐진다.

        계약은 그대로고 **찾는 모양**만 2026-08-29 에 바뀌었다. attImg 이
        md2html 안의 지역 화살표 함수였는데, 그림이 실패하면 다시 거는 손
        (REQ-20260829-019)이 붙으면서 맨 위의 함수 선언으로 나왔다 — 재시도와
        못 받은 자리가 거기 매여 있어야 두 벌이 생기지 않는다.
        """
        body = self._bare_body()
        self.assertIn("attImg(", body, "표기와 같은 함수를 쓰지 않는다")
        self.assertIn("catFind", body,
                      "축약 id 를 풀지 않는다 — 사람이 쓰는 모양이 축약이다")
        m = re.search(r"function attImg\(did, f, p\)\{([\s\S]{0,900}?)\n\}",
                      self.src)
        self.assertIsNotNone(m, "attImg 를 찾지 못했다")
        self.assertIn("attimg", m.group(1), "표기와 같은 클래스를 쓰지 않는다")
        # 주소를 짓는 자리는 attAssetUrl 한 곳이다 (REQ-20260908-047) — 산출물의
        # `p=` 갈래가 생기면서 두 벌이 될 뻔했다. 그 함수가 라우트를 쥔다.
        self.assertIn("attAssetUrl(did, f, p)", m.group(1),
                      "문서 가시성을 상속하는 라우트로 내야 한다")
        self.assertIn("attImg(did, f, p)", self.src,
                      "표기 쪽이 그 함수를 쓰지 않는다 — 갈라진 채로 둔 것이다")

    def test_the_marker_rule_runs_first(self):
        """[Image:] 가 먼저다 (B5). 순서가 뒤집히면 표기 안의 경로를 먼저 집어
        표기가 깨진 채로 남는다."""
        i_marker = self.src.find(r"\[Image: (assets\/")
        i_bare = self.src.find("BARE_ASSET_RE,")
        self.assertGreaterEqual(i_marker, 0, "표기 규칙을 찾지 못했다")
        self.assertGreaterEqual(i_bare, 0, "맨 경로 규칙을 찾지 못했다")
        self.assertLess(i_marker, i_bare, "맨 경로 규칙이 표기보다 앞선다")

    def test_backticks_are_left_alone(self):
        """B3. 백틱 판정은 정규식이 아니라 치환부가 offset 으로 본다."""
        body = self._bare_body()
        self.assertIn("offset", body,
                      "앞뒤 글자를 보지 않는다 — 백틱 안을 가려낼 수 없다")
        self.assertIn('"`"', body, "백틱을 무엇으로 알아보는지가 없다")

    def _bare_body(self):
        m = re.search(r"\.replace\(BARE_ASSET_RE,([\s\S]{0,600}?)\n      \}\);",
                      self.src)
        self.assertIsNotNone(m, "맨 경로 치환부를 찾지 못했다")
        return m.group(1)

    # ---------- 무엇을 집는가 ----------

    def test_it_catches_the_shapes_people_write(self):
        for text, why in HIT:
            with self.subTest(why):
                self.assertRegex(text, self.re, f"못 집는다: {why}")

    def test_it_leaves_the_rest_alone(self):
        for text, why in MISS:
            with self.subTest(why):
                if "백틱" in why or "표기가 먼저" in why:
                    continue          # 정규식이 아니라 치환부·순서가 맡는다
                self.assertNotRegex(text, self.re, f"잘못 집는다: {why}")

    def test_it_pulls_out_the_doc_id_and_the_file(self):
        """집기만 해서는 못 쓴다 — 어느 문서의 어느 파일인지 갈라 내야 한다."""
        text = f"vault/requests/2026/08/assets/{DID}/20260829T092333-image.png"
        m = self.re.search(text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), DID)
        self.assertEqual(m.group(2), "20260829T092333-image.png")

    def test_it_stops_at_the_end_of_the_path(self):
        """문장부호까지 파일명으로 삼키면 링크가 깨진다."""
        m = self.re.search(f"(캡처: assets/{DID}/shot.png)")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "shot.png")
        m2 = self.re.search(f"assets/{DID}/shot.png, 그리고")
        self.assertEqual(m2.group(2), "shot.png")


if __name__ == "__main__":
    unittest.main()
