"""Windows 탐색기에서 두 번 눌러 시작 (REQ-20260915-006-62x6).

주인 물음 2026-09-15 11:26: 「윈도우 native 버전에서는 cmd 를 사용하지 않고 윈도우 탐색기에서
실행할 수 있는 환경을 만들어 주는 건 어떤가?」 Claude Code 는 터미널 프로그램이라 콘솔 창은
남지만, **사람이 치는 일**은 없앤다: zip 을 푼 폴더 맨 위의 `section9.cmd`(두 번 누르면 그
창에서 `bin\\s9.cmd code`) · `section9-dashboard.cmd`(대시보드만: `code --no-claude` 가
서버를 보장하고 브라우저를 연다) · 첫 실행이 바탕화면·시작 메뉴에 두는 `section9.lnk`.

배포판은 **작업 트리의 두 파일을 HEAD 위에 얹은 tree** 로 짓는다(임시 index) — HEAD 로만
지으면 그 둘을 처음 담는 commit 의 검사가 옛 HEAD 를 보고 「없다」로 선다.
바로 가기는 PowerShell(WScript.Shell COM)의 몫이라 여기서는 run 을 가짜로 넣어 넘기는
본문(-EncodedCommand 를 UTF-16LE 로 되풀어)만 대조한다 — 실제 .lnk 는 이 컴퓨터의 Windows
에서 실측했다(REQ 노트). 실행: python3 tests/ win_launcher
"""
import base64
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from unpacked import load as _load  # noqa: E402

RELEASE = os.path.join(ROOT, "bin", "s9-release")
FIRSTRUN = os.path.join(ROOT, "bin", "s9_firstrun.py")
LAUNCHERS = ("section9.cmd", "section9-dashboard.cmd", "section9-stop.cmd")
PREFIX = "section9/"


