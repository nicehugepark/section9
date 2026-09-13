"""GitHub 연동 — link/create/unlink 와 거부 사유 (REQ-20260913-008-62x6).

로컬 bare 저장소가 GitHub 노릇을, 가짜 gh 스크립트와 로컬 http 스텁이 gh·GitHub API
노릇을 한다. 네트워크에 나가지 않는다. 재는 것: 빈 저장소에 잇기 · 비어 있지 않은
저장소 거부 · 닿지 않는 URL 거부 · unlink(멱등) · 우리 이력이면 다시 잇기 · gh 의
argv · 토큰 API 의 경로와 헤더 · state 의 can.why · URL 정규화 · 토큰이 argv 에 없다.

격리: S9_ROOT=임시 뿌리(마커 읽기·쓰기는 bin/s9.py 의 sync_mode/sync_set_mode 를 그대로
넘긴다). 실행: python3 tests/ github_link
"""
import base64
import http.server
import importlib.machinery
import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
GH_MOD = os.path.join(HERE, "..", "bin", "s9_github.py")
TOKEN = "fake-github-token-for-the-stub-0000000000"   # 진짜 꼴(ghp_…)이면 guard 의 비밀 검사가 commit 을 막는다 — 맞는 일이다


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def _load(name, path):
    spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ApiStub(http.server.BaseHTTPRequestHandler):
    seen = []            # (method, path, Authorization, body)
    clone_url = ""

    def _send(self, st, body):
        raw = json.dumps(body).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        ApiStub.seen.append(("GET", self.path, self.headers.get("Authorization", ""), None))
        if self.path == "/user":
            return self._send(200, {"login": "tester"})
        self._send(404, {"message": "Not Found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode() or "{}")
        ApiStub.seen.append(("POST", self.path, self.headers.get("Authorization", ""), body))
        if self.path in ("/user/repos", "/orgs/acme/repos"):
            owner = "acme" if self.path.startswith("/orgs/") else "tester"
            return self._send(201, {"clone_url": ApiStub.clone_url,
                                    "html_url": f"https://github.com/{owner}/{body.get('name')}",
                                    "full_name": f"{owner}/{body.get('name')}"})
        self._send(404, {"message": "Not Found"})

    def log_message(self, *a):
        pass


class GithubLink(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in cls._genv:
            os.environ.pop(k, None)
        cls._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_SYNC")}
        os.environ.pop("S9_SYNC", None)
        cls.tmp = tempfile.mkdtemp(prefix="s9ghlink-")
        cls.root = os.path.join(cls.tmp, "work")
        os.makedirs(os.path.join(cls.root, "vault"))
        _git(cls.root, "init", "-q", "-b", "main")
        _git(cls.root, "config", "user.name", "t")
        _git(cls.root, "config", "user.email", "t@t")
        with open(os.path.join(cls.root, "vault", "seed.md"), "w") as f:
            f.write("seed\n")
        os.environ["S9_ROOT"] = cls.root
        cls.m = _load("s9_ghlink_main", S9)
        cls.g = _load("s9_ghlink_mod", GH_MOD)
        cls.m.sync_set_mode("local", chosen=False)
        _git(cls.root, "add", "-A")
        _git(cls.root, "commit", "-qm", "init")
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), ApiStub)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        for k, v in cls._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.update(cls._genv)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # 시험마다 같은 출발점 — origin 없음 · local(고르지 않음) · 새 bare · gh 없음 · 로컬 API
        _git(self.root, "remote", "remove", "origin")
        self.m.sync_set_mode("local", chosen=False)
        self.bare = os.path.join(tempfile.mkdtemp(prefix="s9ghbare-", dir=self.tmp), "origin.git")
        _git(self.tmp, "init", "-q", "--bare", "-b", "main", self.bare)
        self.g.find_gh = lambda: ""
        self.g._LOGIN_CACHE.clear()
        self.g.API_BASE = f"http://127.0.0.1:{self.port}"
        ApiStub.seen, ApiStub.clone_url = [], self.bare

    # ── 살림 ──
    def _state(self, **kw):
        return self.g.github_state(self.root, mode_get=self.m.sync_mode, **kw)

    def _link(self, url, **kw):
        return self.g.github_link(self.root, url, mode_set=self.m.sync_set_mode, **kw)

    def _origin(self):
        return _git(self.root, "remote", "get-url", "origin").stdout.strip()

    def _fake_gh(self, protocol="https"):
        d = tempfile.mkdtemp(prefix="s9ghbin-", dir=self.tmp)
        log = os.path.join(d, "argv.log")
        p = os.path.join(d, "gh")
        with open(p, "w") as f:
            f.write("#!/bin/sh\n"
                    f"printf '%s\\n' \"$*\" >> {shlex.quote(log)}\n"
                    "case \"$1 $2\" in\n"
                    "  'auth token') echo fake-gh-token ;;\n"
                    "  'api user') echo '{\"login\": \"tester\"}' ;;\n"
                    f"  'config get') echo {protocol} ;;\n"
                    f"  'repo create') echo {shlex.quote(self.bare)} ;;\n"
                    "  *) echo \"unexpected: $*\" >&2; exit 2 ;;\n"
                    "esac\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        self.g.find_gh = lambda: p
        return log

    # ── S1 ──
    def test_state_unlinked_and_can_why(self):
        st = self._state()
        self.assertFalse(st["linked"])
        self.assertEqual((st["origin"], st["web_url"], st["sync_mode"]), ("", "", "local"))
        self.assertEqual(st["auth"], {"gh": False, "token": False, "login": ""})
        self.assertTrue(st["can"]["link"]["ok"])
        self.assertFalse(st["can"]["create"]["ok"])
        self.assertIn("GITHUB_TOKEN", st["can"]["create"]["why"])
        self.assertIn("gh", st["can"]["create"]["why"])
        self.assertEqual(st["token_key"], "GITHUB_TOKEN")

    # ── S2 ──
    def test_link_empty_repo(self):
        res = self._link(self.bare)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self._origin(), self.bare)
        head = _git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(_git(self.tmp, "--git-dir", self.bare, "rev-parse", "main").stdout.strip(), head)
        up = _git(self.root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        self.assertEqual(up.stdout.strip(), "origin/main")
        self.assertEqual(self.m.sync_mode(), "remote")
        self.assertTrue(self.m.sync_mode_chosen())
        self.assertEqual((res["sync_mode"], res["branch"]), ("remote", "main"))
        st = self._state()
        self.assertTrue(st["linked"])
        self.assertEqual(st["origin"], self.bare)

    # ── S3 ──
    def test_link_rejects_nonempty_foreign_repo(self):
        other = os.path.join(self.tmp, "other-" + os.path.basename(os.path.dirname(self.bare)))
        os.makedirs(other)
        _git(other, "init", "-q", "-b", "main")
        _git(other, "config", "user.name", "o")
        _git(other, "config", "user.email", "o@o")
        with open(os.path.join(other, "theirs.md"), "w") as f:
            f.write("theirs\n")
        _git(other, "add", "-A")
        _git(other, "commit", "-qm", "theirs")
        _git(other, "push", "-q", self.bare, "main")
        res = self._link(self.bare)
        self.assertFalse(res["ok"])
        self.assertIn("비어 있지 않은 저장소", res["error"])
        self.assertIn("code --join", res["error"])
        self.assertEqual(self._origin(), "")
        self.assertEqual(self.m.sync_mode(), "local")

    # ── S4 ──
    def test_link_rejects_unreachable_url(self):
        res = self._link(os.path.join(self.tmp, "nowhere.git"))
        self.assertFalse(res["ok"])
        self.assertIn("닿지 않거나 권한이 없습니다", res["error"])
        self.assertEqual(self._origin(), "")
        self.assertEqual(self.m.sync_mode(), "local")

    # ── S5 ──
    def test_unlink_then_relink_own_history(self):
        self.assertTrue(self._link(self.bare)["ok"])
        res = self.g.github_unlink(self.root, mode_set=self.m.sync_set_mode)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self._origin(), "")
        self.assertEqual(self.m.sync_mode(), "local")
        self.assertTrue(os.path.exists(os.path.join(self.root, "vault", "seed.md")))
        again = self.g.github_unlink(self.root, mode_set=self.m.sync_set_mode)
        self.assertTrue(again["ok"])
        self.assertIn("이미 끊겨", again["said"])
        # 원격에 남은 것은 우리 이력이다 — 다시 잇는 것은 거부가 아니다
        back = self._link(self.bare)
        self.assertTrue(back["ok"], back)
        self.assertEqual(self.m.sync_mode(), "remote")

    # ── S6 ──
    @unittest.skipIf(os.name == "nt", "가짜 gh 는 sh 스크립트다")
    def test_create_calls_gh_with_visibility_and_org(self):
        log = self._fake_gh()
        res = self.g.github_create(self.root, "demo", private=True, mode_set=self.m.sync_set_mode)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self._origin(), self.bare)
        self.assertEqual(self.m.sync_mode(), "remote")
        res2 = self.g.github_create(self.root, "demo", private=False, org="acme",
                                    mode_set=self.m.sync_set_mode)
        self.assertTrue(res2["ok"], res2)
        with open(log, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertIn("repo create demo --private", lines)
        self.assertIn("repo create acme/demo --public", lines)
        self.assertNotIn("--confirm", " ".join(lines))     # gh 2.x 에는 없는 옵션이다

    # ── S7 ──
    def test_create_via_token_api(self):
        res = self.g.github_create(self.root, "demo", private=True,
                                   mode_set=self.m.sync_set_mode, token=TOKEN)
        self.assertTrue(res["ok"], res)
        posts = [s for s in ApiStub.seen if s[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][1], "/user/repos")
        self.assertEqual(posts[0][2], "Bearer " + TOKEN)
        self.assertEqual(posts[0][3], {"name": "demo", "private": True})
        self.assertEqual(self._origin(), self.bare)
        self.assertEqual(res["created"], "https://github.com/tester/demo")
        res2 = self.g.github_create(self.root, "demo", private=False, org="acme",
                                    mode_set=self.m.sync_set_mode, token=lambda: TOKEN)
        self.assertTrue(res2["ok"], res2)
        self.assertEqual([s[1] for s in ApiStub.seen if s[0] == "POST"][-1], "/orgs/acme/repos")
        self.assertEqual(ApiStub.seen[-1][3]["private"], False)

    # ── S8 ──
    def test_state_with_token_asks_login_and_hides_value(self):
        st = self._state(token=TOKEN)
        self.assertEqual(st["auth"], {"gh": False, "token": True, "login": "tester"})
        self.assertTrue(st["can"]["create"]["ok"])
        self.assertNotIn(TOKEN, json.dumps(st, ensure_ascii=False))
        self.assertEqual([s[1] for s in ApiStub.seen], ["/user"])
        self._state(token=TOKEN)                       # 5분 캐시 — 두 번째는 묻지 않는다
        self.assertEqual(len(ApiStub.seen), 1)

    # ── S9 ──
    def test_url_forms_normalize_to_web_url(self):
        for u in ("https://github.com/o/r", "https://github.com/o/r.git", "https://github.com/o/r/",
                  "git@github.com:o/r.git", "ssh://git@github.com/o/r.git", "github.com/o/r",
                  "HTTPS://GitHub.com/o/r.git"):
            info = self.g.parse_remote(u)
            self.assertEqual(info["web_url"], "https://github.com/o/r", u)
            self.assertEqual((info["owner"], info["repo"]), ("o", "r"), u)
            self.assertEqual(info["ssh_url"], "git@github.com:o/r.git", u)
        self.assertEqual(self.g.parse_remote(self.bare)["web_url"], "")
        self.assertEqual(self.g.parse_remote(r"C:\repo\x")["web_url"], "")

    # ── S10 ──
    def test_token_travels_by_env_not_argv_and_helper_lifecycle(self):
        calls, plan = [], {"ls": 128, "push": 0}
        real = self.g._run

        def spy(argv, cwd=None, timeout=0, env=None):
            calls.append((list(argv), dict(env or {})))
            if "ls-remote" in argv:
                return subprocess.CompletedProcess(argv, plan["ls"], "",
                                                   "fatal: could not read from remote" if plan["ls"] else "")
            if "push" in argv:
                return subprocess.CompletedProcess(argv, plan["push"], "", "")
            return real(argv, cwd=cwd, timeout=timeout or 10, env=env)

        self.g._run = spy
        try:
            res = self._link("https://github.com/o/r.git", token=TOKEN)
            self.assertFalse(res["ok"])
            ls = [c for c in calls if "ls-remote" in c[0]]
            self.assertEqual(len(ls), 1)
            argv, env = ls[0]
            self.assertNotIn(TOKEN, " ".join(argv))
            self.assertEqual(env["GIT_CONFIG_KEY_0"], "http.https://github.com/.extraheader")
            basic = env["GIT_CONFIG_VALUE_0"].split("Basic ", 1)[1]
            self.assertEqual(base64.b64decode(basic).decode(), "x-access-token:" + TOKEN)
            self.assertEqual(self._origin(), "")            # 접근 확인에서 진 것은 아무것도 바꾸지 않는다
            # 접근·push 가 되는 자리(원격은 흉내) — origin 과 그 뒤 동기화가 쓸 helper 가 남는다
            plan["ls"] = 0
            res = self._link("https://github.com/o/r.git", token=TOKEN)
            self.assertTrue(res["ok"], res)
            self.assertEqual((self._origin(), self.m.sync_mode(), res["web_url"]),
                             ("https://github.com/o/r.git", "remote", "https://github.com/o/r"))
            helper = _git(self.root, "config", "--local", "--get", "credential.https://github.com.helper")
            self.assertEqual(helper.returncode, 0)
            self.assertIn("secret get GITHUB_TOKEN", helper.stdout)
            self.assertIn(os.path.join(os.path.dirname(os.path.realpath(GH_MOD)), "s9"), helper.stdout)
            self.assertNotIn(TOKEN, helper.stdout)          # 값이 아니라 읽는 길만 적힌다
            self.assertTrue(self.g.github_unlink(self.root, mode_set=self.m.sync_set_mode)["ok"])
            gone = _git(self.root, "config", "--local", "--get", "credential.https://github.com.helper")
            self.assertNotEqual(gone.returncode, 0)
            self.assertEqual((self._origin(), self.m.sync_mode()), ("", "local"))
        finally:
            self.g._run = real
        # 서버에는 답할 사람이 없다 — git 이 자격을 묻지 않고 실패하도록 환경에 못박는다
        r = self.g._run([sys.executable, "-c",
                         "import os; print(os.environ.get('GIT_TERMINAL_PROMPT'))"])
        self.assertEqual(r.stdout.strip(), "0")


if __name__ == "__main__":
    unittest.main()
