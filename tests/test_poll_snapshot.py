"""폴링 폭풍에도 서버가 산다 — TTL 스냅샷 게이트 (REQ-20260831-002-62x6).

001(재파싱 관문 캐시) 마감 뒤에도 라이브가 죽었다: 브라우저 재시도 폭풍
(ss 실측 ESTABLISHED 95연결)이 요청마다 0.4~1.7s 의 신선도 스캔
(catalog_with_live 0.81s·session_rows 1.68s — streams_glob 181회·/proc 43회/패스)
을 연결 수만큼 곱했다. 느려짐→클라 타임아웃→재연결의 자기 유지 나선.

고침: 001 의 공유 게이트(_share_default_pass)에 TTL 스냅샷을 얹는다 —
serve 기동 시에만 POLL_SNAPSHOT_SEC=2.0 (CLI·시험 기본 0 = 매번 신선).
TTL 안이라도 지문(카탈로그 stat + 서버 POST 카운터)이 바뀌면 재계산 —
전이·세우기 직후의 조회가 낡은 화면을 받지 않는다. 행동 경로(chat_target)는
게이트 밖 — tail 종료 0.2s 내 반영 계약(test_dashboard_chat C9/C18)이 산다.

실행: python3 tests/ poll_snapshot
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
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def s9mod(root):
    os.environ["S9_ROOT"] = root
    name = "s9psnap_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class PollSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9psnap-")
        self.m = s9mod(self.tmp)
        self.m.current_machine = lambda: "testbox"
        os.makedirs(self.m.STATE, exist_ok=True)
        self.doc("REQ-20260831-951-zzzz")
        self.m.rebuild_index(quiet=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def doc(self, doc_id):
        path = os.path.join(self.m.VAULT, "requests", "2026", "08",
                            doc_id + ".md")
        meta = {"id": doc_id, "type": "request", "title": "스냅샷 " + doc_id,
                "summary": "s", "status": "in-progress", "size": "S",
                "user": "tester", "machine": "testbox",
                "created": "2026-08-31T00:00:00+09:00",
                "updated": "2026-08-31T00:00:00+09:00", "priority": 50}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.m.write_doc(path, meta, "\n## Notes\n\n## History\n")
        return path

    def counted(self, gate):
        """게이트의 계산부를 세는 래퍼로 바꾼다 — {'n'} 카운터를 돌려준다."""
        calls = {"n": 0}
        real = gate._compute

        def wrap(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        gate._compute = wrap
        self.addCleanup(lambda: setattr(gate, "_compute", real))
        return calls

    # ---- T1. 정상: TTL 안의 연속 기본 호출 = 계산 1회 --------------------
    def test_t1_snapshot_hit_within_ttl(self):
        self.m.POLL_SNAPSHOT_SEC = 2.0
        calls = self.counted(self.m.catalog_with_live)
        r1 = self.m.catalog_with_live()
        r2 = self.m.catalog_with_live()
        self.assertEqual(calls["n"], 1,
                         "TTL 안의 두 번째 호출이 계산을 다시 돌렸다")
        self.assertEqual({r["id"] for r in r1}, {r["id"] for r in r2})

    # ---- T2. 경계: 유효창(max(TTL, 계산 소요))이 지나면 재계산 ----------
    def test_t2_ttl_expiry_recomputes(self):
        self.m.POLL_SNAPSHOT_SEC = 0.05
        calls = self.counted(self.m.catalog_with_live)
        self.m.catalog_with_live()
        win = max(0.05, self.m.catalog_with_live._state["dur"])
        time.sleep(win + 0.05)
        self.m.catalog_with_live()
        self.assertEqual(calls["n"], 2, "유효창이 지났는데 낡은 스냅샷이 나왔다")

    def test_t2b_slow_compute_widens_the_window(self):
        """계산 소요 > TTL 이면 소요만큼은 유효 — 눌린 시스템이 폴마다
        전량 재계산하는 나선(스냅샷이 태어나자마자 만료)을 막는다."""
        self.m.POLL_SNAPSHOT_SEC = 0.05
        calls = self.counted(self.m.catalog_with_live)
        real = self.m.catalog_with_live._compute

        def slow(*a, **k):
            time.sleep(0.3)               # 계산이 TTL(0.05)보다 길다
            return real(*a, **k)

        self.m.catalog_with_live._compute = slow
        self.addCleanup(lambda: setattr(
            self.m.catalog_with_live, "_compute", real))
        self.m.catalog_with_live()        # dur ≈ 0.3 기록
        time.sleep(0.1)                   # TTL 은 지났지만 dur 안이다
        self.m.catalog_with_live()
        self.assertEqual(calls["n"], 1,
                         "계산 소요보다 어린 스냅샷을 버리고 다시 돌았다")

    # ---- T3. 경계: 문서가 바뀌면 TTL 안이라도 재계산 --------------------
    def test_t3_doc_change_invalidates(self):
        self.m.POLL_SNAPSHOT_SEC = 30.0
        calls = self.counted(self.m.catalog_with_live)
        self.m.catalog_with_live()
        self.doc("REQ-20260831-952-zzzz")
        self.m.rebuild_index(quiet=True)      # 전이·노트가 지나는 그 길
        rows = self.m.catalog_with_live()
        self.assertEqual(calls["n"], 2,
                         "문서가 바뀌었는데 스냅샷이 낡은 보드를 돌려줬다 — "
                         "전이 직후 화면이 승인/반려를 잃어버린 것으로 보인다")
        self.assertIn("REQ-20260831-952-zzzz", {r["id"] for r in rows})

    # ---- T4. 경계: 서버 행동(POST)이 오면 TTL 안이라도 재계산 -----------
    def test_t4_post_epoch_invalidates(self):
        self.m.POLL_SNAPSHOT_SEC = 30.0
        calls = self.counted(self.m.catalog_with_live)
        self.m.catalog_with_live()
        self.m._POLL_EPOCH[0] += 1            # do_POST 가 하는 그 일
        self.m.catalog_with_live()
        self.assertEqual(calls["n"], 2,
                         "행동 직후의 조회가 낡은 화면을 받았다")

    def test_t4b_do_post_rolls_the_epoch(self):
        """카운터를 굴리는 자리는 do_POST 입구 한 곳이다 (분기 금지)."""
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index("def do_POST(self):")
        j = src.index("def ", i + 10)
        self.assertIn("_POLL_EPOCH[0] += 1", src[i:j],
                      "POST 입구가 스냅샷 지문을 굴리지 않는다")

    # ---- T5. 회귀: 기본(TTL=0)은 매번 신선 — 001 의 의미 보존 -----------
    def test_t5_default_ttl_zero_always_fresh(self):
        self.assertEqual(self.m.POLL_SNAPSHOT_SEC, 0.0,
                         "모듈 기본 TTL 이 0 이 아니다 — CLI·시험이 낡는다")
        calls = self.counted(self.m.catalog_with_live)
        self.m.catalog_with_live()
        self.m.catalog_with_live()
        self.assertEqual(calls["n"], 2,
                         "TTL=0 인데 스냅샷이 재사용됐다 — CLI 의미가 바뀐다")

    def test_t5b_serve_is_the_only_place_that_raises_ttl(self):
        src = open(S9_SRC, encoding="utf-8").read()
        hits = [l for l in src.splitlines()
                if "POLL_SNAPSHOT_SEC = " in l and not l.lstrip().startswith("#")]
        self.assertEqual(len(hits), 2, hits)   # 모듈 기본 0.0 + cmd_serve 2.0

    # ---- T6. 계약: 행동 경로는 게이트 밖 --------------------------------
    def test_t6_chat_target_is_not_gated(self):
        self.assertFalse(hasattr(self.m.chat_target, "_compute"),
                         "chat_target 이 게이트를 지난다 — tail 종료 0.2s 내 "
                         "반영 계약(C9/C18)이 깨진다")
        src = open(S9_SRC, encoding="utf-8").read()
        self.assertNotIn("@_share_default_pass\ndef chat_target", src)

    # ---- T7. sessions 도 같은 게이트 — limit 명시는 우회 ----------------
    def test_t7_session_rows_shares_and_bypasses(self):
        self.m.POLL_SNAPSHOT_SEC = 2.0
        calls = self.counted(self.m.session_rows)
        self.m.session_rows()
        self.m.session_rows()
        self.assertEqual(calls["n"], 1, "sessions 스냅샷이 재사용되지 않는다")
        self.m.session_rows(limit=5)
        self.assertEqual(calls["n"], 2, "limit 명시 호출이 스냅샷을 얻어 탔다")

    # ---- T9. 응답 캐시는 게이트 **뒤**에 선다 — 두 번째 판정 금지 -------
    def test_t9_response_cache_sits_behind_the_gate(self):
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index('elif parsed.path == "/api/catalog"')
        blk = src[i:src.index("elif parsed.path", i + 10)]
        g = blk.index("catalog_with_live()")
        c = blk.index("_CATALOG_RESP")
        self.assertLess(g, c,
                        "응답 캐시가 게이트보다 먼저 답한다 — TTL·지문 "
                        "무효화를 우회하는 두 번째 신선도 판정이 생겼다")
        self.assertIn('_state["seq"]', blk,
                      "응답 캐시 키에 스냅샷 세대가 없다 — 새 계산 뒤에도 "
                      "낡은 바이트가 나간다")

    # ---- 오염 방지: 계산자·스냅샷 수신자 모두 사본을 받는다 -------------
    def test_snapshot_is_isolated_from_callers(self):
        self.m.POLL_SNAPSHOT_SEC = 2.0
        r1 = self.m.catalog_with_live()       # 계산한 호출자
        r1[0]["live"] = "오염"
        r2 = self.m.catalog_with_live()       # 스냅샷 수신자
        self.assertNotEqual(r2[0].get("live"), "오염",
                            "계산자의 장식이 스냅샷에 배어 나왔다")
        r2[0]["title"] = "오염2"
        r3 = self.m.catalog_with_live()
        self.assertNotEqual(r3[0].get("title"), "오염2")


if __name__ == "__main__":
    unittest.main()
