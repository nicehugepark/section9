"""안 바뀐 카탈로그는 안 보낸다 — ETag/304 + gzip (REQ-20260831-004-62x6).

이 기계의 TCP 루프백은 virtioproxy 프록시를 지나 ~6MB/s 다(유닉스 소켓
1.8GB/s — TCP 경로만 붕괴). 548KB catalog 를 95연결이 폴링하면 ~70MB/s
수요로 회선이 12배 초과돼 HTTP p95 12s 가 실측됐다(REQ-20260831-003 재벤치).
고침은 바이트를 줄이는 것: no-store→no-cache+ETag 로 브라우저가 매 폴
재검증(안 바뀌면 304 헤더 한 줄), 본문이 갈 때는 gzip.

실행: python3 tests/ catalog_conditional
"""
import gzip
import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import free_port, wait_server  # noqa: E402


class CatalogConditional(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9cond-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_PORT_GUARD": "off"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=20)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=cls.env, timeout=20)
        for i in range(3):
            cls.mkdoc(f"doc{i}")
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
    def mkdoc(cls, title):
        subprocess.run([S9, "new", "request", "--title", title,
                        "--summary", "t", "--goal", "t", "--size", "S",
                        "--user", "alice", "--body", "x" * 200],
                       capture_output=True, env=cls.env, timeout=20)

    def get(self, path="/api/catalog", headers=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:      # 304 는 여기로 온다
            return e.code, dict(e.headers), e.read()

    # T1. 200 응답에 ETag 와 Cache-Control: no-cache 가 있다
    def test_catalog_conditional(self):
        """CatalogConditional 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("t1_etag_and_no_cache"):
                code, hdr, body = self.get()
                self.assertEqual(code, 200)
                self.assertTrue(hdr.get("ETag", "").startswith('"'))
                self.assertEqual(hdr.get("Cache-Control"), "no-cache")
                self.assertTrue(json.loads(body))

            # T2. 받은 ETag 로 재요청하면 304, 본문 없음
        with self.subTest("t2_if_none_match_304"):
                _, hdr, _ = self.get()
                code, hdr2, body = self.get(headers={"If-None-Match": hdr["ETag"]})
                self.assertEqual(code, 304)
                self.assertEqual(body, b"")
                self.assertEqual(hdr2.get("ETag"), hdr["ETag"])

            # T3. gzip 을 받는 클라이언트에게는 압축본 — 해제하면 동일, 더 작다
        with self.subTest("t3_gzip"):
                _, _, plain = self.get()
                code, hdr, z = self.get(headers={"Accept-Encoding": "gzip"})
                self.assertEqual(code, 200)
                self.assertEqual(hdr.get("Content-Encoding"), "gzip")
                raw = gzip.GzipFile(fileobj=io.BytesIO(z)).read()
                self.assertEqual(raw, plain)
                self.assertLess(len(z), len(plain))

            # T4. 문서가 바뀌면 옛 ETag 로도 200 새 본문·새 ETag (지문 무효화 관통)
        with self.subTest("t4_change_invalidates"):
                _, hdr, _ = self.get()
                old = hdr["ETag"]
                self.mkdoc("fresh-after-etag")
                code, hdr2, body = self.get(headers={"If-None-Match": old})
                self.assertEqual(code, 200)
                self.assertNotEqual(hdr2.get("ETag"), old)
                self.assertIn("fresh-after-etag", body.decode())

            # T5. archived 뷰가 다르면 ETag 가 다르다 — 교차 304 오염 금지
        with self.subTest("t5_view_separation"):
                _, h1, _ = self.get("/api/catalog")
                _, h2, _ = self.get("/api/catalog?archived=1")
                self.assertNotEqual(h1["ETag"], h2["ETag"])
                code, _, _ = self.get("/api/catalog?archived=1",
                                      headers={"If-None-Match": h1["ETag"]})
                self.assertEqual(code, 200)

            # T6. 불일치 If-None-Match 는 200 정상 본문
        with self.subTest("t6_mismatch_full_body"):
                code, _, body = self.get(headers={"If-None-Match": '"nope"'})
                self.assertEqual(code, 200)
                self.assertTrue(json.loads(body))

            # T7. Accept-Encoding 없는 클라이언트는 비압축 그대로 (기존 계약)
        with self.subTest("t7_plain_client_unchanged"):
            code, hdr, body = self.get()
            self.assertEqual(code, 200)
            self.assertIsNone(hdr.get("Content-Encoding"))
            self.assertEqual(int(hdr["Content-Length"]), len(body))
            self.assertTrue(json.loads(body))

if __name__ == "__main__":
    unittest.main()
