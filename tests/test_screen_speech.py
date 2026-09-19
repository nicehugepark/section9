"""대시보드와 가이드의 사용자 문구는 존댓말이다 (REQ-20260919-013-62x6).

낱말은 `test_screen_lexicon` 이 지키는데 **말투는 아무도 안 봤다**. 실측
2026-09-19(REQ-20260919-002-62x6): 가이드 화면 93.5% · 요청 문서의 노트 6.1% —
같은 규약 한 줄을 두고 자리마다 갈렸고, 갈린 까닭은 존댓말에 검사가 하나도
없어서였다. 글로만 있는 규칙은 모델이 바뀌면 진다.

전이 메모는 `s9 status --note` 가 막고(REQ-20260919-008-62x6), 노트 본문은
`s9 note` 가 막는다(REQ-20260919-012-62x6). 남은 자리가 화면 문구다 — 이 글은
명령이 아니라 소스에 박혀 있으니 막을 전이가 없고, 그래서 시험이 맡는다.

**세는 눈은 한 벌이다.** 읽는 자리는 `screensurf.surfaces()` 를 그대로 쓰고
(`test_screen_lexicon` 이 쓰는 그 모듈이다), 판정은 `bin/s9` 의
`plain_speech_in` 을 그대로 쓴다 — 눈이 둘이면 한 벌만 고쳐진다.
다만 이 눈은 `code_blind` 다: `<pre>`·`<code>`·템플릿 안의 HTML 주석을 안 본다.
거기 선 글은 **기계가 찍은 출력을 그대로 옮긴 인용**이거나(가이드 2.1 절의 첫
실행 출력) 다음 개발자에게 하는 말이라, 말투를 고치면 가이드가 거짓말이 된다.

**재는 자리는 판정이 선 자리다** — 대시보드(`web/index.html` · `web/app/*.js`)와
가이드(`web/guide.html`). 판정 없이 검사를 넓히면 다음 사람이 오탐으로 읽고
목록째 지운다(`BANNED_WEB` 가 세운 그 선). 밖에 둔 것과 까닭:

  · `verify-*.html` — 개발자가 눈으로 보려고 세운 검증 하네스다. 사람이 쓰는
    화면이 아니고, 그 글은 무엇을 어떻게 보라는 **지시문**이라 명령형이 제 말투다.
  · `bin/s9` · `bin/s9-guard` — 서버 문장이 팝업으로 나가는 자리가 섞여 있지만
    대부분은 터미널에서 에이전트가 읽는 글이다. 한 파일에 두 독자가 살아, 어느
    문자열이 사람 앞에 나가는지 판정이 먼저 서야 한다. 그 판정 없이 여기를 넓히면
    오탐이 목록째 지워지게 만든다 — 남은 몫으로 REQ-20260919-013-62x6 에 적었다.
  · 주석·docstring — 다음 개발자에게 하는 말이다. `_surfaces()` 가 이미 걷어낸다.

실행: python3 tests/ screen_speech
"""
import importlib.machinery
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import screensurf   # noqa: E402  — 읽는 눈을 그대로 빌려 쓴다

S9 = os.path.join(HERE, "..", "bin", "s9")
_spec = importlib.util.spec_from_loader(
    "s9_screen_speech", importlib.machinery.SourceFileLoader("s9_screen_speech", S9))
_s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_s9)

# 사람이 쓰는 화면. 나머지 표면을 왜 뺐는지는 이 파일 머리에 적었다.
DASHBOARD_HTML = {"index.html", "guide.html"}


def _screens():
    """사람이 쓰는 화면만 → 표시 이름: 사용자 문자열."""
    return {name: text
            for name, text in screensurf.surfaces(code_blind=True).items()
            if name.startswith("app/") or name in DASHBOARD_HTML}


# ── 반말로 두는 자리 — **근거와 함께만 오른다** ─────────────────────────────
#
# `KEPT_AUTO` 와 같은 방식이다: 목록에 없는 반말은 새로 생기는 즉시 걸리고,
# 지나가게 하려면 이 자리에 까닭을 적어야 한다. 판정을 코드가 아니라 문서에
# 남기게 하는 것이 이 목록의 값이다.
KEPT_PLAIN = {
    "기록에서 답을 찾지 못했다":
        "화면 문장이 아니라 **표식**이다 — 서버(bin/s9.py AGENT_ANSWER_MISS_MARK)가"
        " 이 글자로 답을 시작하라고 시키고 화면은 그 글자를 알아보기만 한다."
        " 말투를 고치면 양쪽이 서로를 못 알아본다 (web/app/const.js)",
}


def _plain_hits(text):
    """이 화면의 반말 평서문 — [(문장 꼬리, 그 줄)…]."""
    hits = []
    for line in text.splitlines():
        rest = line
        for ok in KEPT_PLAIN:
            rest = rest.replace(ok, " ")
        for tail in _s9.plain_speech_in(rest, limit=99):
            hits.append((tail, rest.strip()[:100]))
    return hits


