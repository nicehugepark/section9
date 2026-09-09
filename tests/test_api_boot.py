"""대시보드 부트 한 왕복 — /api/boot (REQ-20260909-086-62x6).

화면은 뜰 때 whoami·projects·docindex·serveguard·catalog 를 **따로** 불렀다.
이 환경의 루프백은 요청 하나에 고정 비용이 있다 — 아무 일도 안 하는 stdlib
서버도 새 연결 한 요청에 140~200ms 다(실측 2026-09-09, bin/s9 의 계산은
whoami 0.2ms·projects 0.06ms·serveguard 0.8ms). 그래서 서버 쪽 지렛대는
계산이 아니라 **왕복 수**다: 부트의 다섯 조각을 한 응답으로 묶는다.

조각은 단독 API 가 쓰는 함수를 그대로 부른다 — 묶음이 단독과 다른 답을 하면
화면이 두 얼굴을 갖는다. 그래서 여기서 조각마다 단독 API 와 같은지 잰다.

같은 문서의 「요청마다 /proc 전수」 가설도 여기서 반증으로 못박는다:
proc_scope/streams_scope 는 **게으르다** — 들어가고 나오는 것만으로는 아무것도
훑지 않는다(계기 불변). 훑기는 그 표를 실제로 묻는 API 에서만 일어난다.

실행: python3 tests/ api_boot
"""
import gzip
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"
sys.path.insert(0, HERE)

from portpool import free_port, wait_server  # noqa: E402


