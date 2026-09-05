"""viewer 쓰기 게이트 (REQ-20260902-028 · DOC-20260902-001 §2 축4).

시스템 role `viewer` 는 ROLES 에 있었지만 판정에 쓰는 코드가 없었다. 강제 자리는
둘뿐이다 — 문서 쓰기의 단일 경계 `write_doc`(`_write_gate`) 와 대시보드 POST
진입부. 이 파일은 **클래스 시험**이다: viewer × 쓰기 서브커맨드 × POST 라우트
전수를 돌려 전부 거부됨을, 조회는 됨을 확인한다. POST 라우트 목록은 소스에서
뽑는다 — 라우트가 늘면 허용 목록에 올리기 전엔 여기가 먼저 빨개진다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ viewer_gate
"""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
HOOK = os.path.join(REPO, "bin", "s9-audit-prompt")
MACHINE = "TESTMACH"

from portpool import free_port, wait_server  # noqa: E402

REQ_RE = re.compile(r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _tree_digest(root):
    """vault/ 와 users/*/profile.md 의 내용 지문 — 거부된 쓰기는 흔적이 없어야 한다."""
    h = hashlib.sha256()
    for base in ("vault", "users"):
        for dp, dn, fns in os.walk(os.path.join(root, base)):
            dn[:] = sorted(d for d in dn if d not in ("streams", "secrets"))
            for fn in sorted(fns):
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(dp, fn)
                h.update(os.path.relpath(p, root).encode())
                with open(p, "rb") as f:
                    h.update(f.read())
    return h.hexdigest()


class ViewerGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9vgate-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": MACHINE,
                   "S9_REWORK_WATCH": "off"}
        for k in ("S9_SESSION", "S9_USER", "S9_AUTO_RESUME"):
            cls.env.pop(k, None)

        def cli(*argv, user=None, expect=0):
            env = dict(cls.env)
            if user:
                env["S9_USER"] = user
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=env, timeout=20, stdin=subprocess.DEVNULL)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)} (as {user}): "
                                     f"rc={r.returncode}\n{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "root", "--role", "admin")
        cli("user", "add", "alice")
        cli("user", "add", "watcher")
        cli("user", "role", "watcher", "viewer", user="root")
        cli("project", "add", "px", "--name", "PX", "--user", "root")
        cli("project", "member", "px", "add", "watcher", "--role", "viewer",
            "--user", "root")
        r = cli("new", "request", "--title", "doc one", "--summary", "s",
                "--goal", "g", "--project", "px", "--body", "one", user="root")
        cls.doc1 = REQ_RE.search(r.stdout).group(0)
        r = cli("new", "request", "--title", "doc two", "--summary", "s",
                "--goal", "g", "--project", "px", "--body", "two", user="root")
        cls.doc2 = REQ_RE.search(r.stdout).group(0)

        # viewer 신원의 대시보드 서버 — whoami 가 watcher 로 파생된다
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**cls.env, "S9_USER": "watcher"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.root, ignore_errors=True)

    def post(self, path, body):
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"raw": raw}

    def get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=8) as r:
            return r.status, r.read()

    # G2. 클래스 시험 — viewer × 쓰기 서브커맨드 전수: 전부 rc≠0, 문서 무변경
    def test_viewer_gate(self):
        """ViewerGate 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("g2_viewer_write_subcommands_all_denied"):
                # 되돌리기·소거에 실제 대상이 있어야 게이트까지 간다 (대상이 없으면
                # "휴지통에 없다"로 먼저 끝나 무엇이 막았는지 알 수 없다)
                self.cli("rm", self.doc2, "--reason", "fixture", user="root")
                before = _tree_digest(self.root)
                writes = [
                    ("new", "request", "--title", "v", "--summary", "s", "--goal",
                     "g", "--body", "x"),
                    ("status", self.doc1, "in-progress", "--note", "v"),
                    ("note", self.doc1, "viewer note"),
                    ("set", self.doc1, "--title", "renamed by viewer"),
                    ("link", self.doc1, "--relates", self.doc2, "--why", "v"),
                    ("assign", self.doc1, "alice"),
                    ("claim", self.doc1, "--session", "vvvv0000"),
                    ("log", "viewer event", "--session", "vvvv0000"),
                    # --user 로 남을 사칭해도 write_doc 는 환경 신원(S9_USER)을 본다
                    ("note", self.doc1, "spoof", "--user", "root"),
                    ("status", self.doc1, "in-progress", "--user", "root"),
                    # 지우기·되돌리기도 쓰기다 — write_doc 를 지나지 않는 shutil.move
                    # 라 처음엔 이 문 밖에 있었다(실측: viewer 가 rm·purge 를 통과했다)
                    ("rm", self.doc1, "--reason", "x"),
                    ("archive", self.doc1),
                    ("restore", self.doc2),
                    ("purge", "--all", "--yes"),
                    # 계정 등록도 쓰기다 — 이것이 열려 있으면 아래 G10 의 우회가 산다
                    ("user", "add", "newbie"),
                    # 남의 개인 설정 — 값은 settings.json 으로 곧장 가 문서를 지나지
                    # 않는다. 판정은 do_user_config_set 한 곳.
                    ("user", "config", "alice", "pref_x", "hacked"),
                ]
                for argv in writes:
                    r = self.cli(*argv, user="watcher", expect=None)
                    self.assertNotEqual(r.returncode, 0, f"{argv} 가 통과했다:\n{r.stdout}")
                    # assign 은 자기 권한 검사가 먼저 선다 — 거부이기만 하면 된다.
                    # 나머지는 게이트의 문장이 그대로 나와야 한다(트레이스백 금지).
                    # 묶음 처리(rm·archive…)는 건별 사유라 stdout 으로 나간다.
                    if argv[0] != "assign":
                        self.assertIn("관찰 계정", r.stdout + r.stderr, argv)
                    self.assertNotIn("Traceback", r.stderr, argv)
                # 전체 쓰기(tag backfill)도 흔적을 남기지 않는다
                self.cli("tag", "backfill", user="watcher", expect=None)
                self.assertEqual(_tree_digest(self.root), before,
                                 "거부된 쓰기가 문서에 흔적을 남겼다")

            # G3. 조회는 된다
        with self.subTest("g3_viewer_reads_allowed"):
                for argv in (("show", self.doc1), ("ls",), ("search", "doc"),
                             ("digest",), ("user", "role", "watcher")):
                    r = self.cli(*argv, user="watcher", expect=None)
                    self.assertEqual(r.returncode, 0, f"{argv}: {r.stderr}")

            # G4. 클래스 시험 — do_POST 의 라우트를 소스에서 전수 추출해 viewer 서버에
            #     때린다: 본인 pref 설정 하나만 예외, 나머지 전부 403
        with self.subTest("g4_viewer_post_routes_all_denied"):
                with open(S9_SRC, encoding="utf-8") as f:
                    src = f.read()
                i = src.index("def do_POST(self):")
                j = src.index("except WriteDenied", i)
                routes = sorted(set(re.findall(r'parsed\.path == "(/api/[^"]+)"', src[i:j])))
                self.assertGreaterEqual(len(routes), 20, routes)
                for must in ("/api/chat", "/api/wake", "/api/stop", "/api/session/restart",
                             "/api/session/wake", "/api/assign", "/api/status", "/api/note"):
                    self.assertIn(must, routes)
                allowed = {"/api/user/config"}
                before = _tree_digest(self.root)
                payload = {"id": self.doc1, "to": "in-progress", "doc": self.doc1,
                           "text": "hi", "user": "alice", "name": "watcher",
                           "key": "pref_x", "value": "y", "sid": "vvvv0000",
                           "slug": "px", "member": "alice", "role": "member",
                           "ids": [self.doc1], "op": "archive", "all": True}
                for route in routes:
                    if route in allowed:
                        continue
                    st, body = self.post(route, payload)
                    self.assertEqual(st, 403, (route, body))
                    self.assertIn("관찰 계정", body.get("error", ""), route)
                # 사칭 as= 도 viewer 서버에서는 admin 이 아니라 못 쓴다
                st, body = self.post("/api/status", {**payload, "as": "root"})
                self.assertIn(st, (400, 403), body)
                self.assertEqual(_tree_digest(self.root), before,
                                 "거부된 POST 가 문서에 흔적을 남겼다")
                # 허용 예외: 본인 pref 는 저장된다 (profile Notes 의 audit 한 줄이 곧 흔적)
                st, body = self.post("/api/user/config", payload)
                self.assertEqual(st, 200, body)
                # 남의 설정·관찰 범위는 403/400 — 예외가 문이 되지 않는다
                st, _ = self.post("/api/user/config", {**payload, "name": "alice"})
                self.assertEqual(st, 403)
                st, _ = self.post("/api/user/config", {**payload, "key": "observe",
                                                       "value": "all"})
                self.assertEqual(st, 400)

            # G5. GET 은 200
        with self.subTest("g5_viewer_get_allowed"):
                for path in ("/api/whoami", "/api/catalog", "/api/projects"):
                    st, raw = self.get(path)
                    self.assertEqual(st, 200, path)
                st, raw = self.get("/api/whoami")
                self.assertEqual(json.loads(raw).get("role"), "viewer")

            # G8. 옆문 없음 — 게이트를 끄는 환경변수 스위치가 소스에 없다
        with self.subTest("g8_no_side_door"):
            with open(S9_SRC, encoding="utf-8") as f:
                src = f.read()
            self.assertNotRegex(src, r"S9_(SYSTEM|INTERNAL|BYPASS)_?WRITE")
            i = src.index("def _write_gate(")
            j = src.index("def write_doc(", i)
            self.assertNotIn("os.environ", src[i:j], "게이트 안에 환경변수 분기가 있다")

class WriteGateModule(unittest.TestCase):
    """모듈 직접 호출 — G1 (vault 거부) · G6 (profile role 2겹)."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9wgate-")
        env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": MACHINE}
        for k in ("S9_SESSION", "S9_USER"):
            env.pop(k, None)

        def cli(*argv, user=None):
            e = dict(env)
            if user:
                e["S9_USER"] = user
            return subprocess.run([S9, *argv], capture_output=True, text=True,
                                  env=e, timeout=20, stdin=subprocess.DEVNULL)
        cli("init")
        cli("user", "add", "root", "--role", "admin")
        cli("user", "add", "mallory")
        cli("user", "add", "watcher")
        cli("user", "role", "watcher", "viewer", user="root")
        cls.patch = mock.patch.dict(os.environ, {"S9_ROOT": cls.root,
                                                 "S9_MACHINE": MACHINE})
        cls.patch.start()
        os.environ.pop("S9_SESSION", None)
        cls.m = _load("s9_wgate", S9)

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        shutil.rmtree(cls.root, ignore_errors=True)

    def _as(self, user):
        return mock.patch.dict(os.environ, {"S9_USER": user})

    # G1. viewer 의 vault 쓰기는 WriteDenied, 파일도 생기지 않는다
    def test_write_gate_module(self):
        """모듈 직접 호출 — G1 (vault 거부) · G6 (profile role 2겹)."""
        with self.subTest("g1_vault_write_denied_for_viewer"):
                p = os.path.join(self.m.VAULT, "requests", "2026", "09", "REQ-x.md")
                meta = {"id": "REQ-x", "type": "request", "title": "t"}
                with self._as("watcher"):
                    with self.assertRaises(self.m.WriteDenied) as cm:
                        self.m.write_doc(p, meta, "body")
                self.assertIn("관찰 계정", str(cm.exception))
                self.assertTrue(issubclass(self.m.WriteDenied, ValueError))
                self.assertFalse(os.path.exists(p))
                # member 는 그대로 쓴다 (회귀)
                with self._as("mallory"):
                    self.m.write_doc(p, meta, "body")
                self.assertTrue(os.path.exists(p))

            # G6. profile role 변경은 admin 만 — write_doc 층(방어선 2겹)
        with self.subTest("g6_profile_role_change_needs_admin"):
                prof = os.path.join(self.m.USERS, "mallory", "profile.md")
                with open(prof, encoding="utf-8") as f:
                    meta, body = self.m.fm_parse(f.read())
                self.assertEqual(meta.get("role", "member"), "member")
                with self._as("mallory"):
                    with self.assertRaises(self.m.WriteDenied):
                        self.m.write_doc(prof, {**meta, "role": "admin"}, body)
                    # role 이 아닌 필드는 본인이 고친다
                    self.m.write_doc(prof, {**meta, "display": "M"}, body)
                self.assertEqual(self.m.user_role("mallory"), "member")
                with self._as("root"):
                    self.m.write_doc(prof, {**meta, "role": "admin"}, body)
                self.assertEqual(self.m.user_role("mallory"), "admin")
                with self._as("root"):
                    self.m.write_doc(prof, {**meta, "role": "member"}, body)

            # G6b. 부트스트랩 — admin 이 하나도 없으면 첫 admin 을 세울 수 있다
        with self.subTest("g6b_bootstrap_without_admin"):
            root = tempfile.mkdtemp(prefix="s9wboot-")
            try:
                env = {**os.environ, "S9_ROOT": root, "S9_MACHINE": MACHINE}
                env.pop("S9_USER", None)
                subprocess.run([S9, "init"], capture_output=True, env=env)
                subprocess.run([S9, "user", "add", "first"], capture_output=True,
                               env=env, stdin=subprocess.DEVNULL)
                with mock.patch.dict(os.environ, {"S9_ROOT": root, "S9_USER": "first"}):
                    m = _load("s9_wboot", S9)
                    prof = os.path.join(m.USERS, "first", "profile.md")
                    with open(prof, encoding="utf-8") as f:
                        meta, body = m.fm_parse(f.read())
                    m.write_doc(prof, {**meta, "role": "admin"}, body)
                    self.assertEqual(m.user_role("first"), "admin")
            finally:
                shutil.rmtree(root, ignore_errors=True)

