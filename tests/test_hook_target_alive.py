"""죽은 훅 경로는 '설치됨'이 아니다 (REQ-20260828-014-62x6).

사용자 신고: "컴퓨터를 재시작하고 s9 code 를 실행하고 대시보드를 열어보면
대시보드 터미널은 세션이 꺼져있다 … 세션깨우기를 하면 새 터미널 창이 하나 더
열리는데 그럼에도 아직 no session 이다."

전역 `~/.claude/settings.json` 의 section9 훅 8개가 전부 사라진 worktree
경로(`<ROOT>/state/worktrees/probe/bin/…`)를 가리키고 있었다. 훅 명령은
`2>/dev/null || true` 라 없는 파일을 불러도 아무 소리를 내지 않는다 —
SessionStart 가 바인딩을 안 쓰고, 대시보드는 살아 있는 세션을 못 본다.
프롬프트 audit 도 같이 죽는다. **이 저장소가 가장 경계하는 조용한 실패다.**

자가 치유(`cmd_code` preflight)는 있었는데 눈이 문자열이었다:
`"s9-audit-prompt" in txt and ROOT in txt` — 죽은 worktree 경로가 ROOT 를
부분문자열로 품고 있어 "설치됨"으로 통과했다. 그래서 훅을 **경로로 열어 보게**
하고, 애초에 worktree 경로가 전역 설정에 적히지 않게 막는다.

실행: python3 tests/ hook_target_alive
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
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


def _settings(home, hooks):
    d = os.path.join(home, ".claude")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"hooks": hooks}, f)
    return d


def _hookblock(script):
    return {"SessionStart": [{"hooks": [
        {"type": "command",
         "command": f"{script} start 2>/dev/null || true"}]}],
            "UserPromptSubmit": [{"hooks": [
                {"type": "command",
                 "command": f"{os.path.dirname(script)}/s9-audit-prompt"
                            f" 2>/dev/null || true"}]}]}


class HookTargetAlive(unittest.TestCase):
    """N1·B1·B2 — 훅은 '적혀 있는가'가 아니라 '부를 수 있는가'로 본다."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="s9hthome-")
        self.root = tempfile.mkdtemp(prefix="s9htroot-")
        os.makedirs(os.path.join(self.root, "bin"))
        self._old = os.environ.get("CLAUDE_CONFIG_DIR")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._old
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.root, ignore_errors=True)

    def _use(self, hooks):
        os.environ["CLAUDE_CONFIG_DIR"] = _settings(self.home, hooks)

    def _make(self, *names):
        for n in names:
            p = os.path.join(self.root, "bin", n)
            with open(p, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(p, 0o755)

    def test_n1_live_target_is_installed(self):
        self._make("s9-audit-session", "s9-audit-prompt")
        self._use(_hookblock(os.path.join(self.root, "bin",
                                          "s9-audit-session")))
        m = _load("s9_hta_n1", S9)
        self.assertTrue(m.hooks_installed(root=self.root),
                        "실재하는 훅인데 미설치로 읽는다")

    def test_b1_dead_worktree_path_is_not_installed(self):
        """지워진 worktree 잔재 — 경로가 ROOT 를 부분문자열로 품는다."""
        self._make("s9-audit-session", "s9-audit-prompt")
        gone = os.path.join(self.root, "state", "worktrees", "probe", "bin",
                            "s9-audit-session")
        self.assertFalse(os.path.exists(gone))
        self._use(_hookblock(gone))
        m = _load("s9_hta_b1", S9)
        self.assertFalse(m.hooks_installed(root=self.root),
                         "없는 파일을 부르는 훅을 '설치됨'으로 읽는다 — "
                         "자가 치유가 영영 안 돈다")

    def test_b2_empty_settings_is_not_installed(self):
        self._use({})
        m = _load("s9_hta_b2", S9)
        self.assertFalse(m.hooks_installed(root=self.root))

    def test_b2b_other_workspace_is_not_installed(self):
        """살아 있어도 **남의 워크스페이스** 훅이면 이 ROOT 는 미설치다."""
        other = tempfile.mkdtemp(prefix="s9htother-")
        os.makedirs(os.path.join(other, "bin"))
        for n in ("s9-audit-session", "s9-audit-prompt"):
            with open(os.path.join(other, "bin", n), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
        try:
            self._use(_hookblock(os.path.join(other, "bin",
                                              "s9-audit-session")))
            m = _load("s9_hta_b2b", S9)
            self.assertFalse(m.hooks_installed(root=self.root))
        finally:
            shutil.rmtree(other, ignore_errors=True)


class InstallFromWorktree(unittest.TestCase):
    """B3 — 전역 설정에는 worktree가 아니라 메인 저장소 경로가 적힌다.

    전역 `settings.json` 은 worktree보다 오래 산다. worktree 경로를 적으면 그
    디렉토리가 지워진 순간 훅 전부가 조용한 no-op 이 된다 — 이번 사고의 원인.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9wt-")
        self.main = os.path.join(self.tmp, "main")
        os.makedirs(os.path.join(self.main, "bin"))
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        run = lambda *a: subprocess.run(a, cwd=self.main, env=env,
                                        capture_output=True)
        run("git", "init", "-q", "-b", "main")
        with open(os.path.join(self.main, "bin", "s9-audit-prompt"), "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        run("git", "add", "-A")
        run("git", "commit", "-qm", "init")
        self.wt = os.path.join(self.tmp, "wt")
        r = run("git", "worktree", "add", "-q", "--detach", self.wt)
        self.ok = r.returncode == 0 and os.path.isdir(self.wt)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_b3_worktree_resolves_to_main_root(self):
        if not self.ok:
            self.skipTest("git worktree 를 만들 수 없는 환경")
        m = _load("s9inst_wt", INSTALL)
        self.assertTrue(hasattr(m, "main_worktree_root"),
                        "s9-install 에 main_worktree_root() 가 없다")
        self.assertEqual(os.path.realpath(m.main_worktree_root(self.wt)),
                         os.path.realpath(self.main),
                         "worktree에서 실행한 설치가 worktree 경로를 심는다")

    def test_b3b_plain_dir_is_itself(self):
        m = _load("s9inst_plain", INSTALL)
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain, exist_ok=True)
        self.assertEqual(m.main_worktree_root(plain), plain)


if __name__ == "__main__":
    unittest.main()
