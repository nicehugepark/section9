"""모든 진행이 세워진다 — 세우기가 세 갈래를 안다 (REQ-20260830-035 · 서버 몫).

사용자: "중단하기 버튼이 왜 깨우기 이후에만 뜨는지 모르겠다. 모든 진행중인
작업들은 기본적으로 중단이 가능해야지."

024 의 `stop_request` 는 무인 작업자(pid)만 세울 줄 알았다. 그런데 진행의
주체는 셋이다 — 무인 작업자·세션·위임 에이전트. 세션과 위임은 킬 대상이
아니라 **지시를 전달할 상대**다: 세션에는 interrupt 지시(멈추고 보고 후
클레임 해제), 위임에는 같은 줄에 agent 필드를 실어 리드가 TaskStop 으로
세운다. 아무도 없으면 되살아나지 않게 표시만 세운다.

판정은 `stoppable_verdict` 하나다 — 누름(stop_request)과 그리기
(catalog_with_live)가 같은 함수를 지난다. 두 벌이면 화면이 「세울 수 있다」
그려 놓고 누르면 「세울 수 없다」가 돌아온다.

실행: python3 tests/ stop_branch
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
BOOT = os.path.join(HERE, "..", "bin", "s9-audit-session")
SRC = open(S9_SRC, encoding="utf-8").read()

DOC = "REQ-20260830-990-62x6"


def _load(name, root):
    old = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    # ROOT·STATE 는 import 시점에 굳고 machine 은 부를 때마다 환경에서 읽는다 —
    # env 를 되돌리는 이 격리에서 그 둘이 어긋난다. 바인딩을 훑는 자리가 이
    # 머신 것만 보게 된 뒤로(REQ-20260902-017 `_local_binding_glob`) 그
    # 어긋남이 "아무 바인딩도 없다"가 됐다. env 를 열어 두면 같은 프로세스의
    # 다른 시험까지 물들므로 이 모듈 안에서만 머신을 못박는다.
        m.current_machine = lambda: "TEST"
        return m
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old


def _blk(src, name):
    i = src.find(f"def {name}(")
    assert i > 0, name
    j = src.find("\ndef ", i + 10)
    return src[i:j if j > i else len(src)]


class ThreeWaysToStand(unittest.TestCase):
    """S2~S6 — 세우기가 진행의 주체를 알아본다."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9stopbr-")
        os.makedirs(os.path.join(cls.root, "state", "sessions"))
        cls.m = _load("s9stopbr", cls.root)
        cls.auto = tempfile.mkdtemp(prefix="s9stopbr-auto-")
        cls.m._auto_dir = staticmethod(lambda: cls.auto)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, True)
        shutil.rmtree(cls.auto, True)

    def setUp(self):
        for p in glob.glob(os.path.join(self.root, "state", "sessions",
                                        "*.json")):
            os.remove(p)
        self.m.stop_mark_clear(DOC)
        self.m.locate = lambda _i: "/fake/doc.md"
        self.m.read_doc = lambda _p: ({"id": DOC, "type": "request",
                                       "status": "in-progress"}, "")

    def binding(self, sid, doc=None, agent_doc=None, ended=""):
        """살아 있는(또는 끝난) 세션 바인딩 하나 — 활동 증거는 방금 쓴 파일."""
        tp = os.path.join(self.root, f"tr-{sid}.jsonl")
        with open(tp, "w") as f:
            f.write("x\n")
        b = {"machine": "TEST", "session": sid, "transcript_path": tp,
             "active_reqs": [doc] if doc else [], "ended": ended}
        if agent_doc:
            atp = os.path.join(self.root, f"agent-{sid}.output")
            with open(atp, "w") as f:
                f.write("x\n")
            b["agent_transcript_path"] = [atp]
            b["agent_req"] = {atp: agent_doc}
        with open(os.path.join(self.root, "state", "sessions",
                               f"TEST__{sid}.json"), "w") as f:
            json.dump(b, f)
        return b

    def inbox(self, sid):
        p = self.m.chat_inbox_path(sid)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    # ---- S2. 세션 갈래 ----------------------------------------------------
    def test_s2_a_live_claim_gets_the_instruction(self):
        """세션은 죽이지 않는다 — 지시가 그 수신함에 닿고 표시가 선다."""
        sid = "aabb0002"
        self.binding(sid, doc=DOC)
        r = self.m.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertEqual(r.get("action"), "signaled")
        self.assertTrue(self.m.stop_mark(DOC), "세운 표시가 없다 — 워처가 되살린다")
        lines = self.inbox(sid)
        self.assertTrue(lines, "지시가 수신함에 안 닿았다")
        l = lines[-1]
        self.assertEqual(l.get("kind"), "interrupt")
        self.assertEqual(l.get("req"), DOC)
        for kw in (DOC, "보고", "--release"):
            self.assertIn(kw, l.get("text", ""),
                          f"지시문에 {kw} 가 없다 — 멈추고 보고 후 해제까지가 지시다")

    def test_s2b_the_screen_reads_a_human_sentence(self):
        sid = "aabb0002"
        self.binding(sid, doc=DOC)
        r = self.m.stop_request(DOC, actor="nicehugepark")
        self.assertNotIn("signaled", r.get("message", ""),
                         "액션 낱말이 사람 문장에 샜다")
        self.assertTrue(r.get("message", "").strip())

    # ---- S3. 죽은 세션 ----------------------------------------------------
    def test_s3_a_dead_claim_only_raises_the_mark(self):
        """지시 받을 창이 없으면 세워 두기만 한다 — 화면은 그 문장을 그대로 쓴다."""
        sid = "aabb0003"
        self.binding(sid, doc=DOC, ended="2026-08-30T00:00:00+09:00")
        r = self.m.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertEqual(r.get("action"), "no-recipient")
        # 문장은 REQ-20260901-005 로 개정 — 「세워 두다」 잔재가 「자동
        # 이어받기 끄기」 정책 문법으로 갔다. 고정할 성질은 "사람 문장 + 정책만
        # 걸었다는 사실"이다.
        self.assertIn("지시를 받을 곳이 없어", r.get("message", ""))
        self.assertIn("자동 이어받기", r.get("message", ""))
        self.assertTrue(self.m.stop_mark(DOC))
        self.assertEqual(self.inbox(sid), [], "죽은 수신함에 지시를 넣었다")

    # ---- S4. 위임 갈래 ----------------------------------------------------
    def test_s4_a_delegated_hand_is_relayed_to_the_lead(self):
        """위임은 리드 세션의 자식이다 — 같은 줄에 agent 필드를 실어 보낸다."""
        sid = "aabb0004"
        self.binding(sid, doc=DOC, agent_doc=DOC)   # 클레임+위임 — 위임이 이긴다
        r = self.m.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertEqual(r.get("action"), "relayed")
        lines = self.inbox(sid)
        self.assertTrue(lines, "리드 수신함에 아무것도 안 닿았다")
        l = lines[-1]
        self.assertEqual(l.get("kind"), "interrupt")
        self.assertEqual(l.get("req"), DOC)
        self.assertTrue(l.get("agent"),
                        "agent 필드가 없다 — 리드가 누구를 세울지 모른다")
        self.assertFalse(self.m.stop_mark(DOC),
                         "위임 갈래가 표시를 세웠다 — 세우는 것은 리드의 몫이다")

    # ---- S5. idle 갈래 ----------------------------------------------------
    def test_s5_nobody_home_means_mark_only(self):
        """아무도 없으면 되살아나지 않게 세워 둔다 — 두 번 눌러도 오류가 아니다."""
        r = self.m.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertEqual(r.get("action"), "none")
        self.assertTrue(self.m.stop_mark(DOC), "idle 갈래가 표시를 안 세운다")
        r2 = self.m.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r2.get("ok"), "두 번 누른 것이 오류가 됐다")

    # ---- S6. 감사 ---------------------------------------------------------
    def test_s6_every_branch_is_audited_with_its_kind(self):
        logged = []
        real = self.m._auto_log
        self.m._auto_log = lambda msg: logged.append(msg)
        try:
            self.binding("aabb0006", doc=DOC)
            self.m.stop_request(DOC, actor="nicehugepark")     # session
            self.m.stop_mark_clear(DOC)
            for p in glob.glob(os.path.join(self.root, "state", "sessions",
                                            "*.json")):
                os.remove(p)
            self.m.stop_request(DOC, actor="nicehugepark")     # idle
        finally:
            self.m._auto_log = real
        press = [l for l in logged if "STOP-PRESS" in l]
        self.assertGreaterEqual(len(press), 2, "갈래가 감사를 안 지난다")
        self.assertTrue(all("kind=" in l for l in press),
                        "어느 갈래였는지가 감사에 없다")


