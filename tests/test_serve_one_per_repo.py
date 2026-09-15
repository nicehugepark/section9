"""한 저장소에는 대시보드가 하나다 (REQ-20260915-014-62x6).

주인 지적 2026-09-15 13:26: 「지금 9909, 9910, 9911가 다 떠있다. 어떻게 다 떠있게
됐는지 알수가 없네. wsl에서도 하나만 떠야하고, 윈도우에서도 하나만 떠야하는거
아니야?」 — 실측: 9909(11:02 기동)와 9910(13:06)이 **같은 저장소**를 쓰고 있었고
9911 은 Windows 의 다른 폴더라 별개였다. 원인은 감시자의 멱등 키가 **포트**라는
것이다: 포트를 옮기면 옛 포트의 감시자가 남아 옛 서버를 계속 되살린다.

계약: 사람이 부른 기동과 `--stop` 이 **다른 포트에 남은 이 저장소의 대시보드를
거둔다** — 감시자를 먼저 물리고, 서버를 내리고, 포트가 풀릴 때까지 확인한다.
다른 저장소의 것은 건드리지 않는다.

실행: python3 tests/ serve_one_per_repo
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
        "s9one", importlib.machinery.SourceFileLoader("s9one", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class OneDashboardPerRepo(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.root = tempfile.mkdtemp(prefix="s9one-")
        os.makedirs(os.path.join(self.root, "state"))
        for port in (9909, 9910, 9911):
            open(os.path.join(self.root, "state",
                              f"serve-guard.{port}.lock"), "w").close()
        self.killed = []          # (port, sig)
        self.asked = []           # 감시자에 중지를 알린 포트
        self.freed = True         # SIGTERM 으로 포트가 풀리는가
        m = self.m
        m._signal_port = lambda p, sig: self.killed.append((p, sig)) or 1
        m._wait_port_free = lambda host, p, tries=20: self.freed
        m._guard_ask_stop = lambda p, pid=None, root=None: self.asked.append(p) or True

    def guards(self, live):
        """live 에 든 포트에만 감시자가 있다 — 물리면 곧 물러난다."""
        gone = set()

        def alive(port, root=None):
            if port in live and port not in gone:
                gone.add(port)         # 다음 물음에는 물러나 있다
                return 4242
            return None
        self.m._guard_alive = alive

    def servers(self, mine, other=()):
        def info(port, host="127.0.0.1", timeout=1.5):
            if port in mine:
                return {"started": "now", "root": self.root}
            if port in other:
                return {"started": "now", "root": os.path.join(self.root, "다른곳")}
            return None
        self.m.serveinfo_at = info

    # P1. 다른 포트의 내 대시보드를 거둔다 — 감시자 먼저, 그다음 서버
    def test_p1_the_other_port_of_my_repo_is_swept(self):
        self.guards(live={9909})
        self.servers(mine={9909, 9910})
        got = self.m.serve_sweep_others(9910, root=self.root, wait=1)
        self.assertEqual(got, [9909], "다른 포트의 내 대시보드를 못 거뒀다")
        self.assertEqual(self.asked, [9909], "감시자를 먼저 물리지 않았다")
        self.assertEqual(self.killed, [(9909, signal.SIGTERM)])
        self.assertTrue(os.path.exists(os.path.join(
            self.root, "state", "serve-guard.9909.stop")), "중지 파일이 없다")
        # 지금 앉을 자리는 건드리지 않는다
        self.assertNotIn(9910, [p for p, _ in self.killed])

    # P2. 다른 저장소의 것은 남의 것이다
    def test_p2_another_repo_on_another_port_is_left_alone(self):
        self.guards(live=set())
        self.servers(mine={9910}, other={9911})
        self.assertEqual(self.m.serve_sweep_others(9910, root=self.root, wait=1), [])
        self.assertEqual(self.killed, [])
        self.assertEqual(self.asked, [])

    # P3. SIGTERM 으로 안 풀리면 올린다 — 안 죽는 서버는 거둔 것이 아니다
    def test_p3_a_server_that_ignores_sigterm_is_escalated(self):
        self.freed = False
        self.guards(live=set())
        self.servers(mine={9909, 9910})
        self.assertEqual(self.m.serve_sweep_others(9910, root=self.root, wait=1), [9909])
        self.assertEqual([s for _, s in self.killed],
                         [signal.SIGTERM, self.m.sig_kill()],
                         "포트가 안 풀렸는데 SIGTERM 하나로 끝냈다")

    # P4. 감시자만 남고 서버가 없는 자리도 거둔다 — 두면 그 감시자가 서버를 띄운다
    def test_p4_a_lone_guard_is_stopped_too(self):
        self.guards(live={9909})
        self.servers(mine={9910})
        self.assertEqual(self.m.serve_sweep_others(9910, root=self.root, wait=1), [9909])
        self.assertEqual(self.asked, [9909])
        self.assertEqual(self.killed, [], "서버가 없는 자리에 시그널을 보냈다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
