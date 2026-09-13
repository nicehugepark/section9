"""원격 대시보드 ssh 터널 자동 유지 (REQ-20260906-010).

리드가 손으로 띄운 `ssh -L` 터널이 끊기면 조용히 사라졌다(실측 2026-09-06 00:5x→08:42,
사유 미기록). 사람이 명령을 치지 않는다는 전제라 터널도 하네스가 지킨다:

  s9 tunnel <비밀이름> <로컬포트> <원격포트> [--keep]   띄운다(백그라운드 감시자)
  s9 tunnel --status                                   상태
  s9 tunnel <로컬포트> --stop                           정리

지키는 것 셋:
  ① 비밀의 **값**은 여기 코드가 읽지 않는다 — `s9 secret run` 치환으로만 지난다.
     state/·log 어디에도 값이 없다(이름만).
  ② 개인 장치의 **이름**은 코드에 없다 — 이름은 필수 인자로만 받는다
     (projects/section9/CONTEXT.md 「개인 장치의 이름은 코드 밖에 둔다」,
     tests/test_no_secret_names.py 가 저장소 전체를 지킨다).
  ③ WSL 규율 — `-4` 와 `127.0.0.1:` 명시(DOC-20260906-001). 빠지면 [::1] 이중
     바인드가 되어 연결이 거절된다.

ssh 는 가짜 실행 파일이다(인자·pid 를 파일에 적고 TERM 까지 기다린다). 실제
네트워크·포트 바인드는 없다 — 포트 번호는 상태 파일의 키일 뿐이다.

실행: python3 tests/ tunnel
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
DOCTOR = os.path.join(REPO, "bin", "s9-doctor")

FAKE_SSH = r'''#!/bin/sh
# 가짜 ssh — 인자와 pid 를 적고 TERM 이 올 때까지 기다린다
echo "$@" >> "$FAKE_SSH_ARGS"
echo $$ >> "$FAKE_SSH_PIDS"
trap 'exit 0' TERM INT
if [ -f "$FAKE_SSH_ARGS.busy" ]; then
  echo "bind [127.0.0.1]:45919: Address already in use" >&2
  echo "channel_setup_fwd_listener_tcpip: cannot listen to port: 45919" >&2
  echo "Could not request local forwarding." >&2
  exit 255
fi
while [ ! -f "$FAKE_SSH_ARGS.quit" ]; do sleep 0.2; done
'''

# 실제 꼴을 흉내 낸 래퍼 — 비밀 값이 이 스크립트를 가리키고, 진짜 ssh(가짜)는
# 그 **손자**로 같은 프로세스 그룹에 선다. 래퍼가 종료돼도 손자는 남는다.
FAKE_WRAP = '''#!/bin/sh
"$(dirname "$0")/fakessh" "$@" &
wait
'''


def wait_for(cond, timeout=10.0, every=0.1):
    """조건 대기 — 고정 sleep 대신 짧은 폴 + 시한 (빠른 테스트 규칙)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(every)
    return cond()


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


class _Base(unittest.TestCase):
    NAME = "tunnelbox"          # 시험용 비밀 이름 — 실제 장치 이름이 아니다

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9tun-")
        # 값에 들어가는 토큰이 어디에도 새지 않는지 grep 으로 잰다
        cls.token = "sekrit-%08x" % int.from_bytes(os.urandom(4), "big")
        cls.bindir = tempfile.mkdtemp(prefix=cls.token + "-")
        cls.fake = os.path.join(cls.bindir, "fakessh")
        with open(cls.fake, "w", encoding="utf-8") as f:
            f.write(FAKE_SSH)
        os.chmod(cls.fake, stat.S_IRWXU)
        cls.wrap = os.path.join(cls.bindir, "fakewrap")
        with open(cls.wrap, "w", encoding="utf-8") as f:
            f.write(FAKE_WRAP)
        os.chmod(cls.wrap, stat.S_IRWXU)
        cls.args_log = os.path.join(cls.bindir, "args.log")
        cls.pids_log = os.path.join(cls.bindir, "pids.log")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_USER": "alice",
                   "S9_MACHINE": "testbox", "FAKE_SSH_ARGS": cls.args_log,
                   "FAKE_SSH_PIDS": cls.pids_log}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        r = subprocess.run([S9, "secret", "set", cls.NAME], input=cls.fake,
                           capture_output=True, text=True, env=cls.env, timeout=30)
        assert r.returncode == 0, r.stdout + r.stderr

    @classmethod
    def tearDownClass(cls):
        try:
            open(cls.args_log + ".quit", "w").close()
        except OSError:
            pass
        for p in cls.ports():
            subprocess.run([S9, "tunnel", str(p), "--stop"], capture_output=True,
                           text=True, env=cls.env, timeout=30)
        for pid in cls.ssh_pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        shutil.rmtree(cls.root, ignore_errors=True)
        shutil.rmtree(cls.bindir, ignore_errors=True)

    @classmethod
    def ports(cls):
        return []

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=30, stdin=subprocess.DEVNULL)
        if expect is not None:
            assert r.returncode == expect, f"s9 {' '.join(argv)} rc={r.returncode}\n{r.stdout}{r.stderr}"
        return r.stdout + r.stderr

    @classmethod
    def ssh_pids(cls):
        try:
            with open(cls.pids_log, encoding="utf-8") as f:
                return [int(x) for x in f.read().split()]
        except (OSError, ValueError):
            return []

    def state(self, lport):
        p = os.path.join(self.root, "state", f"tunnel-{lport}.json")
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None


