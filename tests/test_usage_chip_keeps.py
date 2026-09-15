"""사용량 칩은 못 받았다고 지워지지 않는다 (REQ-20260907-068).

한 번(`tries: 1`) 실패하면 칩을 비우고 마지막 값까지 버렸다 — WSL 중계의 간헐
리셋 한 번에 계정 줄이 아무 말 없이 사라졌다. 이제 마지막 값이 있으면 「지금은
마지막으로 받은 값이다」 마크를 달고 남고, 받은 적이 없으면 「사용량을 받지
못했습니다」가 선다.

그 마크는 **글리프가 아니라 그림이다** (REQ-20260910-026). 여기 있던 `⏳` 는
코드포인트 U+23F3 이라 맥·iPad Safari 가 컬러 이모지 폰트로 그렸다 — 색도 획
두께도 OS 가 정했다. 이제 마크를 `mask` + `currentColor` 로 그리므로 색이
스킨·톤을 따라간다. 아래 두 검사가 그 결정을 계약으로 고정한다: 칩의 렌더
결과에 이모지 후보 코드포인트가 없고, CSS 가 폰트가 아닌 그림으로 그린다.

그 뒤 마크는 **사전 한 곳으로 모였다** (REQ-20260910-027) — 칩이 제 클래스를
갖지 않고 `mk("clock")` 으로 사전의 낱말을 부른다. 그래서 이 시험은 흉내 낸
`mk` 가 아니라 const.js 의 그 함수를 그대로 실어 잰다.

`renderUsageChip` 과 실패 갈래를 node 로 **실행**해 잰다(소스 글자 대조 아님).
실행: python3 tests/ usage_chip_keeps
"""
import os
import re
import subprocess
import unittest

from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다

HERE = os.path.dirname(os.path.abspath(__file__))
# 준비 삼아 한 번만 읽는다 (DOC-20260907-002)
USAGE_SRC = open(os.path.join(HERE, "..", "web", "app", "usage.js"), encoding="utf-8").read()
# 마크를 부르는 `mk()` 는 const.js 가 소유한다 (REQ-20260910-027). 가짜로 흉내
# 내지 않고 **그 함수를 그대로 실어** 잰다 — 시험이 제 손으로 만든 마크를 보고
# 통과하면, 화면이 부르는 마크가 바뀌어도 아무도 못 잡는다.
CONST_SRC = open(os.path.join(HERE, "..", "web", "app", "const.js"), encoding="utf-8").read()
import glob
import shutil


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

# stale 마크 하나를 가리키는 선택자 — 시험이 이 글자를 한 곳에서만 안다.
# 마크가 사전으로 옮겨 가면서(REQ-20260910-027) 칩이 제 클래스를 갖지 않고
# 사전의 낱말(`mk-clock`)을 부른다 — 「얼마나 지났나」와 「언제 잰 값인가」는
# 같은 것을 묻는 말이라 시각 마크 하나로 합쳤다.
STALE = 'class="mk mk-clock"'


def is_emoji_candidate(ch):
    """이모지 폰트 폴백이 컬러 타일로 그릴 수 있는 코드포인트인가.

    구간만 본다 — U+2300~U+27BF(기타 기호·딩뱃) 안의 시계·모래시계류와
    U+1F000 이상 전부, 그리고 이모지 표현 선택자(U+FE0F). 잉크를 OS 가
    정하는 글리프를 화면 어휘로 쓰지 않는다는 규칙이라 넉넉하게 잡는다.
    """
    cp = ord(ch)
    return cp >= 0x1F000 or cp == 0xFE0F or 0x231A <= cp <= 0x23F3 \
        or 0x2600 <= cp <= 0x27BF

