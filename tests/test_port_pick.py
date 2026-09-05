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
        # 남의 임시 루트에서 돈다(실측 2026-09-05: project_api·whoami 등 8파일 붉음).
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_PORT")}
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_PORT", None)
        spec = importlib.util.spec_from_loader(
            "s9_portpick", importlib.machinery.SourceFileLoader("s9_portpick", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

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
