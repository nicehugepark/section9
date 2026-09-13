"""초대 명령으로 첫 실행 — `s9 code --join <url> --project <slug>` 한 번으로 팀 저장소에 합류하는가
(REQ-20260913-013-62x6).

로컬 bare 저장소를 GitHub 삼는다. 첫 인스턴스(작업 트리 사본 + ensure_repo 의 저장소)에 사람 둘
(admin alice · member bob)과 프로젝트 둘(mp — bob 이 이메일 키 `bob@example.org` 로 초대돼 있다 ·
other — bob 미참여)을 세워 bare 로 push 하고, 두 번째 자리(코드만 — test_firstrun 의 release_shape)
에서 HOME 의 .gitconfig 를 bob 으로 둔 채 **그 자리의** `bin/s9 code --join <bare> --project mp
--no-open` 을 S9_CODE_DRYRUN=1 로 돌린다 — claude 를 띄우기 직전까지 사람의 흐름을 그대로 지난다
(합류 → 대시보드 → s9-install → 신원 → 프로젝트 참여).

실서버는 클래스당 하나(시험 포트) — 정리는 test_firstrun 과 같다.

실행: python3 tests/ join
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
BOB_EMAIL = "bob@example.org"
DRIFT = os.path.join("harness", "common", "PROTOCOL.md")     # 배포판에 실리는 추적 파일 하나
DRIFT_LINE = "\nLOCAL-DRIFT — 원격 판이 이겨야 한다\n"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _stub_code_root(path):
    os.makedirs(os.path.join(path, "bin"), exist_ok=True)
    with open(os.path.join(path, "bin", "s9.py"), "w", encoding="utf-8") as f:
        f.write("# stub\n")


class JoinByInvite(unittest.TestCase):
    """초대 명령 한 줄 — 실서버 하나, 클래스당 한 번."""

    @classmethod
    def setUpClass(cls):
        cls.fr = _load("s9_firstrun_join", FIRSTRUN)
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix="s9join-"))
        # ── 팀의 첫 인스턴스: 저장소 + 사람 둘 + 프로젝트 둘 → bare 로 push ──
        cls.lead = os.path.join(cls.base, "lead")
        os.makedirs(cls.lead)
        release_shape(cls.lead)
        home1 = os.path.join(cls.base, "home-lead")
        os.makedirs(os.path.join(home1, ".claude"))
        env1 = _clean_env()
        env1.update({"HOME": home1, "CLAUDE_CONFIG_DIR": os.path.join(home1, ".claude"),
                     "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off", "S9_USER": "alice"})
        with mock.patch.dict(os.environ, {"S9_ROOT": cls.lead}):
            shape = _load("s9_lead_body", os.path.join(cls.lead, "bin", "s9"))
        res = cls.fr.ensure_repo(cls.lead, shape.INSTANCE_TRACK_GITIGNORE,
                                 shape.sync_marker_body("local", chosen=False), env=env1)
        if not res["created"]:
            raise RuntimeError(f"첫 인스턴스의 저장소가 서지 않았다: {res}")
        cls._cli(cls.lead, env1, "user", "add", "alice", "--role", "admin",
                 "--emails", "alice@example.org")
        cls._cli(cls.lead, env1, "project", "add", "mp", "--name", "M P")
        cls._cli(cls.lead, env1, "project", "add", "other", "--name", "Other")
        cls._cli(cls.lead, {**env1, "S9_USER": "bob"}, "user", "add", "bob")
        # 초대(REQ-20260913-010)가 적어 두는 꼴 — 프로필 emails 에 없는 이메일은 그대로 키가 된다
        cls._cli(cls.lead, env1, "project", "member", "mp", "add", BOB_EMAIL,
                 "--role", "contributor")
        _git(cls.lead, "add", "vault", "users", "projects", ".s9-sync")
        _git(cls.lead, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "team docs", env=env1)
        cls.bare = os.path.join(cls.base, "team.git")
        r = _git(cls.base, "init", "-q", "--bare", cls.bare)
        if r.returncode != 0:
            raise RuntimeError(r.stderr)
        _git(cls.lead, "remote", "add", "origin", cls.bare)
        r = _git(cls.lead, "push", "-q", "origin", "main", env=env1)
        if r.returncode != 0:
            raise RuntimeError(f"bare 로 push 하지 못했다: {r.stderr}")
        cls.team_head = _git(cls.bare, "rev-parse", "main").stdout.strip()
        # ── 초대받은 사람의 자리: 코드만, git 신원은 bob ──
        cls.root = os.path.join(cls.base, "section9-0.9.0")
        os.makedirs(cls.root)
        release_shape(cls.root)
        with open(os.path.join(cls.root, DRIFT), "a", encoding="utf-8") as f:
            f.write(DRIFT_LINE)
        cls.home = os.path.join(cls.base, "home-bob")
        cls.cfg = os.path.join(cls.home, ".claude")
        os.makedirs(cls.cfg)
        with open(os.path.join(cls.home, ".gitconfig"), "w", encoding="utf-8") as f:
            f.write(f"[user]\n\tname = bob\n\temail = {BOB_EMAIL}\n")
        cls.port = free_port()
        cls.env = _clean_env()
        cls.env.update({"HOME": cls.home, "CLAUDE_CONFIG_DIR": cls.cfg,
                        "S9_PORT": str(cls.port), "S9_CODE_DRYRUN": "1",
                        "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off"})
        cls.s9 = os.path.join(cls.root, "bin", "s9")
        cls._mod = None
        cls.first = cls.code()

    @classmethod
    def _cli(cls, root, env, *argv):
        r = subprocess.run([sys.executable, os.path.join(root, "bin", "s9"), *argv],
                           capture_output=True, encoding="utf-8", errors="replace",
                           env=env, cwd=root, stdin=subprocess.DEVNULL, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"s9 {' '.join(argv)} 실패: {r.stdout}{r.stderr}")
        return r

    @classmethod
    def code(cls):
        return subprocess.run([sys.executable, cls.s9, "code", "--join", cls.bare,
                               "--project", "mp", "--no-open"],
                              capture_output=True, encoding="utf-8", errors="replace",
                              env=cls.env, cwd=cls.root, stdin=subprocess.DEVNULL,
                              timeout=300)

    @classmethod
    def _serve_procs(cls):
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
        for p in left:
            try:
                os.kill(p["pid"], signal.SIGKILL)
            except OSError:
                pass
        if left:
            time.sleep(1.0)
        _rmtree(cls.base)

    @classmethod
    def s9mod(cls):
        """합류한 자리의 s9 본체를 모듈로 — ROOT 는 import 때 잡히므로 S9_ROOT 를 잠깐 돌린다."""
        if cls._mod is None:
            with mock.patch.dict(os.environ, {"S9_ROOT": cls.root}):
                cls._mod = _load("s9_joined_body", cls.s9)
        return cls._mod

    def as_bob(self):
        """모듈 안의 판정이 bob 으로 서게 — 러너의 세션·계정 환경을 걷는다."""
        patch = mock.patch.dict(os.environ, {"S9_USER": "bob", "HOME": self.home})
        patch.start()
        os.environ.pop("S9_SESSION", None)
        self.addCleanup(patch.stop)

    def members(self, slug="mp"):
        mod = self.s9mod()
        return list((mod.load_project(slug)[0].get("members") or []))

    def test_n1_repo_is_the_team_repo_and_install_ran_after_it(self):
        """N1. 합류: exit 0 · 「합류했다」 · main=origin/main · origin=bare · 문서·사람이 왔다 · git 훅 · 대시보드."""
        r = self.first
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("합류했다", r.stdout)
        self.assertIn('["claude"', r.stdout, "claude 를 띄우는 자리까지 가지 못했다")
        self.assertEqual(_git(self.root, "symbolic-ref", "--short", "HEAD").stdout.strip(), "main")
        self.assertEqual(_git(self.root, "remote", "get-url", "origin").stdout.strip(), self.bare)
        self.assertEqual(_git(self.root, "rev-parse", "origin/main").stdout.strip(), self.team_head)
        # 그 뒤 문서 이벤트가 commit 을 더했을 수 있다 — 팀의 끝이 이 자리 이력의 조상이면 된다
        self.assertEqual(_git(self.root, "merge-base", "--is-ancestor", self.team_head, "HEAD").returncode, 0)
        self.assertEqual(_git(self.root, "config", "branch.main.remote").stdout.strip(), "origin")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "vault", "projects", "mp.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "users", "alice", "profile.md")))
        for name in ("pre-commit", "post-commit"):
            self.assertTrue(os.path.isfile(os.path.join(self.root, ".git", "hooks", name)),
                            f"{name} 이 .git/hooks 에 없다 — 설치가 합류보다 먼저 돌았다")
        self.assertIn("대시보드", r.stdout)
        wait_server(self.port)
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/serveinfo", timeout=5) as resp:
            info = json.loads(resp.read().decode("utf-8", "replace"))
        self.assertEqual(os.path.realpath(str(info.get("root") or "")), self.root, info)

    def test_n2_remote_code_wins_and_sync_is_remote(self):
        """N2. 합류 전 그 자리의 로컬 변경은 원격 판으로 덮인다 · .s9-sync 는 remote 로 올라간다."""
        mine = _read(os.path.join(self.root, DRIFT))
        self.assertNotIn("LOCAL-DRIFT", mine)
        self.assertEqual(mine, _read(os.path.join(self.lead, DRIFT)))
        self.assertEqual(_git(self.root, "status", "--porcelain", "--", DRIFT).stdout.strip(), "")
        self.assertEqual(_read(os.path.join(self.root, ".s9-sync")).split()[0], "remote")

    def test_n3_email_keyed_member_becomes_the_user(self):
        """N3. mp 의 `bob@example.org` 멤버가 bob(contributor) 이 되고 프로필 emails 에 그 이메일이 붙는다."""
        self.assertIn("프로젝트 mp 에 참여했다", self.first.stdout)
        users = [m.get("user") for m in self.members()]
        self.assertIn("bob", users)
        self.assertNotIn(BOB_EMAIL, users)
        me = next(m for m in self.members() if m.get("user") == "bob")
        self.assertEqual(me.get("role"), "contributor")
        prof = self.s9mod().user_profile("bob")
        self.assertIn(BOB_EMAIL, [str(e).lower() for e in (prof.get("emails") or [])])

    def test_n4_the_project_is_bobs_default_for_the_next_s9_code(self):
        """N4. users/bob/config 의 default_project=mp · 그 자리의 code_project(None) 이 bob 으로 mp 를 낸다."""
        mod = self.s9mod()
        self.assertEqual(mod.user_config("bob").get("default_project"), "mp")
        self.as_bob()
        self.assertEqual(mod.code_project(None), "mp")
        # 명시가 이긴다 — 초대받은 프로젝트가 다른 세션의 --project 를 덮지 않는다
        self.assertEqual(mod.code_project("other"), "other")

    def test_n5_identity_is_attached_and_a_non_member_joins_as_contributor(self):
        """N5. bob 프로필에 이 OS 계정·이 컴퓨터가 붙는다 · 멤버가 아닌 프로젝트(other)는 contributor 로 들어간다."""
        mod = self.s9mod()
        prof = mod.user_profile("bob")
        self.assertIn(getpass.getuser(), prof.get("os_accounts") or [])
        self.assertIn(mod.current_machine(), prof.get("machines") or [])
        self.as_bob()
        res = self.fr.join_project(vars(mod), "other", "bob", BOB_EMAIL)
        self.assertTrue(res["added"], res)
        me = next(m for m in self.members("other") if m.get("user") == "bob")
        self.assertEqual(me.get("role"), "contributor")
        self.assertEqual(mod.user_config("bob").get("default_project"), "other")
        mod.do_user_config_set("bob", "default_project", "mp", actor="bob")   # 다른 항목의 전제로 되돌린다

    def test_i1_second_run_changes_nothing(self):
        """I1. 같은 URL 로 두 번째: exit 0 · 「합류했다」 없음 · bob 멤버 하나 · os_accounts 중복 없음 · 기본 그대로."""
        r = self.code()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("합류했다", r.stdout)
        self.assertIn("이미 합류한 자리", r.stdout)
        users = [m.get("user") for m in self.members()]
        self.assertEqual(users.count("bob"), 1, users)
        self.assertNotIn(BOB_EMAIL, users)
        accts = self.s9mod().user_profile("bob").get("os_accounts") or []
        self.assertEqual(accts.count(getpass.getuser()), 1, accts)
        self.assertEqual(self.s9mod().user_config("bob").get("default_project"), "mp")
        res = self.fr.join_repo(self.root, self.bare, env=self.env)
        self.assertEqual((res["created"], res["skipped"], res["error"]), (False, "joined", ""), res)

    def test_e1_a_different_url_is_refused(self):
        """E1. origin 이 있는 자리에 다른 URL: error(origin 언급) · origin·가지 불변."""
        res = self.fr.join_repo(self.root, os.path.join(self.base, "elsewhere.git"), env=self.env)
        self.assertFalse(res["created"], res)
        self.assertIn("origin", res["error"])
        self.assertEqual(_git(self.root, "remote", "get-url", "origin").stdout.strip(), self.bare)
        self.assertEqual(_git(self.root, "symbolic-ref", "--short", "HEAD").stdout.strip(), "main")

    def test_e2_a_place_with_documents_or_without_code_is_refused(self):
        """E2. vault/ 에 문서가 있는 자리 → error(문서) 이고 .git 을 만들지 않는다 · 코드 없는 자리 → no-code."""
        d = os.path.join(self.base, "with-docs")
        _stub_code_root(d)
        os.makedirs(os.path.join(d, "vault", "requests"))
        with open(os.path.join(d, "vault", "requests", "REQ-x.md"), "w", encoding="utf-8") as f:
            f.write("---\nid: REQ-x\n---\n")
        res = self.fr.join_repo(d, self.bare, env=self.env)
        self.assertIn("문서", res["error"])
        self.assertFalse(os.path.exists(os.path.join(d, ".git")))
        empty = os.path.join(self.base, "empty-vault")     # 빈 디렉토리는 문서가 아니다
        _stub_code_root(empty)
        os.makedirs(os.path.join(empty, "vault", "requests"))
        self.assertFalse(self.fr.has_documents(empty))
        data_only = os.path.join(self.base, "data-only")
        os.makedirs(data_only)
        res = self.fr.join_repo(data_only, self.bare, env=self.env)
        self.assertEqual((res["created"], res["skipped"]), (False, "no-code"), res)

    def test_f1_a_failed_fetch_rolls_back(self):
        """F1. 없는 URL: error · 이번에 만든 .git 되돌림 · 표식 없음."""
        d = os.path.join(self.base, "bad-url")
        _stub_code_root(d)
        res = self.fr.join_repo(d, os.path.join(self.base, "no-such.git"), "x\n", "remote\n",
                                env=self.env)
        self.assertFalse(res["created"], res)
        self.assertTrue(res["error"], res)
        self.assertIn("rolled-back", res["did"])
        self.assertFalse(os.path.exists(os.path.join(d, ".git")))
        self.assertFalse(os.path.exists(os.path.join(d, ".s9-sync")))

    def test_u1_our_valued_flags_never_reach_claude(self):
        """U1. code_argv: --join/--project 는 값까지 떼어지고 나머지 순서는 그대로 · `--join=<url>` 꼴도 같다."""
        mod = self.s9mod()
        ns = mod.code_argv(["--join", "URL", "--project", "mp", "--no-open", "-p", "안녕"])
        self.assertEqual((ns.join, ns.project, ns.no_open), ("URL", "mp", True))
        self.assertEqual(ns.claude_args, ["-p", "안녕"])
        ns = mod.code_argv(["--model", "x", "--join=URL2", "질문", "-c"])
        self.assertEqual((ns.join, ns.project), ("URL2", ""))
        self.assertEqual(ns.claude_args, ["--model", "x", "질문", "-c"])
        ns = mod.code_argv(["-p", "안녕"])
        self.assertEqual((ns.join, ns.project), ("", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
