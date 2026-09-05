"""언급한 것을 그 자리에서 열고 집는다 (REQ-20260828-021 · REQ-20260828-022).

사용자(021): "이 터미널에서도 참조하는 파일을 언급하는데, 요청 문서든, 생성된
파일이든, 참조된 파일이든 실제 링크를 달아서 별도 탭으로 열던가 아니면
미리보기 팝업을 보이던가 했으면 좋겠다. 문서와 파일을 언급시키는데 찾아가서
확인하기 너무 불편하고 어려워."

사용자(022): "터미널 대답에서 문서 같은걸 대답을 하면, 다른 화면으로 이동하지
않고 바로 이어서 말하기가 됐으면 좋겠음."

두 요구가 **같은 글자**에 붙는다. 손잡이를 둘 세우면 문서 id 옆에 버튼이 둘
서거나 하나가 다른 하나를 가린다 — 그래서 글자 자체가 하나의 손잡이이고, 두
행동은 그 아래 펴지는 카드가 나눠 갖는다.

계약은 일곱이다.

  ① 터미널의 문서 id 는 **진짜 링크**다 — href 가 있어야 가운데클릭·Ctrl+클릭·
     "새 탭에서 열기" 가 따라온다 (REQ-20260827-013 이 세운 규율).
  ② 그러나 **맨클릭은 화면을 갈아치우지 않는다** (REQ-20260827-072 의 터미널
     판). 읽던 자리를 잃는 순간 이 기능은 Docs 탭으로 건너가는 것과 같아진다.
  ③ 집기는 **새 길을 만들지 않는다** — 이미 있는 `docPick` 을 부른다
     (REQ-20260827-064). 두 벌이면 아티클 스위치와의 배타 규칙(-073)이 한
     벌에만 걸린다.
  ④ 문서를 여는 길도 하나다 — 링크·카드·미리보기가 `docOpen` 한 곳을 쓴다.
  ⑤ **코드 블록 안에는 링크가 번지지 않는다.** 블록은 읽을 것이 아니라 붙일
     것이라, 앵커가 섞이면 드래그 선택이 링크 드래그가 되고 복사본에 마크업이
     들어간다 (REQ-20260828-023 designer 경고).
  ⑥ 파일은 **이미 있는 게이트로만** 내준다 — 문서 첨부는 `/api/asset`(문서
     가시성 상속). 저장소의 아무 파일이나 내주는 새 길은 만들지 않는다
     (DOC-20260827-007: 새로 만들면 옆문이다). 그 경계는 REQ-20260828-028.
  ⑦ 미리보기는 **한 번에 하나**이고, 본문은 접지 않고 **자른다** — 접힌 글은
     Ctrl+F 에 걸리지 않아 화면에 있는데도 없는 것처럼 보인다.

실행: python3 tests/ term_mention
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


class TermMention(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()
        # 주석 안의 낱말은 계약의 대상이 아니다 — 실행되는 줄만 본다
        self.code = re.sub(r"/\*[\s\S]*?\*/", "", self.src)
        self.code = re.sub(r"(?m)^\s*//.*$", "", self.code)

    # ---------- ① 진짜 링크 ----------

    def test_the_mention_is_a_real_link(self):
        """href 와 data-doc 이 **같은 값**이어야 한다 — 갈라지면 새 탭만 다른
        문서를 연다 (REQ-20260827-013 이 dlink 주석에 적어 둔 그 이유)."""
        m = re.search(r"const ccDocLink = id => \{([\s\S]*?)\n\};", self.code)
        self.assertIsNotNone(m, "터미널 문서 링크를 짓는 자리가 없다")
        fn = m.group(1)
        # 여는 값은 **카탈로그의 정식 id** 다 (REQ-20260828-021): 글에 적힌 짧은
        # 형태로 열면 열리는 문서가 없거나 다른 문서가 된다. 보이는 글자는 원문
        # 그대로이므로 "무엇을 여는가"와 "무엇이라 적혀 있는가"는 별개다.
        parts = re.findall(
            r'(href="#docs/|data-doc="|data-tdoc=")\$\{esc\(([\w.]+)\)\}', fn)
        self.assertEqual(len(parts), 3,
                         "href·data-doc·data-tdoc 셋이 다 있지는 않다: %s" % parts)
        self.assertEqual(len({p[1] for p in parts}), 1,
                         "href 와 data-doc 이 갈렸다 — 새 탭만 다른 문서를 연다")

    def test_the_terminal_paints_the_link_with_its_own_palette(self):
        """터미널은 tone 무관 상시 다크다 — 문서 화면의 잉크를 물려받으면
        종이 톤에서 검은 글씨가 검은 판에 앉는다."""
        m = re.search(r"\.ccterm a\.doclink\{([^}]*)\}", self.src)
        self.assertIsNotNone(m, "터미널 안 문서 링크의 색이 정해지지 않았다")
        self.assertIn("var(--cc-", m.group(1),
                      "터미널이 제 팔레트가 아닌 색으로 링크를 그린다")

    # ---------- ② 화면을 갈아치우지 않는다 ----------

    def test_a_plain_click_does_not_replace_the_screen(self):
        """터미널 손잡이는 `[data-doc]` 핸들러보다 **먼저** 잡혀야 한다.

        그 아래 핸들러는 Docs 탭으로 화면을 통째로 바꾼다 — 순서가 뒤집히면
        읽던 자리를 잃고, 이 기능은 탭을 건너뛰는 것과 같아진다.
        """
        i = self.code.find('closest("[data-tdoc]")')
        j = self.code.find('const doc = evEl(e.target)?.closest("[data-doc]")')
        self.assertGreater(i, 0, "터미널 손잡이를 잡는 자리가 없다")
        self.assertGreater(j, 0, "문서 열기 위임을 찾지 못했다")
        self.assertLess(i, j, "문서 열기가 터미널 손잡이보다 먼저 잡는다")
        blk = self.code[i:j]
        self.assertIn("e.preventDefault()", blk, "해시 이동이 그대로 일어난다")
        self.assertIn("ccPeek(", blk, "누르면 미리보기가 열리지 않는다")

    def test_modifier_clicks_stay_with_the_browser(self):
        """수식키·가운데클릭은 "새 탭에서 열기" 다 — 가로채면 두 군데서 열린다."""
        i = self.code.find('closest("[data-tdoc]")')
        blk = self.code[i:i + 400]
        for k in ("metaKey", "ctrlKey", "shiftKey", "altKey", "e.button !== 0"):
            self.assertIn(k, blk, "%s 를 브라우저에 남기지 않는다" % k)

    # ---------- ③④ 길은 하나씩 ----------

    def test_picking_reuses_the_one_path(self):
        """이어 말하기는 `docPick` 을 부른다 — 새 길을 내지 않는다."""
        i = self.code.find("dataset.ppick")
        self.assertGreater(i, 0, "미리보기의 집기 손잡이가 없다")
        self.assertIn("docPick(", self.code[i:i + 200],
                      "집기가 제 길을 새로 판다")

    def test_opening_a_document_has_one_door(self):
        """링크·카드·미리보기가 같은 함수로 문서를 연다."""
        self.assertIn("function docOpen(id)", self.code, "문 하나가 없다")
        self.assertIn("docOpen(doc.dataset.doc)", self.code,
                      "문서 링크가 제 손으로 탭을 바꾼다")
        self.assertIn("docOpen(t)", self.code,
                      "미리보기의 문서 열기가 다른 길로 간다")

    # ---------- ⑤ 블록 안으로는 번지지 않는다 ----------

    def test_the_link_never_leaks_into_a_code_block(self):
        """fenced 블록은 문서 id 규칙보다 **먼저** 자리표시자로 빠진다.

        순서가 뒤집히면 블록 안까지 앵커가 들어가고, 통째로 긁어 붙이는
        자리가 링크 드래그로 망가진다.
        """
        md = self.code[self.code.find("  const md = s => {"):]
        md = md[:md.find("ccBlocks(inline)")]
        blk = md.find("```")
        doc = md.find("DOC_ID_INLINE_RE")
        self.assertGreater(blk, 0, "코드블록 규칙을 찾지 못했다")
        self.assertGreater(doc, 0, "터미널에서 문서 id 를 링크로 만들지 않는다")
        self.assertLess(blk, doc, "문서 id 규칙이 코드블록보다 먼저 돈다")
        # 인라인 백틱 안에는 **명시적으로** 건다 — 순서를 바꾸지 않고.
        # 감싸는 것이 하나 더 늘 수 있어(REQ-20260828-028 이 같은 자리에서 코드
        # 경로 손잡이를 건다) 글자 하나가 아니라 **백틱 몸통에 ccDocs 가 걸리는
        # 것**을 짚는다. 이 시험이 지키는 것은 호출의 모양이 아니라 그 사실이다.
        self.assertRegex(self.code, r"ccDocs\([\w]*\(?c[,)]",
                         "인라인 코드 안의 문서 id 가 링크가 되지 않는다")

    # ---------- ⑥ 파일은 이미 있는 게이트로만 ----------

    def test_files_go_out_only_through_the_gate_that_exists(self):
        """첨부는 `/api/asset`(문서 가시성 상속)으로만. 저장소 파일을 내주는
        새 라우트는 만들지 않았다 — 경계는 REQ-20260828-028 에서 정한다."""
        i = self.code.find('class="ccasset"')
        self.assertGreater(i, 0, "첨부 경로에 손잡이가 없다")
        self.assertIn("/api/asset?doc=", self.code[i:i + 400],
                      "첨부를 이미 있는 게이트로 내주지 않는다")
        with open(S9_SRC, encoding="utf-8") as f:
            srv = f.read()
        routes = set(re.findall(r'parsed\.path == "(/api/[\w/-]+)"', srv))
        # 새 파일 서빙 라우트가 조용히 생기면 여기서 걸린다
        for bad in ("/api/file", "/api/source", "/api/repo", "/api/read"):
            self.assertNotIn(bad, routes,
                             "저장소 파일을 내주는 새 길이 생겼다: %s" % bad)

    # ---------- ⑦ 한 번에 하나, 접지 않고 자른다 ----------

    def test_only_one_preview_at_a_time(self):
        fn = self._fn("ccPeek")
        self.assertIn("ccPeekClose()", fn, "앞서 편 카드를 닫지 않는다")
        self.assertIn("ccPeekId === id", fn, "같은 것을 다시 눌러도 접히지 않는다")

    def test_the_preview_cuts_instead_of_folding(self):
        """접힌 글은 Ctrl+F 에 걸리지 않는다 — 화면에 있는데 없는 것처럼 보인다."""
        fn = self._fn("ccPeekBody")
        self.assertNotIn("<details", fn, "미리보기가 본문을 접는다")
        self.assertIn("data-pmore", fn, "잘린 나머지를 펼 손잡이가 없다")
        self.assertIn("CCPEEK_LINES", fn, "자를 줄 수가 정해져 있지 않다")

    def test_the_preview_says_when_it_cannot_show(self):
        """빈·없음·실패를 다 말한다 — 조용히 아무것도 안 뜨면 고장으로 읽힌다."""
        fn = self._fn("ccPeek") + self._fn("ccPeekBody")
        for phrase in ("찾지 못했습니다", "불러오는 중", "불러오지 못했습니다",
                       "서버에 닿지 못했습니다", "본문이 비어 있습니다"):
            self.assertIn(phrase, fn, "상태 하나가 말이 없다: %s" % phrase)

    def test_the_card_has_no_colour_field_and_no_side_bar(self):
        """색면 하이라이트·세로 띠 금지 — 이 제품이 확정한 금지다."""
        m = re.search(r"\.ccterm \.ccpeek\{([^}]*)\}", self.src)
        self.assertIsNotNone(m, "미리보기 카드 규칙을 찾지 못했다")
        decl = m.group(1)
        self.assertNotIn("background", decl, "카드가 색면을 깐다")
        self.assertNotIn("border-left", decl, "카드에 세로 띠가 섰다")
        self.assertIn("border-top", decl, "카드가 어디서 시작하는지 말하지 않는다")

    def test_escape_closes_it_like_everything_else(self):
        """닫는 법이 둘이면 안 된다 — 얹기 카드와 같은 키로 닫힌다."""
        i = self.code.find('if (e.key !== "Escape") return;')
        self.assertGreater(i, 0, "Escape 처리를 찾지 못했다")
        self.assertIn("ccPeekClose()", self.code[i:i + 300],
                      "Esc 로 미리보기가 닫히지 않는다")

    # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
