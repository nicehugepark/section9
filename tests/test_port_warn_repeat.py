"""같은 경고를 몇 번 말하는가 (REQ-20260827-019-62x6).

사용자가 12분치 serve 로그를 붙여 왔는데 **열한 줄이 글자 하나까지 같았다** —
같은 포트 경고가 76초마다 다시 나오고 있었다.

수치는 맞았고 문구도(REQ-20260827-020 에서) 고쳤지만, 되풀이 자체가 결함이다.
**정보가 없는 반복은 정보를 가린다**: 그 사이에 있었을 다른 줄(서버 사망·재기동·
고아 회수)이 그 벽에 묻히고, 사람은 곧 그 로그를 안 읽게 된다.

그래서 **상황이 바뀔 때만** 말한다. 바뀜의 정의는 *사람이 판단을 다시 해야 하는
것*이다 — 심각도 구간 · 가장 많이 쥔 쪽 · 우리 몫. 숫자가 12956 → 12973 으로
흔들리는 것은 판단을 바꾸지 않는다.

그리고 아무것도 안 바뀌어도 한 시간에 한 번은 말한다 — **조용한 것과 감시가
죽은 것은 로그에서 구별되지 않는다.**

실행: python3 tests/ port_warn_repeat
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


class PortWarnRepeat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_loader(
            "s9warn", importlib.machinery.SourceFileLoader("s9warn", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def setUp(self):
        self.m._port_warn_last.clear()

    def test_r1_same_situation_speaks_once(self):
        """R1. 같은 상황은 한 번만 말한다 (이 요청의 전부).

        1분 주기로 다섯 번 돌아도 로그에는 한 줄이어야 한다.
        """
        said = [self.m._port_warn_should_speak("15|19596|0", 1000 + i * 60)
                for i in range(5)]
        self.assertEqual(said, [True, False, False, False, False], said)

    def test_r2_a_new_holder_speaks(self):
        """R2. 가장 많이 쥔 쪽이 바뀌면 말한다 — 사람이 다시 판단할 일이다."""
        self.m._port_warn_should_speak("15|19596|0", 1000)
        self.assertTrue(self.m._port_warn_should_speak("15|777|0", 1060))

    def test_r3_our_share_changing_speaks(self):
        """R3. **우리 몫**이 달라지면 말한다.

        0개에서 3개가 되는 순간이 이 경고가 존재하는 이유다 — 그때부터는
        우리가 할 일이 있다.
        """
        self.m._port_warn_should_speak("15|777|0", 1000)
        self.assertTrue(self.m._port_warn_should_speak("15|777|3", 1060))

    def test_r4_silence_does_not_last_forever(self):
        """R4. 변화가 없어도 한 시간에 한 번은 말한다.

        조용한 것과 감시가 죽은 것은 로그에서 구별되지 않는다.
        """
        self.m._port_warn_should_speak("15|777|3", 1000)
        self.assertFalse(
            self.m._port_warn_should_speak("15|777|3", 1000 + 3599))
        self.assertTrue(
            self.m._port_warn_should_speak("15|777|3", 1000 + 3601))

    def test_r5_jitter_is_not_a_change(self):
        """R5. 숫자가 흔들리는 것은 변화가 아니다.

        붙여 온 로그에서 12954~13000 사이를 오갔는데 판단은 내내 같았다.
        그 흔들림마다 말하면 아무것도 안 고친 것이다.
        """
        self.assertEqual(int(0.790 * 20), int(0.793 * 20))

    def test_r6_the_recovery_path_is_not_muted(self):
        """R6. **자동 회수 경로는 이 침묵에 걸리지 않는다.**

        90% 를 넘겨 마지막 안전망이 도는 것은 매번 남아야 한다 — 그건 "상황이
        같다"가 아니라 "계속 나쁘다"이고, 회수가 실제로 돌았다는 기록이다.
        조용하게 만들다 사고 기록을 지우면 고침이 새 위험이 된다.
        """
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        # 사다리(REQ-20260904-016) 뒤의 모양: 문(`_port_recover_gate`)이 열리면
        # `if ok:` 가지가 회수를 돌린다. **그 가지**는 침묵 장치를 지나지 않는다.
        # 세워 둔(held) 가지는 같은 말을 되풀이하지 않아도 된다 — 그건 "계속
        # 나쁘다"가 아니라 "여전히 안 죽인다"이고, 왜인지는 verdict.held 에 남는다.
        tick = src.split("def port_guard_tick", 1)[1].split("\ndef ", 1)[0]
        opened = tick.split("if ok:", 1)[1].split("else:", 1)[0]
        self.assertIn('_doctor("--recover", "--yes")', opened,
                      "열린 가지에 회수가 없다 — 구조가 바뀌었으면 이 시험을 다시 읽어라")
        self.assertNotIn("_port_warn_should_speak", opened,
                         "자동 회수 경로까지 침묵시켰다")


if __name__ == "__main__":
    unittest.main()