class Lifecycle(_Base):
    """S1→S2→S3→S4 — 한 터널의 한살이를 순서대로 (감시자 기동은 클래스당 1회)."""
    L, R = 45919, 45910

    @classmethod
    def ports(cls):
        return [cls.L]

    def test_t1_start_writes_state_and_ssh_gets_wsl_flags(self):
        out = self.cli("tunnel", self.NAME, str(self.L), str(self.R))
        self.assertIn(str(self.L), out)
        st = wait_for(lambda: (self.state(self.L) or {}).get("child_pid") and self.state(self.L))
        self.assertTrue(st, "state/tunnel-<L>.json 이 안 생겼다")
        self.assertTrue(alive(st["pid"]), "감시자 pid 가 실행 중이 아니다")
        self.assertEqual(st["secret"], self.NAME)
        self.assertEqual((st["lport"], st["rport"]), (self.L, self.R))
        self.assertEqual(st["retries"], 0)
        self.assertTrue(st.get("started"))
        argv = wait_for(lambda: os.path.exists(self.args_log) and read(self.args_log))
        self.assertTrue(argv, "가짜 ssh 가 불리지 않았다")
        line = argv.strip().splitlines()[0]
        self.assertIn("-4", line.split())
        self.assertIn("-N", line.split())
        self.assertIn(f"-L 127.0.0.1:{self.L}:127.0.0.1:{self.R}", line)
        self.assertIn("ServerAliveInterval", line)

    def test_t2_status_cli_and_doctor_line(self):
        out = self.cli("tunnel", "--status")
        self.assertIn(f"{self.L}→{self.R}", out)
        self.assertIn("실행 중", out)
        self.assertIn(self.NAME, out)
        self.assertNotIn(self.token, out)
        # doctor 는 s9 가 못 뜰 때도 쓰는 독립 파일이라 상태 파일을 직접 읽는다
        os.environ["S9_ROOT"] = self.root
        try:
            spec = importlib.util.spec_from_loader(
                "s9_doctor_tun", importlib.machinery.SourceFileLoader("s9_doctor_tun", DOCTOR))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
        finally:
            os.environ.pop("S9_ROOT", None)
        rows = m.tunnel_info(self.root)
        self.assertEqual([r["lport"] for r in rows], [self.L])
        self.assertTrue(rows[0]["alive"])
        line = m.tunnel_line(rows)
        self.assertIn(f"{self.L}→{self.R}", line)
        self.assertIn("실행 중", line)
        self.assertIn("ssh 터널", line)

    def test_t3_reconnects_after_ssh_dies(self):
        before = self.state(self.L)
        first = self.ssh_pids()[-1]
        self.assertEqual(before["child_pid"] and True, True)
        os.kill(first, signal.SIGTERM)
        st = wait_for(lambda: (lambda s: s and s.get("retries", 0) >= 1 and
                              s.get("status") == "up" and self.ssh_pids()[-1] != first and s)
                      (self.state(self.L)), timeout=15)
        self.assertTrue(st, f"재연결이 안 됐다: {self.state(self.L)}")
        self.assertEqual(st["pid"], before["pid"], "감시자는 그대로여야 한다")
        second = self.ssh_pids()[-1]
        self.assertNotEqual(first, second)
        self.assertTrue(alive(second))
        self.assertEqual(len(read(self.args_log).strip().splitlines()), 2)

    def test_t4_secret_value_absent_from_state_and_log(self):
        stdir = os.path.join(self.root, "state")
        leaked = []
        for fn in os.listdir(stdir):
            p = os.path.join(stdir, fn)
            if not os.path.isfile(p):
                continue
            try:
                body = read(p)
            except OSError:
                continue
            if self.token in body:
                leaked.append(fn)
        self.assertEqual(leaked, [], "비밀 값이 state/ 에 새었다")
        self.assertIn(self.NAME, json.dumps(self.state(self.L)))

    def test_t5_stop_kills_both_and_clears_state(self):
        st = self.state(self.L)
        sup, child = st["pid"], self.ssh_pids()[-1]
        out = self.cli("tunnel", str(self.L), "--stop")
        self.assertIn(str(self.L), out)
        self.assertTrue(wait_for(lambda: not alive(sup)), "감시자가 종료되지 않았다")
        self.assertTrue(wait_for(lambda: not alive(child)), "ssh 가 종료되지 않았다")
        self.assertIsNone(self.state(self.L))
        self.assertNotIn(f"{self.L}→", self.cli("tunnel", "--status"))
        # 두 번째 --stop 은 조용히 성공한다 (멱등)
        self.cli("tunnel", str(self.L), "--stop")


