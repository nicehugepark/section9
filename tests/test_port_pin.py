"""`--port` 만으로는 포트가 못박히지 않는다 (REQ-20260913-004).

주인 지적 2026-09-13 17:26: 「9912로 고정하라고 한적없다. 처음부터 9909였고, 이미
사용 중인 포트라면 +1을 하고 같은 사용자가 9909를 사용하고 있다면 이미 실행 중이니
다시 서버를 띄울 필요가 없는게 규칙이었던거야.」

전날 리드가 `s9 serve --restart --port 9912` 로 옮긴 것이 `port.pinned` 로 굳어
다음 `s9 code` 가 9909 로 돌아오지 못했다. `--port` 를 친 것이 사람인지 에이전트인지
코드는 가를 수 없다 — 그래서 못박는 것은 `--pin` 이라고 말했을 때뿐이고, 그 밖의
`--port` 는 「이번 기동이 앉은 자리」(port.auto)로만 적혀 --stop 뒤에 잊힌다.

실행: python3 tests/ port_pin
"""
import importlib.machinery
import importlib.util
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


class PortPin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.s9 = _load("s9_port_pin", self.root)
        self.st = os.path.join(self.root, "state")

    def tearDown(self):
        self.tmp.cleanup()

    def test_port_alone_is_not_a_pin(self):
        """정상: --port 만 주면 「이번 기동이 앉은 자리」다 — 잊을 수 있는 기록."""
        self.assertEqual(self.s9.port_record_kind(True, False, True, False), "auto")

    def test_pin_is_the_only_pin(self):
        """정상: 사람이 --pin 이라고 말했을 때만 못박힌다."""
        self.assertEqual(self.s9.port_record_kind(True, True, True, False), "pin")

    def test_machine_chosen_or_env_is_not_recorded(self):
        """경계: 기계가 고른 값(--port-auto → given=False)·S9_PORT·감시자 없는 1회 실행은 적지 않는다."""
        self.assertEqual(self.s9.port_record_kind(False, True, True, False), "")
        self.assertEqual(self.s9.port_record_kind(True, True, True, True), "")
        self.assertEqual(self.s9.port_record_kind(True, False, False, False), "")

    def test_given_port_is_forgotten_after_stop_but_pinned_is_kept(self):
        """회귀: --port 로 앉은 자리는 --stop 이 잊고(다음 기동이 9909 부터), --pin 은 남는다."""
        auto = os.path.join(self.st, "port.auto")
        self.s9._port_remember(9912, "given", self.root, auto)
        self.assertEqual(self.s9.s9_port(self.root), 9912)
        self.assertTrue(self.s9._forget_auto_port(self.root))
        self.assertEqual(self.s9.s9_port(self.root), 9909)
        self.assertTrue(self.s9._pin_port(9915, self.root))
        self.assertFalse(self.s9._forget_auto_port(self.root))
        self.assertEqual(self.s9.s9_port(self.root), 9915)


if __name__ == "__main__":
    unittest.main()
