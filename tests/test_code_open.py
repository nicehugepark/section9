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

    def test_our_flags_never_reach_claude(self):
        """우리 스위치가 claude 로 새면 claude 가 모르는 옵션으로 죽는다.

        소스 글자를 대조하지 않는다(DOC-20260907-002) — 갈라 주는 함수를 실제로
        불러 무엇이 넘어가는지 본다.
        """
        ns = mod.code_argv(["--no-open", "--no-claude", "-p", "안녕"])
        self.assertTrue(ns.no_open)
        self.assertTrue(ns.no_claude)
        self.assertEqual(ns.claude_args, ["-p", "안녕"])

    def test_order_of_the_rest_is_kept(self):
        # 순서를 흐트러뜨리면 claude 의 위치 인자가 어긋난다 (REQ-20260824-036)
        ns = mod.code_argv(["--model", "x", "--no-open", "질문", "-c"])
        self.assertEqual(ns.claude_args, ["--model", "x", "질문", "-c"])

    def test_nothing_of_ours_means_nothing_removed(self):
        ns = mod.code_argv(["-p", "안녕"])
        self.assertEqual(ns.claude_args, ["-p", "안녕"])
        self.assertFalse(ns.no_open)
        self.assertFalse(ns.no_claude)


if __name__ == "__main__":
    unittest.main()