class KeepAndCode(_Base):
    """S7 — --keep 이 state/tunnels.json 에 적고, s9 code 기동이 그것을 올린다."""
    L, R = 45929, 45920

    @classmethod
    def ports(cls):
        return [cls.L]

    def test_keep_then_code_autostarts_and_stop_forgets(self):
        self.cli("tunnel", self.NAME, str(self.L), str(self.R), "--keep")
        keep = os.path.join(self.root, "state", "tunnels.json")
        self.assertTrue(os.path.exists(keep))
        with open(keep, encoding="utf-8") as f:
            rows = json.load(f)
        self.assertEqual([(r["secret"], r["lport"], r["rport"]) for r in rows],
                         [(self.NAME, self.L, self.R)])
        st = wait_for(lambda: self.state(self.L))
        # 같은 포트로 다시 띄우면 두 번째는 「이미 실행 중」 — 감시자가 둘이 되지 않는다
        out = self.cli("tunnel", self.NAME, str(self.L), str(self.R))
        self.assertIn("이미", out)
        self.assertEqual(self.state(self.L)["pid"], st["pid"])
        # 감시자를 강제 종료해(세션 종료와 같은 상황) code 기동이 다시 올리는지
        os.kill(st["pid"], signal.SIGKILL)
        wait_for(lambda: not alive(st["pid"]))
        for pid in self.ssh_pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        # `s9 code` 는 대시보드 감시자까지 띄우므로 여기서는 그 안의 같은 갈래
        # (`tunnel --autostart`)를 직접 부르고, code 가 그 갈래를 지나는지는
        # 원문 계약으로 잰다 — 실서버를 띄우지 않는다(빠른 테스트 규칙).
        src = read(os.path.join(REPO, "bin", "s9.py"))
        # 함수 **전체**를 본다 — 4000자 창은 첫 실행·합류 갈래(REQ-20260913-007·013)가
        # 앞에 서면서 터널 줄이 창 밖으로 밀렸다(실측 2026-09-13).
        _s = src.index("def cmd_code(")
        body = src[_s:src.index("\ndef ", _s + 1)]
        self.assertIn("tunnel_autostart(", body, "s9 code 가 터널 자동 기동을 지나지 않는다")
        r = subprocess.run([S9, "tunnel", "--autostart"], capture_output=True, text=True,
                           env=self.env, timeout=60, stdin=subprocess.DEVNULL)
        self.assertIn("터널", r.stdout + r.stderr)
        st2 = wait_for(lambda: (lambda s: s and s.get("pid") != st["pid"] and alive(s["pid"]) and s)
                       (self.state(self.L)))
        self.assertTrue(st2, f"code 기동이 터널을 안 올렸다: {r.stdout}{r.stderr}")
        self.cli("tunnel", str(self.L), "--stop")
        with open(keep, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])


