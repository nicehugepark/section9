"""대답 속 코드 블록을 어떤 모양으로 내는가 (REQ-20260828-023-62x6).

사용자는 처음에 "코드 스니펫을 접어 달라"고 했지만, 세어 보니 최근 대화 40개의
대답 본문 fenced 블록 43개 중 **11줄을 넘는 것이 하나도 없었다.** 그 43개는
소스 코드가 아니라 붙여 실행할 명령·실측 수치·결정 요약이었다 — 접으면 대답이
결론을 잃는다. 사용자도 되돌리며 못박았다: "당장은 안접어도 된다."

남은 진짜 결함은 길이가 아니라 **재질**이었다. 코드 블록이 회색 색면 + 왼쪽
세로 띠로 그려져 있었는데, 이 제품이 쓰지 않기로 한 바로 그 두 가지다. 문장
사이에 회색 덩어리가 끼면 무엇이 강조인지 사라진다.

이 테스트가 지키는 계약은 다섯이다.

  ① 코드 블록에 색면(background)과 세로 띠(border-left)를 쓰지 않는다.
     구분은 표·헤딩이 이미 쓰는 어휘로 — 위아래 헤어라인 + 왼쪽 들여쓰기.
  ② 인라인 코드도 색면이 아니라 글자색으로 말한다.
  ③ 같은 규칙이 터미널(.ccterm)과 문서/스트림(.term) 양쪽에 걸린다.
     같은 ccText 출력을 그리는데 스트림에서만 맨 글자로 흐르면 안 된다.
     .term 에는 --cc-* 토큰이 없으므로 var() 에 fallback 이 반드시 붙는다.
  ④ 블록에는 복사 손잡이가 있다 — 이 블록들의 절반이 붙여 실행할 명령이다.
     평소엔 숨고 포인터·키보드 초점이 올 때만 선다.
  ⑤ 복사본에 손잡이의 글자가 섞이지 않는다. 손잡이는 선택(드래그)에도 끼지
     않는다(user-select:none) — 섞이면 붙여넣은 명령이 깨진다.

픽셀이 아니라 이 계약만 검사한다. 실제 렌더는 사람의 캡처 확인 몫이다.

실행: python3 tests/ code_block_look
"""
import json
import os
import re
import subprocess
import unittest
import websrc                     # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


def css_rules(src, needle):
    """선택자에 needle 이 들어간 CSS 규칙들을 (선택자, 본문) 으로 돌려준다."""
    out = []
    for m in re.finditer(r"([^{}/;]+)\{([^{}]*)\}", src):
        sel, body = m.group(1).strip(), m.group(2)
        if needle in sel:
            out.append((sel, body))
    return out


def js_func(src, name):
    """함수 하나의 소스를 통째로 꺼낸다 (중괄호 균형)."""
    i = src.find("function %s(" % name)
    if i < 0:
        raise AssertionError("%s 함수를 찾지 못했다" % name)
    j = src.index("{", i)
    depth, k = 0, j
    while k < len(src):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1
    raise AssertionError("%s 함수의 끝을 찾지 못했다" % name)


