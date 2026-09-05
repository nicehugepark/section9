"""판정 화면이 "무엇에 대한 판정인가"를 먼저 말하는가 (REQ-20260826-023 반려 재작업).

반려 사유: "이 건은 무슨 내용에 대한 리뷰인지 모르겠고, 리뷰 확인 포인트도
뭔말인지 모르겠다."

판정을 요구하는 자리는 두 곳이다 — Board 의 review 카드와 문서 뷰어의 .gate
callout. 둘 다 지금까지 **전이 note(확인 포인트)만** 보여줬다. 제목 한 줄
("대시보드 메시지 유실")로는 무슨 건인지 떠오르지 않는 채 결론부터 읽게 되니
확인 포인트가 뭔 말인지 알 수 없는 것이 당연하다. 요약(summary)을 확인 포인트
**위에** 놓아 배경 → 판단 요구 순서를 만든다.

덧붙여 확인 포인트는 대개 "① … ② … ③ …" 로 여러 갈래를 한 문단에 욱여넣는다.
원문을 고치지 않고 번호 앞에서만 줄을 끊어 갈래 수가 눈에 잡히게 한다.

픽셀이 아니라 이 구조 계약만 검사한다 (단일 파일 JS라 정적 계약으로 검증).

실행: python3 tests/ review_context
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


class ReviewContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        with open(S9_SRC, encoding="utf-8") as f:
            cls.s9 = f.read()

    # --- S1: Board 판정 카드 ---

    def test_review_context(self):
        """ReviewContext 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("card_judge_shows_summary"):
            m = re.search(r'const acts = isReq && r\.status === "review"\s*\?(.+?)\n', self.src, re.S)
            self.assertIsNotNone(m, "판정 블록을 찾지 못했다")
            blk = m.group(1)
            self.assertIn("r.summary", blk, "판정 카드가 무엇에 대한 건인지 말하지 않는다")
            self.assertIn("무엇을", blk)
        with self.subTest("card_summary_precedes_review_point"):
            m = re.search(r'const acts = isReq && r\.status === "review"\s*\?(.+?)\n', self.src, re.S)
            blk = m.group(1)
            self.assertLess(blk.index("r.summary"), blk.index("r.review_point"))
        with self.subTest("card_summary_only_on_judge_cards"):
            m = re.search(r'return `<div class="card".+?\n\}', self.src, re.S)
            self.assertIsNotNone(m)
            body = m.group(0)
            # 카드 본문 템플릿(판정 블록은 acts 변수로 주입되므로 여기 없어야 한다)
            self.assertNotIn("r.summary", body)
        with self.subTest("card_summary_caption_is_not_the_loudest"):
            m = re.search(r"\.rvpt\.what \.rvcap\{([^}]*)\}", self.src)
            self.assertIsNotNone(m, ".rvpt.what .rvcap 규칙이 없다")
            css = m.group(1)
            self.assertNotIn("--c-review", css)
            # faint(2.9:1)는 캡션에 이미 한 번 반려된 잉크다 (REQ-20260825-081) —
            # 조용하게 만들려다 안 읽히게 하면 같은 실수를 반복한다.
            self.assertNotIn("--faint", css)
        with self.subTest("card_summary_is_clamped"):
                m = re.search(r"\.rvpt\.what \.wtx\{([^}]*)\}", self.src)
                self.assertIsNotNone(m, ".rvpt.what .wtx 클램프 규칙이 없다")
                self.assertIn("line-clamp", m.group(1))

            # --- S2: 문서 뷰어 gate callout ---
        with self.subTest("gate_shows_summary"):
            self.assertIn('class="gate-w"', self.src)
            m = re.search(r'const what = m\.summary \? `<div class="gate-w">([^`]*)`', self.src)
            self.assertIsNotNone(m, "gate-w 를 summary 로 채우지 않는다")
            self.assertIn("esc(m.summary)", m.group(1))
        with self.subTest("gate_summary_precedes_note"):
            m = re.search(r'gate = `<div class="gate">(.+?)`;', self.src, re.S)
            self.assertIsNotNone(m)
            tpl = m.group(1)
            self.assertLess(tpl.index("${what}"), tpl.index('class="gate-b"'))
        with self.subTest("gate_w_css_is_ledger_language"):
                m = re.search(r"\.gate-w\{([^}]*)\}", self.src)
                self.assertIsNotNone(m, ".gate-w CSS 규칙이 없다")
                css = m.group(1)
                self.assertNotIn("border-radius", css)
                self.assertNotIn("box-shadow", css)

            # --- S3: 확인 포인트 갈래 나누기 ---
        with self.subTest("gate_note_splits_numbered_points"):
            m = re.search(r"function gateNote\(note\)\{(.+?)\n\}", self.src, re.S)
            self.assertIsNotNone(m, "gateNote 가 없다")
            fn = m.group(1)
            self.assertIn("[①-⑳]", fn)
            self.assertIn(r"\(\d{1,2}\)", fn)   # 두 표기를 모두 받는다
            self.assertIn("gate-p", fn)
            # 원문은 손대지 않는다 — 자르기만 하고 치환하지 않는다
            self.assertNotIn(".replace(", fn)
        with self.subTest("gate_note_split_regex_has_no_lookbehind"):
            m = re.search(r"function gateNote\(note\)\{(.+?)\n\}", self.src, re.S)
            self.assertNotIn("(?<=", m.group(1))
        with self.subTest("gate_note_requires_sequential_numbering"):
            m = re.search(r"function gateNote\(note\)\{(.+?)\n\}", self.src, re.S)
            fn = m.group(1)
            self.assertIn("n === i + 1", fn)
        with self.subTest("gate_note_escapes_before_split"):
            m = re.search(r"function gateNote\(note\)\{(.+?)\n\}", self.src, re.S)
            fn = m.group(1)
            self.assertLess(fn.index("esc(note)"), fn.index("gate-p"))
        with self.subTest("gate_note_used_by_both_current_and_history"):
            self.assertIn("gateNote(cur.note)", self.src)
            self.assertIn("gateNote(r.note)", self.src)
            # 옛 경로(직접 linkifyIds(esc(...)))가 gate 안에 남아있지 않다
            m = re.search(r'gate = `<div class="gate">(.+?)`;', self.src, re.S)
            self.assertNotIn("linkifyIds(esc(cur.note))", m.group(1))
        with self.subTest("single_point_note_stays_one_block"):
            m = re.search(r"function gateNote\(note\)\{(.+?)\n\}", self.src, re.S)
            self.assertIn("marked.length > 1", m.group(1))
        with self.subTest("gate_note_behaviour"):
                CN = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

                def split_parts(src):
                    marks = [0]
                    for i, ch in enumerate(src):
                        if ch in CN and i:
                            marks.append(i)
                        elif re.match(r"\s\(\d{1,2}\)\s", src[i:]) and i:
                            marks.append(i)
                    marks.append(len(src))
                    out = []
                    for a, b in zip(marks, marks[1:]):
                        s = src[a:b].strip()
                        if s:
                            out.append(s)
                    return out

                def num(s):
                    if s and s[0] in CN:
                        return CN.index(s[0]) + 1
                    m = re.match(r"\((\d{1,2})\)", s)
                    return int(m.group(1)) if m else 0

                def splits(src):
                    parts = split_parts(src)
                    marked = [n for n in map(num, parts) if n]
                    return (len(marked) > 1 and all(n == i + 1 for i, n in enumerate(marked)),
                            parts)

                ok, parts = splits("확인 포인트 3개. ① 첫째다. ② 둘째다. ③ 셋째다.")
                self.assertTrue(ok)
                self.assertEqual(len(parts), 4)          # 머리말 + 세 갈래

                ok, parts = splits("확인 포인트 (F5 후 Docs 탭): (1) 타입바 순서. (2) 미답 표기. (3) 그래프.")
                self.assertTrue(ok)
                self.assertEqual(len(parts), 4)

                # 갈래가 아닌 글: 우연한 괄호 숫자에 끊기지 않는다
                ok, _ = splits("테스트 (3) 건이 실패했다. 원인은 하나다.")
                self.assertFalse(ok)

                # 번호가 순서를 어기면 갈래로 보지 않는다
                ok, _ = splits("① 첫째. ③ 셋째.")
                self.assertFalse(ok)

                # 평범한 한 문단은 그대로 둔다
                ok, _ = splits("유예 600초가 적절한지 봐 달라.")
                self.assertFalse(ok)

            # --- S4: 원천 계약 — 카탈로그가 summary 를 싣는다 ---
        with self.subTest("catalog_carries_summary"):
            self.assertIn('"summary": meta.get("summary", "")', self.s9)

if __name__ == "__main__":
    unittest.main(verbosity=2)
