"""계정을 바꿔도 하네스가 따라간다 (REQ-20260827-032-62x6).

사용자 질문: "지금 상태에서 claude 계정을 전환하려고 하는데 어떻게 해야하지?"

전환 기능은 있다 — 대시보드 Terminal 탭의 모델 라벨을 누르면 account 를 고를 수
있고, 고르면 같은 대화를 `CLAUDE_CONFIG_DIR=~/.claude-profiles/<이름>` 로 다시 연다.

그런데 `CLAUDE_CONFIG_DIR` 은 설정 디렉토리 **전체**를 옮긴다 — `settings.json` 도
거기로 간다. 그리고 `bin/s9-install` 은 `~/.claude` 를 하드코딩하고 있었다. 즉 새
프로필에는 section9 훅도, 역할 에이전트도, 스킬도 없다:

    프롬프트가 REQ 로 기록되지 않고 · 응답이 문서에 안 붙고 · 질문 문서도 안 생긴다

**그리고 이 실패는 조용하다.** 계정을 바꾼 사람은 평소처럼 일하는데 외부기억에는
아무것도 안 남는다 — 이 저장소가 가장 경계하는 실패 모양이다. `cmd_code` 의 자가
치유 preflight 도 `~/.claude` 를 봐서 "설치돼 있다"고 판단하고 넘어갔다. 방어가
있는데 보는 곳이 틀렸다.

고침: `CLAUDE_CONFIG_DIR` 을 아는 곳을 `claude_home()` 하나로 두고 두 파일이 그것만
본다. 그러면 이미 있는 자가 치유가 제 눈을 뜬다 — 새 장치를 더하는 게 아니다.

실행: python3 tests/ profile_hooks
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ClaudeHome(unittest.TestCase):
    """N1·B1 — 설정 디렉토리를 아는 곳은 한 군데다."""

    def test_n1_honors_config_dir(self):
        prof = tempfile.mkdtemp(prefix="s9prof-")
        for name, path in (("s9_home", S9), ("s9inst_home", INSTALL)):
            env = dict(os.environ)
            env["CLAUDE_CONFIG_DIR"] = prof
            old = os.environ.get("CLAUDE_CONFIG_DIR")
            os.environ["CLAUDE_CONFIG_DIR"] = prof
            try:
                m = _load(name + "_a", path)
                self.assertTrue(hasattr(m, "claude_home"),
                                f"{path} 에 claude_home() 이 없다")
                self.assertEqual(m.claude_home(), prof, path)
            finally:
                if old is None:
                    os.environ.pop("CLAUDE_CONFIG_DIR", None)
                else:
                    os.environ["CLAUDE_CONFIG_DIR"] = old

    def test_b1_default_is_home_claude(self):
        old = os.environ.pop("CLAUDE_CONFIG_DIR", None)
        try:
            for name, path in (("s9_home", S9), ("s9inst_home", INSTALL)):
                m = _load(name + "_b", path)
                self.assertEqual(m.claude_home(),
                                 os.path.expanduser("~/.claude"), path)
        finally:
            if old is not None:
                os.environ["CLAUDE_CONFIG_DIR"] = old


class InstallIntoProfile(unittest.TestCase):
    """N2·N3 — 설치가 프로필로 간다. 실 HOME 은 건드리지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="s9profhome-")
        cls.prof = os.path.join(cls.home, ".claude-profiles", "second")
        os.makedirs(cls.prof, exist_ok=True)
        # S9_ROOT 은 실제 리포다 — s9-install 은 자기 위치에서 harness/ 를
        # 읽으므로 빈 디렉토리를 주면 설치할 원본이 없다. 격리하는 것은
        # HOME 과 CLAUDE_CONFIG_DIR 이고, 그 둘이면 실 계정은 안 건드린다.
        env = {**os.environ, "HOME": cls.home,
               "CLAUDE_CONFIG_DIR": cls.prof, "S9_MACHINE": "testbox"}
        env.pop("S9_SESSION", None)
        env.pop("S9_ROOT", None)
        cls.out = subprocess.run([INSTALL, "--quiet", "--no-remote-control"],
                                 capture_output=True, text=True, env=env,
                                 timeout=120)

    # N2. 훅이 프로필의 settings.json 에 들어간다
    def test_install_into_profile(self):
        """N2·N3 — 설치가 프로필로 간다. 실 HOME 은 건드리지 않는다."""
        with self.subTest("n2_hooks_land_in_profile"):
                sp = os.path.join(self.prof, "settings.json")
                self.assertTrue(os.path.exists(sp),
                                f"프로필에 settings.json 이 없다\n{self.out.stdout}"
                                f"{self.out.stderr}")
                with open(sp, encoding="utf-8") as f:
                    self.assertIn("s9-audit-prompt", f.read())

            # N2b. 실 HOME(~/.claude)에는 만들지 않는다 — 격리 HOME 안에서도 확인
        with self.subTest("n2b_real_home_untouched"):
                self.assertFalse(
                    os.path.exists(os.path.join(self.home, ".claude",
                                                "settings.json")),
                    "프로필로 설치했는데 ~/.claude 에도 썼다")

            # N3. 스킬·에이전트도 프로필로 — 없으면 designer 위임이 안 된다
        with self.subTest("n3_skills_agents_land_in_profile"):
            for d in ("skills", "agents"):
                p = os.path.join(self.prof, d)
                self.assertTrue(os.path.isdir(p), f"{p} 없음\n{self.out.stdout}")
                self.assertTrue(os.listdir(p), f"{p} 비어 있음")

class CodePreflightSeesProfile(unittest.TestCase):
    """B2 — `s9 code` 의 자가 치유가 프로필을 본다.

    실 HOME 쪽에는 설치된 것처럼 꾸며 두고, 프로필만 비운다. 예전에는
    `~/.claude` 를 보고 "설치돼 있다"로 넘어갔다 — 방어가 있는데 보는 곳이
    틀렸던 자리다. (설치를 실제로 돌리지 않고 판정 함수만 본다.)
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="s9pfhome-")
        self.root = tempfile.mkdtemp(prefix="s9pfroot-")
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        with open(os.path.join(self.home, ".claude", "settings.json"),
                  "w", encoding="utf-8") as f:
            f.write(json.dumps({"note": "s9-audit-prompt"}))
        self.prof = os.path.join(self.home, ".claude-profiles", "second")
        os.makedirs(self.prof, exist_ok=True)
        self._old = os.environ.get("CLAUDE_CONFIG_DIR")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._old

    def test_b2_empty_profile_reads_as_not_installed(self):
        os.environ["CLAUDE_CONFIG_DIR"] = self.prof
        m = _load("s9_hooked_a", S9)
        self.assertFalse(m.hooks_installed(root=self.root),
                         "빈 프로필인데 설치됐다고 본다")

    def test_b2b_hooked_profile_reads_as_installed(self):
        # 훅은 '적혀 있는가'가 아니라 '부를 수 있는가'로 본다 —
        # 실재하는 스크립트를 세워 둔다 (REQ-20260828-014).
        os.makedirs(os.path.join(self.root, "bin"), exist_ok=True)
        script = os.path.join(self.root, "bin", "s9-audit-prompt")
        with open(script, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        with open(os.path.join(self.prof, "settings.json"),
                  "w", encoding="utf-8") as f:
            f.write(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [
                {"type": "command",
                 "command": f"{script} 2>/dev/null || true"}]}]}}))
        os.environ["CLAUDE_CONFIG_DIR"] = self.prof
        m = _load("s9_hooked_b", S9)
        self.assertTrue(m.hooks_installed(root=self.root))


if __name__ == "__main__":
    unittest.main()
