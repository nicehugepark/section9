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

    def test_n5_the_onboarding_guides_stand_before_anyone_is_registered(self):
        """N5. 첫 `s9 code` 는 이름을 묻기 전에 사용법 안내 요청을 general 에 open 으로 심고, 첫 commit 에
        함께 담는다 (REQ-20260914-011-62x6) — 배포판의 harness/common/onboarding/*.md 한 편이 요청 하나."""
        mod = self.s9mod()
        files = mod.onboarding_files()
        rows = [r for r in mod.load_catalog()
                if r.get("type") == "request" and "onboarding" in (r.get("tags") or [])]
        self.assertEqual(len(rows), len(files), [r["title"] for r in rows])
        self.assertGreaterEqual(len(files), 1, "배포판에 안내 파일이 없다")
        self.assertIn(f"사용법 안내 요청 {len(files)}건이 Board 의 open 열에 섰다", self.first.stdout)
        for r in rows:
            self.assertEqual(r["status"], "open", r["title"])
            self.assertEqual(r["project"], mod.DEFAULT_PROJECT_SLUG, r["title"])
            self.assertEqual(r["user"], getpass.getuser(), r["title"])
        self.assertEqual(mod.onboarding_state().get("reason"), "seeded")
        tracked = set(_git(self.root, "ls-tree", "-r", "--name-only", "HEAD").stdout.split("\n"))
        for r in rows:
            rel = os.path.relpath(mod.find_path(r["id"]), self.root).replace(os.sep, "/")
            self.assertIn(rel, tracked, "안내가 첫 commit 에 담기지 않았다")

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


