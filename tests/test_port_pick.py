"""포트가 남의 것이면 다음 포트로 (REQ-20260905-016).

같은 리눅스 서버에 여러 사람이 각자 section9 을 설치한다 — 9909 에 남의 서버가
먼저 앉아 있으면 내 것은 9910 부터 빈 자리로 가고, 그 포트를 state/port 에 적어
그 뒤의 호출·훅·화면 링크가 따라간다. 내 서버가 떠 있으면 종전대로 재사용한다.

실행: python3 tests/ port_pick
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class PickPort(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9port-")
        # 환경은 빌려 쓰고 돌려준다 — 같은 샤드의 다음 시험이 S9_ROOT 를 물려받으면
        # 남의 임시 루트에서 돈다(실측 2026-09-05: project_api·whoami 등 8파일 실패).
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_PORT")}
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_PORT", None)
        spec = importlib.util.spec_from_loader(
            "s9_portpick", importlib.machinery.SourceFileLoader("s9_portpick", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        # 윈도우 쪽 목록은 이 파일의 관심이 아니다 — 있는 그대로 두면 WSL 에서 netstat.exe
        # 를 실제로 부른다. 그 갈래는 test_win_neighbor 가 _foreign 주입으로 잰다.
        self.m.windows_listen_owner = lambda port, _lines=None: None

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _port_file(self):
        try:
            return open(os.path.join(self.root, "state", "port"), encoding="utf-8").read().strip()
        except OSError:
            return ""

    def test_p1_my_server_is_reused(self):
        """P1. 내 저장소의 서버가 답하면 그 포트 그대로 — 새로 띄우지 않는다."""
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: {"started": "x", "root": self.root})
        self.assertEqual((port, why), (9909, "mine"))
        self.assertEqual(self._port_file(), "")

    def test_p2_someone_elses_section9_moves_me_to_the_next_open_port(self):
        """P2. 다른 저장소의 section9 이 답하면 9910~ 의 빈 포트로 가고 state/port 에 적는다."""
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: {"started": "x", "root": "/home/other/section9"},
            _next=lambda: 9912)
        self.assertEqual((port, why), (9912, "other"))
        self.assertEqual(self._port_file(), "9912")
        self.assertEqual(self.m.s9_port(self.root), 9912, "그 뒤의 호출이 새 포트를 따르지 않는다")

    def test_p6_a_rootless_answer_from_a_stranger_moves_me(self):
        """P6. 응답에 root 가 없고 내 저장소의 기동 흔적도 없으면 남의 것 — 옮긴다.

        원격 리눅스 실측 2026-09-06: 다른 리눅스 사용자의 옛 section9 이 9909 에 앉아 있었고,
        그 옛 판은 serveinfo 에 root 를 안 실었다. 예전 조항은 그것을 내 것으로 봤다.
        """
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: {"started": "x"}, _next=lambda: 9910)
        self.assertEqual((port, why), (9910, "other"))
        self.assertEqual(self._port_file(), "9910")

    def test_p7_a_rootless_answer_from_my_own_launch_is_still_mine(self):
        """P7. 같은 root 없는 응답이라도 내 저장소가 그 포트에 띄운 흔적(살아 있는 pid)이 있으면 내 것."""
        import json
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        with open(os.path.join(self.root, "state", "serve-code.json"), "w", encoding="utf-8") as f:
            json.dump({"port": 9909, "pid": os.getpid(), "started": "x"}, f)
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: {"started": "x"}, _next=lambda: 9910)
        self.assertEqual((port, why), (9909, "mine"))
        self.assertEqual(self._port_file(), "")
        # 흔적의 포트가 다르면 흔적이 아니다
        with open(os.path.join(self.root, "state", "serve-code.json"), "w", encoding="utf-8") as f:
            json.dump({"port": 9911, "pid": os.getpid(), "started": "x"}, f)
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: {"started": "x"}, _next=lambda: 9910)
        self.assertEqual((port, why), (9910, "other"))

    def test_p3_a_busy_port_moves_and_a_free_port_stays(self):
        """P3. 답은 없는데 bind 가 안 되면 옮기고, 비어 있으면 그대로."""
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: None, _bindable=lambda p: False,
            _next=lambda: 9911)
        self.assertEqual((port, why), (9911, "busy"))
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: None, _bindable=lambda p: True)
        self.assertEqual((port, why), (9909, "free"))


    def test_p5_an_auto_moved_port_comes_back_when_the_default_is_mine_again(self):
        """P5. 자동으로 옮긴 포트는 기본 포트에 내 서버가 답하면 되돌아온다 — 표식(port.auto)이 재료."""
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: {"started": "x", "root": "/other"},
            _next=lambda: 9913)
        self.assertEqual((port, why), (9913, "other"))
        self.assertTrue(os.path.exists(os.path.join(self.root, "state", "port.auto")))
        port, why = self.m.pick_dashboard_port(
            None, root=self.root, _info=lambda p: {"started": "x", "root": self.root})
        self.assertEqual((port, why), (9909, "mine"))
        self.assertEqual(self._port_file(), "", "되돌아왔는데 state/port 가 남아 있다")

    def _moved_to(self, port):
        st = os.path.join(self.root, "state")
        os.makedirs(st, exist_ok=True)
        with open(os.path.join(st, "port"), "w") as f:
            f.write(str(port))
        with open(os.path.join(st, "port.auto"), "w") as f:
            f.write("other x\n")

    def test_p11_an_auto_moved_port_comes_back_when_the_default_is_free(self):
        """P11. 9909 가 비어 있으면 돌아온다 (REQ-20260908-064) — 내 서버가 답할 때만
        돌아오던 것을 넓혔다. 사용자 물음 2026-09-08: 「9909가 비게되면 9909로 돌아오면 안되나」."""
        self._moved_to(9913)
        port, why = self.m.pick_dashboard_port(
            None, root=self.root, _info=lambda p: None, _bindable=lambda p: True)
        self.assertEqual((port, why), (9909, "free"))
        self.assertEqual(self._port_file(), "", "돌아왔는데 state/port 가 남아 있다")
        self.assertFalse(os.path.exists(os.path.join(self.root, "state", "port.auto")))

    def test_p12_stays_while_my_server_still_lives_on_the_moved_port(self):
        """P12. 옮겨 앉은 포트에 내 서버가 살아 있으면 9909 가 비어 있어도 옮기지 않는다
        — 돌아오면 대시보드가 둘이 된다."""
        self._moved_to(9913)
        port, why = self.m.pick_dashboard_port(
            None, root=self.root,
            _info=lambda p: {"started": "x", "root": self.root} if p == 9913 else None,
            _bindable=lambda p: True)
        self.assertEqual((port, why), (9913, "mine"))
        self.assertEqual(self._port_file(), "9913")

    def test_p13_a_busy_default_keeps_the_moved_port(self):
        """P13. 9909 가 답은 없는데 bind 가 안 되면(다른 프로그램) 그대로 옮겨 앉은 자리다."""
        self._moved_to(9913)
        port, why = self.m.pick_dashboard_port(
            None, root=self.root, _info=lambda p: None,
            _bindable=lambda p: p != 9909)
        self.assertEqual((port, why), (9913, "free"))

    def test_p4_a_pinned_port_is_never_moved(self):
        """P4. 사람이 S9_PORT 로 못박았으면 옮기지 않는다 — 그건 사람의 결정이다."""
        os.environ["S9_PORT"] = "9909"
        try:
            port, why = self.m.pick_dashboard_port(
                9909, root=self.root, _info=lambda p: {"started": "x", "root": "/other"},
                _next=lambda: 9915)
            self.assertEqual(port, 9909)
        finally:
            os.environ.pop("S9_PORT", None)


if __name__ == "__main__":
    unittest.main()

    # P8. --stop 은 자동으로 옮겨 적은 포트를 잊는다 — 다음 기동이 기본 포트부터 (REQ-20260906-083)
    def test_p8_stop_forgets_an_auto_moved_port(self):
        st = os.path.join(self.root, "state"); os.makedirs(st, exist_ok=True)
        open(os.path.join(st, "port"), "w").write("9910"); open(os.path.join(st, "port.auto"), "w").write("busy")
        self.assertTrue(self.m._forget_auto_port(self.root))
        self.assertFalse(os.path.exists(os.path.join(st, "port")))
        # 표식 없는 state/port 는 옛 코드의 자동 이동이다 — 잊는다 (맥 실측 2026-09-06 14:44)
        open(os.path.join(st, "port"), "w").write("9910")
        self.assertTrue(self.m._forget_auto_port(self.root))
        self.assertFalse(os.path.exists(os.path.join(st, "port")))
        # 사람이 --port 로 정한 포트(port.pinned)는 잊지 않는다
        self.m._pin_port(9931, self.root)
        self.assertFalse(self.m._forget_auto_port(self.root))
        self.assertEqual(open(os.path.join(st, "port")).read(), "9931")

    # P9. 사람이 --port 로 정하면 state/port 에 남고 자동 이동 표식은 지워진다
    def test_p9_an_explicit_port_is_pinned(self):
        st = os.path.join(self.root, "state"); os.makedirs(st, exist_ok=True)
        open(os.path.join(st, "port.auto"), "w").write("busy")
        self.assertTrue(self.m._pin_port(9909, self.root))
        self.assertEqual(open(os.path.join(st, "port")).read(), "9909")
        self.assertFalse(os.path.exists(os.path.join(st, "port.auto")))
        self.assertTrue(os.path.exists(os.path.join(st, "port.pinned")))

    # P10. 방금 닫은 포트(TIME_WAIT 연결이 남은 포트)는 free 다 — 실제 서버와 같은 조건으로 잰다 (REQ-20260906-085)
    def test_p10_a_just_closed_port_is_still_bindable(self):
        import socket, threading
        import sys as _sys; _sys.path.insert(0, HERE)
        import portpool
        srv = portpool.pool_socket(); port = srv.getsockname()[1]
        def serve_one():
            c, _ = srv.accept(); c.recv(1); c.close()      # 서버 쪽이 먼저 닫는다 → 서버 쪽 TIME_WAIT
        t = threading.Thread(target=serve_one); t.start()
        cl = socket.create_connection(("127.0.0.1", port)); cl.sendall(b"x"); t.join(2); cl.close(); srv.close()
        self.assertTrue(self.m.port_bindable(port), "TIME_WAIT 만으로 포트를 남의 것으로 읽는다")
        port2, why = self.m.pick_dashboard_port(port, root=self.root, _info=lambda p: None, _next=lambda: port + 1)
        self.assertEqual((port2, why), (port, "free"))

