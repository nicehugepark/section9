"""압축을 풀어 처음 실행한 자리 — `s9 code` 한 번으로 혼자 쓰는 상태가 서는가 (REQ-20260913-007).

사람은 GitHub 릴리스의 tar.gz/zip 을 받아 풀고 `bin/s9 code` 만 친다. 그 자리에는
`.git` 도 `state/` 도 없다. 이 시험은 그 자리를 그대로 만든다: working tree 를
배포판 모양(.gitattributes 의 export-ignore 적용 · .git 없음)으로 임시 디렉토리에
복사하고, HOME 과 CLAUDE_CONFIG_DIR 을 임시로 돌린 채 시험 포트로 **그 자리의**
`bin/s9 code --no-open` 을 실행한다. S9_CODE_DRYRUN=1 이라 claude 를 띄우기 직전에
멈춘다 — `--no-claude` 는 preflight(설치·신원) 앞에서 돌아가므로 사람의 흐름을
끝까지 지나는 것은 DRYRUN 쪽이다.

`git archive HEAD` 를 풀지 않는 까닭: HEAD 는 commit 전의 새 코드를 모른다 — commit
검사가 이 시험을 돌릴 때도 HEAD 는 옛 코드다. 그래서 `git archive --worktree-attributes`
와 같은 규칙(export-ignore)을 working tree 에 적용한다(release_shape).

실서버는 클래스당 하나(시험 포트), 끝나면 `serve --stop` 으로 내리고 남은 것은 pid 로 거둔다.

실행: python3 tests/ firstrun
"""
import getpass
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from portpool import free_port, wait_server, _proc_snapshot  # noqa: E402
from unpacked import load as _load, git as _git, rmtree as _rmtree  # noqa: E402
from unpacked import release_shape, clean_env as _clean_env  # noqa: E402

FIRSTRUN = os.path.join(ROOT, "bin", "s9_firstrun.py")
SUBJECT = "section9 첫 실행"


