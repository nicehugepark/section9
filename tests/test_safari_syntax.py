"""화면 조각이 사파리에서 문법으로 죽지 않는다 (REQ-20260829-038).

제보는 "md 파일 문서 렌더링이 사파리에서 깨진다"였고 **캡처가 없었다.** 이 자리에는
사파리도 없다. 그래서 짐작으로 CSS 를 고치는 대신, 사파리가 실제로 못 쓰는 문법을
코드에서 **세어** 확정했다. 나온 것은 한 줄이었다:

    web/app/ccrender.js:27   const CCTBL_CELL = /(?<!\\)\|/;

lookbehind 는 JavaScriptCore 가 **사파리 16.4 에서야** 받았다. 그전 사파리는 이것을
런타임 오류가 아니라 **문법 오류**로 다룬다 — 문법 오류는 그 파일을 통째로 죽인다.
오늘 화면을 26조각으로 갈랐으므로(REQ-20260829-027) 죽는 단위가 곧 조각 하나다.

그리고 그 조각이 하필 문서 렌더의 길목이었다:

    web/app/attach.js:195    const tb = mdTable(lines, li, "mdtbl", inline);   ← md2html
    web/app/ccrender.js:52   function mdTable(lines, i, cls, cell){            ← 죽는 자리

`md2html` 은 문서 본문의 **모든 줄**에 대해 `mdTable` 을 부른다. 그러니 ccrender.js
가 안 실행되면 첫 줄에서 ReferenceError 가 나고 문서 본문이 통째로 안 그려진다.
증상이 정확히 "문서만 깨진다"로 보이는 이유다 — 카드도 그래프도 멀쩡하다.

이 시험이 막는 것은 그 한 줄이 아니라 **그 종류**다. 조각으로 가른 뒤로는 신문법
하나가 기능 하나를 통째로 지우므로, 하한을 글자로 세어 못박는다. 이 저장소가
이미 여러 번 쓴 방식이고, `web/app/attach.js` 의 주석("가변 길이 lookbehind 를
쓰지 않으려는 것이다", REQ-20260829-008)이 말하듯 한 번은 사람이 손으로 피했던
함정이다 — 사람의 기억이 아니라 시험이 지켜야 한다.

**하한**: 사파리 15.6 (2022, 인텔 맥의 마지막 사파리 중 하나 — 아직 쓰는 사람이 있다).
예외가 필요하면 그 줄에 `safari-ok:` 와 이유를 적는다. 침묵으로는 못 지나간다.

실행: python3 tests/ safari_syntax
"""
import os
import re
import unittest

import webasset

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
APP = os.path.join(WEB, "app")

# 그 줄만은 봐준다는 표식. 이유를 함께 적어야 한다 — 표식만 달고 지나가면
# 다음 사람은 그것이 검토된 예외인지 급했던 흔적인지 알 수 없다.
ALLOW = re.compile(r"safari-ok:\s*\S")

# (정규식, 이름, 사파리 최소 버전, 깨졌을 때 보이는 것)
#
# **문법(syntax)** 은 파일을 통째로 죽인다 — 그 조각의 함수가 전부 없어진다.
# **런타임(runtime)** 은 그 함수가 불린 순간만 죽인다 — 화면 일부만 빈다.
# 둘은 증상이 다르므로 구분해 적는다. 캡처 없는 제보를 읽을 때 이 구분이
# "어디가 깨졌나"를 좁혀 준다.
BANNED = [
    (r"\(\?<[=!]", "정규식 lookbehind (?<= (?<!", "16.4", "syntax",
     "그 조각 파일 전체가 실행되지 않는다"),
    (r"\(\?<[A-Za-z_$]", "정규식 named group (?<name>)", "11.1", "syntax",
     "그 조각 파일 전체가 실행되지 않는다"),
    (r"\\k<", "정규식 named backref \\k<>", "11.1", "syntax",
     "그 조각 파일 전체가 실행되지 않는다"),
    (r"(?<![\w$])(\?\?=|\|\|=|&&=)", "논리 대입 ??= ||= &&=", "16.0", "syntax",
     "그 조각 파일 전체가 실행되지 않는다"),
    (r"(?<![\w$.])#[A-Za-z_$][\w$]*\s*(?:=|;|\()", "클래스 private 필드 #x", "14.1",
     "syntax", "그 조각 파일 전체가 실행되지 않는다"),
    (r"\.replaceAll\(", "String.replaceAll", "15.4", "runtime",
     "부른 함수만 죽는다"),
    (r"(?<![\w$])\w[\w$.\]\)]*\.at\(", "Array/String .at()", "15.4", "runtime",
     "부른 함수만 죽는다"),
    (r"Object\.hasOwn\b", "Object.hasOwn", "15.4", "runtime",
     "부른 함수만 죽는다"),
    (r"(?<![\w$.])structuredClone\(", "structuredClone", "15.4", "runtime",
     "부른 함수만 죽는다"),
    (r"\.findLast(?:Index)?\(", "findLast / findLastIndex", "15.4", "runtime",
     "부른 함수만 죽는다"),
    (r"\.(?:toSorted|toReversed|toSpliced)\(", "toSorted / toReversed / toSpliced",
     "16.4", "runtime", "부른 함수만 죽는다"),
    (r"(?:Object|Map)\.groupBy\b", "Object.groupBy / Map.groupBy", "17.4",
     "runtime", "부른 함수만 죽는다"),
    (r"(?<![\w$.])Array\.fromAsync\(", "Array.fromAsync", "18.2", "runtime",
     "부른 함수만 죽는다"),
    (r"(?<![\w$.])RegExp\.escape\(", "RegExp.escape", "18.2", "runtime",
     "부른 함수만 죽는다"),
    (r"AbortSignal\.(?:timeout|any)\b", "AbortSignal.timeout / any", "16.0",
     "runtime", "부른 함수만 죽는다"),
    (r"(?<![\w$.])requestIdleCallback\(", "requestIdleCallback", "N/A", "runtime",
     "부른 함수만 죽는다 (사파리는 아직 안 준다)"),
]


