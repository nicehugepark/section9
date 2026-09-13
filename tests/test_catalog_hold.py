"""휘발 필드만 바뀐 카탈로그는 다시 보내지 않는다 — 안정 서명 캐시 키·응답 행 깎기·
keep-alive 유휴 상한 (REQ-20260913-033-62x6).

실측 2026-09-13(주인 서버 9909, 11초 간격 3회): /api/catalog?window=all 은 매번
다른 ETag 였고 달라진 필드는 quiet_mins·stall_why·updated·lease.renewed 뿐이었다 —
상태가 아니라 시각·분 계수다. 화면은 그것 때문에 10분에 54회, 11.6MB(원문 2.1MB
×54) 를 다시 받았다. 고침 셋: ① 응답 캐시 키가 검사 세대가 아니라 (휘발 필드를 뺀
안정 서명, 60초 구간) — 상태 변경은 즉시, 휘발 변경은 구간마다 한 번. ② 응답 행에서
화면이 읽지 않는 키와 빈 값 키를 뺀다(인덱스 행은 그대로). ③ KEEPALIVE_IDLE 은
Chrome 이 스스로 유휴 소켓을 닫는 300초보다 길다 — 서버가 먼저 닫아 WSL 중계에
남는 죽은 소켓이 생기지 않는다.

격리: S9_ROOT=mktemp, 서버 없이 모듈 직접 호출(빠른 테스트 규칙).
실행: python3 tests/ catalog_hold
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
WEB = os.path.join(HERE, "..", "web", "app")

T0 = "2026-09-13T21:00:00+09:00"
T1 = "2026-09-13T21:01:00+09:00"
T2 = "2026-09-13T21:02:00+09:00"


def s9mod(root):
    os.environ["S9_ROOT"] = root
    for k in ("S9_KEEPALIVE_IDLE", "S9_CATALOG_HOLD", "S9_SESSION"):
        os.environ.pop(k, None)
    name = "s9hold_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _js_const(fname, name):
    with open(os.path.join(WEB, fname), encoding="utf-8") as f:
        src = f.read()
    mo = re.search(r"const %s = (\d+);" % re.escape(name), src)
    assert mo, f"{fname} 에 {name} 이 없다"
    return int(mo.group(1))


class CatalogHold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9hold-")
        cls.m = s9mod(cls.tmp)
        cls.m.current_machine = lambda: "testbox"
        os.makedirs(cls.m.STATE, exist_ok=True)
        cls.m._catalog_bucket = lambda now=None: 1     # 구간은 시험이 넘긴다
        cls.ids = ["REQ-20260913-901-hold", "REQ-20260913-902-hold"]
        for i in cls.ids:
            cls.doc(i)
        cls.m.rebuild_index(quiet=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def doc(cls, doc_id, status="in-progress", renewed=T0, updated=T0):
        path = os.path.join(cls.m.VAULT, "requests", "2026", "09", doc_id + ".md")
        meta = {"id": doc_id, "type": "request", "title": "보류 시험 " + doc_id,
                "summary": "s", "status": status, "size": "S", "user": "tester",
                "machine": "testbox", "created": T0, "updated": updated,
                "priority": 50,
                "lease": {"user": "tester", "machine": "testbox", "session": "abcd1234",
                          "since": T0, "renewed": renewed}}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cls.m.write_doc(path, meta, "\n## Notes\n\n## History\n")
        return path

    def resp(self):
        body, etag, _z, _w = self.m.catalog_response("tester", False, "all")
        return json.loads(body), etag, body

    def row(self, rows, doc_id):
        return next(r for r in rows if r["id"] == doc_id)

    # ---- S1. 리스 갱신만 있는 쓰기(doc_lease_acquire 경로)는 같은 ETag --------
    def test_s1_lease_only_write_keeps_etag(self):
        rows0, etag0, body0 = self.resp()
        self.assertEqual(self.row(rows0, self.ids[0])["lease"]["renewed"], T0)
        self.doc(self.ids[0], renewed=T1)          # updated 는 그대로 — 클레임 경로
        self.m.rebuild_index(quiet=True)
        idx = {r["id"]: r for r in self.m.load_catalog()}
        self.assertEqual(idx[self.ids[0]]["lease"]["renewed"], T1,
                         "전제: 인덱스 행에는 새 renewed 가 있다")
        rows1, etag1, body1 = self.resp()
        self.assertEqual(etag1, etag0, "리스 시각만 바뀌었는데 ETag 가 바뀌었다 — "
                         "화면이 전량 카탈로그를 다시 받는다")
        self.assertEqual(body1, body0)
        # 노트 쓰기(updated 만) 도 같은 구간에서는 같은 본문이다
        self.doc(self.ids[0], renewed=T1, updated=T1)
        self.m.rebuild_index(quiet=True)
        _r, etag2, _b = self.resp()
        self.assertEqual(etag2, etag0, "updated 만 바뀌었는데 ETag 가 바뀌었다")

    # ---- S2. 상태 전이는 같은 구간이라도 즉시 새 본문 -----------------------
    def test_s2_state_change_is_immediate(self):
        _r, etag0, _b = self.resp()
        self.doc(self.ids[1], status="review")
        self.m.rebuild_index(quiet=True)
        rows1, etag1, _b = self.resp()
        self.assertNotEqual(etag1, etag0, "상태가 바뀌었는데 옛 본문을 돌려줬다")
        self.assertEqual(self.row(rows1, self.ids[1])["status"], "review")
        self.doc("REQ-20260913-903-hold")                     # 새 문서도 즉시 (T4 계약)
        self.m.rebuild_index(quiet=True)
        rows2, etag2, _b = self.resp()
        self.assertNotEqual(etag2, etag1)
        self.assertIn("REQ-20260913-903-hold", {r["id"] for r in rows2})

    # ---- S3. 구간이 넘어가면 휘발 필드가 최신으로 실린다 ---------------------
    def test_s3_bucket_rollover_refreshes_volatile(self):
        self.doc(self.ids[0], renewed=T1)
        self.m.rebuild_index(quiet=True)
        rows0, etag0, _b = self.resp()
        self.doc(self.ids[0], renewed=T2, updated=T2)
        self.m.rebuild_index(quiet=True)
        _r, etag1, _b = self.resp()
        self.assertEqual(etag1, etag0, "전제: 같은 구간에서는 보류된다")
        old = self.m._catalog_bucket
        self.m._catalog_bucket = lambda now=None: 2
        try:
            rows2, etag2, _b = self.resp()
        finally:
            self.m._catalog_bucket = old
        self.assertNotEqual(etag2, etag0)
        r = self.row(rows2, self.ids[0])
        self.assertEqual(r["lease"]["renewed"], T2, "구간이 넘어갔는데 리스 시각이 낡았다")
        self.assertEqual(r["updated"], T2)

    # ---- S4. 응답 행: 안 읽는 키·빈 값 키가 없고 행이 가볍다 -----------------
    def test_s4_wire_rows_are_slim(self):
        rows, _e, body = self.resp()
        self.assertTrue(rows)
        for r in rows:
            for k in self.m.CATALOG_WIRE_DROP:
                self.assertNotIn(k, r, f"{k} 는 화면이 읽지 않는데 실렸다")
            for k in self.m.CATALOG_WIRE_SPARSE:
                if k in r:
                    self.assertNotIn(r[k], ("", [], {}, None), f"{k} 가 빈 값으로 실렸다")
            for k in ("id", "type", "title", "status", "user", "machine", "path",
                      "created", "updated", "status_since"):
                self.assertIn(k, r, f"화면이 그대로 쓰는 {k} 가 빠졌다")
        self.assertEqual(self.row(rows, self.ids[0])["lease"]["machine"], "testbox",
                         "값이 있는 lease 는 실려야 한다")
        idx = {r["id"]: r for r in self.m.load_catalog()}
        self.assertIn("creator_raw", idx[self.ids[0]], "인덱스 행까지 깎였다 — CLI 가 읽는다")
        self.assertLessEqual(len(body) / len(rows), 800,
                             f"행당 {len(body) / len(rows):.0f}B — 상한 800B")

    # ---- S5. 이벤트 벡터의 catalog 키 — 리스 갱신엔 조용, 상태 변경엔 바뀐다 --
    def test_s5_events_key_follows_state_only(self):
        with open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"catalog": catalog_change_key(),', src,
                      "events_vector 의 catalog 조각이 안정 서명이 아니다")
        self.doc(self.ids[1], status="blocked")             # 상태를 못 박고 잰다
        self.m.rebuild_index(quiet=True)
        k0 = self.m.catalog_change_key()
        self.assertTrue(k0)
        self.doc(self.ids[1], status="blocked", renewed=T2, updated=T2)
        self.m.rebuild_index(quiet=True)
        self.assertEqual(self.m.catalog_change_key(), k0,
                         "리스·노트 시각만 바뀌었는데 채널이 화면을 깨운다")
        self.doc(self.ids[1], status="review")
        self.m.rebuild_index(quiet=True)
        self.assertNotEqual(self.m.catalog_change_key(), k0,
                            "상태가 바뀌었는데 채널이 조용하다")

    # ---- S6. 유휴 상한은 브라우저의 소켓 만료·화면 안전 폴보다 길다 -----------
    def test_s6_keepalive_outlives_browser_and_belt(self):
        belt = _js_const("events_ch.js", "EV_POLL_MS") / 1000.0
        self.assertGreater(self.m.KEEPALIVE_IDLE, self.m.BROWSER_USED_IDLE_SEC,
                           "서버가 Chrome(300초)보다 먼저 닫으면 WSL 중계에 죽은 "
                           "소켓이 남아 첫 fetch 가 실패하고 다시 건다")
        self.assertGreater(self.m.KEEPALIVE_IDLE, belt)
        self.assertLessEqual(self.m.CATALOG_HOLD_SEC, belt,
                             "재전송 구간이 안전 폴보다 길면 분 계수가 폴보다 낡는다")
        self.assertLess(_js_const("app.js", "CATALOG_TTL") / 1000.0, belt,
                        "화면의 카탈로그 신선도가 안전 폴보다 길면 벨트를 굶긴다")


if __name__ == "__main__":
    unittest.main()
