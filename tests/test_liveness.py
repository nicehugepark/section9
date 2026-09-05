"""생존 판정 단일화 (REQ-20260826-016).

사용자 지적: "지목 전송이 되면서 헬스체크도 되는거여야하는데 그것도 잘못되고
있는것 아닌가?"

서버 판정들이 지금은 우연히 같은 답을 낸다. 문제는 **같은 질문을 서로 다른
코드가 따로 계산한다**는 것이다 — 스트립(/api/agents)은 transcript mtime 이
180초 이내인가로, 헬스체크는 pid·진전·워커 로그로. 규칙이 갈라져 있으면
언젠가 답도 갈라지고, 그때 화면은 "돌고 있다"는데 워처는 "아무도 안 한다"로
움직인다. 오늘 실제로 그 어긋남에서 중복 스폰(REQ-20260826-013)과 반려 통지
오배달(REQ-20260826-015)이 났다.

그래서 판정을 judge_health 한 곳으로 모으고, 이 파일이 그 단일성을 고정한다.
실행: python3 tests/ liveness
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

os.environ.setdefault("S9_ROOT", tempfile.mkdtemp(prefix="s9-live-"))
spec = importlib.util.spec_from_loader(
    "s9_mod_live", importlib.machinery.SourceFileLoader("s9_mod_live", S9))
s9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s9)


class SingleJudgment(unittest.TestCase):
    """actor_alive 는 judge_health 를 감쌀 뿐 자기 규칙을 갖지 않는다."""

    def test_single_judgment(self):
        """actor_alive 는 judge_health 를 감쌀 뿐 자기 규칙을 갖지 않는다."""
        with self.subTest("agrees_with_judge_health_on_every_input"):
            cases = []
            for actor in ("sub:designer", "lead:claude-opus-5", "worker:auto",
                          "wf:review", "이상한값"):
                for age in (None, 0, 60, 179, 181, 3000):
                    for pid in (None, True, False):
                        cases.append((actor, age, pid))
            for actor, age, pid in cases:
                state, _why = s9.judge_health(actor, age=age, pid_alive=pid)
                self.assertEqual(s9.actor_alive(actor, age=age, pid_alive=pid),
                                 state == "alive",
                                 f"{actor} age={age} pid={pid} → {state}")
        with self.subTest("recorded_result_wins"):
            self.assertFalse(s9.actor_alive("sub:designer", age=0, recorded="done"))
            self.assertFalse(s9.actor_alive("sub:designer", age=0, recorded="failed"))
        with self.subTest("window_comes_from_one_table"):
            win = s9.HEALTH_WIN["sub"]
            self.assertTrue(s9.actor_alive("sub:designer", age=win - 1))
            self.assertFalse(s9.actor_alive("sub:designer", age=win + 1))
        with self.subTest("unknown_actor_is_not_alive"):
            self.assertFalse(s9.actor_alive("", age=0))
            self.assertFalse(s9.actor_alive("garbage", age=0))
        with self.subTest("never_raises"):
            for bad in (None, 123, [], {}):
                s9.actor_alive(bad, age="x", pid_alive="y", log_line=None)

class StripUsesTheSameRule(unittest.TestCase):
    """스트립(/api/agents)의 active 가 자기만의 180 을 들고 있지 않다."""

    def test_no_literal_window_in_agents_handler(self):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        i = src.index('parsed.path == "/api/agents"')
        seg = src[i:i + 2600]
        self.assertIn("actor_alive", seg,
                      "스트립이 단일 판정을 쓰지 않는다")
        self.assertNotIn('st["mtime"] < 180', seg,
                         "스트립이 자기 숫자로 생존을 판정한다")


if __name__ == "__main__":
    unittest.main()
