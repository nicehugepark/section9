"""시험이 앉은 자리는 자리를 옮기는 것이 아니다 (REQ-20260916-004-2n7g).

실측 2026-09-16 00:05:13. 9909 를 보던 감시자 59946 이 죽었고 감시 로그의 사유는
「감시 중지 신호」였다. 같은 시각 0바이트 중지 표식이 새로 생겼다 — 그 둘을 함께
만드는 자리는 `serve_sweep_others()` 하나다. 그때 사람이 한 일은 시험을 돌린 것뿐이었다.

읽어서 좁힌 경로: `s9 serve` 는 `--guard-run`·`--stop`·`--stop-guard` 가 아니면
**언제나** `serve_sweep_others(args.port)` 를 부르고, 그 뿌리는 그 프로세스의 ROOT 다.
실 저장소를 ROOT 로 가진 serve 가 9909 아닌 포트로 뜨면 그 자리에서 9909 를 거둔다.
시험 실행에서 그런 serve 가 뜨는 길은 둘 — ① 시험 모듈이
`os.environ.setdefault("S9_ROOT", tmp)` 로 뿌리를 세우는데 setdefault 라 부른 셸에
S9_ROOT 가 있으면 실 뿌리가 그대로 남는다(REQ 전용 worktree 세션은 S9_ROOT 가 본
저장소로 못박혀 있다), ② 서버를 띄우는 fixture 40여 곳 중 env 에 S9_ROOT 를 싣지
않는 자리. 둘 다 **풀 포트(18800~23999)** 로 뜬다 — 시험이 쓰는 포트는 거기서만 온다.

여기서 고정하는 계약: 풀 포트에 앉는 serve 는 아무것도 거두지 않는다. 사람이 자리를
옮기는 기동(풀 밖 포트)은 종전대로 거둔다 — 「한 저장소에는 대시보드가 하나다」
(REQ-20260915-014-62x6)는 그대로 산다.

실행: python3 tests/ sweep_scope
"""
import importlib.machinery
import importlib.util
import os
import signal
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def load():
    spec = importlib.util.spec_from_loader(
        "s9sweepscope",
        importlib.machinery.SourceFileLoader("s9sweepscope", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class SweepScope(unittest.TestCase):
    """거두는 자리를 가르는 술어 — 뿌리 안에서만, 사람의 자리에서만."""

    def setUp(self):
        self.m = load()
        self.root = tempfile.mkdtemp(prefix="s9sweepscope-")
        os.makedirs(os.path.join(self.root, "state"))
        for port in (9909, 9910):
            open(os.path.join(self.root, "state",
                              f"serve-guard.{port}.lock"), "w").close()
        self.killed = []          # (port, sig)
        self.asked = []           # 감시자에 중지를 알린 포트
        m = self.m
        m._signal_port = lambda p, sig: self.killed.append((p, sig)) or 1
        m._wait_port_free = lambda host, p, tries=20: True
        m._guard_ask_stop = \
            lambda p, pid=None, root=None: self.asked.append(p) or True
        self.gone = set()
        m._guard_alive = self._alive
        m.serveinfo_at = self._info
        self.nested = os.environ.pop("S9_TESTS_NESTED", None)

    def tearDown(self):
        if self.nested is None:
            os.environ.pop("S9_TESTS_NESTED", None)
        else:
            os.environ["S9_TESTS_NESTED"] = self.nested

    def _alive(self, port, root=None):
        """9909 에만 감시자가 있다 — 물리면 곧 물러난다."""
        if port == 9909 and port not in self.gone:
            self.gone.add(port)
            return 4242
        return None

    def _info(self, port, host="127.0.0.1", timeout=1.5):
        if port in (9909, 9910):
            return {"started": "now", "root": self.root}
        return None

    def sweep(self, keep):
        return self.m.serve_sweep_others(keep, root=self.root, wait=1)

    def stop_marker(self, port):
        return os.path.join(self.root, "state", f"serve-guard.{port}.stop")

    # ── 1. 사람의 기동은 종전대로 거둔다 ───────────────────────────────
    def test_1_a_human_move_still_sweeps(self):
        self.assertEqual(self.sweep(9910), [9909],
                         "사람이 자리를 옮기는데 옛 자리를 안 거뒀다")
        self.assertEqual(self.asked, [9909])
        self.assertEqual(self.killed, [(9909, signal.SIGTERM)])

    # ── 2. 시험이 앉는 자리는 아무것도 거두지 않는다 ────────────────────
    def test_2_a_pool_port_sweeps_nothing(self):
        said = []
        self.assertEqual(
            self.m.serve_sweep_others(18801, root=self.root, wait=1,
                                      out=said.append), [],
            "시험 포트에 앉은 서버가 사람의 대시보드를 거뒀다")
        self.assertEqual(self.killed, [], "시그널을 보냈다")
        self.assertEqual(self.asked, [], "감시자에 중지를 알렸다")
        self.assertFalse(os.path.exists(self.stop_marker(9909)),
                         "중지 표식을 남겼다 — 다음에 뜨는 감시자가 이것을 읽는다")

    # ── 3. 풀의 양 끝과 그 바로 밖 ─────────────────────────────────────
    def test_3_the_edges_of_the_pool(self):
        for port in (18800, 23999):
            with self.subTest(port=port):
                self.assertTrue(self.m.is_test_port(port),
                                f"{port} 는 풀 안이다")
        for port in (18799, 24000, 9909, 9910):
            with self.subTest(port=port):
                self.assertFalse(self.m.is_test_port(port),
                                 f"{port} 는 사람의 자리다")

    # ── 4. 안쪽 시험 실행은 바깥 세계를 건드리지 않는다 ─────────────────
    def test_4_nested_test_run_sweeps_nothing(self):
        """뿌리를 묻지 않고 도는 기동 — 실제 `s9 serve` 가 이 자리다."""
        os.environ["S9_TESTS_NESTED"] = "1"
        self.m.ROOT = self.root
        self.assertEqual(self.m.serve_sweep_others(9910, wait=1), [],
                         "안쪽 시험 실행이 바깥의 대시보드를 거뒀다")
        self.assertEqual(self.killed, [])
        self.assertEqual(self.asked, [])

    # ── 4b. 뿌리를 명시로 받은 호출은 그 계약을 잴 수 있다 ───────────────
    def test_4b_an_explicit_root_is_still_measurable(self):
        """안쪽 실행이어도 뿌리를 지정한 호출은 종전대로 돈다 — 유닛 시험의 자리."""
        os.environ["S9_TESTS_NESTED"] = "1"
        self.assertEqual(self.sweep(9910), [9909],
                         "뿌리를 지정한 호출까지 막으면 계약을 잴 수 없다")

    # ── 5. 뿌리가 다르면 보이지도 않는다 ────────────────────────────────
    def test_5_another_root_is_invisible(self):
        """임시 뿌리의 sweep 은 실 저장소의 감시자 잠금을 세지 않는다."""
        empty = tempfile.mkdtemp(prefix="s9sweepscope-other-")
        os.makedirs(os.path.join(empty, "state"))
        self.assertEqual(self.m._guard_ports(empty), [],
                         "남의 뿌리의 잠금을 내 것으로 셌다")
        self.assertEqual(self.m.serve_sweep_others(9910, root=empty, wait=1), [])
        self.assertEqual(self.killed, [])

    # ── 6. 검사가 sweep 안에 선다 ──────────────────────────────────────
    def test_6_the_guard_stands_inside_the_sweep(self):
        """호출자마다 따로 두면 새로 드는 호출자를 못 지킨다 — 함수 안에 하나."""
        src = open(S9 + ".py", encoding="utf-8").read()
        i = src.index("def serve_sweep_others(")
        body = src[i:i + 3000]
        self.assertIn("is_test_port(keep_port)", body,
                      "시험 자리 검사가 sweep 안에 없다")
        self.assertIn("S9_TESTS_NESTED", body,
                      "안쪽 시험 실행 검사가 sweep 안에 없다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
