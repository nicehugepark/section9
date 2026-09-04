"""윈도우 동적 포트 고갈 판정·회수 대상 선별 테스트 (REQ-20260825-100).

실사례(2026-08-25): WSL 포트 중계 COM 대리 프로세스(DllHost)가 동적 포트
16,384개 중 15,709개를 Bound 로 잡고 놓지 않아 새 리스닝 포트 공개가
실패했다 — 브라우저는 ERR_NO_BUFFER_SPACE, 테스트 29건 connection refused.
리눅스 쪽 자원 회수(--fix)로는 절대 풀리지 않는 상태라, 진단이 윈도우 쪽
소진도를 보고 회수 대상을 골라내야 한다.

판정 규칙 두 가지를 고정한다:
(1) 소진도 등급 — 고갈된 뒤가 아니라 임계(warn)에서 먼저 알린다.
(2) 회수 대상 — 지배적 점유 + COM 대리(dllhost)일 때만. 사용자 브라우저·앱은
    아무리 많이 잡고 있어도 죽이지 않고 안내만 한다.
실행: python3 tests/ port_exhaustion
"""
import importlib.util
import shutil
import subprocess
import tempfile
import time
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")

spec = importlib.util.spec_from_loader(
    "s9doctor", SourceFileLoader("s9doctor", DOCTOR))
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)

RELAY_CMD = ("C:\\WINDOWS\\system32\\DllHost.exe "
             "/Processid:{17696EAC-9568-4CF5-BB8C-82515AAD6C09}")


def win(bound, top_count=0, name="dllhost.exe", cmd=RELAY_CMD, total=16384):
    return {"bound": bound, "start": 49152, "count": total,
            "top_pid": 31172, "top_count": top_count,
            "top_name": name, "top_cmd": cmd}


