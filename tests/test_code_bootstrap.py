"""세션이 스스로 수신 대기를 켜는가 (REQ-20260827-025-62x6).

재부팅 뒤 `s9 code` 를 실행하면 대시보드 터미널이 `idle` 로 남는다. 사람이
아무 줄이나 한 번 쳐야 그제서야 `live` 가 된다 — 여태 그래 왔다.

이유는 하나다. `claude` 는 대화형으로 뜨면 **첫 사용자 입력 전까지 한 턴도
돌지 않는다.** SessionStart 훅이 "수신함 tail 을 arm 하라"고 컨텍스트에 넣어
두어도, 그 지시를 실행할 주체가 아직 안 깨어 있다. 그래서 대시보드의
`_inbox_watch_alive()` 는 false 를 보고, 화면은 정직하게 idle 이라고 쓴다.
화면이 거짓말을 한 적은 없다 — 세션이 정말로 안 듣고 있었다.

그래서 `s9 code` 가 **기동 프롬프트 한 줄**을 붙여 세션이 스스로 첫 턴을 돌게
한다. 그 줄은 사용자의 말이 아니므로 REQ 카드도, 감사 서문도 만들지 않는다.

실행: python3 tests/ code_bootstrap
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")

# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100)
from portpool import pool_socket  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load("s9_bootstrap_hook", HOOK)
# 격리 (test_audit_prompt.py 와 같은 이유): 무인 워커 세션에서 스위트를 돌리면
# 상속된 S9_AUTO_RESUME=1 이 main() 을 auto-resume 분기로 보낸다.
os.environ.pop("S9_AUTO_RESUME", None)


class CodeBootstrap(unittest.TestCase):
    """`s9 code` 가 만드는 명령줄만 본다 (S9_CODE_DRYRUN — claude 는 안 뜬다)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9boot-")
        # 더미 리스너: cmd_code 의 포트 체크를 통과시켜 실서버 스폰 방지
        cls.lsock = pool_socket()
        cls.port = cls.lsock.getsockname()[1]
        threading.Thread(target=cls._accept_loop, daemon=True).start()
        # HOME 격리 + 훅 설치済 가장 — preflight 가 실 HOME 을 만지지 않게
        cls.home = tempfile.mkdtemp(prefix="s9boothome-")
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
        with open(os.path.join(cls.home, ".claude", ".credentials.json"),
                  "w") as f:
            f.write("{}")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_PORT": str(cls.port),
                   "HOME": cls.home, "S9_CODE_DRYRUN": "1",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.env.pop("S9_AUTO_RESUME", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=15)
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

    def code(self, *argv):
        r = subprocess.run([S9, "code", *argv], capture_output=True, text=True,
                           env=self.env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        last = r.stdout.strip().splitlines()[-1]
        return json.loads(last)

    # N1. 인자 없이 부르면 기동 프롬프트가 마지막 인자로 붙는다
    def test_code_bootstrap(self):
        """`s9 code` 가 만드는 명령줄만 본다 (S9_CODE_DRYRUN — claude 는 안 뜬다)."""
        with self.subTest("n1_bootstrap_appended"):
                cmd = self.code()
                self.assertTrue(cmd[-1].startswith(hook.BOOTSTRAP_MARK), cmd)

            # N2. 그 줄은 수신 대기를 켜라고 말한다 — 기동의 목적이 그것이다
        with self.subTest("n2_says_arm"):
                self.assertIn("수신함", self.code()[-1])

            # B1. 사용자가 자기 프롬프트를 줬으면 붙이지 않는다 — 위치 인자가 둘이 되면
            #     claude 가 받아들이지 않는다. 사람의 말이 우선이다.
        with self.subTest("b1_user_prompt_wins"):
                cmd = self.code("포트 상태 봐줘")
                self.assertEqual(cmd[-1], "포트 상태 봐줘", cmd)
                self.assertFalse(any(a.startswith(hook.BOOTSTRAP_MARK) for a in cmd),
                                 cmd)

            # B2. 플래그만 준 경우는 프롬프트가 없는 것이다 — 기동 줄이 붙는다
        with self.subTest("b2_flags_only_still_boots"):
            cmd = self.code("--permission-mode", "acceptEdits")
            self.assertIn("acceptEdits", cmd)
            self.assertTrue(cmd[-1].startswith(hook.BOOTSTRAP_MARK), cmd)

class BootstrapTurnIsNotAsk(unittest.TestCase):
    """F1·F2·R1 — 기동 줄은 사용자의 요청이 아니다."""

    def _run_hook(self, prompt):
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            # 훅은 몇몇 출력을 실제로 파싱한다 — 빈 문자열을 주면 그 자리에서
            # 죽어 분류 자체를 못 본다 (`new` 의 문서 id, `user current` 의 이름)
            out = ("REQ-20260827-999-test created" if argv[0] == "new"
                   else "tester")
            return mock.Mock(returncode=0, stdout=out)

        payload = json.dumps({"prompt": prompt, "session_id": "bbbb1111xx"})
        with mock.patch.object(hook, "run", fake_run), \
             mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            hook.main()
        return calls, out.getvalue()

    # F1. 카드를 만들지 않는다
    def test_bootstrap_turn_is_not_ask(self):
        """F1·F2·R1 — 기동 줄은 사용자의 요청이 아니다."""
        with self.subTest("f1_no_card"):
                calls, _ = self._run_hook(hook.BOOTSTRAP_MARK + " 세션 기동")
                self.assertFalse(any(a[0] == "new" for a in calls), calls)

            # F2. 감사 서문을 주입하지 않는다 — 세션 첫 화면을 훅 텍스트로 덮지 않는다.
            #     (응답 형식 규율 한 줄은 어느 턴에나 붙는 전역 규칙이라 여기서도 남는다.)
        with self.subTest("f2_no_audit_preamble"):
                _, printed = self._run_hook(hook.BOOTSTRAP_MARK + " 세션 기동")
                self.assertNotIn("[section9 audit]", printed)
                self.assertLess(len(printed), 1200, printed)

            # R1. 마커 없는 보통 프롬프트는 예전대로 — request 는 카드를 만든다
        with self.subTest("r1_normal_prompt_still_audited"):
            calls, _ = self._run_hook(
                "대시보드 헤더에 서버 상태 배너를 새로 만들어줘. 자리는 로고 오른쪽이다.")
            self.assertTrue(any(a[0] == "new" for a in calls), calls)

if __name__ == "__main__":
    unittest.main()
