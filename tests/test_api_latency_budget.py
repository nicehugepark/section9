"""대시보드 API 응답 예산 — audit·catalog 가 요청마다 다시 계산하지 않는다 (REQ-20260909-062-62x6).

실측 2026-09-09 13:3x: /api/audit 가 4.9~7.5초, Audit 탭이 열리지 않았다. 계산은
0.12초였고(문서 1,618건 전수 읽기 + History 파싱) 나머지는 **바이트**였다 —
사건 12,756건 2.7MB 를 gzip 없이 보냈고, 이 환경의 루프백은 맨살 stdlib
서버로도 2.7MB 에 2.8~8.5초다(60KB 는 0.25초). limit 도 무시됐다.

고침: audit_data 는 파일 stat(mtime_ns·size)을 키로 문서별 사건을 캐시해
바뀐 파일만 다시 읽고, limit 을 지키며 total 을 같이 준다. _json 응답은
gzip 을 받는 클라이언트에 압축본을 보낸다(2.7MB → 177KB).

실행: python3 tests/ api_latency_budget
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

N_SESSIONS = 200
N_REQUESTS = 300
HIST_LINES = 30


def s9mod(root):
    os.environ["S9_ROOT"] = root
    name = "s9latency_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ApiLatencyBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9latency-")
        cls.m = s9mod(cls.tmp)
        cls.m.current_machine = lambda: "testbox"
        os.makedirs(cls.m.STATE, exist_ok=True)
        cls.ses_paths = []
        for i in range(N_SESSIONS):
            sid = f"SES-20260909-{i:03d}-zzzz"
            hist = "".join(
                f"- 2026-09-09T{(h % 24):02d}:{(i % 60):02d}:00+09:00 "
                f"prompt 사건 {i}-{h} (by tester)\n" for h in range(HIST_LINES))
            cls.ses_paths.append(cls.doc(
                "sessions", sid, "session",
                {"session": f"{i:08x}", "machine": "testbox"},
                "\n## Notes\n\n## History\n" + hist))
        for i in range(N_REQUESTS):
            cls.doc("requests", f"REQ-20260909-{i:03d}-zzzz", "request",
                    {"status": "in-progress", "size": "S"},
                    "\n## Notes\n\n## History\n")
        cls.m.rebuild_index(quiet=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def doc(cls, kind, doc_id, typ, extra, body):
        path = os.path.join(cls.m.VAULT, kind, "2026", "09", doc_id + ".md")
        meta = {"id": doc_id, "type": typ, "title": "예산 시험 " + doc_id,
                "summary": "s", "status": extra.pop("status", "active"),
                "user": "tester", "machine": "testbox",
                "created": "2026-09-09T00:00:00+09:00",
                "updated": "2026-09-09T00:00:00+09:00", "priority": 50}
        meta.update(extra)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cls.m.write_doc(path, meta, body)
        return path

    def _count_reads(self):
        """read_doc 호출 수를 세는 스텁 — 재계산 유무의 관측 지점."""
        m = self.m
        calls = {"n": 0}
        orig = m.read_doc

        def counted(path):
            calls["n"] += 1
            return orig(path)
        m.read_doc = counted
        self.addCleanup(setattr, m, "read_doc", orig)
        return calls

    # ---- S1. 따뜻한 audit_data 는 0.5초 안 ----------------------------
    def test_s1_audit_warm_under_budget(self):
        first = self.m.audit_data()
        t = time.monotonic()
        second = self.m.audit_data()
        warm = time.monotonic() - t
        self.assertEqual(len(first["events"]), N_SESSIONS * HIST_LINES)
        self.assertEqual(first["events"], second["events"])
        ts = [e["ts"] for e in second["events"]]
        self.assertEqual(ts, sorted(ts, reverse=True))
        self.assertLess(warm, 0.5, f"audit warm {warm:.3f}s")

    # ---- S2. 따뜻한 catalog_with_live 는 0.3초 안 --------------------
    def test_s2_catalog_warm_under_budget(self):
        self.m.catalog_with_live()
        t = time.monotonic()
        rows = self.m.catalog_with_live()
        warm = time.monotonic() - t
        self.assertGreaterEqual(len(rows), N_SESSIONS + N_REQUESTS)
        self.assertLess(warm, 0.3, f"catalog warm {warm:.3f}s")

    # ---- S3. 문서가 안 바뀌면 다시 읽지 않는다 -------------------------
    def test_s3_no_reread_when_unchanged(self):
        self.m.audit_data()
        calls = self._count_reads()
        self.m.audit_data()
        self.assertEqual(calls["n"], 0)

    # ---- S4. 바뀐 파일 하나만 다시 읽는다 ------------------------------
    def test_s4_incremental_reread_of_changed_file(self):
        self.m.audit_data()
        path = self.ses_paths[7]
        with open(path, "a", encoding="utf-8") as f:
            f.write("- 2026-09-09T23:59:59+09:00 note: 증분 사건 (by tester)\n")
        # mtime 눈금이 거친 파일 시스템에서도 stat 키가 바뀌게 — 크기가 이미 다르다
        calls = self._count_reads()
        d = self.m.audit_data()
        self.assertEqual(calls["n"], 1)
        self.assertEqual(d["events"][0]["text"], "note: 증분 사건")
        self.assertEqual(d["events"][0]["by"], "tester")
        self.assertEqual(d["events"][0]["doc"], os.path.basename(path)[:-3])

    # ---- S5. limit 은 최신 N건, total 은 전체 --------------------------
    def test_s5_limit_and_total(self):
        full = self.m.audit_data()
        lim = self.m.audit_data(limit=50)
        self.assertEqual(len(lim["events"]), 50)
        self.assertEqual(lim["events"], full["events"][:50])
        self.assertEqual(lim["total"], len(full["events"]))
        for bad in (0, -3, "abc", None):
            d = self.m.audit_data(limit=bad)
            self.assertEqual(len(d["events"]), len(full["events"]), bad)

    # ---- S6. 깨진 문서가 섞여도 나머지는 나온다 --------------------------
    def test_s6_broken_docs_do_not_break_the_rest(self):
        bad_dir = os.path.join(self.m.VAULT, "sessions", "2026", "09")
        p1 = os.path.join(bad_dir, "SES-20260909-900-zzzz.md")
        p2 = os.path.join(bad_dir, "SES-20260909-901-zzzz.md")
        with open(p1, "w", encoding="utf-8") as f:
            f.write("---\nid: SES-20260909-900-zzzz\ntype: session\n"
                    "session: [unclosed\n---\n## History\n- 이상한 줄\n-\n")
        with open(p2, "w", encoding="utf-8") as f:
            f.write("no frontmatter at all\n## History\n- 2026-09-09T01:00:00+09:00 x\n")
        self.addCleanup(lambda: [os.path.exists(p) and os.remove(p) for p in (p1, p2)])
        d = self.m.audit_data()
        self.assertGreaterEqual(len(d["events"]), N_SESSIONS * HIST_LINES)

    # ---- S7. gzip 을 받는 클라이언트에는 압축본 --------------------------
    def test_s7_json_response_gzip_when_accepted(self):
        obj = {"events": [{"ts": "2026-09-09T00:00:00+09:00", "text": "x" * 40}] * 500}
        raw, enc = self.m.json_response_bytes(obj, "")
        self.assertIsNone(enc)
        self.assertEqual(json.loads(raw.decode()), obj)
        z, enc = self.m.json_response_bytes(obj, "gzip, deflate, br")
        self.assertEqual(enc, "gzip")
        self.assertLess(len(z), len(raw) // 4)
        self.assertEqual(json.loads(gzip.decompress(z).decode()), obj)
        # 작은 본문은 압축하지 않는다 — 헤더가 본문보다 커진다
        small, enc = self.m.json_response_bytes({"ok": True}, "gzip")
        self.assertIsNone(enc)
        self.assertEqual(json.loads(small.decode()), {"ok": True})


if __name__ == "__main__":
    unittest.main()
