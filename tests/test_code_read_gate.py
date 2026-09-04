"""저장소 소스를 화면에 내주는 문 (REQ-20260828-028-62x6, 서버측).

`/api/asset` 은 **문서 첨부** 전용이고 판정은 `doc_visible` 이다. 코드 파일에는
대응하는 판정이 없었고, 그 자리에 새 문을 내는 것이 이 요청이다. security-engineer
판정(문서의 decision 노트)의 결론은 하나다 — **허용목록이되 허용하는 것은 "주인이
없는 디렉터리" 다섯뿐**이다: `bin/ docs/ harness/ tests/ web/` + 최상위
`README.md·CLAUDE.md·pyproject.toml`.

이 파일이 지키는 것은 기능이 아니라 **그 목록**이다. 특히 `test_g*` 의 클래스 단위
시험 — `git ls-files` 전수를 돌려 허용 뿌리 밖의 추적 파일이 하나도 열리지 않음을
확인한다. 누가 `CODE_ROOTS` 에 한 줄 더하면 여기가 즉시 빨개진다. 허용목록이
조용히 넓어지는 것을 막는 유일한 장치다.

왜 "git 추적 파일만" 이 아닌가: 이 저장소는 `vault/**`(약 900개)·
`state/sessions/*.json`(당시 91개 — 2026-09-02 track 해제, REQ-20260902-026)·
`users/*/config/settings.json` 을 **추적한다**.
그 규칙을 쓰면 `doc_visible`·`stream_visible` 이 통째로 무효가 되고, 어제
REQ-20260828-012 가 정한 "비밀은 값도 경로도 주지 않는다" 가 그 자리에서 뒤집힌다.

격리: S9_ROOT=mktemp — 라이브 vault를 건드리지 않는다. 클래스 단위 시험만
실저장소를 읽는다(읽기 전용).
실행: python3 tests/ code_read
"""
import http.client
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
MACHINE = "TESTMACH"

from portpool import free_port, wait_server  # noqa: E402


def _load_s9(root=None):
    """bin/s9 를 모듈로 읽는다. root=None 이면 실저장소(ROOT 기본값)."""
    old = os.environ.get("S9_ROOT")
    if root is None:
        os.environ.pop("S9_ROOT", None)
    else:
        os.environ["S9_ROOT"] = root
    try:
        name = "s9codegate" + (root or "repo").replace(os.sep, "_")[-24:]
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old


def _req(port, path, host_header=None, tries=14):
    """(status, body_bytes) — Host 헤더를 직접 통제해야 해서 http.client 를 쓴다."""
    delay, last = 0.2, None
    for _ in range(tries):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
            try:
                if host_header is None:
                    c.putrequest("GET", path)
                else:
                    c.putrequest("GET", path, skip_host=True)
                    c.putheader("Host", host_header)
                c.endheaders()
                r = c.getresponse()
                return r.status, r.read()
            finally:
                c.close()
        except (ConnectionError, OSError) as e:
            last = e
            time.sleep(delay)
            delay = min(delay * 1.7, 2.0)
    raise last


