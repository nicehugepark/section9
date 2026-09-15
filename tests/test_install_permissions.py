"""설치가 깔아 주는 승인 목록 (REQ-20260915-006-2n7g).

하네스 밖의 승인 층이 `git stash drop` 을 막으면 무인 작업자는 동기화가 치워 둔
보관함을 비우지 못하고 사람을 부른다(2026-09-15 실제 사고, REQ-20260915-012-62x6).
그래서 설치가 그 몇 줄을 permissions.allow 에 깔고, uninstall 이 그것만 걷는다.
사용자가 적어 둔 규칙은 어느 쪽에서도 건드리지 않는다.

실행: python3 tests/ install_permissions
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
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


def load(root):
    old = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            "s9install_perm", importlib.machinery.SourceFileLoader("s9install_perm", INSTALL))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old


class InstallPermissions(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9perm-root-")
        self.home = tempfile.mkdtemp(prefix="s9perm-home-")
        self.keep = {k: os.environ.get(k) for k in ("CLAUDE_CONFIG_DIR", "HOME")}
        os.environ["CLAUDE_CONFIG_DIR"] = self.home
        os.environ["HOME"] = self.home
        subprocess.run(["git", "init", "-q", self.root], check=True)
        # 설치가 읽는 것 — 훅 정의 하나면 된다
        os.makedirs(os.path.join(self.root, "harness", "claude"))
        with open(os.path.join(self.root, "harness", "claude", "hooks.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"hooks": {"Stop": [{"matcher": "", "hooks": [
                {"type": "command", "command": "{ROOT}/bin/s9-audit"}]}]}}, f)
        self.m = load(self.root)
        self.m.say = lambda *a, **k: None
        self.m.PLACED.clear(); self.m.COLLIDED.clear()
        self.m.SET_BY_US.clear(); self.m.ALLOW_ADDED.clear()

    def tearDown(self):
        for k, v in self.keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for d in (self.root, self.home):
            shutil.rmtree(d, ignore_errors=True)

    @property
    def settings_path(self):
        return os.path.join(self.home, "settings.json")

    def read(self):
        with open(self.settings_path, encoding="utf-8") as f:
            return json.load(f)

    def write(self, data):
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_p1_install_lays_the_harness_rules(self):
        """정상: 빈 자리에 설치하면 하네스 규칙 셋이 permissions.allow 에 선다."""
        self.m.install_claude_hooks()
        allow = self.read()["permissions"]["allow"]
        for rule in self.m.HARNESS_ALLOW:
            self.assertIn(rule, allow, rule)

    def test_p2_the_users_own_rules_stay(self):
        """경계: 사용자가 적어 둔 규칙과 deny 칸은 그대로 있고 우리 규칙이 뒤에 붙는다."""
        self.write({"permissions": {"allow": ["Bash(npm test:*)"],
                                    "deny": ["Bash(rm -rf /:*)"]}})
        self.m.install_claude_hooks()
        perms = self.read()["permissions"]
        self.assertEqual(perms["allow"][0], "Bash(npm test:*)")
        self.assertEqual(perms["deny"], ["Bash(rm -rf /:*)"])
        self.assertIn("Bash(git stash drop:*)", perms["allow"])

    def test_p3_a_second_install_does_not_repeat_a_rule(self):
        """경계: 이미 다 들어 있으면 두 번째 설치가 같은 줄을 또 넣지 않는다."""
        self.m.install_claude_hooks()
        first = self.read()["permissions"]["allow"]
        self.m.ALLOW_ADDED.clear()
        self.m.install_claude_hooks()
        self.assertEqual(self.read()["permissions"]["allow"], first)
        self.assertEqual(self.m.ALLOW_ADDED, [])

    def test_p4_uninstall_takes_back_only_ours(self):
        """회귀: uninstall 은 설치가 넣은 규칙만 걷고 사용자의 것은 남긴다."""
        self.write({"permissions": {"allow": ["Bash(npm test:*)"]}})
        self.m.install_claude_hooks()
        self.m._write_placed(self.home)
        self.m.uninstall(home=self.home, root=self.root, bring_back=False, out=lambda *a: None)
        self.assertEqual(self.read()["permissions"]["allow"], ["Bash(npm test:*)"])

    def test_p5_uninstall_leaves_no_empty_slot(self):
        """회귀: 우리 것만 있던 자리는 통째로 걷힌다 — 빈 칸을 남기지 않는다."""
        self.m.install_claude_hooks()
        self.m._write_placed(self.home)
        self.m.uninstall(home=self.home, root=self.root, bring_back=False, out=lambda *a: None)
        self.assertNotIn("permissions", self.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