class Grandchild(_Base):
    """S9·S10 — 래퍼(child_pid)가 종료돼도 손자 ssh 가 남으면 그룹을 정리하고 다시 잇는다.
    실측 2026-09-06: child_pid 를 kill 하니 ssh 가 살아남아 포트를 쥐었고, 새 ssh 는
    「Address already in use」로 5회 연속 실패 — 사람이 그룹을 죽인 뒤에야 이어졌다."""
    L, R = 45949, 45940
    NAME = "tunnelwrap"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 이 클래스의 비밀 값은 래퍼를 가리킨다 (손자 구조)
        r = subprocess.run([S9, "secret", "set", cls.NAME], input=cls.wrap,
                           capture_output=True, text=True, env=cls.env, timeout=30)
        assert r.returncode == 0, r.stdout + r.stderr

    @classmethod
    def ports(cls):
        return [cls.L]

    def test_t1_wrapper_killed_grandchild_reaped_then_reconnected(self):
        self.cli("tunnel", self.NAME, str(self.L), str(self.R))
        st = wait_for(lambda: (self.state(self.L) or {}).get("child_pid") and self.state(self.L))
        first = wait_for(lambda: self.ssh_pids() and self.ssh_pids()[-1])
        self.assertTrue(alive(first))
        # 래퍼(child_pid = `s9 secret run`)만 종료 — 손자 fakessh 는 같은 그룹에 남는다
        os.kill(st["child_pid"], signal.SIGTERM)
        st2 = wait_for(lambda: (lambda s: s and s.get("status") == "up" and
                               s.get("retries", 0) >= 1 and self.ssh_pids()[-1] != first and s)
                       (self.state(self.L)), timeout=15)
        self.assertTrue(st2, f"재연결이 안 됐다: {self.state(self.L)}")
        self.assertFalse(alive(first), "손자 ssh 가 정리되지 않고 남았다")
        second = self.ssh_pids()[-1]
        self.assertTrue(alive(second))
        log = read(os.path.join(self.root, "state", f"tunnel-{self.L}.log"))
        self.assertIn("남은 ssh 그룹", log)

    def test_t2_address_in_use_means_reap_and_immediate_retry(self):
        st = self.state(self.L)
        before = st["retries"]
        cur = self.ssh_pids()[-1]
        logp = os.path.join(self.root, "state", f"tunnel-{self.L}.log")
        busy = self.args_log + ".busy"
        open(busy, "w").close()                    # 다음 ssh 는 「포트 점유」로 끝난다
        os.kill(cur, signal.SIGTERM)
        self.assertTrue(wait_for(lambda: "즉시 재시도" in read(logp), timeout=15),
                        "포트 점유를 즉시 재시도로 다루지 않았다")
        os.remove(busy)
        st2 = wait_for(lambda: (lambda s: s and s.get("status") == "up" and
                               s.get("retries", 0) > before + 1 and alive(s.get("child_pid") or 0) and s)
                       (self.state(self.L)), timeout=20)
        self.assertTrue(st2, f"포트가 풀린 뒤 다시 잇지 못했다: {self.state(self.L)}")
        self.assertEqual(st2["pid"], st["pid"])
        # 즉시 재시도는 한 번뿐 — 두 번째 점유는 backoff 로 간다 (핫루프 금지)
        self.assertLessEqual(read(logp).count("즉시 재시도"), 2)
        self.assertTrue(wait_for(lambda: not alive(cur)))


class Rejections(_Base):
    """S6·S8 — 이름은 필수, 모르는 이름은 감시자가 뜨기 전에 거부."""

    def test_name_required_and_unknown_rejected(self):
        out = self.cli("tunnel", "45939", "45930", expect=1)
        self.assertIn("포트", out)          # 이름 없이 숫자 둘이면 사용법으로 거부
        self.assertFalse(os.path.exists(os.path.join(self.root, "state", "tunnel-45930.json")))
        out = self.cli("tunnel", "nosuchsecret", "45939", "45930", expect=1)
        self.assertIn("nosuchsecret", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "state", "tunnel-45939.json")))
        out = self.cli("tunnel", self.NAME, "0", "45930", expect=1)
        self.assertIn("포트", out)

    def test_no_default_secret_name_in_code(self):
        src = read(os.path.join(REPO, "bin", "s9.py"))
        i = src.index("def cmd_tunnel(")
        block = src[i:i + 6000]
        self.assertNotRegex(block, r"default=['\"][A-Za-z]", "터널 명령에 기본 비밀 이름이 있다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
