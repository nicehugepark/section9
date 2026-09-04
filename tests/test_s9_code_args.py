"""s9 code 실행 인자 전달 테스트 (REQ-20260824-036).

s9 code 뒤의 인자는 claude에 그대로 전달되고(REMAINDER), 계정 설정
s9code_args가 기본 인자로 앞에 붙는다(명령행이 우선). S9_CODE_DRYRUN=1 이면
exec 대신 최종 명령을 JSON으로 출력한다(테스트 시임).

격리: S9_ROOT=mktemp, S9_PORT=유효 포트에 미리 접속 가능해야 서버 스폰이
없다 — 여기서는 더미 리스너를 띄워 대시보드 보장 단계를 스킵시킨다.
실행: python3 tests/test_s9_code_args.py
"""
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import pool_socket  # noqa: E402


class TestAutoUpdate(unittest.TestCase):
    """claude 자동 업그레이드 (REQ-20260825-025): 24h 스로틀·옵트아웃·실패 무해."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9upd-")
        prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE", "S9_USER")}
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "updtester"
        try:
            spec = importlib.util.spec_from_loader(
                "s9_mod_upd", importlib.machinery.SourceFileLoader("s9_mod_upd", S9))
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        cls.stamp = os.path.join(cls.tmp, "state", "claude-update.ts")

    def run_update(self, cfg=None):
        calls = []

        def fake_run(argv, **kw):
            calls.append(argv)
            return mock.Mock(stdout="updated", stderr="")
        with mock.patch.object(self.mod, "user_config",
                               lambda u: dict(cfg or {})), \
             mock.patch("subprocess.run", side_effect=fake_run):
            self.mod._maybe_update_claude()
        return calls

    # U1. 최초 실행 → claude update 1회 + 스탬프 생성 (시도 기준 스로틀)
    def test_u1_first_run_updates(self):
        if os.path.exists(self.stamp):
            os.remove(self.stamp)
        calls = self.run_update()
        self.assertEqual(calls, [["claude", "update"]])
        self.assertTrue(os.path.exists(self.stamp))
        # U2. 24h 내 재실행 → 스킵
        self.assertEqual(self.run_update(), [])
        # U3. 스탬프가 낡으면 다시 시도
        old = time.time() - 90000
        os.utime(self.stamp, (old, old))
        self.assertEqual(self.run_update(), [["claude", "update"]])

    # U4. 옵트아웃(code_autoupdate=off) → 시도 없음
    def test_u4_opt_out(self):
        if os.path.exists(self.stamp):
            os.remove(self.stamp)
        self.assertEqual(self.run_update({"code_autoupdate": "off"}), [])
        self.assertFalse(os.path.exists(self.stamp))


class TestCodeArgs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9code-")
        # 더미 리스너: cmd_code의 포트 체크를 통과시켜 실서버 스폰 방지
        cls.lsock = pool_socket()
        cls.port = cls.lsock.getsockname()[1]
        t = threading.Thread(target=cls._accept_loop, daemon=True)
        t.start()
        # HOME 격리 + 훅 설치済 가장 — preflight(REQ-052)가 실 HOME을 만지거나
        # s9-install을 트리거하지 않게 한다
        cls.home = tempfile.mkdtemp(prefix="s9codehome-")
        os.makedirs(os.path.join(cls.home, ".claude"), exist_ok=True)
        # 훅은 '적혀 있는가'가 아니라 '부를 수 있는가'로 판정된다
        # (REQ-20260828-014) — 가짜 ROOT 에도 실제 스크립트를 세워 둔다.
        os.makedirs(os.path.join(cls.tmp, "bin"), exist_ok=True)
        for _n in ("s9-audit-prompt", "s9-audit-session"):
            _p = os.path.join(cls.tmp, "bin", _n)
            with open(_p, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(_p, 0o755)
        with open(os.path.join(cls.home, ".claude", "settings.json"), "w") as f:
            f.write(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [
                {"type": "command",
                 "command": os.path.join(cls.tmp, "bin", "s9-audit-prompt")
                            + " 2>/dev/null || true"}]}]}}))
        with open(os.path.join(cls.home, ".claude",
                               ".credentials.json"), "w") as f:
            f.write("{}")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_PORT": str(cls.port),
                   "HOME": cls.home,
                   "S9_CODE_DRYRUN": "1", "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env, timeout=15)
        subprocess.run([S9, "user", "add", "tester"], capture_output=True,
                       env=cls.env, timeout=15)

    @classmethod
    def _accept_loop(cls):
        while True:
            try:
                c, _ = cls.lsock.accept()
                c.close()
            except OSError:
                return

    @classmethod
    def tearDownClass(cls):
        cls.lsock.close()

    def run_code(self, *argv):
        r = subprocess.run([S9, "code", *argv], capture_output=True, text=True,
                           env=self.env, timeout=15)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        return last

    # G1. 인자 전달: 뒤따르는 인자가 claude 명령에 그대로 포함
    def test_test_code_args(self):
        """TestCodeArgs 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("g1_args_passthrough"):
                out = self.run_code("--permission-mode", "acceptEdits")
                cmd = json.loads(out)
                self.assertEqual(cmd[0], "claude")
                self.assertIn("--permission-mode", cmd)
                self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "acceptEdits")

            # G2. 계정 기본값: s9code_args 설정이 실행 인자에 포함
        with self.subTest("g2_config_default"):
                subprocess.run([S9, "user", "config", "tester", "s9code_args",
                                "--permission-mode acceptEdits"],
                               capture_output=True, env=self.env, timeout=15)
                try:
                    cmd = json.loads(self.run_code())
                    self.assertIn("--permission-mode", cmd)
                    self.assertIn("acceptEdits", cmd)
                finally:
                    subprocess.run([S9, "user", "config", "tester", "s9code_args", ""],
                                   capture_output=True, env=self.env, timeout=15)

            # G3. 병합 순서: 계정 기본값이 앞, 명령행이 뒤(명령행 우선)
        with self.subTest("g3_merge_order"):
                subprocess.run([S9, "user", "config", "tester", "s9code_args", "--model opus"],
                               capture_output=True, env=self.env, timeout=15)
                try:
                    cmd = json.loads(self.run_code("--model", "sonnet"))
                    self.assertEqual(cmd.index("--model"), 1)          # 기본값이 먼저
                    self.assertEqual(cmd[1:3], ["--model", "opus"])
                    self.assertEqual(cmd[3:5], ["--model", "sonnet"])  # 명령행이 뒤
                finally:
                    subprocess.run([S9, "user", "config", "tester", "s9code_args", ""],
                                   capture_output=True, env=self.env, timeout=15)

            # G5. auto 모드(REQ-20260824-036 반려 반영): s9code_args '--permission-mode
            # auto' 설정 시 claude가 auto 모드로 실행 — 사람이 다시 승인할 필요가 없다
        with self.subTest("g5_auto_mode_config"):
                subprocess.run([S9, "user", "config", "tester", "s9code_args",
                                "--permission-mode auto"],
                               capture_output=True, env=self.env, timeout=15)
                try:
                    cmd = json.loads(self.run_code())
                    self.assertEqual(cmd[1:3], ["--permission-mode", "auto"])
                finally:
                    subprocess.run([S9, "user", "config", "tester", "s9code_args", ""],
                                   capture_output=True, env=self.env, timeout=15)

            # P1. preflight: 훅 미설치 흔적(settings.json에 마커 없음) → s9-install 자동
            #     실행 안내가 출력되고 설치가 수행된다 (REQ-20260824-052)
        with self.subTest("p1_preflight_installs"):
                home2 = tempfile.mkdtemp(prefix="s9codeh2-")
                # 실리포 유사 ROOT(bin/ 존재) — s9-install이 자기 파일들을 찾을 수 있게
                root2 = tempfile.mkdtemp(prefix="s9coderoot-")
                os.symlink(os.path.join(HERE, "..", "bin"),
                           os.path.join(root2, "bin"))
                os.symlink(os.path.join(HERE, "..", "harness"),
                           os.path.join(root2, "harness"))
                env2 = {**self.env, "HOME": home2, "S9_ROOT": root2}
                r = subprocess.run([S9, "code"], capture_output=True, text=True,
                                   env=env2, timeout=60, stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("훅 미설치", r.stdout)
                self.assertTrue(os.path.exists(
                    os.path.join(home2, ".claude", "settings.json")))
                self.assertIn("미로그인", r.stdout)   # credentials 없음 → 로그인 예고
                self.assertIn('["claude"', r.stdout)  # 그 후 실행은 계속된다

            # P2. preflight: 미등록 사용자 + 비대화형 → 등록 안내만 출력(멈추지 않음)
        with self.subTest("p2_preflight_unregistered_notty"):
                env2 = {**self.env}
                env2.pop("S9_USER")               # OS 계정 fallback → 미등록
                r = subprocess.run([S9, "code"], capture_output=True, text=True,
                                   env=env2, timeout=30, stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("미등록 사용자", r.stdout)
                self.assertIn('["claude"', r.stdout)

            # G4. 회귀: --no-claude 는 대시보드만 — dry-run 출력(JSON exec 라인) 없음
        with self.subTest("g4_no_claude"):
            r = subprocess.run([S9, "code", "--no-claude"], capture_output=True,
                               text=True, env=self.env, timeout=15)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn('["claude"', r.stdout)

if __name__ == "__main__":
    unittest.main(verbosity=2)
