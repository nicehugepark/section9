"""`s9 preview` — worktree 작업자가 제가 고친 web/ 을 띄워 보는 길
(REQ-20260916-014-62x6).

실제 사고 2026-09-16 11:05: worktree 에서 도는 작업자가 화면을 고쳤는데,
9909 서버는 **본 저장소의** web/ 을 서비스해 캡처에 그 변경이 없었다. 우회는
전부 작업자의 명령 허용 목록 밖이었다(환경변수 접두 · 일반 http 서버).

이 파일이 재는 것(전부 실제로 서버를 띄워 받아 본다 — 소스 글자를 읽지 않는다):
  ① 정적은 **그 자리의** web/ 에서 나온다 (본 저장소 것이 아니다)
  ② 묶음(/app/all.js·/css/all.css)도 그 자리의 조각으로 만들어진다
  ③ 정적이 아닌 경로는 넘길 서버의 응답을 그대로 돌려준다 (상태코드·본문·POST)
  ④ 넘길 서버가 없으면 정적은 그대로, 나머지는 503 + 사유
  ⑤ web/ 밖(../ · 심링크)은 404
  ⑥ 명령이 끝나면 그 포트는 비어 있다 — 부모가 사라진 서버가 남지 않는다

실행: python3 tests/ preview_overlay
"""
import http.server
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9_SRC = os.path.join(ROOT, "bin", "s9.py")


