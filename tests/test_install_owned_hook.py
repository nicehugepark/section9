"""설치자는 제가 심은 훅을 **어느 경로에서 설치됐든** 제 것으로 알아본다
(REQ-20260910-010-2n7g, 실제 사고 2026-09-10 22:41).

시험이 임시 저장소(/T/s9run-*/s9coderoot-*/bin/)에서 실 계정 프로필에 설치를
돌려 남긴 s9-git-gate 훅 5개가, 그 디렉토리가 지워진 뒤에도 settings.json 에
남았다. `owned_hook` 이 경로(`/section9/bin/`)와 `s9-audit` 이름만 보아서
그 다섯은 남의 훅으로 분류됐고, 재설치가 다섯 번 돌아도 걷히지 않았다 — 그
계정으로 뜬 세션은 도구를 부를 때마다 「PreToolUse:Bash hook error … No such
file」 을 사람 화면에 찍었다.
"""
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")
STALE = ("/private/var/folders/65/x/T/s9run-24646-5bwchszz/s9run-24655-06rainrr/"
         "s9coderoot-xe4inqm_/bin/s9-git-gate")


def _load():
    import importlib.util
    spec = importlib.util.spec_from_loader("s9install", None)
    m = importlib.util.module_from_spec(spec)
    m.__dict__["__file__"] = os.path.abspath(INSTALL)
    src = open(INSTALL, encoding="utf-8").read()
    exec(compile(src, INSTALL, "exec"), m.__dict__)
    return m


class InstallOwnedHook(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_o1_temp_root_gate_is_ours(self):
        """임시 저장소 경로의 s9-git-gate 도 이 하네스가 심은 것이다."""
        self.assertTrue(self.m.owned_hook(STALE))
        self.assertTrue(self.m.owned_hook(
            '"C:\\Users\\x\\s9\\bin\\s9-git-gate.cmd"'))
        self.assertTrue(self.m.owned_hook(
            "/tmp/wt/bin/s9-audit-prompt 2>/dev/null || true"))

    def test_o2_strangers_stay_strangers(self):
        """남의 훅은 여전히 남의 것 — 이름이 비슷해도 잡지 않는다."""
        # (`s9-audit` 이 든 명령은 예전 규칙이 이미 제 것으로 본다 — 여기서 다투지 않는다)
        for cmd in ("/usr/local/bin/git-gate", "echo s9-git-gatex",
                    "/opt/tools/gate-keeper", "npm run lint"):
            self.assertFalse(self.m.owned_hook(cmd), cmd)

    def test_o3_reinstall_sweeps_stale_gate_hooks(self):
        """재설치 한 번이 죽은 경로의 훅을 걷어내고 제 것 하나만 남긴다."""
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, ".claude"))
            sp = os.path.join(home, ".claude", "settings.json")
            stale = [{"matcher": "Bash", "hooks": [{"type": "command",
                      "command": STALE.replace("24646", str(i))}]}
                     for i in range(5)]
            foreign = {"matcher": "Bash", "hooks": [{"type": "command",
                       "command": "/usr/local/bin/someone-elses-hook"}]}
            json.dump({"hooks": {"PreToolUse": stale + [foreign]}},
                      open(sp, "w"))
            saved = {k: os.environ.get(k) for k in ("HOME", "CLAUDE_CONFIG_DIR")}
            try:
                os.environ["HOME"] = home
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
                self.m.QUIET = True
                self.m.install_claude_hooks()
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            got = json.load(open(sp))["hooks"]["PreToolUse"]
            cmds = [h["command"] for e in got for h in e["hooks"]]
            gates = [c for c in cmds if c.endswith("s9-git-gate")
                     or c.endswith('s9-git-gate.cmd"')]
            self.assertEqual(len(gates), 1, cmds)
            self.assertNotIn("s9run-", gates[0])
            self.assertIn("/usr/local/bin/someone-elses-hook", cmds)

    def test_o4_runner_strips_profile_dir_from_children(self):
        """러너는 자식 시험에 CLAUDE_CONFIG_DIR 을 물려주지 않는다 — 다섯 번의
        누수는 전부 계정 프로필로 뜬 세션의 백그라운드 전체 실행에서 났다."""
        src = open(os.path.join(HERE, "__main__.py"), encoding="utf-8").read()
        self.assertTrue('pop("CLAUDE_CONFIG_DIR"' in src,
                        "tests/__main__.py 가 자식 env 에서 CLAUDE_CONFIG_DIR 을 걷어내지 않는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
