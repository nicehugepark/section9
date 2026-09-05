"""터미널에 나온 코드 파일 경로를 눌러 그 줄을 본다 — 화면 몫 (REQ-20260828-028-62x6).

서버는 끝났다(`/api/code`, 판정은 `code_visible` 하나). 화면이 지킬 것은 다르다.
이 저장소의 대답에는 `web/index.html:4016` 같은 경로가 늘 섞여 있는데, 그 글자를
쓴 것은 **에이전트**다 — 남이 쓴 글을 화면이 마크업으로 그리면 그 순간 경로가
코드가 된다. 그리고 서버가 일부러 지운 차이(막힘·부재·이진이 같은 404)를 화면이
문구로 되살리면, 지운 이유가 무의미해진다.

이 테스트가 지키는 계약은 아홉이다.

  A. 허용 뿌리 목록은 **한 벌처럼 산다.** 화면에도 사본이 있지만 그것은 게이트가
     아니라 "죽은 링크를 안 그리기 위한 그리기 규칙"이다. 두 벌이 갈라지면
     화면은 열리지도 않는 밑줄을 세우거나 열리는 파일을 감춘다 — 여기서 맞대 본다.
  B. 서버가 준 글자(`lines`·`path`)는 **textContent 로만** 들어간다. innerHTML 이
     이 경로에 한 번이라도 있으면 계약이 깨진 것이다.
  C. 못 연 이유는 **한 문구**다. 화면이 "비밀 폴더라 못 엽니다" 같은 말을 지어내면
     서버가 지운 차이를 화면이 되살린다.
  D. 열리지 않는 경로에는 손잡이를 세우지 않는다. 모양으로 미리 아는 것은 미리
     거르고, 눌러 봐야 아는 것은 **한 번만** 눌리게 하고 그 뒤로 밑줄을 거둔다.
  E. 코드 블록 안 경로에는 손잡이를 걸지 않는다 — 블록은 읽을 것이 아니라 붙일
     것이고, 앵커가 섞이면 드래그 선택이 링크 드래그가 된다 (REQ-20260828-023).
  F. 새 컴포넌트를 만들지 않는다. 문서 미리보기(`.ccpeek`)의 카드·자리·슬롯을
     그대로 나눠 쓴다 — 한 줄에 손잡이가 여럿 서는 자리다.
  G. 파일 전체를 여는 길은 만들지 않는다 (판정 §6).
  H. 키보드로 닿는다. href 없는 손잡이라 `role="button"` + tabindex 로 이 화면에
     이미 있는 Enter/Space 핸들러에 얹힌다.
  I. 문구는 사용자 언어다 — 404·API·게이트 같은 말이 화면에 나오지 않는다.

실행: python3 tests/ code_peek_ui
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def js_func(src, name):
    """함수/화살표 하나의 소스를 통째로 꺼낸다 (중괄호 균형)."""
    for pat in ("async function " + name, "function " + name,
                "const " + name + " ="):
        i = src.find(pat)
        if i >= 0:
            break
    else:
        return ""
    j = src.find("{", i)
    if j < 0:
        return ""
    depth, k = 0, j
    while k < len(src):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1
    return ""


def js_list(src, name):
    """`const NAME = [...]` 의 문자열 원소들."""
    m = re.search(r"const " + name + r"\s*=\s*\[(.*?)\];", src, re.S)
    if not m:
        return None
    return re.findall(r'"([^"]*)"', m.group(1))


def py_tuple(src, name):
    """`NAME = (...)` 의 문자열 원소들."""
    m = re.search(r"^" + name + r"\s*=\s*\((.*?)\)\s*$", src, re.S | re.M)
    if not m:
        return None
    return re.findall(r'"([^"]*)"', m.group(1))


class CodePeekUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        with open(S9_SRC, encoding="utf-8") as f:
            cls.s9 = f.read()

    # ---------- A. 두 벌이 갈라지지 않는다 ----------

    def test_a1_the_allowlist_mirror_equals_the_server(self):
        """화면의 사본과 서버의 원본이 글자까지 같다.

        갈라지는 두 방향이 다 나쁘다. 화면이 넓으면 **열리지도 않는 밑줄**이
        서고(REQ-20260828-021 이 없앤 그 죽은 링크), 화면이 좁으면 열리는 파일이
        맨 글자로 남아 아무도 그런 기능이 있는 줄 모른다. 서버가 뿌리를 하나
        늘리는 날 이 시험이 먼저 빨개져서 화면도 같이 결정하게 만든다.
        """
        for js, py in (("CODE_ROOTS", "CODE_ROOTS"),
                       ("CODE_FILES", "CODE_FILES"),
                       ("CODE_EXT", "CODE_EXT")):
            a, b = js_list(self.src, js), py_tuple(self.s9, py)
            self.assertIsNotNone(a, f"화면에 {js} 사본이 없다")
            self.assertIsNotNone(b, f"bin/s9 에 {py} 가 없다")
            self.assertEqual(a, b,
                             f"{js}: 화면과 서버가 갈라졌다 — 화면 {a} / 서버 {b}")

    def test_a2_the_regex_is_built_from_the_mirror(self):
        """경로를 집는 정규식은 목록에서 **만들어진다** — 손으로 적지 않는다.

        손으로 `(bin|docs|…)` 를 적어 두면 위 시험이 초록인 채로 정규식만
        낡는다. 목록에서 join 하면 한 곳만 고치면 된다.
        """
        m = re.search(r"const CODE_REL_RE = new RegExp\((.*?)\);", self.src, re.S)
        self.assertIsNotNone(m, "CODE_REL_RE 가 목록에서 만들어지지 않는다")
        body = m.group(1)
        self.assertIn("CODE_ROOTS.join", body)
        self.assertIn("CODE_FILES.map", body)

    def test_a3_the_screen_reads_the_fields_the_server_sends(self):
        """카드가 읽는 이름이 서버가 보내는 이름과 같다."""
        route = self.s9[self.s9.find("/api/code"):]
        route = route[:route.find("/api/doc")]
        for k in ("path", "line", "from", "to", "total", "lines"):
            self.assertIn(f'"{k}"', route, f"서버가 {k} 를 보내지 않는다")
        draw = js_func(self.src, "ccCodeDraw")
        for k in ("d.path", "d.line", "d.from", "d.to", "d.total", "d.lines"):
            self.assertIn(k, draw, f"카드가 {k} 를 읽지 않는다")

    # ---------- B. 남이 쓴 글자는 textContent 로만 ----------

    def test_b1_code_lines_never_become_markup(self):
        """`lines` 의 출처는 저장소 파일이고, 경로의 출처는 **에이전트가 쓴 글**이다.

        어떤 링크를 그릴지로는 막을 수 없다 — 서버에서만 막힌다. 화면이 할 수
        있는 유일한 방어가 이것이다.
        """
        draw = js_func(self.src, "ccCodeDraw")
        self.assertTrue(draw, "ccCodeDraw 가 없다")
        self.assertNotIn("innerHTML", draw,
                         "코드 줄을 그리는 자리에 innerHTML 이 있다")
        self.assertRegex(draw, r"ct\.textContent\s*=\s*t\b",
                         "코드 줄이 textContent 로 들어가지 않는다")

    def test_b2_the_path_never_becomes_markup(self):
        """카드 머리의 경로도 같은 글자다 — 되비추면 그 글자가 화면에 들어간다."""
        for name in ("ccCodePeek", "ccCodeFail", "ccCodeLoad", "ccCodeBury"):
            body = js_func(self.src, name)
            self.assertTrue(body, f"{name} 이 없다")
            self.assertNotIn("innerHTML", body, f"{name} 에 innerHTML 이 있다")

    def test_b3_the_card_builder_only_sets_text(self):
        """카드의 칸을 만드는 헬퍼 자체가 textContent 밖으로 못 나간다."""
        el = js_func(self.src, "ccEl")
        self.assertTrue(el, "ccEl 헬퍼가 없다")
        self.assertIn("textContent", el)
        self.assertNotIn("innerHTML", el)

    # ---------- C. 못 연 이유는 한 문구 ----------

    def test_c1_one_sentence_for_every_failure(self):
        """서버가 막힘·부재·이진을 **바이트까지 같은 404** 로 만들었다.

        화면이 그중 하나를 골라 말하면 서버가 지운 차이를 화면이 되살린다 —
        "비밀 폴더라 못 엽니다" 는 곧 목록이다. 문구는 상수 하나여야 한다.
        """
        self.assertEqual(len(re.findall(r"const CODE_FAIL\s*=", self.src)), 1,
                         "못 연 이유 문구가 상수 하나가 아니다")
        fail = js_func(self.src, "ccCodeFail")
        self.assertIn("CODE_FAIL", fail)
        # 상태 코드·응답 본문을 보고 문구를 가르는 분기가 없다
        self.assertNotIn("status", fail)
        self.assertNotIn("if (", fail.replace("if (!", ""))

    def test_c2_the_card_does_not_guess_why(self):
        """이유를 가르는 말이 카드 어디에도 없다."""
        fail = js_func(self.src, "ccCodeFail")
        load = js_func(self.src, "ccCodeLoad")
        m = re.search(r'const CODE_FAIL\s*=\s*"([^"]*)"', self.src)
        self.assertIsNotNone(m)
        blob = fail + load + m.group(1)
        for word in ("권한", "비밀", "이진", "차단", "막혀", "금지", "허용되지"):
            self.assertNotIn(word, blob,
                             f"'{word}' — 화면이 못 연 이유를 짐작해 말하고 있다")

    def test_c3_a_dead_server_is_not_a_dead_path(self):
        """서버에 못 닿은 것은 그 경로가 못 열린다는 뜻이 아니다.

        여기서 묻어 버리면 서버가 잠깐 죽은 사이에 본 줄들이 영영 링크를 잃는다.
        """
        load = js_func(self.src, "ccCodeLoad")
        catch = load[load.find("catch"):]
        self.assertNotIn("ccCodeBury", catch,
                         "서버에 못 닿았을 뿐인데 경로를 묻고 있다")
        self.assertIn("ccCodeFail", load, "404 는 실패 카드로 가야 한다")

    def _states(self):
        return {n: js_func(self.src, n)
                for n in ("ccCodePeek", "ccCodeLoad", "ccCodeDraw", "ccCodeFail")}

    def test_c4_every_state_has_a_way_out(self):
        """카드의 **모든 상태**에 닫기가 있다 — 여는 순간부터.

        불러오는 중이나 못 받았을 때 닫기가 없으면, 잘못 누른 카드를 없애려고
        같은 손잡이를 다시 찾아 눌러야 한다. 그건 되돌리기가 아니라 수수께끼다.
        """
        for name, body in self._states().items():
            if name == "ccCodeLoad":
                continue                       # 상태를 새로 세우지 않는 자리
            self.assertIn("data-pclose", body, f"{name} 상태에 닫기가 없다")

    def test_c5_a_failed_fetch_offers_to_try_again(self):
        """못 받았으면 다시 받을 손잡이를 준다 — 이 화면이 이미 쓰는 어휘
        (`data-retrans`·`data-resupply`)와 같은 자리."""
        load = js_func(self.src, "ccCodeLoad")
        catch = load[load.find("catch"):]
        self.assertIn("data-cretry", catch, "못 받은 자리에 다시 받을 길이 없다")
        self.assertIn("data-cretry", js_func(self.src, "onDocClick") or self.src,
                      "다시 받기 버튼이 아무 데도 연결돼 있지 않다")

    # ---------- D. 열리지 않는 것에는 손잡이를 안 세운다 ----------

    def test_d1_a_handle_only_stands_where_it_can_open(self):
        """모양이 안 맞거나 이미 실패한 경로는 밑줄 없는 맨 값으로 남는다."""
        span = js_func(self.src, "ccPathSpan")
        self.assertTrue(span, "ccPathSpan 이 없다")
        self.assertRegex(
            span, r"if \(!rel \|\| ccCodeDead\.has\(rel\)\)\s*\n?\s*return "
                  r"`<span class=\"ccval\">",
            "열 수 없는 경로가 앵커로 서지 않는지 확인할 수 없다")
        self.assertIn('class="ccval ccpath"', span)

    def test_d2_the_shape_check_mirrors_the_server(self):
        """서버 `_code_shape_ok` 의 다섯 갈래를 화면 사본도 그대로 갖는다."""
        js = js_func(self.src, "codeShapeOk")
        self.assertTrue(js, "codeShapeOk 사본이 없다")
        self.assertIn('x === ".."', js, "상대참조를 안 거른다")
        self.assertIn('startsWith(".")', js, "점파일(.git/.claude)을 안 거른다")
        self.assertIn("CODE_ROOTS.includes", js, "허용 뿌리를 안 본다")
        self.assertIn("CODE_EXT.some", js, "확장자 허용목록을 안 본다")
        self.assertIn('segs[0] === "bin"', js,
                      "확장자 없는 파일을 bin/ 바로 밑으로 좁히지 않는다")

    def test_d3_a_failed_path_is_buried_once(self):
        """한 번 눌러 안 열리면 지금 떠 있는 밑줄까지 거둔다.

        같은 자리를 두 번 세 번 눌러 보게 만드는 것이 죽은 링크의 정체다.
        """
        fail = js_func(self.src, "ccCodeFail")
        self.assertIn("ccCodeBury", fail)
        bury = js_func(self.src, "ccCodeBury")
        self.assertIn("ccCodeDead.add", bury)
        self.assertIn("replaceWith", bury, "이미 그려진 밑줄을 안 거둔다")
        self.assertIn("textContent", bury,
                      "글자는 그대로 남아야 한다 — 원문의 사본이다")

    def test_d4_an_absolute_path_is_not_guessed(self):
        """리포 뿌리를 모르면 자르지 않는다.

        짐작으로 잘라 **남의 리포 경로를 이 리포의 파일로 열어 보이는 것**이
        못 여는 것보다 나쁘다.
        """
        rel = js_func(self.src, "codeRel")
        self.assertTrue(rel, "codeRel 이 없다")
        self.assertIn("workspace", rel)
        self.assertIn('return ""', rel)

    # ---------- E. 코드 블록 안에는 걸지 않는다 ----------

    def test_e1_no_handles_inside_a_fenced_block(self):
        """블록은 읽을 것이 아니라 **붙일 것**이다 (REQ-20260828-023).

        앵커가 섞이면 드래그 선택이 링크 드래그가 되어 복사본에 마크업이 섞인다.
        코드 블록은 자리표시자로 먼저 빠지고, 경로 규칙은 그 뒤에 돈다.
        """
        i = self.src.find("const inline = ccPathRules(esc(s)")
        self.assertGreater(i, 0, "경로 규칙이 체인 안에서 함수로 불리지 않는다")
        chain = self.src[i:i + 3000]
        blk = chain.find('class="ccblk"')
        end = chain.find(", keep)")
        self.assertGreater(blk, 0, "코드 블록 치환이 이 체인 안에 없다")
        self.assertGreater(end, blk,
                           "경로 규칙이 코드 블록 치환보다 먼저 돈다")

    # ---------- F. 새 컴포넌트를 만들지 않았다 ----------

    def test_f1_the_code_card_is_the_document_card(self):
        """같은 카드·같은 자리·같은 슬롯. 카드가 둘씩 열리면 무엇을 눌렀는지
        알 수 없다."""
        peek = js_func(self.src, "ccCodePeek")
        self.assertIn('box.className = "ccpeek"', peek, "새 카드를 만들었다")
        self.assertIn("ccPeekClose()", peek, "앞의 카드를 닫지 않는다")
        self.assertIn("ccPeekEl = box", peek, "카드 슬롯을 나눠 쓰지 않는다")
        self.assertIn('insertAdjacentElement("afterend"', peek,
                      "언급된 줄 바로 아래가 아니다")

    def test_f2_the_card_speaks_the_existing_vocabulary(self):
        """칸 이름이 문서 카드의 것과 같다 — 새 이름을 만들면 스킨이 갈라진다."""
        draw = js_func(self.src, "ccCodeDraw") + js_func(self.src, "ccCodeFail")
        for cls in ('"pk"', '"pt"', '"pa"'):
            self.assertIn(cls, draw, f"{cls} 칸을 안 쓴다")
        self.assertIn('"pmore"', draw, "더 보기가 기존 텍스트 버튼이 아니다")

    def test_f3_no_colour_fill_and_no_vertical_band(self):
        """상태는 밝기와 굵기로만 — 색면 하이라이트·세로 띠 금지."""
        m = re.search(r"\.ccpeek \.pcode\{.*?\.ccpeek \.pcode \.cl\.on \.ct\{[^}]*\}",
                      self.src, re.S)
        self.assertIsNotNone(m, "코드 창 CSS 를 찾지 못했다")
        css = m.group(0)
        self.assertNotIn("background", css, "코드 줄에 색면이 있다")
        self.assertNotIn("border-left", css, "코드 줄에 세로 띠가 있다")
        self.assertIn("overflow-x:auto", css, "긴 줄이 카드를 넓힌다")
        self.assertIn("user-select:none", css,
                      "줄 번호가 선택에 낀다 — 긁어 복사한 코드 앞에 번호가 붙는다")

    # ---------- G. 파일 전체를 여는 길은 없다 ----------

    def test_g1_there_is_no_way_to_open_the_whole_file(self):
        """전체 보기를 열면 상한·창 논의가 무의미해지고 다음 요청은 반드시
        "그럼 편집도" 가 된다 (security-engineer 판정 §6)."""
        load = js_func(self.src, "ccCodeLoad")
        # 부르는 자리가 하나다 — 두 곳이 되면 한 곳이 상한을 잊는다
        self.assertEqual(self.src.count("/api/code"), 1,
                         "코드를 부르는 자리가 하나가 아니다")
        self.assertIn("/api/code", load)
        self.assertIn("&line=", load, "줄 없이 파일을 부른다")
        self.assertIn("&ctx=", load, "창 없이 파일을 부른다")
        span = js_func(self.src, "ccPathSpan")
        self.assertNotIn('target="_blank"', span)
        self.assertNotIn("href=", span, "손잡이가 새 탭으로 파일을 연다")

    def test_g2_the_window_grows_once_and_stops(self):
        """앞뒤 더 보기는 서버 상한(ctx≤60)까지 한 걸음이다."""
        self.assertRegex(self.src, r"CODE_CTX_MORE\s*=\s*60",
                         "창 상한이 서버(CODE_MAX_CTX)와 다르다")
        self.assertRegex(self.s9, r"CODE_MAX_CTX\s*=\s*60")

    # ---------- H. 키보드 ----------

    def test_h1_the_handle_is_reachable_by_keyboard(self):
        """href 가 없으므로 Tab 이 저절로 닿지 않는다 — 이 화면에 이미 있는
        Enter/Space 핸들러(`[role="button"]` + tabIndex)에 얹는다."""
        span = js_func(self.src, "ccPathSpan")
        self.assertIn('role="button"', span)
        self.assertIn('tabindex="0"', span)
        self.assertIn('draggable="false"', span,
                      "링크 드래그가 글 선택을 가로챈다 — 터미널은 긁어 복사하는 자리다")
        self.assertIn('t.closest(\'[role="button"]\')', self.src,
                      "Enter/Space 핸들러가 사라졌다")

    def test_h2_the_focus_ring_uses_the_terminal_ink(self):
        """짚은 자리가 보여야 한다.

        전역 초점 링은 --text(판의 잉크)를 쓰는데, 종이 톤에서 그건 검은 선이라
        상시 다크인 터미널 판 위에서 사라진다. 안 보이는 초점 링은 없는 것과 같다.
        """
        m = re.search(r"a\.ccpath:focus-visible[^{]*\{([^}]*)\}", self.src)
        self.assertIsNotNone(m, "손잡이에 초점 링이 없다")
        self.assertIn("--cc-text", m.group(1),
                      "초점 링이 터미널 팔레트를 안 쓴다 — 종이 톤에서 사라진다")

    # ---------- I. 문구 ----------

    def test_i1_plain_language(self):
        """화면에 나오는 말에 내부 용어가 없다."""
        say = [m.group(1) for m in
               re.finditer(r'(?:textContent = |ccEl\("(?:pt|ps|pk)", )"([^"]{4,})"',
                           self.src)]
        m = re.search(r'const CODE_FAIL\s*=\s*"([^"]*)"', self.src)
        say.append(m.group(1))
        for s in say:
            for bad in ("404", "API", "게이트", "라우트", "허용목록", "fetch",
                        "endpoint", "innerHTML"):
                self.assertNotIn(bad, s, f"화면 문구에 내부 용어: {s}")

    def test_i2_the_diagnostic_switch_exists(self):
        """세 상태를 눈으로 세워 볼 손잡이 — 진짜 터미널 출력에 셋이 한 줄로
        나오는 일은 드물다."""
        self.assertIn("codePeekDiag", self.src)
        self.assertIn("?codepeek", self.src)
        diag = js_func(self.src, "codePeekDiag")
        self.assertIn("ccText(CODE_DIAG", diag,
                      "진단이 진짜 렌더러를 안 쓴다 — 화면을 속이는 진단이다")


if __name__ == "__main__":
    unittest.main()