def load_s9():
    spec = importlib.util.spec_from_file_location("s9mod_preview", S9_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get(url, method="GET", data=None):
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class FakeUpstream:
    """넘김 대상 — 받은 경로·본문을 그대로 돌려주는 최소 서버."""

    def __init__(self):
        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):
                pass

            def _answer(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                if self.path == "/api/teapot":
                    code, out = 418, b"upstream-teapot"
                else:
                    code, out = 200, json.dumps(
                        {"upstream": True, "path": self.path,
                         "method": self.command,
                         "body": body.decode("utf-8", "replace")}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            do_GET = do_POST = _answer

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()


class PreviewOverlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_s9()
        cls.tmp = tempfile.mkdtemp(prefix="s9-preview-")
        web = os.path.join(cls.tmp, "web")
        os.makedirs(os.path.join(web, "app"))
        os.makedirs(os.path.join(web, "css"))
        with open(os.path.join(web, "index.html"), "w", encoding="utf-8") as f:
            # 조각 선언은 본 껍데기와 **같은 모양**이어야 묶음이 그것을 읽는다
            # (PART_LINK_RE/PART_SRC_RE: 줄 하나에 상대 경로).
            f.write('<html><head>\n'
                    '<link rel="stylesheet" href="css/one.css">\n'
                    '</head><body>WORKTREE-MARKER\n'
                    '<script src="app/one.js"></script>\n'
                    '</body></html>\n')
        with open(os.path.join(web, "app", "one.js"), "w", encoding="utf-8") as f:
            f.write("/*APP-PIECE-MARKER*/")
        with open(os.path.join(web, "css", "one.css"), "w", encoding="utf-8") as f:
            f.write("/*CSS-PIECE-MARKER*/")
        # web/ 밖의 비밀 하나 — 심링크와 ../ 가 이것을 못 집어야 한다
        cls.secret = os.path.join(cls.tmp, "secret.txt")
        with open(cls.secret, "w", encoding="utf-8") as f:
            f.write("OUTSIDE-SECRET")
        try:
            os.symlink(cls.secret, os.path.join(web, "leak.txt"))
            cls.symlinked = True
        except OSError:
            cls.symlinked = False
        # 묶음은 「방금 쓴 조각」을 쓰는 중으로 보고 기다린다(BUNDLE_DWELL_SEC) —
        # 시험이 그 대기를 사지 않게 mtime 을 뒤로 물린다.
        old = time.time() - 60
        for base, _dirs, names in os.walk(web):
            for n in names:
                os.utime(os.path.join(base, n), (old, old))
        cls.up = FakeUpstream()
        cls.srv, cls.port = cls.mod.preview_serve(cls.tmp, cls.up.port)
        cls.base = "http://127.0.0.1:%d" % cls.port
        # 넘길 서버가 없는 갈래는 따로 하나 더 (④)
        cls.srv0, cls.port0 = cls.mod.preview_serve(cls.tmp, 0)
        cls.base0 = "http://127.0.0.1:%d" % cls.port0

    @classmethod
    def tearDownClass(cls):
        for s in (cls.srv, cls.srv0):
            if s:
                s.shutdown()
        cls.up.stop()
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- ① 정적은 그 자리의 web/ 에서 -------------------------------
    def test_s1_index_comes_from_this_place(self):
        code, body = get(cls_base(self) + "/")
        self.assertEqual(code, 200)
        self.assertIn(b"WORKTREE-MARKER", body)

    def test_s1b_named_piece_comes_from_this_place(self):
        code, body = get(cls_base(self) + "/app/one.js")
        self.assertEqual(code, 200)
        self.assertIn(b"APP-PIECE-MARKER", body)

    # ---- ② 묶음도 그 자리의 조각으로 --------------------------------
    def test_s2_bundles_are_built_here(self):
        for path, marker in (("/app/all.js", b"APP-PIECE-MARKER"),
                             ("/css/all.css", b"CSS-PIECE-MARKER")):
            code, body = get(cls_base(self) + path)
            self.assertEqual(code, 200, path)
            self.assertIn(marker, body, path)

    # ---- ③ 나머지는 넘긴다 ------------------------------------------
    def test_s3_other_paths_go_upstream(self):
        code, body = get(cls_base(self) + "/api/digest?x=1")
        self.assertEqual(code, 200)
        d = json.loads(body.decode())
        self.assertTrue(d["upstream"])
        self.assertEqual(d["path"], "/api/digest?x=1")

    def test_s3b_upstream_status_and_post_body_survive(self):
        code, body = get(cls_base(self) + "/api/teapot")
        self.assertEqual(code, 418)
        self.assertEqual(body, b"upstream-teapot")
        code, body = get(cls_base(self) + "/api/note", method="POST",
                         data=b'{"hello":1}')
        self.assertEqual(code, 200)
        d = json.loads(body.decode())
        self.assertEqual(d["method"], "POST")
        self.assertEqual(d["body"], '{"hello":1}')

    # ---- ④ 넘길 서버가 없을 때 --------------------------------------
    def test_s4_without_upstream_static_still_works(self):
        code, body = get(self.base0 + "/")
        self.assertEqual(code, 200)
        self.assertIn(b"WORKTREE-MARKER", body)
        code, body = get(self.base0 + "/api/digest")
        self.assertEqual(code, 503)
        self.assertIn("s9 serve", body.decode("utf-8", "replace"))

    # ---- ⑤ web/ 밖은 안 낸다 ----------------------------------------
    def test_s5_outside_web_is_not_served(self):
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/leak.txt"):
            if path == "/leak.txt" and not self.symlinked:
                continue
            code, body = get(cls_base(self) + path)
            self.assertNotIn(b"OUTSIDE-SECRET", body, path)

    # ---- ⑥ 수명: 명령이 끝나면 포트가 비어 있다 ----------------------
    def test_s6_server_does_not_outlive_the_command(self):
        env = dict(os.environ, S9_TESTS_NESTED="1")
        r = subprocess.run(
            [sys.executable, S9_SRC, "preview", "--check",
             "--from", self.tmp, "--upstream", str(self.up.port)],
            capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        port = 0
        for tok in r.stdout.split():
            if tok.startswith("port="):
                port = int(tok.split("=", 1)[1])
        self.assertTrue(port, r.stdout + r.stderr)
        self.assertIn("status=200", r.stdout)
        # 붙는지가 아니라 **답하는지**를 본다: WSL 의 윈도우 중계는 리눅스
        # 리스너가 닫힌 뒤에도 한동안 그 포트를 공개하고, connect 는 성공한 뒤
        # 곧바로 reset 된다 (DOC-20260906-003).
        with self.assertRaises(Exception):
            urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=5)

    # ---- ⑦ 작업자가 실제로 칠 수 있는 줄인가 -------------------------
    def test_s7_worker_may_run_it(self):
        tools = self.mod.worker_s9_tools("/tmp/s9root/bin/s9")
        self.assertIn("Bash(/tmp/s9root/bin/s9 preview:*)", tools)


def cls_base(t):
    return t.base


class ThePreviewPortIsNotABypass(unittest.TestCase):
    """preview 포트가 쓰기 경계를 얇게 만들지 않는다 (REQ-20260916-003 과 맞물린다).

    프록시는 Origin 을 **떼서** 넘긴다 — 지어내면 이 포트가 남의 페이지에게
    본 서버의 교차출처 검사를 우회하는 길이 되기 때문이다. 그런데 떼고 나면
    Sec-Fetch-Site 를 안 싣는 옛 브라우저에서는 본 서버가 「브라우저가 아니다」로
    읽어 통과시킨다. 그래서 **떼기 전에** 이 포트 기준으로 한 번 잰다.
    """

    def setUp(self):
        import importlib.machinery, importlib.util, os
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, "..", "bin", "s9.py")
        spec = importlib.util.spec_from_loader(
            "s9_pv", importlib.machinery.SourceFileLoader("s9_pv", path))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def ok(self, origin, site, host="127.0.0.1:9951"):
        return self.m.origin_ok(origin, site, host)

    def test_a_cross_site_write_is_refused_at_the_preview_port(self):
        self.assertFalse(self.ok("http://evil.example", "cross-site"))
        self.assertFalse(self.ok("http://evil.example", None),
                         "Sec-Fetch-Site 를 안 싣는 옛 브라우저에서 새는 자리")

    def test_the_preview_page_itself_is_allowed(self):
        self.assertTrue(self.ok("http://127.0.0.1:9951", "same-origin"))

    def test_a_non_browser_caller_is_still_allowed(self):
        # 같은 컴퓨터의 프로세스는 이미 파일을 고칠 수 있다 — 여기서 막을 것이 없다
        self.assertTrue(self.ok(None, None))


if __name__ == "__main__":
    unittest.main()
