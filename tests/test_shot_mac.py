"""s9 shot 맥 후보 (REQ-20260911-002) — 맥에서 후보가 0개이던 결함의 회귀 시험.

2026-09-11 실측: 맥에서 `s9 shot --engine chrome` 이 /Applications 의 Chrome 을
두고도 「브라우저를 찾지 못했습니다. WSL이면 …」로 끝났다. 후보 목록에 윈도우
디스크와 리눅스 PATH 이름밖에 없었다.

실행: python3 tests/ shot_mac
"""
import importlib.machinery
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
sys.path.insert(0, HERE)
import cdpreal  # noqa: E402

TMP = tempfile.mkdtemp(prefix="s9-shotmac-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_shotmac", importlib.machinery.SourceFileLoader("s9_mod_shotmac", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HOME_EDGE = os.path.expanduser(
    "~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
URL = "http://127.0.0.1:9909/"


class Args:
    def __init__(self, **kv):
        self.url = URL
        self.out = os.path.join(TMP, "shot.png")
        self.size = "1440,900"
        self.wait = "3000"
        self.__dict__.update(kv)


def run_shot(present):
    """맥으로 가장하고 cmd_shot 을 격리 실행 — present 에 든 경로만 존재한다.

    반환: (subprocess.run 호출 인자 목록, SystemExit 코드 or None, stderr)"""
    calls = []
    args = Args()

    def fake_run(argv, *a, **kw):
        calls.append(argv)
        with open(args.out, "wb") as f:
            f.write(b"\x89PNG")
        return mock.Mock(returncode=0, stdout="", stderr="")

    real_exists = os.path.exists

    def exists(p):
        p = str(p)
        if p in present:
            return True
        if "/Applications/" in p or p.startswith("/mnt/c/"):
            return False
        return real_exists(p)

    err, code = io.StringIO(), None
    with mock.patch.object(mod, "os_platform", lambda: "macOS"), \
         mock.patch.object(mod, "_playwright_available", lambda: False), \
         mock.patch.object(subprocess, "run", fake_run), \
         mock.patch.object(mod.os.path, "exists", exists), \
         mock.patch.object(mod.shutil, "which", lambda n: None), \
         mock.patch.object(mod, "_reclaim_shot_procs", lambda m, win=False: 0), \
         mock.patch.object(mod, "_sweep_before_shot", lambda: {"alive": 0}), \
         mock.patch.object(sys, "stderr", err):
        try:
            mod.cmd_shot(args)
        except SystemExit as e:
            code = e.code
    try:
        os.remove(args.out)
    except OSError:
        pass
    return calls, code, err.getvalue()


class TestShotMac(unittest.TestCase):
    def test_mac_candidates_found(self):
        """정상: /Applications 의 Chrome 을 찾아 headless 캡처 명령을 만든다."""
        calls, code, err = run_shot({CHROME})
        self.assertIsNone(code, err)
        self.assertEqual(calls[0][0], CHROME, calls)
        self.assertIn("--headless=new", calls[0])
        self.assertTrue(any(a.startswith("--screenshot=") for a in calls[0]), calls[0])
        calls, code, _ = run_shot({HOME_EDGE})       # ~/Applications 만 있어도 잡힌다
        self.assertIsNone(code)
        self.assertEqual(calls[0][0], HOME_EDGE)
        calls, _c, _e = run_shot({CHROME, HOME_EDGE})  # 둘 다면 /Applications 먼저
        self.assertEqual(calls[0][0], CHROME)

    def test_mac_none_hint(self):
        """실패: 후보가 없으면 판별 문구와 맥의 여는 명령으로 비-0."""
        calls, code, err = run_shot(set())
        self.assertEqual(code, 3, err)
        self.assertEqual(calls, [])
        self.assertIn("macOS", err)
        self.assertIn(f"open {URL}", err)
        self.assertNotIn("WSL이면", err)

    def test_list_matches_cdpreal(self):
        """회귀: 시험 헬퍼(cdpreal)의 맥 목록과 도구의 목록이 갈리지 않는다."""
        ours = [os.path.join("/Applications", r) for r in mod.SHOT_MAC_APPS]
        for p in cdpreal.MAC_CANDIDATES:
            self.assertIn(p, ours)


if __name__ == "__main__":
    unittest.main()
