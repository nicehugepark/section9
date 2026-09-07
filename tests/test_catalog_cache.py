"""catalog 폭주가 서버를 세운다 — load_catalog 프로세스 캐시 (REQ-20260831-001-62x6).

실측 2026-08-31 00:26~. /api/catalog 한 요청이 load_catalog 를 **44회** 불러
json.loads 를 34,133회 돌렸다(737문서, catalog_with_live 3.556s CPU). 경로는
claim_dead(바인딩×REQ마다 재파싱)·canon_id→id_alias·_stop_claim_map·resolve_id —
같은 인덱스 파일을 한 패스 안에서 거듭 파싱하는 구조가 문서 수 성장과 함께
절벽을 넘었고, 폴링이 겹치자 스레드가 쌓여 GIL 정체로 응답이 72~91초→120초
타임아웃까지 갔다.

고침은 **경로 한 곳**: load_catalog 자신이 인덱스 파일 stat(mtime_ns·size·ino)
을 키로 파싱 결과를 프로세스에 캐시한다. rebuild_index 는 os.replace(원자 교체
— ino 가 반드시 바뀐다)라 무효화가 보장되고, 엔드포인트별 특수 캐시 분기는
만들지 않는다. 반환 행은 매 호출 얕은 복사 — catalog_with_live 가 r["live"]
등을 덧써도 캐시가 오염되지 않는다. 파싱 세대는 _CATALOG_CACHE["gen"] 으로
드러난다(시험·디버깅 관측용).

실행: python3 tests/ catalog_cache
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def s9mod(root, tag=""):
    """bin/s9 를 격리 ROOT 로 적재 (S9_ROOT 는 모듈 상단에서 읽힌다)."""
    os.environ["S9_ROOT"] = root
    name = "s9ccache" + tag + "_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class CatalogCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9ccache-")
        self.m = s9mod(self.tmp)
        self.m.current_machine = lambda: "testbox"
        os.makedirs(self.m.STATE, exist_ok=True)
        self.doc("REQ-20260831-901-zzzz")
        self.doc("REQ-20260831-902-zzzz")
        self.m.rebuild_index(quiet=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def doc(self, doc_id, status="in-progress"):
        path = os.path.join(self.m.VAULT, "requests", "2026", "08",
                            doc_id + ".md")
        meta = {"id": doc_id, "type": "request", "title": "캐시 시험 " + doc_id,
                "summary": "s", "status": status, "size": "S",
                "user": "tester", "machine": "testbox",
                "created": "2026-08-31T00:00:00+09:00",
                "updated": "2026-08-31T00:00:00+09:00", "priority": 50}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.m.write_doc(path, meta, "\n## Notes\n\n## History\n")
        return path

    def gen(self):
        return self.m._CATALOG_CACHE["gen"]

    # ---- S1. 정상: 두 번째 호출은 재파싱하지 않는다 --------------------
    def test_s1_second_call_hits_cache(self):
        r1 = self.m.load_catalog()
        g = self.gen()
        self.assertGreaterEqual(g, 1, "첫 호출이 파싱 세대를 남기지 않았다")
        r2 = self.m.load_catalog()
        self.assertEqual(self.gen(), g,
                         "인덱스가 안 바뀌었는데 두 번째 호출이 재파싱했다")
        self.assertEqual(r1, r2, "캐시 적중이 다른 내용을 돌려줬다")

    # ---- S2. 경계: 인덱스 갱신은 캐시를 무효화한다 ---------------------
    def test_s2_rebuild_invalidates(self):
        ids0 = {r["id"] for r in self.m.load_catalog()}
        self.assertNotIn("REQ-20260831-903-zzzz", ids0)
        g = self.gen()
        self.doc("REQ-20260831-903-zzzz")
        self.m.rebuild_index(quiet=True)      # os.replace — stat 이 바뀐다
        rows = self.m.load_catalog()
        self.assertIn("REQ-20260831-903-zzzz", {r["id"] for r in rows},
                      "인덱스를 다시 지었는데 낡은 캐시가 새 문서를 감췄다")
        self.assertEqual(self.gen(), g + 1, "무효화 후 재파싱이 한 번이 아니다")

    def test_s2b_inplace_append_invalidates(self):
        """rebuild 를 안 거친 직접 쓰기(크기 변화)도 다음 호출이 본다."""
        self.m.load_catalog()
        extra = dict(self.m.load_catalog()[0], id="REQ-20260831-904-zzzz",
                     path="vault/requests/2026/08/REQ-20260831-904-zzzz.md")
        import json
        with open(self.m.CATALOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(extra, ensure_ascii=False) + "\n")
        self.assertIn("REQ-20260831-904-zzzz",
                      {r["id"] for r in self.m.load_catalog()},
                      "파일이 자랐는데 캐시가 옛 목록을 돌려줬다")

    # ---- S3. 실패: 호출자의 장식이 캐시를 오염시키지 않는다 ------------
    def test_s3_caller_mutation_does_not_pollute(self):
        rows = self.m.load_catalog()
        rows[0]["live"] = True                # catalog_with_live 가 하는 그 일
        rows[0]["title"] = "오염"
        again = {r["id"]: r for r in self.m.load_catalog()}
        tainted = again[rows[0]["id"]]
        self.assertNotIn("live", tainted,
                         "호출자가 덧쓴 키가 다음 호출 결과에 배어 나왔다")
        self.assertNotEqual(tainted["title"], "오염",
                            "호출자의 값 변경이 캐시에 스몄다")

    # ---- S4. 경계: 파일이 없으면 빈 목록 — 유령 캐시 금지 --------------
    def test_s4_missing_file_returns_empty(self):
        self.m.load_catalog()                 # 캐시를 채워 둔다
        os.remove(self.m.CATALOG)
        self.assertEqual(self.m.load_catalog(), [],
                         "파일이 사라졌는데 캐시가 옛 행을 유령으로 돌려줬다")
        self.m.rebuild_index(quiet=True)
        self.assertTrue(self.m.load_catalog(), "파일이 돌아왔는데 빈 목록이다")

    # ---- S5. 회귀: catalog_with_live 한 패스 = 파싱 1회 ----------------
    def test_s5_one_parse_per_pass(self):
        fresh = s9mod(self.tmp, tag="cold")   # 찬 캐시에서 시작
        fresh.current_machine = lambda: "testbox"
        rows = fresh.catalog_with_live()
        self.assertTrue(rows, "전제: 카탈로그가 비어 있지 않다")
        self.assertEqual(fresh._CATALOG_CACHE["gen"], 1,
                         "한 catalog 패스가 인덱스를 두 번 이상 파싱했다 "
                         "(종전 44회 재파싱 회귀)")

    # ---- S7. 파생 캐시: id_alias 는 인덱스가 바뀔 때만 재구축 ----------
    def test_s7_alias_cached_until_index_changes(self):
        self.doc("REQ-20260831-906")          # 지문 없는 레거시 id 는 아니고
        self.doc("REQ-20260831-907-abcd")     # 접미 있는 정식 id — alias 대상
        self.m.rebuild_index(quiet=True)
        a1 = self.m.id_alias()
        self.assertEqual(a1.get("REQ-20260831-907"), "REQ-20260831-907-abcd")
        g = self.m._ALIAS_CACHE["gen"]
        a2 = self.m.id_alias()
        self.assertEqual(self.m._ALIAS_CACHE["gen"], g,
                         "인덱스가 안 바뀌었는데 alias 맵을 다시 지었다")
        self.assertEqual(a1, a2)
        a2["REQ-20260831-907"] = "오염"       # 호출자 변형이
        self.assertEqual(self.m.id_alias().get("REQ-20260831-907"),
                         "REQ-20260831-907-abcd", "캐시에 스몄다")
        self.doc("REQ-20260831-908-abcd")
        self.m.rebuild_index(quiet=True)
        self.assertEqual(self.m.id_alias().get("REQ-20260831-908"),
                         "REQ-20260831-908-abcd",
                         "인덱스 갱신 후에도 낡은 alias 맵이 나왔다")
        self.assertEqual(self.m._ALIAS_CACHE["gen"], g + 1)

    def test_s7b_explicit_rows_bypass_alias_cache(self):
        """rows 를 명시한 호출(필터된 부분집합일 수 있다)은 캐시를 안 탄다."""
        self.doc("REQ-20260831-909-abcd")
        self.m.rebuild_index(quiet=True)
        self.m.id_alias()                     # 전체 맵을 캐시에 채운다
        sub = [r for r in self.m.load_catalog()
               if r["id"] == "REQ-20260831-909-abcd"]
        a = self.m.id_alias(sub)
        self.assertEqual(list(a), ["REQ-20260831-909"],
                         "명시 rows 호출이 캐시된 전체 맵을 돌려줬다")

    # ---- S8/S9. 동시 폴링은 계산 하나를 공유한다 -----------------------
    def test_s8_concurrent_default_calls_share_one_compute(self):
        import threading
        calls = {"n": 0}
        real = self.m.catalog_with_live._compute

        def slow(stall_win=None):
            calls["n"] += 1
            time.sleep(0.15)                  # 겹칠 시간을 만든다
            return real(stall_win)

        self.m.catalog_with_live._compute = slow
        try:
            out, errs = [None] * 4, []

            def poll(i):
                try:
                    out[i] = self.m.catalog_with_live()
                except Exception as e:        # noqa: BLE001 — 시험 수집용
                    errs.append(e)

            ts = [threading.Thread(target=poll, args=(i,)) for i in range(4)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=10)
            self.assertFalse(errs, f"동시 호출이 죽었다: {errs}")
            self.assertEqual(calls["n"], 1,
                             "동시 기본 호출 4개가 계산을 공유하지 않았다 "
                             f"(계산 {calls['n']}회)")
            ids0 = {r["id"] for r in out[0]}
            for i in (1, 2, 3):
                self.assertEqual({r["id"] for r in out[i]}, ids0,
                                 "공유된 결과가 서로 다르다")
            out[0][0]["live"] = "오염"         # 응답 간 공유 dict 금지
            self.assertNotIn("오염", str(out[1][0].get("live", "")),
                             "두 응답이 같은 dict 를 공유한다")
        finally:
            self.m.catalog_with_live._compute = real

    def test_s9_explicit_stall_win_bypasses_sharing(self):
        import threading
        calls = {"n": 0}
        real = self.m.catalog_with_live._compute

        def slow(stall_win=None):
            calls["n"] += 1
            time.sleep(0.1)
            return real(stall_win)

        self.m.catalog_with_live._compute = slow
        try:
            done = []

            def default_call():
                done.append(self.m.catalog_with_live())

            t = threading.Thread(target=default_call)
            t.start()
            time.sleep(0.02)                  # 기본 호출이 계산에 들어간 뒤
            self.m.catalog_with_live(stall_win=5)   # CLI 경로 — 공유 금지
            t.join(timeout=10)
            self.assertEqual(calls["n"], 2,
                             "stall_win 명시 호출이 기본 호출의 결과를 "
                             "얻어 탔다 — 다른 창의 판정이 섞인다")
        finally:
            self.m.catalog_with_live._compute = real

    # ---- 기존 계약: tombstone(.trash) 행은 여전히 걸러진다 -------------
    def test_trash_rows_stay_excluded(self):
        import json
        ghost = dict(self.m.load_catalog()[0], id="REQ-20260831-905-zzzz",
                     path="vault/requests/2026/08/.trash/REQ-20260831-905-zzzz.md")
        with open(self.m.CATALOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(ghost, ensure_ascii=False) + "\n")
        self.assertNotIn("REQ-20260831-905-zzzz",
                         {r["id"] for r in self.m.load_catalog()},
                         "tombstone 행이 캐시 경로로 되살아났다")


if __name__ == "__main__":
    unittest.main()
