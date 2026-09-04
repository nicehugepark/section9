"""시각화 에이전트 강화 계약 (REQ-20260825-057, -082 통합 반영).

designer·ux-writer·frontend-developer는 s9-design 스킬을 필수 로드하고,
참조 계보(Apple HIG·토스류)를 기준으로 명시해야 한다. 스킬 본문은 원칙
나열이 아니라 실행 규칙(상태 설계·모션·접근성·문구)을 담는다.
2026-08-25 사용자 판정으로 ux-craft는 s9-design에 흡수됐다 — 스킬은 하나뿐이다.

실행: python3 tests/ ux_agents
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(HERE, "..", "harness", "claude", "agents")
SKILL = os.path.join(HERE, "..", "harness", "claude", "skills", "s9-design",
                     "SKILL.md")
VISUAL = ("designer", "ux-writer", "frontend-developer")


class TestUxAgents(unittest.TestCase):
    def _read(self, name):
        with open(os.path.join(AGENTS, name + ".md"), encoding="utf-8") as f:
            return f.read()

    # U1. 세 에이전트 모두 s9-design을 필수 스킬로 로드
    def test_test_ux_agents(self):
        """TestUxAgents 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("u1_skill_required"):
                for a in VISUAL:
                    txt = self._read(a)
                    self.assertIn("- **s9-design**", txt, a)
                    self.assertIn("필수 스킬", txt, a)

            # U2. 참조 계보가 정의에 명시된다 (요청: Apple·토스 참조)
        with self.subTest("u2_reference_lineage"):
                for a in VISUAL:
                    txt = self._read(a)
                    self.assertIn("HIG", txt, a)
                    self.assertIn("토스", txt, a)

            # U3. 스킬이 실행 규칙을 담는다 — 원칙 이름만 나열하지 않는다
        with self.subTest("u3_skill_actionable"):
                with open(SKILL, encoding="utf-8") as f:
                    s = f.read()
                for key in ("빈 상태", "로딩", "에러", "prefers-reduced-motion",
                            "4.5:1", "44", "되돌리기", "자가 점검"):
                    self.assertIn(key, s, key)

            # U4. 스킬은 하나다 (REQ-20260825-082 판정: "굳이 2개로 나눌 이유가 없다").
            #     ux-craft 디렉토리가 되살아나거나 정의가 그것을 가리키면 실패한다.
        with self.subTest("u4_single_skill"):
                craft = os.path.join(HERE, "..", "harness", "claude", "skills", "ux-craft")
                self.assertFalse(os.path.exists(craft), "ux-craft가 다시 생겼다")
                for a in VISUAL:
                    self.assertNotIn("ux-craft", self._read(a), a)

            # U5. 흡수된 완성도 기준이 s9-design 안에 실제로 있다 — 이름만 합치고
            #     내용이 빠지면 통합이 아니라 삭제다.
        with self.subTest("u5_craft_content_absorbed"):
            with open(SKILL, encoding="utf-8") as f:
                s = f.read()
            for key in ("한 화면 한 결정", "prefers-reduced-motion", "4.5:1",
                        "동사+목적", "자가 점검", "디자인 언어", "토큰"):
                self.assertIn(key, s, key)

class TestNewSkin(unittest.TestCase):
    """새 스킨·톤 (REQ-20260825-062 재작업): 기존 화면을 손대는 대신 선택
    가능한 스킨/톤으로 제공한다 — Apple·토스 계보(여백·카드·라운드·단일 강조)."""
    def setUp(self):
        with open(index_path(),
                  encoding="utf-8") as f:
            self.html = f.read()

    def test_s1_skin_registered(self):
        self.assertIn('[data-skin="calm"]', self.html)
        self.assertIn('["calm","calm', self.html)

    def test_s2_tones_registered(self):
        for t in ("mist", "graphite"):
            self.assertIn(f':root[data-theme="{t}"]', self.html)
            self.assertIn(f'["{t}","{t}', self.html)

    def _calm_seg(self):
        """calm 스킨 **블록**에 닻을 내린다 — 주석을 먼저 걷는다.

        벨트 주석(actions.css)이 calm 셀렉터를 근거로 인용하면서, 원문 첫
        occurrence 가 주석 속으로 옮겨가 s3/s4 가 엉뚱한 구획을 재게 됐다
        (REQ-20260831-019 mask 처방 주석에서 실측). 닻은 코드에만 내린다."""
        nocom = re.sub(r"/\*[\s\S]*?\*/", " ", self.html)
        i = nocom.index('[data-skin="calm"]')
        return nocom[i:i + 4000]

    def test_s3_distinct_axes(self):
        """썸네일 구분 조건: 기본(ledger)과 배경·모양·깊이가 다르다."""
        seg = self._calm_seg()
        self.assertIn("border-radius", seg)     # 모양
        self.assertIn("box-shadow", seg)        # 깊이
        self.assertIn("border:0", seg)          # 선 대신 면

    def test_s5_cockpit_removed(self):
        """cockpit 스킨 제거 (REQ-20260825-079: 다크-온-다크 판독 불가) —
        CSS 블록·레지스트리 어디에도 남지 않는다(저장값은 ledger 폴백)."""
        self.assertNotIn('[data-skin="cockpit"]', self.html)
        self.assertNotIn('["cockpit"', self.html)

    def test_s4_tokens_only(self):
        """스킨은 tone 토큰 위에서 동작 — 색 하드코딩 최소(그림자 제외).

        mask-image 의 #000 은 색이 아니라 알파 스텐실이라 세지 않는다."""
        hard = [l for l in self._calm_seg().splitlines()
                if "#" in l and "rgba(" not in l and "shadow" not in l
                and "mask-image" not in l]
        self.assertEqual(hard, [], hard)