class CodeBlockLook(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()
        self.blk = [r for r in css_rules(self.src, ".ccblk")
                    if ".ccbcp" not in r[0]]
        self.assertTrue(self.blk, ".ccblk 규칙이 없다")

    # ---------- ① 색면·세로 띠 금지 ----------

    def test_block_has_no_fill(self):
        """색면 하이라이트 금지 — 블록 자체에 background 를 칠하지 않는다."""
        for sel, body in self.blk:
            self.assertNotRegex(
                body, r"background",
                "코드 블록에 색면이 남아 있다 (%s)" % sel)

    def test_block_has_no_vertical_bar(self):
        """세로 띠 금지 — 왼쪽 테두리로 구분하지 않는다."""
        for sel, body in self.blk:
            self.assertNotRegex(
                body, r"border-left\s*:\s*(?!0)",
                "코드 블록에 세로 띠가 남아 있다 (%s)" % sel)

    def test_block_separates_with_hairline_and_indent(self):
        """구분은 위아래 헤어라인 + 왼쪽 들여쓰기로 — 표·헤딩과 같은 어휘."""
        body = " ".join(b for _, b in self.blk)
        self.assertRegex(body, r"border-top\s*:\s*1px solid",
                         "위쪽 헤어라인이 없다")
        self.assertRegex(body, r"border-bottom\s*:\s*1px solid",
                         "아래쪽 헤어라인이 없다")
        pad = re.search(r"padding\s*:([^;}]*)", body)
        self.assertTrue(pad, "블록에 padding 이 없다")
        left = pad.group(1).split()
        self.assertTrue(
            any(v.endswith("px") and v[:-2].isdigit() and int(v[:-2]) >= 10
                for v in left),
            "왼쪽 들여쓰기(10px 이상)가 없다: %r" % pad.group(1))

    # ---------- ② 인라인 코드 ----------

    def test_inline_code_has_no_fill(self):
        """인라인 코드도 면이 아니라 글자로 — 회색 조각을 문장에 흩지 않는다."""
        rules = css_rules(self.src, ".cccode")
        self.assertTrue(rules, ".cccode 규칙이 없다")
        for sel, body in rules:
            self.assertNotRegex(body, r"background",
                                "인라인 코드에 색면이 남아 있다 (%s)" % sel)
        self.assertRegex(" ".join(b for _, b in rules), r"color\s*:",
                         "인라인 코드는 글자색으로 말해야 한다")

    # ---------- ③ 터미널과 스트림 양쪽 ----------

    def test_rules_reach_both_terminal_and_stream(self):
        """같은 ccText 출력을 그리는 두 자리에 같은 규칙이 걸린다."""
        for cls in (".ccblk", ".cccode"):
            sels = " ".join(s for s, _ in css_rules(self.src, cls))
            self.assertIn(".ccterm " + cls, sels,
                          "터미널에 %s 규칙이 없다" % cls)
            self.assertIn(".term " + cls, sels,
                          "문서/스트림(.term)에 %s 규칙이 없다" % cls)

    def test_stream_rules_carry_fallbacks(self):
        """.term 에는 --cc-* 가 정의돼 있지 않다 — var() 에 fallback 필수."""
        rules = [r for r in css_rules(self.src, ".ccblk") if ".term" in r[0]]
        rules += [r for r in css_rules(self.src, ".cccode") if ".term" in r[0]]
        self.assertTrue(rules, ".term 용 규칙이 없다")
        for sel, body in rules:
            for v in re.findall(r"var\(([^)]*)\)", body):
                self.assertIn(",", v,
                              "fallback 없는 토큰이 있다: var(%s) — %s" % (v, sel))

    # ---------- ④ 복사 손잡이 ----------

    def test_block_markup_carries_copy_handle(self):
        """블록을 그릴 때 복사 손잡이를 함께 낸다."""
        f = js_func(self.src, "ccText")
        m = re.search(r'class="ccblk"[^`]*', f)
        self.assertTrue(m, "ccblk 마크업을 찾지 못했다")
        mk = m.group(0)
        if "ccbcp" not in mk:
            # 손잡이 마크업을 상수로 뽑아 쓸 수도 있다 — 그 상수가 손잡이여야 한다.
            names = re.findall(r"\$\{(\w+)\}", mk)
            self.assertTrue(
                any(re.search(r"const %s\s*=[^;]*ccbcp" % n, self.src)
                    for n in names),
                "블록 마크업에 복사 손잡이가 없다: %s" % mk)

    def test_copy_handle_is_quiet_until_pointed_at(self):
        """평소엔 숨고, 포인터나 키보드 초점이 올 때만 선다."""
        rules = css_rules(self.src, ".ccbcp")
        self.assertTrue(rules, ".ccbcp 규칙이 없다")
        base = [b for s, b in rules if ":hover" not in s and ":focus" not in s]
        self.assertTrue(any(re.search(r"opacity\s*:\s*0\b", b) for b in base),
                        "손잡이가 평소에 숨지 않는다")
        shown = " ".join(s for s, _ in rules)
        self.assertIn(":hover", shown, "포인터를 올려도 안 뜬다")
        self.assertIn(":focus-visible", shown,
                      "키보드 초점으로 닿을 수 없다 (WCAG 2.1.1)")

    # ---------- ⑤ 복사본이 깨지지 않는다 ----------

    def test_handle_is_not_selectable(self):
        """드래그 선택에 손잡이 글자가 딸려오면 붙여넣은 명령이 깨진다."""
        body = " ".join(b for _, b in css_rules(self.src, ".ccbcp"))
        self.assertRegex(body, r"user-select\s*:\s*none",
                         "손잡이가 선택에 끼어든다")

    def test_copy_strips_the_handle_text(self):
        """복사본에서 손잡이 글자를 빼고 준다."""
        f = js_func(self.src, "ccBlockCopy")
        self.assertRegex(
            f, r"\.ccbcp[^\n]*remove\(\)",
            "복사 전에 손잡이를 걷어내지 않는다 — 첫 줄에 손잡이 글자가 섞인다")
        self.assertIn("textContent", f, "블록의 글자를 읽지 않는다")
        self.assertIn("clipboard", f, "클립보드에 쓰지 않는다")
        self.assertRegex(f, r"복사됨|복사 실패",
                         "눌렀는데 아무 말이 없다 — 성공/실패를 말해야 한다")

    def test_copy_gives_only_what_can_be_pasted(self):
        """복사본에 찌꺼기가 없다 — **실행해서** 잰다 (REQ-20260911-003).

        주인 지적 2026-09-11 08:57: 「편하자고 복사를했는데 찌꺼기가 같이
        복사되면 지워야하니까 더 불편해지잖아」. 블록 **안**의 들여쓰기는
        뜻이므로 남기고, 블록이 통째로 밀려 있는 앞머리와 앞뒤 빈 줄·줄 끝
        공백만 걷는다. 글자 검사가 아니라 함수를 불러 결과를 본다.
        """
        node = websrc.find_node()
        if not node:
            self.skipTest("node 가 없다 — 실행으로 재는 갈래")
        fn = js_func(self.src, "ccCopyText")
        cases = [
            ("    cd ~/section9\n    bin/s9 sync",
             "cd ~/section9\nbin/s9 sync", "공통 앞머리를 안 걷었다"),
            ("  a\n    b\n  c", "a\n  b\nc",
             "상대 들여쓰기까지 걷었다 — 그건 뜻이다"),
            ("\n\n  x  \n\n", "x", "앞뒤 빈 줄이나 줄 끝 공백이 남았다"),
            ("\tif x:\n\t    y", "if x:\n    y",
             "탭 앞머리를 글자로 세지 않았다"),
            ("no indent\nhere", "no indent\nhere", "멀쩡한 것을 건드렸다"),
        ]
        prog = fn + "\nconst C = " + json.dumps([[a, b] for a, b, _ in cases]) \
            + ";\nconsole.log(JSON.stringify(C.map(([s]) => ccCopyText(s))));"
        r = subprocess.run([node, "-e", prog], capture_output=True, text=True,
                           timeout=30)
        self.assertEqual(0, r.returncode, r.stderr[-500:])
        got = json.loads(r.stdout.strip().splitlines()[-1])
        for (src, want, why), g in zip(cases, got):
            self.assertEqual(want, g, f"{why}: {src!r} → {g!r}")

    def test_copy_runs_the_text_through_that_one_place(self):
        """손잡이가 주는 것은 그 함수를 지난 글자다 — 두 벌로 만들지 않는다."""
        f = js_func(self.src, "ccBlockCopy")
        self.assertRegex(f, r"writeText\(ccCopyText\(",
                         "블록의 글자를 다듬지 않고 그대로 클립보드에 넣는다")

    def test_copy_is_delegated_not_per_element(self):
        """스트림은 통째로 다시 그려진다 — 리스너는 위임 하나로 둔다."""
        self.assertNotRegex(
            self.src, r'class="ccbcp"[^>]*onclick',
            "손잡이마다 리스너를 붙이면 재렌더마다 죽는다")
        self.assertRegex(
            self.src, r'closest\("\.ccbcp"\)',
            "위임 핸들러(closest(\".ccbcp\"))가 없다")


if __name__ == "__main__":
    unittest.main()
