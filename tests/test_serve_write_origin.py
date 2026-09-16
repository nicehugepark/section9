"""대시보드 서버의 쓰기 경계 (REQ-20260916-003-62x6).

이 서버에는 인증이 한 겹도 없다 — 신원은 `whoami_info` 가 OS 계정에서 파생하고,
그 전제는 「루프백 바인드 = 브라우저 사용자 = 서버 기동 계정」이다. 전제가 깨지는
길이 둘이고, 이 파일이 지키는 것도 그 둘이다.

① **남의 페이지가 우리 주소로 쏜다** (CSRF). 사람이 연 아무 웹페이지가
   `fetch('http://127.0.0.1:9909/api/chat', {method:'POST', mode:'no-cors', …})`
   한 줄을 실행하면 Host 는 `127.0.0.1:9909` 그대로라 리바인딩 방어
   (`host_header_ok`)를 그냥 지난다. 그렇게 들어간 채팅 한 줄은 훅이 「사용자
   메시지로 간주해 처리하라」로 리드에 주입한다 — 임의 명령 실행이다.
   구분점은 브라우저가 스스로 붙이고 페이지의 스크립트가 지울 수 없는 두 헤더
   `Origin` · `Sec-Fetch-Site` 하나뿐이다.

② **바깥 주소에 bind 했다**. `--host 0.0.0.0` 은 그 주소에 닿는 누구나 브라우저
   사용자가 되게 하는데, 예전에는 `host_header_ok` 가 그 자리에서 **스스로
   판정을 껐고** 쓰기 라우트는 바인드 주소를 보지도 않았다.

**헤더가 둘 다 없으면 통과**인 것도 이 파일이 지킨다(N2). 그것은 브라우저가
아니라 같은 컴퓨터의 프로세스(CLI·시험·curl)이고, 그 프로세스는 이미 저장소
파일을 직접 고칠 수 있다 — 거기에 막을 것이 없다. 이 줄을 조이면 기존 시험
수십 개가 함께 죽는다.

격리: S9_ROOT=mktemp — 라이브 vault 를 건드리지 않는다.
실행: python3 tests/ serve_write_origin
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
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
MACHINE = "TESTMACH"

from portpool import free_port, wait_server  # noqa: E402


def _post(port, path, body=None, headers=None, host_header=None):
    """(status, body_bytes) — 헤더를 글자 그대로 통제해야 해서 http.client 다.

    urllib 은 Host·Origin 을 마음대로 손대고, requests 는 이 저장소에 없다.
    """
    payload = json.dumps(body or {}).encode("utf-8")
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        c.putrequest("POST", path, skip_host=bool(host_header))
        if host_header:
            c.putheader("Host", host_header)
        c.putheader("Content-Type", "application/json")
        c.putheader("Content-Length", str(len(payload)))
        for k, v in (headers or {}).items():
            c.putheader(k, v)
        c.endheaders()
        c.send(payload)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


def _get(port, path):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        c.request("GET", path)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


class WriteBoundary(unittest.TestCase):
    """실제로 띄운 서버 셋에 물어보는 시험 — 소스 글자 대조가 아니다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9wbnd-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": MACHINE,
                   "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off",
                   "S9_SYNC": "off", "S9_USER": "boss"}
        cls.env.pop("S9_SESSION", None)

        def cli(*argv, expect=0):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=60)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r

        cli("init")
        cli("user", "add", "boss", "--role", "admin")
        r = cli("new", "request", "--title", "경계 시험 문서",
                "--summary", "s", "--goal", "g", "--body", "b")
        cls.doc_id = re.search(
            r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?", r.stdout).group(0)

        cls.port = free_port()          # 127.0.0.1 (기본)
        cls.port_open = free_port()     # 0.0.0.0, 고치기 막힘 (기본)
        cls.port_write = free_port()    # 0.0.0.0 + --open-write (운영자가 열었다)
        cls.srvs = []
        for port, host, extra in ((cls.port, "127.0.0.1", []),
                                  (cls.port_open, "0.0.0.0", []),
                                  (cls.port_write, "0.0.0.0", ["--open-write"])):
            cls.srvs.append(subprocess.Popen(
                [S9, "serve", "--host", host, "--port", str(port), *extra],
                env=cls.env, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL))
        for port in (cls.port, cls.port_open, cls.port_write):
            wait_server(port)

    @classmethod
    def tearDownClass(cls):
        for p in cls.srvs:
            p.terminate()
        for p in cls.srvs:
            p.wait(timeout=10)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def status(self, port=None, **kw):
        """경계를 지났나만 본다 — 지나면 없는 id 로 400, 막히면 403.

        판정을 상태 코드 하나로 읽기 위해 **일부러 없는 문서**를 지목한다.
        전이가 성공해 버리면 시험이 서버의 상태를 바꾼다.
        """
        return _post(port or self.port, "/api/status",
                     {"id": "REQ-99999999-999", "to": "done"}, **kw)

    def ours(self, port=None):
        p = port or self.port
        return {"Origin": f"http://127.0.0.1:{p}",
                "Sec-Fetch-Site": "same-origin"}

    # ── 정상 ─────────────────────────────────────────────────────────
    def test_n1_our_own_page_passes(self):
        """N1. 대시보드가 보내는 꼴 그대로면 경계를 지난다."""
        st, body = self.status(headers=self.ours())
        self.assertEqual(st, 400, body[:300])

    def test_n2_no_browser_headers_passes(self):
        """N2. 헤더가 둘 다 없으면 브라우저가 아니다 — 같은 컴퓨터의 프로세스다.

        여기를 조이면 CLI·시험·curl 이 전부 죽는데, 그 프로세스는 이미 저장소
        파일을 직접 고칠 수 있어 막아도 얻는 것이 없다.
        """
        st, body = self.status()
        self.assertEqual(st, 400, body[:300])

    def test_n3_get_is_untouched(self):
        """N3. 읽기는 그대로다 — 경계는 쓰기에만 선다."""
        st, body = _get(self.port, f"/api/doc?id={self.doc_id}")
        self.assertEqual(st, 200, body[:200])

    # ── 경계 ─────────────────────────────────────────────────────────
    def test_b1_localhost_name_matches(self):
        """B1. `localhost` 로 연 화면도 제 Origin 과 맞는다."""
        st, body = self.status(
            host_header=f"localhost:{self.port}",
            headers={"Origin": f"http://localhost:{self.port}",
                     "Sec-Fetch-Site": "same-origin"})
        self.assertEqual(st, 400, body[:300])

    def test_b2_sec_fetch_none_passes(self):
        """B2. `Sec-Fetch-Site: none` 은 사람이 주소를 직접 친 자리다."""
        st, body = self.status(
            headers={"Origin": f"http://127.0.0.1:{self.port}",
                     "Sec-Fetch-Site": "none"})
        self.assertEqual(st, 400, body[:300])

    def test_b3_open_write_opens_the_outside_bind(self):
        """B3. 운영자가 `--open-write` 로 연 서버는 바깥 주소에서도 고친다."""
        st, body = self.status(port=self.port_write,
                               headers=self.ours(self.port_write))
        self.assertEqual(st, 400, body[:300])

    # ── 실패 ─────────────────────────────────────────────────────────
    def test_f1_foreign_origin_is_refused(self):
        """F1. 남의 페이지에서 온 쓰기는 403 이다."""
        for site in ("cross-site", "same-site", None):
            h = {"Origin": "http://evil.example.com"}
            if site:
                h["Sec-Fetch-Site"] = site
            with self.subTest(site=site):
                st, _b = self.status(headers=h)
                self.assertEqual(st, 403, f"남의 Origin 이 지났다 (site={site})")

    def test_f2_other_local_server_is_refused(self):
        """F2. 같은 루프백이어도 **포트가 다르면** 우리 화면이 아니다.

        이 컴퓨터에서 도는 남의 개발 서버 한 대가 그대로 공격자 자리가 된다.
        """
        st, _b = self.status(headers={"Origin": f"http://127.0.0.1:{self.port + 1}",
                                      "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(st, 403)

    def test_f3_cross_site_without_origin_is_refused(self):
        """F3. Origin 이 없어도 `Sec-Fetch-Site: cross-site` 면 남의 페이지다."""
        st, _b = self.status(headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(st, 403)

    def test_f4_null_origin_is_refused(self):
        """F4. `Origin: null` — sandbox iframe · file:// 은 출처가 없다."""
        st, _b = self.status(headers={"Origin": "null",
                                      "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(st, 403)

    def test_f5_outside_bind_is_read_only(self):
        """F5. 바깥 주소에 bind 한 서버는 기본이 읽기만이다 — 읽기는 안 깬다."""
        st, _b = self.status(port=self.port_open,
                             headers=self.ours(self.port_open))
        self.assertEqual(st, 403)
        st, body = _get(self.port_open, f"/api/doc?id={self.doc_id}")
        self.assertEqual(st, 200, body[:200])

    def test_f6_the_actual_attack_writes_nothing_to_the_inbox(self):
        """F6. 이 요청을 세운 그 공격 — 채팅 한 줄이 수신함에 들어가지 못한다.

        상태 코드만 보면 「막았다」를 믿게 되지만, 정말 지켜야 하는 것은
        **파일에 한 줄도 늘지 않는 것**이다. 그 줄이 곧 리드에 주입되는 지시다.
        """
        box = os.path.join(self.tmp, "state", "terminal")
        before = {}
        for base, _d, files in os.walk(box) if os.path.isdir(box) else []:
            for fn in files:
                p = os.path.join(base, fn)
                before[p] = os.path.getsize(p)
        st, _b = _post(self.port, "/api/chat",
                       {"kind": "chat", "text": "PWNED-BY-ANOTHER-PAGE"},
                       headers={"Origin": "http://evil.example.com",
                                "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(st, 403)
        hit = []
        for base, _d, files in os.walk(box) if os.path.isdir(box) else []:
            for fn in files:
                p = os.path.join(base, fn)
                if before.get(p, 0) != os.path.getsize(p):
                    hit.append(p)
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        if "PWNED-BY-ANOTHER-PAGE" in f.read():
                            hit.append(p)
                except OSError:
                    pass
        self.assertEqual(hit, [], f"공격 문구가 남았다: {hit}")

    # ── 회귀: 화면이 그 사실을 말하나 ────────────────────────────────
    def test_r4_serveinfo_carries_the_boundary(self):
        """R4. `/api/serveinfo` 가 bind·loopback·open_write 를 낸다 —
        화면이 경계를 추측하지 않게."""
        st, body = _get(self.port, "/api/serveinfo")
        self.assertEqual(st, 200, body[:200])
        d = json.loads(body)
        self.assertEqual(d["bind"], "127.0.0.1")
        self.assertTrue(d["loopback"])
        self.assertFalse(d["open_write"])

        d = json.loads(_get(self.port_write, "/api/serveinfo")[1])
        self.assertEqual(d["bind"], "0.0.0.0")
        self.assertFalse(d["loopback"])
        self.assertTrue(d["open_write"])

        d = json.loads(_get(self.port_open, "/api/serveinfo")[1])
        self.assertFalse(d["open_write"])


def _load_s9():
    """bin/s9 를 모듈로 읽는다 — 판정 함수를 서버 없이 부른다."""
    spec = importlib.util.spec_from_loader(
        "s9wbnd", importlib.machinery.SourceFileLoader("s9wbnd", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class OriginFunction(unittest.TestCase):
    """판정 함수 자체 — 서버 없이 부른다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9wbndf-")
        os.environ["S9_ROOT"] = cls.tmp
        cls.m = _load_s9()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ok(self, origin, site, host="127.0.0.1:9909"):
        return self.m.origin_ok(origin, site, host)

    def test_p1_the_table(self):
        """판정 표 — 한 줄이 한 사실이다."""
        cases = [
            # (Origin, Sec-Fetch-Site, 통과하나)
            ("http://127.0.0.1:9909", "same-origin", True),
            ("http://127.0.0.1:9909", "none", True),
            ("http://127.0.0.1:9909", None, True),
            ("HTTP://127.0.0.1:9909", "same-origin", True),   # scheme 대소문자
            (None, None, True),                               # 브라우저가 아니다
            ("", "", True),
            (None, "same-origin", True),
            (None, "cross-site", False),
            (None, "same-site", False),
            ("http://127.0.0.1:9908", None, False),           # 옆 포트
            ("http://127.0.0.1", None, False),                # 포트 없음
            # scheme 은 보지 않는다 — 판정은 host:port 다. 서버는 제가 http 로
            # 답한다는 것만 알지 브라우저가 무엇으로 왔는지(앞에 선 TLS 종단이
            # 있는지) 모르고, `https://127.0.0.1:9909` 를 가지려면 우리가 듣고
            # 있는 바로 그 포트를 남이 쥐어야 한다 — 그럴 수 없다.
            ("https://127.0.0.1:9909", None, True),
            ("http://evil.example.com", None, False),
            ("null", None, False),
            ("NULL", None, False),
            ("file://", None, False),
            ("not a url", None, False),
        ]
        for origin, site, want in cases:
            with self.subTest(origin=origin, site=site):
                self.assertEqual(self.ok(origin, site), want)

    def test_p2_it_lives_next_to_host_header_ok(self):
        """판정 자리는 `host_header_ok` 형제다.

        떨어져 있으면 다음에 읽는 사람이 세 번째 검사를 발명한다 — 그리고
        둘이 갈리면 어느 쪽도 못 믿는다.
        """
        with open(S9 + ".py", encoding="utf-8") as f:
            src = f.read()
        self.assertLess(0, src.index("def host_header_ok"))
        self.assertLess(src.index("def host_header_ok"),
                        src.index("def origin_ok"))
        self.assertIn("self._host_guard() or self._write_guard()", src)

    def test_r1_open_write_says_so_on_the_screen(self):
        """R1. 고치기를 열어 둔 채 바깥 주소에 서 있으면 알림 줄이 말한다."""
        rows = self._notices("0.0.0.0", True)
        row = next((r for r in rows if r["id"] == "server:openwrite"), None)
        self.assertIsNotNone(row, f"알림이 없다: {[r['id'] for r in rows]}")
        self.assertEqual(row["sev"], "halt")
        self.assertIn("0.0.0.0", row["say"])

    def test_r2_read_only_outside_bind_says_so_too(self):
        """R2. 막혀 있는 것도 말한다 — 버튼이 왜 듣지 않는지가 화면에 있어야 한다."""
        rows = self._notices("0.0.0.0", False)
        row = next((r for r in rows if r["id"] == "server:outsidebind"), None)
        self.assertIsNotNone(row, f"알림이 없다: {[r['id'] for r in rows]}")
        self.assertEqual(row["sev"], "note")

    def test_r3_loopback_says_nothing(self):
        """R3. 루프백에서는 서지 않는다 — 늘 서는 알림은 아무도 안 읽는다."""
        ids = [r["id"] for r in self._notices("127.0.0.1", False)]
        self.assertNotIn("server:openwrite", ids)
        self.assertNotIn("server:outsidebind", ids)

    def _notices(self, host, open_write):
        m = self.m
        old = (m.SERVE_HOST, m.SERVE_OPEN_WRITE, m.SERVE_STARTED)
        m.SERVE_HOST, m.SERVE_OPEN_WRITE = host, open_write
        m.SERVE_STARTED = m.SERVE_STARTED or "2026-09-16T00:00:00+09:00"
        try:
            return m.notices_info()["notices"]
        finally:
            m.SERVE_HOST, m.SERVE_OPEN_WRITE, m.SERVE_STARTED = old

    def test_b4_the_watcher_hands_the_decision_down(self):
        """B4. 감시자가 되살린 서버의 경계가 죽기 전과 같다.

        인자를 **불러서 본다** (DOC-20260907-002) — 소스 글자를 대조하지 않는다.
        기본이 닫힘이라 빠뜨려도 위험이 열리지는 않지만, 운영자가 연 것이
        말없이 닫히면 그것대로 사람이 원인을 못 찾는다.
        """
        self.assertNotIn("--open-write", self.m.guard_argv(9909, "0.0.0.0"))
        self.assertIn("--open-write",
                      self.m.guard_argv(9909, "0.0.0.0", True))


if __name__ == "__main__":
    unittest.main()