class FirstRun(unittest.TestCase):
    """압축을 푼 자리에서 `s9 code` 한 번 — 실서버 하나, 클래스당 한 번."""

    @classmethod
    def setUpClass(cls):
        cls.fr = _load("s9_firstrun_under_test", FIRSTRUN)
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix="s9firstrun-"))
        cls.root = os.path.join(cls.base, "section9-0.9.0")
        os.makedirs(cls.root)
        cls.copied = release_shape(cls.root)
        cls.home = os.path.join(cls.base, "home")
        cls.cfg = os.path.join(cls.home, ".claude")
        os.makedirs(cls.cfg)
        cls.port = free_port()
        cls.env = _clean_env()
        cls.env.update({"HOME": cls.home, "CLAUDE_CONFIG_DIR": cls.cfg,
                        "S9_PORT": str(cls.port), "S9_CODE_DRYRUN": "1",
                        "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off"})
        cls.s9 = os.path.join(cls.root, "bin", "s9")
        cls._mod = None
        cls.first = cls.code()

    @classmethod
    def code(cls):
        return subprocess.run([sys.executable, cls.s9, "code", "--no-open"],
                              capture_output=True, encoding="utf-8", errors="replace",
                              env=cls.env, cwd=cls.root, stdin=subprocess.DEVNULL,
                              timeout=240)

    @classmethod
    def _serve_procs(cls):
        """이 시험의 임시 자리에서 뜬 serve 프로세스 — 감시자와 서버 둘 다."""
        return [p for p in _proc_snapshot()
                if "serve" in p["argv"] and any(cls.base in a for a in p["argv"])]

    @classmethod
    def tearDownClass(cls):
        subprocess.run([sys.executable, cls.s9, "serve", "--stop", "--port", str(cls.port)],
                       capture_output=True, env=cls.env, cwd=cls.root,
                       stdin=subprocess.DEVNULL, timeout=90)
        deadline = time.monotonic() + 10
        while cls._serve_procs() and time.monotonic() < deadline:
            time.sleep(0.5)
        left = sorted(cls._serve_procs(), key=lambda p: 0 if "--supervise" in p["argv"] else 1)
        for p in left:                       # 감시자 먼저 — 자식만 죽이면 되살린다
            try:
                os.kill(p["pid"], signal.SIGKILL)
            except OSError:
                pass
        if left:
            time.sleep(1.0)
        _rmtree(cls.base)

    @classmethod
    def s9mod(cls):
        """그 자리의 s9 본체를 모듈로 — ROOT 는 import 때 잡히므로 S9_ROOT 를 잠깐 돌린다."""
        if cls._mod is None:
            with mock.patch.dict(os.environ, {"S9_ROOT": cls.root}):
                cls._mod = _load("s9_unpacked_body", cls.s9)
        return cls._mod

    def test_n1_repo_stands_on_main_with_one_commit(self):
        """N1. 첫 `s9 code`: exit 0 · 「새로 세웠다」 한 줄 · .git · main · commit 하나 · 임시 신원."""
        r = self.first
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("저장소를 새로 세웠다", r.stdout)
        self.assertIn('["claude"', r.stdout, "claude 를 띄우는 자리까지 가지 못했다")
        self.assertTrue(os.path.isdir(os.path.join(self.root, ".git")))
        self.assertEqual(_git(self.root, "symbolic-ref", "--short", "HEAD").stdout.strip(), "main")
        self.assertEqual(_git(self.root, "log", "--format=%s").stdout.strip().splitlines(), [SUBJECT])
        # HOME 이 비어 있으니 신원은 저장소 로컬의 임시 신원이다 (시스템 설정에 있으면 그것을 쓴다)
        sysname = _git(self.root, "config", "--system", "user.name", env=self.env).stdout.strip()
        local = _git(self.root, "config", "--local", "user.name").stdout.strip()
        if not sysname:
            self.assertEqual(local, self.fr.temp_identity(getpass.getuser())[0])
            self.assertEqual(_git(self.root, "config", "--local", "user.email").stdout.strip(),
                             self.fr.temp_identity(getpass.getuser())[1])

    def test_n2_sync_marker_is_local_and_unchosen(self):
        """N2. `.s9-sync` 는 local + 아직 고르지 않음 — 그 자리의 sync_mode() 가 "local" 을 낸다."""
        with open(os.path.join(self.root, ".s9-sync"), encoding="utf-8") as f:
            body = f.read()
        self.assertEqual(body.split()[0], "local", body)
        self.assertIn("아직 고르지 않음", body)
        mod = self.s9mod()
        with mock.patch.dict(os.environ):
            os.environ.pop("S9_SYNC", None)
            self.assertEqual(mod.sync_mode(), "local")
            self.assertFalse(mod.sync_mode_chosen())

    def test_n3_gitignore_is_the_instance_one_and_the_commit_holds_the_code(self):
        """N3. .gitignore 는 INSTANCE_TRACK_GITIGNORE 그대로; 첫 commit 에 코드·표식은 담기고 state/·index/ 는 없다."""
        mod = self.s9mod()
        with open(os.path.join(self.root, ".gitignore"), encoding="utf-8") as f:
            self.assertEqual(f.read(), mod.INSTANCE_TRACK_GITIGNORE)
        tracked = set(_git(self.root, "ls-tree", "-r", "--name-only", "HEAD").stdout.split("\n"))
        for p in (".gitignore", ".s9-sync", "bin/s9.py", "bin/s9_firstrun.py", "bin/s9-install"):
            self.assertIn(p, tracked, p)
        stray = sorted(p for p in tracked if p.startswith(("state/", "index/", ".claude/")))
        self.assertEqual(stray, [], "이 컴퓨터의 살림이 첫 commit 에 담겼다")

    def test_n4_install_ran_after_the_repo_stood(self):
        """N4. 설치가 저장소 뒤에 돌았다 — claude 훅은 임시 CLAUDE_CONFIG_DIR 에, git 훅은 .git/hooks 에."""
        self.assertIn("훅 미설치", self.first.stdout)
        with open(os.path.join(self.cfg, "settings.json"), encoding="utf-8") as f:
            settings = json.load(f)
        cmds = [h.get("command", "") for entries in (settings.get("hooks") or {}).values()
                for e in entries for h in (e or {}).get("hooks", [])]
        mine = os.path.join(self.root, "bin", "s9-audit-")
        self.assertTrue(any(mine in c for c in cmds), cmds)
        for name in ("pre-commit", "post-commit"):
            self.assertTrue(os.path.isfile(os.path.join(self.root, ".git", "hooks", name)),
                            f"{name} 이 .git/hooks 에 없다 — 설치가 저장소보다 먼저 돌았다")

    def test_n5_dashboard_answers_from_this_root(self):
        """N5. 대시보드가 시험 포트에서 답하고, 그 root 는 압축을 푼 자리다."""
        self.assertIn("대시보드", self.first.stdout)
        wait_server(self.port)
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/serveinfo", timeout=5) as r:
            info = json.loads(r.read().decode("utf-8", "replace"))
        self.assertEqual(os.path.realpath(str(info.get("root") or "")), self.root, info)

    def test_i1_second_run_changes_nothing(self):
        """I1. 두 번째 `s9 code`: exit 0, 「새로 세웠다」 없음, 설치 다시 없음, 첫 실행 commit 은 하나."""
        r = self.code()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("저장소를 새로 세웠다", r.stdout)
        self.assertNotIn("훅 미설치", r.stdout)
        subjects = _git(self.root, "log", "--format=%s").stdout.strip().splitlines()
        self.assertEqual(subjects.count(SUBJECT), 1, subjects)
        res = self.fr.ensure_repo(self.root, "x", "y", env=self.env)
        self.assertEqual((res["created"], res["skipped"], res["did"]), (False, "repo", []), res)

    def test_e1_install_first_gives_the_same_shape(self):
        """E1. 사람이 `bin/s9-install` 을 먼저 쳐도 같은 결과 — 저장소·main·첫 commit·local·git 훅."""
        root2 = os.path.join(self.base, "install-first")
        os.makedirs(root2)
        release_shape(root2)
        r = subprocess.run([sys.executable, os.path.join(root2, "bin", "s9-install"),
                            "--quiet", "--no-claude"],
                           capture_output=True, encoding="utf-8", errors="replace",
                           env=self.env, cwd=root2, stdin=subprocess.DEVNULL, timeout=240)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(_git(root2, "symbolic-ref", "--short", "HEAD").stdout.strip(), "main")
        self.assertEqual(_git(root2, "log", "--format=%s").stdout.strip().splitlines(), [SUBJECT])
        with open(os.path.join(root2, ".s9-sync"), encoding="utf-8") as f:
            self.assertEqual(f.read().split()[0], "local")
        self.assertTrue(os.path.isfile(os.path.join(root2, ".git", "hooks", "pre-commit")),
                        "git 훅이 없다 — 설치가 저장소를 세우기 전에 훅 자리를 물었다")
        res = self.fr.ensure_repo(root2, "x", "y", env=self.env)
        self.assertEqual((res["created"], res["skipped"]), (False, "repo"), res)

    def test_u1_data_only_root_is_left_alone(self):
        """U1. 코드가 없는 자리(시험의 데이터 전용 S9_ROOT)에는 저장소를 세우지 않는다."""
        d = os.path.join(self.base, "data-only")
        os.makedirs(os.path.join(d, "vault"))
        res = self.fr.ensure_repo(d, "x", "y", env=self.env)
        self.assertEqual((res["created"], res["skipped"]), (False, "no-code"), res)
        self.assertFalse(os.path.exists(os.path.join(d, ".git")))

    def test_u2_existing_identity_is_kept(self):
        """U2. git 신원이 이미 있으면(전역 .gitconfig) 저장소 로컬 임시 신원을 쓰지 않는다."""
        d = os.path.join(self.base, "with-identity")
        os.makedirs(os.path.join(d, "bin"))
        with open(os.path.join(d, "bin", "s9.py"), "w", encoding="utf-8") as f:
            f.write("# stub\n")
        home2 = os.path.join(self.base, "home-with-identity")
        os.makedirs(home2)
        with open(os.path.join(home2, ".gitconfig"), "w", encoding="utf-8") as f:
            f.write("[user]\n\tname = Someone\n\temail = someone@example.org\n")
        env = {**self.env, "HOME": home2}
        res = self.fr.ensure_repo(d, "*.log\n", "local\n", env=env)
        self.assertTrue(res["created"], res)
        self.assertNotIn("identity", res["did"], res)
        self.assertEqual(_git(d, "config", "--local", "user.name").stdout.strip(), "")
        self.assertEqual(_git(d, "log", "-1", "--format=%an", env=env).stdout.strip(), "Someone")

    def test_f1_without_git_it_reports_and_creates_nothing(self):
        """F1. git 실행 파일이 없으면 예외 없이 error 를 돌려주고 .git 을 만들지 않는다."""
        d = os.path.join(self.base, "no-git")
        os.makedirs(os.path.join(d, "bin"))
        with open(os.path.join(d, "bin", "s9.py"), "w", encoding="utf-8") as f:
            f.write("# stub\n")
        res = self.fr.ensure_repo(d, "x", "y", env=self.env,
                                  git=os.path.join(self.base, "no-such-git"))
        self.assertFalse(res["created"], res)
        self.assertTrue(res["error"], res)
        self.assertFalse(os.path.exists(os.path.join(d, ".git")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
