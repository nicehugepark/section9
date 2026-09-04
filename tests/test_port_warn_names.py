"""포트 경고가 범인을 말하는가 (REQ-20260827-020-62x6).

사용자가 터미널 로그를 붙여 왔다 — "동적 포트 12956/16384 (79%) … 우리 것이
아닌 점유자를 의심하라". 실측하니 정말 우리 것이 아니었다: Windows COM 대리
프로세스(`dllhost.exe`) 하나가 13,392개를 쥐고 있었고 **우리 것은 0개**였다.

문제는 수치가 아니라 문구다. "의심하라"까지만 말하고 누구인지는 말하지 않는데,
그 답은 방금 `doctor` 가 이미 준 값 안에 있다(`top_name`·`top_pid`·`top_count`).
사람에게 다시 조사를 시키는 것이고, 실제로 사용자가 이 줄만 보고 우리 결함으로
읽었다.

한 줄에 **경보 + 범인 + 우리 몫**이 함께 있어야 그 자리에서 판단이 끝난다.
우리 것이 0개인데 82%라면 우리가 할 일이 없다는 뜻이고, 그 사실이야말로 이
줄이 전해야 할 것이다.

실행: python3 tests/ port_warn_names
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class PortWarnNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(S9, encoding="utf-8") as f:
            cls.src = f.read()
        m = re.search(r'elif ratio >= PORT_GUARD_WARN:(.*?)\n    return verdict',
                      cls.src, re.S)
        cls.warn = m.group(1) if m else ""

    def test_port_warn_names(self):
        """PortWarnNames 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("p1_the_warning_names_the_holder"):
            self.assertTrue(self.warn, "경고 분기를 찾지 못했다")
            for f in ("top_name", "top_pid", "top_count"):
                self.assertIn(f, self.warn, f"{f} 를 쓰지 않는다")
        with self.subTest("p2_it_never_claims_a_share_it_cannot_know"):
            # **주석이 아니라 실제로 찍히는 문장**을 본다. 처음엔 소스 블록을 통째로
            # 훑었는데, 이 결함의 내력을 적어 둔 주석에 그 문구가 들어 있어 테스트가
            # 헛되이 붉어졌다 — 계약은 코드가 하는 말이지 코드에 대한 설명이 아니다.
            code = "\n".join(l for l in self.warn.splitlines()
                             if not l.strip().startswith("#"))
            self.assertNotIn('win.get("sample")', code, "없는 필드를 다시 읽는다")
            self.assertNotIn("우리 것은", code, "알 수 없는 몫을 다시 단언한다")
        with self.subTest("p3_it_survives_missing_fields"):
            self.assertIn('if win.get("top_name") and win.get("top_count")',
                          self.warn, "필드가 없을 때의 갈래가 없다")
        with self.subTest("p4_auto_recovery_threshold_is_untouched"):
            # 0.90 은 그대로 문의 첫 조건이다 (REQ-20260904-016 뒤로는 그 문이
            # `_port_recover_gate` 안에 있고, 비율 하나로는 열리지 않는다).
            self.assertIn("if ratio < PORT_GUARD_AUTO:", self.src)
            self.assertIn("PORT_GUARD_AUTO = 0.90", self.src)
            self.assertIn('_doctor("--recover", "--yes")', self.src)

if __name__ == "__main__":
    unittest.main()