class ClonedPlace(unittest.TestCase):
    """git clone 으로 온 자리의 git 신원 (REQ-20260921-003-62x6).

    실측 2026-09-21: 임시 신원을 박는 자리는 ensure_repo(저장소를 새로 세울 때)와
    join_repo(초대로 합류할 때) 둘뿐이었다. clone 으로 온 자리는 `.git` 이 이미 있어
    ensure_repo 가 skipped=repo 로 빠지고 `--join` 도 아니라 어느 갈래도 타지 않는다 —
    user.name 을 정해 두지 않은 컴퓨터에서 문서 commit 이 통째로 거부되고 `s9 doctor`
    가 「git 이름」을 ✗ 로 짚었다.

    이 시험의 컴퓨터에는 git 신원이 없다: HOME 을 빈 임시 자리로 돌리고
    GIT_CONFIG_NOSYSTEM 으로 시스템 설정도 끊는다 — 그래야 실제 결함의 자리가 된다.
    """

    @classmethod
    def setUpClass(cls):
        cls.fr = _load("s9_firstrun_clone", FIRSTRUN)
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix="s9clone-"))
        cls.home = os.path.join(cls.base, "home")
        os.makedirs(cls.home)
        cls.env = _clean_env()
        cls.env.update({"HOME": cls.home, "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": os.path.join(cls.home, ".gitconfig")})
        # 클론의 원본 — 배포판 모양에 저장소를 세운 자리(ensure_repo 갈래는 그대로다)
        cls.src = os.path.join(cls.base, "section9-0.9.0")
        os.makedirs(cls.src)
        release_shape(cls.src)
        res = cls.fr.ensure_repo(cls.src, "state/\nindex/\n.claude/\n",
                                 "local\n", env=cls.env)
        assert res["created"], res
        cls.port = free_port()
        cls.ran = None                       # N3 이 `s9 code` 를 돌린 자리

    @classmethod
    def tearDownClass(cls):
        if cls.ran:
            subprocess.run([sys.executable, os.path.join(cls.ran, "bin", "s9"),
                            "serve", "--stop", "--port", str(cls.port)],
                           capture_output=True, env=cls.env, cwd=cls.ran,
                           stdin=subprocess.DEVNULL, timeout=90)
            deadline = time.monotonic() + 10
            while cls._serve_procs() and time.monotonic() < deadline:
                time.sleep(0.5)
            left = sorted(cls._serve_procs(),
                          key=lambda p: 0 if "--supervise" in p["argv"] else 1)
            for p in left:                   # 감시자 먼저 — 자식만 죽이면 되살린다
                try:
                    os.kill(p["pid"], signal.SIGKILL)
                except OSError:
                    pass
            if left:
                time.sleep(1.0)
        _rmtree(cls.base)

    @classmethod
    def _serve_procs(cls):
        return [p for p in _proc_snapshot()
                if "serve" in p["argv"] and any(cls.base in a for a in p["argv"])]

    @classmethod
    def clone(cls, name):
        """원본을 clone 한 자리 — `.git` 은 있고 로컬 신원은 없다(clone 은 설정을 옮기지 않는다)."""
        dst = os.path.join(cls.base, name)
        r = subprocess.run(["git", "clone", "--quiet", cls.src, dst], capture_output=True,
                           encoding="utf-8", errors="replace", env=cls.env, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        return dst

    def test_n1_a_clone_gets_a_local_identity(self):
        """N1. clone 한 자리에 ensure_identity 를 부르면 저장소 로컬에 임시 신원이 선다."""
        d = self.clone("clone-n1")
        self.assertEqual(_git(d, "config", "--local", "user.name", env=self.env).stdout.strip(),
                         "", "clone 한 자리에 이미 신원이 있다 — 이 시험의 전제가 깨졌다")
        res = self.fr.ensure_identity(d, env=self.env)
        self.assertEqual((res["set"], res["scope"], res["error"]), (True, "local", ""), res)
        want = self.fr.temp_identity(getpass.getuser())
        got = (_git(d, "config", "--local", "user.name", env=self.env).stdout.strip(),
               _git(d, "config", "--local", "user.email", env=self.env).stdout.strip())
        self.assertEqual(got, want)
        again = self.fr.ensure_identity(d, env=self.env)
        self.assertEqual((again["set"], again["scope"]), (False, "local"), again)

    def test_n2_a_commit_stands_with_that_identity(self):
        """N2. 그 자리에서 문서 commit 이 선다 — 신원 부재로 거부되지 않는다."""
        d = self.clone("clone-n2")
        self.fr.ensure_identity(d, env=self.env)
        with open(os.path.join(d, "note.md"), "w", encoding="utf-8") as f:
            f.write("문서 하나\n")
        self.assertEqual(_git(d, "add", "note.md", env=self.env).returncode, 0)
        r = _git(d, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "문서 하나",
                 env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(_git(d, "log", "-1", "--format=%an", env=self.env).stdout.strip(),
                         self.fr.temp_identity(getpass.getuser())[0])

    def test_n3_s9_code_in_a_clone_stands_the_identity(self):
        """N3. clone 한 자리에서 `s9 code` 한 번 — 로컬 신원이 서고 doctor 의 「git 이름」이 ✗ 가 아니다."""
        d = self.clone("clone-n3")
        type(self).ran = d
        cfg = os.path.join(self.base, "claude-n3")
        os.makedirs(cfg)
        env = {**self.env, "CLAUDE_CONFIG_DIR": cfg, "S9_PORT": str(self.port),
               "S9_CODE_DRYRUN": "1", "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off"}
        r = subprocess.run([sys.executable, os.path.join(d, "bin", "s9"), "code", "--no-open"],
                           capture_output=True, encoding="utf-8", errors="replace",
                           env=env, cwd=d, stdin=subprocess.DEVNULL, timeout=240)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("저장소를 새로 세웠다", r.stdout, "clone 한 자리에 저장소를 또 세웠다")
        want = self.fr.temp_identity(getpass.getuser())
        self.assertEqual(_git(d, "config", "--local", "user.name", env=env).stdout.strip(),
                         want[0], "`s9 code` 가 clone 한 자리의 신원을 세우지 않았다")
        self.assertIn("git 이름을 임시로", r.stdout, "무엇을 했는지 화면에서 말하지 않았다")
        doctor = _load("s9doctor_for_clone", os.path.join(ROOT, "bin", "s9-doctor"))
        with mock.patch.dict(os.environ, {k: env[k] for k in
                                          ("HOME", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL")}):
            verdict = doctor.ident_verdict(doctor.ident_info(d))
        self.assertNotEqual(verdict["level"], "critical", verdict)

    def test_n4_s9_code_uses_the_profile_mail_when_there_is_one(self):
        """N4. 그 자리에 그 사람의 프로필이 있으면 `s9 code` 는 임시값이 아니라 프로필 메일을 세운다.

        clone 으로 온 자리에는 users/ 가 함께 온다 — 그 사람이 이미 정해 둔 주소가 거기
        있는데도 기계가 지어낸 `<계정>@local` 을 박으면, 이 컴퓨터에서 쌓이는 commit 이
        그 사람의 GitHub 계정에 이어지지 않는다 (REQ-20260921-011-62x6).
        """
        d = self.clone("clone-n4")
        acct = getpass.getuser()
        prof = os.path.join(d, "users", "hong")
        os.makedirs(prof, exist_ok=True)
        with open(os.path.join(prof, "profile.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: hong\nrole: admin\n"
                    'emails: ["hong@corp.co.kr"]\ngithub: hong-gildong\n'
                    f'os_accounts: ["{acct}"]\n---\n\n## Notes\n')
        port = free_port()
        cfg = os.path.join(self.base, "claude-n4")
        os.makedirs(cfg)
        env = {**self.env, "CLAUDE_CONFIG_DIR": cfg, "S9_PORT": str(port),
               "S9_CODE_DRYRUN": "1", "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off"}
        r = subprocess.run([sys.executable, os.path.join(d, "bin", "s9"), "code", "--no-open"],
                           capture_output=True, encoding="utf-8", errors="replace",
                           env=env, cwd=d, stdin=subprocess.DEVNULL, timeout=240)
        try:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(
                (_git(d, "config", "--local", "user.name", env=env).stdout.strip(),
                 _git(d, "config", "--local", "user.email", env=env).stdout.strip()),
                ("hong-gildong", "hong@corp.co.kr"),
                "프로필에 메일이 있는데 그 주소를 세우지 않았다")
            self.assertNotIn("임시로", r.stdout, "프로필 메일을 두고 임시값이라고 말했다")
            self.assertIn("프로필에 적어 둔 메일이다", r.stdout,
                          "어느 칸의 값인지 화면에서 말하지 않았다")
        finally:
            subprocess.run([sys.executable, os.path.join(d, "bin", "s9"),
                            "serve", "--stop", "--port", str(port)],
                           capture_output=True, env=env, cwd=d,
                           stdin=subprocess.DEVNULL, timeout=90)

    def test_b1_a_global_identity_is_left_alone(self):
        """B1. 전역에 신원이 있으면 아무것도 쓰지 않는다 — 로컬은 비어 있다."""
        d = self.clone("clone-b1")
        home2 = os.path.join(self.base, "home-global")
        os.makedirs(home2)
        with open(os.path.join(home2, ".gitconfig"), "w", encoding="utf-8") as f:
            f.write("[user]\n\tname = Someone\n\temail = someone@example.org\n")
        env = {**self.env, "HOME": home2,
               "GIT_CONFIG_GLOBAL": os.path.join(home2, ".gitconfig")}
        res = self.fr.ensure_identity(d, env=env)
        self.assertEqual((res["set"], res["scope"], res["skipped"]),
                         (False, "global", "global"), res)
        self.assertEqual(_git(d, "config", "--local", "user.name", env=env).stdout.strip(), "")

    def test_b2_a_local_identity_is_not_overwritten(self):
        """B2. 이 저장소에 이미 박힌 값은 덮지 않는다 — 전역과 로컬을 나눠 읽어야 갈린다."""
        d = self.clone("clone-b2")
        _git(d, "config", "--local", "user.name", "Someone", env=self.env)
        _git(d, "config", "--local", "user.email", "someone@example.org", env=self.env)
        res = self.fr.ensure_identity(d, env=self.env)
        self.assertEqual((res["set"], res["scope"]), (False, "local"), res)
        self.assertEqual(_git(d, "config", "--local", "user.name", env=self.env).stdout.strip(),
                         "Someone")

    def test_b3_a_place_without_a_repo_is_left_alone(self):
        """B3. `.git` 이 없는 자리는 no-repo — 전역 설정에는 손대지 않는다."""
        d = os.path.join(self.base, "no-repo")
        os.makedirs(d)
        res = self.fr.ensure_identity(d, env=self.env)
        self.assertEqual((res["set"], res["skipped"]), (False, "no-repo"), res)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".gitconfig")),
                         "저장소가 없는 자리에서 전역 설정을 건드렸다")

    def test_f1_without_git_it_reports_and_raises_nothing(self):
        """F1. git 실행 파일이 없으면 예외를 내지 않고 error 한 줄을 돌려준다."""
        d = self.clone("clone-f1")
        res = self.fr.ensure_identity(d, env=self.env,
                                      git=os.path.join(self.base, "no-such-git"))
        self.assertEqual(res["set"], False, res)
        self.assertTrue(res["error"], res)


class IdentityLadder(unittest.TestCase):
    """신원이 아무 데도 없는 자리에 **무엇을** 세우는가 (REQ-20260921-011-62x6).

    임시값(`s9 <계정>` / `<계정>@local`)은 이 컴퓨터 밖에서 어느 계정에도 안 붙고, 한 번
    원격 이력에 박히면 빼는 길이 이력 재작성뿐이다. 그래서 칸이 셋이다 — 프로필에 적어
    둔 메일 → `<github>@users.noreply.github.com` → 임시값. 이 시험의 컴퓨터에는 git
    신원이 없다(HOME 을 빈 임시 자리로, GIT_CONFIG_NOSYSTEM 으로 시스템 설정도 끊는다).
    """

    @classmethod
    def setUpClass(cls):
        cls.fr = _load("s9_firstrun_ladder", FIRSTRUN)
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix="s9ladder-"))
        cls.home = os.path.join(cls.base, "home")
        os.makedirs(cls.home)
        cls.env = _clean_env()
        cls.env.update({"HOME": cls.home, "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": os.path.join(cls.home, ".gitconfig")})
        cls.acct = getpass.getuser()

    @classmethod
    def tearDownClass(cls):
        _rmtree(cls.base)

    def repo(self, name):
        """신원이 하나도 없는 빈 저장소 하나."""
        d = os.path.join(self.base, name)
        os.makedirs(d)
        r = _git(d, "init", "-q", "-b", "main", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return d

    def local(self, d, key):
        return _git(d, "config", "--local", "--get", key, env=self.env).stdout.strip()

    def test_n1_a_profile_mail_stands(self):
        """N1. 프로필에 쓸 수 있는 메일이 있으면 그 주소 — 이름은 github, 없으면 id."""
        self.assertEqual(
            self.fr.pick_identity({"emails": ["hong@corp.co.kr"], "github": "hong-gildong"},
                                  user="hong"),
            ("hong-gildong", "hong@corp.co.kr", "profile"))
        self.assertEqual(
            self.fr.pick_identity({"emails": ["hong@corp.co.kr"]}, user="hong"),
            ("hong", "hong@corp.co.kr", "profile"))

    def test_n2_github_gives_a_noreply_mail(self):
        """N2. 메일이 없고 github 가 있으면 GitHub 이 그 계정에 이어 주는 주소."""
        self.assertEqual(
            self.fr.pick_identity({"github": "hong-gildong"}, user="hong"),
            ("hong-gildong", "hong-gildong@users.noreply.github.com", "noreply"))

    def test_n3_nothing_falls_back_to_the_temp_value(self):
        """N3. 둘 다 없으면 지금까지대로 임시값이다 — 회귀."""
        want = self.fr.temp_identity(self.acct) + ("temp",)
        self.assertEqual(self.fr.pick_identity({}, account=self.acct, user="hong"), want)
        self.assertEqual(self.fr.pick_identity(None, account=self.acct), want)

    def test_n4_ensure_identity_says_which_rung_it_used(self):
        """N4. 실제 저장소에 박히는 값과 `source` 가 사다리의 칸을 말한다."""
        d = self.repo("ladder-n4")
        res = self.fr.ensure_identity(d, env=self.env, user="hong",
                                      profile={"emails": ["hong@corp.co.kr"],
                                               "github": "hong-gildong"})
        self.assertEqual((res["set"], res["source"], res["scope"], res["error"]),
                         (True, "profile", "local", ""), res)
        self.assertEqual((self.local(d, "user.name"), self.local(d, "user.email")),
                         ("hong-gildong", "hong@corp.co.kr"))
        d2 = self.repo("ladder-n4b")
        res = self.fr.ensure_identity(d2, env=self.env, user="hong",
                                      profile={"github": "hong-gildong"})
        self.assertEqual((res["set"], res["source"]), (True, "noreply"), res)
        self.assertEqual(self.local(d2, "user.email"),
                         "hong-gildong@users.noreply.github.com")

    def test_b1_a_dead_profile_mail_drops_to_the_next_rung(self):
        """B1. 이 컴퓨터 안에서만 닿는 주소는 건너뛴다 — 다음 칸으로 내려간다."""
        for mail in ("me@box.local", "me@x.localdomain", "me@x.lan", "me@x.home"):
            with self.subTest(mail=mail):
                self.assertEqual(
                    self.fr.pick_identity({"emails": [mail], "github": "hong-gildong"}),
                    ("hong-gildong", "hong-gildong@users.noreply.github.com", "noreply"))
                self.assertEqual(
                    self.fr.pick_identity({"emails": [mail]}, account=self.acct)[2], "temp")

    def test_b1b_a_reserved_domain_mail_drops_to_the_next_rung(self):
        """B1b. RFC 2606 이 예약한 도메인도 건너뛴다 (REQ-20260921-020-62x6).

        `.invalid` 는 「어디에도 닿지 않는다」고 못박힌 자리라 GitHub 계정에 등록할 수
        없고 메일도 가지 않는다 — 프로필에 그것이 적혀 있어도 「그 사람이 정해 둔
        주소」가 아니다."""
        for mail in ("me@x.invalid", "me@corp.example", "me@x.test", "me@box.localhost"):
            with self.subTest(mail=mail):
                self.assertEqual(
                    self.fr.pick_identity({"emails": [mail], "github": "hong-gildong"}),
                    ("hong-gildong", "hong-gildong@users.noreply.github.com", "noreply"))
                self.assertEqual(
                    self.fr.pick_identity({"emails": [mail]}, account=self.acct)[2], "temp")

    def test_b1c_a_reachable_lookalike_is_kept(self):
        """B1c. 예약된 것은 최상위 도메인 넷뿐이다 — 닮은 주소는 그대로 쓴다."""
        for mail in ("me@example.com", "me@example.org", "me@invalid.co.kr",
                     "me@local.example.com", "me@testing.io"):
            with self.subTest(mail=mail):
                self.assertEqual(
                    self.fr.pick_identity({"emails": [mail], "github": "hong-gildong"}),
                    ("hong-gildong", mail, "profile"))

    def test_b2_the_first_usable_mail_wins(self):
        """B2. 메일 꼴이 아닌 값은 건너뛰고, 여럿이면 쓸 수 있는 첫 번째를 쓴다."""
        self.assertEqual(
            self.fr.pick_identity({"emails": ["", "홍길동", "me@box.local",
                                              "hong@corp.co.kr", "second@corp.co.kr"]},
                                  user="hong"),
            ("hong", "hong@corp.co.kr", "profile"))

    def test_b3_a_github_name_that_cannot_be_one_is_skipped(self):
        """B3. GitHub 계정 이름의 꼴이 아니면 noreply 칸을 건너뛴다 — 안 닿는 주소를 짓지 않는다."""
        for bad in ("hong gildong", "hong@example.com", "-hong", "hong--" + "x" * 40, "홍길동"):
            with self.subTest(github=bad):
                self.assertEqual(
                    self.fr.pick_identity({"github": bad}, account=self.acct)[2], "temp")

    def test_b4_an_identity_already_there_is_not_touched(self):
        """B4. 이미 정해 둔 값이 있으면 사다리는 돌지 않는다 — 덮지 않는다(회귀)."""
        d = self.repo("ladder-b4")
        _git(d, "config", "--local", "user.name", "Someone", env=self.env)
        _git(d, "config", "--local", "user.email", "someone@example.org", env=self.env)
        res = self.fr.ensure_identity(d, env=self.env, user="hong",
                                      profile={"emails": ["hong@corp.co.kr"]})
        self.assertEqual((res["set"], res["scope"], res["source"]), (False, "local", ""), res)
        self.assertEqual(self.local(d, "user.email"), "someone@example.org")

    def test_f1_no_profile_still_stands_an_identity(self):
        """F1. 프로필을 넘기지 않아도 예외 없이 임시값까지 내려간다."""
        d = self.repo("ladder-f1")
        res = self.fr.ensure_identity(d, env=self.env)
        self.assertEqual((res["set"], res["source"]), (True, "temp"), res)
        self.assertEqual((self.local(d, "user.name"), self.local(d, "user.email")),
                         self.fr.temp_identity(self.acct))

    # ── commit 에 설 이름 (REQ-20260921-017-62x6) ──────────────────────────
    # commit 은 GitHub·터미널에서 **다시 만나는** 자리라 그 도구가 아는 이름으로 선다
    # (규약 2조). 첫 판은 사람 이름을 첫 칸에 두고 로마자가 필요하면 `display` 에
    # 적으라고 했다가 반려됐다 — 주인 지적 2026-09-21 13:01: 「설정에 개인 github
    # 이름이 있는데 왜 display_name 을 사용할지말지 고민하는거지?」. `display` 는
    # 화면 이름의 칸이고, 그 사람이 GitHub 에서 불리는 이름은 이미 `github` 에 있다.

    def test_c1_the_github_login_stands_in_the_commit(self):
        """N1·N2. github 이 있으면 그것이 선다 — 사람 이름이 함께 있어도."""
        self.assertEqual(
            self.fr.pick_identity({"emails": ["hong@corp.co.kr"], "github": "hong-gildong",
                                   "first_name": "길동", "last_name": "홍"}, user="hong"),
            ("hong-gildong", "hong@corp.co.kr", "profile"))
        # `display` 는 화면 이름의 칸이라 commit 이름을 가로채지 않는다
        self.assertEqual(
            self.fr.pick_identity({"github": "hong-gildong", "display": "Gildong Hong",
                                   "first_name": "길동", "last_name": "홍"}, user="hong"),
            ("hong-gildong", "hong-gildong@users.noreply.github.com", "noreply"))

    def test_c2_without_github_the_persons_name_stands(self):
        """N3. GitHub 을 쓰지 않는 사람은 제 이름으로, 그것도 없으면 id 로 선다."""
        self.assertEqual(
            self.fr.pick_identity({"emails": ["hong@corp.co.kr"],
                                   "first_name": "길동", "last_name": "홍"},
                                  user="hong")[0], "홍길동")
        self.assertEqual(
            self.fr.pick_identity({"emails": ["hong@corp.co.kr"]}, user="hong")[0], "hong")

    def test_c3_the_repo_gets_the_same_name(self):
        """N4. 실제 저장소에 박히는 값도 같은 이름이다."""
        d = self.repo("ladder-c3")
        res = self.fr.ensure_identity(d, env=self.env, user="hong",
                                      profile={"emails": ["hong@corp.co.kr"],
                                               "github": "hong-gildong",
                                               "first_name": "길동", "last_name": "홍"})
        self.assertEqual((res["set"], res["source"], res["error"]), (True, "profile", ""), res)
        self.assertEqual(self.local(d, "user.name"), "hong-gildong")

    def test_c4_one_half_of_a_name_still_stands(self):
        """B1·B2. github 이 없을 때 — 성만·이름만 있어도 그 글자가 서고,
        로마자는 「이름 성」이다."""
        self.assertEqual(self.fr.pick_identity({"emails": ["a@corp.co.kr"],
                                                "first_name": "길동"}, user="hong")[0], "길동")
        self.assertEqual(self.fr.pick_identity({"emails": ["a@corp.co.kr"],
                                                "last_name": "홍"}, user="hong")[0], "홍")
        self.assertEqual(self.fr.pick_identity({"emails": ["a@corp.co.kr"],
                                                "first_name": "Gildong",
                                                "last_name": "Hong"}, user="hong")[0],
                         "Gildong Hong")

    def test_c5_a_name_that_breaks_the_author_line_is_dropped(self):
        """B3. 꺾쇠·줄바꿈·제어문자가 섞인 이름은 버리고 다음 칸으로 내려간다."""
        for bad in ("홍 <a@b.c>", "홍\n길동", "홍\x00길동"):
            with self.subTest(display=bad):
                self.assertEqual(
                    self.fr.pick_identity({"emails": ["a@corp.co.kr"], "display": bad},
                                          user="hong")[0], "hong")
        # 앞뒤 공백과 사이의 겹공백은 다듬는다 — 버릴 값은 아니다.
        self.assertEqual(
            self.fr.pick_identity({"emails": ["a@corp.co.kr"], "display": "  Gildong   Hong "},
                                  user="hong")[0], "Gildong Hong")

    def test_c6_the_temp_rung_keeps_its_shape(self):
        """B4. 임시 칸은 `s9 <계정>` 그대로다 — doctor 가 그 모양으로 우리 값을 가른다."""
        self.assertEqual(
            self.fr.pick_identity({"first_name": "길동", "last_name": "홍"},
                                  account=self.acct, user="hong"),
            self.fr.temp_identity(self.acct) + ("temp",))

    def test_c7_the_name_is_built_in_one_place(self):
        """F2. 화면의 이름과 commit 의 이름은 같은 함수에서 나온다 — 두 벌이 아니다."""
        s9 = _load("s9_for_name", os.path.join(os.path.dirname(FIRSTRUN), "s9.py"))
        for prof in ({"display": "타치코마", "first_name": "길동", "last_name": "홍"},
                     {"first_name": "길동", "last_name": "홍"},
                     {"first_name": "Gildong", "last_name": "Hong"},
                     {"last_name": "홍"}, {}):
            with self.subTest(profile=prof):
                self.assertEqual(s9.user_full_name(prof), self.fr.person_full_name(prof))

    def test_f3_join_does_not_carry_a_dead_mail_into_the_profile(self):
        """F3. 합류가 이 컴퓨터의 git 메일을 프로필로 옮길 때 죽은 주소는 옮기지 않는다.

        넘어오는 값은 이 컴퓨터의 `git config user.email` 인데, 신원이 없던 자리에서는
        그것이 방금 우리가 박은 임시 주소다 — 그것을 프로필에 적으면 기계가 지어낸
        주소가 사람의 회사 메일 옆에 영영 남는다."""
        updated = []
        ns = {"load_project": lambda slug: ({"slug": slug, "members":
                                             [{"user": "bob", "role": "member"}]},
                                            "본문\n", os.path.join(self.base, "mp.md")),
              "user_role": lambda u: "member",
              "do_user_attach": lambda u: ("acct", "machine", False),
              "EMAIL_RE": r"[^@\s]+@[^@\s]+\.[^@\s]+",
              "user_profile": lambda u: {"emails": ["bob@corp.co.kr"]},
              "do_user_update": lambda u, **kw: updated.append(kw),
              "user_config": lambda u: {"default_project": "mp"},
              "do_user_config_set": lambda *a, **kw: None,
              "today_date": lambda: "2026-09-21",
              "now_iso": lambda: "2026-09-21T11:00:00+09:00"}
        self.fr.join_project(ns, "mp", "bob", f"{self.acct}@local")
        self.assertEqual(updated, [], "임시 주소가 프로필 emails 에 박혔다")
        self.fr.join_project(ns, "mp", "bob", "bob-new@corp.co.kr")
        self.assertEqual([kw.get("emails") for kw in updated],
                         [["bob@corp.co.kr", "bob-new@corp.co.kr"]],
                         "멀쩡한 주소까지 막았다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
