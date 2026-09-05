"""uninstall 과 reset (REQ-20260905-027 · 028).

uninstall 은 설치가 놓은 것만 걷는다 — 사용자의 훅·스킬·글은 그대로, 저장소와
자격증명·백업은 손대지 않는다. reset 은 기계 상태(state/·index/)를 백업 뒤 비운다 —
문서(vault·users·projects)는 그대로이고 되돌리기가 된다.
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import portpool

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")
ENV = os.path.join(HERE, "..", "bin", "s9_env.py")
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(path, name, root):
    old = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, path))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old


class Uninstall(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9un-root-")
        self.home = tempfile.mkdtemp(prefix="s9un-home-")
        self.xdg = tempfile.mkdtemp(prefix="s9un-xdg-")
        self.keep = {k: os.environ.get(k) for k in ("CLAUDE_CONFIG_DIR", "XDG_STATE_HOME", "HOME")}
        os.environ["CLAUDE_CONFIG_DIR"] = self.home
        os.environ["XDG_STATE_HOME"] = self.xdg
        os.environ["HOME"] = self.home          # ~/.gemini 가 여기로
        subprocess.run(["git", "init", "-q", self.root], check=True)
        os.makedirs(os.path.join(self.root, "harness", "claude", "agents"))
        os.makedirs(os.path.join(self.root, "harness", "common"))
        open(os.path.join(self.root, "harness", "common", "PROTOCOL.md"), "w").write("규약\n")
        open(os.path.join(self.root, "harness", "claude", "agents", "designer.md"), "w").write(
            "---\nname: designer\ndescription: d\n---\n")
        # 사용자의 것 — 훅·에이전트·GEMINI.md 글
        mine_hook = {"matcher": "", "hooks": [{"type": "command", "command": "/home/me/my-hook.sh"}]}
        ours_hook = {"matcher": "", "hooks": [{"type": "command", "command": f"{self.root}/bin/s9-audit"}]}
        json.dump({"hooks": {"Stop": [mine_hook, ours_hook], "PreToolUse": [ours_hook]},
                   "remoteControlAtStartup": True, "theme": "dark"},
                  open(os.path.join(self.home, "settings.json"), "w"))
        os.makedirs(os.path.join(self.home, "agents"))
        open(os.path.join(self.home, "agents", "mine.md"), "w").write("---\nname: mine\n---\n")
        os.makedirs(os.path.join(self.home, ".gemini"))
        self.m = _load(INSTALL, "s9install_un", self.root)
        self.m.say = lambda *a, **k: None
        self.m.PLACED.clear(); self.m.COLLIDED.clear(); self.m.SET_BY_US.clear()
        # 설치가 놓는 것들
        self.m.link_into(os.path.join(self.root, "harness", "claude", "agents"),
                         os.path.join(self.home, "agents"), "agent(공용)")
        self.m.SET_BY_US.add("remoteControlAtStartup")
        self.m._write_placed(self.home)
        self.m.managed_block(os.path.join(self.home, ".gemini", "GEMINI.md"), "gemini")
        with open(os.path.join(self.home, ".gemini", "GEMINI.md"), "a") as f:
            f.write("\n내가 쓴 줄\n")
        self.m.install_git_hooks()
        os.makedirs(os.path.join(self.root, "state"))
        open(os.path.join(self.root, "state", "installed_at"), "w").write("2026-09-05\n")

    def tearDown(self):
        for k, v in self.keep.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        for d in (self.root, self.home, self.xdg):
            shutil.rmtree(d, ignore_errors=True)

    def test_u1_only_ours_leave_and_theirs_stay(self):
        """U1. 우리 훅·링크·블록·git 훅·표식은 걷히고 사용자의 훅·에이전트·글·키는 그대로다."""
        r = self.m.uninstall(home=self.home, root=self.root, bring_back=False, out=lambda *a: None)
        st = json.load(open(os.path.join(self.home, "settings.json")))
        cmds = [h["command"] for e in st.get("hooks", {}).get("Stop", []) for h in e["hooks"]]
        self.assertEqual(cmds, ["/home/me/my-hook.sh"])
        self.assertNotIn("PreToolUse", st.get("hooks", {}))
        self.assertNotIn("remoteControlAtStartup", st); self.assertEqual(st["theme"], "dark")
        self.assertTrue(os.path.exists(os.path.join(self.home, "agents", "mine.md")))
        self.assertFalse(os.path.lexists(os.path.join(self.home, "agents", "designer.md")))
        g = open(os.path.join(self.home, ".gemini", "GEMINI.md")).read()
        self.assertNotIn("section9:begin", g); self.assertIn("내가 쓴 줄", g)
        hooks = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=self.root,
                               capture_output=True, text=True).stdout.strip()
        self.assertFalse(os.path.exists(os.path.join(self.root, hooks, "pre-commit")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "state", "installed_at")))
        self.assertFalse(os.path.exists(self.m.placed_manifest_path(self.home)))
        self.assertTrue(os.path.exists(os.path.join(self.root, "harness", "common", "PROTOCOL.md")), "저장소는 그대로")
        kinds = {w for w, _ in r["removed"]}
        self.assertTrue({"hook", "settings-key", "agent", "block", "git-hook", "marker", "manifest"} <= kinds, kinds)

    def test_u2_dry_run_changes_nothing(self):
        """U2. --dry-run 은 무엇을 걷을지 말만 하고 바이트 하나 안 바꾼다."""
        before = {}
        for dp, _dn, fns in os.walk(self.home):
            for fn in fns:
                p = os.path.join(dp, fn)
                if not os.path.islink(p):
                    before[p] = open(p, "rb").read()
        said = []
        r = self.m.uninstall(home=self.home, root=self.root, bring_back=False, dry_run=True, out=said.append)
        self.assertTrue(r["removed"]); self.assertTrue(any("(예정)" in s for s in said))
        for p, b in before.items():
            self.assertEqual(open(p, "rb").read(), b, p)
        self.assertTrue(os.path.lexists(os.path.join(self.home, "agents", "designer.md")))

    def test_u3_brings_the_install_backup_back(self):
        """U3. 설치 전 백업이 있으면 되돌린다 — 지금 자리의 다른 내용은 .s9-conflict 로 비켜 선다."""
        env = _load(ENV, "s9env_un", self.root)
        # 설치 전 모습: settings.json 이 달랐다
        open(os.path.join(self.home, "CLAUDE.md"), "w").write("옛 규칙\n")
        env.backup(home=self.home)
        open(os.path.join(self.home, "CLAUDE.md"), "w").write("설치 뒤 바뀐 규칙\n")
        self.m.uninstall(home=self.home, root=self.root, bring_back=True, out=lambda *a: None)
        self.assertEqual(open(os.path.join(self.home, "CLAUDE.md")).read(), "옛 규칙\n")
        aside = [n for n in os.listdir(self.home) if n.startswith("CLAUDE.md.s9-conflict-")]
        self.assertEqual(len(aside), 1, "바뀐 것은 잃지 않고 옆으로")


def _listen_published(timeout=3.0):
    """127.0.0.1 에 리스너를 세우고 **연결이 실제로 되는 때까지** 기다린 뒤 (socket, port) 를 준다.
    WSL 의 윈도우 중계(DOC-20260903-001)는 새 리스너를 몇십 ms 뒤에 공개한다 — 바로 두드리면
    ECONNREFUSED 다. 그것은 「없다」가 아니라 「아직」이다."""
    import socket, threading, time
    srv = portpool.pool_socket()          # 풀에서 — 임시 포트 bind 는 윈도우 동적 포트를 먹는다
    port = srv.getsockname()[1]

    def _drain():
        # 받아서 곧 닫는다. 아무도 accept 하지 않으면 리눅스는 backlog 가 찬 뒤의
        # SYN 을 버려 connect 가 타임아웃되고, 판정이 「닫힘(free)」으로 떨어진다
        # (jade 실측 2026-09-06: silent → mine 사이에서 free). WSL 은 중계가 대신
        # 받아 주어 이 결함이 보이지 않았다.
        while True:
            try:
                c, _ = srv.accept()
                c.close()
            except OSError:
                return
    threading.Thread(target=_drain, daemon=True).start()
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close()
            return srv, port
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"리스너 :{port} 가 {timeout}초 안에 공개되지 않았다")


def _closed_port():
    """지금 아무도 안 듣는 포트 하나 — 두드려서 거절되는 것을 확인한 뒤 준다.
    「방금 닫은 포트」는 WSL 중계가 한동안 계속 공개해 둔다(DOC-20260903-001) — 닫았다고 닫힌 게 아니다."""
    import socket
    port = 31999                          # 대역 표의 더미 — 아무도 bind 하지 않는다 (bin/s9-doctor)
    try:
        socket.create_connection(("127.0.0.1", port), 0.3).close()
    except OSError:
        return port
    raise AssertionError(f"더미 포트 {port} 가 열려 있다 — 대역 표(bin/s9-doctor)를 어긴 것이 있다")


class Reset(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9rs-root-")
        self.xdg = tempfile.mkdtemp(prefix="s9rs-xdg-")
        self.keep = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = self.xdg
        for d in ("state/sessions", "index/by-user", "vault/requests", "users/me"):
            os.makedirs(os.path.join(self.root, d))
        self.port = _closed_port()
        open(os.path.join(self.root, "state", "port"), "w").write(f"{self.port}\n")
        open(os.path.join(self.root, "state", "sessions", "s.json"), "w").write("{}")
        open(os.path.join(self.root, "index", "catalog.jsonl"), "w").write('{"id":"x"}\n')
        open(os.path.join(self.root, "vault", "requests", "REQ-1.md"), "w").write("문서\n")
        open(os.path.join(self.root, "users", "me", "profile.md"), "w").write("나\n")
        self.env = _load(ENV, "s9env_rs", self.root)

    def tearDown(self):
        if self.keep is None: os.environ.pop("XDG_STATE_HOME", None)
        else: os.environ["XDG_STATE_HOME"] = self.keep
        shutil.rmtree(self.root, ignore_errors=True); shutil.rmtree(self.xdg, ignore_errors=True)

    def test_s1_backup_then_clear_leaves_documents_alone(self):
        """S1. 백업이 state/·index/ 를 통째로 담고, 비운 뒤 두 디렉토리는 남되 비어 있으며 vault·users 는 그대로다."""
        b = self.env.reset_backup(self.root)
        self.assertTrue(os.path.isfile(os.path.join(b, "state", "sessions", "s.json")))
        self.assertTrue(os.path.isfile(os.path.join(b, "index", "catalog.jsonl")))
        self.assertTrue(b.startswith(os.path.join(self.xdg, "section9", "reset")))
        gone = self.env.reset_clear(self.root)
        self.assertTrue(gone)
        self.assertEqual(os.listdir(os.path.join(self.root, "state")), [])
        self.assertEqual(os.listdir(os.path.join(self.root, "index")), [])
        self.assertEqual(open(os.path.join(self.root, "vault", "requests", "REQ-1.md")).read(), "문서\n")
        self.assertEqual(open(os.path.join(self.root, "users", "me", "profile.md")).read(), "나\n")
        self.assertEqual(self.env.reset_backups(self.root), [os.path.basename(b)])

    def test_s2_restore_brings_the_state_back(self):
        """S2. 되돌리기는 그 백업의 state/·index/ 를 그대로 올리고, 되돌리기 직전 상태도 남긴다."""
        b = self.env.reset_backup(self.root)
        self.env.reset_clear(self.root)
        open(os.path.join(self.root, "state", "new.txt"), "w").write("비운 뒤 생긴 것\n")
        r = self.env.reset_restore(self.root, os.path.basename(b))
        self.assertEqual(open(os.path.join(self.root, "state", "port")).read(), f"{self.port}\n")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "index", "catalog.jsonl")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "state", "new.txt")))
        self.assertTrue(r["pre"] and os.path.isfile(os.path.join(r["pre"], "state", "new.txt")), "직전 상태도 백업")

    def test_s3_cli_refuses_without_tty_or_yes_and_dry_run_is_free(self):
        """S3. 터미널이 아니면 --yes 없이는 비우지 않는다; --dry-run 은 목록만; --yes 면 백업 뒤 비운다."""
        env = {**os.environ, "S9_ROOT": self.root}   # state/port 는 닫힌 포트 — 대시보드가 없다
        r = subprocess.run([sys.executable, S9, "reset"], capture_output=True, text=True, env=env,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertNotEqual(r.returncode, 0); self.assertIn("--yes", r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "state", "port")))
        r = subprocess.run([sys.executable, S9, "reset", "--dry-run"], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("(예정)", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "state", "port")))
        r = subprocess.run([sys.executable, S9, "reset", "--yes"], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("s9 reset --restore", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.root, "state", "sessions", "s.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "vault", "requests", "REQ-1.md")))
        self.assertEqual(len(self.env.reset_backups(self.root)), 1)

    def test_s4_an_open_but_silent_port_stops_the_reset(self):
        """S4. 포트가 열려 있는데 답이 없으면 「없다」가 아니라 「모른다」— 비우지 않는다. 닫혀 있어야 free 다."""
        s9 = _load(S9 + ".py", "s9_reset_t", self.root)
        srv, port = _listen_published()
        open(os.path.join(self.root, "state", "port"), "w").write(f"{port}\n")
        try:
            p, v, _ = s9.dashboard_alive_here(self.root, info_at=lambda _p: None)
            self.assertEqual((p, v), (port, "silent"))
            p, v, _ = s9.dashboard_alive_here(self.root, info_at=lambda _p: {"root": self.root})
            self.assertEqual(v, "mine")
            p, v, _ = s9.dashboard_alive_here(self.root, info_at=lambda _p: {"root": "/elsewhere"})
            self.assertEqual(v, "other")
        finally:
            srv.close()
        open(os.path.join(self.root, "state", "port"), "w").write(f"{_closed_port()}\n")
        p, v, _ = s9.dashboard_alive_here(self.root, info_at=lambda _p: {"root": self.root})
        self.assertEqual(v, "free", "닫힌 포트만 free 다")
        # 실제 명령: silent 면 --yes 를 줘도 비우지 않는다
        srv, port = _listen_published()
        open(os.path.join(self.root, "state", "port"), "w").write(f"{port}\n")
        try:
            env = {**os.environ, "S9_ROOT": self.root}
            r = subprocess.run([sys.executable, S9, "reset", "--yes"], capture_output=True, text=True,
                               env=env, stdin=subprocess.DEVNULL, timeout=60)
            self.assertNotEqual(r.returncode, 0); self.assertIn("답이 없다", r.stdout + r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(self.root, "state", "sessions", "s.json")))
        finally:
            srv.close()


if __name__ == "__main__":
    unittest.main()
