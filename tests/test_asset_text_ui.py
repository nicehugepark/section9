"""첨부 안의 글자를 화면에서 읽을 수 있는가 (REQ-20260827-005-62x6).

`s9 search <문구> --body` 는 이미 첨부(PDF 등) 안의 글자를 전문으로 찾는다
(REQ-20260826-020). 검색 결과에도 그 줄이 그대로 나온다. 그런데 문서를 열면
첨부는 파일 이름 칩 하나뿐이라, **찾아 놓고도 읽을 수가 없었다.** 원본을 열면
브라우저의 PDF 뷰어로 넘어가 대시보드를 떠난다.

서버는 `GET /api/asset-text?doc=&f=` 로 그 본문을 준다 — 검사는 원본
파일 라우트와 글자 그대로 같고, 없는 것과 못 보는 것을 같은 404 로 낸다.
화면이 할 일은 셋이다: 발췌를 보여주고, 펼치면 전문을 주고, 검색해서 왔으면
찾던 문구가 있는 자리를 펴 보이는 것.

이 테스트가 지키는 계약은 일곱이다.

  ① 본문은 문서 가시성을 상속하는 그 라우트에서만 온다 — 파일 경로를 화면이
     직접 조립하지 않는다.
  ② 사이드카가 없는 첨부(이미지·압축 등)는 404 이고 **그게 정상이다** —
     에러 문구를 그리지 않는다. 없는 것을 매번 알리면 있는 것이 안 읽힌다.
  ③ 첫 화면은 발췌다. 전문은 사용자가 펼칠 때만 — 4천 자가 넘는 본문이
     문서 한가운데를 밀어내지 않는다.
  ④ 아주 긴 본문에는 상한이 있고, 잘랐으면 잘랐다고 말한다.
  ⑤ 펼친 본문은 스크롤 상자다 — 키보드로도 스크롤된다(WCAG 2.1.1).
  ⑥ PDF 안의 글자는 남이 쓴 글자다 — 반드시 escape 를 거친다.
  ⑦ 검색 결과의 조각이 첨부에서 왔으면 어느 파일인지 밝힌다. 파일 이름 없이
     줄 번호만 보이면 문서 본문의 그 줄로 읽힌다.

실행: python3 tests/ asset_text_ui
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

JARGON = ("sidecar", "asset-text", "API", "fetch", "404", "라우트", "인덱스")


def js_func(src, name):
    """함수 하나의 소스를 통째로 꺼낸다 (중괄호 균형)."""
    i = src.find("function " + name)
    if i < 0:
        i = src.find("async function " + name)
    if i < 0:
        return ""
    j = src.find("{", i)
    depth, k = 0, j
    while k < len(src):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1
    return src[i:]


class AssetTextUI(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()
        self.fn = js_func(self.src, "attachTexts")
        self.assertTrue(self.fn, "첨부 본문을 붙이는 함수(attachTexts)가 없다")

    # ---------- ① 검사가 걸린 한 곳에서만 ----------

    def test_text_comes_from_the_gated_route(self):
        self.assertIn("/api/asset-text?doc=", self.fn,
                      "본문은 문서 가시성을 상속하는 라우트에서 와야 한다")
        self.assertRegex(self.fn, r"encodeURIComponent\(",
                         "문서 id·파일명은 인코딩해서 넘겨야 한다")
        self.assertNotRegex(self.fn, r"assets/\$|\.text/|vault/",
                            "화면이 파일 경로를 직접 조립하면 검사를 비껴간다")

    def test_it_runs_after_the_document_body_is_drawn(self):
        loaddoc = js_func(self.src, "loadDoc")
        self.assertIn("attachTexts(", loaddoc,
                      "문서를 그린 뒤 첨부 본문을 붙여야 한다")

    def test_chip_carries_its_own_document_and_file(self):
        """칩이 data-doc 을 쓰면 전역 문서 링크 위임이 클릭을 가로챈다."""
        m = re.search(r'<a class="attfile"[^`]*?>', self.src)
        self.assertIsNotNone(m, "첨부 칩을 그리는 자리를 찾지 못했다")
        chip = m.group(0)
        self.assertRegex(chip, r'data-a(doc|tt)', "칩이 자기 문서·파일을 들고 있어야 한다")
        self.assertNotIn('data-doc=', chip,
                         'data-doc 은 문서 열기 위임의 이름이다 — 칩에 쓰면 클릭이 가로채인다')

    # ---------- ② 없는 것은 정상 ----------

    def test_missing_sidecar_is_silent(self):
        self.assertRegex(self.fn, r"if\s*\(!\s*r\.ok\s*\)\s*(return|continue|break)",
                         "본문이 없으면 조용히 넘어가야 한다")
        for bad in ("실패", "오류", "에러", "없습니다"):
            self.assertNotIn(bad, self.fn,
                             f"본문이 없는 첨부에 '{bad}' 를 그리면 잡음이 된다")

    # ---------- ③④ 발췌 먼저, 전문은 펼칠 때 ----------

    def test_excerpt_first_full_text_on_demand(self):
        self.assertRegex(self.src, r"const ATT_HEAD\s*=\s*\d+",
                         "발췌 분량이 값으로 정해져 있어야 한다")
        self.assertIn("attmore", self.src, "전문을 펼치는 버튼이 없다")
        m = re.search(r'<button[^>]*class="attmore"[^>]*>([^<]*)</button>', self.src)
        self.assertIsNotNone(m, "펼치기 버튼을 찾지 못했다")
        self.assertRegex(m.group(1), r"보기|펼치",
                         "버튼은 동사+목적이어야 한다")

    def test_very_long_text_is_capped_and_says_so(self):
        m = re.search(r"const ATT_MAX\s*=\s*(\d+)", self.src)
        self.assertIsNotNone(m, "아주 긴 본문의 상한이 없다")
        self.assertGreaterEqual(int(m.group(1)), 4000,
                                "4천 자는 넘게 보여줘야 한다 (전문이 그만큼 온다)")
        self.assertRegex(self.src, r"ATT_MAX[\s\S]{0,600}?(생략|여기까지)",
                         "잘랐으면 잘랐다고 말해야 한다")

    # ---------- ⑤ 스크롤 상자는 키보드로도 스크롤된다 ----------

    def test_scroll_box_is_reachable_by_keyboard(self):
        css = re.search(r"\.attx\.open\{([^}]*)\}", self.src)
        self.assertIsNotNone(css, "펼친 본문의 스크롤 상자 스타일이 없다")
        self.assertIn("overflow", css.group(1), "긴 본문은 상자 안에서 스크롤돼야 한다")
        self.assertIn("max-height", css.group(1), "높이 상한이 없으면 문서를 밀어낸다")
        self.assertRegex(self.fn, r'tabIndex\s*=\s*0|tabindex="0"',
                         "스크롤 상자는 키보드로도 스크롤돼야 한다 (WCAG 2.1.1)")

    # ---------- ⑥ 남이 쓴 글자 ----------

    def test_attachment_text_is_escaped(self):
        self.assertRegex(self.fn, r"\b(esc|hl)\(",
                         "PDF 안의 글자를 그대로 넣으면 태그가 살아난다")
        for rhs in re.findall(r"innerHTML\s*=\s*([^;]+);", self.fn):
            if re.search(r"\b(full|body|clip|brief|j\.text)\b", rhs):
                self.assertRegex(
                    rhs, r"\b(esc|hl|brief)\(|\bbrief\b",
                    "본문 문자열을 그대로 innerHTML 에 넣으면 태그가 살아난다")

    # ---------- ⑦ 이 줄이 어디서 왔는지 ----------

    def test_search_snippet_names_the_attachment_it_came_from(self):
        cand = [c for c in re.findall(r'<div class="snip">.*?</div>', self.src)
                if "hl(m.text" in c]
        self.assertTrue(cand, "검색 결과 조각을 그리는 자리를 찾지 못했다")
        snip = cand[0]
        self.assertIn("m.file", snip,
                      "첨부에서 온 줄이면 어느 파일인지 밝혀야 한다")
        self.assertIn("esc(m.file)", snip, "파일명도 escape 를 거쳐야 한다")

    # ---------- 문구 ----------

    def test_wording_is_in_the_users_language(self):
        """화면에 나가는 말(한글이 든 조각)만 본다 — 코드의 이름은 대상이 아니다."""
        seen = [s for s in re.findall(r">([^<>`$]{2,120})<", self.fn)
                if re.search(r"[가-힣]", s)]
        self.assertTrue(seen, "첨부 본문 블록에 사용자에게 보이는 말이 없다")
        for line in seen:
            for j in JARGON:
                self.assertNotIn(j, line,
                                 f"화면 문구에 내부 용어({j})가 새면 안 된다: {line}")


if __name__ == "__main__":
    unittest.main()