class TestSkinAudit(unittest.TestCase):
    """전체 스킨 점검 (REQ-20260825-081): calm에만 반영됐던 컴포넌트 계약과
    사용자 확정 금지 패턴을 전 스킨에 고정한다. 스킨이 늘어날 때마다 같은
    결함이 재발하지 않도록 계약으로 박는다."""
    def setUp(self):
        with open(index_path(),
                  encoding="utf-8") as f:
            self.html = f.read()

    # A1. 담당자 이니셜(.av)은 calm 전용 링 마크다. 베이스에서 켜져 있으면
    #     "@이름" 표기를 쓰는 스킨에서 "@Ssjpark1"처럼 붙어 오타로 읽힌다.
    def test_a1_avatar_hidden_by_default(self):
        self.assertIn(".av{display:none}", self.html)
        self.assertIn('[data-skin="calm"] .card .av{', self.html)

    # A2. 판정 캡션(.rvcap)은 faint가 아니라 상태 잉크 — 전 스킨에서 읽혀야
    #     한다("확인 요청"/"대기 사유"가 무엇을 판정하는지 알려주는 라벨).
    def test_a2_judge_caption_is_status_ink(self):
        # 찾는 것은 **베이스**의 캡션 규칙이다 — 줄머리에 홀로 선 `.rvcap{`.
        # 첫 substring 으로 집으면 나중에 얹힌 자리별 규칙
        # (`.gate>.rvpt .rvcap{…}` 처럼 조상 셀렉터를 단 것)이 앞 파일에 있을 때
        # 그것을 잡아, 잉크와 무관한 조판 규칙을 놓고 잉크를 따진다
        # (REQ-20260831-015 에서 실제로 그렇게 붉었다).
        m = re.search(r"\n\.rvcap\{", self.html)
        self.assertIsNotNone(m, "베이스의 .rvcap 규칙이 없다")
        seg = self.html[m.start() + 1:m.start() + 261]
        self.assertIn("var(--c-review)", seg)
        self.assertNotIn("var(--faint)", seg)
        self.assertIn('.card[data-status="blocked"] .rvcap{color:var(--c-blocked)}',
                      self.html)

    # A3. 카드 좌측 컬러 띠 금지 (사용자 반려로 확정 — "전형적인 클로드 디자인").
    #     어느 skin override에서도 .card에 상태색 세로 띠를 두지 않는다.
    def test_a3_no_card_left_color_bar(self):
        for line in self.html.splitlines():
            if ".card{" in line or ".card {" in line:
                self.assertNotIn("border-left", line, line)
        self.assertNotIn("border-left:3px solid var(--sc", self.html)

    # A4. 카드 배경 틴트 하이라이트 금지 — 상태색은 잉크·윤곽으로만 쓴다.
    def test_a4_no_card_status_fill(self):
        for line in self.html.splitlines():
            st = line.strip()
            if st.startswith("background") and "var(--sc" in st:
                self.fail("카드/행 배경에 상태색 채움: " + st)

    # A8. 톤별 대응은 "다크 tone 전부"를 덮어야 한다 — calm의 잉크 명도 반전이
    #     graphite/carbon만 덮어 phosphor에서 태그·이니셜이 어두운 배경에 어두운
    #     색으로 얹혔다 (REQ-20260825-081 육안 확인).
    def test_a8_dark_tone_coverage(self):
        for anchor in ('--hu-s:62%', '--calm-shadow:0 0 0 1px var(--hairline)'):
            i = self.html.index(anchor)
            seg = self.html[max(0, i - 400):i]
            for tone in ("graphite", "carbon", "phosphor"):
                self.assertIn('[data-skin="calm"][data-theme="%s"]' % tone, seg,
                              "%s 톤이 calm 다크 대응에서 빠졌다 (%s)" % (tone, anchor))

    # A5. 레지스트리에 등록된 skin은 모두 CSS 구현 블록을 가진다
    #     (ledger는 베이스 자체라 override 블록이 없다).
    def test_a5_registry_matches_css(self):
        import re
        m = re.search(r'key:"s9skin".*?opts:\[(.*?)\]\}', self.html, re.S)
        self.assertTrue(m, "skin 레지스트리를 찾지 못했다")
        names = re.findall(r'\["([a-z]+)",', m.group(1))
        self.assertIn("ledger", names)
        for n in names:
            if n == "ledger":
                continue
            self.assertIn('[data-skin="%s"]' % n, self.html,
                          "%s: 등록만 되고 CSS 블록이 없다" % n)

    # A6. 컬러 셸 스킨은 그 셸 위 텍스트의 잉크를 따로 지정한다 — 안 하면
    #     라이트 tone에서 어두운 잉크가 어두운 밴드에 묻혀 신원 줄이 사라진다.
    def test_a6_colored_shell_defines_ink(self):
        self.assertIn('[data-skin="cobalt"] .hrow2 .who{', self.html)
        self.assertIn('[data-skin="cobalt"] .hrow2 .usagechip{', self.html)
        self.assertIn('[data-skin="field"] .hrow2{background:var(--panel)', self.html)

    # A7. 목록 카운터(.count)는 터미널 탭 안내줄까지 겸한다 — faint(2.9:1)로는
    #     컬러 캔버스 스킨(cork/field/glass)에서 읽히지 않았다.
    def test_a7_count_contrast(self):
        i = self.html.index(".count{")
        self.assertIn("color:var(--muted)", self.html[i:i + 60])


