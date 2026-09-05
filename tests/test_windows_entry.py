"""윈도우 네이티브에서 하네스가 서는가 (REQ-20260903-005).

이 시험은 **리눅스에서 윈도우 갈래를 강제해** 돌린다. 그 판이 늘 곁에 있지
않으므로, 갈래를 이름으로 갈라 두고(`proc_backend`·`spawn_backend` 가 세운 그
규율) 여기서 그 이름을 눌러 본다. 실제 윈도우 실행 기록은 REQ 문서에 따로
남는다 — 이 파일이 지키는 것은 **그 기록을 다시 얻을 수 있는 구조**다.

여기 있는 시나리오는 전부 네이티브 윈도우(Python 3.12.10 · NTFS ·
%USERPROFILE%)에서 실측으로 드러난 결함에서 나왔다. 짐작으로 세운 것이 하나도
없다.

실행: python3 tests/ windows_entry
"""
import importlib.machinery
import importlib.util
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BIN = os.path.join(REPO, "bin")
S9 = os.path.join(BIN, "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
sys.path.insert(0, HERE)
import s9cli  # noqa: E402


def _load(path, name):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 훅·설치·git 게이트가 이름으로 부르는 도구들. 여기 있는 것은 그 판에서도
# 진입점이 있어야 한다 — 없으면 그 도구는 윈도우에서 아예 없는 것이다.
WRAPPED = ("s9", "s9-guard", "s9-install", "s9-doctor", "s9-guide-md",
           "s9-git-gate", "s9-audit-prompt", "s9-audit-session",
           "s9-audit-response", "s9-audit-subagent", "s9-audit-agent")
TOOLS = WRAPPED


class TestCmdWrappers(unittest.TestCase):
    """W1·W2·W5 — 그 판의 진입점(`.cmd`)이 지켜야 할 계약."""

    def test_w5_every_tool_has_an_entry_point(self):
        """훅이 부르는 도구마다 윈도우 진입점이 있다."""
        for name in WRAPPED:
            with self.subTest(tool=name):
                self.assertTrue(os.path.isfile(os.path.join(BIN, name)),
                                f"{name}: 도구 자체가 없다")
                self.assertTrue(
                    os.path.isfile(os.path.join(BIN, name + ".cmd")),
                    f"{name}: 윈도우에는 진입점이 없다 — 그 판에서 이 도구는 "
                    f"부를 수가 없다")

    def test_w1_wrapper_runs_the_tool_exactly_once(self):
        """실패해도 두 번 돌지 않는다.

        종전 한 줄 `where python && (A) || (B)` 는 A 가 0이 아닌 코드로 끝나면
        B 를 부른다 — 문서를 쓰는 명령이면 **두 번 쓴다**. 구조로 못박는다:
        도구를 부르는 자리는 한 줄뿐이고, 그 줄에 `||` 가 없다.
        """
        for name in WRAPPED:
            with self.subTest(tool=name):
                body = open(os.path.join(BIN, name + ".cmd"),
                            encoding="ascii").read()
                calls = [ln for ln in body.splitlines()
                         if f"%~dp0{name}" in ln and not ln.lstrip()
                         .lower().startswith("rem")]
                self.assertEqual(len(calls), 1,
                                 f"{name}: 도구를 부르는 줄이 {len(calls)}개다")
                self.assertNotIn("||", calls[0],
                                 f"{name}: `||` 는 실패를 재실행으로 바꾼다")

    def test_w1b_wrapper_propagates_the_exit_code(self):
        """종료코드를 삼키지 않는다 — 훅과 git 게이트의 판정이 여기 걸린다."""
        for name in WRAPPED:
            with self.subTest(tool=name):
                body = open(os.path.join(BIN, name + ".cmd"),
                            encoding="ascii").read()
                self.assertIn("exit /b %ERRORLEVEL%", body)

    def test_w2_wrapper_does_not_trust_the_name_python_alone(self):
        """스토어 별칭 스텁을 피한다.

        `where python` 은 스텁을 먼저 집는다(실측: 아무것도 안 하고 9009).
        그래서 이름을 묻는 것으로 끝내지 않고 **실제로 돌려 본 뒤** 고르고,
        PATH 에 없을 때 갈 자리도 둔다.
        """
        for name in WRAPPED:
            with self.subTest(tool=name):
                body = open(os.path.join(BIN, name + ".cmd"),
                            encoding="ascii").read()
                self.assertNotIn("where python", body)
                self.assertIn('python -c "" >nul 2>nul', body)
                self.assertIn("LOCALAPPDATA", body)

    def test_w4_wrapper_forces_utf8_output(self):
        for name in WRAPPED:
            with self.subTest(tool=name):
                body = open(os.path.join(BIN, name + ".cmd"),
                            encoding="ascii").read()
                self.assertIn("PYTHONUTF8=1", body)

    def test_w4b_wrapper_is_ascii_and_crlf(self):
        """`.cmd` 는 콘솔 코드페이지로 읽힌다 — 한글을 두면 그 줄이 깨진다.

        실측: UTF-8 한글 주석을 담은 래퍼가 cp949 콘솔에서 주석 조각을 명령으로
        실행했다. 까닭은 우리 말로 docs/11-windows.md 에 적고, 파일은 ASCII 로
        둔다. 줄 끝도 CRLF 여야 한다 — cmd.exe 는 LF 만인 배치에서 마지막 줄을
        흘린다.
        """
        for name in WRAPPED:
            with self.subTest(tool=name):
                raw = open(os.path.join(BIN, name + ".cmd"), "rb").read()
                try:
                    raw.decode("ascii")
                except UnicodeDecodeError as e:
                    self.fail(f"{name}.cmd 에 ASCII 아닌 바이트: {e}")
                self.assertIn(b"\r\n", raw, f"{name}.cmd 가 CRLF 가 아니다")

    def test_w5b_wrappers_do_not_drift(self):
        """복제는 갈라진다 — 열한 벌이 도구 이름 말고는 같은 글자여야 한다."""
        # 도구 이름이 **이름으로 서는 자리**만 지운다 — 통째로 replace 하면
        # `s9` 가 `s9-doctor` 의 앞머리와 오류 문구의 `s9:` 까지 먹어 벌마다
        # 다른 글자가 나온다(이 시험이 처음 붉어진 이유가 그것이었다).
        norm = {}
        for name in WRAPPED:
            body = open(os.path.join(BIN, name + ".cmd"),
                        encoding="ascii").read()
            norm[name] = (body.replace("%~dp0" + name, "%~dp0<TOOL>")
                          .replace("`" + name + "`", "`<TOOL>`"))
        shapes = set(norm.values())
        self.assertEqual(len(shapes), 1,
                         "래퍼가 갈라졌다: "
                         + ", ".join(sorted(
                             n for n in norm
                             if norm[n] != norm["s9"])))


class TestKillSignalDoor(unittest.TestCase):
    """W6 — `signal.SIGKILL` 은 윈도우에 없다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9winentry-")
        os.environ["S9_ROOT"] = cls.tmp
        cls.m = _load(S9, "s9winentry")

    def test_w6_door_falls_back_where_sigkill_is_absent(self):
        """있는 판에서는 SIGKILL, 없는 판에서는 SIGTERM.

        **이 시험 자신이 두 판에서 다 돌아야 한다** — 윈도우에서 돌려 보니
        `signal.SIGKILL` 을 곧바로 만지는 첫 줄이 AttributeError 로 죽었다.
        없는 것을 없는 판에서 이름으로 부르지 않는다는 규율이 제품에만
        해당하는 것이 아니다.
        """
        real = getattr(signal, "SIGKILL", None)
        if real is not None:
            self.assertEqual(self.m.sig_kill(), real)
            try:
                del signal.SIGKILL
                self.assertEqual(self.m.sig_kill(), signal.SIGTERM)
            finally:
                signal.SIGKILL = real
        else:
            self.assertEqual(self.m.sig_kill(), signal.SIGTERM)

    def test_w6b_no_bare_sigkill_left_in_the_tool(self):
        """이름을 그대로 쓰던 자리가 다시 생기면 여기서 붉어진다."""
        src = open(S9_SRC, encoding="utf-8").read()
        bare = [ln for ln in src.splitlines()
                if re.search(r"_sig\.SIGKILL|signal\.SIGKILL", ln)
                and "getattr" not in ln and not ln.lstrip().startswith("#")
                and "`" not in ln]          # 까닭을 적은 문장은 제외
        self.assertEqual(bare, [], f"문을 지나지 않는 SIGKILL: {bare}")


class TestTempDoor(unittest.TestCase):
    """W7 — 윈도우에는 `TMPDIR` 도 `/tmp` 도 없다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load(S9, "s9winentry_tmp")

    def test_w7_tmpdir_wins_when_set(self):
        with mock.patch.dict(os.environ, {"TMPDIR": "/somewhere/else"}):
            self.assertEqual(self.m.tmp_dir(), "/somewhere/else")

    def test_w7b_falls_back_to_the_platform_temp(self):
        import tempfile as _t
        env = {k: v for k, v in os.environ.items() if k != "TMPDIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.m.tmp_dir(), _t.gettempdir())

    def test_w7c_no_hardcoded_slash_tmp_left(self):
        src = open(S9_SRC, encoding="utf-8").read()
        hits = [ln for ln in src.splitlines()
                if 'os.environ.get("TMPDIR", "/tmp")' in ln
                and not ln.lstrip().startswith("#")
                and "`" not in ln]          # 문서 문장은 제외
        self.assertEqual(hits, [], f"문을 지나지 않는 /tmp: {hits}")


class TestMetricsCollectorSeam(unittest.TestCase):
    """W9 — 죽이기 전에 묻는 물음이 그 판에서도 답을 내야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load(S9, "s9winentry_metrics")

    def test_w9_goes_through_the_seam_not_slash_proc(self):
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index("def _metrics_is_collector(")
        j = re.compile(r"^def ", re.M).search(src, i + 10).start()
        body = src[i:j]
        self.assertIn("pid_cmdline(", body)
        code = [ln for ln in body.splitlines()
                if "/proc/" in ln and not ln.lstrip().startswith("#")
                and "`" not in ln]
        self.assertEqual(code, [], f"아직 /proc 을 직독한다: {code}")

    def test_w9b_a_foreign_process_is_not_ours(self):
        """남의 프로세스를 우리 것으로 보면 `metrics stop` 이 그것을 죽인다.

        윈도우에서 이 시험이 처음 붉어졌을 때 원인은 판정이 아니라 **프로세스
        표가 통째로 비어 있는 것**이었다 (`_ps_lines` 의 인코딩). 그래서 여기서
        표부터 확인한다 — 못 보는 판에서 「모른다」로 참을 돌려주는 것은 규율이고,
        볼 수 있는 판에서 참이 나오면 결함이다.
        """
        p = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"],
                             stdin=subprocess.DEVNULL)
        try:
            self.m.proc_cache_clear()
            self.assertTrue(self.m.pid_alive(p.pid),
                            "이 판에서 프로세스를 아예 못 본다 — 판정 이전의 결함")
            # 갓 뜬 자식은 exec 가 끝나기 전 잠깐 **명령줄이 비어 있다**. 그
            # 순간을 재면 「모른다」가 나오고, 이 시험은 규율대로 참을 받아 붉어진다
            # — 제품이 아니라 재는 때가 틀린 것이다. 명령줄이 보일 때까지 기다린다.
            for _ in range(50):
                self.m.proc_cache_clear()
                if self.m.pid_cmdline(p.pid):
                    break
                time.sleep(0.1)
            self.assertTrue(self.m.pid_cmdline(p.pid),
                            "자식의 명령줄을 끝내 못 읽었다")
            self.assertFalse(self.m._metrics_is_collector(p.pid),
                             "남의 프로세스를 우리 수집기로 봤다")
        finally:
            p.kill()
            p.wait(timeout=5)

    def test_w9c_unknowable_defers_to_true(self):
        """볼 수 없는 판에서는 참으로 둔다 — 정상 정지를 막는 쪽이 더 나쁘다."""
        old = os.environ.get("S9_PROC_BACKEND")
        os.environ["S9_PROC_BACKEND"] = "none"
        try:
            self.m.proc_cache_clear()
            self.assertTrue(self.m._metrics_is_collector(os.getpid()))
        finally:
            if old is None:
                os.environ.pop("S9_PROC_BACKEND", None)
            else:
                os.environ["S9_PROC_BACKEND"] = old
            self.m.proc_cache_clear()


class TestShotCandidates(unittest.TestCase):
    """W8 — 그 판의 브라우저는 그 판의 이름으로 찾는다."""

    def test_w8_native_windows_branch_exists(self):
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index("    candidates = []")
        block = src[i:i + 2000]
        self.assertIn('os.name == "nt"', block,
                      "네이티브 윈도우 갈래가 없다 — 그 판에서 후보가 0개다")
        self.assertIn("ProgramFiles", block)
        self.assertIn("msedge.exe", block)
        # 설치 드라이브를 가정하지 않는다 — `C:\\` 를 글자로 적으면 D 드라이브
        # 설치에서 조용히 못 찾는다.
        nt = block[block.index('os.name == "nt"'):]
        nt = nt[:nt.index("for base in (")]
        self.assertNotIn("C:\\\\Program", nt)


class TestUtf8OutputDoor(unittest.TestCase):
    """W4 — 도구가 직접 불려도 출력이 UTF-8 이어야 한다."""

    MARK = 'if os.name == "nt":'

    def test_w4c_every_tool_carries_the_guard(self):
        for name in TOOLS:
            with self.subTest(tool=name):
                src = open(os.path.join(BIN, name), encoding="utf-8").read()
                self.assertIn('_std.reconfigure(encoding="utf-8"', src,
                              f"{name}: 윈도우에서 출력이 콘솔 코드페이지로 "
                              f"나간다")

    def test_w4d_guard_stands_before_any_output(self):
        """import 직후에 서야 한다 — 뒤에 서면 그 사이 출력이 이미 깨진다."""
        for name in TOOLS:
            with self.subTest(tool=name):
                src = open(os.path.join(BIN, name), encoding="utf-8").read()
                guard = src.index('_std.reconfigure(encoding="utf-8"')
                self.assertLess(guard, 6000,
                                f"{name}: 가드가 너무 뒤에 선다")


class TestShebangDoor(unittest.TestCase):
    """W3 — 윈도우는 shebang 을 모른다."""

    @unittest.skipIf(os.name == "nt", "이 조항은 shebang 이 있는 판의 계약이다")
    def test_w3_identity_on_posix(self):
        """리눅스·맥에서는 아무것도 하지 않는다 — 기준선이 한 글자도 안 바뀐다."""
        argv = [S9, "ls"]
        self.assertEqual(s9cli.shebang_argv(argv), argv)
        self.assertFalse(s9cli.install(), "리눅스에서 얹으면 기준선이 바뀐다")

    def test_w3b_prefixes_the_interpreter_on_windows(self):
        with mock.patch.object(os, "name", "nt"):
            got = s9cli.shebang_argv([S9, "ls", "--status", "open"])
        self.assertEqual(got, [sys.executable, S9, "ls", "--status", "open"])

    def test_w3c_leaves_other_programs_alone(self):
        """우리 도구가 아닌 것에는 손대지 않는다."""
        with mock.patch.object(os, "name", "nt"):
            self.assertEqual(s9cli.shebang_argv(["git", "status"]),
                             ["git", "status"])
            wrapper = os.path.join(BIN, "s9.cmd")
            self.assertEqual(s9cli.shebang_argv([wrapper, "ls"]),
                             [wrapper, "ls"])
            self.assertEqual(s9cli.shebang_argv([]), [])

    def test_w3d_runner_installs_the_door(self):
        src = open(os.path.join(HERE, "__main__.py"), encoding="utf-8").read()
        self.assertIn("s9cli.install()", src)


class TestDoctorWinBranch(unittest.TestCase):
    """W10 — 진단이 그 판에서 「없다」로 답하면 뒤따르는 판정이 조용히 틀린다."""

    def test_w10_proc_cmd_has_three_branches(self):
        src = open(os.path.join(BIN, "s9-doctor"), encoding="utf-8").read()
        i = src.index("def proc_cmd(")
        body = src[i:re.compile(r"^def ", re.M).search(src, i + 10).start()]
        self.assertIn("/proc/", body)
        self.assertIn('os.name == "nt"', body)
        self.assertIn("Win32_Process", body)
        self.assertIn('"ps"', body)

    def test_w10b_still_answers_on_this_machine(self):
        """어느 판에서 돌든 **자기 자신의 명령줄**은 답해야 한다.

        진단이 "모른다"를 "없다"로 답하면 `reparented`·고아 회수가 조용히
        틀린 판정을 낸다 — 빈 문자열은 그 자체가 결함이다.
        """
        d = _load(os.path.join(BIN, "s9-doctor"), "s9winentry_doctor")
        got = d.proc_cmd(os.getpid())
        self.assertTrue(got, "자기 자신의 명령줄조차 못 읽는다")
        self.assertIn("python", got.lower())


class TestInstallHookCommands(unittest.TestCase):
    """훅이 스텁을 집지 않는다 — 설치가 그 판의 진입점을 적는다."""

    def test_hooks_point_at_the_wrapper_on_windows(self):
        src = open(os.path.join(BIN, "s9-install"), encoding="utf-8").read()
        i = src.index("def install_claude_hooks(")
        body = src[i:re.compile(r"^def ", re.M).search(src, i + 10).start()]
        self.assertIn('script + ".cmd"', body)
        self.assertNotIn("f'python \"{script}\"{args}'", body)
        self.assertIn("sys.executable", body)


class TestToolsCallS9Portably(unittest.TestCase):
    """W11 — 도구가 `bin/s9` 를 부르는 자리 (REQ-20260903-005 실측).

    `subprocess.run([S9, ...])` 는 리눅스에서 shebang 덕에 돌 뿐이다. 윈도우에는
    그 단계가 없어 훅이 s9 를 부르는 자리마다 `WinError 2/193` 이 났다 — 즉
    바인딩·로그·digest·서버 기동이 그 판에서 전부 조용히 실패했다.

    판을 갈라 분기하지 않고 **판에 기대는 것을 없앴다**: 지금 도는 인터프리터로
    그 파일을 연다. 리눅스에서 결과가 같고, 실행 권한 비트에도 안 기댄다.
    """

    HOOKS = ("s9-audit-prompt", "s9-audit-session", "s9-audit-response",
             "s9-audit-subagent", "s9-audit-agent")

    def test_w11_hooks_prefix_the_interpreter(self):
        for name in self.HOOKS:
            with self.subTest(tool=name):
                src = open(os.path.join(BIN, name), encoding="utf-8").read()
                self.assertIn("S9_ARGV = [sys.executable, S9]", src,
                              f"{name}: argv 문이 없다")
                bare = [ln for ln in src.splitlines()
                        if re.search(r"\[S9[,\]]", ln)
                        and not ln.lstrip().startswith("#")]
                self.assertEqual(bare, [],
                                 f"{name}: 문을 지나지 않는 호출: {bare}")

    def test_w11b_inline_paths_prefix_the_interpreter_too(self):
        for name in ("s9", "s9-guard", "s9-install"):
            with self.subTest(tool=name):
                src = open(os.path.join(BIN, name), encoding="utf-8").read()
                bare = [ln for ln in src.splitlines()
                        if '[os.path.join(ROOT, "bin", "s9")' in ln
                        and not ln.lstrip().startswith("#")]
                self.assertEqual(bare, [],
                                 f"{name}: 인터프리터 없이 부른다: {bare}")

    def test_w11c_installer_starts_the_dashboard_portably(self):
        src = open(os.path.join(BIN, "s9-install"), encoding="utf-8").read()
        i = src.index("def start_dashboard(")
        body = src[i:re.compile(r"^def |^if __name__", re.M)
                   .search(src, i + 10).start()]
        self.assertIn("sys.executable", body)
        # `start_new_session` 은 POSIX 전용이다 — 없는 판에서는 그 판의 플래그로.
        self.assertIn("CREATE_NEW_PROCESS_GROUP", body)


class TestInstallDoesNotLieAboutFailure(unittest.TestCase):
    """W12 — 조용한 실패를 성공으로 돌려주지 않는다.

    실측: 네이티브 윈도우에서 `s9-install --quiet` 이 오류 한 줄만 남기고
    **rc=0** 으로 끝났다. post-merge 훅이 그 형태로 부르므로, 설치가 안 된
    기계가 설치된 기계와 구분되지 않았다.
    """

    def test_w12_quiet_does_not_turn_failure_into_success(self):
        src = open(os.path.join(BIN, "s9-install"), encoding="utf-8").read()
        self.assertNotIn("sys.exit(0 if QUIET else 1)", src)
        tail = src[src.index('if __name__ == "__main__":'):]
        self.assertIn("sys.exit(1)", tail)

    def test_w12b_the_git_hook_tolerates_that_nonzero(self):
        """정직해진 종료코드가 git 훅을 멈추지 않는지 함께 못박는다."""
        src = open(os.path.join(BIN, "s9-install"), encoding="utf-8").read()
        i = src.index("def install_git_hooks(")
        body = src[i:re.compile(r"^def ", re.M).search(src, i + 10).start()]
        self.assertIn('s9-install" --quiet || true', body)


class TestFileEncodingIsExplicit(unittest.TestCase):
    """W14 — 파일 인코딩도 주변에 맡기지 않는다 (REQ-20260903-005).

    `open(path)` 의 기본 인코딩은 `locale.getpreferredencoding()` 이다. 리눅스는
    거의 언제나 UTF-8 이라 표가 안 났지만, 한국어 윈도우에서는 **cp949** 다 —
    그러면 이 저장소의 문서(UTF-8)를 읽다 `UnicodeDecodeError` 가 나고, 쓰는
    쪽은 판마다 다른 바이트를 남긴다. 같은 저장소를 두 판에서 함께 쓰는 것이
    이 요청의 목적이므로, 그 자리가 판을 타면 안 된다.

    `.cmd` 래퍼가 `PYTHONUTF8=1` 을 세우지만 그것만 믿지 않는다 — 래퍼를 거치지
    않고 부르는 길(시험·다른 하네스·직접 실행)이 있고, 환경변수는 언제든
    빠질 수 있다. 계약은 코드에 적는다.
    """

    def _bare_opens(self, path):
        import ast
        tree = ast.parse(open(path, encoding="utf-8").read())
        bad = []
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "open"):
                continue
            mode = ""
            if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                mode = str(n.args[1].value)
            for kw in n.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
            if "b" in mode or any(kw.arg is None for kw in n.keywords):
                continue        # 바이트로 여는 것과 **kwargs 는 이 조항 밖이다
            if not any(kw.arg == "encoding" for kw in n.keywords):
                bad.append(n.lineno)
        return bad

    def test_w14_tools_name_the_encoding(self):
        for name in TOOLS:
            with self.subTest(tool=name):
                bad = self._bare_opens(os.path.join(BIN, name))
                self.assertEqual(
                    bad, [],
                    f"{name}: 인코딩을 안 적은 텍스트 open() 줄 {bad} — "
                    f"한국어 윈도우에서는 cp949 로 열린다")


if __name__ == "__main__":
    unittest.main()
