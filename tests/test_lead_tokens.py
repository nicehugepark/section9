"""리드 턴의 토큰 계상 (REQ-20260908-020-62x6).

리드가 손으로 남기는 `s9 note` 에는 훅이 없어 기여 항목의 transcript 가 비고
started 와 ended 가 같은 순간이었다 — 창이 [지금, 지금] 이라 usage 가 0 건이고,
그래서 9월 요청 371건 중 27건에만 토큰이 있었다. 여기서 재는 것 셋:
  ① 리드 항목의 transcript 를 세션 바인딩에서 채우는가,
  ② 창의 앞을 **이 턴의 시작**(마지막 사람 프롬프트)으로 잡는가,
  ③ 한 턴을 두 번 세지 않는가.

원칙은 그대로다 — 모르면 0 이 아니라 없는 채로 둔다.
격리: S9_ROOT=mktemp (모듈 로드 전에 환경을 세운다). 실행: python3 tests/ lead_tokens
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")

# 모듈 상수(ROOT/STATE)가 import 시점에 굳으므로 환경을 먼저 세운다.
_ROOTDIR = tempfile.mkdtemp(prefix="s9leadtok")
os.environ["S9_ROOT"] = _ROOTDIR
os.environ["S9_MACHINE"] = "testbox"
os.environ["S9_SESSION"] = "aaaabbbb"

_spec = importlib.util.spec_from_loader(
    "s9lead", importlib.machinery.SourceFileLoader("s9lead", S9))
s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s9)


def _usage(ts, mid, i, o):
    return {"type": "assistant", "timestamp": ts, "uuid": mid + "-u",
            "message": {"id": mid, "role": "assistant", "usage": {
                "input_tokens": i, "output_tokens": o,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0}}}


def _human(ts, text="사람의 말"):
    return {"type": "user", "timestamp": ts,
            "message": {"role": "user", "content": text}}


def _tool_result(ts):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}


TURN0 = "2026-09-08T00:00:00.000Z"          # 지난 턴의 사람 프롬프트
TURN1 = "2026-09-08T01:00:00.000Z"          # 이 턴의 사람 프롬프트 = 창의 앞
NOW1 = "2026-09-08T10:00:30+09:00"          # = 01:00:30Z
NOW2 = "2026-09-08T10:01:00+09:00"          # = 01:01:00Z
EVENTS = [
    _human(TURN0),
    _usage("2026-09-08T00:00:30.000Z", "m0", 700, 7),    # 지난 턴 — 이 창 밖
    _human(TURN1),
    _usage("2026-09-08T01:00:10.000Z", "m1", 10, 1),     # 노트1 창 안
    _tool_result("2026-09-08T01:00:20.000Z"),            # 사람의 말이 아니다
    _usage("2026-09-08T01:00:40.000Z", "m2", 20, 2),     # 노트2 창 안
]
TOK1 = {"in": 10, "out": 1, "cache_read": 0, "cache_create": 0}
TOK2 = {"in": 20, "out": 2, "cache_read": 0, "cache_create": 0}
BOTH = {"in": 30, "out": 3, "cache_read": 0, "cache_create": 0}
LEAD = "lead:claude-opus-5"


class LeadTokenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="s9leadtx")
        cls.tp = os.path.join(cls.dir, "session.jsonl")
        with open(cls.tp, "w", encoding="utf-8") as f:
            for e in EVENTS:
                f.write(json.dumps(e) + "\n")
        os.makedirs(s9.STATE, exist_ok=True)
        with open(s9.binding_path("testbox", "aaaabbbb"), "w",
                  encoding="utf-8") as f:
            json.dump({"machine": "testbox", "session": "aaaabbbb",
                       "transcript_path": cls.tp}, f)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)
        shutil.rmtree(_ROOTDIR, ignore_errors=True)

    # --- S1
    def test_s1_lead_entry_gets_transcript_and_tokens(self):
        """S1: transcript 가 빈 리드 항목에 바인딩의 경로가 채워지고 토큰이 적힌다."""
        meta = {}
        e = s9.record_contribution(meta, LEAD, item="i1", ts=NOW1)
        self.assertEqual(e["transcript"], self.tp)
        self.assertEqual(e["started"], TURN1)      # 창의 앞 = 이 턴의 시작
        self.assertEqual(e["tokens"], TOK1)        # 지난 턴(m0)은 안 들어온다
        self.assertEqual(meta["tokens"], TOK1)

    # --- S2
    def test_s2_turn_start_is_last_human_prompt(self):
        """S2: 창의 앞은 마지막 **사람** 프롬프트 — tool_result 는 건너뛴다."""
        self.assertEqual(s9.transcript_turn_start(self.tp), TURN1)
        # 뒤에서부터 넓혀 가며 찾는 경로(파일이 한 번에 안 들어오는 경우)도 같은 답
        keep = s9.TURN_TAIL_BYTES
        try:
            s9.TURN_TAIL_BYTES = 64
            self.assertEqual(s9.transcript_turn_start(self.tp), TURN1)
        finally:
            s9.TURN_TAIL_BYTES = keep
        # 사람의 말이 없는 transcript, 없는 파일 → "" (0 이 아니라 없음)
        only_tool = os.path.join(self.dir, "tool.jsonl")
        with open(only_tool, "w", encoding="utf-8") as f:
            f.write(json.dumps(_tool_result(TURN1)) + "\n")
        self.assertEqual(s9.transcript_turn_start(only_tool), "")
        self.assertEqual(s9.transcript_turn_start(self.tp + ".none"), "")

    # --- S3
    def test_s3_two_notes_in_one_turn_do_not_double_count(self):
        """S3: 한 턴에 노트 둘 — 창이 겹치지 않고 머리 합계는 한 턴어치다."""
        meta = {}
        e1 = s9.record_contribution(meta, LEAD, item="i1", ts=NOW1)
        e2 = s9.record_contribution(meta, LEAD, item="i2", ts=NOW2)
        self.assertEqual(e1["tokens"], TOK1)
        self.assertEqual(e2["started"], NOW1)   # 둘째의 앞 = 첫째의 끝
        self.assertEqual(e2["tokens"], TOK2)
        self.assertEqual(meta["tokens"], BOTH)

    # --- S4
    def test_s4_reclose_adds_only_the_increase(self):
        """S4: 같은 actor·item 을 다시 닫으면 늘어난 만큼만 더해진다(회귀)."""
        meta = {}
        s9.record_contribution(meta, LEAD, item="i1", ts=NOW1)
        e = s9.record_contribution(meta, LEAD, item="i1", ts=NOW2)
        self.assertEqual(len(meta["contributions"]), 1)
        self.assertEqual(e["tokens"], BOTH)     # 창이 넓어져 둘 다 들어왔고
        self.assertEqual(meta["tokens"], BOTH)  # 머리는 부풀지 않았다

    # --- S5
    def test_s5_unknown_stays_absent(self):
        """S5: 세션·바인딩·파일을 못 찾으면 아무것도 적지 않는다(0 아님)."""
        keep = os.environ.pop("S9_SESSION")
        try:
            meta = {}
            e = s9.record_contribution(meta, LEAD, item="i1", ts=NOW1)
            self.assertEqual(e["transcript"], "")
            self.assertNotIn("tokens", e)
            self.assertNotIn("tokens", meta)
            self.assertEqual(s9.lead_transcript(), "")
        finally:
            os.environ["S9_SESSION"] = keep
        # 바인딩은 있지만 경로가 사라진 경우도 같다
        self.assertEqual(s9.lead_transcript("nosuchse"), "")

    # --- S6
    def test_s6_subagent_entry_untouched(self):
        """S6: 서브에이전트 항목은 이 경로를 타지 않는다 — 제 파일만 쓴다."""
        meta = {}
        e = s9.record_contribution(meta, "sub:backend-developer:ab33f5f4",
                                   item="i1", ts=NOW1)
        self.assertEqual(e["transcript"], "")
        self.assertNotIn("tokens", e)
        # 명시된 transcript 가 있으면 그 말이 옳다 — 덮어쓰지 않는다
        e2 = s9.record_contribution(meta, LEAD, item="i2",
                                    transcript=self.tp, ts=NOW2, started=NOW1)
        self.assertEqual(e2["transcript"], self.tp)
        self.assertEqual(e2["started"], NOW1)

    # --- S7
    def test_s7_older_entry_window_not_widened_across_turns(self):
        """S7: 지난 턴에 시작된 항목을 지금 닫으며 창을 턴 너머로 넓히지 않는다."""
        meta = {"contributions": [
            {"actor": LEAD, "item": "i1", "started": "2026-09-08T09:00:00+09:00",
             "ended": "2026-09-08T09:00:00+09:00", "result": "running",
             "transcript": ""}]}
        e = s9.record_contribution(meta, LEAD, item="i1", ts=NOW2)
        self.assertEqual(e["started"], "2026-09-08T09:00:00+09:00")
        self.assertEqual(e["transcript"], "")
        self.assertNotIn("tokens", e)
        self.assertNotIn("tokens", meta)


    # --- S8
    def test_s8_hook_turn_note_after_manual_note_does_not_overlap(self):
        """S8: 손 노트 뒤에 Stop 훅이 같은 턴의 보고를 또 붙여도 겹치지 않는다.

        훅은 `--started <턴 시작>` 을 넘기므로 손 노트의 창과 통째로 겹친다 —
        창의 앞을 직전 항목의 끝으로 밀어 한 턴을 한 번만 센다."""
        meta = {}
        s9.record_contribution(meta, LEAD, item="i1", ts=NOW1)   # 손 노트
        e = s9.record_contribution(meta, LEAD, item="[stamp]", result="done",
                                   transcript=self.tp, ts=NOW2, started=TURN1)
        self.assertEqual(e["started"], NOW1)   # 훅이 준 앞이 첫 항목의 끝으로 밀렸다
        self.assertEqual(e["tokens"], TOK2)
        self.assertEqual(meta["tokens"], BOTH)


if __name__ == "__main__":
    unittest.main()
