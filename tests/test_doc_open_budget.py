"""문서 열기 경로의 서버 예산 — /api/doc 이 하는 일은 문서 수를 따라 커지지 않는다 (REQ-20260913-031-62x6).

실측 2026-09-13 21:0x(주인 「카드를 눌러 문서로 넘어갈 때 상당히 오래 걸린다」):
서버 쪽 /api/doc 은 p50 5ms 였고 실브라우저(Windows Chrome, 같은 WSL 중계)로 잰
카드 클릭→문서 화면은 기본 목록에서 43~157ms, request 무리를 전부 편 목록(267행)
에서 270~487ms 였다 — 화면 쪽 비용은 목록 행 수에 비례하고, 서버 쪽은 상수다.
이 시험은 서버 쪽 상수를 지킨다: locate 가 색인을 쓰지 않고 vault 를 훑기 시작하면,
문서 하나를 여는 데 다른 문서까지 읽기 시작하면, 응답이 gzip 없이 나가기 시작하면
실패한다(중계는 ~6MB/s 라 바이트가 곧 시간이다, REQ-20260831-004).

실행: python3 tests/ doc_open_budget
"""
import importlib.machinery
import importlib.util
import gzip
import json
import os
import shutil
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

N_REQUESTS = 1900
OPEN_ROUNDS = 100
WARM_BUDGET_MS = 20.0       # 회당 평균 — 실측 vault 1,917건에서 /api/doc p50 5ms
GZIP_BUDGET = 8192          # 30KB 급 문서 본문의 압축본 상한


def s9mod(root):
    os.environ["S9_ROOT"] = root
    name = "s9docopen_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class DocOpenBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9docopen-")
        cls.m = s9mod(cls.tmp)
        cls.m.current_machine = lambda: "testbox"
        os.makedirs(cls.m.STATE, exist_ok=True)
        cls.ids = []
        for i in range(N_REQUESTS):
            doc_id = f"REQ-20260913-{i:03d}-zzzz"
            path = os.path.join(cls.m.VAULT, "requests", "2026", "09", doc_id + ".md")
            meta = {"id": doc_id, "type": "request", "title": "예산 시험 " + doc_id,
                    "summary": "s", "status": "in-progress", "size": "S",
                    "user": "tester", "machine": "testbox",
                    "created": "2026-09-13T00:00:00+09:00",
                    "updated": "2026-09-13T00:00:00+09:00", "priority": 50}
            os.makedirs(os.path.dirname(path), exist_ok=True)
            cls.m.write_doc(path, meta, "\n## Original\n\n본문\n\n## Notes\n\n## History\n")
            cls.ids.append(doc_id)
        cls.m.rebuild_index(quiet=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _open(self, doc_id):
        """핸들러(/api/doc)가 하는 일 그대로 — 찾고, 읽고, 볼 수 있는지 판정한다."""
        m = self.m
        path = m.locate(doc_id)
        self.assertTrue(path, doc_id)
        meta, body = m.read_doc(path)
        self.assertTrue(m.doc_access(meta, "tester"))
        return meta, body

    # ---- S1. 따뜻한 열기 100회 평균이 예산 안 — vault 전수 훑기로 되돌아가면 실패 ----
    def test_s1_warm_open_under_budget(self):
        self._open(self.ids[-1])
        t = time.monotonic()
        for i in range(OPEN_ROUNDS):
            self._open(self.ids[(i * 97) % N_REQUESTS])
        per = (time.monotonic() - t) * 1000.0 / OPEN_ROUNDS
        self.assertLess(per, WARM_BUDGET_MS, f"문서 열기 회당 {per:.2f}ms")

    # ---- S2. 문서 하나를 여는 데 읽는 문서는 그 하나뿐 ----------------------------
    def test_s2_open_reads_only_that_doc(self):
        m = self.m
        self._open(self.ids[7])
        calls = []
        orig = m.read_doc

        def counted(path):
            calls.append(os.path.basename(path))
            return orig(path)
        m.read_doc = counted
        self.addCleanup(setattr, m, "read_doc", orig)
        self._open(self.ids[8])
        self.assertEqual(calls, [self.ids[8] + ".md"])

    # ---- S3. 30KB 급 본문은 gzip 을 받는 클라이언트에 8KB 이하로 ---------------------
    def test_s3_doc_response_gzip_small(self):
        m = self.m
        meta, _ = self._open(self.ids[3])
        notes = "".join(
            f"\n### 2026-09-13T21:{i % 60:02d}:{(i * 7) % 60:02d}+09:00 response (by tester)\n"
            f"실측 {i}: 카드 클릭에서 문서 화면까지 {40 + i % 120}ms · 요청 {1 + i % 6}건 · "
            f"바이트 {2000 + i * 13} — 서버 /api/doc p50 5ms, 화면 목록 {66 + i}행.\n"
            for i in range(160))
        body = "\n## Original\n\n본문\n\n## Notes\n" + notes + "\n## History\n"
        self.assertGreater(len(body.encode("utf-8")), 30000)
        obj = {"meta": meta, "body": body, "path": "vault/requests/x.md"}
        raw, enc = m.json_response_bytes(obj, "")
        self.assertIsNone(enc)
        z, enc = m.json_response_bytes(obj, "gzip, deflate, br")
        self.assertEqual(enc, "gzip")
        self.assertLess(len(z), GZIP_BUDGET, f"gzip {len(z)}B (raw {len(raw)}B)")
        self.assertEqual(json.loads(gzip.decompress(z).decode())["body"], body)


if __name__ == "__main__":
    unittest.main()
