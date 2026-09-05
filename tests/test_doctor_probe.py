"""진단이 병을 키우지 않는다 — 공개 지연 프로브의 규율 (REQ-20260904-017 · 014).

devops-engineer 가 코드를 읽다 찾았다(REQ-20260904-013): `probe_new_port` 가
0.25초 고정 간격으로 최대 12초를 두드려, 공개가 늦어지는 **바로 그때** 시간당
최대 2,880개를 태웠다 — 실측 소모 속도(2,670/h)와 같은 자릿수다. 그리고 그
프로브는 커널 임시 포트(0)에 bind 했다 — 시험에서는 적발하는 행위인데 도구는
문 밖이었다.

실행: python3 tests/ doctor_probe
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import sys
import subprocess
import socket
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCTOR = os.path.join(ROOT, "bin", "s9-doctor")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_doctor_probe", importlib.machinery.SourceFileLoader(
            "s9_doctor_probe", DOCTOR))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TheProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_p1_backs_off_instead_of_hammering(self):
        """P1. 공개가 늦으면 두드리는 간격이 자라고, 12초 예산 안에 10회 이하다."""
        sleeps = []
        def never(_port):
            raise OSError("not yet")
        r = self.m.probe_new_port(budget=12.0, _connect=never,
                                  _sleep=lambda s: sleeps.append(s))
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "publish")
        # 상한은 손으로 고른 수가 아니라 파라미터에서 나온다 — 예산을 채우는
        # 데 드는 잠의 횟수 + 1. (예전 고정 0.25초는 같은 12초에 48회였다.)
        wait, spent, sleeps_needed = self.m.PROBE_FIRST, 0.0, 0
        while spent + wait < 12.0:
            spent += wait
            sleeps_needed += 1
            wait = min(self.m.PROBE_MAX, wait * self.m.PROBE_GROWTH)
        self.assertEqual(r["attempts"], sleeps_needed + 1,
                         f"12초에 {r['attempts']}회 — 예산 계산이 어긋난다")
        self.assertLess(r["attempts"], 48 // 3,
                        f"12초에 {r['attempts']}회 — 되먹임이 그대로다")
        self.assertTrue(all(b >= a for a, b in zip(sleeps, sleeps[1:])),
                        f"간격이 자라지 않는다: {sleeps}")
        self.assertGreaterEqual(sleeps[0], 0.04)
        self.assertLessEqual(max(sleeps), self.m.PROBE_MAX + 1e-9)

    def test_p2_the_window_is_counted_not_buried(self):
        """P2. 첫 시도가 거부되고 둘째에 붙으면 attempts=2 로 창이 보인다.

        0.25초 고정 간격은 7% 창(12~16ms 실패)을 0.25 로 묻었다 — 세지 않는
        재시도는 결함을 가린다.
        """
        calls = {"n": 0}
        def once_refused(_port):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionRefusedError("window")
        r = self.m.probe_new_port(budget=5.0, _connect=once_refused,
                                  _sleep=lambda s: None)
        self.assertTrue(r["ok"])
        self.assertEqual(r["attempts"], 2)

    def test_p3_binds_in_our_band_not_ephemeral(self):
        """P3. 프로브 리스너는 임시 포트(0)가 아니라 우리 대역(18990~)에 선다."""
        r = self.m.probe_new_port(budget=3.0, _connect=lambda p: None,
                                  _sleep=lambda s: None)
        self.assertTrue(r["ok"])
        self.assertIn(r["port"], self.m.PROBE_PORTS)
        lo, hi = min(self.m.PROBE_PORTS), max(self.m.PROBE_PORTS)
        self.assertLess(hi, 32768, "커널 임시 범위와 겹친다")
        self.assertGreaterEqual(lo, self.m.POOL_LO, "우리 대역 아래다")
        self.assertGreater(lo, self.m.POOL_HI, "프로브가 풀과 겹친다 — 칸이 늘면 시험 서버가 그 자리를 잡는다")
        self.assertLess(hi, 32768)

    def test_p4_the_pool_never_reaches_the_probes(self):
        """P4. 칸을 아무리 넓혀도 풀 꼭대기는 회수 대역 안이고 프로브 아래다.

        실사고 2026-09-05 (REQ-20260905-005): 칸 8 로 풀이 19056 까지 자랐는데
        회수 대역은 18999 에서 끝나, 19089 의 감시자 둘이 스위트 뒤에 남았다.
        두 파일의 상수가 갈리면 바로 그 사고다 — 여기서 못박는다.
        """
        code = ("import portpool as p; print(p.POOL_BASE, p.POOL_SIZE, p.SLOT_SIZE)")
        for slots in ("4", "8", "16", "64"):
            r = subprocess.run([sys.executable, "-c", code], cwd=HERE,
                               capture_output=True, text=True, timeout=60,
                               env={**os.environ, "S9_TEST_PORT_SLOTS": slots})
            base, size, slot = map(int, r.stdout.split())
            top = base + size - 1
            self.assertGreaterEqual(base, self.m.POOL_LO)
            self.assertLessEqual(top, self.m.POOL_HI,
                                 f"칸 {slots}: 풀 꼭대기 {top} 가 회수 대역 밖이다")
            self.assertLess(top, min(self.m.PROBE_PORTS), f"칸 {slots}: 프로브와 겹친다")
            self.assertGreaterEqual(slot, 8, f"칸 {slots}: 칸이 8포트보다 좁다")

    def test_p5_a_reparented_supervisor_in_the_pool_is_an_orphan(self):
        """P5. 재양육된 풀 포트의 감시자는 고아다 — 자식만 죽이면 되살아난다."""
        rows = [(15248, 1, 3000,
                 "/usr/bin/python3 /x/bin/s9 serve --supervise --guard-run --port 19089 --host 127.0.0.1"),
                (17682, 15248, 3000, "python3 /x/bin/s9 serve --host 127.0.0.1 --port 19089")]
        _serves, orphans, _chromes = self.m.scan(rows, live_runs=set())
        self.assertIn(15248, [p for p, _a, _c in orphans], "풀 안 감시자가 고아로 안 보인다")

    def test_p6_nothing_in_the_pool_dies_while_a_suite_runs(self):
        """P6. 스위트가 도는 동안은 풀의 재양육 서버를 거두지 않는다.

        감시자는 double fork 로 일부러 재양육된다 — 살아 있는 실행 루트가 있으면
        그것은 시험 중인 물건이다. 실사고 2026-09-05: 대시보드 틱이 돌고 있는
        시험의 감시자를 죽여 전체가 292→521초, 3건 붉음.
        """
        rows = [(15248, 1, 30,
                 "/usr/bin/python3 /x/bin/s9 serve --supervise --guard-run --port 19089 --host 127.0.0.1")]
        _s, orphans, _c = self.m.scan(rows, live_runs={4242})
        self.assertEqual(orphans, [], "도는 스위트의 감시자를 고아로 봤다")

    def test_p7_live_runs_come_from_run_roots_with_living_owners(self):
        """P7. 살아 있는 실행 = 주인이 살아 있는 s9run-<pid>- 루트."""
        base = tempfile.mkdtemp(prefix="s9probe-")
        try:
            os.makedirs(os.path.join(base, f"s9run-{os.getpid()}-abc"))
            os.makedirs(os.path.join(base, "s9run-999999999-dead"))
            self.assertEqual(self.m.live_test_runs(base), {os.getpid()})
            # 러너가 TMPDIR 을 실행 루트로 돌린 자식 안에서 불려도 형제를 본다
            inner = os.path.join(base, f"s9run-{os.getpid()}-abc")
            orig = self.m.tempfile.gettempdir
            self.m.tempfile.gettempdir = lambda: inner
            try:
                self.assertIn(os.getpid(), self.m.live_test_runs())
            finally:
                self.m.tempfile.gettempdir = orig
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_p4_the_listener_really_answers(self):
        """P4. 흉내가 아니라 진짜로 — 리스너가 서고 실제 연결이 닿는다."""
        r = self.m.probe_new_port(budget=5.0)
        self.assertTrue(r["ok"], r)
        self.assertGreaterEqual(r["attempts"], 1)

    def test_p5_no_ephemeral_bind_in_the_doctor(self):
        """P5. 도구에도 문이 선다 — `bind(("127.0.0.1", 0))` 이 s9-doctor 에 없다."""
        src = open(DOCTOR, encoding="utf-8").read()
        import re
        # 주석과 독스트링은 설명이지 실행이 아니다 — 걷어내고 본다.
        code = re.sub(r'"""[\s\S]*?"""', "", src)
        code = "\n".join(l for l in code.splitlines() if not l.strip().startswith("#"))
        self.assertIsNone(re.search(r'bind\(\(\s*"127\.0\.0\.1"\s*,\s*0\s*\)\)', code),
                          "임시 포트에 bind 하는 자리가 도구에 남아 있다")


class TheRetractedClaim(unittest.TestCase):
    """REQ-20260904-014. 「죽여도 세션·에이전트는 살아남는다」는 거둔 단언이다.

    REQ-20260902-066 이 근거 없음으로 판정했고, 그 중계가 나르던 연결이 전부
    끊기는 것은 설계상 확실하다. 확인 프롬프트만 고쳐지고 **사람이 고장 났을 때
    읽는 안내문**은 옛 단언 그대로였다 — 안내가 거짓이면 안내가 곧 피해다.
    """

    def test_c1_no_survival_claim_in_user_facing_text(self):
        import re
        for path in (DOCTOR, os.path.join(ROOT, "bin", "s9.py")):
            src = open(path, encoding="utf-8").read()
            # 주석과 독스트링 안의 「거둔 단언이다」 같은 설명은 두고, 문자열
            # 리터럴(사람에게 나가는 문장)만 본다.
            # 주석 줄은 설명이고, 한 줄짜리 문자열 리터럴만 사람에게 나간다.
            for ln in src.splitlines():
                if ln.strip().startswith("#"):
                    continue
                for m in re.finditer(r'["\'](?:[^"\'\\]|\\.)*살아남는다(?:[^"\'\\]|\\.)*["\']', ln):
                    ctx = m.group(0)
                    self.assertTrue("거둔" in ctx or "더는" in ctx or "않는다" in ctx
                                    or "끊긴다" in ctx,
                                    f"{os.path.basename(path)}: 안내문에 거둔 단언이 남았다: {ctx[:80]}")


if __name__ == "__main__":
    unittest.main()
