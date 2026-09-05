"""끊긴 턴을 저절로 잇는다 (REQ-20260905-023).

네트워크 오류로 턴이 끊기면 Claude Code 는 transcript 에 `isApiErrorMessage` 줄을
남기고 멈춘다 — 사람이 치기 전까지 아무도 잇지 않는다(실측 2026-09-05 20:47).
서버 틱이 그것을 보고 수신함에 「계속」을 넣는다: 유예 뒤에, 같은 오류엔 한 번만,
세션당 시간 상한만큼만.

실행: python3 tests/ dead_turn
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _line(kind, ts, api_err=False, text="x"):
    d = {"type": kind, "timestamp": ts, "message": {"role": kind, "content": [{"type": "text", "text": text}]}}
    if api_err:
        d["isApiErrorMessage"] = True
    return json.dumps(d)


class DeadTurn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9dead-")
        old = os.environ.get("S9_ROOT"); os.environ["S9_ROOT"] = self.tmp
        try:
            spec = importlib.util.spec_from_loader(
                "s9_deadturn", importlib.machinery.SourceFileLoader("s9_deadturn", S9))
            self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        finally:
            if old is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = old
        self.tp = os.path.join(self.tmp, "t.jsonl")
        self.state = os.path.join(self.tmp, "turn-resume.json")
        self.sent = []

    def _binding(self):
        return {"session": "abcd1234", "transcript_path": self.tp, "ended": ""}

    def _tick(self, now):
        return self.m.dead_turn_tick(bindings=[self._binding()], now=now,
                                     send=lambda text, sid: self.sent.append((sid, text)),
                                     state_path=self.state, live=lambda b: True)

    def test_d1_an_old_api_error_at_the_tail_gets_one_continue(self):
        """D1. 꼬리가 API 오류이고 유예(90초)를 넘겼으면 「계속」 한 번 — 같은 오류엔 다시 안 넣는다."""
        with open(self.tp, "w") as f:
            f.write(_line("user", "2026-09-05T11:40:00Z") + "\n")
            f.write(_line("assistant", "2026-09-05T11:47:50Z", api_err=True,
                          text="API Error: Connection lost mid-response.") + "\n")
        err_t = 1788608870.0                    # 2026-09-05T11:47:50Z
        self.assertEqual(self._tick(err_t + 30), [], "유예 안인데 넣었다")
        self.assertEqual(len(self._tick(err_t + 120)), 1)
        self.assertEqual(self.sent[0][0], "abcd1234")
        self.assertIn("이어서 계속", self.sent[0][1])
        self.assertEqual(self._tick(err_t + 200), [], "같은 오류에 두 번 넣었다")

    def test_d2_a_later_user_line_means_someone_already_continued(self):
        """D2. 오류 뒤에 사용자 줄이 있으면(사람이 이미 이었다) 넣지 않는다."""
        with open(self.tp, "w") as f:
            f.write(_line("assistant", "2026-09-05T11:47:50Z", api_err=True) + "\n")
            f.write(_line("user", "2026-09-05T11:49:24Z") + "\n")
        self.assertEqual(self._tick(1788608870.0 + 600), [])

    def test_d3_a_session_is_not_nagged_more_than_the_hourly_cap(self):
        """D3. 세션당 한 시간에 상한(3)만큼만 — 이어도 또 끊기는 회선은 사람 몫이다."""
        base = 1788608870.0
        for i in range(5):
            with open(self.tp, "w") as f:
                f.write(_line("assistant", f"2026-09-05T11:{47 + i}:50Z", api_err=True) + "\n")
            self._tick(base + i * 60 + 120)
        self.assertEqual(len(self.sent), self.m.DEAD_TURN_MAX_PER_HOUR)


if __name__ == "__main__":
    unittest.main()
