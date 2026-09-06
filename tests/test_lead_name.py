"""리드의 이름은 타치코마 (REQ-20260906-022, 주인 결정 2026-09-06).

사람이 부르는 이름이자 응답 머리의 이름이다. 귀속(lead:<모델>)은 그대로다.
규약·훅 주입·화면 라벨이 같은 이름을 쓴다.

실행: python3 tests/ lead_name
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _const(path):
    m = re.search(r'^LEAD_NAME = "([^"]+)"', open(path, encoding="utf-8").read(), re.M)
    return m.group(1) if m else ""


class LeadName(unittest.TestCase):
    def test_l1_one_name_everywhere(self):
        """L1. s9.py·훅·규약·CLAUDE.md·카드 라벨이 같은 이름을 말한다."""
        name = _const(os.path.join(REPO, "bin", "s9.py"))
        self.assertEqual(name, "타치코마")
        self.assertEqual(_const(os.path.join(REPO, "bin", "s9-audit-prompt")), name)
        self.assertEqual(_const(os.path.join(REPO, "bin", "s9-audit-response")), name)
        proto = open(os.path.join(REPO, "harness", "common", "PROTOCOL.md"), encoding="utf-8").read()
        self.assertIn(f"KST - {name}]`", proto)
        self.assertIn(f"now --as {name}", proto)
        self.assertIn("「타치코마가」", proto, "리드가 자신을 부르는 법이 규약에 없다")
        claude_md = open(os.path.join(REPO, "CLAUDE.md"), encoding="utf-8").read()
        self.assertIn(f"KST - {name}]`", claude_md, "생성물(CLAUDE.md)이 따라오지 않았다")
        card = open(os.path.join(REPO, "web", "app", "card.js"), encoding="utf-8").read()
        self.assertIn(f'return "{name}"', card)

    def test_l2_attribution_kind_stays_lead(self):
        """L2. 귀속 규격 lead:<모델> 은 그대로다 — 이름은 사람이, 귀속은 기계가."""
        src = open(os.path.join(REPO, "bin", "s9.py"), encoding="utf-8").read()
        self.assertIn('"lead"', src)
        self.assertIn("lead:<model>", open(os.path.join(REPO, "harness", "common", "PROTOCOL.md"), encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