class CodeReadGate(unittest.TestCase):
    """실제로 띄운 서버에 물어보는 시험 — 소스 문자열 검사가 아니다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9code-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": MACHINE,
                   "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off",
                   "S9_SYNC": "off", "S9_USER": "boss"}
        for k in ("S9_SESSION", "S9_CODE_READ"):
            cls.env.pop(k, None)

        def cli(*argv, expect=0):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=30)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "boss", "--role", "admin")
        r = cli("new", "request", "--title", "code gate doc",
                "--summary", "s", "--goal", "g", "--body", "zebra-body")
        cls.doc_id = re.search(
            r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?", r.stdout).group(0)

        def w(rel, text, mode="w"):
            p = os.path.join(cls.tmp, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, mode, **({} if "b" in mode else
                                 {"encoding": "utf-8"})) as f:
                f.write(text)
            return p

        # 허용 뿌리 — 내줘야 하는 것
        w("web/index.html", "".join(f"line {i}\n" for i in range(1, 501)))
        w("bin/s9", "".join(f"src {i}\n" for i in range(1, 201)))
        w("docs/guide.md", "# guide\n" * 40)
        w("README.md", "readme\n" * 10)
        w("tests/test_x.py", "x\n" * 10)
        w("harness/h.md", "h\n" * 10)
        # 한 줄 400자 절단 확인용
        w("docs/long.md", "A" * 900 + "\n")

        # 막아야 하는 것 — 전부 실제로 디스크에 만든다
        w("users/boss/config/settings.json",
          json.dumps({"external_secrets_path": "/home/x/s9-secrets"}))
        w("users/boss/secrets/token.txt", "sk-SECRET-VALUE")
        w("state/sessions/TESTMACH__abcd1234.json",
          json.dumps({"user": "boss", "transcript_path": "/abs/path.jsonl"}))
        w(".claude/settings.json", json.dumps({"permissions": {}}))
        w(".git/config", "[core]\n")
        w("index/catalog.jsonl", '{"id":"X"}\n')
        w("projects/p/CONTEXT.md", "ctx\n")

        # 4MB 초과 — 허용 뿌리 안이지만 상한이 막는다
        w("docs/huge.md", "z" * (4 * 1024 * 1024 + 10))
        # 이진 — 허용 뿌리 안·허용 확장자지만 NUL 이 막는다
        w("docs/bin.txt", b"PNG\x00\x01\x02binary", mode="wb")

        # 심링크 탈출 (테스트가 만들고 tearDown 이 지운다)
        cls.link = os.path.join(cls.tmp, "web", "_t.html")
        os.symlink(os.path.join("..", "users", "boss", "config",
                                "settings.json"), cls.link)

        cls.vault_doc = None
        for base, _d, files in os.walk(os.path.join(cls.tmp, "vault")):
            for fn in files:
                if fn.endswith(".md"):
                    cls.vault_doc = os.path.relpath(
                        os.path.join(base, fn), cls.tmp).replace(os.sep, "/")
                    break
            if cls.vault_doc:
                break
        assert cls.vault_doc, "vault 문서가 없다 — 픽스처가 틀렸다"

        cls.port = free_port()          # 127.0.0.1 바인드 (기본)
        cls.port_open = free_port()     # 0.0.0.0 바인드 (전제가 깨진 자리)
        cls.srvs = []
        for port, host in ((cls.port, "127.0.0.1"), (cls.port_open, "0.0.0.0")):
            cls.srvs.append(subprocess.Popen(
                [S9, "serve", "--host", host, "--port", str(port)],
                env=cls.env, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL))
        for port in (cls.port, cls.port_open):
            wait_server(port)

    @classmethod
    def tearDownClass(cls):
        for p in cls.srvs:
            p.terminate()
        for p in cls.srvs:
            p.wait(timeout=5)
        if os.path.islink(cls.link):
            os.unlink(cls.link)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def code(self, port=None, **params):
        import urllib.parse
        q = urllib.parse.urlencode(params)
        return _req(port or self.port, f"/api/code?{q}")

    # ── S1·S2. 열린다 ────────────────────────────────────────────────
    def test_a1_opens_a_window_around_the_line(self):
        """S1. 그 줄 언저리만 낸다 — 파일 전체가 아니다."""
        st, body = self.code(path="web/index.html", line=250, ctx=12)
        self.assertEqual(st, 200, body)
        d = json.loads(body)
        self.assertEqual(d["from"], 238)
        self.assertEqual(d["to"], 262)
        self.assertEqual(d["total"], 500)
        self.assertEqual(len(d["lines"]), 25)
        self.assertEqual(d["lines"][0], "line 238")
        self.assertEqual(d["lines"][12], "line 250")
        # 돌려주는 path 는 입력 글자가 아니라 정규화된 실경로다
        self.assertEqual(d["path"], "web/index.html")

    def test_a2_extensionless_bin_s9_opens(self):
        """S2. `bin/s9` — 확장자가 없어도 열린다 (bin/ 바로 밑에서만)."""
        st, body = self.code(path="bin/s9", line=100, ctx=3)
        self.assertEqual(st, 200, body)
        d = json.loads(body)
        self.assertEqual(d["lines"][3], "src 100")

    def test_a3_no_line_gives_the_head(self):
        """line 없이 부르면 머리부터 — 화면이 늘 line 을 아는 것은 아니다."""
        st, body = self.code(path="docs/guide.md")
        self.assertEqual(st, 200, body)
        self.assertEqual(json.loads(body)["from"], 1)

    # ── S3. 막힌다, 그리고 바이트까지 같다 ────────────────────────────
    BLOCKED = [
        "users/boss/config/settings.json",
        "users/boss/secrets/token.txt",
        "state/sessions/TESTMACH__abcd1234.json",
        "index/catalog.jsonl",
        ".claude/settings.json",
        ".git/config",
        "projects/p/CONTEXT.md",
        "bin/../users/boss/config/settings.json",
        "../../../etc/passwd",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "bin\\..\\users\\boss\\config\\settings.json",
        "web/",
        "web//index.html",
        "./web/index.html",
        "bin/sub/s9",              # 확장자 없는 것은 bin/ 바로 밑에서만
        "docs/x.exe",              # 확장자 허용목록 밖
        "web/_t.html",             # 심링크 탈출 (S4)
        "docs/huge.md",            # 4MB 상한 (S5)
        "docs/bin.txt",            # 이진 (S6)
    ]

    def test_b1_everything_that_must_be_blocked_is(self):
        """S3~S6. 막을 것이 전부 404 다."""
        for rel in self.BLOCKED:
            with self.subTest(rel=rel):
                st, _b = self.code(path=rel)
                self.assertEqual(st, 404, f"열렸다: {rel}")
        st, _b = self.code(path=self.vault_doc)
        self.assertEqual(st, 404, f"vault 문서가 열렸다: {self.vault_doc}")

    def test_b2_blocked_absent_and_binary_are_byte_identical(self):
        """S3. 막힘·부재·이진의 응답이 **바이트까지** 같다.

        갈라 놓으면 그 차이가 곧 목록이 된다 — 내용을 막아도 존재가 새면
        막은 것이 아니다. `/api/asset-text` 가 지키는 규율 그대로.
        """
        ref = self.code(path="docs/이런건없다.md")          # 진짜 부재
        self.assertEqual(ref[0], 404)
        for rel in self.BLOCKED + [self.vault_doc, ""]:
            with self.subTest(rel=rel):
                self.assertEqual(self.code(path=rel), ref,
                                 f"응답이 부재와 다르다: {rel}")

    def test_b3_symlink_escape_dies(self):
        """S4. `web/_t.html -> ../users/*/config/settings.json` 이 새지 않는다.

        글자 검사는 심링크를 모른다 — realpath 뒤에 같은 모양 검사를 한 번 더
        돌려야 죽는다. 여기서 처음 필요해진 방어다.
        """
        self.assertTrue(os.path.islink(self.link))
        st, body = self.code(path="web/_t.html")
        self.assertEqual(st, 404)
        self.assertNotIn(b"secrets", body)

    def test_b4_static_html_route_does_not_leak_the_same_symlink(self):
        """S11. 같은 심링크를 `/_t.html` 정적 라우트가 내주면 옆문이다.

        `/api/code` 만 막고 그 옆의 정적 라우트가 열려 있으면 막은 것이 아니다.
        """
        st, body = _req(self.port, "/_t.html")
        self.assertEqual(st, 404, body[:200])
        self.assertNotIn(b"external_secrets_path", body)

    # ── S5. 상한 ─────────────────────────────────────────────────────
    def test_c1_window_is_capped(self):
        """S5. `ctx` 를 아무리 크게 줘도 창이 무한히 커지지 않는다."""
        st, body = self.code(path="web/index.html", line=250, ctx=100000)
        self.assertEqual(st, 200, body)
        d = json.loads(body)
        self.assertLessEqual(len(d["lines"]), 400)

    def test_c2_one_line_is_truncated(self):
        """S5. 한 줄이 아무리 길어도 400자에서 자른다."""
        st, body = self.code(path="docs/long.md")
        self.assertEqual(st, 200, body)
        self.assertEqual(len(json.loads(body)["lines"][0]), 400)

    # ── S8. 루프백 전제 ──────────────────────────────────────────────
    def test_d1_open_bind_serves_no_code(self):
        """S8. `--host 0.0.0.0` 서버는 소스를 내주지 않는다.

        whoami 가 "브라우저 사용자 = 서버 기동 계정" 을 파생으로 쓴다. 그 전제가
        깨진 자리에서 조용히 동작하는 것이 가장 나쁜 경우다.
        """
        st, _b = self.code(path="web/index.html", line=10, port=self.port_open)
        self.assertEqual(st, 404)

    def test_d2_open_bind_still_serves_docs(self):
        """S8. 같은 서버에서 `/api/doc` 은 그대로 — 기존 경로를 깨지 않았다."""
        st, body = _req(self.port_open, f"/api/doc?id={self.doc_id}")
        self.assertEqual(st, 200, body[:200])
        self.assertIn("zebra-body", json.loads(body)["body"])

    # ── S10. Host 검증 (별건 판단분) ─────────────────────────────────
    def test_e1_loopback_bind_rejects_foreign_host_header(self):
        """S10. 루프백 바인드 서버는 남의 이름으로 온 요청을 거부한다.

        DNS 리바인딩: 사용자가 방문한 아무 페이지나 `evil.example.com` 을
        127.0.0.1 로 재해석시켜 same-origin 으로 `/api/*` 를 읽는다. 뷰어는
        서버 기동 계정이다.
        """
        for path in ("/api/code?path=web/index.html&line=10",
                     f"/api/doc?id={self.doc_id}",
                     "/api/catalog", "/"):
            with self.subTest(path=path):
                st, _b = _req(self.port, path, host_header="evil.example.com")
                self.assertNotEqual(st, 200, f"남의 Host 로 열렸다: {path}")

    def test_e2_loopback_host_headers_pass(self):
        """S10. 실제로 쓰는 Host 값들은 전부 통과한다 — 화면을 깨지 않는다."""
        for h in (f"127.0.0.1:{self.port}", f"localhost:{self.port}",
                  f"[::1]:{self.port}", "127.0.0.1", "localhost"):
            with self.subTest(host=h):
                st, _b = _req(self.port, f"/api/doc?id={self.doc_id}",
                              host_header=h)
                self.assertEqual(st, 200, f"Host {h} 가 막혔다")

    def test_e3_open_bind_accepts_any_host(self):
        """S10. `--host 0.0.0.0` 은 운영자가 원격 접속을 연 것이다 — 안 깬다.

        리바인딩 방어는 **루프백 바인드일 때만** 건다. 여기서까지 걸면
        `--host` 로 띄운 원격 접속이 통째로 죽는다.
        """
        st, _b = _req(self.port_open, f"/api/doc?id={self.doc_id}",
                      host_header="my-box.local:9909")
        self.assertEqual(st, 200)


class CodeVisibleFunction(unittest.TestCase):
    """판정 함수 자체 — 서버 없이 부른다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load_s9()                  # 실저장소 ROOT

    def test_f1_it_lives_next_to_doc_visible(self):
        """판정 자리는 `doc_visible` 바로 위, 형제로.

        떨어져 있으면 다음에 읽는 사람이 세 번째 게이트를 발명한다.
        """
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        i_code = src.find("\ndef code_visible(")
        i_doc = src.find("\ndef doc_visible(")
        self.assertGreater(i_code, 0, "code_visible 이 없다")
        self.assertGreater(i_doc, i_code, "code_visible 이 doc_visible 위가 아니다")
        between = src[i_code:i_doc]
        self.assertLess(between.count("\ndef "), 5,
                        "code_visible 과 doc_visible 사이가 너무 멀다")

    def test_g1_no_tracked_file_outside_the_roots_opens(self):
        """S7. **클래스 단위** — `git ls-files` 전수.

        허용 뿌리 5개 + 최상위 파일 3개 밖의 추적 파일이 하나라도 열리면 실패다.
        누가 `CODE_ROOTS` 에 한 줄 더하면 여기가 즉시 빨개진다 — 허용목록이
        조용히 넓어지는 것을 막는 유일한 장치다.
        """
        out = subprocess.run(["git", "-C", REPO, "ls-files", "-z"],
                             capture_output=True, text=True, timeout=60)
        files = [p for p in out.stdout.split("\0") if p]
        self.assertGreater(len(files), 500, "git ls-files 가 비었다 — 시험이 헛돈다")
        roots = set(self.m.CODE_ROOTS)
        tops = set(self.m.CODE_FILES)
        leaked, outside = [], 0
        for rel in files:
            head = rel.split("/")[0]
            if (head in roots and "/" in rel) or rel in tops:
                continue
            outside += 1
            if self.m.code_visible(rel):
                leaked.append(rel)
        self.assertGreater(outside, 500,
                           "허용 뿌리 밖 추적 파일이 너무 적다 — 뿌리가 넓어졌나")
        self.assertEqual(leaked[:20], [],
                         f"허용 뿌리 밖 추적 파일 {len(leaked)}개가 열린다")

    def test_g2_the_roots_are_the_five(self):
        """뿌리가 다섯이라는 사실 자체를 못 박는다 — 늘리려면 여기를 고쳐야 한다."""
        self.assertEqual(tuple(self.m.CODE_ROOTS),
                         ("bin", "docs", "harness", "tests", "web"))
        self.assertEqual(set(self.m.CODE_FILES),
                         {"CLAUDE.md", "README.md", "pyproject.toml"})

    def test_g3_allowed_files_do_open(self):
        """막기만 하고 안 열리면 기능이 아니다."""
        for rel in ("README.md", "bin/s9", "web/index.html",
                    "tests/test_code_read_gate.py"):
            with self.subTest(rel=rel):
                self.assertTrue(self.m.code_visible(rel), rel)

    def test_h1_instance_switch_closes_the_door(self):
        """S9. `S9_CODE_READ=off` 면 열리던 것도 닫힌다 (인스턴스 스위치).

        사용자별 등급은 두지 않는다 — 등급을 두면 "코드에 주인이 없다" 는 이
        판정의 전제가 흐려지고, 그 순간 `vault/` 를 뿌리에 넣자는 말이
        논리적으로 가능해진다.
        """
        self.assertTrue(self.m.code_visible("README.md"))
        os.environ["S9_CODE_READ"] = "off"
        try:
            self.assertEqual(self.m.code_visible("README.md"), "")
        finally:
            os.environ.pop("S9_CODE_READ", None)
        self.assertTrue(self.m.code_visible("README.md"))


if __name__ == "__main__":
    unittest.main()