def s9mod(root):
    os.environ["S9_ROOT"] = root
    name = "s9boot_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9_SRC))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ApiBoot(unittest.TestCase):
    """서버 기동은 클래스당 한 번, s9 왕복도 setUpClass 에서만."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9boot-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "alice", "S9_PORT_GUARD": "off"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        # alice 는 admin — 그래야 ?as=bob 대리가 서고 alice 는 전량을 본다
        cls.cli("user", "add", "alice", "--role", "admin")
        cls.cli("user", "add", "bob")
        for i in range(3):
            cls.cli("new", "request", "--title", f"doc{i}", "--summary", "t",
                    "--goal", "t", "--size", "S", "--user", "alice",
                    "--body", "x" * 200)
        # bob 만의 문서 — 뷰어에 따라 docindex 가 달라야 S3 가 뜻을 가진다
        cls.cli("new", "request", "--title", "bob-only", "--summary", "t",
                "--goal", "t", "--size", "S", "--user", "bob",
                "--body", "y" * 200)
        # 번들(S7)용 껍데기와 조각 — 서버는 ROOT/web 에서 읽는다
        cls.web = os.path.join(cls.tmp, "web")
        os.makedirs(os.path.join(cls.web, "app"))
        os.makedirs(os.path.join(cls.web, "css"))
        with open(os.path.join(cls.web, "index.html"), "w") as f:
            f.write('<link rel="stylesheet" href="css/a.css">\n'
                    '<script src="app/a.js"></script>\n'
                    '<script src="app/b.js"></script>\n')
        with open(os.path.join(cls.web, "app", "a.js"), "w") as f:
            f.write("// a\n" + "var a = 1;\n" * 800)
        with open(os.path.join(cls.web, "app", "b.js"), "w") as f:
            f.write("// b\nvar b = 2;\n")
        with open(os.path.join(cls.web, "css", "a.css"), "w") as f:
            f.write("body{margin:0}\n")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    @classmethod
    def cli(cls, *a):
        r = subprocess.run([S9, *a], capture_output=True, env=cls.env,
                           timeout=30)
        assert r.returncode == 0, (a, r.stderr.decode(errors="replace")[-400:])
        return r

    def get(self, path, headers=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def getj(self, path, headers=None):
        st, hd, body = self.get(path, headers)
        self.assertEqual(st, 200, (path, body[:200]))
        if hd.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return json.loads(body.decode()), hd

    # ── S1 ── 다섯 조각, 단독 API 와 같은 답
    def test_s1_boot_has_five_pieces_equal_to_single_apis(self):
        boot, _ = self.getj("/api/boot")
        for k in ("whoami", "projects", "docindex", "serveguard", "catalog"):
            self.assertIn(k, boot)
        self.assertEqual(boot["whoami"], self.getj("/api/whoami")[0])
        self.assertEqual(boot["projects"], self.getj("/api/projects")[0])
        self.assertEqual(boot["docindex"], self.getj("/api/docindex")[0])
        self.assertTrue(len(boot["docindex"]) >= 3)

    # ── S2 ── serveguard(now 제외)·catalog ETag
    def test_s2_serveguard_and_catalog_etag(self):
        boot, _ = self.getj("/api/boot")
        single = self.getj("/api/serveguard")[0]
        strip = lambda d: {k: v for k, v in d.items() if k != "now"}  # noqa: E731
        self.assertEqual(strip(boot["serveguard"]), strip(single))
        st, hd, _ = self.get("/api/catalog?window=board")
        self.assertEqual(st, 200)
        self.assertEqual(boot["catalog"]["etag"], hd.get("ETag"))
        self.assertEqual(boot["catalog"]["window"],
                         hd.get("X-S9-Catalog-Window"))
        # 그 ETag 로 조건부 요청을 걸면 304 — 화면이 부트 값으로 첫 폴을 아낀다
        st2, _, body2 = self.get("/api/catalog?window=board",
                                 {"If-None-Match": boot["catalog"]["etag"]})
        self.assertEqual((st2, body2), (304, b""))

    # ── S3 ── 뷰어 필터가 묶음에서 빠지지 않는다
    def test_s3_viewer_filter_applies_in_bundle(self):
        for me in ("alice", "bob"):
            boot, _ = self.getj(f"/api/boot?as={me}")
            self.assertEqual(boot["projects"],
                             self.getj(f"/api/projects?as={me}")[0], me)
            self.assertEqual(boot["docindex"],
                             self.getj(f"/api/docindex?as={me}")[0], me)
        a = {r[0] for r in self.getj("/api/boot?as=alice")[0]["docindex"]}
        b = {r[0] for r in self.getj("/api/boot?as=bob")[0]["docindex"]}
        self.assertNotEqual(a, b, "뷰어가 달라도 같은 색인이면 필터가 빠진 것")

    # ── S4 ── 스코프 진입·이탈은 훑기 0회 (게으름의 증명)
    def test_s4_scopes_are_lazy(self):
        m = s9mod(self.tmp)
        p0, s0 = m._PROC_STAT["reads"], m._STREAMS_STAT["reads"]
        for _ in range(100):
            with m.proc_scope(), m.streams_scope():
                pass
        self.assertEqual((m._PROC_STAT["reads"], m._STREAMS_STAT["reads"]),
                         (p0, s0))
        # 스코프 안에서 실제로 물으면 그때 한 번 — 두 번 물어도 한 번
        with m.proc_scope():
            m.proc_table()
            m.proc_table()
        self.assertEqual(m._PROC_STAT["reads"], p0 + 1)

    # ── S5 ── boot 한 요청이 늘리는 proc 훑기는 최대 1
    def test_s5_boot_scans_proc_at_most_once(self):
        self.getj("/api/boot")                       # 캐시를 채운다
        before = self.getj("/api/serveinfo")[0]["proc"]["reads"]
        self.getj("/api/boot")
        after = self.getj("/api/serveinfo")[0]["proc"]["reads"]
        self.assertLessEqual(after - before, 1)

    # ── S6 ── 전송은 _json 경로 그대로: gzip 협상(4KB 미만은 원문)·Vary·no-store
    def test_s6_json_transport_contract(self):
        st, hd, body = self.get("/api/boot", {"Accept-Encoding": "gzip"})
        self.assertEqual(st, 200)
        self.assertEqual(hd.get("Vary"), "Accept-Encoding")
        self.assertEqual(hd.get("Cache-Control"), "no-store")
        if hd.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        else:
            self.assertLess(len(body), 4096, "4KB 이상인데 gzip 이 아니다")
        self.assertIn("whoami", json.loads(body.decode()))

    # ── S7 ── 번들은 gzip · ETag · no-cache, 조각이 바뀌면 지문이 바뀐다
    def test_s7_bundle_gzip_etag_and_invalidation(self):
        st, hd, body = self.get("/app/all.js", {"Accept-Encoding": "gzip"})
        self.assertEqual(st, 200)
        self.assertEqual(hd.get("Content-Encoding"), "gzip")
        self.assertEqual(hd.get("Cache-Control"), "no-cache")
        etag = hd.get("ETag")
        self.assertTrue(etag)
        text = gzip.decompress(body).decode()
        self.assertIn("var a = 1;", text)
        self.assertIn("window.__S9_BUNDLE", text)
        st2, hd2, body2 = self.get("/app/all.js", {"If-None-Match": etag})
        self.assertEqual((st2, body2), (304, b""))
        self.assertEqual(hd2.get("ETag"), etag)
        # gzip 을 안 받는 클라이언트는 원문 그대로
        st3, hd3, body3 = self.get("/app/all.js")
        self.assertEqual(st3, 200)
        self.assertIsNone(hd3.get("Content-Encoding"))
        self.assertIn(b"var b = 2;", body3)
        # 조각을 고치면 다음 요청은 새 본문·새 ETag. 다 쓴 뒤에야다 — 묶음은
        # 모든 조각이 dwell(기본 1초)만큼 조용할 때만 새로 짓는다
        # (REQ-20260909-095). 여기서는 mtime 을 뒤로 옮겨 그 시간을 안 기다린다.
        fp = os.path.join(self.web, "app", "b.js")
        with open(fp, "a") as f:
            f.write("var b2 = 3;\n")
        old = time.time() - 30
        os.utime(fp, (old, old))
        st4, hd4, body4 = self.get("/app/all.js", {"If-None-Match": etag})
        self.assertEqual(st4, 200)
        self.assertNotEqual(hd4.get("ETag"), etag)
        self.assertIn(b"var b2 = 3;", body4)

    # ── S8 ── catalog 응답 캐시는 창마다 슬롯을 가진다
    def test_s8_catalog_response_cache_keeps_a_slot_per_window(self):
        m = s9mod(self.tmp)
        m.POLL_SNAPSHOT_SEC = 2.0
        b0 = m._RESP_STAT["builds"]
        m.catalog_response("alice", False, "all")
        m.catalog_response("alice", False, "board")
        m.catalog_response("alice", False, "all")
        m.catalog_response("alice", False, "board")
        self.assertEqual(m._RESP_STAT["builds"] - b0, 2)
        b1 = m._RESP_STAT["builds"]
        obj, body, etag, zbody = m.docindex_response("alice")
        self.assertEqual(m.docindex_response("alice")[0], obj)
        self.assertEqual(m._RESP_STAT["builds"] - b1, 1)
        self.assertEqual(json.loads(body.decode()), obj)
        self.assertEqual(gzip.decompress(zbody), body)

    # ── S9 ── graph_data 는 안 바뀐 문서를 다시 읽지 않는다
    def test_s9_graph_data_rereads_only_changed_docs(self):
        m = s9mod(self.tmp)
        calls = {"n": 0}
        real = m.read_doc

        def counted(path):
            calls["n"] += 1
            return real(path)
        m.read_doc = counted
        try:
            g1 = m.graph_data()
            n_docs = sum(1 for _ in m.walk_docs())
            self.assertEqual(len(g1["nodes"]), n_docs)
            calls["n"] = 0
            g2 = m.graph_data()
            self.assertEqual(calls["n"], 0, "안 바뀐 문서를 다시 읽었다")
            self.assertEqual(g2, g1)
            # 문서 하나에 relates 를 더하면 그 1건만 다시 읽고 엣지가 는다
            paths = sorted(m.walk_docs())
            meta, body = real(paths[0])
            other = [real(p)[0]["id"] for p in paths[1:2]][0]
            with open(paths[0], encoding="utf-8") as f:
                src = f.read()
            src = src.replace("\nstatus:", f"\nrelates: [\"{other}\"]\nstatus:", 1)
            with open(paths[0], "w", encoding="utf-8") as f:
                f.write(src)
            os.utime(paths[0], None)
            calls["n"] = 0
            g3 = m.graph_data()
            self.assertEqual(calls["n"], 1)
            self.assertIn({"from": meta["id"], "to": other, "rel": "relates"},
                          g3["edges"])
        finally:
            m.read_doc = real

    # ── S10 ── 세대 키 바이트 캐시: 같은 키는 빌드 1회, 상한을 넘기면 버린다
    def test_s10_cached_bytes_builds_once_and_bounds(self):
        m = s9mod(self.tmp)
        import threading
        cache, lock, built = {}, threading.Lock(), {"n": 0}

        def build():
            built["n"] += 1
            return b"x" * 5000, {"win": "w"}
        e1 = m._cached_bytes(cache, lock, ("k", 1), build, keep=3)
        e2 = m._cached_bytes(cache, lock, ("k", 1), build, keep=3)
        self.assertIs(e1, e2)
        self.assertEqual(built["n"], 1)
        self.assertEqual(gzip.decompress(e1["zbody"]), e1["body"])
        self.assertTrue(e1["etag"].startswith('"') and e1["win"] == "w")
        for i in range(2, 8):
            m._cached_bytes(cache, lock, ("k", i), build, keep=3)
        self.assertEqual(built["n"], 7)
        self.assertEqual(len(cache), 3)
        self.assertNotIn(("k", 1), cache)          # 오래된 것부터 버린다
        self.assertIn(("k", 7), cache)


if __name__ == "__main__":
    unittest.main()