STUBS = r"""
// 마크는 사전(marks.css)에서 온다 — 화면은 이름만 부른다 (REQ-20260910-027).
// mk() 는 흉내내지 않는다: 아래에서 실물(CONST_SRC 의 그 함수)을 얹는다.
const esc = s => String(s);
const usageTitle = () => "사용량";
function mkEl(){ const a = {}; return {textContent: "", innerHTML: "",
  setAttribute(k, v){ a[k] = v; }, removeAttribute(k){ delete a[k]; }, attrs: a}; }
"""


def _fn(src, name):
    i = src.index(f"function {name}(")
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{": depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0: return src[i:j + 1]
    raise AssertionError(name)


# 흉내가 아니라 실물 — 화면이 부르는 그 `mk()` 를 실어야 마크가 바뀔 때 잡힌다.
# (STUBS 를 쓰는 자리가 넷이라 여기 한 번만 얹는다.)
STUBS += _fn(CONST_SRC, "mk") + "\n"


def _fail_branch(src):
    """refreshUsage 안의 실패 갈래만 — `if (!d || ...){` 부터 `usageLast = d;` 앞까지."""
    body = _fn(src, "refreshUsage")
    a = body.index("if (!d || (!d.ok && !d.stale)){")
    b = body.index("usageLast = d;")
    return body[a:b]


@unittest.skipUnless(NODE, "node 가 없다")
class Chip(unittest.TestCase):
    def _run(self, driver):
        src = USAGE_SRC
        prog = STUBS + _fn(src, "renderUsageChip") + "\n" + driver
        r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_a_good_value_is_drawn(self):
        out = self._run(r"""
const el = mkEl();
renderUsageChip(el, {email: "a@b", limits: [{kind: "session", percent: 29}, {kind: "weekly_all", percent: 22}]});
console.log(el.innerHTML);""")
        self.assertIn("a@b", out); self.assertIn("5h", out); self.assertIn("29%", out)
        self.assertNotIn(STALE, out)

    def test_a_stale_value_carries_the_mark(self):
        out = self._run(r"""
const el = mkEl();
renderUsageChip(el, {email: "a@b", stale: true, limits: []});
console.log(el.innerHTML);""")
        self.assertIn(STALE, out)
        # 그림이라 스크린리더에 닿지 않는다 — 같은 사실은 usageTitle 이 말한다
        self.assertIn("aria-hidden", out)

    def test_the_chip_carries_no_emoji_codepoint(self):
        """칩이 그리는 글자에 이모지 후보가 없다 (REQ-20260910-026).

        `⏳`(U+23F3)가 여기 있었다 — 맥·iPad Safari 가 노란 타일로 그렸다.
        stale 이든 아니든, 한도가 없어 `—` 가 서는 갈래까지 모두 본다.
        """
        for label, driver in (
            ("성한 값", r"""renderUsageChip(el, {email: "a@b", limits: [
  {kind: "session", percent: 29}, {kind: "weekly_all", percent: 22},
  {kind: "weekly_scoped", percent: 8, scope_name: "Opus"}]});"""),
            ("stale", r"""renderUsageChip(el, {email: "a@b", stale: true, limits: []});"""),
        ):
            out = self._run("const el = mkEl();\n" + driver + "\nconsole.log(el.innerHTML);")
            for ch in out:
                self.assertFalse(
                    is_emoji_candidate(ch),
                    f"{label}: 이모지 후보 U+{ord(ch):04X}({ch})가 사용량 칩에 있다 — "
                    f"맥·iPad 에서 컬러 이모지로 그려진다. 격자에 맞춘 마크로 "
                    f"바꿔라 (REQ-20260910-026)")

    def test_failure_after_a_value_keeps_it_with_the_mark(self):
        """핵심 — 실패해도 마지막 값이 마크를 달고 남는다. 칩이 비지 않는다."""
        src = USAGE_SRC
        driver = STUBS + _fn(src, "renderUsageChip") + r"""
let usageLast = {email: "a@b", limits: [{kind: "session", percent: 29}]};
const el = mkEl(); el.setAttribute("tabindex", "0");
const d = null;                                   // 이번 폴은 못 받았다
(function(){ """ + _fail_branch(src) + r""" })();
console.log(JSON.stringify({html: el.innerHTML, text: el.textContent, last: !!usageLast}));"""
        r = subprocess.run([NODE, "-e", driver], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = __import__("json").loads(r.stdout.strip())
        self.assertIn("a@b", got["html"], "마지막 값이 지워졌다 — 계정 줄이 사라진다")
        self.assertIn(STALE, got["html"], "못 받은 것을 표시하지 않는다")
        self.assertTrue(got["last"], "usageLast 를 버렸다 — 다음 실패에 빈 칸이 된다")

    def test_failure_with_no_value_says_so(self):
        """받은 적이 없으면 빈 칸이 아니라 그 사실을 말한다."""
        src = USAGE_SRC
        driver = STUBS + _fn(src, "renderUsageChip") + r"""
let usageLast = null;
const el = mkEl(); el.setAttribute("tabindex", "0");
const d = null;
(function(){ """ + _fail_branch(src) + r""" })();
console.log(JSON.stringify({text: el.textContent, tab: "tabindex" in el.attrs}));"""
        r = subprocess.run([NODE, "-e", driver], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = __import__("json").loads(r.stdout.strip())
        self.assertIn("받지 못했습니다", got["text"], "빈 칸이다 — 아무 문제 없음으로 읽힌다")
        self.assertFalse(got["tab"], "글자만 있는 칩이 tab 순서에 남았다")


class StaleMarkIsDrawn(unittest.TestCase):
    """마크는 폰트가 아니라 그림이고, 그림은 사전에서 온다 (REQ-20260910-026·027).

    여기 있던 검사는 `.usagechip .stale` 한 규칙을 붙들고 있었다. 마크가 사전
    한 곳(`web/css/marks.css`)으로 모이면서 칩은 제 클래스를 갖지 않고 사전의
    낱말(`mk-clock`)을 부르게 됐는데 — 이 파일 위쪽 `STALE` 이 이미 그 글자를
    안다 — 이 검사만 옛 이름에 남아, 아무 요소도 물지 않는 규칙을 살아 있는
    것처럼 붙들었다(REQ-20260916-014-2n7g). 검사의 자리를 화면이 실제로 그리는
    것으로 옮긴다: `.mk` 가 칠하고 `--mk-clock-src` 가 모양을 준다.
    격자 11칸·획 1px·단축 금지는 사전 전체를 세는 test_marks_dictionary 가
    본다. node 가 없어도 도는 검사다.
    """
    @classmethod
    def setUpClass(cls):
        with open(index_path(), encoding="utf-8") as f:
            cls.html = f.read()

    def test_the_mark_is_painted_by_a_mask(self):
        m = re.search(r"\n\.mk,[^{]*\{([^}]*)\}", self.html)
        self.assertIsNotNone(m, "사전의 `.mk` 규칙이 없다 — 마크를 무엇으로 그리나")
        css = m.group(1)
        self.assertIn("background-color:currentColor", css,
                      "색을 스킨·톤이 아니라 다른 곳이 정한다")
        self.assertIn("mask-image:var(--mk)", css, "그림이 아니다")

    def test_the_stale_mark_has_a_drawing_in_the_dictionary(self):
        """칩이 부르는 낱말에 그림이 실제로 달려 있다 — 빈 이름이 아니다."""
        self.assertRegex(
            self.html, r"--mk-clock-src:url\(\"data:image/svg\+xml,",
            "시각 마크가 사전에 그림으로 없다 — 글리프로 되돌아가면 잉크를 OS 가 정한다")
        self.assertRegex(
            self.html, r"\.mk-clock\{--mk:var\(--mk-clock-src\)\}",
            "칩이 부르는 `mk-clock` 이 사전의 그림을 물지 않는다")


if __name__ == "__main__":
    unittest.main()
