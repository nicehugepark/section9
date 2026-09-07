"""`s9 code` 가 대시보드를 브라우저로 연다 (REQ-20260907-035).

여는 도구 이름은 판마다 다르고 없는 판도 있다. 그래서 고르는 일(argv 를
돌려준다)과 부르는 일을 갈라 두었고, 여기서는 **고르는 쪽만** 본다 —
시험이 브라우저를 띄우지 않는다.

고정하는 계약 셋.
1. 판마다 맞는 도구를 고르고, 앞 후보가 없으면 뒤 후보로 떨어진다.
2. 후보가 하나도 없으면 None — 브라우저는 곁가지라 `s9 code` 가 멈추지 않는다.
3. 끄는 길이 있다: `S9_NO_OPEN=1` 과 `s9 code --no-open`.

실행: python3 tests/ code_open
"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-codeopen-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_codeopen", importlib.machinery.SourceFileLoader("s9_mod_codeopen", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

URL = "http://127.0.0.1:9909/"


def have(*names):
    """이 이름들만 설치돼 있는 판을 흉내낸다."""
    return lambda n: ("/usr/bin/" + n) if n in names else None


class PickCmd(unittest.TestCase):
    def test_wsl_prefers_wslview(self):
        self.assertEqual(mod.browser_open_cmd(URL, _which=have("wslview", "xdg-open"),
                                              _plat="WSL"),
                         ["wslview", URL])

    def test_wsl_falls_back_to_explorer(self):
        # wslview 가 없는 WSL 이 흔하다. xdg-open 이 있어도 그것으로 열면
        # 리눅스 안에서 열려 사람 눈에 안 보이니 윈도우 쪽으로 간다.
        self.assertEqual(mod.browser_open_cmd(URL, _which=have("explorer.exe", "xdg-open"),
                                              _plat="WSL"),
                         ["explorer.exe", URL])

    def test_linux_uses_xdg_open(self):
        self.assertEqual(mod.browser_open_cmd(URL, _which=have("xdg-open"), _plat="Linux"),
                         ["xdg-open", URL])

    def test_macos_uses_open(self):
        self.assertEqual(mod.browser_open_cmd(URL, _which=have("open"), _plat="macOS"),
                         ["open", URL])

    def test_none_when_nothing_installed(self):
        self.assertIsNone(mod.browser_open_cmd(URL, _which=have(), _plat="Linux"))


class OffSwitch(unittest.TestCase):
    def test_env_turns_it_off(self):
        old = os.environ.get("S9_NO_OPEN")
        os.environ["S9_NO_OPEN"] = "1"
        try:
            # 껐으면 도구를 고르러 가지도 않는다 — Popen 이 불릴 일이 없다.
            self.assertFalse(mod.browser_open(URL, out=lambda *a, **k: None))
        finally:
            if old is None:
                os.environ.pop("S9_NO_OPEN", None)
            else:
                os.environ["S9_NO_OPEN"] = old

    def test_flag_is_not_passed_to_claude(self):
        # `s9 code` 는 argparse 를 우회해 잔여 인자를 claude 로 넘긴다.
        # 우리 것인 --no-open 이 거기 섞이면 claude 가 모르는 옵션으로 죽는다.
        src = open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8").read()
        self.assertIn('_own = ("--no-claude", "--no-open")', src)


if __name__ == "__main__":
    unittest.main()
