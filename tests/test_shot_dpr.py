"""`s9 shot --dpr <배율>` — 배율을 주고 찍는다 (REQ-20260915-026-62x6).

규약은 마크를 **배율 1·1.25·1.5 에서 보라**고 한다(PROTOCOL 19조: 상자가
「14×14, 중심 (7,7)」이어도 비정수 배율에서는 획이 화소 경계에 앉아 흐릿해진다).
그런데 캡처에 배율을 줄 손잡이가 없어, 2026-09-15 의 화면 판정(REQ-20260915-023·024)은
배율 1 만 보고 끝났다 — designer 가 「제가 만든 기하는 전부 정수라 설계상 배율
불변이지만, **눈으로 본 판정은 아닙니다**」로 남긴 자리다.

지키는 것 넷.
  ① 배율이 명령에 실린다 — Chrome 은 깃발(`--force-device-scale-factor`), Playwright 는
     API(컨텍스트의 deviceScaleFactor). CLI 에는 그 옵션이 아예 없어 node 스크립트로
     부른다. 사람이 쓰는 손잡이는 `--dpr` 하나다.
  ② **기본값(1)이면 명령줄이 종전과 한 글자도 다르지 않다** — 없던 옵션이 늘
     붙으면 그것을 모르는 옛 러너에서 캡처가 통째로 깨진다.
  ③ 1.25 는 1.25 로 실린다 — 정수로 반올림하면 이 손잡이의 뜻이 사라진다.
  ④ 못 읽는 값은 **캡처를 걸기 전에** 막는다 — 브라우저를 띄운 뒤 실패하면
     사람은 러너를 의심한다.

실행: python3 tests/ shot_dpr
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-shotdpr-")
os.environ["S9_ROOT"] = TMP

spec = importlib.util.spec_from_loader(
    "s9_for_shot_dpr", importlib.machinery.SourceFileLoader("s9_for_shot_dpr", S9))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TheValue(unittest.TestCase):
    def test_it_reads_the_scales_the_protocol_asks_for(self):
        for raw, want in (("1", 1.0), ("1.25", 1.25), ("1.5", 1.5), (2, 2.0)):
            self.assertEqual(m._shot_dpr(raw), want, raw)

    def test_a_fraction_stays_a_fraction(self):
        self.assertEqual(m._shot_dpr_str(1.25), "1.25")
        self.assertEqual(m._shot_dpr_str(1.5), "1.5")

    def test_a_whole_number_is_written_plainly(self):
        self.assertEqual(m._shot_dpr_str(2.0), "2")

    def test_what_cannot_be_read_stops_before_the_browser(self):
        for raw in ("", "크게", "0", "-1", "9"):
            with self.assertRaises(ValueError, msg=raw):
                m._shot_dpr(raw)


class ThePlaywrightCommand(unittest.TestCase):
    """러너를 띄우지 않는다 — 조립된 명령줄만 본다.

    CLI 에는 배율이 없다(실측 2026-09-15: `--device-scale-factor` 는 unknown option).
    배율은 컨텍스트의 값이라 API 로만 주므로, 배율이 1 이 아니면 같은 playwright 를
    node 스크립트로 부른다."""

    RUNNER = "C:\\Temp\\s9-webkit\\run-npx.cmd"
    DIRECT = ("/mnt/c/Temp/s9-webkit/node-v22-win-x64/node.exe",
              "C:\\Temp\\s9-webkit\\node_modules\\playwright\\cli.js")

    def _cmd(self, **kw):
        with mock.patch.object(m, "_shot_pw_direct", return_value=self.DIRECT):
            return m._shot_webkit_cmd("http://127.0.0.1:9909/", "1440,900", 3000,
                                      "C:\\Temp\\x.png", runner=self.RUNNER, **kw)

    def test_the_scale_rides_along(self):
        cmd = self._cmd(dpr=1.5)
        self.assertIn("-e", cmd, "스크립트 경로가 아니라 CLI 로 갔다")
        self.assertIn("1.5", cmd, "배율이 인자에 없다")
        self.assertIn("deviceScaleFactor", cmd[cmd.index("-e") + 1],
                      "스크립트가 배율을 컨텍스트에 안 준다")

    def test_a_fraction_is_not_rounded(self):
        self.assertIn("1.25", self._cmd(dpr=1.25))

    def test_the_package_path_rides_along(self):
        """`node -e` 에는 모듈 해석의 기준이 없다 — playwright 의 자리를 준다."""
        cmd = self._cmd(dpr=1.5)
        self.assertIn("C:\\Temp\\s9-webkit\\node_modules\\playwright", cmd)

    def test_the_script_is_ascii_only(self):
        """WSL → Windows node 로 건너가며 한글이 깨져 SyntaxError 로 죽었다."""
        m._SHOT_PW_DPR_SCRIPT.encode("ascii")

    def test_the_script_reads_the_args_the_way_node_e_gives_them(self):
        """`-e` 는 스크립트 경로가 없어 argv[1] 부터 사용자 인자다 — slice(2) 면 둘이 잘린다.
        `--` 를 표로 두는 길도 막혀 있다: node 가 그것을 제 옵션으로 먹는다."""
        self.assertIn("process.argv.slice(1)", m._SHOT_PW_DPR_SCRIPT)
        self.assertNotIn('indexOf("--")', m._SHOT_PW_DPR_SCRIPT)

    def test_the_default_changes_nothing(self):
        """배율 1 이면 옛 CLI 명령줄 그대로 — 이 계약이 무너지면 옛 러너가 깨진다."""
        self.assertEqual(self._cmd(dpr=1.0), self._cmd())
        line = " ".join(self._cmd())
        self.assertIn("screenshot", line)
        self.assertNotIn("-e", self._cmd())

    def test_without_a_direct_node_it_says_where_to_go(self):
        """cmd.exe 를 거치는 판에서는 스크립트의 따옴표를 증명할 수 없다 — 거절하고 길을 준다."""
        with mock.patch.object(m, "_shot_pw_direct", return_value=None):
            with self.assertRaises(ValueError) as e:
                m._shot_webkit_cmd("http://x/", "800,600", 1000, "C:\\Temp\\x.png",
                                   runner=self.RUNNER, dpr=1.5)
        self.assertIn("--engine chrome", str(e.exception))


class TheChromeCommand(unittest.TestCase):
    def test_the_same_handle_means_the_same_thing(self):
        """Chrome 경로도 같은 값을 받는다 — 엔진마다 깃발 이름만 다르다."""
        src = open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8").read()
        i = src.index("def cmd_shot(")
        body = src[i:i + 12000]
        self.assertIn("--force-device-scale-factor=", body,
                      "Chrome 경로에 배율이 안 실린다")
        self.assertIn("if dpr != 1.0", body,
                      "배율 1 에서도 깃발이 붙는다 — 종전 명령줄이 달라진다")


class TheMacCommand(unittest.TestCase):
    def test_the_mac_page_is_made_with_that_scale(self):
        self.assertIn("device_scale_factor=dpr", m._SHOT_MAC_PW_SCRIPT,
                      "맥 갈래의 페이지가 배율을 안 받는다")
        self.assertIn("sys.argv[6]", m._SHOT_MAC_PW_SCRIPT,
                      "맥 갈래에 배율이 전달되지 않는다")


if __name__ == "__main__":
    unittest.main()