class OneVerdictTwoReaders(unittest.TestCase):
    """S7 — 판정 함수는 하나, 읽는 자리가 둘이다."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9stopbrv-")
        os.makedirs(os.path.join(cls.root, "state", "sessions"))
        cls.m = _load("s9stopbrv", cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, True)

    def test_s7_the_verdict_names_all_four_kinds(self):
        v = self.m.stoppable_verdict
        agents = {DOC: {"session": "s1", "agent": "a1", "age": 3}}
        claims = {DOC: {"live": ["s2"], "dead": []}}
        self.assertEqual(v(DOC, worker={"pid": 1}, agents=agents,
                           claims=claims)["kind"], "worker")
        self.assertEqual(v(DOC, agents=agents, claims=claims)["kind"], "agent")
        self.assertEqual(v(DOC, agents={}, claims=claims)["kind"], "session")
        self.assertEqual(v(DOC, agents={}, claims={})["kind"], "idle")
        self.assertEqual(v(DOC, agents={},
                           claims={DOC: {"live": [], "dead": ["s3"]}})["kind"],
                         "idle")

    def test_s7b_both_readers_go_through_the_one_verdict(self):
        cat = _blk(SRC, "catalog_with_live")
        self.assertIn('r["stoppable"]', cat, "행이 갈래를 안 나른다")
        self.assertIn("stoppable_verdict", cat)
        stop = _blk(SRC, "stop_request")
        self.assertIn("stoppable_verdict", stop,
                      "누름이 그리기와 다른 판정을 쓴다")

    def test_s7c_every_in_progress_row_carries_the_kind(self):
        """stoppable 은 파생값이다 — 새 상태 축이 아니라 매 회 계산된다."""
        cat = _blk(SRC, "catalog_with_live")
        m = re.search(r'if r\.get\("status"\) != "in-progress":\s*\n\s*'
                      r'continue[\s\S]*?r\["stoppable"\]', cat)
        self.assertTrue(m, "in-progress 행 루프 안에서 계산되지 않는다")


class TheBootstrapKnows(unittest.TestCase):
    """S8 — 수신 세션이 지목 interrupt 의 뜻을 안다."""

    @classmethod
    def setUpClass(cls):
        cls.boot = open(BOOT, encoding="utf-8").read()

    def test_s8_the_instruction_exists(self):
        self.assertIn("지목한 중단", self.boot,
                      "req 실린 interrupt 의 뜻이 부트스트랩에 없다")
        self.assertIn("클레임을 해제", self.boot)
        self.assertIn("--release", self.boot)

    def test_s8b_the_delegated_half_names_taskstop(self):
        self.assertIn("TaskStop", self.boot,
                      "agent 필드가 실린 interrupt 를 리드가 어떻게 세우는지 없다")


if __name__ == "__main__":
    unittest.main()
