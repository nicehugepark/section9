"""점유 경고가 남 탓으로 읽히지 않는다 (REQ-20260828-004-62x6).

실사고 2026-08-28 07:03. 경고 줄은 이렇게 말했다:

    가장 많이 쥔 쪽은 dllhost.exe(pid 16120) 11,499개다.

리드는 그것을 읽고 사용자에게 **두 번 틀린 말**을 했다 — "우리 것은 아닙니다",
"제가 손댈 수 있는 게 아닙니다". 사용자가 "이 머신엔 section9 외엔 특별한
프로세스가 없다"고 되짚어 준 뒤에야 다시 봤다.

둘 다 사실이 아니었다. `dllhost.exe` 는 **WSL 이 포트를 호스트에 공개할 때
소유자로 잡히는 중계**라 거기 쌓인 것은 대개 우리가 연 자리이고, `s9 doctor
--recover` 로 즉시 돌려받을 수 있다. `s9 doctor` 는 이미 그렇게 말하고 있었는데
매 턴 눈에 들어오는 경고 줄만 이름을 대고 끝냈다.

소유자 값으로 "우리 것/남의 것"을 가릴 수 없다는 것은 그대로다
(REQ-20260827-022) — 그건 답할 수 없는 질문이다. 그러나 **그 이름이 무엇인지는
말할 수 있고, 말해야 한다.** 이름만 대고 끝내면 읽는 사람이 스스로 남 탓으로
채워 넣는다.

실행: python3 tests/ port_owner_wording
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_pow", importlib.machinery.SourceFileLoader("s9_pow", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class PortOwnerWording(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        src = open(S9_SRC, encoding="utf-8").read()
        # 구간은 **표식으로** 끊는다 — 예전엔 1400자를 세었는데, 그 앞의
        # 주석이 길어지자(REQ-20260902-066) `who += (` 가 창 밖으로 밀려
        # setUpClass 가 ValueError 로 죽었다. 글자 수는 계약이 아니다.
        i = src.index('who = ""')
        cls.seg = src[i:src.index("# 심각도를 비율에 맞춰", i)]
        # 실제로 사람에게 나가는 문장만 — 주석은 이 실수를 인용하고 있어서
        # 그대로 재면 주석 때문에 계약이 깨진다.
        j = cls.seg.index("who += (")
        cls.said = cls.seg[j:cls.seg.index(")\n", j)]

    # N1. 중계 이름을 알아본다
    def test_port_owner_wording(self):
        """PortOwnerWording 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_relay_recognised"):
                for n in ("dllhost.exe", "DLLHOST.EXE", " svchost.exe "):
                    self.assertTrue(self.m._is_wsl_relay(n), n)

            # B1. 아무 이름이나 중계로 치지 않는다 — 그러면 진짜 남의 점유를 가린다
        with self.subTest("b1_other_names_not_relay"):
                for n in ("chrome.exe", "python3", "", None, "docker.exe"):
                    self.assertFalse(self.m._is_wsl_relay(n), n)

            # N2. 중계일 때는 그것이 무엇인지와 되돌리는 명령을 함께 말한다
        with self.subTest("n2_says_what_and_how"):
                self.assertIn("_is_wsl_relay", self.seg)
                self.assertIn("중계", self.seg)
                self.assertIn("--recover", self.seg,
                              "돌려받는 방법을 말하지 않는다")

            # F1. "우리 것/남의 것" 을 단정하지 않는다 — 답할 수 없는 질문이다
            #     (REQ-20260827-022 에서 그렇게 단정했다가 매번 거짓을 말했다)
        with self.subTest("f1_no_ownership_claim"):
            for phrase in ("우리 것이 아니", "남의 프로세스", "우리 몫"):
                self.assertNotIn(phrase, self.said, phrase)

if __name__ == "__main__":
    unittest.main()
