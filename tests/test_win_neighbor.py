"""한 노트북의 윈도우 네이티브 section9 과 WSL section9 이 부딪히지 않는다 (REQ-20260906-055).

WSL 리스너는 윈도우 127.0.0.1 로 중계되지만 윈도우 리스너는 WSL 안에서 보이지
않는다 — bind 는 되고 답은 없어 `free` 로 읽혔다. WSL 에서는 윈도우 목록을 한 번
더 보고, 두 화면이 다 「section9」이라 whoami 가 root 경로와 OS 를 함께 준다.

실행: python3 tests/ win_neighbor
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(name):
    spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class WindowsNeighbor(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9winnb-")
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_PORT")}
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_PORT", None)
        self.m = _load("s9_winnb")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    # N1. 윈도우 쪽 프로그램이 9909 를 듣는다 → bind 는 되지만 옮긴다
    def test_n1_a_windows_listener_moves_me_even_though_bind_works(self):
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: None, _bindable=lambda p: True,
            _foreign=lambda p: (4242, "python.exe") if p == 9909 else None,
            _next=lambda: 9910)
        self.assertEqual((port, why), (9910, "windows"))
        with open(os.path.join(self.root, "state", "port"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "9910")

    # N2. 소유자가 WSL 중계(dllhost)면 우리 쪽 흔적이다 — 그대로 free
    def test_n2_a_relay_owner_is_not_a_neighbor(self):
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: None, _bindable=lambda p: True,
            _foreign=lambda p: (777, "dllhost.exe"))
        self.assertEqual((port, why), (9909, "free"))

    # N3. 목록 읽기 — 듣는 줄은 상대 주소가 :0 (상태 낱말은 언어팩을 탄다), 이름은 tasklist CSV
    def test_n3_owner_is_read_from_netstat_and_tasklist(self):
        calls = []

        def lines(argv):
            calls.append(argv[0])
            if argv[0].endswith("netstat.exe"):
                return ["  TCP    0.0.0.0:9909    0.0.0.0:0    수신 대기    4242",
                        "  TCP    127.0.0.1:9909  127.0.0.1:5   ESTABLISHED  99"]
            return ['"python.exe","4242","Console","1","40,000 K"']
        with unittest.mock.patch.object(self.m, "os_platform", lambda: "WSL"), \
                unittest.mock.patch.object(self.m.os.path, "exists", lambda p: True):
            self.assertEqual(self.m.windows_listen_owner(9909, _lines=lines), (4242, "python.exe"))
            self.assertIsNone(self.m.windows_listen_owner(9910, _lines=lines))
        # WSL 이 아니면 아무것도 묻지 않는다
        with unittest.mock.patch.object(self.m, "os_platform", lambda: "Linux"):
            self.assertIsNone(self.m.windows_listen_owner(9909, _lines=lines))

    # N2b. 이름을 못 읽은 소유자는 남이 아니다 — 모르는 것을 「남」으로 읽지 않는다
    def test_n2b_an_owner_without_a_name_is_not_a_neighbor(self):
        port, why = self.m.pick_dashboard_port(
            9909, root=self.root, _info=lambda p: None, _bindable=lambda p: True,
            _foreign=lambda p: (777, ""))
        self.assertEqual((port, why), (9909, "free"))

    # N5. --restart 는 내 포트를 다시 띄우라는 뜻 — 옛 서버가 늦게 답해도 옮기지 않는다
    def test_n5_restart_never_moves_the_port(self):
        import types
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        with open(os.path.join(self.root, "state", "port"), "w", encoding="utf-8") as f:
            f.write("9931")
        boom = lambda: (_ for _ in ()).throw(AssertionError("restart 가 포트를 골랐다"))
        a = types.SimpleNamespace(port=None, restart=True)
        self.assertEqual(self.m.serve_port_for(a, _pick=boom), (9931, "restart"))
        a = types.SimpleNamespace(port=9944, restart=True)
        self.assertEqual(self.m.serve_port_for(a, _pick=boom), (9944, "given"))
        a = types.SimpleNamespace(port=None, restart=False)
        self.assertEqual(self.m.serve_port_for(a, _pick=lambda: (9910, "busy")), (9910, "busy"))

    # N4. whoami 가 root 경로와 OS 를 준다 — 두 화면을 가르는 재료
    def test_n4_whoami_says_which_root_and_os(self):
        with unittest.mock.patch.object(self.m, "resolve_user", lambda *a, **k: "nobody-here"):
            w = self.m.whoami_info()
        self.assertEqual(os.path.realpath(w["root"]), os.path.realpath(self.root))
        self.assertIn(w["os"], ("Linux", "WSL", "macOS", "Windows"))
        self.assertEqual(w["workspace"], os.path.basename(self.root))


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