class PortVerdict(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(doctor.port_verdict(win(66))["level"], "ok")
        self.assertEqual(doctor.port_verdict(win(11000))["level"], "warn")
        self.assertEqual(doctor.port_verdict(win(15715))["level"], "critical")

    def test_no_windows_side_is_not_an_error(self):
        self.assertEqual(doctor.port_verdict({}), {})
        self.assertEqual(doctor.port_verdict(None), {})


class RecoverTarget(unittest.TestCase):
    def test_recover_target(self):
        """RecoverTarget 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("relay_hoarder_identified"):
            t = doctor.relay_hoarder(win(15715, top_count=15709))
            self.assertIsNotNone(t)
            self.assertEqual(t["pid"], 31172)
            self.assertTrue(t["is_known_relay"])
        with self.subTest("user_app_never_a_target"):
            self.assertIsNone(doctor.relay_hoarder(
                win(15715, top_count=15709, name="chrome.exe", cmd="chrome.exe")))
        with self.subTest("small_share_not_a_target"):
            self.assertIsNone(doctor.relay_hoarder(win(66, top_count=29)))

class Advice(unittest.TestCase):
    def base(self, **kw):
        d = {"probe": {"ok": False, "latency": None, "stage": "publish",
                       "error": "12초 안에 공개되지 않음"},
             "degraded": True, "orphan_test_servers": [],
             "headless_chrome": [], "windows_ports": {}}
        d.update(kw)
        return d

    def test_exhaustion_points_at_reclaim_not_wsl_shutdown(self):
        d = self.base(windows_ports=win(15715, top_count=15709))
        lines = doctor.advise(d)
        text = "\n".join(lines)
        self.assertIn("--recover", text)
        first_recover = next(i for i, l in enumerate(lines) if "--recover" in l)
        # 회수를 설명하며 "wsl --shutdown 과 다르다"고 대비시키는 줄은 제외 —
        # 순서를 보는 것이지 단어 등장을 보는 게 아니다.
        shutdown = [i for i, l in enumerate(lines)
                    if "wsl --shutdown" in l and "--recover" not in l]
        self.assertTrue(shutdown and all(i > first_recover for i in shutdown),
                        "회수가 wsl --shutdown 보다 먼저 제시돼야 한다")
        # 호스트 포트가 이미 말랐으면 리눅스 쪽 --fix 보다 회수가 앞선다.
        first_fix = next(i for i, l in enumerate(lines) if "--fix" in l)
        ladder = [i for i, l in enumerate(lines) if l.startswith("1) ")]
        self.assertTrue(any("--recover" in lines[i] for i in ladder),
                        "고갈 상태에서는 회수가 첫 조치여야 한다")
        self.assertLess(min(i for i in ladder), first_fix)

    def test_warn_level_surfaces_before_exhaustion(self):
        d = self.base(probe={"ok": True, "latency": 0.3},
                      degraded=False, windows_ports=win(11000, top_count=10800))
        text = "\n".join(doctor.advise(d))
        self.assertIn("포트", text)


def dead_pid():
    """확실히 죽은 pid — 자식을 띄우고 곧바로 거둔다."""
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


class Orphan(unittest.TestCase):
    """고아의 정의는 나이가 아니라 **소유자 사망**이다 (REQ-20260826-002).

    나이로 가르면 유예 시간만큼 반드시 쌓인다 — 90%에서 손쓰는 구조가 그래서
    방어가 못 된다. 소유자를 보면 캡처를 띄운 프로세스가 죽는 순간 고아고,
    살아 있는 동안은 절대 대상이 아니다. 즉 "쌓일 수 있는 창"이 없다.
    """

    def setUp(self):
        self.killed = []
        self._kill = doctor.kill_win
        doctor.kill_win = lambda pids: (self.killed.extend(pids), len(pids))[1]
        self._which = doctor.shutil.which
        doctor.shutil.which = lambda name: None      # 프로필 정리 경로 무력화
        self._wintemp = doctor.WIN_TEMP
        doctor.WIN_TEMP = "/nonexistent-s9"

    def tearDown(self):
        doctor.kill_win = self._kill
        doctor.shutil.which = self._which
        doctor.WIN_TEMP = self._wintemp

    def browsers(self, rows):
        return doctor.sweep_stale_shots(browsers=rows)

    def test_dead_owner_is_reclaimed_immediately(self):
        gone = dead_pid()
        out = self.browsers([{"pid": 9001, "age": 2,
                              "cmd": f"chrome.exe --user-data-dir=C:\\Temp\\s9shot-{gone}",
                              "owner": gone}])
        self.assertEqual(self.killed, [9001])
        self.assertEqual(out["orphans"], 1)
        self.assertEqual(out["alive"], 0)

    def test_live_owner_is_never_touched(self):
        """방금 뜬 캡처든 오래 걸리는 캡처든, 소유자가 살아 있으면 대상이 아니다."""
        mine = os.getpid()
        out = self.browsers([{"pid": 9002, "age": 4000, "marker": f"s9shot-{mine}",
                              "cmd": f"chrome.exe --user-data-dir=C:\\Temp\\s9shot-{mine}",
                              "owner": mine}])
        self.assertEqual(self.killed, [])
        self.assertEqual(out["alive"], 1)
        self.assertEqual(out["procs"], 0)

    def test_marker_must_be_exactly_our_shape(self):
        """`s9shot-<pid>` 정확히 그 형태만 소유자 표식이다.

        끝을 막지 않으면 `s9shot-9j2anjm6`(랜덤 접미사가 숫자로 시작) 이
        pid 9 로 읽혀 "죽은 주인"이 되고 남의 디렉터리가 즉시 삭제된다.
        실제로 이 부분매치가 테스트의 임시 루트를 지워 플레이크를 만들었다.
        모르는 형태는 소유자 없음으로 두는 편이 안전하다 — 나이 규칙으로 넘어간다.
        """
        self.assertEqual(doctor.OWNER_RE.search("C:\\Temp\\s9shot-1234").group(1),
                         "1234")
        self.assertEqual(doctor.OWNER_RE.search("s9shot-77 --headless").group(1),
                         "77")
        for wrong in ("s9shot-9j2anjm6", "s9shot-12ab", "s9shot-3_x", "s9shot-4-5"):
            self.assertIsNone(doctor.OWNER_RE.search(wrong), wrong)

    def test_population_counts_captures_not_processes(self):
        """캡처 하나가 프로세스 11개를 띄운다(실측) — 프로세스로 세면 상한 8이
        첫 캡처에서 초과돼 상한 자체가 무의미해진다. 세는 단위는 캡처 건수다."""
        mine = os.getpid()
        rows = [{"pid": 9100 + i, "age": 3, "marker": f"s9shot-{mine}",
                 "cmd": f"chrome.exe --user-data-dir=C:\\Temp\\s9shot-{mine} --type=renderer",
                 "owner": mine} for i in range(11)]
        out = self.browsers(rows)
        self.assertEqual(out["alive"], 1, "캡처 1건으로 세야 한다")
        self.assertEqual(out["alive_procs"], 11)
        self.assertEqual(self.killed, [])

    def test_ownerless_marker_falls_back_to_age(self):
        rows = [{"pid": 9003, "age": 30, "cmd": "chrome.exe cdp-prof-x",
                 "owner": None},
                {"pid": 9004, "age": 5000, "cmd": "chrome.exe cdp-prof-y",
                 "owner": None}]
        out = self.browsers(rows)
        self.assertEqual(self.killed, [9004])
        self.assertEqual(out["stale"], 1)
        self.assertEqual(out["alive"], 1)


class Sweep(unittest.TestCase):
    """프로필 디렉토리도 같은 기준으로 회수한다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9sweep-")
        self._env = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = self.tmp
        # powershell 이 없는 환경으로 두어 윈도우 프로세스는 건드리지 않는다.
        self._which = doctor.shutil.which
        doctor.shutil.which = lambda name: None
        self._wintemp = doctor.WIN_TEMP
        doctor.WIN_TEMP = os.path.join(self.tmp, "no-such")

    def tearDown(self):
        doctor.shutil.which = self._which
        doctor.WIN_TEMP = self._wintemp
        if self._env is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = self._env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mkprof(self, name, age):
        path = os.path.join(self.tmp, name)
        os.makedirs(path, exist_ok=True)
        old = 1_700_000_000.0 - age      # 고정 시각 기준 — 실행 시각에 안 흔들린다
        os.utime(path, (old, old))
        return path

    def test_profile_follows_owner_not_age(self):
        gone = self.mkprof(f"s9shot-{dead_pid()}", 0)     # 소유자 사망 → 즉시
        mine = self.mkprof(f"s9shot-{os.getpid()}", 0)    # 소유자 생존 → 보존
        now = time.time()
        os.utime(mine, (now - 9999, now - 9999))          # 나이는 기준이 아니다
        other = self.mkprof("my-work", 0)                 # 표식 없는 남의 것
        out = doctor.sweep_stale_shots(max_age=600, browsers=[])
        self.assertFalse(os.path.exists(gone))
        self.assertTrue(os.path.exists(mine),
                        "소유자가 살아 있으면 아무리 오래돼도 진행 중이다")
        self.assertTrue(os.path.exists(other), "표식 없는 것은 우리 것이 아니다")
        self.assertEqual(out["profiles"], 1)


if __name__ == "__main__":
    unittest.main()
