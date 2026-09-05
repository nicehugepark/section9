"""원격제어 기본값은 옵트인 (REQ-20260905-030).

s9-install 이 remoteControlAtStartup 을 기본으로 켜지 않는다. 켜는 길은 `--remote-control`
한 가지이고, 사용자가 이미 켜 둔 것은 건드리지 않는다.
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


class RemoteControlOptIn(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9rc-root-")
        self.home = tempfile.mkdtemp(prefix="s9rc-home-")
        self.keep = {k: os.environ.get(k) for k in ("CLAUDE_CONFIG_DIR", "S9_ROOT")}
        os.environ["CLAUDE_CONFIG_DIR"] = self.home
        os.environ["S9_ROOT"] = self.root
        os.makedirs(os.path.join(self.root, "harness", "claude"))
        shutil.copy(os.path.join(HERE, "..", "harness", "claude", "hooks.json"),
                    os.path.join(self.root, "harness", "claude", "hooks.json"))   # 훅 원본이 있어야 심는다
        spec = importlib.util.spec_from_loader("s9install_rc", importlib.machinery.SourceFileLoader("s9install_rc", INSTALL))
        self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        self.m.say = lambda *a, **k: None
        self.m.SET_BY_US.clear()
        self.argv = sys.argv

    def tearDown(self):
        sys.argv = self.argv
        for k, v in self.keep.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True); shutil.rmtree(self.home, ignore_errors=True)

    def _settings(self):
        try:
            return json.load(open(os.path.join(self.home, "settings.json")))
        except OSError:
            return {}

    def test_r1_default_install_does_not_turn_remote_control_on(self):
        """R1. 기본 설치는 remoteControlAtStartup 을 만들지 않는다 — 훅은 심는다."""
        sys.argv = ["s9-install"]
        self.m.install_claude_hooks()
        st = self._settings()
        self.assertNotIn("remoteControlAtStartup", st)
        self.assertTrue(st.get("hooks"), "훅은 여전히 심는다")
        self.assertNotIn("remoteControlAtStartup", self.m.SET_BY_US)

    def test_r2_flag_turns_it_on_and_remembers_it_was_us(self):
        """R2. --remote-control 이면 켜고, 우리가 켰다는 것을 기억한다(uninstall 이 되돌린다)."""
        sys.argv = ["s9-install", "--remote-control"]
        self.m.install_claude_hooks()
        self.assertTrue(self._settings().get("remoteControlAtStartup") is True)
        self.assertIn("remoteControlAtStartup", self.m.SET_BY_US)

    def test_r3_user_choice_is_kept_either_way(self):
        """R3. 사용자가 이미 켜 둔 값은 플래그가 없어도 그대로고, 우리가 켠 것으로 적지 않는다."""
        json.dump({"remoteControlAtStartup": True}, open(os.path.join(self.home, "settings.json"), "w"))
        sys.argv = ["s9-install"]
        self.m.install_claude_hooks()
        self.assertTrue(self._settings().get("remoteControlAtStartup") is True)
        self.assertNotIn("remoteControlAtStartup", self.m.SET_BY_US)
        self.assertFalse(self.m.remote_control_wanted([]))
        self.assertTrue(self.m.remote_control_wanted(["--remote-control"]))


if __name__ == "__main__":
    unittest.main()
