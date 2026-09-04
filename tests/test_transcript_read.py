"""트랜스크립트 판독기 — 한 파일을 보는 눈은 하나다 (REQ-20260901-011).

실사고 2026-09-01 12:37~12:41: fable 한도가 소진된 세션에서 모델·계정 전환이
「지금 이 세션이 일하는 중이라 바꾸지 않았습니다」로 네 번 거부됐다. 한도에
막힌 턴은 트랜스크립트에 합성 assistant 이벤트로 끝나는데
(`model="<synthetic>"` · `stop_reason="stop_sequence"` · `error="rate_limit"`),
게이트(`_transcript_busy`)는 `stop_reason != end_turn` 한 줄로 그것을 「진행
중」이라 읽었다. 같은 파일을 읽는 이웃 둘은 이미 알고 있었다 —
`session_model` 은 합성 표기를 건너뛰고, `stream_end_info` 는 꼬리 서명을
「사용 한도 소진」이라 부른다. **게이트만 낡았다.**

뿌리는 판정 로직이 아니라 **공유 판독기가 없다**는 것이었다. 그래서 이 파일이
지키는 계약은 둘이다: ① 판독 결과가 맞다 ② 판독하는 자리가 하나뿐이다.

실행: python3 tests/ transcript_read
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9tread-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_tread", importlib.machinery.SourceFileLoader("s9_mod_tread", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def write(entries, name):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return path


def asst(stop="end_turn", model="claude-fable-5", text="x", **kv):
    return {"type": "assistant",
            "message": {"stop_reason": stop, "model": model,
                        "content": [{"type": "text", "text": text}]}, **kv}


def user(text="해 줘"):
    return {"type": "user", "message": {"content": text}}


# 실측 원문 그대로 (a8186437, 2026-09-01 03:37:05Z)
LIMIT_TEXT = ("You've reached your Fable 5 limit. "
              "Run /usage-credits to continue or switch models with /model.")


def limit_event():
    return asst(stop="stop_sequence", model="<synthetic>", text=LIMIT_TEXT,
                error="rate_limit", apiErrorStatus=429, isApiErrorMessage=True)


class WhatTheReaderSees(unittest.TestCase):
    """① 판독 결과가 맞다."""

    # S1. 정상: 끝난 턴은 끝난 턴이다
    def test_what_the_reader_sees(self):
        """① 판독 결과가 맞다."""
        with self.subTest("s1_finished_turn_is_idle"):
                st = mod.transcript_read(write([user(), asst("end_turn")], "s1.jsonl"))
                self.assertTrue(st["ok"])
                self.assertFalse(st["busy"])
                self.assertFalse(st["limit"])
                self.assertEqual(st["model"], "claude-fable-5")

            # S2. 진행 중: 도구를 부르는 중이거나 사용자 턴이 마지막이면 busy
        with self.subTest("s2_running_turn_is_busy"):
                self.assertTrue(mod.transcript_read(
                    write([asst("tool_use")], "s2a.jsonl"))["busy"])
                self.assertTrue(mod.transcript_read(
                    write([asst("end_turn"), user()], "s2b.jsonl"))["busy"])
                # 직전 중단 직후의 사용자 턴은 아무도 응답하지 않는다
                self.assertFalse(mod.transcript_read(write(
                    [asst("end_turn"), user("[Request interrupted by user]")],
                    "s2c.jsonl"))["busy"])
                # 블록 목록으로 들어온 같은 말도 같게 읽는다
                self.assertFalse(mod.transcript_read(write(
                    [{"type": "user", "message": {"content": [
                        {"type": "text", "text": "[Request interrupted by user]"}]}}],
                    "s2d.jsonl"))["busy"])

            # S3. 한도(핵심 회귀): 한도로 굳은 턴은 **도는 턴이 아니다**
        with self.subTest("s3_limit_is_not_busy"):
                st = mod.transcript_read(write(
                    [user(), limit_event()], "s3.jsonl"))
                self.assertFalse(st["busy"], "한도로 굳은 턴이 다시 '진행 중'으로 읽힌다")
                self.assertTrue(st["limit"])
                self.assertTrue(st["limit_seen"])
                self.assertEqual(st["limit_model"], "Fable 5")
                # 사람이 네 번 시도하면 같은 줄이 네 번 쌓인다 — 판정은 그대로다
                st4 = mod.transcript_read(write(
                    [user()] + [limit_event()] * 4, "s3b.jsonl"))
                self.assertFalse(st4["busy"])
                self.assertTrue(st4["limit"])

            # S4. 서명 다중화: 문구 하나에만 기대지 않는다
        with self.subTest("s4_signatures_are_plural"):
                # 문구가 바뀌어도 에러 표식이 남으면 한도다
                st = mod.transcript_read(write([asst(
                    stop="stop_sequence", model="<synthetic>", text="다른 문구",
                    error="rate_limit")], "s4a.jsonl"))
                self.assertTrue(st["limit"])
                # 에러 표식이 없어도 문구가 있으면 한도다
                st = mod.transcript_read(write([asst(
                    stop="stop_sequence", model="<synthetic>",
                    text=LIMIT_TEXT)], "s4b.jsonl"))
                self.assertTrue(st["limit"])
                # 429 만 있어도 한도다
                st = mod.transcript_read(write([asst(
                    stop="stop_sequence", model="<synthetic>", text="",
                    apiErrorStatus=429)], "s4c.jsonl"))
                self.assertTrue(st["limit"])

            # S5. 판정 불가는 신호를 안 보내는 쪽으로 — 여기서 예외가 나면 안 된다
        with self.subTest("s5_unreadable_is_quiet"):
                for p in ("", "/no/such/file.jsonl",
                          write([], "s5-empty.jsonl")):
                    st = mod.transcript_read(p)
                    self.assertFalse(st["busy"])
                    self.assertFalse(st["limit"])
                broken = os.path.join(TMP, "s5-broken.jsonl")
                with open(broken, "w", encoding="utf-8") as f:
                    f.write('{"type": 깨진 줄\n')
                self.assertFalse(mod.transcript_read(broken)["busy"])

            # S7. 이웃 계약 보존: 상태줄의 모델과 끝난 사유는 그대로다
        with self.subTest("s7_neighbours_unchanged"):
                tp = write([asst("end_turn", "claude-opus-5"), limit_event()],
                           "s7.jsonl")
                # 합성 표기는 모델이 아니다 (REQ-082 · 기존 R15)
                self.assertEqual(mod.session_model({"transcript_path": tp}),
                                 "claude-opus-5")
                # 끝난 사유는 여전히 판별된다 (REQ-20260901-006)
                self.assertTrue(mod.transcript_read(tp)["limit_seen"])

            # 캐시가 판정을 굳히지 않는다 — 파일이 바뀌면 답도 바뀐다
        with self.subTest("cache_follows_the_file"):
            p = os.path.join(TMP, "cache.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps(asst("tool_use")) + "\n")
            self.assertTrue(mod.transcript_read(p)["busy"])
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(asst("end_turn")) + "\n")
            self.assertFalse(mod.transcript_read(p)["busy"])

class WhereTheReadingLives(unittest.TestCase):
    """② 판독하는 자리가 하나뿐이다 — 이 감시가 다음 '게이트만 낡음'을 막는다."""

    @classmethod
    def setUpClass(cls):
        with open(S9, encoding="utf-8") as f:
            cls.src = f.read()

    # S6. 세 함수가 같은 판독기를 부른다
    def test_s6_three_callers_share_one_reader(self):
        for fn in ("_transcript_busy", "session_model", "stream_end_info"):
            m = re.search(r"( *)def %s\(" % fn, self.src)
            self.assertTrue(m, f"{fn} 를 못 찾았다 — 감시가 눈을 잃었다")
            # 다음 같은 깊이의 def 까지가 그 함수의 몸이다
            rest = self.src[m.end():]
            nxt = re.search(r"\n%sdef " % m.group(1), rest)
            body = rest[:nxt.start()] if nxt else rest
            self.assertIn("transcript_read(", body,
                          f"{fn} 가 판독기를 안 쓴다 — 손으로 다시 파싱하면 "
                          f"한 곳만 고쳐지는 그 결함이 돌아온다")

    # S6(b). 합성·한도 서명이 판독기 밖에 중복 정의되지 않는다
    def test_s6b_signature_defined_once(self):
        self.assertEqual(self.src.count('"reached your" in'), 2,
                         "한도 서명 검사가 판독기 밖에 또 있다")
        self.assertEqual(self.src.count('startswith("<")'), 2,
                         "합성 표기 검사가 판독기 밖에 또 있다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
