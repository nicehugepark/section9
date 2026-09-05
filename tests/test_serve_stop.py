"""대시보드를 실제로 내리는 명령이 있는가 (REQ-20260826-036-62x6).

사용자가 "restart 도 안 되고 stop 도 안 된다"에 걸렸다. 그럴 만했다 —
`s9 serve` 는 감시자(supervisor)를 부모로 달고 뜨고, 감시자는 서버가 죽으면
되살린다. 서버만 죽이면 몇 초 뒤 부활하므로 끈 것처럼 보이지 않는다. 그런데
있는 것은 `--stop-guard`(감시자만 물린다)뿐이었고, 서버까지 내리는 명령은
아예 없었다. 사람이 매번 pkill 을 따로 쳐야 했다.

이 테스트가 지키는 것은 명령의 존재가 아니라 **순서**다: 감시자를 먼저 물리고,
물러난 것을 **확인한 뒤** 서버를 내린다. 거꾸로 하면 감시자가 그 틈에 새 서버를
띄워, 명령은 성공했는데 대시보드는 살아 있는 상태가 된다 — 사용자가 겪은 것이
정확히 그 모양이다.

실제 포트·프로세스는 건드리지 않는다. 시그널·포트 판정·감시자 판정은 전부
주입으로 갈아끼우고 **호출 순서만** 본다.

실행: python3 tests/ serve_stop
"""
import argparse
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
PORT = 19909


class ServeStop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9stop-")
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9stopmod", importlib.machinery.SourceFileLoader("s9stopmod", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def _args(self, **kw):
        base = dict(port=PORT, host="127.0.0.1", stop=False, restart=False,
                    supervise=False, stop_guard=False)
        base.update(kw)
        return argparse.Namespace(**base)

    def _run_stop(self, guard_pids, port_busy=True):
        """guard_pids: `_guard_alive` 가 부를 때마다 돌려줄 값들."""
        m = self.mod
        events = []
        pids = list(guard_pids)

        def guard_alive(port, root=None):
            v = pids.pop(0) if pids else None
            events.append(f"guard_alive->{v}")
            return v

        def signal_port(port, sig):
            events.append("signal_port")
            return 1

        busy = [port_busy]

        with mock.patch.object(m, "_guard_alive", side_effect=guard_alive), \
             mock.patch.object(m, "_signal_port", side_effect=signal_port), \
             mock.patch.object(m, "_port_busy",
                               side_effect=lambda *a, **k: busy[0]), \
             mock.patch.object(m, "_wait_port_free", return_value=True), \
             mock.patch("time.sleep", lambda *_: None):
            try:
                m.cmd_serve(self._args(stop=True))
            except SystemExit as e:
                events.append(f"die:{e.code}")
        return events

    def stop_file(self):
        return self.mod._guard_paths(PORT)["stop"]

    def setUp(self):
        try:
            os.remove(self.stop_file())
        except OSError:
            pass

    def test_t1_guard_is_stopped_before_the_server(self):
        """T1. 감시자가 먼저 물러나고 **그 다음** 서버를 내린다.

        이 순서가 뒤집히면 감시자가 그 틈에 새 서버를 띄운다 — 명령은 성공했는데
        대시보드는 살아 있는 상태가 되고, 사용자는 "stop 이 안 먹는다"로 본다.
        """
        events = self._run_stop([4242, None])
        self.assertIn("signal_port", events, events)
        self.assertLess(events.index("guard_alive->None"),
                        events.index("signal_port"),
                        f"감시자 퇴장을 확인하기 전에 서버를 죽였다: {events}")

    def test_t2_stubborn_guard_aborts_the_kill(self):
        """T2. 감시자가 안 물러나면 서버를 건드리지 않고 멈춘다.

        되살아날 것을 알면서 죽이면 '내렸다'는 거짓 보고만 남는다.
        """
        events = self._run_stop([4242] * 200)
        self.assertNotIn("signal_port", events,
                         f"물러나지 않은 감시자를 두고 서버를 죽였다: {events}")
        self.assertTrue(any(e.startswith("die:") for e in events), events)

    def test_t3_no_server_is_not_an_error(self):
        """T3. 내릴 서버가 없으면 조용히 끝난다 — 멱등이어야 두 번 쳐도 안전하다."""
        events = self._run_stop([None], port_busy=False)
        self.assertNotIn("signal_port", events, events)
        self.assertFalse(any(e.startswith("die:") for e in events), events)

    def test_t4_stop_is_a_real_flag(self):
        """T4. `--stop` 이 파서에 있다 — 없으면 사용자는 또 찾다 못 찾는다."""
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('sv.add_argument("--stop", action="store_true"', src)

    def test_t6_the_guard_is_told_by_signal_not_only_by_a_file(self):
        """T6. 중지는 **신호로** 전한다 (REQ-20260829-018).

        중지 파일만 두었더니 평상시에 `--stop` 이 늘 실패했다: 감시자는 자식이
        사는 동안 `proc.wait()` 에 잠겨 있어서 그 파일을 **자식이 죽은 뒤에야**
        본다. 서버가 멀쩡히 도는 동안에는 영원히 안 본다는 뜻이고, 그래서
        "감시자가 물러나지 않았다"가 정상 상태의 답이 되어 버렸다. 신호는 잠긴
        곳까지 닿는다.
        """
        m = self.mod
        sent = []
        with mock.patch.object(m, "_guard_alive",
                               side_effect=[4242, None, None]), \
             mock.patch.object(m, "_signal_port", return_value=1), \
             mock.patch.object(m, "_port_busy", return_value=True), \
             mock.patch.object(m, "_wait_port_free", return_value=True), \
             mock.patch("os.kill", side_effect=lambda p, s: sent.append((p, s))), \
             mock.patch("time.sleep", lambda *_: None):
            m.cmd_serve(self._args(stop=True))
        self.assertIn(4242, [p for p, _ in sent],
                      "감시자 pid 에 아무 신호도 보내지 않았다 — 파일만 두면 "
                      "서버가 사는 동안 감시자는 그것을 보지 못한다")

    def test_t7_the_guard_hears_the_signal_while_blocked(self):
        """T7. 감시자가 그 신호를 받을 채비를 하고 돈다 — 보내는 쪽만 고치면
        아무 데도 닿지 않는다."""
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        i = src.find("def serve_guard_loop(")
        self.assertGreater(i, 0)
        self.assertIn("_guard_stop_signal", src[i:i + 1500],
                      "감시 루프가 중지 신호를 받을 자리를 마련하지 않았다")
        j = src.find("def _guard_stop_signal(")
        self.assertGreater(j, 0, "_guard_stop_signal() 이 없다")
        blk = src[j:j + 1400]
        self.assertIn("SIGTERM", blk)
        self.assertNotIn("proc.terminate", blk,
                         "물러나면서 서버를 함께 죽였다 — --stop-guard 는 "
                         "서버를 살려 둔 채 감시만 놓는 명령이다")

    def test_t5_kill_path_is_shared_with_restart(self):
        """T5. `--stop` 과 `--restart` 가 같은 종료 경로를 쓴다.

        두 벌로 두면 한쪽만 고쳐지는 게 시간 문제다 (SIGTERM→유예→SIGKILL 이
        이미 SSE 장수명 연결 때문에 한 번 다듬어진 경로다).
        """
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertGreaterEqual(src.count("_signal_port("), 4, src.count)


if __name__ == "__main__":
    unittest.main()
