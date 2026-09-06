"""`s9 serve --restart` 는 감시자가 있으면 되살리기를 맡기고 **돌아온다** (REQ-20260906-006-2n7g).

맥 실측 2026-09-06 14:34: `s9 serve --restart` 가 옛 서버에 SIGTERM 을 보낸 뒤 제 프로세스에서
서버를 띄웠다. 그 명령은 돌아오지 않으니 에이전트의 셸에서는 120초 뒤 백그라운드로 밀렸고,
옛 감시자(--supervise)는 살아남아 「이미 감시 중」만 찍었다 — 포트 주인은 앞단 프로세스,
감시자는 남의 서버를 지켜보는 모양이 됐다. 세션이 끝나면 앞단 서버가 함께 죽는다.

감시자의 설계는 「--restart 가 포트를 잡으면 양보한다」였다. 그 설계는 사람이 터미널에서
앞단 서버를 원할 때만 맞고, 훅·규약이 「s9 serve --restart 로 다시 띄워라」라고 시키는 자리
(에이전트 셸)에서는 틀린다. 그래서 갈래를 하나 더 둔다: **감시자가 있으면 옛 서버만 내리고
감시자가 되살린 새 서버가 답할 때까지 기다린 뒤 돌아온다.** 감시자가 없으면 종전대로 앞단.

실포트·실프로세스는 건드리지 않는다. 감시자 판정·포트 판정·시그널·serveinfo 는 전부
주입으로 갈아끼우고 호출 순서와 반환만 본다.

실행: python3 tests/ serve_restart
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
S9_SRC = S9 + ".py"
PORT = 19919


class _Foreground(BaseException):
    """앞단 기동 경로에 들어섰다는 표지 — link_audit 이 그 경로의 첫 걸음이다.
    (cmd_serve 가 link_audit 을 `except Exception` 으로 감싸므로 BaseException 이어야 새지 않는다)"""


class ServeRestart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9restart-")
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9restartmod", importlib.machinery.SourceFileLoader("s9restartmod", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _args(self, **kw):
        base = dict(port=PORT, host="127.0.0.1", stop=False, restart=True,
                    supervise=False, stop_guard=False, guard_run=False)
        base.update(kw)
        return argparse.Namespace(**base)

    def _run(self, guard, infos, busy_after_kill=False):
        """guard: `_guard_alive` 의 답. infos: `serveinfo_at` 이 차례로 돌려줄 값들
        (다 쓰면 마지막 값을 반복). 반환: 사건 목록."""
        m = self.mod
        events = []
        seq = list(infos)

        def serveinfo(port, host="127.0.0.1", timeout=1.5):
            v = seq.pop(0) if len(seq) > 1 else seq[0]
            events.append(f"serveinfo->{(v or {}).get('started')}")
            return v

        def signal_port(port, sig):
            events.append(f"signal_port:{int(sig)}")
            return 1

        def wait_free(host, port, tries=20):
            events.append("wait_port_free")
            return not busy_after_kill

        def link_audit(fix=False):
            events.append("foreground")
            raise _Foreground()

        with mock.patch.object(m, "_guard_alive", return_value=guard), \
             mock.patch.object(m, "_port_busy", return_value=True), \
             mock.patch.object(m, "_signal_port", side_effect=signal_port), \
             mock.patch.object(m, "_wait_port_free", side_effect=wait_free), \
             mock.patch.object(m, "serveinfo_at", side_effect=serveinfo), \
             mock.patch.object(m, "link_audit", side_effect=link_audit), \
             mock.patch.object(m, "serve_port_for", return_value=(PORT, "restart")), \
             mock.patch("time.sleep", lambda *_: None):
            try:
                m.cmd_serve(self._args())
                events.append("returned")
            except _Foreground:
                pass
            except SystemExit as e:
                events.append(f"die:{e.code}")
        return events

    OLD = {"started": "2026-09-06T14:20:32+09:00", "pid": 81012}
    NEW = {"started": "2026-09-06T14:34:20+09:00", "pid": 84999}

    def test_r1_guard_revives_and_the_command_returns(self):
        """r1. 감시자가 있으면 옛 서버만 내리고, 되살아난 서버를 확인한 뒤 돌아온다."""
        ev = self._run(guard=4242, infos=[self.OLD, None, self.NEW])
        self.assertEqual(ev[0], f"serveinfo->{self.OLD['started']}", ev)
        self.assertIn("signal_port:15", ev, ev)
        self.assertIn(f"serveinfo->{self.NEW['started']}", ev, ev)
        self.assertEqual(ev[-1], "returned", ev)
        self.assertNotIn("foreground", ev, "감시자가 있는데 앞단 서버를 띄웠다")

    def test_r2_without_a_guard_the_old_path_stays(self):
        """r2. 감시자가 없으면(윈도우처럼 fcntl 이 없는 판 포함) 종전대로 앞단 기동."""
        ev = self._run(guard=None, infos=[None])
        self.assertIn("signal_port:15", ev, ev)
        self.assertIn("wait_port_free", ev, ev)
        self.assertEqual(ev[-1], "foreground", ev)

    def test_r3_a_guard_that_does_not_revive_is_an_error_not_a_hang(self):
        """r3. 상한 안에 새 서버가 답하지 않으면 사유를 말하고 끝난다."""
        ev = self._run(guard=4242, infos=[self.OLD, None])
        self.assertTrue(ev[-1].startswith("die:"), ev)
        self.assertNotIn("foreground", ev, ev)
        self.assertNotIn("returned", ev, ev)

    def test_r4_an_old_server_without_serveinfo_still_counts_as_revived(self):
        """r4. 옛 서버가 serveinfo 를 못 주던 상태여도 새 서버가 답하면 성공이다."""
        ev = self._run(guard=4242, infos=[None, None, self.NEW])
        self.assertEqual(ev[-1], "returned", ev)

    def test_r5_the_restart_branch_asks_the_guard_first(self):
        """r5. 소스 회귀 — --restart 갈래가 _guard_alive 를 묻는다."""
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        anchor = ('if _port_busy(args.host, args.port):\n'
                  '        if getattr(args, "restart", False):\n')
        i = src.find(anchor)
        self.assertGreater(i, 0, "cmd_serve 의 --restart 갈래를 못 찾았다")
        j = src.find("_signal_port(", i)
        self.assertGreater(j, 0)
        self.assertIn("_guard_alive(", src[i:j],
                      "--restart 가 감시자를 묻지 않고 곧장 서버를 내린다")


if __name__ == "__main__":
    unittest.main()
