"""캡처 위생 계약 — s9 shot 이 브라우저를 남기지 않는다 (REQ-20260825-099).

2026-08-25 사고: 캡처 40~60회 만에 윈도우 chrome.exe 가 165개까지 쌓여 호스트
동적 포트가 96% 소진됐고, 그 결과 브라우저는 ERR_NO_BUFFER_SPACE, WSL 은 새
리스닝 포트 공개 실패, 테스트는 29건 connection refused 로 무너졌다.

여기서 고정하는 계약은 세 가지다.
1. 캡처마다 **전용 프로필**을 쓴다 — 사용자의 브라우저 세션에 붙지 않고,
   끝난 뒤 "우리 것만" 골라 죽일 수 있는 표식이 된다.
2. 성공·실패·타임아웃 **어느 경로로 나가든** 회수한다(finally). 사고 당시엔
   실패 경로에서 그냥 빠져나가 프로세스가 남았다.
3. 살아 있는 캡처가 상한을 넘으면 **더 얹지 않는다**. 단, 상한을 보기 전에
   먼저 회수를 돌린다 — 죽은 것 때문에 막히면 사람이 상한을 무시하게 되고
   그 순간 상한은 없는 것이 된다.

실행: python3 tests/ shot_hygiene
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# 접두사를 "s9shot-" 으로 두면 안 된다 — 그건 이 테스트가 검증하는 회수 장치가
# 지우는 표식이다. s9-doctor 의 sweep_stale_shots 는 TMPDIR 에서 SHOT_MARKERS
# ("s9shot-"/"cdp-prof-") 로 시작하는 디렉터리를 rmtree 하고, 소유자 판정
# 정규식이 s9shot-(\d+) 라 mkdtemp 의 랜덤 접미사가 숫자로 시작하면(예:
# s9shot-9j2anjm6 → pid 9) 죽은 pid 로 읽혀 즉시 삭제 대상이 된다.
# 캡처는 매번 sweep 을 선행하므로 스위트 실행 중 캡처가 한 번이라도 돌면
# 이 테스트의 S9_ROOT 가 통째로 사라지고 FileNotFoundError 로 깨진다 —
# 접미사 뽑기에 따라 되기도 안 되기도 하던 플레이크다.
TMP = tempfile.mkdtemp(prefix="s9-shothyg-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_shot", importlib.machinery.SourceFileLoader("s9_mod_shot", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class Args:
    def __init__(self, **kv):
        self.url = "http://127.0.0.1:9909/"
        self.out = os.path.join(TMP, "shot.png")
        self.size = "1440,900"
        self.wait = "3000"
        self.__dict__.update(kv)


def run_shot(alive=0, run_side_effect=None, args=None, make_out=True):
    """cmd_shot 을 격리 실행한다 — 브라우저는 리눅스 경로(가짜)로 고정.

    반환: (subprocess.run 호출 인자 목록, 회수 호출 목록, SystemExit 코드 or None)
    """
    calls, reclaimed = [], []

    def fake_run(argv, *a, **kw):
        calls.append(argv)
        if run_side_effect:
            raise run_side_effect
        if make_out:
            with open(Args().out if args is None else args.out, "wb") as f:
                f.write(b"\x89PNG")
        return mock.Mock(returncode=0, stdout="", stderr="")

    def fake_reclaim(marker, win=False):
        reclaimed.append((marker, win))
        return 0

    # 윈도우 크롬 후보 경로는 이 머신에 실제로 있다 — 테스트는 리눅스 경로
    # 브라우저를 쓰도록 고정해 /mnt/c 쓰기 없이 검증한다.
    real_exists = os.path.exists

    def no_win_browser(p):
        return False if str(p).startswith("/mnt/c/Program Files") else real_exists(p)

    code = None
    with mock.patch.object(subprocess, "run", fake_run), \
         mock.patch.object(mod.os.path, "exists", no_win_browser), \
         mock.patch.object(mod.shutil, "which",
                           lambda n: "/usr/bin/chromium" if n == "chromium" else None), \
         mock.patch.object(mod, "_reclaim_shot_procs", fake_reclaim), \
         mock.patch.object(mod, "_sweep_before_shot", lambda: {"alive": alive}):
        try:
            mod.cmd_shot(args or Args())
        except SystemExit as e:
            code = e.code
        except Exception as e:
            # 브라우저가 죽어 예외가 밖으로 나가는 것 자체는 계약이 아니다 —
            # 중요한 건 그 경로에서도 finally 회수가 돌았는지다.
            code = f"raised:{type(e).__name__}:{e}"
    return calls, reclaimed, code


class TestShotProfile(unittest.TestCase):
    # H1. 캡처마다 전용 프로필 — 사용자 세션에 붙지 않는다
    def test_h1_dedicated_profile(self):
        calls, _r, code = run_shot()
        self.assertIsNone(code, f"정상 캡처가 종료 코드 {code} 로 끝났다")
        self.assertEqual(len(calls), 1, calls)
        argv = calls[0]
        prof = [a for a in argv if a.startswith("--user-data-dir=")]
        self.assertTrue(prof, argv)
        # 표식은 프로세스마다 달라야 한다 — 회수 대상을 남의 것과 구분하는 근거
        self.assertIn(f"s9shot-{os.getpid()}", prof[0])
        for flag in ("--headless=new", "--no-first-run",
                     "--disable-background-networking"):
            self.assertIn(flag, argv, flag)

    # H2. 회수 대상은 그 프로필 — 캡처가 끝나면 우리 것만 정리한다
    def test_h2_reclaim_uses_marker(self):
        calls, reclaimed, _c = run_shot()
        self.assertEqual(len(reclaimed), 1, reclaimed)
        marker = reclaimed[0][0]
        self.assertIn(marker, calls[0][3])   # --user-data-dir 인자와 같은 표식

    # H3. 실패·타임아웃 경로에서도 회수한다 (사고의 직접 원인)
    def test_h3_reclaim_on_timeout(self):
        for exc in (subprocess.TimeoutExpired(cmd="chromium", timeout=60),
                    OSError("browser crashed")):
            with self.subTest(exc=type(exc).__name__):
                _c, reclaimed, _code = run_shot(run_side_effect=exc)
                self.assertEqual(len(reclaimed), 1,
                                 f"{type(exc).__name__} 경로에서 회수가 없다")

    # H4. 프로필 디렉토리도 남기지 않는다
    def test_h4_profile_dir_removed(self):
        removed = []
        real_exists = os.path.exists

        def no_win_browser(p):
            return (False if str(p).startswith("/mnt/c/Program Files")
                    else real_exists(p))

        def fake_run(argv, *a, **kw):
            prof = [x for x in argv if x.startswith("--user-data-dir=")][0]
            os.makedirs(prof.split("=", 1)[1], exist_ok=True)
            with open(Args().out, "wb") as f:
                f.write(b"\x89PNG")
            return mock.Mock(returncode=0)

        with mock.patch.object(subprocess, "run", fake_run), \
             mock.patch.object(mod.os.path, "exists", no_win_browser), \
             mock.patch.object(mod.shutil, "which",
                               lambda n: "/usr/bin/chromium" if n == "chromium" else None), \
             mock.patch.object(mod.shutil, "rmtree",
                               lambda p, **kw: removed.append(p)), \
             mock.patch.object(mod, "_reclaim_shot_procs", lambda m, win=False: 0), \
             mock.patch.object(mod, "_sweep_before_shot", lambda: {"alive": 0}):
            try:
                mod.cmd_shot(Args())
            except SystemExit:
                pass
        self.assertTrue(removed, "프로필 디렉토리 정리가 없다")
        self.assertIn(f"s9shot-{os.getpid()}", removed[0])


class TestShotCap(unittest.TestCase):
    # H5. 상한 초과면 브라우저를 아예 띄우지 않는다 (종료 4 + 안내)
    def test_h5_cap_refuses(self):
        calls, reclaimed, code = run_shot(alive=mod.SHOT_MAX_HEADLESS)
        self.assertEqual(code, 4, code)
        self.assertEqual(calls, [], "상한을 넘겼는데 브라우저를 띄웠다")
        self.assertEqual(reclaimed, [])

    # H6. 상한 아래면 정상 진행 — 경계값에서 막히지 않는다
    def test_h6_below_cap_proceeds(self):
        calls, _r, code = run_shot(alive=mod.SHOT_MAX_HEADLESS - 1)
        self.assertIsNone(code)
        self.assertEqual(len(calls), 1)

    # H7. 상한을 보기 **전에** 회수를 돌린다 — 죽은 개체가 상한을 막지 않게
    def test_h7_sweep_before_cap(self):
        order = []
        real_exists = os.path.exists

        def no_win_browser(p):
            return (False if str(p).startswith("/mnt/c/Program Files")
                    else real_exists(p))

        def fake_sweep():
            order.append("sweep")
            return {"alive": 0}

        def fake_run(argv, *a, **kw):
            order.append("launch")
            with open(Args().out, "wb") as f:
                f.write(b"\x89PNG")
            return mock.Mock(returncode=0)

        with mock.patch.object(subprocess, "run", fake_run), \
             mock.patch.object(mod.os.path, "exists", no_win_browser), \
             mock.patch.object(mod.shutil, "which",
                               lambda n: "/usr/bin/chromium" if n == "chromium" else None), \
             mock.patch.object(mod, "_reclaim_shot_procs", lambda m, win=False: 0), \
             mock.patch.object(mod, "_sweep_before_shot", fake_sweep):
            try:
                mod.cmd_shot(Args())
            except SystemExit:
                pass
        self.assertEqual(order, ["sweep", "launch"], order)

    # H8. 윈도우 쪽 개체수를 못 읽으면 리눅스 ps 폴백으로 센다
    #     (순수 리눅스 환경에서 상한이 통째로 비활성화되면 안 된다)
    def test_h8_linux_fallback_count(self):
        seen = []
        real_exists = os.path.exists

        def no_win_browser(p):
            return (False if str(p).startswith("/mnt/c/Program Files")
                    else real_exists(p))

        with mock.patch.object(subprocess, "run",
                               lambda *a, **kw: mock.Mock(returncode=0)), \
             mock.patch.object(mod.os.path, "exists", no_win_browser), \
             mock.patch.object(mod.shutil, "which",
                               lambda n: "/usr/bin/chromium" if n == "chromium" else None), \
             mock.patch.object(mod, "_reclaim_shot_procs", lambda m, win=False: 0), \
             mock.patch.object(mod, "_sweep_before_shot", lambda: {}), \
             mock.patch.object(mod, "_headless_chrome_pids",
                               lambda marker="": seen.append(marker) or
                               list(range(mod.SHOT_MAX_HEADLESS))):
            code = None
            try:
                mod.cmd_shot(Args())
            except SystemExit as e:
                code = e.code
        self.assertEqual(code, 4, "윈도우 개체수 부재 시 상한이 무력화됐다")


class TestShotArtifacts(unittest.TestCase):
    """프로세스만 회수하고 파일을 남기면 디스크가 조용히 찬다 (REQ-099 3항 d).

    다만 최근 캡처는 검증 근거라 지우면 안 된다 — 나이로만 가른다."""
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9doc-")
        prev = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = cls.root
        try:
            spec = importlib.util.spec_from_loader(
                "s9_doctor_mod", importlib.machinery.SourceFileLoader(
                    "s9_doctor_mod", os.path.join(HERE, "..", "bin", "s9-doctor")))
            cls.doc = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.doc)
        finally:
            if prev is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = prev

    def _shot(self, name, age_sec):
        import time as _t
        d = os.path.join(self.root, "state", "shots")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(b"x" * 1024)
        t = _t.time() - age_sec
        os.utime(p, (t, t))
        return p

    # H10. 오래된 산출물만 지운다 — 최근 것은 근거로 남는다
    def test_h10_prune_old_only(self):
        old = self._shot("old.png", 10 * 86400)
        fresh = self._shot("fresh.png", 60)
        n, freed = self.doc.prune_shot_files()
        self.assertEqual(n, 1, (n, freed))
        self.assertEqual(freed, 1024)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(fresh), "최근 캡처를 지웠다")

    # H11. 지울 게 없으면 조용히 0 — 매번 도는 경로라 부작용이 없어야 한다
    def test_h11_prune_idempotent(self):
        self._shot("recent.png", 60)
        self.assertEqual(self.doc.prune_shot_files(), (0, 0))


class TestSessionStartSweep(unittest.TestCase):
    """serve 가 죽어 있는 동안에는 아무도 고아를 거두지 않는다 — 세션 시작이
    그 공백을 메운다 (REQ-20260825-099). 2026-08-25 사고 직전이 그 구간이었다."""
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_loader(
            "s9_sess_hook", importlib.machinery.SourceFileLoader(
                "s9_sess_hook", os.path.join(HERE, "..", "bin",
                                             "s9-audit-session")))
        cls.hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.hook)

    # H12. 서버가 이미 떠 있어도(=조기 반환 경로) 회수는 던진다
    def test_h12_sweep_even_when_serve_alive(self):
        spawned = []

        class _Sock:
            def close(self):
                pass

        # S9_ROOT 를 저장소로 고정한다 — 스위트 전체 실행에서는 앞선 모듈이
        # 임시 루트를 남겨둘 수 있고, 그 루트엔 bin/s9-doctor 가 없어 회수가
        # 조용히 건너뛰어진다(계약이 아니라 환경 때문에 실패하는 경우).
        repo = os.path.abspath(os.path.join(HERE, ".."))
        with mock.patch.dict(os.environ, {"S9_ROOT": repo}), \
             mock.patch.object(self.hook.subprocess, "Popen",
                               lambda argv, **kw: spawned.append(argv)), \
             mock.patch("socket.create_connection", lambda *a, **kw: _Sock()):
            self.hook.ensure_serve()
        self.assertTrue(spawned, "세션 시작에 회수를 던지지 않는다")
        self.assertIn("--sweep", spawned[0])
        self.assertTrue(spawned[0][1].endswith("s9-doctor"), spawned[0])

    # H13. 회수 실패가 세션 시작을 막지 않는다
    def test_h13_sweep_failure_is_not_fatal(self):
        def boom(*a, **kw):
            raise OSError("no fork")
        with mock.patch.object(self.hook.subprocess, "Popen", boom), \
             mock.patch("socket.create_connection", boom):
            self.hook.ensure_serve()      # 예외가 새어나오면 실패


class TestSuiteNetworkDiscipline(unittest.TestCase):
    """서버를 띄우는 테스트가 고갈에 기름을 붓지 않는다 (사고 당시의 되먹임).

    옛 대기 루프는 0.1초 간격 400회였다 — 공개가 늦어지는 바로 그 순간
    파일마다 400회씩 두드려 커넥션을 쏟아냈다. 지금은 portpool.wait_server
    의 지수 백오프 한 곳으로 모았고, 그 계약은 test_port_pool 이 지킨다.
    여기서는 **다시 갈라지지 않는지**만 본다.
    """
    def test_h9_no_private_wait_loops(self):
        bad = []
        for fn in sorted(os.listdir(HERE)):
            if not fn.startswith("test_") or not fn.endswith(".py"):
                continue
            with open(os.path.join(HERE, fn), encoding="utf-8") as f:
                src = f.read()
            # 서버를 **띄우는** 파일만 본다. 글자 "serve" 로 고르면 주석·
            # 독스트링에 그 말이 있고 create_connection 을 흉내내기로 가로채는
            # 파일까지 걸린다 — test_metrics 가 그 자리였고 서버를 띄우지도
            # 기다리지도 않는다. 실제로 띄우는 자리는 argv 토큰으로 드러난다.
            spawns = ('"serve"' in src) or ("'serve'" in src)
            if not spawns or "create_connection" not in src:
                continue
            if "wait_server" not in src:
                bad.append(fn)
        self.assertEqual(bad, [], f"공용 대기 헬퍼를 안 쓰는 서버 테스트: {bad}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
