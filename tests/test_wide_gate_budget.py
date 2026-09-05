"""전체 스위트는 commit 뒤 배경에서 — 커밋 문은 붉음 라쳇으로 지킨다 (REQ-20260905-010).

실사고 2026-09-05: 라벨 한 줄에 러너 33줄이 딸려 문이 전체 스위트를 요구했고
그 실행이 멈춰 커밋이 한 시간 밀렸다. quality-assurance 실측: commit 전 동기
게이트는 하루 174분, commit 뒤 비동기는 5분 — 12~35배. 문은 막는 대신
**붉음을 기억한다**: 마지막 붉음이 마지막 초록보다 새로우면 code 커밋을 세운다.

실행: python3 tests/ wide_gate_budget
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_guard_ratchet", importlib.machinery.SourceFileLoader("s9_guard_ratchet", GUARD))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class RedRatchet(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.red = {"at": 1000.0, "files": ["test_code_read_gate.py"]}

    def test_t1_red_newer_than_green_blocks(self):
        """T1. 마지막 붉음이 마지막 초록보다 새로우면 막는다 — 초록 없음도 막는다."""
        blocked, files = self.m.red_ratchet(["bin/s9.py"], red=self.red,
                                            green_age=600, now=1500, fix_env="")
        self.assertTrue(blocked)                 # 초록 at=900 < 붉음 1000
        self.assertEqual(files, ["test_code_read_gate.py"])
        # green_age=None 은 「초록 없음」이 아니라 「기록을 찾아보라」다 — 실저장소의
        # 초록이 신선하면 이 단언이 시각에 따라 갈린다(실측 2026-09-05). 없음은 함수로 세운다.
        keep = self.m.full_green_age
        self.m.full_green_age = lambda: None
        try:
            self.assertTrue(self.m.red_ratchet(["bin/s9.py"], red=self.red,
                                               green_age=None, now=1500, fix_env="")[0])
        finally:
            self.m.full_green_age = keep

    def test_t2_green_after_red_passes(self):
        """T2. 붉음 뒤에 초록이 있었으면 막지 않는다 · 기록이 없어도 막지 않는다."""
        self.assertFalse(self.m.red_ratchet(["bin/s9.py"], red=self.red,
                                            green_age=100, now=1500, fix_env="")[0])
        self.assertFalse(self.m.red_ratchet(["bin/s9.py"], red={},
                                            green_age=None, now=1500, fix_env="")[0])

    def test_t3_the_fix_and_the_declared_exception_pass(self):
        """T3. 붉은 파일의 시험을 담은 커밋(고치러 온 것)과 S9_FIX_RED 는 지나간다."""
        self.assertFalse(self.m.red_ratchet(
            ["bin/s9.py", "tests/test_code_read_gate.py"], red=self.red,
            green_age=600, now=1500, fix_env="")[0])
        self.assertFalse(self.m.red_ratchet(["bin/s9.py"], red=self.red,
                                            green_age=600, now=1500,
                                            fix_env="REQ-20260905-007-62x6")[0])


class OneFullRunAtATime(unittest.TestCase):
    """전체 실행은 한 번에 하나 (REQ-20260905-022)."""

    def test_o1_a_live_full_job_stops_a_second_spawn(self):
        """O1. kind=full 이고 pid 가 살아 있는 잡이 있으면 그 pid, 죽은 pid 나 표적 잡은 0."""
        import json
        import tempfile
        m = _load()
        d = tempfile.mkdtemp(prefix="s9jobs-")
        def put(name, **kw):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                json.dump(kw, f)
        put("tests-1.json", kind="full", pid=999999999)          # 죽은 실행
        put("tests-2.json", kind="targeted", pid=os.getpid())     # 표적
        self.assertEqual(m.full_run_in_flight(d), 0)
        put("tests-3.json", kind="full", pid=os.getpid())         # 살아 있는 전체
        self.assertEqual(m.full_run_in_flight(d), os.getpid())

    def test_o2_the_runner_reaps_its_children_on_sigterm(self):
        """O2. 러너는 SIGTERM 에 샤드·좁혀서-다시 자식을 함께 거둔다(구조)."""
        src = open(os.path.join(HERE, "__main__.py"), encoding="utf-8").read()
        blk = src.split("def run_sharded", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_signal.SIGTERM", blk, "SIGTERM 에 자식을 거두지 않는다")
        self.assertIn("RETRY_PROCS", blk, "좁혀서-다시 자식을 추적하지 않는다")

    def test_o3_commit_time_knobs_do_not_leak_into_the_background_run(self):
        """O3. 커밋 때의 손잡이(S9_FIX_RED 등)는 배경 전체 실행에 물려주지 않는다(구조)."""
        src = open(GUARD, encoding="utf-8").read()
        blk = src.split("def after_commit", 1)[1].split("\ndef ", 1)[0]
        for k in ("S9_FIX_RED", "S9_ALLOW_CONCURRENT"):
            self.assertIn(k, blk, f"{k} 를 배경 실행 환경에서 걷지 않는다")


if __name__ == "__main__":
    unittest.main()
