"""고른 문서는 **제자리에서 살짝** 구분된다 (REQ-20260831-007).

이 파일은 `tests/test_doc_pin_release.py` 를 **대체한다** — 그 파일이 지키던
규칙("지금 보는 문서를 목록 맨 위에 못 박는다", REQ-20260828-009 → -20260829-012)을
사용자가 뒤집었기 때문이다. 뒤집힌 규칙을 지키는 시험을 남겨 두면 회귀 그물이
사용자의 최신 판정과 반대편에 선다.

사용자: "docs 탭에서 좌측 문서에서 현재 보고 있는 문서를 최상단 row 로 하나
뽑기보다는 그냥 목록들 사이에서 살짝 강조만 되면 좋을 것 같다. 그리고 좌측 문서
목록들을 번갈아가면서 선택하다보면 문서 목록이 자꾸 바뀐다."

## 둘은 같은 하나였다

실브라우저(CDP)로 잰 것: 목록 id 배열을 A→B→A→B 로 갈아타며 찍었더니 매번
달라졌다. 원인은 폴링도, 정렬 축도 아니었다 — 순서 얼림(stableOrder)은 15초
폴링을 35초 관찰해도 흔들리지 않았다. 흔든 것은 **못 박기 자체**다: 고른 줄을
제 무리에서 빼내 맨 위에 세우므로, A 에서 B 로 옮기면 A 가 제자리로 돌아가고
B 가 빠져나가 그 사이의 줄이 전부 한 칸씩 밀린다.

## 못 박기가 풀려던 문제는 다른 길로 푼다

"묻혀 있으면 못 찾는다"(009)는 참이다. 자리를 옮기는 대신 **보이게** 한다 —
한도(20) 밖이면 거기까지 펴고(docReach, 줄지 않는다), 사람이 방금 고른 것이면
그 줄로 스크롤한다(붙박이 타입바 두께만큼 물러서서).

실행: python3 tests/ doc_place_emphasis
"""
import os
import re
import unittest
from webasset import index_path

INDEX = index_path()


def rules_for(src, needle):
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"(?m)^([^\n{}]+)\{([^{}]*)\}", src)
            if needle in m.group(1)]


