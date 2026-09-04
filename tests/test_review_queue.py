"""판정 큐가 계보를 화면에서 지키는가 (REQ-20260831-015 화면 몫, DOC-20260831-002 규칙2).

서버는 review 행에 세 값을 싣는다(`review_family`, tests/test_review_family.py 가
그 계약을 지킨다). 화면이 할 일은 셋이다:

  ① review 열을 `review_order` 로 세운다 — 그 값 하나로 오름차순 정렬하면
     같은 묶음이 붙어 서고 선행(created 이른 쪽)이 위에 온다.
  ② `review_prior` 가 있는 후행 카드에 "먼저 볼 것이 있다"를 한 줄로 말한다.
  ③ `review_stale` 이 있는 카드에 "판정 대상이 바뀌는 중"을 한 줄로 말한다.

**자리가 계약인 이유**: 이 두 줄은 승인·반려 버튼보다 **먼저** 읽혀야 한다.
버튼 아래에 서면 사용자는 판정을 내린 다음에 경고를 읽는다 — 경고가 아니라
사후 통지다. 그래서 판정 블록의 맨 위가 계약이다.

**한 줄이 계약인 이유**: s9-design 「카드 사실 줄」이 정한 밀도다 — 축마다 한 줄,
카드 최대 두 줄. 둘 다 관계 축이라 사다리로 하나만 세우고, 진 쪽은 이긴 줄의
꼬리로 붙는다.

픽셀이 아니라 이 구조 계약만 검사한다 (실렌더 확인은 browser-verify 몫).

실행: python3 tests/ review_queue
"""
import re
import unittest

from webasset import index_path

INDEX = index_path()


class ReviewQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        m = re.search(r"function judgeQueueHTML\(r\)\{(.+?)\n\}", cls.src, re.S)
        cls.jq = m.group(1) if m else ""
        m = re.search(r"function renderBoard\(rows\)\{(.+?)\n\}", cls.src, re.S)
        cls.board = m.group(1) if m else ""
        m = re.search(r"function cardHTML\(r\)\{(.+?)\n\}", cls.src, re.S)
        cls.card = m.group(1) if m else ""

    # --- S1/S2 정렬 ---

    def test_review_queue(self):
        """ReviewQueue 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("review_column_sorts_by_review_order"):
            self.assertTrue(self.board, "renderBoard 를 찾지 못했다")
            m = re.search(r'if \(st === "review"\)\s*\n\s*(grp = .+?;)', self.board, re.S)
            self.assertIsNotNone(m, "review 열 전용 정렬 분기가 없다")
            self.assertIn("reviewKey", m.group(1))
        with self.subTest("review_order_has_fallback_key"):
                m = re.search(r"function reviewKey\(r\)\{(.+?)\n\}", self.src, re.S)
                self.assertIsNotNone(m, "reviewKey 폴백 술어가 없다")
                body = m.group(1)
                self.assertIn("review_order", body)
                self.assertIn("created", body)
                self.assertIn("000", body)

            # --- S3/S4 두 줄 ---
        with self.subTest("prior_line_names_the_leader"):
            self.assertTrue(self.jq, "judgeQueueHTML 을 찾지 못했다")
            self.assertIn("review_prior", self.jq)
            self.assertIn("catFind", self.jq)
        with self.subTest("prior_line_counts_the_rest"):
            self.assertIn("depmore", self.jq)
        with self.subTest("stale_line_exists"):
            self.assertIn("review_stale", self.jq)
        with self.subTest("no_lock"):
                for bad in ("disabled", "aria-disabled"):
                    self.assertNotIn(bad, self.jq)

            # --- S5 사다리 ---
        with self.subTest("one_line_per_axis"):
            self.assertIn("factTail", self.jq)
            # 사다리는 **이긴 쪽에서 나간다**: 낡음 갈래가 서면 그 자리에서 return
            # 하므로 두 줄이 이어 붙어 나갈 길이 없다.
            self.assertRegex(self.jq, r"if \(churn\.length\)\s*\n\s*return",
                             "낡음 갈래가 그 자리에서 끝나지 않는다 — 사다리가 아니다")
            # 이긴 줄 뒤에 다른 줄을 덧대는 형태(두 div 를 한 템플릿에)도 금지.
            for chunk in self.jq.split("return")[1:]:
                self.assertLessEqual(len(re.findall(r'class="rvpt', chunk.split(";")[0])), 1,
                                     "한 번에 두 줄이 나간다")
        with self.subTest("dep_line_outranks_queue_line"):
                m = re.search(r"const queue = (.+?);\n", self.card)
                self.assertIsNotNone(m, "cardHTML 이 큐 줄을 세우지 않는다")
                self.assertIn("bl.length", m.group(1))

            # --- S6 자리 ---
        with self.subTest("queue_line_precedes_the_buttons"):
                m = re.search(r'const acts = isReq && r\.status === "review"\s*\?(.+?)\n', self.card, re.S)
                self.assertIsNotNone(m, "판정 블록을 찾지 못했다")
                blk = m.group(1)
                self.assertIn("queue", blk, "판정 블록에 큐 줄이 없다")
                self.assertLess(blk.index("queue"), blk.index("acts"),
                                "큐 줄이 승인·반려 버튼보다 뒤에 있다")
                self.assertLess(blk.index("queue"), blk.index("r.review_point"),
                                "큐 줄이 확인 요청보다 뒤에 있다")

            # --- S7 잉크·금지 ---
        with self.subTest("reuses_the_one_line_grammar"):
            for cls in (r"\.rvpt\.ahead", r"\.rvpt\.churn"):
                self.assertRegex(self.src, cls + r"[,{]")
        with self.subTest("ink_only_no_fill"):
            for sel in ("ahead", "churn"):
                for m in re.finditer(r"\.rvpt\.%s(?: \.rvcap)?\{([^}]*)\}" % sel, self.src):
                    css = m.group(1)
                    self.assertNotIn("background", css, sel + " 줄이 면을 칠한다")
                    self.assertNotIn("border-left", css, sel + " 줄에 좌측 띠가 있다")
        with self.subTest("caption_ink_is_not_faint"):
            for m in re.finditer(r"\.rvpt\.(?:ahead|churn) \.rvcap\{([^}]*)\}", self.src):
                self.assertNotIn("--faint", m.group(1))
        with self.subTest("skin_override_restores_the_ink"):
            for skin in set(re.findall(r'\[data-skin="([\w-]+)"\][^{]*\.judge \.rvcap\{', self.src)):
                self.assertRegex(
                    self.src,
                    r'\[data-skin="%s"\][^{]*\.rvpt\.(?:ahead|churn) \.rvcap' % skin,
                    "%s 스킨이 판정 큐 캡션 잉크를 덮고 되돌리지 않는다" % skin)
        with self.subTest("line_is_clipped_to_one_line"):
                # 스킨 블록(.gate·calm 등)은 자기 언어대로 이 줄을 눕힐 수 있다 —
                # 계약이 보는 것은 베이스(카드)의 규칙이다.
                m = re.search(r"\n\.rvpt\.ahead,\.rvpt\.churn\{([^}]*)\}", self.src)
                self.assertIsNotNone(m, "베이스의 한 줄 규칙이 없다")
                self.assertIn("nowrap", m.group(1))
                self.assertIn("ellipsis", m.group(1))

            # --- S8 경계 ---
        with self.subTest("silent_without_fields"):
                self.assertRegex(self.jq, r'return ""')

            # --- S9 문서 화면 ---
        with self.subTest("document_gate_says_the_same"):
            m = re.search(r"gate = `<div class=\"gate\">(.+?)`;", self.src, re.S)
            self.assertIsNotNone(m, "gate callout 을 찾지 못했다")
            blk = m.group(1)
            self.assertIn("gq", blk, "문서 gate 에 판정 큐 줄이 없다")
            self.assertLess(blk.index("gq"), blk.index("gate-b"),
                            "큐 줄이 확인 포인트보다 뒤에 있다")
        with self.subTest("document_gate_shares_one_source"):
            m = re.search(r"const gq = (.+?);\n", self.src)
            self.assertIsNotNone(m, "문서 gate 가 큐 줄을 짓지 않는다")
            self.assertIn("judgeQueue", m.group(1))

if __name__ == "__main__":
    unittest.main()
