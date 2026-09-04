"""serve 감시자 — 죽은 사유가 남고, 되살아나고, 산 것은 건드리지 않는다.

REQ-20260825-096. 2026-08-25 22:19 대시보드가 사라졌을 때 두 가지가 없었다:
(1) state/serve.log 에 크래시 흔적이 없어 **왜 죽었는지 사후에 알 수 없었고**,
(2) 아무도 되살리지 않아 사람이 접속 거부를 겪고서야 손으로 띄웠다.

외부 스케줄러(systemd/cron)는 사용자가 명시적으로 배제했으므로 자기 감시로 푼다.
여기서 고정하는 계약:
  S1 사유가 남는다      S2 되살아난다        S3 백오프가 늘어난다
  S4 정상 종료는 안 살린다  S5 감시자는 하나   S6/S7 살아 있는 것은 안 건드린다

실행: python3 tests/ serve_guard
"""
import importlib.machinery
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from portpool import free_port, wait_server          # noqa: E402

S9 = os.path.join(HERE, "..", "bin", "s9")
os.environ.setdefault("S9_ROOT", tempfile.mkdtemp(prefix="s9guard-mod-"))
_spec = importlib.util.spec_from_loader(
    "s9_mod_serveguard",
    importlib.machinery.SourceFileLoader("s9_mod_serveguard", S9))
s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s9)


class FakeProc:
    """spawn 주입용 — 이미 죽어 있는 자식."""
    def __init__(self, rc, on_wait=None):
        self.rc, self.on_wait = rc, on_wait

    def wait(self):
        if self.on_wait:
            self.on_wait()
        return self.rc