class DocPlaceEmphasis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        m = re.search(r"async function renderDocs\(rows\)\{(.+?)\n\}\n", cls.src, re.S)
        assert m, "renderDocs 를 찾지 못했다"
        cls.rd = m.group(1)

    # --- ① 뽑아 올리지 않는다 ---

    def test_doc_place_emphasis(self):
        """DocPlaceEmphasis 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("nothing_is_lifted_out_of_its_group"):
            self.assertNotIn("const pin = selectedDoc", self.rd,
                             "고른 문서를 따로 뽑아내는 길이 남아 있다")
            self.assertNotIn("rowHTML(pin)", self.rd, "뽑은 줄을 맨 위에 세우고 있다")
            self.assertNotIn("pinhead", self.src, "뽑은 줄의 머리글이 남아 있다")
        with self.subTest("every_row_goes_into_its_group"):
            m = re.search(r"ordered\.forEach\(([\s\S]{0,160}?)\);\n", self.rd)
            self.assertTrue(m, "무리 나누기 한 줄을 못 찾았다")
            body = m.group(1)
            self.assertIn("groups[r.type]", body, "무리로 나누지 않는다")
            for word in ("selectedDoc", "sel", "pin"):
                self.assertNotIn(word, body,
                                 "무리 나누기가 선택을 예외로 두고 있다: %s" % word)
        with self.subTest("the_freeze_rule_is_untouched"):
                self.assertRegex(
                    self.src,
                    r'const refreeze = !\(\$\(\'#view \.docs\[data-pane="docs"\] \.doclist\'\)'
                    r' && \$\("#viewer"\)\);',
                    "얼음 조건이 바뀌었다")

            # --- ② 제자리에서 살짝 ---
        with self.subTest("the_mark_is_ink_not_a_field"):
            base = dict(rules_for(self.src, ".doclist .row.sel"))
            rest = [c for s, c in base.items()
                    if s.endswith(".row.sel:not(:hover)") or s.endswith(".row.sel")]
            self.assertTrue(rest, "고른 줄의 쉼 얼굴이 정해져 있지 않다")
            flat = "".join(rest).replace(" ", "")
            self.assertIn("background:none", flat, "쉼 얼굴에 면이 깔렸다")
            for sel, body in base.items():
                b = body.replace(" ", "")
                self.assertNotIn("border-left", b, "왼쪽 세로 띠는 금지다: " + sel)
                self.assertNotRegex(b, r"box-shadow:inset\d*px",
                                    "왼쪽 세로 띠(inset 바)는 금지다: " + sel)
        with self.subTest("the_mark_the_ink_and_the_weight_all_stand"):
            self.assertRegex(self.src, r'\.doclist \.row\.sel \.id::before\{content:"●"',
                             "지금 이것을 가리키는 표식이 없다")
            self.assertRegex(self.src, r"\.doclist \.row\.sel \.id\{color:var\(--text\)\}",
                             "고른 줄의 번호가 이웃과 같은 잉크다")
            self.assertRegex(self.src, r"\.doclist \.row\.sel>div:nth-child\(3\)\{font-weight:",
                             "고른 줄의 제목이 이웃과 같은 굵기다")
        with self.subTest("the_mark_inherits_its_ink"):
            m = re.search(r"\.doclist \.row\.sel \.id::before\{([^}]*)\}", self.src)
            self.assertIsNotNone(m)
            self.assertIn("color:currentColor", m.group(1).replace(" ", ""),
                          "● 의 색을 박아 두었다")
        with self.subTest("the_hovered_face_is_not_swallowed"):
                for sel, body in rules_for(self.src, ".doclist .row.sel"):
                    if "background:none" in body.replace(" ", ""):
                        self.assertIn(":not(:hover)", sel,
                                      "고른 줄이 hover 얼굴을 잃는다: " + sel)

            # --- ③ 묻히지 않게 하되, 자리는 그대로 ---
        with self.subTest("the_reach_only_grows"):
            self.assertRegex(self.src, r"(?m)^let docReach", "펴 놓은 만큼의 기억이 없다")
            self.assertRegex(self.rd, r"docReach\[g\] = Math\.max\(docReach\[g\] \|\| 0, si \+ 1\)",
                             "펴 놓은 자리가 줄어들 수 있다")
            self.assertRegex(self.rd, r"if \(refreeze \|\| docReachKey !== okey\)",
                             "조건이 바뀌어도 옛 폄이 남는다")
        with self.subTest("the_eye_moves_not_the_row"):
            self.assertRegex(self.rd, r"if \(selectedDoc && \(fresh \|\| refreeze\)\)",
                             "사람이 고른 때와 배경 갱신을 가르지 않고 스크롤한다")
            self.assertIn('scrollIntoView({block: "nearest"})', self.rd,
                          "고른 줄을 화면 안으로 들이지 않는다")
        with self.subTest("the_sticky_bar_does_not_bury_the_row"):
                m = re.search(r"(?m)^\.doclist \.row\{([^{}]*)\}", self.src, re.S)
                self.assertIsNotNone(m, "목록 행 규칙을 찾지 못했다")
                body = m.group(1)
                self.assertIn("scroll-margin-top", body.replace(" ", ""),
                              "붙박이 두께만큼 물러서지 않는다")
                self.assertIn("--tbh", body, "타입바 높이를 실측값으로 쓰지 않는다")

            # --- ④ 풀 수 있다 (REQ-20260829-012 가 세운 능력) ---
        with self.subTest("the_release_handle_lives_in_the_row"):
            m = re.search(r"const rowHTML = r => \{(.+?)\n  \};", self.rd, re.S)
            self.assertIsNotNone(m, "목록 행을 짓는 자리를 찾지 못했다")
            self.assertIn("data-seloff", m.group(1), "손잡이가 줄 안에 없다")
            self.assertRegex(m.group(1), r'const off = on \?',
                             "손잡이가 고른 줄에만 서지 않는다")
        with self.subTest("the_handle_is_caught_before_the_row"):
            self.assertRegex(self.src, r'closest\("\[data-seloff\]"\)',
                             "손잡이를 눌러도 아무 일도 일어나지 않는다")
            off = self.src.index('closest("[data-seloff]")')
            row = self.src.index('closest("[data-doc]")')
            self.assertLess(off, row, "행을 여는 길이 손잡이보다 먼저 잡힌다")
        with self.subTest("the_handle_is_ink_and_reachable_by_keyboard"):
            self.assertRegex(self.src, r'<button type="button" class="seloff"',
                             "손잡이가 진짜 button 이 아니다")
            body = dict(rules_for(self.src, ".seloff"))
            base = [c for s, c in body.items() if s.endswith(".seloff")]
            self.assertTrue(base, ".seloff 규칙이 없다")
            flat = base[0].replace(" ", "")
            self.assertIn("background:none", flat)
            self.assertIn("border:0", flat)
            self.assertIn("color:inherit", flat, "잉크를 박으면 반전 스킨에서 묻힌다")
            self.assertTrue(any(":focus-visible" in s for s in body),
                            "키보드로 닿은 자리가 보이지 않는다")
        with self.subTest("the_handle_does_not_change_the_row_height"):
            body = dict(rules_for(self.src, ".seloff"))
            base = [c for s, c in body.items() if s.endswith(".seloff")][0].replace(" ", "")
            self.assertIn("font-size:10px", base, "번호 칸보다 큰 글자가 줄을 키운다")
            self.assertIn("line-height:inherit", base)
        with self.subTest("letting_go_clears_the_selection_everywhere"):
            m = re.search(r"function docDeselect\(\)\{(.+?)\n\}", self.src, re.S)
            self.assertIsNotNone(m, "선택을 푸는 함수가 없다")
            fn = m.group(1)
            self.assertIn("selectedDoc = null", fn)
            self.assertIn("pushRoute()", fn, "주소에 문서가 남아 새로고침하면 되살아난다")
        with self.subTest("letting_go_shows_the_empty_state"):
                m = re.search(r"function docDeselect\(\)\{(.+?)\n\}", self.src, re.S)
                self.assertIsNotNone(m)
                self.assertIn("문서를 선택하세요", m.group(1),
                              "푼 뒤에 오른쪽이 무엇을 보여 주는지 정해지지 않았다")

            # --- 물려받은 규율 (REQ-20260829-012 에서 그대로 옮겨 온다) ---
        with self.subTest("switching_documents_rebuilds_the_list"):
            m = re.search(r"function docOpen\(id\)\{(.+?)\n\}", self.src, re.S)
            self.assertIsNotNone(m, "docOpen 을 찾지 못했다")
            fn = m.group(1)
            self.assertIn("render()", fn, "문서를 바꿔도 목록을 다시 그리지 않는다")
            self.assertNotIn("loadDoc(", fn, "목록을 건너뛰고 뷰어만 갈아 끼우는 길이 남아 있다")
        with self.subTest("the_human_path_and_the_poll_path_stay_apart"):
            self.assertRegex(self.src, r"(?m)^let docFresh",
                             "사람이 고른 경로를 구별하는 표시가 없다")
            self.assertRegex(self.rd, r"const fresh = docFresh; docFresh = false;",
                             "겹친 렌더가 서로의 표시를 가져간다 — 맨 위에서 읽고 끈다")
            self.assertIn("loadDoc(selectedDoc, !fresh)", self.rd,
                          "사람이 고른 문서도 배경 갱신처럼 연다")
        with self.subTest("the_switch_can_be_reproduced_without_hands"):
            self.assertIn("[?&]swap=", self.src, "문서를 갈아탄 화면을 세워 볼 길이 없다")
            self.assertRegex(self.src, r"docOpen\(r\.id\)")
        with self.subTest("escape_does_not_drop_the_document"):
            m = re.search(r'if \(e\.key !== "Escape"\) return;(.+?)\}\);', self.src, re.S)
            self.assertIsNotNone(m, "전역 Escape 핸들러를 찾지 못했다")
            self.assertNotIn("selectedDoc", m.group(1),
                             "Esc 가 문서 선택까지 지운다 — 같은 키에 두 층이 얹혔다")
            self.assertNotIn("docDeselect", m.group(1))

if __name__ == "__main__":
    unittest.main()
