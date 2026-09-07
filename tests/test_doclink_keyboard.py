"""문서로 가는 길이 마우스에만 열려 있다 (REQ-20260827-013-62x6).

보드 카드는 REQ-20260827-007 에서 Enter/Space 로 열리게 했다. 남은 두 자리가
이 문서의 몫이다.

  ① 문서 링크(a.doclink)는 href 없는 <a> 였다. href 없는 앵커는 링크가 아니라
     밑줄 친 글자다 — Tab 이 닿지 않고, 가운데클릭도 ctrl+클릭도 없다. 문서
     본문·검색 결과·audit 표·backlink·선행 대기 레일… 그리는 자리가 아홉이다.
  ② 목록 행(.doclist .row, .row[data-stream], .backlinks .bl)은 <div> 라
     같은 문제인데, 여기엔 함정이 하나 더 있다. 행을 전부 Tab 길에 올리면
     300건짜리 목록은 "닿는다"가 아니라 "빠져나올 수 없다"가 된다. 목록에
     Tab 으로 한 번 들어가고 안에서는 방향키로 옮기는 roving tabindex 가
     그래서 표준 해법이다.

이 테스트가 지키는 계약은 여섯이다.

  A. 문서 링크는 **한 헬퍼**에서만 만들어진다 — href 와 data-doc 이 같은 값이다.
     (갈라지면 새 탭만 다른 문서를 연다.)
  B. 목록 하나 = Tab 한 번. 렌더된 행은 전부 tabindex="-1" 이고, 딱 하나만
     0 으로 올라간다.
  C. 방향키는 옮기기만 한다. 여는 것은 Enter/Space — 방향키가 열면 목록을
     훑는 동안 문서를 300장 부른다.
  D. 수식키 클릭은 브라우저 몫으로 남긴다(새 탭). 맨클릭만 가로채 히스토리가
     두 번 쌓이지 않게 한다.
  E. href 안에 문서 id 가 들어가면서 생기는 재귀 링크화를 자리표시자로 막는다
     — 첨부 img 에서 한 번 겪은 그 결함이다.
  F. 포커스 표시는 기존 어휘 그대로: 실선 잉크 = 지금 여기. 새 색·색면 없음.

실행: python3 tests/ doclink_keyboard
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node",
                "/mnt/c/Temp/s9-webkit/node-*/node.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = find_node()


class DoclinkKeyboard(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()

    # ---------- A. 링크는 한 곳에서만 만들어진다 ----------

    def test_doclink_is_built_by_a_single_helper(self):
        m = re.search(r"const dlink = \([^)]*\) =>([^\n]*\n?[^\n]*)", self.src)
        self.assertIsNotNone(
            m, "a.doclink 를 만드는 헬퍼(dlink)가 없다 — 아홉 자리에 손으로 "
               "href 를 적으면 언젠가 한 자리가 빠진다")
        body = m.group(1)
        self.assertIn('class="doclink"', body)
        self.assertIn("href=", body, "href 없는 앵커에는 Tab 이 닿지 않는다")
        self.assertIn('#docs/', body, "해시 라우트와 같은 주소여야 한다")
        self.assertIn("data-doc=", body,
                      "클릭 위임이 읽는 자리는 그대로 남아야 한다")

    def test_href_and_data_doc_carry_the_same_id(self):
        """새 탭으로 여는 문서와 이 탭에서 여는 문서가 갈라지면 안 된다."""
        m = re.search(r"const dlink = \(([^)]*)\) =>(.*?)`;", self.src, re.S)
        self.assertIsNotNone(m, "dlink 헬퍼 본문을 찾지 못했다")
        arg = m.group(1).split(",")[0].strip()
        body = m.group(2)
        href = re.search(r'href="[^"]*\$\{([^}]*)\}"', body)
        ddoc = re.search(r'data-doc="\$\{([^}]*)\}"', body)
        self.assertIsNotNone(href, "href 값이 상수로 박혀 있다")
        self.assertIsNotNone(ddoc, "data-doc 값을 찾지 못했다")
        self.assertIn(arg, href.group(1), f"href 가 {arg} 에서 오지 않는다")
        self.assertIn(arg, ddoc.group(1), f"data-doc 이 {arg} 에서 오지 않는다")

    def test_every_render_site_goes_through_the_helper(self):
        """손으로 적은 <a class="doclink"> 가 한 자리도 남지 않아야 한다."""
        hand = [ln for ln in self.src.split("\n")
                if '<a class="doclink"' in ln and "href=" not in ln]
        self.assertEqual(
            [], hand,
            "헬퍼를 거치지 않고 직접 그린 문서 링크가 남아 있다 — "
            "이 자리들만 href 가 없어 키보드로 닿지 않는다:\n" + "\n".join(hand))

    def test_helper_is_actually_used_at_the_nine_render_sites(self):
        uses = re.findall(r"\bdlink\(", self.src)
        self.assertGreaterEqual(
            len(uses), 9,
            f"문서 링크를 그리는 자리는 아홉인데 헬퍼 호출이 {len(uses)}곳뿐이다")

    # ---------- B. 목록 하나 = Tab 한 번 ----------

    def rows(self, cls):
        """여는 태그 하나를 통째로 — 줄바꿈은 계약이 아니다."""
        return re.findall(r"<div class=\"" + cls + r"[^>]*>", self.src, re.S)

    def test_list_rows_are_controls_with_the_same_vocabulary_as_cards(self):
        for cls, tag in (("row", "문서/스트림 목록 행"), ("bl\"", "backlink 행")):
            rows = [r for r in self.rows(cls)
                    if "data-doc=" in r or "data-stream=" in r]
            self.assertTrue(rows, f"{tag} 을(를) 그리는 자리를 찾지 못했다")
            for r in rows:
                self.assertIn('role="button"', r,
                              f"{tag} 이 컨트롤임을 밝히지 않는다: {r[:90]}")
                self.assertIn("data-rove-item", r,
                              f"{tag} 이 방향키 이동 대상으로 표시되지 않았다")

    def test_rows_are_rendered_out_of_the_tab_order(self):
        """300건이면 Tab 300번이다 — 렌더 시점에는 전부 -1 이어야 한다."""
        rows = [r for r in re.findall(r"<div [^>]*data-rove-item[^>]*>", self.src, re.S)]
        self.assertTrue(rows, "행에 tabindex 를 적은 자리가 없다")
        for r in rows:
            self.assertIn('tabindex="-1"', r,
                          "렌더된 행이 tabindex 0 으로 나가면 목록 전체가 "
                          f"Tab 길에 올라간다: {r[:90]}")

    def test_exactly_one_row_is_lifted_into_the_tab_order(self):
        """계약은 **결과**다 — 딱 하나만 0, 나머지는 -1.

        전에는 이 자리가 `tabIndex = … ? 0 : -1` 이라는 **구현의 글자**를 정규식으로
        못 박았다. REQ-20260907-029 가 같은 뜻을 쓰기 가드가 붙은 두 줄로 고치자
        (`const want = …; if (r.tabIndex !== want) r.tabIndex = want;`) 뜻은 그대로인데
        시험이 깨졌다 — 같은 계열을 그날 이미 두 번 고쳤다(REQ-20260907-046).
        글자를 못 박으면 뜻이 같은 개정마다 깨지고, 고치는 사람은 계약을 읽지 않고
        글자만 맞추게 된다. 그래서 조각을 떼어 node 로 **실행해** 결과를 잰다."""
        m = re.search(r"function roveSync\(\)\{(.*?)\n\}", self.src, re.S)
        self.assertIsNotNone(m, "roving tabindex 를 세우는 roveSync 가 없다")
        rove = "function roveSync(){" + m.group(1) + "\n}"
        if not NODE:
            self.skipTest("node 없음 — 실행 검증 생략")

        def run(n, sel):
            """줄 n 개 중 sel 번째가 열려 있는 목록 하나. 결과 tabIndex 를 돌려준다."""
            script = "\n".join([
                'const ROVE_ITEM = "[data-rove-item]";',
                "const mk = i => ({tabIndex: -1,",
                "  classList: {contains: c => c === 'sel' && i === %d}});" % sel,
                "const rows = Array.from({length: %d}, (_, i) => mk(i));" % n,
                "const cont = {querySelectorAll: () => rows};",
                "global.document = {querySelectorAll: () => [cont]};",
                rove,
                "roveSync();",
                "console.log(JSON.stringify(rows.map(r => r.tabIndex)));",
            ])
            p = subprocess.run([NODE, "-e", script], capture_output=True,
                               text=True, timeout=30)
            self.assertEqual(p.returncode, 0, f"node 실행 실패:\n{p.stderr[-2000:]}")
            return json.loads(p.stdout.strip().splitlines()[-1])

        got = run(5, -1)
        self.assertEqual(got.count(0), 1,
                         f"Tab 의 입구가 하나가 아니다: {got}")
        self.assertEqual(got, [0, -1, -1, -1, -1],
                         "짚어 둔 자리도 열린 줄도 없으면 첫 줄이 입구다")

        got = run(5, 3)
        self.assertEqual(got, [-1, -1, -1, 0, -1],
                         "열려 있는 행이 있으면 그 자리가 Tab 의 입구여야 한다")

        # 빈 목록에서 터지면 안 된다 — 줄이 0개여도 실행이 끝나야 한다.
        self.assertEqual(run(0, -1), [])

    def test_rove_containers_are_marked(self):
        self.assertIn("data-rove\"", self.src.replace("data-rove-item", "") + '"',
                      "목록 컨테이너에 data-rove 표시가 없다")
        cnt = len(re.findall(r"data-rove(?![-\w])", self.src))
        self.assertGreaterEqual(cnt, 3,
                                "문서 목록·스트림 목록·backlink 세 자리가 모두 "
                                f"방향키 컨테이너여야 한다 (찾은 곳 {cnt})")

    # ---------- C. 방향키는 옮기고, Enter 가 연다 ----------

    def keydown_blocks(self, n=1200):
        return [self.src[m.start():m.start() + n]
                for m in re.finditer(r'addEventListener\("keydown", (?:e|ev) => \{', self.src)]

    def test_arrow_keys_move_focus_within_the_list(self):
        hit = [b for b in self.keydown_blocks() if "ArrowDown" in b]
        self.assertTrue(hit, "방향키로 행을 옮기는 자리가 없다")
        b = hit[0]
        for k in ("ArrowDown", "ArrowUp", "Home", "End"):
            self.assertIn(k, b, f"{k} 이동이 없다")
        self.assertIn("preventDefault", b,
                      "방향키를 막지 않으면 목록과 페이지가 같이 스크롤된다")
        self.assertRegex(b, r"ROVE_ITEM|data-rove-item",
                         "목록 안에 있을 때만 방향키를 가로채야 한다")
        self.assertRegex(self.src, r'ROVE_ITEM = "\[data-rove-item\]"',
                         "ROVE_ITEM 이 가리키는 것이 행 표시여야 한다")

    def test_arrow_keys_do_not_open_the_document(self):
        m = re.search(r"function roveMove\((.*?)\n\}", self.src, re.S)
        self.assertIsNotNone(m, "행 사이 이동(roveMove)을 찾지 못했다")
        b = m.group(1)
        self.assertNotIn(".click()", b,
                         "방향키가 문서를 열면 목록을 훑는 동안 문서를 "
                         "300장 부른다 — 여는 것은 Enter/Space 뿐이다")
        self.assertNotIn("loadDoc", b, "방향키는 옮기기만 한다")
        self.assertIn(".focus()", b, "방향키는 포커스를 옮겨야 한다")

    def test_arrow_movement_does_not_wrap_around(self):
        m = re.search(r"function roveMove\((.*?)\n\}", self.src, re.S)
        b = m.group(1)
        self.assertRegex(
            b, r"Math\.min\(.*Math\.max\(|Math\.max\(0",
            "목록의 처음과 끝이 어디인지 손끝으로 알 수 있어야 한다 — "
            "끝에서 감싸면 영원히 도는 목록이 된다")
        self.assertNotRegex(b, r"%\s*rows\.length",
                            "나머지 연산으로 감싸는 구현은 끝을 지운다")

    def test_enter_space_path_from_the_board_card_still_stands(self):
        """REQ-20260827-007 이 낸 길을 그대로 쓴다 — 두 갈래로 갈라 두면
        한쪽만 고쳐지는 날이 온다."""
        hit = [b for b in self.keydown_blocks(900)
               if 'role="button"' in b and '"Enter"' in b]
        self.assertTrue(hit, "role=button 컨트롤을 Enter/Space 로 누르는 자리가 사라졌다")
        self.assertRegex(hit[0], r"\.click\(\)", "결과는 클릭과 같은 경로로 흘러야 한다")

    # ---------- D. 수식키 클릭은 브라우저 몫 ----------

    def test_modifier_click_is_left_to_the_browser(self):
        m = re.search(r'const doc = evEl\(e\.target\)\?\.closest\("\[data-doc\]"\);(.{0,700})',
                      self.src, re.S)
        self.assertIsNotNone(m, "문서 열기 클릭 위임을 찾지 못했다")
        b = m.group(1)
        for k in ("metaKey", "ctrlKey", "shiftKey", "altKey"):
            self.assertIn(k, b,
                          f"{k} 클릭을 가로채면 새 탭/새 창이 죽는다 — "
                          "href 를 준 이유의 절반이 사라진다")
        self.assertIn("preventDefault", b,
                      "맨클릭까지 브라우저에 맡기면 해시 이동 + pushRoute 로 "
                      "히스토리가 두 번 쌓인다")

    def test_only_anchors_get_preventdefault(self):
        """카드·행(div)에는 기본 동작이 없다 — 앵커일 때만 막는다."""
        m = re.search(r'const doc = evEl\(e\.target\)\?\.closest\("\[data-doc\]"\);(.{0,700})',
                      self.src, re.S)
        self.assertRegex(m.group(1), r'tagName === "A"|matches\("a',
                         "앵커인지 가려서 막아야 한다")

    # ---------- E. href 속 문서 id 의 재귀 링크화 ----------

    def test_wiki_link_html_is_held_before_linkify_runs_again(self):
        m = re.search(r"\.replace\(DOC_ID_WIKI_RE,\s*\n?\s*\(mm, id\) =>([^\n]*)",
                      self.src)
        self.assertIsNotNone(m, "위키링크([[ID]]) 치환 자리를 찾지 못했다")
        self.assertIn(
            "hold(", m.group(1),
            "href=\"#docs/REQ-…\" 의 앞자는 '/' 다. DOC_ID_INLINE_RE 가 막아 주는 "
            "앞자는 따옴표뿐이라 linkifyIds 가 href 안의 id 를 또 링크로 바꿔 "
            "앵커를 중첩시킨다 — 첨부 img 에서 겪은 그 결함이다. 자리표시자로 "
            "빼 둬야 한다")

    def test_inline_regex_still_guards_attribute_values(self):
        self.assertIn('(^|[^"\\\\w-])', self.src,
                      "속성값 안의 문서 id 를 링크로 바꾸지 않는 방어가 사라졌다")

    # ---------- F. 포커스는 기존 어휘로 ----------

    def test_row_focus_ring_is_the_solid_ink_line(self):
        m = re.search(r"\.doclist \.row:focus-visible[^{]*\{([^}]*)\}", self.src)
        self.assertIsNotNone(m, "목록 행의 포커스 링 규칙이 없다")
        b = m.group(1)
        self.assertIn("solid", b, "실선 = 지금 여기 (점선은 짚기)")
        self.assertIn("var(--text)", b,
                      "포커스 링은 잉크색 — 새 액센트 색을 들이지 않는다")
        self.assertNotIn("background", b, "색면 하이라이트 금지")

    def test_open_row_is_not_marked_by_colour_alone(self):
        rows = [r for r in re.findall(r"<div [^>]*data-rove-item[^>]*>", self.src, re.S)
                if "data-doc=" in r or "data-stream=" in r]
        self.assertTrue(any("aria-current" in r for r in rows),
                        "열려 있는 행이 배경 틴트로만 표시되면 눈으로만 읽힌다")

    # ---------- 미리보기도 두 손 중 어느 쪽으로든 ----------

    def test_hovercard_opens_on_keyboard_focus_too(self):
        self.assertRegex(self.src, r"function showHover\(",
                         "미리보기를 여는 한 경로가 없다 — mouseover 에만 매달려 있다")
        hits = [self.src[m.start():m.start() + 400]
                for m in re.finditer(r'addEventListener\("focusin", e => \{', self.src)]
        self.assertTrue(hits, "focusin 으로 반응하는 자리가 없다")
        self.assertTrue(any("showHover(" in h for h in hits),
                        "키보드로 링크에 닿아도 마우스와 같은 것이 보여야 한다")
        self.assertRegex(self.src, r'addEventListener\("focusout"',
                         "떠날 때 닫히지 않으면 카드가 화면에 남는다")

    def test_hovercard_closes_on_escape(self):
        esc_blocks = re.findall(r'"Escape".{0,200}', self.src, re.S)
        self.assertTrue(any("hideHover" in b or "hovercard" in b for b in esc_blocks),
                        "Escape 로 미리보기를 물릴 수 없다 — 키보드에는 "
                        "'마우스를 치우기'가 없다")

    def test_hovercard_is_not_announced_twice(self):
        self.assertRegex(
            self.src, r'hovercard\.setAttribute\("aria-hidden"|aria-hidden="true"[^>]*hovercard',
            "미리보기는 링크가 이미 말한 것을 그림으로 되풀이하는 자리다 — "
            "읽어 주는 도구에는 숨긴다")

    # ---------- 폴링 재렌더가 손끝을 빼앗지 않는다 ----------

    def test_background_rerender_keeps_the_focused_row(self):
        m = re.search(r"if \(wrap && \$\(\"#viewer\"\)\)(.{0,600})", self.src, re.S)
        self.assertIsNotNone(m, "목록만 갈아끼우는 자리를 찾지 못했다")
        b = m.group(1)
        self.assertIn("activeElement", b,
                      "15초 폴링이 목록을 갈아끼울 때 키보드로 짚어 둔 자리를 "
                      "빼앗으면, 방향키로 훑는 일이 15초마다 처음으로 돌아간다")
        self.assertIn("focus(", b, "같은 행을 다시 짚어 줘야 한다")


if __name__ == "__main__":
    unittest.main()
