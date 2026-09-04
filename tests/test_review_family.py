"""판정 큐 정렬과 낡음 신호 — review_family 읽기 파생 (REQ-20260831-015).

DOC-20260831-002 규칙2·3의 서버 몫: review 상태 REQ 들 사이 계보 간선
(parent/derived_from/relates)의 연결 성분을 카탈로그 행만으로 계산해
review_order(정렬 키)·review_prior(판정 짝)·review_stale(낡음)을 싣고,
반려 재작업 봉투(_spawn_rework)에 살아 있는 후행 목록과 파급 판정 지시를
주입한다. 저장 구조 무변경 — 전부 매 세대 재계산되는 파생이다.

실행: python3 tests/ review_family
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def s9mod(root):
    os.environ["S9_ROOT"] = root
    name = "s9rvfam_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def row(rid, status="review", created="2026-08-31T01:00:00+09:00",
        rtype="request", **kw):
    r = {"id": rid, "type": rtype, "status": status, "created": created,
         "parent": "", "derived_from": "", "relates": []}
    r.update(kw)
    return r


class ReviewFamilyPure(unittest.TestCase):
    """S1~S4: 순수 계산 — 행 dict 만으로 동작(행당 디스크 읽기 없음의 증명)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9rvfam-")
        cls.m = s9mod(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- S1. 정상: 성분 묶음·선행 우선 정렬·판정 짝 ----------------------
    def test_review_family_pure(self):
        """S1~S4: 순수 계산 — 행 dict 만으로 동작(행당 디스크 읽기 없음의 증명)."""
        with self.subTest("s1_component_order_and_prior"):
                a = row("REQ-20260831-901-aaaa", created="2026-08-31T01:00:00+09:00")
                b = row("REQ-20260831-902-bbbb", created="2026-08-31T03:00:00+09:00",
                        parent="REQ-20260831-901-aaaa")
                c = row("REQ-20260831-903-cccc", created="2026-08-31T04:00:00+09:00",
                        relates=["REQ-20260831-902-bbbb"])
                d = row("REQ-20260831-904-dddd", created="2026-08-31T02:00:00+09:00")
                rows = [c, d, a, b]
                self.m.review_family(rows)
                self.assertNotIn("review_prior", a)
                self.assertEqual(b["review_prior"], [a["id"]])
                self.assertEqual(c["review_prior"], [a["id"], b["id"]])
                # 사전식 오름차순만으로: 묶음(a,b,c) 인접 — 사이에 낀 d(02시) 가
                # 묶음을 가르지 않는다 (선두 created 가 묶음 전체의 자리)
                order = sorted(rows, key=lambda r: r["review_order"])
                self.assertEqual([r["id"] for r in order],
                                 [a["id"], b["id"], c["id"], d["id"]])

            # ---- S2. 정상: 낡음 신호 — 파생·relates 만, 우산 방향은 오탐 아님 ----
        with self.subTest("s2_stale_signal"):
            rv = row("REQ-20260831-911-aaaa")
            kid = row("REQ-20260831-912-bbbb", status="in-progress",
                      parent="REQ-20260831-911-aaaa")
            rel = row("REQ-20260831-913-cccc", status="in-progress",
                      relates=["REQ-20260831-911-aaaa"])
            # 우산-자식 정상 흐름: review 의 parent 가 in-progress — 낡음 아님
            umb = row("REQ-20260831-914-dddd", status="in-progress")
            child = row("REQ-20260831-915-eeee",
                        parent="REQ-20260831-914-dddd")
            # 비요청 타입은 무시
            doc = row("DOC-20260831-901-ffff", status="in-progress",
                      rtype="knowledge", relates=["REQ-20260831-911-aaaa"])
            rows = [rv, kid, rel, umb, child, doc]
            self.m.review_family(rows)
            self.assertEqual(rv["review_stale"], [kid["id"], rel["id"]])
            self.assertNotIn("review_stale", child)
        with self.subTest("s2b_stale_via_review_side_relates"):
                # 옛 문서 호환: relates 가 review 쪽에만 적혀 있어도 잡는다
                rv = row("REQ-20260831-921-aaaa",
                         relates=["REQ-20260831-922-bbbb"])
                ip = row("REQ-20260831-922-bbbb", status="in-progress")
                rows = [rv, ip]
                self.m.review_family(rows)
                self.assertEqual(rv["review_stale"], [ip["id"]])

            # ---- S3. 경계: 간선 없음·단독·비review·끊긴 간선·자기참조 ------------
        with self.subTest("s3_solo_and_ignored_edges"):
                solo = row("REQ-20260831-931-aaaa",
                           parent="REQ-19990101-999-zzzz",   # 카탈로그 밖 — 무시
                           relates=["REQ-20260831-931-aaaa"])  # 자기참조 — 무시
                ipro = row("REQ-20260831-932-bbbb", status="in-progress")
                rows = [solo, ipro]
                self.m.review_family(rows)
                self.assertIn("review_order", solo)
                self.assertNotIn("review_prior", solo)
                self.assertNotIn("review_stale", solo)
                for k in ("review_order", "review_prior", "review_stale"):
                    self.assertNotIn(k, ipro)   # review 아닌 행은 무장식

            # ---- S4. 경계: 순환 간선에도 유한 종료·정렬 안정 ---------------------
        with self.subTest("s4_cycle_terminates"):
            a = row("REQ-20260831-941-aaaa", created="2026-08-31T01:00:00+09:00",
                    parent="REQ-20260831-942-bbbb",
                    relates=["REQ-20260831-942-bbbb"])
            b = row("REQ-20260831-942-bbbb", created="2026-08-31T02:00:00+09:00",
                    parent="REQ-20260831-941-aaaa",
                    relates=["REQ-20260831-941-aaaa"])
            rows = [b, a]
            self.m.review_family(rows)      # 예외 없이 끝나야 한다
            self.assertNotIn("review_prior", a)
            self.assertEqual(b["review_prior"], [a["id"]])

class ReworkEnvelope(unittest.TestCase):
    """S5: _spawn_rework 봉투 — 후행 목록과 파급 판정 지시."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9rvenv-")
        self.m = s9mod(self.tmp)
        self.m.current_machine = lambda: "testbox"
        os.makedirs(self.m.STATE, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def doc(self, doc_id, status="in-progress", **extra):
        path = os.path.join(self.m.VAULT, "requests", "2026", "08",
                            doc_id + ".md")
        meta = {"id": doc_id, "type": "request", "title": "봉투 " + doc_id,
                "summary": "s", "status": status, "size": "S",
                "user": "tester", "machine": "testbox",
                "created": "2026-08-31T00:00:00+09:00",
                "updated": "2026-08-31T00:00:00+09:00", "priority": 50}
        meta.update(extra)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.m.write_doc(path, meta, "\n## Notes\n\n## History\n")
        return meta

    def captured_spawn(self):
        got = {}

        def fake(doc_id, meta, prompt, kind, **kw):
            got.update(doc_id=doc_id, prompt=prompt, kind=kind)
            return True

        self.m._spawn_worker = fake
        return got

    def test_s5_heirs_in_envelope(self):
        rej = self.doc("REQ-20260831-951-aaaa")
        self.doc("REQ-20260831-952-bbbb", status="review",
                 parent="REQ-20260831-951-aaaa")            # 파생·살아 있음
        self.doc("REQ-20260831-953-cccc", status="in-progress",
                 relates=["REQ-20260831-951-aaaa"])          # 연관·살아 있음
        self.doc("REQ-20260831-954-dddd", status="done",
                 parent="REQ-20260831-951-aaaa")            # 종결 — 제외
        self.m.rebuild_index(quiet=True)
        got = self.captured_spawn()
        self.assertTrue(self.m._spawn_rework(rej["id"], rej, "반려 사유"))
        self.assertIn("REQ-20260831-952-bbbb", got["prompt"])
        self.assertIn("REQ-20260831-953-cccc", got["prompt"])
        self.assertNotIn("REQ-20260831-954-dddd", got["prompt"])
        self.assertIn("후행", got["prompt"])
        self.assertIn("닿는지", got["prompt"])
        self.assertIn("자동 연쇄 반려 금지", got["prompt"])

    def test_s5b_no_heirs_no_clause(self):
        rej = self.doc("REQ-20260831-961-aaaa")
        self.doc("REQ-20260831-962-bbbb", status="done",
                 parent="REQ-20260831-961-aaaa")
        self.m.rebuild_index(quiet=True)
        got = self.captured_spawn()
        self.assertTrue(self.m._spawn_rework(rej["id"], rej, "반려 사유"))
        self.assertNotIn("후행 작업", got["prompt"])


class SnapshotIntegration(unittest.TestCase):
    """S6: 스냅샷 게이트 안 — 세대당 한 번, 필드는 스냅샷 결과에도 실린다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9rvsnap-")
        self.m = s9mod(self.tmp)
        self.m.current_machine = lambda: "testbox"
        os.makedirs(self.m.STATE, exist_ok=True)
        for i, (rid, extra) in enumerate([
                ("REQ-20260831-971-aaaa", {}),
                ("REQ-20260831-972-bbbb",
                 {"parent": "REQ-20260831-971-aaaa"})]):
            path = os.path.join(self.m.VAULT, "requests", "2026", "08",
                                rid + ".md")
            meta = {"id": rid, "type": "request", "title": "스냅 " + rid,
                    "summary": "s", "status": "review", "size": "S",
                    "user": "tester", "machine": "testbox",
                    "created": f"2026-08-31T0{i + 1}:00:00+09:00",
                    "updated": "2026-08-31T09:00:00+09:00", "priority": 50}
            meta.update(extra)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.m.write_doc(path, meta, "\n## Notes\n\n## History\n")
        self.m.rebuild_index(quiet=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_s6_gate_once_fields_in_snapshot(self):
        self.m.POLL_SNAPSHOT_SEC = 2.0
        calls = {"n": 0}
        real = self.m.catalog_with_live._compute

        def wrap(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        self.m.catalog_with_live._compute = wrap
        self.m.catalog_with_live()
        rows = self.m.catalog_with_live()          # 스냅샷 재사용
        self.assertEqual(calls["n"], 1, "TTL 안 두 번째 호출이 재계산했다")
        by = {r["id"]: r for r in rows}
        head = by["REQ-20260831-971-aaaa"]
        tail = by["REQ-20260831-972-bbbb"]
        self.assertIn("review_order", head)
        self.assertEqual(tail["review_prior"], [head["id"]])
        self.assertLess(head["review_order"], tail["review_order"])


if __name__ == "__main__":
    unittest.main()