class TheScreenSpeaksPolitely(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.screens = _screens()

    def test_the_sweep_actually_read_the_screen(self):
        """빈 글을 훑고 통과가 되는 일이 없게 — 먼저 눈을 확인한다.

        추출이 조용히 실패하면 이 시험은 영원히 통과하고, 그때부터 검사는 없는
        것과 같아진다(`test_screen_lexicon` 이 파이프 종료코드에서 배운 그것)."""
        self.assertGreaterEqual(len(self.screens), 20,
                                "훑은 화면 파일이 너무 적다 — 경로가 틀렸다")
        self.assertIn("guide.html", self.screens, "가이드를 안 훑었다")
        self.assertIn("index.html", self.screens, "대시보드를 안 훑었다")
        joined = "\n".join(self.screens.values())
        self.assertGreater(len(joined), 50000, "사용자 문자열을 못 읽었다")
        for anchor in ("이어가기", "중단하기"):
            self.assertIn(anchor, joined, "화면에 있어야 할 「%s」를 못 찾았다" % anchor)

    def test_no_plain_speech_on_the_dashboard_or_the_guide(self):
        hits = []
        for name, text in sorted(self.screens.items()):
            for tail, line in _plain_hits(text):
                hits.append("%s: …%s   ← %s" % (name, tail, line))
        self.assertEqual(
            [], hits,
            "화면 문구가 반말이다 — 사람이 읽는 글은 존댓말이다(규약 2조 1). "
            "반말로 두어야 할 까닭이 있으면 KEPT_PLAIN 에 근거와 함께 올려라:\n  "
            + "\n  ".join(hits))

    def test_the_eye_does_not_count_the_comments(self):
        """주석의 반말은 세지 않는다 — 다음 개발자에게 하는 말이다.

        규약 2조 1 이 가른 그 경계다: 사람이 읽는 글은 존댓말이고, 에이전트가
        읽는 지시문은 명령형이다. 주석을 존댓말로 고치면 강제가 권유로 읽힌다."""
        src = ('// 여기서는 되돌리지 않는다\n'
               '/* 판정은 한 곳에서만 내린다 */\n'
               'const s = `<!-- 이 줄은 DOM 에만 있고 눈에는 안 보인다 -->`;\n'
               'const t = "이 창에서 이어집니다";\n')
        self.assertEqual(
            _s9.plain_speech_in(screensurf._strings(src, code_blind=True)), [])

    def test_the_eye_does_not_count_the_quoted_output(self):
        """`<pre>`·`<code>` 안은 세지 않는다 — 기계가 찍은 것을 옮긴 인용이다.

        가이드 2.1 절은 첫 실행을 실제로 돌려 그 출력을 그대로 옮겼다. 그 안의
        「…실행한다」를 존댓말로 고치면 가이드가 없는 화면을 말하게 된다."""
        src = ("<p>이 줄은 안내입니다</p>"
               "<pre><code>◌ s9-install 을 먼저 실행한다…</code></pre>")
        self.assertEqual(
            _s9.plain_speech_in(screensurf._html_text(src, code_blind=True)), [])
        self.assertEqual(
            len(_s9.plain_speech_in(screensurf._html_text(src))), 1,
            "낱말을 재는 눈은 그 안까지 보아야 한다 — 기본값이 바뀌었다")

    def test_the_eye_does_count_a_screen_string(self):
        """화면에 나가는 문자열의 반말은 잡는다 — 위 시험의 짝이다."""
        src = 'const s = "이 창에서 이어진다";\n'
        self.assertEqual(
            len(_s9.plain_speech_in(screensurf._strings(src, code_blind=True))), 1)

    def test_the_eye_does_not_count_code_or_imperatives(self):
        """코드 글자와 명령형 지시문은 세지 않는다."""
        for text in ("state/speech-warn-<sid>.json", "aria-describedby=pol-fore",
                     "먼저 서버를 다시 시작하라", "이 창을 닫지 마라"):
            self.assertEqual(_s9.plain_speech_in(text), [], text)

    def test_the_eye_does_not_count_what_a_person_typed(self):
        """사람이 친 말은 세지 않는다 — 화면이 나르기만 하는 글이다.

        인용부호 안(「」·따옴표)은 `plain_speech_in` 이 보지 않고, 사람이 적은
        제목·노트는 소스가 아니라 문서에서 와 이 시험의 눈에 닿지 않는다."""
        self.assertEqual(
            _s9.plain_speech_in("주인 지적 「이게 뭐다」 를 그대로 싣습니다"), [])
        self.assertEqual(
            _s9.plain_speech_in(screensurf._strings('const t = `${r.title}`;')), [])

    def test_the_kept_lines_still_stand(self):
        """반말로 두기로 한 자리가 화면에 살아 있다 — 목록에서 빠진 것만으로는
        지워지지 않았다는 증거가 못 된다(`KEPT_AUTO` 가 세운 그 규율)."""
        joined = "\n".join(self.screens.values())
        for kept in KEPT_PLAIN:
            self.assertIn(kept, joined,
                          "반말 유지 문장 「%s」가 화면에서 사라졌다 — 목록에서도 "
                          "빼라" % kept)


if __name__ == "__main__":
    unittest.main(verbosity=2)
