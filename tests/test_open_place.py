"""이 대시보드가 쓰는 폴더를 그 자리에서 연다 (REQ-20260915-015-62x6).

주인 지적 2026-09-15 13:36: 「한 머신에서도 여러개의 section9이 실행될 수 있다는
사실을 알게됐네… 각 대시보드가 어떤 저장소를 기준으로 실행됐는지 알 수 있어야 하고,
저장소 주소를 클릭하면 탐색기나 터미널이 해당 위치로 실행이 되던가 해야하고」.

고르는 일과 부르는 일을 가른다(browser_open_cmd 와 같은 규율) — 여기서는 argv 만
보고, 프로세스는 띄우지 않는다. 그리고 **경로는 화면에서 받지 않는다**: 받는 순간
이 손잡이로 아무 폴더나 열 수 있게 된다.

실행: python3 tests/ open_place
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
PATH = "/home/hong/section9"


def load():
    spec = importlib.util.spec_from_loader(
        "s9open", importlib.machinery.SourceFileLoader("s9open", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class OpenThePlaceThisDashboardUses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def cmd(self, what, plat, have=("open", "explorer", "explorer.exe", "xdg-open",
                                    "gio", "osascript", "cmd", "cmd.exe",
                                    "x-terminal-emulator")):
        return self.m.open_place_cmd(what, PATH, _which=lambda n: n in have, _plat=plat)

    # O1. 폴더 — 판마다 그 판의 도구
    def test_o1_the_folder_opens_with_the_tool_of_that_platform(self):
        self.assertEqual(self.cmd("folder", "macOS"), ["open", PATH])
        self.assertEqual(self.cmd("folder", "Windows"), ["explorer", PATH])
        self.assertEqual(self.cmd("folder", "linux"), ["xdg-open", PATH])
        # WSL 은 윈도우 쪽 도구로 연다 — 리눅스 도구로 열면 리눅스 안에서 열려
        # 사람 눈에 안 보인다(browser_open_cmd 와 같은 까닭).
        wsl = self.cmd("folder", "WSL")
        self.assertEqual(wsl[0], "explorer.exe")
        self.assertEqual(len(wsl), 2)
        # xdg-open 이 없는 리눅스는 gio 로 물러난다
        self.assertEqual(self.cmd("folder", "linux", have=("gio",)), ["gio", "open", PATH])

    # O2. 터미널 — 그 폴더에서 시작한다
    def test_o2_the_terminal_starts_in_that_folder(self):
        for plat in ("macOS", "Windows", "WSL", "linux"):
            argv = self.cmd("terminal", plat)
            self.assertIsNotNone(argv, plat)
            self.assertIn(PATH, " ".join(argv), f"{plat}: 그 폴더에서 시작하지 않는다")
        self.assertIn("Terminal", " ".join(self.cmd("terminal", "macOS")))
        self.assertIn("cd /d", " ".join(self.cmd("terminal", "Windows")))
        self.assertIn("wsl.exe", self.cmd("terminal", "WSL"))
        self.assertEqual(self.cmd("terminal", "linux")[0], "x-terminal-emulator")

    # O3. 열 도구가 없으면 막다른 길이 아니라 붙여 넣을 한 줄
    def test_o3_no_tool_is_not_a_dead_end(self):
        self.assertIsNone(self.cmd("folder", "linux", have=()))
        self.assertIsNone(self.cmd("terminal", "linux", have=()))
        self.m.open_place_cmd = lambda *a, **k: None      # 도구가 없는 자리를 흉내
        try:
            res = self.m.open_place("terminal", root=PATH)
        finally:
            pass
        self.assertFalse(res["ok"])
        self.assertEqual(res["mode"], "manual")
        self.assertIn(PATH, res["cmd"], "붙여 넣을 한 줄에 경로가 없다")

    # O4. 모르는 값은 열지 않는다 — 여는 것은 폴더와 터미널 둘뿐이다
    def test_o4_only_folder_and_terminal(self):
        self.assertIsNone(self.m.open_place_cmd("etc", PATH,
                                                _which=lambda n: True, _plat="linux"))
        res = self.m.open_place("etc", root=PATH)
        self.assertFalse(res["ok"])

    # O5. 경로는 화면에서 받지 않는다 — 언제나 이 서버의 ROOT 다
    def test_o5_the_path_never_comes_from_the_client(self):
        with open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8") as f:
            src = f.read()
        i = src.index('parsed.path == "/api/open"')
        seg = src[i:i + 600]
        self.assertIn('open_place(str(req.get("what")', seg,
                      "화면이 주는 값은 what 하나여야 한다")
        self.assertNotIn('req.get("path")', seg, "경로를 화면에서 받고 있다")
        self.assertNotIn('req.get("root")', seg, "경로를 화면에서 받고 있다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