class TestBoardScope(unittest.TestCase):
    """Board 정보구조 (REQ-20260825-084 / -085): 보드는 요청의 상태 흐름만
    다루고, 없앤 요소의 취지는 다른 수단이 받는다."""
    def setUp(self):
        with open(index_path(),
                  encoding="utf-8") as f:
            self.html = f.read()

    # B1. Board에 knowledge/session 컬럼이 없다 (REQ-20260825-084)
    def test_b1_no_knowledge_session_column(self):
        self.assertNotIn("knowledge / session", self.html)
        self.assertNotIn('colHTML("etc"', self.html)

    # B2. 없앤 취지("지식·세션 문서에 도달한다")를 Docs 타입바가 받는다 —
    #     타입별 건수가 목록 맨 위에 보이고 한 번 눌러 그 타입만 볼 수 있다.
    def test_b2_docs_type_entry_point(self):
        self.assertIn(".typebar{", self.html)          # 컴포넌트
        self.assertIn('data-typef=', self.html)        # 진입점 렌더
        self.assertIn('closest("[data-typef]")', self.html)  # 클릭 = 타입 필터
        self.assertIn('const TYPE_ORDER', self.html)

    # B3. 타입바 카운트는 타입 조건을 뺀 필터로 센다 — 지금 knowledge를 보는
    #     중에도 session이 몇 건인지 보여야 진입점 구실을 한다.
    def test_b3_type_counts_ignore_type_filter(self):
        # 조건식을 글자 그대로 박지 않는다(b5와 같은 이유). 고정할 성질은
        # "타입바의 타입별 건수는 타입 필터에 영향받지 않는다" 하나이지,
        # 그 게이트가 어떤 이름으로 어떻게 조립되는지가 아니다 —
        # 실제로 REQ-20260826-006이 게이트를 넓히자 이 줄이 깨졌다.
        import re
        # 인자 목록은 계약이 아니다 — REQ-20260827-054 가 "조건 하나를 빼고 다시
        # 세기" 위해 skip 집합을 세 번째 인자로 더했다. 여기서 고정할 성질은
        # 타입 게이트의 동작이지 시그니처가 아니다.
        m = re.search(r"function filtered\(skipQ, skipType(?:, \w+)?\)(.*?)\n}",
                      self.html, re.S)
        self.assertTrue(m, "filtered()가 타입 조건 제외 인자를 받지 않는다")
        body = m.group(1)
        # (1) 타입 조건은 해제 가능한 게이트를 통과해야 한다
        ty = re.search(r"if \(!(\w+) && ty && r\.type !== ty\) return false;", body)
        self.assertTrue(ty, "타입 조건이 해제 가능한 게이트 없이 걸린다")
        gate = ty.group(1)
        # (2) 그 게이트는 skipType으로 열린다 (게이트 자신이거나 그것에서 파생)
        self.assertTrue(
            gate == "skipType"
            or re.search(r"(?:const|let|var) " + gate + r"\s*=[^\n;]*skipType", body),
            "타입 조건 게이트(%s)가 skipType과 무관하다" % gate)
        # (3) 타입바 건수는 그 게이트를 연 채 센다
        self.assertIn("filtered(!!matchMap, true)", self.html)

    # B3b. Board에는 타입 축이 없다 (REQ-20260826-006 회귀 방지):
    #      Docs에서 knowledge를 고른 채 Board로 넘어오면 전 컬럼이 0건이 됐다.
    def test_b3b_type_filter_absent_on_board(self):
        import re
        # 인자 목록은 계약이 아니다 — REQ-20260827-054 가 "조건 하나를 빼고 다시
        # 세기" 위해 skip 집합을 세 번째 인자로 더했다. 여기서 고정할 성질은
        # 타입 게이트의 동작이지 시그니처가 아니다.
        m = re.search(r"function filtered\(skipQ, skipType(?:, \w+)?\)(.*?)\n}",
                      self.html, re.S)
        body = m.group(1)
        ty = re.search(r"if \(!(\w+) && ty && r\.type !== ty\) return false;", body)
        gate = ty.group(1)
        # 게이트가 board 탭에서도 열려야 한다 — 보드는 request 전용이라
        # 타입 조건이 걸리면 결과가 통째로 0건이 된다.
        self.assertTrue(
            re.search(r"(?:const|let|var) " + gate + r'\s*=[^\n;]*tab === "board"', body),
            "Board에서 타입 필터가 결과를 0건으로 만들 수 있다")
        # 화면에서도 사라져야 한다 — 적용되지 않는 컨트롤을 남기지 않는다.
        self.assertRegex(self.html, r'#f-type"\);\s*\n?\s*if \(el\) el\.hidden = \(tab === "board"\)')
        self.assertIn(".hrow2 select[hidden]{display:none}", self.html)

    # B4. session은 숨기지 않되 기본 노출을 낮춘다 (사용성 판단)
    def test_b4_session_lower_priority(self):
        import re
        m = re.search(r"GRP_LIMIT_SESSION = (\d+)", self.html)
        g = re.search(r"GRP_LIMIT = (\d+)", self.html)
        self.assertTrue(m and g)
        self.assertLess(int(m.group(1)), int(g.group(1)))
        # 목록 그룹에 자리가 있어야 "숨기지 않되 낮춘다"가 성립한다. 다만 리터럴을
        # 통째로 박으면 타입이 하나 늘 때마다(REQ-20260826-017의 question) 이
        # 시나리오가 깨진다 — 고정할 성질은 "자리가 있고, 맨 뒤다" 두 가지다.
        gm = re.search(r"const groups = \{([^}]*)\}", self.html)
        self.assertTrue(gm, "Docs 목록의 타입 그룹 맵을 찾지 못했다")
        keys = re.findall(r"(\w+):\[\]", gm.group(1))
        self.assertIn("session", keys)
        self.assertEqual(keys[-1], "session",
                         "session 그룹이 목록 맨 뒤가 아니다 (기본 노출 우선순위)")

    # B5. 문서 카운터는 Board에서만 사라진다 — Docs/Graph의 필터 결과 수는 정보다.
    #     빈 줄이 유령 여백을 남기지 않게 접힌다 (REQ-20260825-085)
    def test_b5_board_document_counter_removed(self):
        # 조건식을 글자 그대로 박지 않는다 — 구현이 "board 에서는 항상 없음 +
        # 다른 탭도 필터가 좁혔을 때만"으로 넓어졌고(REQ-085 결정), 그게 이
        # 시나리오가 원하던 바다. 고정할 성질은 "board 면 빈 문자열"이다.
        import re
        m = re.search(r'\$\("#count"\)\.textContent = \(?tab === "board"'
                      r'[^\n]*\?\s*""', self.html)
        self.assertTrue(m, "board 탭에서 문서 카운터가 비워지지 않는다")
        self.assertIn("narrowed", m.group(0),
                      "다른 탭은 필터가 실제로 좁혔을 때만 건수를 보여야 한다")
        self.assertIn(".count:empty{display:none}", self.html)

    # B6. 이 요청이 손대는 것은 **문서 카운터 하나**다 — 상태별 건수는 건드리지
    #     않는다. 그 계약은 유효하되, 건수가 서 있는 **자리**가 바뀌었다:
    #     상단 상태 띠는 REQ-20260827-070 2차에서 내려갔고(같은 집합을 열 머리와
    #     두 번 세고 있었다), 상태별 건수는 이제 열 머리 하나가 말한다.
    #     그래서 검사 대상을 띠에서 열 머리로 옮겨 다시 쓴다 — 지키려던 것("이
    #     작업이 상태 건수를 없애지 않았다")은 그대로다.
    def test_b6_status_counts_kept(self):
        self.assertIn('<span class="n">${live.length}</span>', self.html,
                      "열 머리의 상태별 건수가 사라졌다")
        self.assertNotIn('class="stats"', self.html,
                         "내려간 상단 띠가 되살아났다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