def app_files():
    _, app = webasset.parts()
    return app


def read(name):
    with open(os.path.join(APP, name), encoding="utf-8") as f:
        return f.read()


def strip_noise(line):
    """한 줄짜리 주석과 문자열 리터럴을 지운다.

    금지 문법을 **설명하는 글**까지 위반으로 세면, 이 시험은 자기를 설명하는
    주석 하나에 걸려 넘어진다 — 실제로 `attach.js` 에는 "가변 길이 lookbehind 를
    쓰지 않으려는 것이다"라는 주석이 있다. 코드가 아닌 것은 브라우저가 읽지
    않으므로 세지 않는다.
    """
    line = re.sub(r"//.*$", "", line)
    line = re.sub(r"/\*.*?\*/", "", line)
    line = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", line)
    line = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', line)
    return line


def code_of(name):
    """주석을 걷어낸 코드만 — 규칙을 **설명하는 글**은 규칙 위반이 아니다."""
    src = read(name)
    skip = block_comment_lines(src)
    return "\n".join(strip_noise(ln) for i, ln in enumerate(src.splitlines(), 1)
                      if i not in skip)


def block_comment_lines(src):
    """여러 줄 주석이 차지한 줄 번호 집합 (1-base).

    이 저장소의 주석은 길다 — 문단으로 적힌 설명 안에서 `(?<=` 같은 글자가
    나오는 것은 위반이 아니라 기록이다.
    """
    out = set()
    for m in re.finditer(r"/\*.*?\*/", src, re.S):
        a = src.count("\n", 0, m.start()) + 1
        b = src.count("\n", 0, m.end()) + 1
        out.update(range(a, b + 1))
    return out


def sweep():
    """(파일, 줄번호, 줄, 이름, 최소버전, 종류, 증상) 목록 — 예외 표식은 뺀다."""
    hits = []
    for name in app_files():
        src = read(name)
        skip = block_comment_lines(src)
        for i, raw in enumerate(src.splitlines(), 1):
            if i in skip or ALLOW.search(raw):
                continue
            code = strip_noise(raw)
            for pat, label, ver, kind, sym in BANNED:
                if re.search(pat, code):
                    hits.append((name, i, raw.strip(), label, ver, kind, sym))
    return hits


def report(hits):
    return "\n".join(
        f"  web/app/{n}:{i}  [{label} — 사파리 {ver}+ / {kind}: {sym}]\n"
        f"      {line[:100]}"
        for n, i, line, label, ver, kind, sym in hits)


class Syntax(unittest.TestCase):
    """S1·S2 — 사파리 15.6 이 못 읽는 문법이 조각에 없다."""

    def test_syntax(self):
        """S1·S2 — 사파리 15.6 이 못 읽는 문법이 조각에 없다."""
        with self.subTest("s1_no_regex_lookbehind"):
            bad = [h for h in sweep() if "lookbehind" in h[3]]
            self.assertEqual(
                bad, [],
                "정규식 lookbehind 가 화면 조각에 있다 — 사파리 16.4 미만은 이것을 "
                "문법 오류로 다뤄 **그 파일 전체를 실행하지 않는다**. 캡처 그룹으로 "
                "바꾸거나 문자를 직접 훑어라:\n" + report(bad))
        with self.subTest("s2_no_syntax_newer_than_safari_15"):
            bad = sweep()
            self.assertEqual(
                bad, [],
                f"사파리 15.6 이 못 읽는 문법이 {len(bad)}건 있다. syntax 는 조각 "
                "하나를 통째로, runtime 은 그 함수만 죽인다:\n" + report(bad))
        with self.subTest("s3_the_exception_needs_a_reason"):
            marked = 'const X = /(?<=a)b/;   // safari-ok: 이유를 적은 자리'
            bare = 'const X = /(?<=a)b/;'
            self.assertTrue(ALLOW.search(marked), "이유를 적은 예외가 안 통한다")
            self.assertFalse(ALLOW.search(bare), "이유 없는 줄이 예외로 새어 나간다")
            self.assertFalse(ALLOW.search('const X = /(?<=a)b/;  // safari-ok:'),
                             "표식만 달고 이유가 빈 줄이 지나간다")