class GuardLoopTest(unittest.TestCase):
    """루프의 판정 — 실제 시간·프로세스 없이 (spawn/sleep/clock 주입)."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9guard-")
        os.makedirs(os.path.join(self.root, "state"))
        self.port = 18999          # 아무도 bind 하지 않는다(주입 루프 전용)
        self.slept = []

    def _records(self):
        p = os.path.join(self.root, "state", "serve-guard.log")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def _run(self, procs, clock_steps=None, rounds=None):
        it = iter(procs)
        steps = iter(clock_steps or [0.0] * (len(procs) * 2 + 4))
        return s9.serve_guard_loop(
            self.port, "127.0.0.1", self.root,
            spawn=lambda: next(it),
            sleep=self.slept.append,
            clock=lambda: next(steps),
            max_rounds=rounds if rounds is not None else len(procs))

    # S1. 비정상 종료의 사유(시그널·종료코드·직전 출력)가 기록으로 남는다
    def test_s1_death_reason_recorded(self):
        with open(os.path.join(self.root, "state", "serve.log"), "a") as f:
            f.write("이전 기동의 로그\n")
        # 자식이 쓰고 죽은 것처럼 serve.log 에 트레이스를 남긴다
        def crash():
            with open(os.path.join(self.root, "state", "serve.log"), "a") as f:
                f.write("Traceback (most recent call last):\n"
                        "MemoryError: out of memory\n")
        self._run([FakeProc(-signal.SIGKILL, on_wait=crash)])
        died = [r for r in self._records() if r["event"] == "died"]
        self.assertEqual(len(died), 1, self._records())
        self.assertEqual(died[0]["rc"], -signal.SIGKILL)
        self.assertEqual(died[0]["reason"], "signal SIGKILL")
        self.assertIn("MemoryError: out of memory", died[0]["tail"])
        self.assertNotIn("이전 기동의 로그", died[0]["tail"],
                         "이번 자식이 쓴 구간만 사유로 남아야 한다")
        # 사람은 serve.log 를 보러 간다 — 거기에도 한 줄이 남아야 한다
        with open(os.path.join(self.root, "state", "serve.log"),
                  encoding="utf-8") as f:
            self.assertIn("[serve-guard]", f.read())

    # S2. 죽으면 다시 띄운다 (루프 수준: 다음 라운드에 spawn 이 또 불린다)
    def test_s2_respawns_after_abnormal_death(self):
        spawns = []

        def spawn():
            spawns.append(1)
            return FakeProc(-signal.SIGKILL)
        s9.serve_guard_loop(self.port, "127.0.0.1", self.root, spawn=spawn,
                            sleep=self.slept.append, clock=lambda: 0.0,
                            max_rounds=3)
        self.assertEqual(len(spawns), 3, "죽을 때마다 되살려야 한다")

    # S3. 연속 실패면 대기가 늘어나고 상한에서 멈춘다 / 건강한 실행은 리셋
    def test_s3_backoff_grows_and_caps(self):
        delays = [s9._guard_backoff(n) for n in range(1, 12)]
        self.assertEqual(delays[0], 1, "첫 실패는 곧바로 되살린다")
        for a, b in zip(delays, delays[1:]):
            self.assertLessEqual(a, b, f"백오프가 줄어든다: {delays}")
        self.assertEqual(delays[-1], max(s9.GUARD_BACKOFF), "상한이 있어야 한다")
        self.assertEqual(s9._guard_backoff(0), delays[0], "0회도 안전해야 한다")

    def test_s3b_backoff_used_and_reset_by_healthy_run(self):
        # 즉사 3회 → 대기가 늘고, 그 다음 오래 산 자식 뒤에는 다시 처음으로
        clock = [0.0, 0.0,            # 1회차 start/end (0s 생존)
                 0.0, 0.0,            # 2회차
                 0.0, 0.0,            # 3회차
                 0.0, s9.GUARD_HEALTHY_SEC + 1,   # 4회차 — 건강한 실행
                 0.0, 0.0]            # 5회차 — 리셋 확인
        self._run([FakeProc(1)] * 5, clock_steps=clock, rounds=5)
        got = [r["fails"] for r in self._records() if r["event"] == "died"]
        self.assertEqual(got, [1, 2, 3, 1, 2], f"실패 카운트: {got}")
        self.assertEqual(self.slept,
                         [s9._guard_backoff(n) for n in (1, 2, 3, 1, 2)])

    # 되살리기로 풀리지 않는 실패(포트 권한·설정 오류)는 무한히 돌지 않는다
    def test_s3c_gives_up_after_persistent_failure(self):
        spawns = []

        def spawn():
            spawns.append(1)
            return FakeProc(1)
        why = s9.serve_guard_loop(self.port, "127.0.0.1", self.root,
                                  spawn=spawn, sleep=self.slept.append,
                                  clock=lambda: 0.0, max_rounds=None)
        self.assertEqual(why, "gave-up")
        self.assertEqual(len(spawns), s9.GUARD_GIVEUP_FAILS)
        self.assertEqual(self._records()[-1]["event"], "gave-up")

    # 열 수 없는 포트는 감시하지 않는다 — 재기동만 반복하는 감시자를 남기지 않는다
    def test_privileged_port_is_refused(self):
        self.assertFalse(s9._guard_detach(1, "127.0.0.1", self.root),
                         "권한 없는 포트에 감시자를 세우면 안 된다")
        self.assertFalse(os.path.exists(
            s9._guard_paths(1, self.root)["lock"]))

    # 기동 실패(fork/exec 고갈)로 감시자 자신이 죽으면 아무도 남지 않는다
    def test_spawn_failure_keeps_guard_alive(self):
        def boom():
            raise OSError("Resource temporarily unavailable")
        why = s9.serve_guard_loop(self.port, "127.0.0.1", self.root,
                                  spawn=boom, sleep=self.slept.append,
                                  clock=lambda: 0.0, max_rounds=3)
        self.assertEqual(why, "max-rounds", "감시자가 살아 있어야 한다")
        events = [r["event"] for r in self._records()]
        self.assertEqual(events.count("spawn-error"), 3, events)
        self.assertEqual(self.slept,
                         [s9._guard_backoff(n) for n in (1, 2, 3)])

    # 감시 중이 아닌데 중지 요청을 쓰면, 다음에 뜨는 감시자가 그걸 보고 죽는다
    def test_stop_guard_without_guard_writes_nothing(self):
        r = subprocess.run([S9, "serve", "--stop-guard", "--port",
                            str(self.port)], capture_output=True, text=True,
                           timeout=30,
                           env={**os.environ, "S9_ROOT": self.root})
        self.assertIn("감시 중인 감시자가 없다", r.stdout, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(
            s9._guard_paths(self.port, self.root)["stop"]))

    # S4. 정상 종료(exit 0)는 사용자 의도 — 되살리지 않고 감시도 끝낸다
    def test_s4_clean_exit_is_not_revived(self):
        spawns = []

        def spawn():
            spawns.append(1)
            return FakeProc(0)
        why = s9.serve_guard_loop(self.port, "127.0.0.1", self.root,
                                  spawn=spawn, sleep=self.slept.append,
                                  clock=lambda: 0.0, max_rounds=5)
        self.assertEqual(why, "clean-exit")
        self.assertEqual(len(spawns), 1, "정상 종료를 되살리면 안 된다")
        self.assertEqual([r["event"] for r in self._records()], ["clean-exit"])

    # S6. 포트를 이미 누가 쥐고 있으면 자식을 띄우지 않는다 (SSE 보호)
    def test_s6_live_server_is_left_alone(self):
        port = free_port()
        import socket
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(4)
        try:
            spawns = []
            s9.serve_guard_loop(port, "127.0.0.1", self.root,
                                spawn=lambda: spawns.append(1),
                                sleep=self.slept.append, clock=lambda: 0.0,
                                max_rounds=3)
            self.assertEqual(spawns, [], "살아 있는 서버가 있으면 띄우지 않는다")
            self.assertEqual(self.slept, [s9.GUARD_POLL_SEC] * 3)
        finally:
            srv.close()

    # S6b. 자식이 "포트는 남의 것"(exit 3)이라고 알리면 실패로 세지 않는다
    def test_s6b_port_busy_child_is_not_a_failure(self):
        self._run([FakeProc(s9.EXIT_PORT_BUSY)] * 2)
        self.assertEqual([r["event"] for r in self._records()], [])
        self.assertEqual(self.slept, [s9.GUARD_POLL_SEC] * 2)

    # S7. 의도적 SIGTERM 뒤에는 최소 대기를 둔다 — `serve --restart` 에 양보한다
    def test_s7_sigterm_yields_before_respawn(self):
        self._run([FakeProc(-signal.SIGTERM)])
        rec = self._records()[-1]
        self.assertGreaterEqual(rec["retry_in"], s9.GUARD_TERM_MIN_SEC)
        self.assertEqual(rec["reason"], "signal SIGTERM")

    # S7b. 감시자는 소스 변경을 보지 않는다 (코드 갱신 반영 수단이 아니다)
    def test_s7b_guard_never_watches_source(self):
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def serve_guard_loop("):
                   src.index("def _guard_lock(")]
        for bad in ("getmtime", "os.kill", "terminate(", "SIGKILL"):
            self.assertNotIn(bad, body,
                             f"감시 루프가 살아 있는 서버에 손대는 신호: {bad}")

    # 감시자는 세션보다 오래 산다 — 죽은 세션 식별자를 자식에게 물려주지 않는다
    def test_child_env_drops_dead_session(self):
        import subprocess as sp
        from unittest import mock
        got = {}

        class _P:
            pass
        with mock.patch.dict(os.environ, {"S9_SESSION": "deadbeef"}), \
             mock.patch.object(sp, "Popen",
                               lambda *a, **kw: (got.update(kw), _P())[1]):
            s9._guard_spawn_child(self.port, "127.0.0.1", self.root)
        self.assertNotIn("S9_SESSION", got["env"],
                         "대시보드가 죽은 세션에 귀속된 문서를 만들게 된다")
        self.assertEqual(got["env"]["S9_SERVE_SUPERVISED"], "1")

    # 중지 요청은 서버를 두고 감시만 끝낸다
    def test_stop_file_ends_watch_only(self):
        stop = s9._guard_paths(self.port, self.root)["stop"]
        open(stop, "w").close()
        why = s9.serve_guard_loop(self.port, "127.0.0.1", self.root,
                                  spawn=lambda: self.fail("자식을 띄우면 안 된다"),
                                  sleep=self.slept.append, clock=lambda: 0.0,
                                  max_rounds=2)
        self.assertEqual(why, "stopped")
        self.assertFalse(os.path.exists(stop), "중지 요청은 한 번만 쓰인다")


class GuardProcessTest(unittest.TestCase):
    """실제로 떼어 놓고 돌린다 — 자식을 SIGKILL 해 되살아나는지까지."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9guardp-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_REWORK_WATCH": "off",
                   "S9_PORT_GUARD": "off"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=30)
        cls.port = free_port()
        launcher = subprocess.Popen(
            [S9, "serve", "--supervise", "--host", "127.0.0.1",
             "--port", str(cls.port)], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=cls.env, text=True)
        launcher.communicate(timeout=30)
        cls.launcher_pid = launcher.pid        # 이미 죽은 pid — 감시자의 부모일 수 없다
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        subprocess.run([S9, "serve", "--stop-guard", "--port", str(cls.port)],
                       capture_output=True, env=cls.env, timeout=15)
        for pid in cls._pids(cls.port) + cls._guard_pids(cls.port):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    @staticmethod
    def _pids(port):
        out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True,
                             timeout=10).stdout
        pids = []
        for line in out.splitlines():
            if f":{port} " not in line:
                continue
            for tok in line.split("pid=")[1:]:
                p = tok.split(",")[0].strip()
                if p.isdigit():
                    pids.append(int(p))
        return pids

    @staticmethod
    def _guard_pids(port):
        out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True,
                             text=True, timeout=10).stdout
        return [int(ln.split()[0]) for ln in out.splitlines()
                if "--supervise" in ln and str(port) in ln
                and "ps -eo" not in ln]

    def _records(self):
        p = os.path.join(self.root, "state", "serve-guard.log")
        with open(p, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def _guard_or_skip(self, port):
        """감시자가 남의 손에 거둬졌으면 환경 탓이므로 판정하지 않는다.

        감시자는 double fork 로 **일부러 고아**가 된다. 그런데 테스트는 풀
        포트(18800~)를 쓰고, s9-doctor --sweep 은 '풀 포트 + 고아'를 회수
        대상으로 본다 — 다른 세션이 시작되기만 해도(세션 시작 훅이 sweep 을
        던진다) 이 감시자가 사라질 수 있다. 실서비스 포트(9909)는 풀 밖이라
        해당되지 않는다."""
        pids = self._guard_pids(port)
        if not pids:
            self.skipTest("감시자가 외부 회수(s9-doctor --sweep)에 거둬졌다 — "
                          "풀 포트 프로세스는 고아로 판정된다")
        return pids

    # S2(통합). 자식을 SIGKILL 하면 사유가 남고 서버가 되살아난다
    def test_guard_process_test(self):
        """실제로 떼어 놓고 돌린다 — 자식을 SIGKILL 해 되살아나는지까지."""
        with self.subTest("s2_kill_child_and_it_comes_back"):
                self._guard_or_skip(self.port)
                pids = self._pids(self.port)
                self.assertTrue(pids, "감시자가 서버를 띄우지 못했다")
                os.kill(pids[0], signal.SIGKILL)
                try:
                    wait_server(self.port)                 # 되살아날 때까지 (백오프 1s)
                except RuntimeError:
                    self._guard_or_skip(self.port)         # 감시자부터 사라졌는가
                    raise
                back = self._pids(self.port)
                self.assertTrue(back and back[0] != pids[0],
                                f"새 프로세스로 되살아나야 한다: {pids} -> {back}")
                died = [r for r in self._records() if r["event"] == "died"]
                self.assertTrue(died, "사망 기록이 없다")
                self.assertEqual(died[-1]["reason"], "signal SIGKILL")

            # 지난 중지 요청의 잔재가 새 감시자를 즉사시키지 않는다
        with self.subTest("stale_stop_file_does_not_kill_new_guard"):
                port = free_port()
                stop = os.path.join(self.root, "state", f"serve-guard.{port}.stop")
                open(stop, "w").close()
                try:
                    subprocess.run([S9, "serve", "--supervise", "--port", str(port)],
                                   capture_output=True, text=True, env=self.env,
                                   timeout=30)
                    wait_server(port)                  # 감시자가 살아 서버를 띄웠다
                    self.assertFalse(os.path.exists(stop), "잔재를 치우지 않았다")
                finally:
                    subprocess.run([S9, "serve", "--stop-guard", "--port", str(port)],
                                   capture_output=True, env=self.env, timeout=15)
                    for pid in self._guard_pids(port) + self._pids(port):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass

            # S5. 같은 포트로 두 번 --supervise 해도 감시자는 하나다.
            #     (클래스가 띄운 감시자를 쓰지 않고 자기 포트로 새로 띄운다 — 다른
            #      세션의 고아 회수(s9-doctor --sweep)가 풀 포트 프로세스를 거둬가는
            #      바람에 "먼저 뜬 감시자"를 전제한 판정이 흔들린 적이 있다.)
        with self.subTest("s5_supervisor_is_singleton"):
                port = free_port()
                try:
                    first = subprocess.run([S9, "serve", "--supervise", "--port",
                                            str(port)], capture_output=True, text=True,
                                           env=self.env, timeout=30)
                    self.assertIn("감시 시작", first.stdout, first.stdout + first.stderr)
                    second = subprocess.run([S9, "serve", "--supervise", "--port",
                                             str(port)], capture_output=True, text=True,
                                            env=self.env, timeout=30)
                    self.assertIn("이미 감시 중", second.stdout,
                                  second.stdout + second.stderr)
                    self.assertEqual(len(self._guard_pids(port)), 1,
                                     "감시자가 둘 이상 떠 있다")
                finally:
                    subprocess.run([S9, "serve", "--stop-guard", "--port", str(port)],
                                   capture_output=True, env=self.env, timeout=15)
                    for pid in self._guard_pids(port) + self._pids(port):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass

            # 감시자는 이 터미널 세션과 무관하게 산다 (setsid 로 분리된 세션)
        with self.subTest("s5b_supervisor_is_detached"):
            pids = self._guard_or_skip(self.port)
            out = subprocess.run(["ps", "-o", "sess=,ppid=", "-p", str(pids[0])],
                                 capture_output=True, text=True, timeout=10).stdout
            sess, ppid = out.split()
            self.assertNotEqual(int(sess), os.getsid(0),
                                "감시자가 나를 띄운 세션에 그대로 남아 있다 — "
                                "터미널이 닫히면 같이 죽는다")
            self.assertNotEqual(int(ppid), self.launcher_pid,
                                "감시자가 자기를 띄운 프로세스에 매달려 있다 — "
                                "그 프로세스가 죽으면 같이 죽는다")
            # 세션 리더가 **아니어야** 한다(double fork) — 리더면 나중에 제어
            # 터미널이 붙을 수 있고, 그 터미널이 닫힐 때 SIGHUP 을 받는다.
            self.assertNotEqual(int(sess), pids[0])

if __name__ == "__main__":
    unittest.main(verbosity=2)
