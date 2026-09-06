"""Stream 화면이 도장 시각을 스스로 고쳐 그리는가 (REQ-20260827-010-62x6).

응답 머리의 도장 — `` `[2026-08-27 00:26:11 KST - 타치코마]` `` — 에 모델이 적어 넣는
시각은 언제나 **프롬프트가 도착한 시각의 복사본**이다. 모델은 자기가 말을 마치는
시각을 알 수 없다. 그래서 문서에 남는 기록은 Stop 훅(bin/s9-audit-response 의
correct_stamp)이 실제 시각으로 바로잡는다 — 그건 실제 데이터로 검증됐다
(REQ-20260826-038: 22:37 노트가 13분 37초 어긋나 있었고, 고침 이후 00:26 노트는
초 단위까지 맞는다).

**Stream 탭은 그 보정이 닿지 않는 자리다.** 이 화면은 문서 노트가 아니라
transcript 를 직접 읽어 그리므로, 같은 응답이 문서에서는 맞는 시각을, 화면에서는
프롬프트가 도착한 시각을 말한다. 대시보드는 그 이벤트의 실제 시각(e.ts)을 이미
쥐고 있으니, 화면이 자기 시각으로 그리면 된다.

이 테스트가 지키는 계약은 다섯이다.

  ① 화면이 그리는 도장의 시각은 **이벤트의 실제 시각**에서 온다.
  ② **이름(역할)은 모델이 쓴 것을 살린다.** 누가 말하는지는 모델만 아는 사실이고,
     여기서 눌러 쓰면 위임된 에이전트의 보고가 리드의 말로 둔갑한다.
  ③ **머리에 있는 것만 도장이다.** 본문 중간에 예시로 적힌 같은 모양을 고치면
     문서가 자기 설명과 어긋난다 — 정규식에 m(multiline) 플래그가 붙으면
     줄머리마다 걸려 그 사고가 난다.
  ④ 접힌 요약과 펼친 본문이 **같은 시각**을 말한다 — 한 화면 안에서 두 자리가
     갈라지면 고친 의미가 없다.
  ⑤ 도장이 없는 이벤트(tool·result 등)는 손대지 않는다.

정규식은 화면 소스에서 그대로 꺼내 **실제로 돌려** 검사한다 — "있더라"가 아니라
"그 글자에 어떻게 걸리더라"를 본다.

실행: python3 tests/ stream_stamp_ui
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

STAMP = "`[2026-08-27 00:13:00 KST - designer]`"
BODY = "본문 첫 줄\n두 번째 줄"


def js_func(src, name):
    """index.html 에서 함수 하나의 소스를 통째로 꺼낸다 (중괄호 균형)."""
    i = src.find("function " + name)
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


class StreamStamp(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()
        m = re.search(r"const STAMP_RE = /(.+?)/([a-z]*);", self.src)
        self.assertIsNotNone(m, "화면에서 도장 정규식을 찾지 못했다")
        self.re_src, self.re_flags = m.group(1), m.group(2)
        # JS 리터럴을 파이썬 re 로 그대로 옮겨 실제로 돌린다 (문법 호환 구간만 씀)
        self.stamp_re = re.compile(self.re_src)

    # ---------- ③ 머리에 있는 것만 도장이다 ----------

    def test_stamp_pattern_matches_only_the_head(self):
        self.assertTrue(self.stamp_re.match(STAMP + "\n" + BODY),
                        "응답 머리의 도장에 걸려야 한다")
        self.assertIsNone(self.stamp_re.match("설명 한 줄\n" + STAMP),
                          "본문 중간의 같은 모양은 도장이 아니다")

    def test_stamp_pattern_is_not_multiline(self):
        """m 플래그가 붙으면 줄머리마다 걸린다 — 문서가 자기 설명과 어긋난다."""
        self.assertNotIn("m", self.re_flags,
                         "도장 정규식에 multiline 플래그가 붙으면 안 된다")
        self.assertNotIn("g", self.re_flags,
                         "도장은 하나뿐이다 — 전역 치환이면 예시까지 바뀐다")

    def test_stamp_pattern_captures_time_and_name_separately(self):
        m = self.stamp_re.match(STAMP)
        self.assertEqual(m.group(1), "2026-08-27 00:13:00")
        self.assertEqual(m.group(2), "designer")

    # ---------- ①② 시각은 화면 것, 이름은 모델 것 ----------

    def test_fix_uses_event_time_and_keeps_the_model_name(self):
        fn = js_func(self.src, "stampFix")
        self.assertTrue(fn, "도장을 고쳐 쓰는 함수(stampFix)가 없다")
        head = re.search(r"head:\s*([^,]+(?:,[^,]*)?),\s*\n?\s*rest", fn) \
            or re.search(r"head:\s*(.+)", fn)
        self.assertIsNotNone(head, "고쳐 쓴 도장을 만드는 자리를 찾지 못했다")
        h = head.group(1)
        self.assertIn("m[2]", h, "이름은 모델이 쓴 것(캡처 2)을 그대로 써야 한다")
        self.assertNotIn("m[1]", h,
                         "모델이 쓴 시각(캡처 1)을 다시 그리면 고친 게 아니다")
        self.assertIn("real", h, "시각은 이벤트의 실제 시각에서 와야 한다")
        self.assertRegex(fn, r"real\s*=\s*[^;]*\bts\b",
                         "실제 시각은 이벤트의 ts 에서 파생해야 한다")

    def test_fix_is_called_with_the_event_timestamp(self):
        fn = js_func(self.src, "renderEvents")
        self.assertTrue(fn, "renderEvents 를 찾지 못했다")
        self.assertRegex(fn, r"stampFix\(\s*e\.text\s*,\s*e\.ts\s*\)",
                         "이벤트 본문과 그 이벤트의 실제 시각을 함께 넘겨야 한다")

    # ---------- ④ 접힌 요약과 펼친 본문이 같은 시각을 말한다 ----------

    def test_collapsed_summary_shows_the_same_corrected_text(self):
        fn = js_func(self.src, "renderEvents")
        body = fn[fn.find("stampFix"):]
        self.assertNotIn("e.text.slice", body,
                         "접힌 요약이 원문을 잘라 쓰면 요약만 옛 시각을 말한다")
        self.assertNotIn("e.text.length", body,
                         "길이 판정도 고쳐 쓴 본문 기준이어야 한다")
        self.assertNotIn("esc(e.text)", body,
                         "펼친 본문도 고쳐 쓴 것을 그려야 한다")

    # ---------- ⑤ 도장이 없으면 손대지 않는다 ----------

    def test_events_without_a_stamp_are_left_alone(self):
        fn = js_func(self.src, "stampFix")
        self.assertRegex(fn, r"if\s*\(!m[^)]*\)\s*return null",
                         "도장이 없는 이벤트는 그대로 둬야 한다")

    # ---------- 고쳤다는 사실을 감추지 않는다 ----------

    def test_correction_is_visible_when_it_actually_moved_the_clock(self):
        """어긋남이 클 때는 무엇을 고쳤는지 볼 수 있어야 한다 (색면 아닌 점선)."""
        self.assertIn(".stampfix", self.src, "고친 도장에 표시가 없다")
        css = re.search(r"\.term \.stampfix\{([^}]*)\}", self.src)
        self.assertIsNotNone(css, "고친 도장 표시의 스타일이 없다")
        self.assertIn("dotted", css.group(1),
                      "점선 밑줄 어휘(doclink)와 같게 — 색면 하이라이트 금지")
        self.assertNotIn("background", css.group(1), "색면 하이라이트 금지")
        i = self.src.find('class="stampfix"')
        self.assertGreater(i, 0, "고친 도장을 그리는 자리를 찾지 못했다")
        tip = re.search(r'title="([^"]*)"', self.src[i:i + 900]).group(1)
        self.assertIn("모델", tip, "무엇을 왜 고쳤는지 사용자 말로 알려야 한다")
        for jargon in ("transcript", "correct_stamp", "STAMP_RE", "e.ts", "hook"):
            self.assertNotIn(jargon, tip,
                             f"화면 문구에 내부 용어({jargon})가 새면 안 된다")


if __name__ == "__main__":
    unittest.main()
