"""재기동이 포트를 잃지 않는다 (REQ-20260907-033).

두 결함이 겹쳐 대시보드가 9909 에서 9910 으로 옮겨 앉은 채 굳었다.

1. **기계가 고른 포트가 사람의 결정으로 못박혔다.** `--port` 가 붙어 있다는
   것만으로 「사람이 정했다」로 읽었는데, `s9 code` 도 감시자의 자기 재실행도
   기계가 고른 값을 그 플래그로 넘긴다. 그래서 자동 이동 표식이 지워지고
   되돌리는 장치가 손을 못 댔다.
2. **재기동 직후의 리셋을 점거로 읽었다.** 중계는 리눅스 리스너가 닫힌 뒤에도
   약 62초 그 포트를 공개하고 붙는 즉시 끊는다(DOC-20260906-003) — 재기동은
   반드시 그 창을 지난다. 그 리셋은 우리 자신의 유령이다.

실행: python3 tests/ port_pin_ghost
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-pinghost-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_pg", importlib.machinery.SourceFileLoader("s9_mod_pg", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class OnlyAPersonPins(unittest.TestCase):
    """기계가 고른 포트는 사람의 결정이 아니다."""

    def test_the_guard_reexec_marks_itself_as_machine_chosen(self):
        argv = mod.guard_argv(9909, "127.0.0.1")
        self.assertIn("--port-auto", argv,
                      "감시자의 자기 재실행이 사람의 결정으로 읽힌다")
        # 감시자로 읽히는 이름은 그대로 남아야 한다 — 진단·시험이 이 낱말로 센다
        self.assertIn("--supervise", argv)
        self.assertIn("--guard-run", argv)
        self.assertEqual(argv[argv.index("--port") + 1], "9909")

    def test_a_person_giving_the_port_is_not_marked(self):
        """사람이 친 명령에는 그 표식이 없다 — 그래야 못박힌다."""
        self.assertNotIn("--port-auto", ["serve", "--supervise", "--port", "9911"])


class TheGhostIsOurs(unittest.TestCase):
    """방금까지 우리가 듣던 자리면 그 리셋은 우리 유령이다."""

    def setUp(self):
        self.state = os.path.join(TMP, "state")
        os.makedirs(self.state, exist_ok=True)
        self.path = os.path.join(self.state, "serve-code.json")

    def _stamp(self, port, pid):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"port": port, "pid": pid, "started": "x", "stamp": "y"}, f)

    def test_no_stamp_is_not_ours(self):
        try:
            os.remove(self.path)
        except OSError:
            pass
        self.assertFalse(mod._port_ghost_is_ours(9909, TMP))

    def test_a_dead_server_on_that_port_is_our_ghost(self):
        self._stamp(9909, 999999)          # 없는 pid = 죽었다
        self.assertTrue(mod._port_ghost_is_ours(9909, TMP))

    def test_a_live_server_is_not_a_ghost(self):
        """살아 있으면 유령이 아니다 — 그 자리의 리셋은 진짜 남의 것일 수 있다."""
        self._stamp(9909, os.getpid())
        self.assertFalse(mod._port_ghost_is_ours(9909, TMP))

    def test_another_port_is_not_ours(self):
        self._stamp(9909, 999999)
        self.assertFalse(mod._port_ghost_is_ours(9910, TMP))


class ResetRetryIsNarrow(unittest.TestCase):
    """되걸기는 밝힌 자리에서만 — 진짜 가로채기가 계기판에서 사라지면 안 된다."""

    def _ready(self, ghost, resets):
        n = {"i": 0}

        def connect(h, p):
            n["i"] += 1
            if n["i"] <= resets:
                raise ConnectionResetError("reset")
            return (b"HTTP/1.0 200 OK\r\nContent-Length: 20\r\n\r\n"
                    b'{"started": "S"}    ')

        return mod.dashboard_ready("127.0.0.1", 9909, expect_started="S",
                                   _connect=connect, _sleep=lambda *_: None,
                                   reset_is_ghost=ghost), n["i"]

    def test_without_the_hint_a_reset_ends_it(self):
        res, calls = self._ready(False, 1)
        self.assertFalse(res["ready"])
        self.assertEqual(calls, 1, "밝히지 않았는데 다시 걸었다")
        self.assertIn("점거", res["why"])

    def test_with_the_hint_a_transient_reset_recovers(self):
        res, calls = self._ready(True, 1)
        self.assertTrue(res["ready"], res)
        self.assertTrue(res["mine"])
        self.assertGreaterEqual(calls, 2)

    def test_the_hint_does_not_retry_forever(self):
        res, calls = self._ready(True, 99)
        self.assertFalse(res["ready"])
        self.assertLessEqual(calls, mod.DASH_READY_TRIES)
        self.assertIn("계속 끊긴다", res["why"])


if __name__ == "__main__":
    unittest.main()