class DocRenderChain(unittest.TestCase):
    """S4 — 문서 렌더가 왜 그 한 줄에 매여 있었는지를 시험이 기억한다."""

    def test_s4_md2html_depends_on_ccrender(self):
        """`md2html` 은 `mdTable` 없이는 한 줄도 못 그린다.

        이 의존 자체는 옳다 — 표 규칙이 터미널 뷰와 문서 뷰에 두 벌로 갈라지지
        않게 하려고 일부러 한 곳에 뒀다. 시험이 막는 것은 의존이 아니라 **그
        의존을 잊는 것**이다: `mdTable` 이 사는 조각은 문법 하한을 어기면
        문서 전체를 지운다는 사실을, 다음 사람이 이 시험에서 읽는다.
        """
        att, cc = read("attach.js"), read("ccrender.js")
        self.assertIn("md2html", att)
        self.assertIn("mdTable(", att,
                      "md2html 이 더는 mdTable 을 안 부른다면 이 시험의 근거를 "
                      "다시 써라 — 문서 렌더의 길목이 옮겨간 것이다")
        self.assertIn("function mdTable(", cc,
                      "mdTable 이 ccrender.js 를 떠났다 — 위 시험의 이름을 그 "
                      "조각으로 옮겨라")
        chain = os.path.join(APP, "ccrender.js")
        with open(chain, encoding="utf-8") as f:
            head = f.read(4000)
        self.assertIn("use strict", head)


class DeadChunkSpeaks(unittest.TestCase):
    """S5 — 조각 하나가 죽으면 화면이 침묵하지 않는다.

    이 요청의 진짜 비용은 lookbehind 한 줄이 아니라 **아무도 아무 말도 하지
    않았다**는 것이다. 캡처 없는 제보가 오갔고, 이 자리에는 사파리가 없다.
    다음번엔 화면이 스스로 말해야 왕복이 한 번으로 끝난다.
    """

    def test_dead_chunk_speaks(self):
        """S5 — 조각 하나가 죽으면 화면이 침묵하지 않는다."""
        with self.subTest("s5_the_reporter_runs_first"):
            _, app = webasset.parts()
            self.assertEqual(app[0], "oops.js",
                             "알리는 조각이 맨 앞이 아니다 — 뒤의 조각이 죽는 것을 "
                             "보려면 그전에 서 있어야 한다")
        with self.subTest("s5b_the_reporter_cannot_die_of_syntax"):
            code = code_of("oops.js")
            for pat, why in ((r"(?<![\w$.])(?:const|let)\s", "const/let"),
                             (r"=>", "화살표 함수"),
                             (r"`", "템플릿 리터럴"),
                             (r"\.\.\.", "전개 연산자"),
                             (r"\?\.", "옵셔널 체이닝"),
                             (r"\?\?", "널 병합")):
                self.assertIsNone(
                    re.search(pat, code),
                    f"web/app/oops.js 가 {why} 를 쓴다 — 알리는 조각은 ES5 여야 한다")
        with self.subTest("s5c_the_reporter_leans_on_nothing"):
            code = code_of("oops.js")
            for fn in ("esc", "dlink", "linkifyIds", "md2html", "catFind", "shortId"):
                self.assertFalse(
                    re.search(r"(?<![\w$.])" + fn + r"\s*\(", code),
                    f"oops.js 가 {fn}() 를 부른다 — 그 조각이 죽었을 때 알림도 "
                    "같이 죽는다 (자기 것으로 지어 써라)")
        with self.subTest("s5d_it_says_what_died_and_what_the_browser_can_do"):
            src = read("oops.js")
            for mark, why in (
                    ('addEventListener("error"', "오류를 안 듣는다"),
                    ('"error", function(e){', "오류 처리기가 없다"),
                    ("}, true);", "캡처 단계로 안 듣는다 — 자원 오류는 버블하지 않는다"),
                    ("userAgent", "어느 브라우저인지 안 적는다"),
                    ("(?<!a)b", "lookbehind 지원 여부를 직접 물어보지 않는다"),
                    ("[?&]oops", "멀쩡할 때 강제로 여는 길(?oops)이 없다 — '봤는데 "
                                 "아무것도 없었다'와 '안 봤다'를 구별할 수 없다")):
                self.assertTrue(mark in src, f"web/app/oops.js: {why}")

if __name__ == "__main__":
    unittest.main(verbosity=2)
