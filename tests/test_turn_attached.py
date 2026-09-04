"""긴 턴이 멈춤으로 보인다 (REQ-20260831-005-62x6).

실사고 2026-08-31 13:14: 리드 세션 38ad98c8 이 REQ-003·004 를 active_reqs 로
클레임하고 12:51부터 도구 호출로 연속 작업 중이었는데, 보드는 두 카드를
「멈춤 17분째 진전 없음」으로 그렸다.

실측으로 밝힌 근원은 REQ 문서의 가설("긴 턴 동안 스트림이 끊긴다")이 아니다 —
transcript 는 도구 호출마다 자라고, `catalog_with_live` 는 그 mtime 으로
`live_kind == "direct"`(클레임 + 2분 내 활동)를 **이미** 계산해 행에 싣는다.
13:18 재현: 같은 행이 live=True · live_age=1 인데 stall_state=stalled 였다.
즉 판정(`stall_verdict`)이 자기 행에 실린 직접 증거를 안 먹었다.

수정은 판정 한 곳에 기존 신호를 입력으로 추가한 것뿐이다 (DOC-20260830-003
"새 신호는 새 함수가 아니라 새 입력이다"): direct 면 stalled 대신 attached —
moving 승격은 금지(C2 — 진전의 시계는 문서 updated 하나), quiet_mins 는
그대로 낸다(감추지 않는다). 간접(session)은 클레임이 아니라서 제외한다
(근원 B — 귀속은 선언으로). 손 뗀 클레임은 claim_dead(30분 유예)가 끊어
direct 가 저절로 꺼진다 — REQ-20260827-074 의 과녁은 그대로 맞는다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ turn_attached
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
    os.environ["S9_ROOT"] = root
    spec = importlib.util.spec_from_loader(
        "s9turnatt", importlib.machinery.SourceFileLoader("s9turnatt", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TurnAttached(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9turnatt-")
        cls.prev_root = os.environ.get("S9_ROOT")
        # **이 프로세스의 머신 이름도 testbox 여야 한다** (REQ-20260902-052).
        # 바인딩 파일은 `testbox__<sid>.json` 인데 모듈이 직접 부르는
        # `catalog_with_live` 는 os.environ 의 머신 이름으로 자리를 찾는다.
        # subprocess 봉투에만 심어 두면 스위트 전체를 돌 때 **앞 시험이 흘린
        # 값** 덕에 우연히 초록이고, 단독으로 돌리면 붉다 — 실제로 그랬다.
        cls.prev_machine = os.environ.get("S9_MACHINE")
        os.environ["S9_MACHINE"] = "testbox"
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        # A 클레임+활동(사고 재현) · B 간접 세션 · C 활동 끊긴 클레임 · D 방금 갱신
        cls.A = cls.mkreq("직접 작업 중인 것")
        cls.B = cls.mkreq("간접 세션의 것", sess="side5678")
        cls.C = cls.mkreq("손 뗀 클레임")
        cls.D = cls.mkreq("방금 움직인 것")
        for rid in (cls.A, cls.B, cls.C, cls.D):
            cls.cli("status", rid, "in-progress", "--note", "t")
        for rid in (cls.A, cls.B, cls.C):
            cls.backdate(rid, 3600)
        cls.cli("index", "rebuild")
        cls.m = _load(cls.root)

    @classmethod
    def tearDownClass(cls):
        if cls.prev_root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = cls.prev_root
        if cls.prev_machine is None:
            os.environ.pop("S9_MACHINE", None)
        else:
            os.environ["S9_MACHINE"] = cls.prev_machine
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
    def mkreq(cls, title, sess=None):
        return cls.cli("new", "request", "--title", title, "--summary", "s",
                       "--goal", "g", "--size", "S", "--user", "alice",
                       "--body", "x", sess=sess).split()[0]

    @classmethod
    def docpath(cls, rid):
        for dp, _dn, fns in os.walk(os.path.join(cls.root, "vault")):
            for fn in fns:
                if fn.startswith(rid) and fn.endswith(".md"):
                    return os.path.join(dp, fn)
        raise AssertionError(f"문서 없음: {rid}")

    @classmethod
    def backdate(cls, rid, secs):
        ts = (datetime.datetime.now().astimezone()
              - datetime.timedelta(seconds=secs)).isoformat(timespec="seconds")
        q = cls.docpath(rid)
        t = open(q, encoding="utf-8").read()
        t = "\n".join((f"status_since: {ts}" if ln.startswith("status_since:")
                       else f"updated: {ts}" if ln.startswith("updated:")
                       else ln) for ln in t.splitlines()) + "\n"
        open(q, "w", encoding="utf-8").write(t)

    def bind(self, session, reqs=(), transcript_age=None):
        """세션 바인딩 하나 — reqs 를 클레임하고 transcript mtime 을 심는다."""
        p = os.path.join(self.root, "state", "sessions",
                         f"testbox__{session}.json")
        b = {"machine": "testbox", "session": session, "user": "alice",
             "history": [], "ended": ""}
        if reqs:
            now_iso = datetime.datetime.now().astimezone().isoformat(
                timespec="seconds")
            b["active_reqs"] = list(reqs)
            b["claim_at"] = {r: now_iso for r in reqs}
        if transcript_age is not None:
            tp = os.path.join(self.root, "state", f"tr-{session}.jsonl")
            open(tp, "w", encoding="utf-8").write("{}\n")
            t = time.time() - transcript_age
            os.utime(tp, (t, t))
            b["transcript_path"] = tp
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f)
        self.addCleanup(os.remove, p)
        return p

    def live_row(self, rid):
        r = next((x for x in self.m.catalog_with_live() if x.get("id") == rid),
                 None)
        self.assertIsNotNone(r, f"색인에 {rid} 가 없다")
        return r

    # ---- S1. 사고 재현: 클레임 + 활동 중인데 문서만 조용 -----------------
    def test_s1_claimed_and_active_turn_is_attached(self):
        self.bind("lead1234", reqs=[self.A], transcript_age=1)
        r = self.live_row(self.A)
        self.assertEqual(r.get("live_kind"), "direct", r)
        self.assertEqual(r.get("stall_state"), "attached",
                         "일하는 세션이 잡은 카드가 멈춤으로 그려진다 — "
                         f"{r.get('stall_state')}: {r.get('stall_why')}")
        self.assertIsNone(r.get("stalled_mins"))
        # 조용함은 감추지 않는다 — 문서의 조용한 시간은 그대로 낸다
        self.assertGreaterEqual(r.get("quiet_mins", 0), 15)

    # ---- S2. 간접 세션(클레임 없음)은 여전히 멈춤 ------------------------
    def test_s2_indirect_session_still_stalls(self):
        self.bind("side5678", transcript_age=1)
        r = self.live_row(self.B)
        self.assertEqual(r.get("live_kind"), "session", r)
        self.assertEqual(r.get("stall_state"), "stalled",
                         "클레임 없는 세션 활동이 멈춤 경보를 껐다 — "
                         "귀속은 선언(클레임)으로만")
        self.assertGreaterEqual(r.get("stalled_mins") or 0, 15)

    # ---- S3. 회귀(REQ-20260827-074): 활동 끊긴 클레임은 멈춤 -------------
    def test_s3_claim_with_stale_activity_stalls(self):
        self.bind("gone9999", reqs=[self.C], transcript_age=600)
        r = self.live_row(self.C)
        self.assertNotEqual(r.get("live_kind"), "direct", r)
        self.assertEqual(r.get("stall_state"), "stalled", r.get("stall_why"))
        self.assertGreaterEqual(r.get("stalled_mins") or 0, 15)

    # ---- S4. 문서가 방금 갱신됐으면 moving — 문서 진전이 이긴다 ----------
    def test_s4_fresh_doc_is_moving_not_attached(self):
        self.bind("lead1234", reqs=[self.D], transcript_age=1)
        r = self.live_row(self.D)
        self.assertEqual(r.get("stall_state"), "moving", r.get("stall_why"))

    # ---- S5. 계약: live 필드 없는 행은 현행 그대로 -----------------------
    def test_s5_row_without_live_fields_unchanged(self):
        old = (datetime.datetime.now().astimezone()
               - datetime.timedelta(seconds=3600)).isoformat(timespec="seconds")
        v = self.m.stall_verdict(
            {"id": self.A, "status": "in-progress", "updated": old},
            time.time(), self.m.STALLED_WIN, hands=[], assigned={})
        self.assertEqual(v["state"], "stalled", v)
        self.assertGreaterEqual(v["mins"], 15)

    # ---- S6. attached 카드의 깨우기는 판정의 문장 그대로 거절 ------------
    def test_s6_wake_refusal_uses_verdict_sentence(self):
        self.bind("lead1234", reqs=[self.A], transcript_age=1)
        r = self.live_row(self.A)
        out = self.m._wake_refusal(self.A, r, self.m.STALLED_WIN,
                                   r.get("updated"), time.time())
        self.assertFalse(out["ok"])
        self.assertEqual(out["action"], "attached", out)
        self.assertIn(r.get("stall_why", ""), out["message"])

    # ---- S7. CLI/워처: 일하는 세션의 카드는 stalled 목록에서 빠진다 ------
    def test_s7_stalled_list_excludes_active_turn(self):
        self.bind("lead1234", reqs=[self.A], transcript_age=1)
        ids = [x["id"] for x in self.m.stalled_requests()]
        self.assertNotIn(self.A, ids,
                         "일하는 세션이 잡은 카드가 워처 스폰 대상에 남아 있다")
