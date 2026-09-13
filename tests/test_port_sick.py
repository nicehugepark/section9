"""듣기만 하고 답하지 않는 포트를 스스로 버리는가 (REQ-20260912-003).

주인 보고 2026-09-12 22:44: 「9909 포트로 대시보드가 왜 자꾸 접속이 끊기는거지?
브라우저 새로 고침을 하면 한참을 실패하다가 연결이 되기도 하고.」

잰 결과는 **포트 하나가 아픈 것**이었다 — 같은 코드가 9931 에서는 20/20 답하는데
9909 는 2/20 이었고 나머지는 붙자마자 리셋이었다(맨살 stdlib 서버도 다른 포트에서는
멀쩡했고, `s9 serve --restart` 로도 안 고쳐졌다). DOC-20260906-003 이 적은 「닫힌
리스너의 공개가 남아 붙은 뒤 끊는다」의 만성판이다.

감시자는 그동안 **누가 듣고 있는지**만 봤다(`_port_busy`). 그래서 아픈 포트 위에서
열세 시간을 자고, 사람이 물어서야 알았다.

여기서 고정하는 계약은 셋이다.
  ① 감시자가 간격을 두고 **왕복**을 재고, 잇달아 두 번 아프면 포트를 옮긴다.
  ② 한 번의 리셋으로는 안 옮긴다 — 재기동 직후 62초 창에도 같은 지문이 나온다.
  ③ 아프다고 적어 둔 포트로는 **돌아가지 않는다**(기록이 살아 있는 동안).

실행: python3 tests/ port_sick
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(name, root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


RESET = {"ready": False, "mine": None, "attempts": 1,
         "why": "리셋 — 우리 자리에서의 리셋은 점거의 증거다 (재시도하지 않는다)"}
GHOST = {"ready": False, "mine": None, "attempts": 1,
         "why": "연결은 됐지만 HTTP 응답이 없다 (중계가 받아준 가짜 연결)"}
REFUSED = {"ready": False, "mine": None, "attempts": 3,
           "why": "거부 — 아무도 듣지 않는다"}
OK = {"ready": True, "mine": True, "attempts": 1, "why": ""}


class ASickPortIsWrittenDown(unittest.TestCase):
    """① 아픈 포트의 기록 — 언제·왜, 그리고 기간이 지나면 잊는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9sick-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.m = _load("s9_sick_" + os.path.basename(self.root), self.root)

    def test_s1_mark_and_read(self):
        self.m.port_sick_mark(9909, "리셋", self.root, now=1000.0)
        rec = self.m.port_sick_recent(9909, self.root, now=1001.0)
        self.assertTrue(rec, "적어 둔 포트를 못 읽는다")
        self.assertIn("리셋", rec["why"])

    def test_s2_the_record_expires(self):
        self.m.port_sick_mark(9909, "리셋", self.root, now=1000.0)
        later = 1000.0 + self.m.PORT_SICK_TTL + 1
        self.assertIsNone(self.m.port_sick_recent(9909, self.root, now=later),
                          "영영 피하면 사람이 기억하는 주소로 못 돌아간다")

    def test_s3_other_ports_are_untouched(self):
        self.m.port_sick_mark(9909, "리셋", self.root, now=1000.0)
        self.assertIsNone(self.m.port_sick_recent(9912, self.root, now=1001.0))

    def test_s4_the_file_is_machine_state_not_a_document(self):
        self.m.port_sick_mark(9909, "리셋", self.root, now=1000.0)
        path = os.path.join(self.root, "state", "port-sick.json")
        self.assertTrue(os.path.exists(path), "기계 상태는 state/ 에 산다")
        with open(path, encoding="utf-8") as f:
            self.assertIn("9909", json.load(f))


