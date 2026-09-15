"""중지 표식은 이름이 적힌 편지다 (REQ-20260916-001-2n7g).

실제 사고 2026-09-15 22:55 ~ 2026-09-16 00:01. 대시보드를 네 번 다시 띄웠는데 네 번
다 「떴다가 곧 죽었다」 — 서버의 종료 코드는 143(SIGTERM)이었고 감시 로그에는 그때마다
「감시 중지 신호」가 남았다. 아무도 중지를 요청하지 않았는데.

원인은 `state/serve-guard.<포트>.stop` 이 **0바이트**였다는 것이다. 이 표식은 「지금
감시 중인 그 감시자」에게 보내는 것인데, 읽을 감시자가 읽기 전에 신호로 죽으면 표식만
남는다. 그 뒤 몇 시간이 지나 뜨는 **다른** 감시자가 그것을 제 것으로 알고 곧바로
물러나고, 자식 서버도 함께 내려갔다. 그날 9910 의 표식은 아홉 시간을 기다리고 있었다.

여기서 고정하는 계약: 표식에 대상 감시자의 pid 가 적히고, 감시 루프는 **제 앞으로 온
것만** 따른다. 죽은 감시자 앞으로 온 것(또는 이름 없는 옛 표식)은 지우고 계속 돌고,
살아 있는 남의 것은 건드리지 않는다 — 그가 읽을 것이다.

실행: python3 tests/ guard_stop_target
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from portpool import free_port          # noqa: E402

S9 = os.path.join(HERE, "..", "bin", "s9")
os.environ.setdefault("S9_ROOT", tempfile.mkdtemp(prefix="s9stoptarget-mod-"))
_spec = importlib.util.spec_from_loader(
    "s9_mod_stoptarget",
    importlib.machinery.SourceFileLoader("s9_mod_stoptarget", S9))
s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s9)


def dead_pid():
    """확실히 죽은 pid 하나 — 자식을 띄우고 거둔다."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class StopMarkerIsAddressed(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9stoptarget-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.port = free_port()
        self.stop = s9._guard_paths(self.port, self.root)["stop"]
        self.slept = []

    def write(self, text):
        with open(self.stop, "w", encoding="utf-8") as f:
            f.write(text)

    def records(self):
        p = os.path.join(self.root, "state", "serve-guard.log")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def loop(self, rounds=1, spawn=None):
        return s9.serve_guard_loop(
            self.port, "127.0.0.1", self.root,
            spawn=spawn or (lambda: self.fail("자식을 띄우면 안 된다")),
            sleep=self.slept.append, clock=lambda: 0.0, max_rounds=rounds)

    # ── 내 앞으로 온 것 ───────────────────────────────────────────────
    def test_2_marker_for_me_stops_the_watch(self):
        """2. 내 pid 가 적힌 표식은 종전대로 지우고 「stopped」로 끝낸다."""
        self.write(f"{os.getpid()}\n")
        self.assertEqual(self.loop(rounds=2), "stopped")
        self.assertFalse(os.path.exists(self.stop), "표식은 한 번만 쓰인다")

    # ── 남의 것 ─────────────────────────────────────────────────────
    def test_4_marker_for_a_dead_guard_is_swept(self):
        """4. 죽은 감시자 앞으로 온 표식은 지우고 계속 돈다 — 이번 사고."""
        self.write(f"{dead_pid()}\n")
        calls = []
        why = self.loop(rounds=1, spawn=lambda: calls.append(1) or FakeDone())
        self.assertNotEqual(why, "stopped", "죽은 감시자의 표식이 나를 세웠다")
        self.assertFalse(os.path.exists(self.stop), "잔재를 치우지 않았다")
        self.assertTrue(calls, "표식을 지나갔으면 제 일(자식 띄우기)을 해야 한다")

    def test_5_nameless_marker_is_swept(self):
        """5. 이름 없는 옛 표식(0바이트)도 지우고 계속 돈다."""
        self.write("")
        calls = []
        why = self.loop(rounds=1, spawn=lambda: calls.append(1) or FakeDone())
        self.assertNotEqual(why, "stopped")
        self.assertFalse(os.path.exists(self.stop))
        self.assertTrue(calls)

    def test_6_marker_for_a_living_stranger_is_left_alone(self):
        """6. 살아 있는 남의 감시자 앞으로 온 표식은 건드리지 않는다."""
        other = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(30)"])
        try:
            self.write(f"{other.pid}\n")
            calls = []
            why = self.loop(rounds=1, spawn=lambda: calls.append(1) or FakeDone())
            self.assertNotEqual(why, "stopped")
            self.assertTrue(os.path.exists(self.stop),
                            "산 사람 앞으로 온 편지를 내가 버렸다")
        finally:
            other.kill()
            other.wait()

    # ── 기록 ────────────────────────────────────────────────────────
    def test_7_sweeping_is_written_down(self):
        """7. 지나간 표식은 감시 로그에 한 줄로 남는다(대상 pid 와 내 pid)."""
        d = dead_pid()
        self.write(f"{d}\n")
        self.loop(rounds=1, spawn=lambda: FakeDone())
        stale = [r for r in self.records() if r["event"] == "stale-stop"]
        self.assertTrue(stale, "지나간 표식이 기록에 없다")
        self.assertIn(str(d), stale[-1]["msg"])
        self.assertIn(str(os.getpid()), stale[-1]["msg"])

    # ── 술어 자체 ────────────────────────────────────────────────────
    def test_target_reader(self):
        """_guard_stop_target — 적힌 pid, 못 읽으면 None."""
        self.write("4242\n")
        self.assertEqual(s9._guard_stop_target(self.stop), 4242)
        self.write("")
        self.assertIsNone(s9._guard_stop_target(self.stop))
        self.write("사람 이름\n")
        self.assertIsNone(s9._guard_stop_target(self.stop))
        self.assertIsNone(s9._guard_stop_target(self.stop + ".없는파일"))


class StopGuardWritesTheTarget(unittest.TestCase):
    """1·3. `--stop-guard` 가 대상을 적는가 / 감시 중이 아니면 아무것도 안 쓰는가."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9stopcli-")
        self.env = dict(os.environ, S9_ROOT=self.root)
        self.port = free_port()

    def test_3_no_guard_writes_nothing(self):
        r = subprocess.run([S9, "serve", "--stop-guard", "--port", str(self.port)],
                           capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(
            s9._guard_paths(self.port, self.root)["stop"]),
            "감시 중이 아닌데 표식을 남겼다")

    def test_1_source_writes_the_alive_pid(self):
        """1. 표식에 그때 감시 중이던 감시자의 pid 를 적는다."""
        src = open(S9 + ".py", encoding="utf-8").read()
        i = src.index('if getattr(args, "stop_guard", False):')
        chunk = src[i:i + 900]
        self.assertIn("_target = _guard_alive(args.port)", chunk)
        self.assertIn('_sf.write(f"{_target}', chunk)


class FakeDone:
    """이미 죽어 있는 자식 — 루프가 한 판 돌게만 한다."""
    def wait(self):
        return 0

    def poll(self):
        return 0


if __name__ == "__main__":
    unittest.main()
