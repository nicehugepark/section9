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
        # 사다리의 기억(최근 표본·--fix 시각·처형 기록)도 시험끼리 샌다 — 매번
        # 비우고, 파일은 임시 자리로 돌리고, 「조용함」은 시험이 정한다 (실제
        # 이 기계에는 살아 있는 세션이 있어 늘 「일하는 중」이 나온다).
        import tempfile
        self._tmpring = tempfile.mkdtemp(prefix="s9ring-")
        self._orig_ring = (s9._port_ring_file, s9._port_quiet)
        s9._port_ring_file = lambda: os.path.join(self._tmpring, "ring.json")
        s9._port_quiet = lambda: True
        s9._port_ring.update({"samples": [], "fix_at": 0.0, "recovers": []})

    def tearDown(self):
        s9._doctor, s9._guard_log = self._orig
        s9._port_ring_file, s9._port_quiet = self._orig_ring
        s9._port_ring.update({"samples": [], "fix_at": 0.0, "recovers": []})
        import shutil
        shutil.rmtree(self._tmpring, ignore_errors=True)

    def climb(self, bound, ticks, top_name="dllhost.exe"):
        """같은 값으로 여러 틱 — 「지속」을 만든다. 마지막 판정을 돌려준다."""
        v = None
        for _ in range(ticks):
            v = self.tick(bound, top_name=top_name)
        return v

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

    def test_p1c_opt_in_goes_through_the_same_gate(self):
        """옵트인은 문을 더 여는 것이지 문을 없애는 것이 아니다 (REQ-20260904-016).

        예전엔 문턱만 주면 한 틱에 곧바로 죽였다 — 그 동작이 2026-09-02 에
        하루 아홉 번 죽인 자리다. 이제 중간 안전망도 마지막 안전망과 **같은
        문**(여섯 조건)을 지난다. 게이트가 두 벌이면 성긴 쪽으로 샌다.
        """
        orig = s9.PORT_GUARD_RELAY_AUTO
        s9.PORT_GUARD_RELAY_AUTO = 0.60
        try:
            v = self.tick(10650)                  # 65%, 한 틱
            self.assertNotEqual(v["action"], "recover")
            self.assertNotIn(("--recover", "--yes"), self.calls)
            self.assertTrue(v.get("held"), "왜 세웠는지가 판정에 없다")
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
        """문턱 아래는 조용하다 — 49% 는 이 기계의 **일하는 중** 값이다.

        실측 2026-09-04(31시간 3,873표본, REQ-20260903-003): 중앙값 30% ·
        p75 54%. 그래서 예전 문턱 0.30 은 하루의 절반이 넘는 값이었고
        「넘었다」가 아무것도 말하지 않았다. 문턱을 0.60 으로 올린 뒤로
        49% 는 아무 말도 하지 않는다.
        """
        v = self.tick(8000)                       # 49% — 일하는 중의 평범한 값
        self.assertIsNone(v["action"])
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
        """문턱을 넘으면 적기만 한다 — 손대지 않는다.

        기록에 적는 말도 실측에 맞춘다: 예전엔 「평시 1~3%」라고 적었는데
        그 전제가 틀렸다. 놀 때 바닥은 10 안팎(0%)이고, 일하는 동안 단조
        증가해 바닥으로 돌아오지 않는다 — 그러니 사람이 볼 값은 비율이
        아니라 기울기다 (REQ-20260903-003).
        """
        v = self.tick(11000)                      # 67% — 문턱(60%) 위
        self.assertEqual(v["action"], "watch")
        self.assertTrue(any("계속 오른다" in m for m in self.logged),
                        f"기울기를 말하지 않는다: {self.logged}")
        self.assertFalse(any("평시 1~3%" in m for m in self.logged),
                         "틀린 평시가 아직 적힌다")
        self.assertNotIn(("--recover", "--yes"), self.calls)

    # ---- 사다리 (REQ-20260904-016) -----------------------------------
    def test_f1_one_sample_over_ninety_does_not_kill(self):
        """F1. 92% 한 표본으로는 안 죽인다 — 오늘 낮 천장 90% 가 한 번 스쳤다."""
        v = self.tick(15000)                      # 92%, 한 틱
        self.assertNotEqual(v["action"], "recover")   # 경고(watch)는 남는다
        self.assertNotIn(("--recover", "--yes"), self.calls)
        self.assertTrue(any("지속" in w for w in v["held"]), v["held"])
        self.assertTrue(any("세운다" in m for m in self.logged),
                        "세운 이유가 기록에 없다 — 다음 아홉 번에 각각의 이유가 있어야 한다")

    def test_l2_sustained_85_runs_the_harmless_fix_first(self):
        """L2. 0.85 가 5틱 지속되면 파괴 없는 회수(--fix) — 남도 사람도 안 죽인다."""
        v = self.climb(14000, s9.PORT_GUARD_SUSTAIN)   # 85.4%
        self.assertEqual(v["action"], "fix")
        self.assertIn(("--fix",), self.calls)
        self.assertNotIn(("--recover", "--yes"), self.calls)
        # 되풀이하지 않는다 — 다음 틱은 간격 안이라 --fix 를 또 부르지 않는다
        v2 = self.tick(14000)
        self.assertNotEqual(v2["action"], "fix")
        self.assertEqual(self.calls.count(("--fix",)), 1)

    def test_l3_all_six_true_opens_the_gate(self):
        """L3. 여섯이 전부 참이면 연다 — 지속·중계·--fix 선행·조용함·예산·비율."""
        self.climb(14000, s9.PORT_GUARD_SUSTAIN)       # --fix 가 먼저 돈다
        v = self.tick(15000)                            # 92%, 아직 안 나아졌다
        self.assertEqual(v["action"], "recover", v.get("held"))
        self.assertIn(("--recover", "--yes"), self.calls)
        self.assertTrue(v["ok"])
        self.assertTrue(any("여섯 조건" in m for m in self.logged))

    def test_f2_nobody_dies_while_someone_works(self):
        """F2. 일하는 중이면 95% 여도 안 죽인다 — 사람의 연결을 끊는 자리에 사람이 있다."""
        s9._port_quiet = lambda: False
        self.climb(14000, s9.PORT_GUARD_SUSTAIN)
        v = self.tick(15600)                            # 95%
        self.assertNotEqual(v["action"], "recover")
        self.assertTrue(any("일하는 중" in w for w in v["held"]), v["held"])
        self.assertNotIn(("--recover", "--yes"), self.calls)

    def test_f3_user_app_hoard_is_never_killed_even_at_ninety(self):
        """F3. 최다 점유자가 사용자 앱이면 92% 지속이어도 안 죽인다 (P2 그대로)."""
        self.climb(14000, s9.PORT_GUARD_SUSTAIN, top_name="chrome.exe")
        v = self.tick(15000, top_name="chrome.exe")
        self.assertNotEqual(v["action"], "recover")
        self.assertTrue(any("사용자 앱" in w for w in v["held"]), v["held"])

    def test_f4_no_recover_before_fix(self):
        """F4. --fix 를 안 거쳤으면 못 죽인다 — 무해한 칸을 건너뛰지 않는다."""
        import time
        s9.PORT_GUARD_FIX_EVERY = 10 ** 9              # 이 시험에서 fix 를 막는다
        s9._port_ring["fix_at"] = time.time() - 3600    # 한 시간 전 — 문의 30분 창 밖
        try:
            v = self.climb(15000, s9.PORT_GUARD_SUSTAIN)  # 92% 지속
            self.assertNotEqual(v["action"], "recover")
            self.assertNotIn(("--recover", "--yes"), self.calls)
            self.assertTrue(any("--fix" in w for w in v["held"]), v["held"])
        finally:
            s9.PORT_GUARD_FIX_EVERY = 600

    def test_f5_budget_holds_the_second_kill(self):
        """F5. 예산을 다 쓰면 세운다 — 시간당 1회."""
        import time
        s9._port_ring["recovers"] = [time.time() - 60]  # 1분 전에 한 번 죽였다
        self.climb(14000, s9.PORT_GUARD_SUSTAIN)
        v = self.tick(15000)
        self.assertNotEqual(v["action"], "recover")
        self.assertTrue(any("예산" in w for w in v["held"]), v["held"])

    def test_b1_a_dip_resets_the_streak(self):
        """B1. 하락이 한 번 끼면 지속이 0 으로 돌아간다."""
        self.climb(14000, 3)
        self.tick(13900)                                # 살짝 내려갔다
        v = self.climb(14000, 3)
        self.assertLess(v["sustain"], s9.PORT_GUARD_SUSTAIN)
        self.assertNotIn(v["action"], ("fix", "recover"))

    def test_b2_too_few_samples_means_unknown_means_no_kill(self):
        """B2. 방금 뜬 서버(표본 5개 미만)는 모른다 — 모르면 안 죽인다."""
        v = self.climb(15000, 2)
        self.assertNotIn(v["action"], ("fix", "recover"))
        self.assertLess(v["sustain"], s9.PORT_GUARD_SUSTAIN)

    def test_l1_rising_over_75_carries_banner_and_eta(self):
        """L1. 0.75 위에서 오르는 중이면 화면 재료(banner·eta_min)가 실린다."""
        import time
        # 표본 시각을 벌려 기울기가 서게 한다
        for i, b in enumerate((12500, 12800, 13100)):
            v = self.tick(b)
            s9._port_ring["samples"][-1][0] = time.time() - (2 - i) * 60
        v = self.tick(13400)                            # 82%, 계속 오른다
        self.assertIn("banner", v)
        self.assertIsNotNone(v["eta_min"], "ETA 가 없다 — 퍼센트는 시간을 말하지 않는다")
        self.assertGreater(v["eta_min"], 0)

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
