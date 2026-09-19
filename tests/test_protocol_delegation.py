"""디자인 위임 규약 영속화 계약 테스트 (REQ-20260825-082, 승인 후속 REQ-057).

승인 메모 "화면 디자인은 기본적으로 새로 만든 에이전트를 사용"이 CLAUDE.md에만
있고(47a975e) 하네스 공통 규약 원본(harness/common/PROTOCOL.md)에는 없으면,
GEMINI.md/AGENTS.md 주입 경로가 규칙을 받지 못해 드리프트한다. 이 계약이 고정한다.
실행: python3 tests/test_protocol_delegation.py
"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class TestProtocolDelegation(unittest.TestCase):
    # P1. PROTOCOL.md에 designer 기본 위임과 스킬 계보·금지 제약이 명시된다
    def test_test_protocol_delegation(self):
        """TestProtocolDelegation 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("p1_protocol_has_design_delegation"):
                proto = read("harness", "common", "PROTOCOL.md")
                for kw in ["designer", "s9-design", "browser-verify",
                           "색면 하이라이트", "세로 띠", "무채색 미니멀"]:
                    self.assertIn(kw, proto, f"PROTOCOL.md에 '{kw}' 누락")

            # P2. CLAUDE.md와 PROTOCOL.md가 같은 핵심 규칙을 담는다 (드리프트 방지)
        with self.subTest("p2_claude_md_in_sync"):
                claude = read("CLAUDE.md")
                for kw in ["designer", "s9-design", "색면 하이라이트", "무채색 미니멀"]:
                    self.assertIn(kw, claude, f"CLAUDE.md에 '{kw}' 누락")

            # P4. 「말과 태도」 셋이 규약에 있고 사본까지 내려온다 (REQ-20260902-009).
            #     사용자 지적: "기본 세팅으로 지시한 것들이 내 개인 선호로 빠져 있다."
            #     개인 설정(pref_*)은 그 사용자에게만 주입되므로, 하네스의 기본값이
            #     거기 있으면 다른 설치·다른 사용자에게는 그 규율이 아예 없다.
        with self.subTest("p4_voice_and_manner_defaults_are_protocol"):
                proto = read("harness", "common", "PROTOCOL.md")
                claude = read("CLAUDE.md")
                for kw in ["말과 태도",
                           "칭찬과 아부는 하지 않는다",      # 말투
                           "남의 도구가 지은 이름은 번역하지 않는다",  # 용어
                           "실행 중인 일은 끝까지 지켜본다"]:  # 작업 방식
                    self.assertIn(kw, proto, f"PROTOCOL.md에 '{kw}' 누락")
                    self.assertIn(kw, claude, f"CLAUDE.md에 '{kw}' 누락 — 재동기화 필요")

            # P5. 용어 조항은 **양쪽 날**을 다 싣는다 — 한쪽만 남으면 무차별 번역이나
            #     무차별 원어 중 하나로 기운다 (REQ-20260902-002 판정의 나머지 절반).
        with self.subTest("p5_the_term_rule_cuts_both_ways"):
                proto = read("harness", "common", "PROTOCOL.md")
                self.assertIn("worktree", proto, "원어로 둘 이름의 예가 없다")
                self.assertIn("무차별 원어", proto,
                              "반대편(무차별 원어도 결함)이 빠지면 조항이 한쪽으로 기운다")

            # P6. 존댓말의 경계가 규약에 서고 생성물까지 내려온다
            #     (REQ-20260919-005-62x6). 실측 2026-09-19: 가이드 화면은 존댓말
            #     93.5% 인데 요청 문서의 노트는 6.1%, 규약 자신은 1.6% 였다.
            #     「어디서나 존댓말」로 넓히면 규약·스킬의 명령형까지 흔들리므로,
            #     사람이 읽는 자리와 에이전트가 읽는 자리를 갈라 적는다.
        with self.subTest("p6_honorific_boundary_is_stated"):
                proto = read("harness", "common", "PROTOCOL.md")
                claude = read("CLAUDE.md")
                for kw in ["사람이 읽는 글은 존댓말이다",
                           "에이전트가 읽는 지시문은 명령형이다",
                           "이 글을 읽는 것이 사람인가, 에이전트인가"]:
                    self.assertIn(kw, proto, f"PROTOCOL.md에 '{kw}' 누락")
                    self.assertIn(kw, claude, f"CLAUDE.md에 '{kw}' 누락 — 재동기화 필요")
                # 경계는 자리를 이름으로 짚어야 한다 — 추상적인 한 줄이면
                # 읽는 에이전트가 제 글이 어느 쪽인지 못 고른다.
                for kw in ["확인 포인트", "스킬 문서", "위임 지시문", "코드 주석"]:
                    self.assertIn(kw, proto, f"PROTOCOL.md 경계 목록에 '{kw}' 누락")

            # P7. 생성물이 원천과 글자까지 같다 (REQ-20260919-005-62x6).
            #     `s9-install --agents-md` 는 PROTOCOL.md 전문을 마커 사이에
            #     넣는 단순 치환이다 — 블록이 원천과 같으면 그 명령을 다시
            #     돌려도 파일이 바뀌지 않는다(멱등). 키워드 몇 개만 세면
            #     원천을 고치고 생성을 안 돌린 드리프트가 그대로 지나간다.
        with self.subTest("p7_claude_md_block_equals_protocol"):
                proto = read("harness", "common", "PROTOCOL.md").strip()
                claude = read("CLAUDE.md")
                begin, end = "<!-- section9:begin -->", "<!-- section9:end -->"
                self.assertIn(begin, claude, "CLAUDE.md 에 section9 블록 마커가 없다")
                self.assertIn(end, claude, "CLAUDE.md 에 section9 블록 끝 마커가 없다")
                block = claude.split(begin, 1)[1].split(end, 1)[0].strip()
                self.assertEqual(block, proto,
                                 "CLAUDE.md 의 블록이 PROTOCOL.md 와 다르다 — "
                                 "원천을 고쳤으면 `bin/s9-install --agents-md CLAUDE.md` 로 "
                                 "생성물을 갱신하라")

            # P3. 시각화 3 에이전트 정의가 s9-design 스킬을 참조한다 (U계약 유지)
        with self.subTest("p3_agents_reference_ux_craft"):
            for name in ["designer", "ux-writer", "frontend-developer"]:
                body = read("harness", "claude", "agents", "s9-agnt-" + name + ".md")
                self.assertIn("s9-design", body, f"{name}.md에 s9-design 누락")

if __name__ == "__main__":
    unittest.main(verbosity=2)