class RegistrationEscalation(unittest.TestCase):
    """G10. 계정 등록으로 게이트를 통째로 우회하지 못한다.

    실측으로 재현된 구멍이었다: `do_user_add` 가 raw `open(...,"w")` 로
    profile.md 를 써서 `_write_gate` 를 지나지 않았고, 그래서 **관찰 계정이든
    member 든** `s9 user add x --role admin` 한 줄로 admin 을 하나 세운 뒤
    `S9_USER=x` 로 무엇이든 쓸 수 있었다. role 변경만 막는 방어선(G6)은
    role '생성'을 안 보고 있었다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9reg-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": MACHINE}
        for k in ("S9_SESSION", "S9_USER"):
            self.env.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def cli(self, *argv, user=None):
        env = dict(self.env)
        if user:
            env["S9_USER"] = user
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=env, timeout=20, stdin=subprocess.DEVNULL)

    def role_of(self, name):
        return self.cli("user", "role", name, user="root").stdout.strip()

    def test_g10_registration_cannot_mint_admin(self):
        self.cli("init")
        # 부트스트랩: admin 이 하나도 없으면 첫 admin 을 세울 수 있다
        self.assertEqual(self.cli("user", "add", "root", "--role", "admin")
                         .returncode, 0)
        self.assertIn("admin", self.role_of("root"))
        self.cli("user", "add", "alice")
        self.cli("user", "add", "watcher")
        self.cli("user", "role", "watcher", "viewer", user="root")
        # admin 이 선 뒤로는 admin 을 세우는 것도 admin 만
        for who in ("alice", "watcher", None):
            r = self.cli("user", "add", f"evil_{who}", "--role", "admin",
                         user=who)
            self.assertNotEqual(r.returncode, 0, (who, r.stdout))
            self.assertFalse(os.path.isdir(
                os.path.join(self.root, "users", f"evil_{who}")),
                f"{who} 의 admin 등록이 폴더를 남겼다")
        # 관찰 계정은 member 등록조차 못 한다 (등록도 쓰기다)
        r = self.cli("user", "add", "ghost", user="watcher")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("관찰 계정", r.stderr)
        # member 의 평범한 등록과 admin 의 admin 등록은 그대로 (회귀)
        self.assertEqual(self.cli("user", "add", "ok1", user="alice")
                         .returncode, 0)
        self.assertEqual(self.cli("user", "add", "ok2", "--role", "admin",
                                  user="root").returncode, 0)
        self.assertIn("admin", self.role_of("ok2"))
        # 등록 문서의 모양은 그대로 — 단일 경계(write_doc)를 지나도 사람이
        # 읽던 파일과 같아야 한다
        with open(os.path.join(self.root, "users", "ok2", "profile.md"),
                  encoding="utf-8") as f:
            txt = f.read()
        self.assertTrue(txt.startswith("---\nname: ok2\nrole: admin\n"), txt[:80])
        self.assertIn("\n---\n", txt)
        self.assertIn("## Notes", txt)
        self.assertIn("os_accounts: [", txt)


class HookViewerSession(unittest.TestCase):
    """G7. viewer 세션의 UserPromptSubmit 훅 — 자동 기록도 정정 유도도 없다."""

    @classmethod
    def setUpClass(cls):
        os.environ.pop("S9_AUTO_RESUME", None)
        cls.hook = _load("s9_audit_prompt_viewer", HOOK)

    def _run_hook(self, prompt, role):
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            if argv[:2] == ("user", "current"):
                return mock.Mock(returncode=0, stdout="watcher  [source: $S9_USER]")
            if argv[:2] == ("user", "role"):
                return mock.Mock(returncode=0, stdout=f"watcher: role = {role}\n")
            if argv[0] == "new":
                return mock.Mock(returncode=0, stdout="REQ-20260902-999-zzzz\n")
            return mock.Mock(returncode=0, stdout="")
        payload = json.dumps({"prompt": prompt, "session_id": "vvvv000011"})
        with mock.patch.object(self.hook, "run", fake_run), \
             mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.hook.main()
        return calls, out.getvalue()

    def test_g7_viewer_no_records_no_correction_nudge(self):
        for prompt in ("logout",                      # fragment
                       "멤버 역할은 어디서 바꾸나요",  # question
                       "로그인 고쳐"):                # request
            calls, printed = self._run_hook(prompt, "viewer")
            self.assertFalse(any(a[0] in ("new", "log") for a in calls),
                             (prompt, calls))
            self.assertIn("additionalContext", printed)
            self.assertIn("관찰 계정", printed)
            self.assertNotIn("s9 new request", printed, prompt)
            self.assertNotIn("s9 new question", printed, prompt)
            # 문구가 "현재 시각" 에서 바뀌었다 — 훅이 넣는 값은 프롬프트가 **도착한**
            # 때이지 지금이 아니고, 그 둘을 같은 말로 부르면 모델이 지어낸 시각을
            # 적게 된다(REQ-20260903-013). 계약은 「시각 도장이 실린다」이므로
            # 지금 그 도장이 쓰는 말로 본다.
            self.assertIn("도착한 시각", printed)   # 시각 도장은 예외 없다

    def test_g7b_member_session_unchanged(self):
        calls, printed = self._run_hook("logout", "member")
        self.assertTrue(any(a[0] == "log" for a in calls), calls)
        self.assertIn("s9 new request", printed)


if __name__ == "__main__":
    unittest.main()
