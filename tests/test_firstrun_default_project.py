"""첫 실행을 마치면 기본 프로젝트가 서 있다 (REQ-20260921-025-62x6).

실측 2026-09-21: 코드만 담긴 시드를 clone 해 `s9 code` 를 돌리자 users/<계정> 은
생겼는데 vault/projects 가 비어 있었다. `ensure_default_project()` 를 `s9 code` 의
**이름 물음 등록 갈래 안**에서만 불렀기 때문이다 — 그 물음을 지나친 자리(터미널이
아닌 곳에서 돌렸거나, 안내를 읽고 `s9 user add` 를 손으로 친 자리)는 아무도 그
함수를 부르지 않는다. `s9 init` 은 「다음 s9 init 에서 선다」고 말하지만 그 두 번째
init 을 아무도 돌리지 않는다.

그래서 호출을 물음 **밖**으로 옮겼다: 등록이 어느 길로 끝났든 `s9 code` 가 한 번
세운다(멱등). 이 파일은 그 자리를 **실제 명령으로** 잰다 — claude 는 뜨지 않는다
(S9_CODE_DRYRUN).

실행: python3 tests/ firstrun_default_project
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import pool_socket  # noqa: E402


class FirstRunStandsTheDefaultProject(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 더미 리스너 — cmd_code 의 포트 검사를 통과시켜 실서버 스폰을 막는다
        cls.lsock = pool_socket()
        cls.port = cls.lsock.getsockname()[1]
        threading.Thread(target=cls._accept_loop, daemon=True).start()

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

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9frdp-")
        self.home = tempfile.mkdtemp(prefix="s9frdphome-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        # HOME 격리 + 훅 설치済 가장 — preflight 가 실 HOME 을 만지지 않게
        # (test_code_bootstrap 과 같은 장치: 훅은 '부를 수 있는가'로 판정된다)
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "bin"), exist_ok=True)
        for _n in ("s9-audit-prompt", "s9-audit-session"):
            _p = os.path.join(self.root, "bin", _n)
            with open(_p, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(_p, 0o755)
        with open(os.path.join(self.home, ".claude", "settings.json"),
                  "w", encoding="utf-8") as f:
            f.write(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [
                {"type": "command",
                 "command": os.path.join(self.root, "bin", "s9-audit-prompt")
                            + " 2>/dev/null || true"}]}]}}))
        with open(os.path.join(self.home, ".claude", ".credentials.json"),
                  "w", encoding="utf-8") as f:
            f.write("{}")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_PORT": str(self.port), "HOME": self.home,
                    "S9_CODE_DRYRUN": "1", "S9_NO_OPEN": "1"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_PROJECT",
                  "S9_USER"):
            self.env.pop(k, None)

    # ── 손잡이 ──────────────────────────────────────────────────────────
    def cli(self, *argv, user="tester", check=True):
        env = dict(self.env)
        if user:
            env["S9_USER"] = user
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=120)
        if check:
            self.assertEqual(r.returncode, 0,
                             " ".join(argv) + "\n" + r.stdout + r.stderr)
        return r

    def install_and_register(self):
        """사람이 실제로 지나는 순서 — 설치의 init 은 등록 전이라 빈손이고,
        등록은 안내를 읽고 손으로 친다(`s9 user add`). 두 번째 init 은 없다."""
        self.cli("init")
        self.cli("user", "add", "tester")

    def projects(self):
        d = os.path.join(self.root, "vault", "projects")
        return sorted(f for f in os.listdir(d)) if os.path.isdir(d) else []

    def meta_of(self, path):
        text = open(path, encoding="utf-8").read()
        fm = text.split("---", 2)[1] if text.startswith("---") else ""
        out = {}
        for line in fm.splitlines():
            m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("'\"")
        return out

    def guides(self):
        out = []
        base = os.path.join(self.root, "vault", "requests")
        for dp, _dn, fns in os.walk(base):
            for fn in fns:
                if not fn.endswith(".md"):
                    continue
                meta = self.meta_of(os.path.join(dp, fn))
                if "onboarding" in (meta.get("tags") or ""):
                    out.append(meta)
        return out

    # ── N1 ──────────────────────────────────────────────────────────────
    def test_n1_code_stands_it_when_registration_ended_elsewhere(self):
        """등록이 `s9 user add` 로 따로 끝난 자리도 `s9 code` 가 세운다."""
        self.install_and_register()
        self.assertEqual(self.projects(), [], "등록만으로 서면 안 된다(설치 순서)")
        r = self.cli("code")
        self.assertEqual(self.projects(), ["general.md"], r.stdout + r.stderr)
        meta = self.meta_of(os.path.join(self.root, "vault", "projects",
                                         "general.md"))
        self.assertEqual(meta["slug"], "general")
        self.assertEqual(meta["creator"], "tester")
        self.assertEqual((meta.get("is_default") or "").lower(), "true")
        self.assertIn("기본 프로젝트", r.stdout)

    # ── N2 ──────────────────────────────────────────────────────────────
    def test_n2_the_guides_stand_with_it(self):
        """사용법 안내 요청이 그 프로젝트에 open 으로 함께 선다."""
        self.install_and_register()
        self.cli("code")
        guides = self.guides()
        self.assertTrue(guides, "안내 요청이 서지 않았다")
        for meta in guides:
            self.assertEqual(meta.get("status"), "open", meta.get("title"))
            self.assertEqual(meta.get("project"), "general", meta.get("title"))

    # ── B1 ──────────────────────────────────────────────────────────────
    def test_b1_second_run_changes_nothing(self):
        """멱등 — `s9 code` 는 매번 도는 자리라 두 번째부터는 조용해야 한다."""
        self.install_and_register()
        self.cli("code")
        before = len(self.guides())
        r = self.cli("code")
        self.assertEqual(self.projects(), ["general.md"])
        self.assertEqual(len(self.guides()), before)
        self.assertNotIn("기본 프로젝트 'general' 를 만들었습니다", r.stdout)

    # ── B2 ──────────────────────────────────────────────────────────────
    def test_b2_no_registered_person_stands_nothing(self):
        """설치가 신원을 지어내지 않는다 (REQ-20260908-027) — 그 규칙은 그대로다."""
        self.cli("init", user=None)
        self.cli("code", user=None)
        self.assertEqual(os.listdir(os.path.join(self.root, "users")), [])
        self.assertEqual(self.projects(), [])

    # ── F1 ──────────────────────────────────────────────────────────────
    def test_f1_init_names_the_step_people_actually_take(self):
        """안내가 거짓을 말하지 않는다 — 사람이 다시 치는 것은 `s9 code` 다."""
        r = self.cli("init", user=None)
        self.assertIn("s9 user add", r.stdout)
        self.assertIn("s9 code", r.stdout)


if __name__ == "__main__":
    unittest.main()
