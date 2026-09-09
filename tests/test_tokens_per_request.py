"""done 요청마다 토큰이 남는가 (REQ-20260909-082-62x6).

9월 done 요청 477건 중 377건에 토큰이 없었다. 원인 셋 — 리드 턴의 토큰이
last_req 하나에만 붙었고, 서브에이전트 기여는 닫히는 running 항목에 토큰을 적지
않은 채 새 항목의 창이 [지금, 지금] 이었으며, 이 세션 밖에서 닫힌 문서는 아무
기록도 없었다. 여기서 재는 것:
  T1  한 턴이 손댄 두 요청이 모두 몫을 받고 합이 보존되는가
  T1b active_reqs 중 이 턴에 갱신된 문서만 몫을 받는가
  T2  손댄 요청이 없으면 primary 하나가 전부를 받는가 / usage 없는 턴은 몫이 없는가
  T3  서브에이전트 transcript 의 usage 가 sub 기여의 tokens 로 남는가
  T4  done 전이에 tokens 가 없으면 History 에 경고 한 줄이 남는가(막지 않는다)
격리: S9_ROOT=mktemp. 실행: python3 tests/ tokens_per_request
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
SID = "c0ffee11"

_ROOTDIR = tempfile.mkdtemp(prefix="s9tokreq")
os.environ["S9_ROOT"] = _ROOTDIR
os.environ["S9_MACHINE"] = "testbox"
os.environ["S9_SESSION"] = SID
os.environ["S9_AUDIT"] = "off"
os.environ.pop("S9_PORT", None)

_spec = importlib.util.spec_from_loader(
    "s9tpr", importlib.machinery.SourceFileLoader("s9tpr", S9))
s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s9)


def _usage(ts, mid, i, o, cr=0, cc=0):
    return {"type": "assistant", "timestamp": ts, "uuid": mid + "-u",
            "message": {"id": mid, "role": "assistant", "usage": {
                "input_tokens": i, "output_tokens": o,
                "cache_read_input_tokens": cr,
                "cache_creation_input_tokens": cc}}}


def _human(ts, text="사람의 말"):
    return {"type": "user", "timestamp": ts,
            "message": {"role": "user", "content": text}}


def _bash(ts, mid, cmd):
    return {"type": "assistant", "timestamp": ts,
            "message": {"id": mid, "role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "t-" + mid,
                 "input": {"command": cmd}}]}}


def _write(path, events):
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


TURN0 = "2026-09-09T00:00:00.000Z"
TURN1 = "2026-09-09T01:00:00.000Z"
END = "2026-09-09T01:05:00.000Z"
TOTAL = {"in": 31, "out": 3, "cache_read": 1000, "cache_create": 7}


class TokensPerRequestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ)
        subprocess.run([S9, "init"], capture_output=True, text=True, env=env,
                       timeout=60, check=True)
        cls.docs = []
        for i in range(3):
            r = subprocess.run(
                [S9, "new", "request", "--title", f"토큰 시험 {i}", "--summary", "s",
                 "--body", "b", "--goal", "토큰이 남는다"],
                capture_output=True, text=True, env=env, timeout=60, check=True)
            cls.docs.append(r.stdout.split()[0].strip())
        cls.dir = tempfile.mkdtemp(prefix="s9tokreqtx")

    def _lead_transcript(self, name, cmds):
        tp = os.path.join(self.dir, name + ".jsonl")
        ev = [_human(TURN0), _usage("2026-09-09T00:00:30.000Z", "m0", 700, 7),
              _human(TURN1),
              _usage("2026-09-09T01:00:10.000Z", "m1", 11, 1, 1000, 7)]
        for k, c in enumerate(cmds):
            ev.append(_bash(f"2026-09-09T01:00:{20 + k:02d}.000Z", f"b{k}", c))
        ev.append(_usage("2026-09-09T01:00:40.000Z", "m2", 20, 2))
        _write(tp, ev)
        return tp

    def test_t1_two_touched_requests_share_and_sum_is_kept(self):
        """T1: `s9 note A`·`s9 status B` 를 부른 턴 — 둘 다 tokens, 합 = 턴의 usage."""
        a, b = self.docs[0], self.docs[1]
        tp = self._lead_transcript("t1", [
            f"S9_SESSION={SID} bin/s9 note {a} --label response '끝'",
            f"cd /x && S9_SESSION={SID} ~/section9/bin/s9 status {b} in-progress --note 착수"])
        plan = s9.plan_turn_tokens(tp, TURN1, END, session=SID, primary=a)
        self.assertEqual(plan["reqs"], [a, b])
        self.assertEqual(plan["total"], TOTAL)
        self.assertEqual(set(plan["shares"]), {a, b})
        summed = None
        for sh in plan["shares"].values():
            summed = s9._tokens_add(summed, sh)
        self.assertEqual(summed, TOTAL, "몫의 합이 턴의 usage 와 같아야 한다")
        # 잔여는 마지막 몫에: in 31 → 15 + 16
        self.assertEqual(plan["shares"][a]["in"], 15)
        self.assertEqual(plan["shares"][b]["in"], 16)
        # 몫을 기여로 적으면 두 문서 모두 tokens 가 있다
        metas = {a: {}, b: {}}
        for rid, m in metas.items():
            s9.record_contribution(m, "lead:claude-x", item="턴", result="done",
                                   ts="2026-09-09T10:05:00+09:00",
                                   tokens=plan["shares"][rid])
            self.assertEqual(m["contributions"][0]["tokens"], plan["shares"][rid])
            self.assertEqual(m["tokens"], plan["shares"][rid])
        self.assertEqual(s9.split_tokens({"in": 0, "out": 0}, 3),
                         [dict.fromkeys(s9.TOKEN_KEYS, 0)] * 3)

    def test_t1b_active_req_counts_only_when_updated_in_this_turn(self):
        """T1b: active_reqs 중 이 턴에 문서가 갱신된 것만 몫을 받는다."""
        a, b, c = self.docs
        tp = self._lead_transcript("t1b", [])
        s9.write_binding({"machine": "testbox", "session": SID, "user": "",
                          "history": [], "last_req": a, "active_reqs": [b, c]})
        for rid, upd in ((b, "2026-09-09T10:03:00+09:00"),     # 창 안(01:03Z)
                         (c, "2026-09-09T08:00:00+09:00")):    # 창 앞(23:00Z 전날)
            p = s9.find_path(rid)
            m, body = s9.read_doc(p)
            m["updated"] = upd
            s9.write_doc(p, m, body)
        plan = s9.plan_turn_tokens(tp, TURN1, END, session=SID, primary=a)
        self.assertEqual(plan["reqs"], [a, b])
        s9.write_binding({"machine": "testbox", "session": SID, "user": "",
                          "history": [], "last_req": "", "active_reqs": []})

    def test_t2_untouched_turn_goes_to_primary_and_no_usage_means_no_share(self):
        """T2: 손댄 요청이 없으면 primary 가 전부; usage 없는 턴은 몫이 없다."""
        a = self.docs[0]
        tp = self._lead_transcript("t2", ["ls -la", "bin/s9 show REQ-20260101-001 --meta"])
        plan = s9.plan_turn_tokens(tp, TURN1, END, session=SID, primary=a)
        self.assertEqual(plan["reqs"], [a])
        self.assertEqual(plan["shares"], {a: TOTAL})
        empty = os.path.join(self.dir, "t2-empty.jsonl")
        _write(empty, [_human(TURN1), _bash("2026-09-09T01:00:20.000Z", "b0",
                                            f"bin/s9 note {a} x")])
        plan = s9.plan_turn_tokens(empty, TURN1, END, session=SID, primary=a)
        self.assertEqual(plan["reqs"], [a])
        self.assertIsNone(plan["total"])
        self.assertEqual(plan["shares"], {})
        self.assertEqual(s9.plan_turn_tokens(tp, "", END, primary=a)["shares"], {})
        self.assertIsNone(s9.parse_tokens_arg(""))
        self.assertIsNone(s9.parse_tokens_arg("not json"))

    def test_t3_subagent_usage_lands_on_the_sub_contribution(self):
        """T3: 서브에이전트 transcript 의 usage 가 지목 REQ 의 sub 기여에 tokens 로."""
        atp = os.path.join(self.dir, "agent.jsonl")
        _write(atp, [
            {"type": "user", "timestamp": "2026-09-09T02:00:00.000Z",
             "message": {"role": "user", "content": "위임 지시"}},
            _usage("2026-09-09T02:00:05.000Z", "s1", 5, 50, 900, 40),
            _usage("2026-09-09T02:00:05.000Z", "s1", 5, 55, 900, 40),   # 같은 응답 되풀이
            _usage("2026-09-09T02:01:00.000Z", "s2", 6, 60, 950, 0),
        ])
        expect = {"in": 11, "out": 115, "cache_read": 1850, "cache_create": 40}
        actor = "sub:backend-developer:abcd1234"
        # 기동 때 PostToolUse 훅이 등록한 running 항목이 있는 경우 (실제 경로)
        meta = {}
        s9.record_contribution(meta, actor, item="082 토큰", result="running",
                               transcript=atp, ts="2026-09-09T10:59:50+09:00")
        s9.record_contribution(meta, actor, item="보고 첫 줄", result="done",
                               transcript=atp, started="2026-09-09T02:00:00.000Z",
                               ts="2026-09-09T11:02:00+09:00")
        rows = meta["contributions"]
        self.assertEqual([r["result"] for r in rows], ["done", "done"])
        with_tok = [r for r in rows if r.get("tokens")]
        self.assertTrue(with_tok, rows)
        self.assertEqual(meta["tokens"], expect)
        # running 등록이 없던 경우(SubagentStop 만 온 경우)도 그대로 남는다
        meta2 = {}
        s9.record_contribution(meta2, actor, item="보고", result="done",
                               transcript=atp, started="2026-09-09T02:00:00.000Z",
                               ts="2026-09-09T11:02:00+09:00")
        self.assertEqual(meta2["contributions"][0]["tokens"], expect)
        self.assertEqual(meta2["tokens"], expect)

    def test_t1c_stop_hook_passes_shares_to_note_and_contrib(self):
        """T1c: Stop 훅이 계획을 받아 primary 는 note --tokens, 나머지는 contrib --tokens."""
        import io
        import sys
        from unittest import mock
        spec = importlib.util.spec_from_loader(
            "s9stop_tpr", importlib.machinery.SourceFileLoader(
                "s9stop_tpr", os.path.join(ROOT, "bin", "s9-audit-response")))
        stop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stop)
        a, b = "REQ-20260909-001-aaaa", "REQ-20260909-002-bbbb"
        share_a, share_b = ({"in": 1, "out": 2, "cache_read": 0, "cache_create": 0},
                            {"in": 1, "out": 3, "cache_read": 0, "cache_create": 0})
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append((argv, inp))

            class R:
                returncode = 0
                stdout = ""
            if argv == ("last", "--active"):
                R.stdout = a
            elif argv == ("bind",):
                R.stdout = "{}"
            elif argv[:2] == ("tokens", "plan"):
                R.stdout = json.dumps({"reqs": [a, b], "total": share_b,
                                       "shares": {a: share_a, b: share_b}})
            return R

        tp = os.path.join(self.dir, "stop.jsonl")
        _write(tp, [_human(TURN1, "해 주세요"),
                    {"type": "assistant", "timestamp": "2026-09-09T01:00:10.000Z",
                     "message": {"model": "opus", "content": [
                         {"type": "text", "text": "`[2026-09-09 10:00:10 KST - 타치코마]` 끝"}]}}])
        data = {"session_id": "c0ffee11deadbeef", "transcript_path": tp, "cwd": ""}
        with mock.patch.object(stop, "run", fake_run), \
                mock.patch.dict(os.environ, {"S9_AUDIT": ""}), \
                mock.patch.object(stop, "mirror_transcript", lambda *x: None), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(data))):
            stop.main()
        notes = [c[0] for c in calls if c[0][0] == "note"]
        self.assertEqual(len(notes), 1, calls)
        self.assertEqual(notes[0][1], a)
        self.assertIn("--tokens", notes[0])
        self.assertEqual(json.loads(notes[0][notes[0].index("--tokens") + 1]), share_a)
        self.assertNotIn("--transcript", notes[0], "몫을 받았으면 창 계산은 건너뛴다")
        contribs = [c[0] for c in calls if c[0][0] == "contrib"]
        self.assertEqual(len(contribs), 1, calls)
        self.assertEqual(contribs[0][1], b)
        self.assertEqual(json.loads(contribs[0][contribs[0].index("--tokens") + 1]), share_b)
        plans = [c[0] for c in calls if c[0][:2] == ("tokens", "plan")]
        self.assertEqual(plans[0][plans[0].index("--primary") + 1], a)

    def test_t4_done_without_tokens_leaves_a_warning_line(self):
        """T4: done 전이 때 tokens 가 없으면 History 에 「tokens 없음」 한 줄 — 막지 않는다."""
        a, b = self.docs[0], self.docs[1]
        s9.do_transition(a, "in-progress", note="착수")
        s9.do_transition(a, "done", note="끝")
        _, body = s9.read_doc(s9.find_path(a))
        warn = [l for l in body.splitlines() if "tokens 없음" in l]
        self.assertEqual(len(warn), 1, body)
        self.assertIn("status: in-progress -> done", body)
        # tokens 가 있으면 그 줄이 없다
        p = s9.find_path(b)
        m, bd = s9.read_doc(p)
        s9.record_contribution(m, "lead:claude-x", item="턴", result="done",
                               ts="2026-09-09T10:05:00+09:00",
                               tokens={"in": 1, "out": 1})
        s9.write_doc(p, m, bd)
        s9.do_transition(b, "in-progress", note="착수")
        s9.do_transition(b, "done", note="끝")
        _, body = s9.read_doc(p)
        self.assertNotIn("tokens 없음", body)


if __name__ == "__main__":
    unittest.main()
