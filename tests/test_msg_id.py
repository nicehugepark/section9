"""한 응답을 무엇으로 가르는가 — 판정은 한 곳이다 (REQ-20260907-051).

Claude 의 jsonl 은 응답 하나를 content block 마다 한 줄로 쓰고 줄마다 같은
usage 를 되풀이한다. 그래서 토큰을 셀 때 같은 응답은 한 번만 센다.

같은 규칙이 두 자리(`agent_file_stats` · `transcript_usage`)에 따로 적혀 있었고
**한 벌만 틀렸다** — `mid = … or ""` 가 초기값과 맞아떨어져 id 없는 이벤트가
첫 줄부터 통째로 안 세어졌다(에이전트 띠의 토큰 0, REQ-20260907-050).

고정하는 계약 셋.
1. 판정은 `event_msg_id` 하나다.
2. **id 가 없으면 아무와도 묶지 않는다** — 묶을 근거가 없으면 묶지 않는다.
3. 같은 id 의 되풀이는 한 번만 센다.

실행: python3 tests/ msg_id
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-msgid-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_msgid", importlib.machinery.SourceFileLoader("s9_mod_msgid", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class WhichAnswerIsThisLine(unittest.TestCase):
    def test_message_id_wins(self):
        self.assertEqual(mod.event_msg_id({"message": {"id": "m1"}, "uuid": "u1"}), "m1")

    def test_uuid_is_the_fallback(self):
        self.assertEqual(mod.event_msg_id({"uuid": "u1"}), "u1")

    def test_no_id_is_empty_not_a_guess(self):
        """timestamp 로 물러나지 않는다 — 그건 「같다」의 근거가 못 된다."""
        self.assertEqual(mod.event_msg_id({"timestamp": "2026-09-07T00:00:00+09:00"}), "")
        self.assertEqual(mod.event_msg_id({}), "")
        self.assertEqual(mod.event_msg_id({"message": {}}), "")


class IdlessLinesAreNeverMerged(unittest.TestCase):
    """묶을 근거가 없으면 묶지 않는다 — 겹쳐 세는 것보다 빠뜨리는 것이 나쁘다."""

    def _usage(self, out):
        return {"output_tokens": out, "input_tokens": 0}

    def _write(self, rows):
        p = os.path.join(TMP, f"t{len(rows)}-{id(rows)}.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p

    def test_two_idless_lines_at_the_same_time_both_count(self):
        ts = "2026-09-07T12:00:00+09:00"
        p = self._write([
            {"timestamp": ts, "message": {"usage": self._usage(10)}},
            {"timestamp": ts, "message": {"usage": self._usage(7)}},
        ])
        got = mod.transcript_usage(p, ts, "2026-09-07T12:00:01+09:00")
        self.assertIsNotNone(got, "usage 를 하나도 못 읽었다")
        self.assertEqual(got["out"], 17,
                         "같은 시각의 id 없는 두 줄이 한 칸에 겹쳐 하나가 사라졌다")

    def test_repeats_of_one_answer_count_once(self):
        ts = "2026-09-07T12:00:00+09:00"
        p = self._write([
            {"timestamp": ts, "message": {"id": "m1", "usage": self._usage(10)}},
            {"timestamp": ts, "message": {"id": "m1", "usage": self._usage(10)}},
            {"timestamp": ts, "message": {"id": "m1", "usage": self._usage(10)}},
        ])
        got = mod.transcript_usage(p, ts, "2026-09-07T12:00:01+09:00")
        self.assertEqual(got["out"], 10, "한 응답을 세 번 셌다")


class OneRuleNotTwo(unittest.TestCase):
    def test_both_readers_share_the_judgement(self):
        """두 자리가 같은 함수를 쓴다 — 두 벌이면 한 벌만 고쳐진다.

        소스 글자를 대조하지 않는다(DOC-20260907-002): 판정 함수를 잠깐
        바꿔치기하고, 두 자리가 **모두** 그 바뀐 답을 따르는지 본다.
        """
        called = []
        real = mod.event_msg_id
        mod.event_msg_id = lambda ev: (called.append(1), real(ev))[1]
        try:
            ts = "2026-09-07T12:00:00+09:00"
            p = os.path.join(TMP, "shared.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": ts,
                                    "message": {"id": "m1",
                                                "usage": {"output_tokens": 5,
                                                          "input_tokens": 0}}}) + "\n")
            mod.transcript_usage(p, ts, "2026-09-07T12:00:01+09:00")
        finally:
            mod.event_msg_id = real
        self.assertTrue(called, "transcript_usage 가 공용 판정을 안 쓴다")


if __name__ == "__main__":
    unittest.main()
