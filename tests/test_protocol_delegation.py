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
                           "도는 일은 끝까지 지켜본다"]:      # 작업 방식
                    self.assertIn(kw, proto, f"PROTOCOL.md에 '{kw}' 누락")
                    self.assertIn(kw, claude, f"CLAUDE.md에 '{kw}' 누락 — 재동기화 필요")

            # P5. 용어 조항은 **양쪽 날**을 다 싣는다 — 한쪽만 남으면 무차별 번역이나
            #     무차별 원어 중 하나로 기운다 (REQ-20260902-002 판정의 나머지 절반).
        with self.subTest("p5_the_term_rule_cuts_both_ways"):
                proto = read("harness", "common", "PROTOCOL.md")
                self.assertIn("worktree", proto, "원어로 둘 이름의 예가 없다")
                self.assertIn("무차별 원어", proto,
                              "반대편(무차별 원어도 결함)이 빠지면 조항이 한쪽으로 기운다")

            # P3. 시각화 3 에이전트 정의가 s9-design 스킬을 참조한다 (U계약 유지)
        with self.subTest("p3_agents_reference_ux_craft"):
            for name in ["designer", "ux-writer", "frontend-developer"]:
                body = read("harness", "claude", "agents", name + ".md")
                self.assertIn("s9-design", body, f"{name}.md에 s9-design 누락")

if __name__ == "__main__":
    unittest.main(verbosity=2)