class TheGuardMeasuresTheRoundTrip(unittest.TestCase):
    """② 감시자는 듣는 것이 아니라 **답하는 것**을 본다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9sickg-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.m = _load("s9_sickg_" + os.path.basename(self.root), self.root)
        self.m._port_busy = lambda h, p, timeout=0.4: True   # 늘 누군가 듣는다
        self.slept = []

    def _run(self, answers, rounds=6, pick=9912):
        seq = list(answers)
        seen = []

        def ready(h, p):
            seen.append(p)
            return seq.pop(0) if seq else OK
        clock = iter([i * 1000.0 for i in range(rounds + 4)])
        return self.m.serve_guard_loop(
            9909, host="127.0.0.1", root=self.root,
            spawn=lambda: self.fail("듣고 있는데 서버를 또 띄웠다"),
            sleep=self.slept.append, clock=lambda: next(clock),
            max_rounds=rounds, _ready=ready, _pick=lambda: pick), seen

    def test_g1_a_healthy_port_is_left_alone(self):
        self._run([OK, OK, OK])
        self.assertIsNone(self.m.port_sick_recent(9909, self.root),
                          "멀쩡한 포트를 아프다고 적었다")
        self.assertEqual(self.m.s9_port(self.root), 9909)

    def test_g2_one_reset_is_not_enough(self):
        # 재기동 직후 62초 창에도 같은 지문이 나온다 — 한 번은 사고가 아니다.
        self._run([RESET, OK, RESET])
        self.assertIsNone(self.m.port_sick_recent(9909, self.root),
                          "한 번의 리셋으로 포트를 버렸다")

    def test_g3_two_in_a_row_moves_the_port(self):
        self._run([RESET, RESET])
        rec = self.m.port_sick_recent(9909, self.root)
        self.assertTrue(rec, "잇달아 아픈데 적지 않았다")
        self.assertEqual(self.m.s9_port(self.root), 9912,
                         "아픈 자리에 그대로 앉아 있다 — 사람이 또 물어야 한다")
        with open(os.path.join(self.root, "state", "serve-guard.log"),
                  encoding="utf-8") as f:
            log = f.read()
        self.assertIn("port-sick", log, "옮긴 사실이 기록에 없다")
        self.assertIn("9912", log, "어디로 옮겼는지 안 적힌다")

    def test_g4_a_fake_connection_counts_too(self):
        self._run([GHOST, GHOST])
        self.assertTrue(self.m.port_sick_recent(9909, self.root),
                        "중계가 받아 준 가짜 연결도 같은 갈래다")

    def test_g5_refusal_is_not_sickness(self):
        # 아무도 안 듣는 것은 되살리기의 몫이다 — 포트를 버릴 일이 아니다.
        self._run([REFUSED, REFUSED])
        self.assertIsNone(self.m.port_sick_recent(9909, self.root))


class ThePickerAvoidsASickPort(unittest.TestCase):
    """③ 아프다고 적어 둔 자리로는 돌아가지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9sickp-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.m = _load("s9_sickp_" + os.path.basename(self.root), self.root)
        self._prev = os.environ.pop("S9_PORT", None)

    def tearDown(self):
        if self._prev is not None:
            os.environ["S9_PORT"] = self._prev

    def _port_file(self, value):
        with open(os.path.join(self.root, "state", "port"), "w",
                  encoding="utf-8") as f:
            f.write(str(value))

    def test_p1_the_sick_base_port_is_not_reclaimed(self):
        # 「9909 가 비면 돌아온다」(REQ-20260908-064)는 규칙이 아픈 자리에서는
        # 어제의 사고를 되풀이한다.
        self._port_file(9912)
        with open(os.path.join(self.root, "state", "port.auto"), "w",
                  encoding="utf-8") as f:
            f.write("sick x\n")
        self.m.port_sick_mark(9909, "리셋", self.root)
        port, why = self.m.pick_dashboard_port(
            root=self.root, _info=lambda p: None,
            _bindable=lambda p: True, _next=lambda: 9913,
            _foreign=lambda p: None)
        self.assertEqual(port, 9912, "아픈 기본 포트로 돌아갔다")
        self.assertEqual(why, "sick-base")

    def test_p2_a_sick_current_port_moves_on(self):
        self._port_file(9909)
        self.m.port_sick_mark(9909, "리셋", self.root)
        port, why = self.m.pick_dashboard_port(
            root=self.root, _info=lambda p: None,
            _bindable=lambda p: True, _next=lambda: 9913,
            _foreign=lambda p: None)
        self.assertEqual((port, why), (9913, "sick"))
        self.assertEqual(self.m.s9_port(self.root), 9913, "옮긴 포트를 안 적었다")

    def test_p3_a_healthy_port_is_kept(self):
        self._port_file(9909)
        port, why = self.m.pick_dashboard_port(
            root=self.root, _info=lambda p: None,
            _bindable=lambda p: True, _next=lambda: 9913,
            _foreign=lambda p: None)
        self.assertEqual((port, why), (9909, "free"))


if __name__ == "__main__":
    unittest.main()