def worktree_tree(paths):
    """HEAD 위에 작업 트리의 `paths` 를 얹은 tree 의 id — 임시 index 라 저장소의 index 는
    건드리지 않는다(개체는 .git/objects 에 남지만 dangling 이라 무해)."""
    fd, idx = tempfile.mkstemp(prefix="s9wl-idx-")
    os.close(fd)
    os.unlink(idx)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_INDEX_FILE"] = idx
    try:
        subprocess.run(["git", "-C", ROOT, "read-tree", "HEAD"], env=env, check=True, capture_output=True)
        subprocess.run(["git", "-C", ROOT, "update-index", "--add", "--", *paths],
                       env=env, check=True, capture_output=True)
        return subprocess.run(["git", "-C", ROOT, "write-tree"], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()
    finally:
        try:
            os.unlink(idx)
        except OSError:
            pass


def read(name):
    with open(os.path.join(ROOT, name), "rb") as f:
        return f.read()


class TheLaunchersInTheRelease(unittest.TestCase):
    """S1 · S2 · S3 · S4 — 세 .cmd(시작·대시보드·끄기)의 계약과 배포판에서의 모양.

    끄기(section9-stop.cmd)는 REQ-20260915-006-62x6 의 반려로 늘었다 — 두 번 눌러
    시작하는데 끄는 것만 명령을 쳐야 하면 같은 사람이 그 자리에서 막힌다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9wl-")
        cls.tree = worktree_tree([*LAUNCHERS, "bin/s9-release"])
        cls.res = subprocess.run([sys.executable, RELEASE, "--ref", cls.tree, "--version", "0.0.0-test",
                                  "--out", cls.tmp], capture_output=True, text=True)
        cls.zip = os.path.join(cls.tmp, "section9-0.0.0-test-windows.zip")
        cls.tgz = os.path.join(cls.tmp, "section9-0.0.0-test-linux-macos.tar.gz")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_s1_zip_carries_both_launchers_as_crlf_ascii(self):
        """S1. zip 의 최상위에 두 .cmd 가 있고 CRLF · ASCII 만이다."""
        import zipfile
        self.assertEqual(self.res.returncode, 0, self.res.stderr)
        with zipfile.ZipFile(self.zip) as zf:
            names = zf.namelist()
            for name in LAUNCHERS:
                self.assertIn(PREFIX + name, names, f"{name} 가 zip 의 최상위에 없다")
                data = zf.read(PREFIX + name)
                self.assertNotIn(b"\r\r\n", data, f"{name}: CR 가 겹쳤다")
                self.assertEqual(data.replace(b"\r\n", b"").count(b"\n"), 0, f"{name}: LF 만인 줄이 있다")
                self.assertTrue(all(b < 128 for b in data), f"{name}: ASCII 밖의 글자 — cmd.exe 는 콘솔 코드페이지로 읽는다")

    def test_s2_each_launcher_moves_home_and_calls_s9_cmd(self):
        """S2. 제 폴더로 이동한 뒤 bin\\s9.cmd 를 `call` 로 부른다 — 시작은 code, 대시보드는 code --no-claude."""
        for name, tail in (("section9.cmd", "code %*"), ("section9-dashboard.cmd", "code --no-claude %*"),
                           ("section9-stop.cmd", "serve --stop %*")):
            text = read(name).decode("ascii")
            self.assertIn('cd /d "%~dp0"', text, f"{name}: 제 폴더로 이동하지 않는다")
            self.assertIn('call "%~dp0bin\\s9.cmd" ' + tail, text, f"{name}: bin\\s9.cmd 를 부르는 줄이 다르다")
            self.assertIn("@echo off", text.splitlines()[0])
            self.assertTrue(text.endswith("\r\n"), f"{name}: 작업 트리에서도 CRLF 다(bin/s9.cmd 와 같은 규칙)")
            self.assertIn("exit /b %RC%", text, f"{name}: 종료 코드를 넘기지 않는다")

    def test_s3_the_window_stays_open_only_on_failure(self):
        """S3. pause 는 종료 코드 검사 블록 안에만 있다 — 정상 종료는 창을 붙들지 않는다."""
        for name in LAUNCHERS:
            text = read(name).decode("ascii").replace("\r\n", "\n")
            block = re.search(r'if not "%RC%"=="0" \((.*?)\n\)', text, re.S)
            self.assertIsNotNone(block, f"{name}: 종료 코드 검사 블록이 없다")
            self.assertIn("pause", block.group(1), f"{name}: 실패 때 창을 붙드는 pause 가 없다")
            self.assertIn("exit code %RC%", block.group(1), f"{name}: 실패 줄에 종료 코드가 없다")
            outside = text.replace(block.group(0), "")
            self.assertNotIn("pause", outside, f"{name}: 정상 종료 길에 pause 가 있다")

    def test_s4_tar_carries_them_without_the_executable_bit(self):
        """S4. 리눅스·맥 tar.gz 에는 최상위 .cmd 가 실행 비트 없이 들어가고 bin/s9 의 비트는 그대로다."""
        with tarfile.open(self.tgz, "r:gz") as tf:
            modes = {m.name: m.mode for m in tf.getmembers() if m.isfile()}
        for name in LAUNCHERS:
            self.assertIn(PREFIX + name, modes)
            self.assertEqual(modes[PREFIX + name] & 0o111, 0, f"{name}: 유닉스에서 실행 파일로 보일 이유가 없다")
        self.assertTrue(modes[PREFIX + "bin/s9"] & 0o111, "bin/s9 의 실행 비트가 사라졌다")


class TheShortcuts(unittest.TestCase):
    """S5 · S6 · S7 — ensure_shortcuts 의 계약(PowerShell 은 가짜)."""

    def setUp(self):
        self.fr = _load("s9_firstrun_shortcuts", FIRSTRUN)
        self.tmp = tempfile.mkdtemp(prefix="s9lnk-")
        self.root = os.path.join(self.tmp, "section9")
        os.makedirs(os.path.join(self.root, "web", "assets"))
        with open(os.path.join(self.root, "section9.cmd"), "wb") as f:
            f.write(b"@echo off\r\n")
        self.desk = os.path.join(self.tmp, "home", "Desktop")
        self.menu = os.path.join(self.tmp, "home", "Programs")
        self.dirs = [("바탕화면", self.desk), ("시작 메뉴", self.menu)]
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_run(self, rc=0, make=True):
        def run(argv, **kw):
            self.calls.append((argv, kw))
            if make:
                for p in re.findall(r"'([^']+\.lnk)'", self.script(argv)):
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    open(p, "wb").close()
            return subprocess.CompletedProcess(argv, rc, b"", b"boom\r\n" if rc else b"")
        return run

    @staticmethod
    def script(argv):
        return base64.b64decode(argv[argv.index("-EncodedCommand") + 1]).decode("utf-16-le")

    def test_s5_one_powershell_call_makes_both_with_target_workdir_icon(self):
        """S5. PowerShell 한 번 — 대상 <root>/section9.cmd · 작업 폴더 <root> · 아이콘 favicon.ico · 이름 section9.lnk."""
        res = self.fr.ensure_shortcuts(self.root, run=self.fake_run(), is_windows=True, dirs=self.dirs)
        self.assertEqual(res["error"], "")
        self.assertEqual(res["created"], ["바탕화면", "시작 메뉴"])
        self.assertEqual(len(self.calls), 1)
        argv, kw = self.calls[0]
        self.assertEqual(argv[:5], ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"])
        self.assertEqual(kw.get("stdin"), subprocess.DEVNULL)
        body = self.script(argv)
        self.assertIn("WScript.Shell", body)
        self.assertIn("'" + os.path.join(self.desk, "section9.lnk") + "'", body)
        self.assertIn("'" + os.path.join(self.menu, "section9.lnk") + "'", body)
        self.assertIn("$s.TargetPath = '" + os.path.join(self.root, "section9.cmd") + "'", body)
        self.assertIn("$s.WorkingDirectory = '" + self.root + "'", body)
        self.assertIn("$s.IconLocation = '" + os.path.join(self.root, "web", "assets", "favicon.ico") + ",0'", body)
        self.assertIn("$s.Save()", body)
        for p in res["paths"]:
            self.assertTrue(os.path.isfile(p))

    def test_s5b_shell_folders_come_from_the_registry_value_expanded_by_env(self):
        """S5b. 자리는 User Shell Folders 의 값(%USERPROFILE%…)을 환경으로 편 것 — 임시 USERPROFILE 이 그대로 따라온다."""
        with mock.patch.dict(os.environ, {"USERPROFILE": r"C:\Temp\s9exp\home",
                                          "APPDATA": r"C:\Temp\s9exp\home\AppData\Roaming"}):
            dirs = dict(self.fr.shortcut_dirs())     # 리눅스에는 winreg 가 없어 기본값을 편다
        self.assertEqual(dirs["바탕화면"], r"C:\Temp\s9exp\home\Desktop")
        self.assertEqual(dirs["시작 메뉴"], r"C:\Temp\s9exp\home\AppData\Roaming\Microsoft\Windows\Start Menu\Programs")
        self.assertEqual(self.fr._ps_quote("C:\\it's"), "'C:\\it''s'")

    def test_s6_existing_ones_are_left_alone(self):
        """S6. 둘 다 있으면 PowerShell 을 부르지 않고(exists), 하나만 없으면 그것만; 최상위 section9.cmd 가 없는 자리는 no-launcher."""
        os.makedirs(self.desk)
        open(os.path.join(self.desk, "section9.lnk"), "wb").close()
        res = self.fr.ensure_shortcuts(self.root, run=self.fake_run(), is_windows=True, dirs=self.dirs)
        self.assertEqual(res["created"], ["시작 메뉴"], res)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn(os.path.join(self.desk, "section9.lnk"), self.script(self.calls[0][0]))
        res = self.fr.ensure_shortcuts(self.root, run=self.fake_run(), is_windows=True, dirs=self.dirs)
        self.assertEqual((res["skipped"], res["created"], len(self.calls)), ("exists", [], 1), res)
        os.remove(os.path.join(self.root, "section9.cmd"))
        res = self.fr.ensure_shortcuts(self.root, run=self.fake_run(), is_windows=True, dirs=self.dirs)
        self.assertEqual(res["skipped"], "no-launcher")
        self.assertEqual(len(self.calls), 1)

    def test_s7_failures_come_back_as_one_line_and_other_platforms_skip(self):
        """S7. powershell 없음 · rc≠0 · timeout 은 예외 없이 error 한 줄; Windows 가 아니면 not-windows."""
        def missing(argv, **kw):
            raise FileNotFoundError("powershell")

        def slow(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 60)
        res = self.fr.ensure_shortcuts(self.root, run=missing, is_windows=True, dirs=self.dirs)
        self.assertEqual(res["error"], "powershell 이 없다")
        res = self.fr.ensure_shortcuts(self.root, run=self.fake_run(rc=1, make=False), is_windows=True, dirs=self.dirs)
        self.assertEqual(res["error"], "powershell rc=1: boom")
        self.assertEqual(res["created"], [])
        res = self.fr.ensure_shortcuts(self.root, run=slow, is_windows=True, dirs=self.dirs)
        self.assertIn("60초", res["error"])
        res = self.fr.ensure_shortcuts(self.root, run=self.fake_run(rc=0, make=False), is_windows=True, dirs=self.dirs)
        self.assertIn("파일이 없다", res["error"])
        res = self.fr.ensure_shortcuts(self.root, run=missing, is_windows=False, dirs=self.dirs)
        self.assertEqual(res["skipped"], "not-windows")
        self.assertEqual(self.fr.ensure_shortcuts(self.root, run=missing)["skipped"],
                         "not-windows" if os.name != "nt" else "")

    def test_s7b_first_run_calls_it_once_after_install_and_never_dies_on_it(self):
        """S7b. `s9 code` 의 첫 실행 길(설치 블록)에서 한 번 부르고, 결과는 print 로만 말한다."""
        with open(os.path.join(ROOT, "bin", "s9.py"), encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def cmd_code(args):"):]
        body = body[:body.index("\ndef ", 10)]
        self.assertEqual(body.count("ensure_shortcuts(ROOT)"), 1)
        self.assertLess(body.index("s9-install"), body.index("ensure_shortcuts(ROOT)"))
        self.assertIn("바로 가기를 만들지 못했다", body)
        self.assertNotIn('die(f"바로 가기', body)


class TheShortcutsGoAwayToo(unittest.TestCase):
    """S10~S13 — 걷기는 놓기의 대칭이다 (REQ-20260915-006-62x6, 주인 지적 2026-09-15:
    「끄는 법, 삭제하는 법 등에 대해서는 가이드가 없는 것 같다」). 걷지 않으면 폴더를
    지운 뒤 바탕화면에 아무 데도 닿지 않는 바로 가기가 남는다."""

    def setUp(self):
        self.fr = _load("s9_firstrun_rmlnk", FIRSTRUN)
        self.tmp = tempfile.mkdtemp(prefix="s9rmlnk-")
        self.root = os.path.join(self.tmp, "section9")
        os.makedirs(self.root)
        self.target = os.path.join(self.root, "section9.cmd")
        self.desk = os.path.join(self.tmp, "home", "Desktop")
        self.menu = os.path.join(self.tmp, "home", "Programs")
        for d in (self.desk, self.menu):
            os.makedirs(d)
        self.dirs = [("바탕화면", self.desk), ("시작 메뉴", self.menu)]
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lnk(self, where, points_at):
        """가짜 .lnk — 본문이 곧 그 바로 가기의 TargetPath 다."""
        p = os.path.join(where, "section9.lnk")
        with open(p, "w", encoding="utf-8") as f:
            f.write(points_at)
        return p

    def fake_run(self, rc=0):
        """WScript.Shell 대신 — 본문의 대상과 같은 것만 지우고 그 경로를 찍는다."""
        def run(argv, **kw):
            self.calls.append((argv, kw))
            body = TheShortcuts.script(argv)
            want = re.search(r"\$s\.TargetPath -ne '([^']+)'", body).group(1)
            out = []
            for p in re.findall(r"'([^']+\.lnk)'", body):
                if os.path.isfile(p) and open(p, encoding="utf-8").read() == want:
                    os.remove(p)
                    out.append(p)
            return subprocess.CompletedProcess(argv, rc, ("\r\n".join(out) + "\r\n").encode(),
                                               b"boom\r\n" if rc else b"")
        return run

    def test_s10_removes_both_with_one_powershell_call(self):
        """S10. 정상: 둘 다 이 저장소를 가리키면 PowerShell 한 번으로 둘 다 걷는다."""
        made = [self.lnk(self.desk, self.target), self.lnk(self.menu, self.target)]
        res = self.fr.remove_shortcuts(self.root, run=self.fake_run(), is_windows=True, dirs=self.dirs)
        self.assertEqual(res["error"], "")
        self.assertEqual(sorted(res["removed"]), sorted(made))
        self.assertEqual(res["kept"], [])
        self.assertEqual(len(self.calls), 1)
        argv, kw = self.calls[0]
        self.assertEqual(argv[:5], ["powershell", "-NoProfile", "-NonInteractive",
                                    "-ExecutionPolicy", "Bypass"])
        self.assertEqual(kw.get("stdin"), subprocess.DEVNULL)
        for p in made:
            self.assertFalse(os.path.exists(p))

    def test_s11_another_folders_shortcut_is_left_alone(self):
        """S11. 경계: 다른 폴더의 section9 을 가리키는 같은 이름은 남긴다 — 설치가 놓은 것만 걷는다."""
        mine = self.lnk(self.desk, self.target)
        other = self.lnk(self.menu, os.path.join(self.tmp, "other", "section9.cmd"))
        res = self.fr.remove_shortcuts(self.root, run=self.fake_run(), is_windows=True, dirs=self.dirs)
        self.assertEqual(res["removed"], [mine])
        self.assertEqual(res["kept"], [other])
        self.assertTrue(os.path.isfile(other))

    def test_s12_nothing_to_do_and_failures_come_back_as_one_line(self):
        """S12. 실패: 지울 것 없음 · powershell 없음 · rc≠0 — 전부 한 줄로 돌아온다(예외 없음)."""
        res = self.fr.remove_shortcuts(self.root, run=self.fake_run(), is_windows=True, dirs=self.dirs)
        self.assertEqual((res["skipped"], res["removed"], len(self.calls)), ("none", [], 0))
        self.lnk(self.desk, self.target)

        def missing(argv, **kw):
            raise FileNotFoundError("powershell")
        res = self.fr.remove_shortcuts(self.root, run=missing, is_windows=True, dirs=self.dirs)
        self.assertEqual(res["error"], "powershell 이 없다")
        res = self.fr.remove_shortcuts(self.root, run=self.fake_run(rc=1), is_windows=True, dirs=self.dirs)
        self.assertIn("rc=1", res["error"])
        self.assertIn("boom", res["error"])
        res = self.fr.remove_shortcuts(self.root, run=self.fake_run(), is_windows=False, dirs=self.dirs)
        self.assertEqual(res["skipped"], "not-windows")

    def test_s13_uninstall_sweeps_them_and_never_dies_on_it(self):
        """S13. 회귀: uninstall 이 걷는 목록에 바로 가기가 있고, 걷기가 지우기를 막지 않는다."""
        with open(os.path.join(ROOT, "bin", "s9-install"), encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def uninstall("):]
        body = body[:body.index("\ndef ", 10)]
        self.assertIn("remove_shortcuts(root)", body)
        self.assertIn('("shortcut"', body)
        self.assertIn("except Exception", body)      # 바로 가기 때문에 uninstall 이 죽지 않는다


if __name__ == "__main__":
    unittest.main(verbosity=2)
