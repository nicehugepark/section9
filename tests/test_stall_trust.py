"""멈춤이 일하는 손을 못 본다 (REQ-20260829-036-62x6).

사용자(20:33): "멈춤으로 나오는건 진짜인가? 신뢰경험이 아직인것같다."

실측으로 밝힌 원인은 "등록을 안 한다"가 아니라 **엉뚱한 문서에 등록한다** 였다.
세션 로그 SES-20260829-027 136행:

    20:09:58 위임 등록: REQ-20260829-029-62x6 ← sub:designer:a848238e (클레임)

그런데 그 기여의 항목 이름이 `"030·031 화면 몫"` 이다 — designer 는 030·031 을
하고 있었고 기록만 029 로 갔다. `s9-audit-agent` 가 정식 id 정규식만 보기 때문에
description 의 `030·031` 은 하나도 안 잡혔고, prompt 에 배경으로 실린 정식 id 는
여럿이라 "유일하지 않으면 고르지 않는다" 규칙에 걸려 클레임 경로로 물러났다.

한 원인이 사고 둘을 낳았다:
  · 030 은 손이 안 보여 **거짓 멈춤** 이 됐고, 20:34 깨우기가 designer 가
    `web/index.html` 을 쓰는 중에 무인 작업자를 하나 더 띄웠다.
  · 029 는 **없는 손이 보여** 진짜 멈춤이 가려졌다.

그래서 이 시험이 붙잡는 것은 두 겹이다. ① 지명이 제대로 풀리는가(그쪽은
test_delegation_target 이 함께 본다) ② **지명이 못 풀렸을 때 그 사실이
숨겨지지 않는가** — 추정으로 붙인 위임은 추정이라고 적히고, 미상의 손이
살아 있는 동안에는 '멈춤' 대신 '미상' 이라 말하며 겹쳐 띄우지 않는다.

판정은 한 자리다: `stall_verdict()` 하나를 화면(`catalog_with_live`) ·
CLI(`stalled_requests`) · 깨우기(`wake_request`) 셋이 함께 먹는다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ stall_trust
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(root):
    """bin/s9 를 이 임시 루트에 물려 모듈로 연다 — ROOT 는 import 시점에 굳는다."""
    os.environ["S9_ROOT"] = root
    spec = importlib.util.spec_from_loader(
        "s9trust", importlib.machinery.SourceFileLoader("s9trust", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.current_machine = lambda: "testbox"   # 바인딩은 이 머신 것만 (REQ-20260902-017)
    return m


class StallTrust(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9trust-")
        cls.prev_root = os.environ.get("S9_ROOT")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        # A 조용한 것 · B 위임이 붙어 있는 것 · C 대기 표식이 붙은 것
        cls.A = cls.mkreq("아무도 없는 것")
        cls.B = cls.mkreq("위임이 붙은 것")
        cls.C = cls.mkreq("차례를 기다리는 것")
        for rid in (cls.A, cls.B, cls.C):
            cls.cli("status", rid, "in-progress", "--note", "t",
                    sess="lead1234")
            cls.backdate(rid, 3600)
        cls.cli("index", "rebuild")
        cls.m = _load(cls.root)

    @classmethod
    def tearDownClass(cls):
        if cls.prev_root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = cls.prev_root
        shutil.rmtree(cls.root, ignore_errors=True)

    # ---- 도구 -----------------------------------------------------------
    @classmethod
    def cli(cls, *argv, sess=None):
        env = dict(cls.env)
        if sess:
            env["S9_SESSION"] = sess
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, timeout=60, stdin=subprocess.DEVNULL)
        assert r.returncode == 0, f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}"
        return r.stdout.strip()

    @classmethod
    def mkreq(cls, title):
        return cls.cli("new", "request", "--title", title, "--summary", "s",
                       "--goal", "g", "--size", "S", "--user", "alice",
                       "--body", "x").split()[0]

    @classmethod
    def docpath(cls, rid):
        for dp, _dn, fns in os.walk(os.path.join(cls.root, "vault")):
            for fn in fns:
                if fn.startswith(rid) and fn.endswith(".md"):
                    return os.path.join(dp, fn)
        raise AssertionError(f"문서 없음: {rid}")

    @classmethod
    def backdate(cls, rid, secs):
        """문서를 과거로 — 멈춤의 시계는 updated 다."""
        ts = (datetime.datetime.now().astimezone()
              - datetime.timedelta(seconds=secs)).isoformat(timespec="seconds")
        q = cls.docpath(rid)
        t = open(q, encoding="utf-8").read()
        t = "\n".join((f"status_since: {ts}" if ln.startswith("status_since:")
                       else f"updated: {ts}" if ln.startswith("updated:")
                       else ln) for ln in t.splitlines()) + "\n"
        open(q, "w", encoding="utf-8").write(t)

    def row(self, rid):
        r = next((x for x in self.m.load_catalog() if x.get("id") == rid), None)
        self.assertIsNotNone(r, f"색인에 {rid} 가 없다")
        return r

    def live_row(self, rid):
        r = next((x for x in self.m.catalog_with_live() if x.get("id") == rid),
                 None)
        self.assertIsNotNone(r, f"색인에 {rid} 가 없다")
        return r

    def verdict(self, rid, now=None):
        return self.m.stall_verdict(self.row(rid), now or time.time(),
                                    self.m.STALLED_WIN)

    def hand(self, session, req=None, age=0.0, ended=""):
        """이 세션에 서브에이전트 손 하나를 붙인다. req=None 이면 미상."""
        d = os.path.join(self.root, "tasks")
        os.makedirs(d, exist_ok=True)
        tp = os.path.join(d, f"{session}-{len(os.listdir(d))}.output")
        open(tp, "w", encoding="utf-8").write("working\n")
        t = time.time() - age
        os.utime(tp, (t, t))
        p = os.path.join(self.root, "state", "sessions",
                         f"testbox__{session}.json")
        try:
            with open(p, encoding="utf-8") as f:
                b = json.load(f)
        except (OSError, ValueError):
            b = {"machine": "testbox", "session": session, "user": "alice",
                 "history": []}
        b["ended"] = ended
        b["agent_transcript_path"] = list(
            b.get("agent_transcript_path") or []) + [tp]
        m = dict(b.get("agent_req") or {})
        m[tp] = req or ""
        b["agent_req"] = m
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f)
        return tp

    def strip_agent_req(self, session):
        """`agent_req` 를 통째로 걷어 옛 바인딩 모양을 만든다."""
        p = os.path.join(self.root, "state", "sessions",
                         f"testbox__{session}.json")
        with open(p, encoding="utf-8") as f:
            b = json.load(f)
        b.pop("agent_req", None)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f)

    def clear_hands(self, session):
        p = os.path.join(self.root, "state", "sessions",
                         f"testbox__{session}.json")
        try:
            with open(p, encoding="utf-8") as f:
                b = json.load(f)
        except (OSError, ValueError):
            return
        b["agent_transcript_path"] = []
        b["agent_req"] = {}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f)

    # ---- C7. 회귀: 진짜 멈춤은 여전히 멈춤이다 ---------------------------
    def test_stall_trust(self):
        """StallTrust 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("c7_real_stall_still_stalls"):
            self.clear_hands("lead1234")
            v = self.verdict(self.A)
            self.assertEqual(v["state"], "stalled", v)
            self.assertGreaterEqual(v["mins"], 15)
            self.assertEqual(self.m.stall_mins(self.row(self.A), time.time(),
                                               self.m.STALLED_WIN), v["mins"],
                             "stall_mins 가 stall_verdict 와 다른 답을 낸다 — "
                             "판정이 두 벌이면 한 벌만 고쳐진다")
        with self.subTest("c7b_live_delegation_is_attached"):
                self.clear_hands("lead1234")
                self.cli("note", self.B, "붙었다", "--agent", "sub:designer:aaaa1111",
                         "--item", "화면", "--result", "running", sess="lead1234")
                self.backdate(self.B, 3600)
                self.cli("index", "rebuild")
                try:
                    v = self.verdict(self.B)
                    self.assertEqual(v["state"], "attached", v)
                    self.assertIsNone(v["mins"])
                finally:
                    pass

            # ---- C8. 도는 워커는 멈춤을 이긴다 (REQ-20260830-009) ----------------
        with self.subTest("c8_a_running_worker_beats_the_stall_clock"):
                self.clear_hands("lead1234")
                r = dict(self.row(self.A))
                base = self.m.stall_verdict(r, time.time(), self.m.STALLED_WIN)
                self.assertEqual(base["state"], "stalled",
                                 "밑그림이 멈춤이 아니면 이 시험은 아무것도 안 잡는다")

                r["live_kind"] = "direct"          # 워커가 문서를 집어 덮인 뒤
                r["worker"] = {"pid": 179646, "age": 80}
                v = self.m.stall_verdict(r, time.time(), self.m.STALLED_WIN)
                self.assertEqual(v["state"], "moving", v)
                self.assertIsNone(v["mins"],
                                  "도는 동안에는 깨울 분(minutes)을 주지 않는다")
                self.assertIsNotNone(v["quiet_mins"],
                                     "조용한 시간까지 감추면 반대편 병이다")

            # ---- C2. 추정으로 붙인 손은 추정이라고 적힌다 ------------------------
        with self.subTest("c2_guessed_hand_is_unassigned"):
            self.clear_hands("lead1234")
            self.hand("lead1234", req=None, age=5)
            hands = self.m.unassigned_hands()
            self.assertEqual([h["session"] for h in hands], ["lead1234"],
                             f"미상의 손이 목록에 없다: {hands}")
        with self.subTest("c2b_named_hand_is_not_unassigned"):
            self.clear_hands("lead1234")
            self.hand("lead1234", req=self.A, age=5)
            self.assertEqual(self.m.unassigned_hands(), [],
                             "지명으로 붙인 손까지 미상으로 세면 깨우기가 영영 "
                             "막힌다 — 확정과 추정은 구별돼야 한다")
        with self.subTest("c2d_legacy_hand_is_traced_through_the_document"):
            self.clear_hands("lead1234")
            tp = self.hand("lead1234", req=None, age=5)
            self.strip_agent_req("lead1234")       # 옛 바인딩 모양으로 되돌린다
            self.assertTrue(self.m.unassigned_hands(),
                            "되짚을 문서가 없는데 손이 안 세어졌다")
            self.cli("note", self.B, "옛 손", "--agent", "sub:designer:bbbb2222",
                     "--item", "화면", "--result", "running", "--transcript", tp,
                     sess="lead1234")
            self.cli("index", "rebuild")
            self.assertEqual(self.m.unassigned_hands(), [],
                             "문서가 이 손의 자리를 말하는데도 미상으로 센다")
        with self.subTest("c2e_a_guess_stays_a_guess_even_with_a_document"):
            self.clear_hands("lead1234")
            tp = self.hand("lead1234", req=None, age=5)   # req="" — 명시적 추정
            self.cli("note", self.B, "추정으로 붙은 손", "--agent",
                     "sub:designer:cccc3333", "--item", "화면", "--result",
                     "running", "--transcript", tp, sess="lead1234")
            self.cli("index", "rebuild")
            self.assertTrue(self.m.unassigned_hands(),
                            "추정이 문서 한 줄로 확정이 됐다")
        with self.subTest("c2f_named_fresh_hand_is_attached"):
            self.clear_hands("lead1234")
            self.hand("lead1234", req=self.A, age=5)
            try:
                v = self.verdict(self.A)
                self.assertEqual(v["state"], "attached", v)
                self.assertEqual(self.live_row(self.A).get("stall_state"),
                                 "attached", "화면 경로가 단독 판정과 다른 답을 낸다")
            finally:
                self.clear_hands("lead1234")
        with self.subTest("c2c_stale_hand_is_not_counted"):
                self.clear_hands("lead1234")
                self.hand("lead1234", req=None, age=self.m.AGENT_FRESH_SEC + 60)
                self.assertEqual(self.m.unassigned_hands(), [])

            # ---- C3. 미상의 손이 있으면 '멈춤' 이 아니라 '미상' -------------------
        with self.subTest("c3_unknown_hand_blocks_the_stall_label"):
            self.clear_hands("lead1234")
            self.hand("lead1234", req=None, age=5)
            v = self.verdict(self.A)
            self.assertEqual(v["state"], "unknown", v)
            self.assertIsNone(self.m.stall_mins(self.row(self.A), time.time(),
                                                self.m.STALLED_WIN),
                              "일하는 손이 있을 수 있는데 '멈춤' 으로 그린다 — "
                              "그 카드의 깨우기가 곧 두 번째 손이다")
            self.assertGreaterEqual(v["quiet_mins"], 15,
                                    "조용한 시간까지 숨기면 안 된다 — 숨기는 것은 "
                                    "'한 일 없이 경보만 꺼진다' 의 반대편 병이다")
        with self.subTest("c3b_cli_and_screen_agree"):
                self.clear_hands("lead1234")
                self.addCleanup(self.clear_hands, "orph9876")
                self.hand("orph9876", req=None, age=5)
                ids = [r["id"] for r in self.m.stalled_requests()]
                self.assertNotIn(self.A, ids,
                                 "CLI 는 '멈췄다' 는데 화면은 '미상' 이다")
                row = self.live_row(self.A)
                self.assertEqual(row.get("stall_state"), "unknown", row)
                self.assertIsNone(row.get("stalled_mins"))

            # ---- C4. 겹쳐 띄우지 않는다 ------------------------------------------
        with self.subTest("c4_wake_refuses_while_a_hand_may_be_attached"):
                # 미상의 손은 클레임 없는 세션에 — c3b 개정(REQ-20260831-005)과 같다.
                self.clear_hands("lead1234")
                self.addCleanup(self.clear_hands, "orph9876")
                self.hand("orph9876", req=None, age=5)
                res = self.m.wake_request(self.A, actor="tester")
                self.assertFalse(res["ok"], res)
                self.assertEqual(res["action"], "unknown", res)
                self.assertTrue(res["message"].strip(),
                                "거부만 주고 이유를 안 주면 사람은 버튼이 고장 났다고 읽는다")

            # ---- C5. 대기는 멈춤이 아니다 ----------------------------------------
        with self.subTest("c5_waiting_is_carried_on_the_row"):
            self.clear_hands("lead1234")
            self.m._wait_mark(self.C, "held",
                              "REQ-20260829-024-62x6 가 bin/s9 를 잡고 있다",
                              since=time.time() - 600)
            try:
                v = self.verdict(self.C)
                self.assertEqual(v["state"], "waiting", v)
                self.assertIsNone(self.m.stall_mins(self.row(self.C), time.time(),
                                                    self.m.STALLED_WIN))
                row = self.live_row(self.C)
                self.assertEqual(row.get("stall_state"), "waiting", row)
                self.assertEqual(row.get("wait_kind"), "held", row)
                self.assertIn("bin/s9", row.get("wait_why") or "")
                self.assertGreaterEqual(row.get("wait_mins") or 0, 9)
                self.assertGreaterEqual(row.get("quiet_mins") or 0, 15)
            finally:
                self.m._wait_clear(self.C)
        with self.subTest("c5b_wake_says_it_is_a_queue_not_a_stall"):
                self.clear_hands("lead1234")
                self.m._wait_mark(self.C, "held", "REQ-x 가 bin/s9 를 잡고 있다",
                                  since=time.time() - 600)
                try:
                    res = self.m.wake_request(self.C, actor="tester")
                    self.assertFalse(res["ok"], res)
                    self.assertEqual(res["action"], "waiting", res)
                finally:
                    self.m._wait_clear(self.C)

            # ---- C6. 판정이 사는 자리는 하나다 -----------------------------------
        with self.subTest("c6_single_verdict_function"):
            src = open(S9, encoding="utf-8").read()
            self.assertIn("def stall_verdict(", src)
            # stall_mins 는 그 함수의 얇은 껍데기여야 한다 — 나이를 다시 재면
            # 두 벌이 된다.
            i = src.index("def stall_mins(")
            body = src[i:src.index("\ndef ", i + 10)]
            self.assertRegex(body, r"\n\s*return stall_verdict\(",
                             "stall_mins 가 판정을 따로 갖고 있다")

if __name__ == "__main__":
    unittest.main()
