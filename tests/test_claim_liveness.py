"""클레임은 활동이 아니라 생존으로 판정한다 (REQ-20260826-013-62x6).

전에는 "120초 내 활동(transcript mtime)"이 있어야 클레임으로 인정했다. 그래서
**일하느라 바쁜 세션일수록 클레임을 잃었다** — 회당 2분짜리 테스트 스위트를
도는 동안 활동 파일이 갱신되지 않기 때문이다. 방향이 정반대다.

실사고 2026-08-26 20:04 — 리드가 19:19 에 클레임한 REQ 두 건에 무인 워커가
겹쳐 떴고, 그중 하나는 **리드가 쓰던 세션 식별자로 되살아났다**(SPAWN(resume)
sid=cb49b2cd). 같은 파일을 둘이 고치는 것보다 나쁘다: 같은 세션을 둘이 쓴다.
그날 하루에 이 뿌리로 네 번 값을 치렀다(REQ-20260826-021).

여기서 검사하는 것은 두 가지다.
  ① 조용하지만 살아 있는 세션의 클레임은 유지된다 (겹침 스폰 차단)
  ② 살아 있는 세션의 id 는 --resume 대상이 되지 않는다 (세션 이중 사용 차단)

격리: S9_ROOT=mktemp. 실행: python3 tests/ claim_liveness
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def s9mod(root):
    """bin/s9 를 모듈로 적재해 판정 함수를 직접 부른다(서브프로세스보다 정확)."""
    import importlib.util
    os.environ["S9_ROOT"] = root
    spec = importlib.util.spec_from_loader(
        "s9mod_" + os.path.basename(root),
        importlib.machinery.SourceFileLoader(
            "s9mod_" + os.path.basename(root), S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ClaimLiveness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9claim-")
        self.env = {**os.environ, "S9_ROOT": self.tmp, "S9_MACHINE": "testbox",
                    "S9_USER": "tester"}
        self.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       env=self.env, timeout=30, stdin=subprocess.DEVNULL)
        self.m = s9mod(self.tmp)
        self.m.ROOT = self.tmp
        self.m.STATE = os.path.join(self.tmp, "state", "sessions")
        self.m.STREAMS = os.path.join(self.tmp, "streams")
        os.makedirs(self.m.STATE, exist_ok=True)
        os.makedirs(self.m.STREAMS, exist_ok=True)
        self.m.current_machine = lambda: "testbox"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def binding(self, sid, req, *, attach_pid=None, activity_age=0, ended=""):
        """세션 바인딩 + 활동 파일. activity_age 초만큼 오래된 것으로 만든다."""
        tp = os.path.join(self.m.STREAMS, f"{sid}-full.jsonl")
        with open(tp, "w") as f:
            f.write("{}\n")
        old = time.time() - activity_age
        os.utime(tp, (old, old))
        b = {"machine": "testbox", "session": sid, "user": "tester",
             "history": [], "active_reqs": [req], "transcript_path": tp,
             "ended": ended}
        if attach_pid is not None:
            b["attach_pid"] = attach_pid
        with open(os.path.join(self.m.STATE, f"testbox__{sid}.json"), "w") as f:
            json.dump(b, f)
        return b

    # ---- ① 겹침 스폰 차단 ------------------------------------------------
    def test_busy_session_keeps_its_claim(self):
        """긴 작업으로 조용해진 세션도 살아 있으면 클레임을 지킨다.

        이 한 줄이 실사고의 전부였다 — 스위트를 도는 동안 클레임을 잃었다.
        """
        self.binding("busysess", "REQ-20260826-013-62x6",
                     attach_pid=1, activity_age=3600)   # 1시간 조용, pid는 생존
        self.assertTrue(self.m.rework_claimed("REQ-20260826-013-62x6"))

    def test_dead_session_does_not_hold_a_claim(self):
        """죽은 세션의 클레임은 인정하지 않는다 — 아무도 이어받지 못하게 된다."""
        self.binding("deadsess", "REQ-20260826-013-62x6",
                     attach_pid=999999999, activity_age=3600)
        self.assertFalse(self.m.rework_claimed("REQ-20260826-013-62x6"))

    def test_ended_session_does_not_hold_a_claim(self):
        """SessionEnd 로 끝난 세션도 마찬가지 — pid 가 남아 있어도 놓아준다."""
        self.binding("endedses", "REQ-20260826-013-62x6",
                     attach_pid=1, activity_age=0, ended="1")
        self.assertFalse(self.m.rework_claimed("REQ-20260826-013-62x6"))

    def test_fresh_activity_still_counts(self):
        """기존 경로 회귀 — pid 없이 활동만 신선해도 클레임이다."""
        self.binding("freshses", "REQ-20260826-013-62x6", activity_age=1)
        self.assertTrue(self.m.rework_claimed("REQ-20260826-013-62x6"))

    def test_unrelated_req_is_not_claimed(self):
        """다른 REQ 를 등록한 세션이 이 REQ 의 클레임을 대신하지 않는다."""
        self.binding("othersss", "REQ-20260826-999-62x6", attach_pid=1)
        self.assertFalse(self.m.rework_claimed("REQ-20260826-013-62x6"))

    # ---- ② 세션 이중 사용 차단 -------------------------------------------
    def test_live_session_id_is_never_resumed(self):
        """살아 있는 세션의 id 로 워커를 되살리지 않는다.

        같은 세션을 두 주체가 쓰면 응답 캡처가 엉뚱한 문서에 붙고 대화 이력이
        갈린다 — 같은 파일을 둘이 고치는 것보다 나쁘다.
        """
        sid_full = "cb49b2cd-1111-2222-3333-444444444444"
        tp = os.path.join(self.tmp, sid_full + ".jsonl")
        with open(tp, "w") as f:
            f.write("{}\n")
        old = time.time() - 3600
        os.utime(tp, (old, old))          # 조용하지만
        b = {"machine": "testbox", "session": "cb49b2cd", "user": "tester",
             "attach_pid": 1,             # 살아 있다
             "transcript_path": tp, "ended": "", "active_reqs": []}
        with open(os.path.join(self.m.STATE, "testbox__cb49b2cd.json"), "w") as f:
            json.dump(b, f)

        seen = {}

        class FakeProc:
            pid = 4242

        def fake_popen(argv, **kw):
            seen["argv"] = argv
            seen["env"] = kw.get("env", {})
            return FakeProc()

        import subprocess as sp
        real = sp.Popen
        sp.Popen = fake_popen
        try:
            self.m.user_config = lambda o: {"auto_resume": True}
            self.m._auto_caps_ok = lambda d, c, *_a, **_k: True
            ok = self.m._spawn_worker(
                "REQ-20260826-013-62x6",
                {"user": "tester", "machine": "testbox", "session": "cb49b2cd"},
                "prompt", "rework", allow_resume=True)
        finally:
            sp.Popen = real
        self.assertTrue(ok)
        self.assertNotIn("--resume", seen["argv"],
                         "살아 있는 세션 id 로 되살아났다 — 세션 이중 사용")
        self.assertNotIn("S9_SESSION", seen["env"],
                         "죽지 않은 세션의 식별자를 워커에 물려줬다")

    def test_envelope_carries_collision_discipline(self):
        """봉투에 충돌 규율이 함께 실린다 — 프롬프트마다 따로 적으면 갈린다."""
        seen = {}

        class FakeProc:
            pid = 4243

        def fake_popen(argv, **kw):
            seen["argv"] = argv
            return FakeProc()

        import subprocess as sp
        real = sp.Popen
        sp.Popen = fake_popen
        try:
            self.m.user_config = lambda o: {"auto_resume": True}
            self.m._auto_caps_ok = lambda d, c, *_a, **_k: True
            self.m._spawn_worker(
                "REQ-20260826-013-62x6",
                {"user": "tester", "machine": "testbox", "session": "nosess00"},
                "본래 프롬프트", "rework")
        finally:
            sp.Popen = real
        prompt = seen["argv"][2]
        self.assertIn("본래 프롬프트", prompt)
        self.assertIn("git status --short", prompt)
        self.assertIn("덮어쓰지 말고 멈춰서", prompt)
        self.assertIn("git checkout", prompt)   # 금지 목록에 있어야 한다


if __name__ == "__main__":
    unittest.main(verbosity=2)
