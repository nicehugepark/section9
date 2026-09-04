"""호스트 포트 감시 임계 동작 테스트 (REQ-20260825-102).

2026-08-25 사고: WSL 포트 중계가 윈도우 동적 포트 16,384개 중 15,709개를
물고 놓지 않아 OS 전체 아웃바운드가 끊겼다. 사람이 "인터넷이 안 된다"를
겪고 나서야 알았고, 그 전까지 아무 경고도 없었다.

그래서 serve 가 주기적으로 재고 임계마다 스스로 손을 쓴다. 이 테스트가
고정하는 것은 **임계와 그때의 행동**이다 —
  60% 미만: 아무것도 하지 않는다(멀쩡한데 건드리면 그게 사고다)
  60%↑   : 기록만 남기고 사람에게 넘긴다 — 무인 중계 종료는 기본 끔
           (REQ-20260902-066; S9_PORT_GUARD_RELAY_AUTO 로 옵트인)
  90%↑   : 점유자 회수 — 고갈되기 전에, 사람 개입 없이
윈도우 쪽을 못 읽는 환경(순수 리눅스)에서는 조용히 아무것도 하지 않는다.
실행: python3 tests/ port_guard
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

os.environ.setdefault("S9_ROOT", tempfile.mkdtemp(prefix="s9guard-"))
spec = importlib.util.spec_from_loader(
    "s9_mod_guard", importlib.machinery.SourceFileLoader("s9_mod_guard", S9))
s9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s9)


class FakeRun:
    def __init__(self, stdout="", rc=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = rc


def fake_doctor(bound, total=16384, calls=None, top_name="dllhost.exe"):
    """--json 은 진단을, 나머지 플래그는 성공을 돌려주는 가짜 s9-doctor."""
    payload = json.dumps({"windows_ports": {"bound": bound, "count": total,
                                            "top_name": top_name,
                                            "top_pid": 31172,
                                            "top_count": bound}})

    def _doctor(*flags, timeout=90):
        if calls is not None:
            calls.append(flags)
        return FakeRun(payload if "--json" in flags and len(flags) == 1
                       else "{}")
    return _doctor


class PortGuard(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.logged = []
        self._orig = (s9._doctor, s9._guard_log)
        s9._guard_log = self.logged.append
        # 경고는 같은 말을 되풀이하지 않는다(REQ-20260827-019) — 그 억제
        # 상태가 모듈에 남아 **다음 시험의 경고를 삼킨다**. 시험끼리 새는
        # 상태라 매번 지운다.
        s9._port_warn_last.clear()

    def tearDown(self):
        s9._doctor, s9._guard_log = self._orig

    def tick(self, bound, total=16384, top_name="dllhost.exe"):
        s9._doctor = fake_doctor(bound, total, self.calls, top_name)
        return s9.port_guard_tick()

    # ---- 중간 안전망 (REQ-20260830-037) — **기본값은 끔** (REQ-20260902-066).
    # 60% 무인 중계 종료는 "회수는 싸다(0.3초·세션 생존)"를 근거로 걸렸는데,
    # 실측 2026-09-02 에 하루 아홉 번 발동해 일곱 번이 실패로 남았고 사용자가
    # "자꾸 wsl 이 죽는 것 같다"고 물었다. 이 환경의 점유는 34~73% 를 온종일
    # 오르내린다 — 60%는 이상 신호가 아니라 평시다. 평시에 남의 프로세스를
    # 죽이는 장치는 방어가 아니라 사고다.
    def test_p1_relay_hoard_is_not_killed_by_default(self):
        v = self.tick(10650)                      # 65% + 최다=중계
        self.assertEqual(v["action"], "watch",
                         "기본값에서 중계를 죽였다 — 평시 대역이다")
        self.assertNotIn(("--recover", "--yes"), self.calls)

    def test_p1b_that_warning_hands_over_the_decision(self):
        """끄는 대신 사람이 판단할 재료를 준다 — 누가 쥐었나·무엇을 치나·대가."""
        self.tick(10650)
        msg = "\n".join(self.logged)
        self.assertIn("dllhost.exe", msg)
        self.assertIn("31172", msg)               # top_pid
        self.assertIn("doctor --recover", msg)
        self.assertIn("WSL 세션", msg,
                      "대가를 안 적으면 예전 단언('세션은 살아남는다')로 되돌아간다")

    def test_p1c_opt_in_restores_the_old_reclaim(self):
        """이 처방이 맞는 설치를 막지는 않는다 — 문턱을 주면 예전 동작 그대로."""
        orig = s9.PORT_GUARD_RELAY_AUTO
        s9.PORT_GUARD_RELAY_AUTO = 0.60
        try:
            v = self.tick(10650)
            self.assertEqual(v["action"], "relay-recover")
            self.assertIn(("--recover", "--yes"), self.calls)
        finally:
            s9.PORT_GUARD_RELAY_AUTO = orig

    def test_p2_user_process_hoard_is_never_touched(self):
        orig = s9.PORT_GUARD_RELAY_AUTO
        s9.PORT_GUARD_RELAY_AUTO = 0.60           # 옵트인이 켜져 있어도
        try:
            v = self.tick(10650, top_name="chrome.exe")  # 65%, 최다=브라우저
            self.assertEqual(v["action"], "watch",
                             "사용자 프로세스가 최다인데 회수를 불렀다 — 불가침")
            self.assertNotIn(("--recover", "--yes"), self.calls)
        finally:
            s9.PORT_GUARD_RELAY_AUTO = orig

    def test_p3_below_threshold_is_unchanged(self):
        v = self.tick(8000)                       # 49% — 중계여도 문턱 미만
        self.assertEqual(v["action"], "watch")
        self.assertNotIn(("--recover", "--yes"), self.calls)

    def test_reclaims_every_tick_regardless_of_pressure(self):
        """핵심: 회수는 소진도와 무관하게 매번 돈다.

        임계에서만 쓸면 그 임계까지는 반드시 쌓인다 — 그게 "90%에서 조치하는
        건 방어가 아니다"라는 지적의 실체다. 평시 2%에서도 회수는 돈다."""
        v = self.tick(211)                        # 1.3% — 평시
        self.assertIsNone(v["action"])
        self.assertEqual(self.calls[0], ("--sweep", "--json"))
        self.assertNotIn(("--recover", "--yes"), self.calls)

    def test_elevated_is_recorded_not_acted_on(self):
        v = self.tick(8000)                       # 49% — 평시보다 높다
        self.assertEqual(v["action"], "watch")
        self.assertTrue(any("평시" in m for m in self.logged))
        self.assertNotIn(("--recover", "--yes"), self.calls)

    def test_last_resort_recovers_and_flags_a_defect(self):
        """90%는 방어선이 아니라 마지막 안전망이다 — 왔다는 것 자체가 결함."""
        v = self.tick(15000)                      # 92%
        self.assertEqual(v["action"], "recover")
        self.assertIn(("--recover", "--yes"), self.calls)
        self.assertTrue(v["ok"])
        self.assertTrue(any("구멍" in m for m in self.logged))

    def test_no_windows_side_is_silent(self):
        s9._doctor = lambda *a, **k: FakeRun(json.dumps({"windows_ports": {}}))
        self.assertEqual(s9.port_guard_tick(), {"swept": {"windows_ports": {}}})
        self.assertFalse(self.logged)

    def test_doctor_missing_does_not_raise(self):
        s9._doctor = lambda *a, **k: None
        self.assertEqual(s9.port_guard_tick(), {"swept": {}})

    def test_reclaimed_orphans_are_logged(self):
        """조용히 사라지면 원인을 못 찾는다 — 회수는 반드시 흔적을 남긴다."""
        def _doctor(*flags, timeout=90):
            if flags == ("--sweep", "--json"):
                return FakeRun(json.dumps({"procs": 3, "orphans": 3,
                                           "profiles": 2, "alive": 1}))
            return FakeRun(json.dumps({"windows_ports": {"bound": 211,
                                                         "count": 16384}}))
        s9._doctor = _doctor
        s9.port_guard_tick()
        self.assertTrue(any("고아 회수" in m for m in self.logged))


if __name__ == "__main__":
    unittest.main()
