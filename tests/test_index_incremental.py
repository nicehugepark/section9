"""증분 카탈로그 — 쓰기 하나가 vault 전체를 다시 읽지 않는다
(REQ-20260902-035-62x6).

rebuild_index 는 쓰기마다 vault 를 통째로 read_doc 했다: 문서 894건에 0.27s,
6,465건에 1.0s. 부르는 자리가 31곳이고 거의 전부 write_doc 직후라, 문서가
늘수록 **상태 하나 바꾸는 일**이 비싸지는 구조였다.

고침은 경계 한 곳이다 — write_doc 이 그 문서 행만 델타 파일에 덧붙이고,
load_catalog 이 base 를 델타로 덮어 한 목록을 만든다. 델타가 길어지면 접어서
base 로 돌린다. 전량은 명시 호출(`s9 index rebuild`)과, 증분이 한 번도 안 돈
자리(삭제·이동·pull)의 몫으로 남는다 — 놓친 자리가 있어도 인덱스가 어긋나지
않고 느려질 뿐인, 안전한 쪽으로 기운 기본값이다.

실행: python3 tests/ index_incremental
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import free_port, wait_server  # noqa: E402


def s9mod(root, tag=""):
    """bin/s9 를 격리 ROOT 로 적재 (S9_ROOT 는 모듈 상단에서 읽힌다)."""
    os.environ["S9_ROOT"] = root
    name = "s9incr" + tag + "_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9incr-")
        self.m = s9mod(self.tmp)
        self.m.current_machine = lambda: "testbox"
        os.makedirs(self.m.STATE, exist_ok=True)
        self.doc("REQ-20260902-901-zzzz")
        self.doc("REQ-20260902-902-zzzz")
        self.m.rebuild_index(quiet=True)      # 첫 전량 — base 가 선다

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path_of(self, doc_id):
        return os.path.join(self.m.VAULT, "requests", "2026", "09",
                            doc_id + ".md")

    def doc(self, doc_id, status="open", user="tester", tags=None):
        path = self.path_of(doc_id)
        meta = {"id": doc_id, "type": "request", "title": "증분 " + doc_id,
                "summary": "s", "status": status, "size": "S",
                "user": user, "machine": "testbox", "project": "section9",
                "tags": tags or [],
                "created": "2026-09-02T00:00:00+09:00",
                "updated": "2026-09-02T00:00:00+09:00", "priority": 50}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.m.write_doc(path, meta, "\n## Notes\n\n## History\n")
        return path

    def ids(self):
        return {r["id"] for r in self.m.load_catalog()}

    def delta_lines(self):
        try:
            with open(self.m.CATALOG_DELTA, encoding="utf-8") as f:
                return [l for l in f if l.strip()]
        except OSError:
            return []

    def base_lines(self):
        with open(self.m.CATALOG, encoding="utf-8") as f:
            return [l for l in f if l.strip()]


class Normal(Base):
    # ---- S1. 쓰기 하나가 vault 전체를 다시 읽지 않는다 -----------------
    def test_s1_one_write_reads_one_doc(self):
        reads = []
        real = self.m.read_doc
        self.m.read_doc = lambda p, *a, **k: (reads.append(p), real(p, *a, **k))[1]
        try:
            self.doc("REQ-20260902-903-zzzz")
        finally:
            self.m.read_doc = real
        self.assertIn("REQ-20260902-903-zzzz", self.ids(),
                      "새 문서가 카탈로그에 안 보인다")
        self.assertLessEqual(
            len(reads), 2,
            f"쓰기 하나가 문서를 {len(reads)}번 읽었다 — 전량 재생성 회귀")

    # ---- S2. base + 델타가 한 목록으로 보인다 --------------------------
    def test_s2_delta_merges_into_one_list(self):
        self.doc("REQ-20260902-904-zzzz")
        self.assertTrue(self.delta_lines(), "델타에 아무것도 안 적혔다")
        self.assertEqual(
            self.ids(),
            {"REQ-20260902-901-zzzz", "REQ-20260902-902-zzzz",
             "REQ-20260902-904-zzzz"},
            "base 와 델타가 한 목록으로 합쳐지지 않았다")

    # ---- S3. by-* 색인 md 가 따라온다 ----------------------------------
    def test_s3_index_files_follow(self):
        did = "REQ-20260902-901-zzzz"
        opened = os.path.join(self.m.INDEX, "by-status", "open.md")
        prog = os.path.join(self.m.INDEX, "by-status", "in-progress.md")
        self.assertIn(did, open(opened, encoding="utf-8").read())
        self.doc(did, status="in-progress")
        self.assertNotIn(did, open(opened, encoding="utf-8").read(),
                         "옛 상태의 색인에 그대로 남아 있다")
        self.assertIn(did, open(prog, encoding="utf-8").read(),
                      "새 상태의 색인에 들어가지 않았다")

    # ---- S4. 델타가 길어지면 접힌다 ------------------------------------
    def test_s4_delta_compacts(self):
        self.m.CATALOG_DELTA_MAX = 5
        for i in range(10, 22):
            self.doc(f"REQ-20260902-9{i}-zzzz")
        before = self.ids()
        self.assertLessEqual(len(self.delta_lines()), 5,
                             "델타가 상한을 넘고도 안 접혔다")
        self.assertGreater(len(self.base_lines()), 5,
                           "접힌 결과가 base 에 안 담겼다")
        self.assertEqual(before, self.ids(), "접기 전후 행 집합이 달라졌다")


class Edge(Base):
    # ---- B1. 삭제 — 묘비가 서고 목록에서 사라진다 -----------------------
    def test_b1_removal_leaves_a_tombstone(self):
        did = "REQ-20260902-901-zzzz"
        self.m.do_rm(did, reason="시험", user="tester")
        self.assertNotIn(did, self.ids(), "지운 문서가 목록에 남아 있다")

    # ---- B2. 대량 쓰기는 증분을 멈춘다 ----------------------------------
    def test_b2_bulk_defers(self):
        n = [0]
        real = self.m.index_upsert
        self.m.index_upsert = lambda *a, **k: (n.__setitem__(0, n[0] + 1),
                                               real(*a, **k))[1]
        try:
            with self.m.index_defer():
                for i in range(30, 40):
                    self.doc(f"REQ-20260902-9{i}-zzzz")
            self.m.rebuild_index(quiet=True)
        finally:
            self.m.index_upsert = real
        self.assertEqual(len(self.delta_lines()), 0,
                         "멈춘 구간인데 델타가 쌓였다")
        self.assertIn("REQ-20260902-939-zzzz", self.ids(),
                      "구간 끝의 전량 재생성이 새 문서를 안 담았다")

    # ---- B3. 델타가 없으면 예전과 똑같다 --------------------------------
    def test_b3_no_delta_is_unchanged(self):
        self.m.rebuild_index(quiet=True, full=True)
        self.assertEqual(self.delta_lines(), [], "전량 뒤에도 델타가 남았다")
        self.assertEqual(
            self.ids(), {"REQ-20260902-901-zzzz", "REQ-20260902-902-zzzz"})

    # ---- B4. 깨진 줄은 그 줄만 버린다 -----------------------------------
    def test_b4_broken_delta_line_is_skipped(self):
        self.doc("REQ-20260902-905-zzzz")
        with open(self.m.CATALOG_DELTA, "a", encoding="utf-8") as f:
            f.write("{이건 json 이 아니다\n")
        self.assertIn("REQ-20260902-905-zzzz", self.ids(),
                      "깨진 줄 하나가 조회를 통째로 세웠다")

    # ---- B5. base 가 없으면 인덱스는 없는 것이다 ------------------------
    def test_b5_no_base_means_no_index(self):
        self.doc("REQ-20260902-906-zzzz")
        os.remove(self.m.CATALOG)
        self.assertEqual(self.m.load_catalog(), [],
                         "base 가 사라졌는데 델타만으로 유령 목록을 냈다")
        self.m.rebuild_index(quiet=True)
        self.assertIn("REQ-20260902-906-zzzz", self.ids(),
                      "전량 재생성이 문서를 되찾지 못했다")


class Failure(Base):
    # ---- F1. 델타만 바뀌어도 캐시·지문이 움직인다 -----------------------
    def test_f1_delta_moves_cache_and_fingerprint(self):
        self.m.load_catalog()
        gen, fp = self.m._CATALOG_CACHE["gen"], self.m._poll_fingerprint()
        self.doc("REQ-20260902-907-zzzz")
        self.m.load_catalog()
        self.assertGreater(self.m._CATALOG_CACHE["gen"], gen,
                           "델타가 바뀌었는데 캐시가 옛 목록을 붙잡았다")
        self.assertNotEqual(self.m._poll_fingerprint(), fp,
                            "델타가 바뀌었는데 폴링 지문이 그대로다 — "
                            "화면이 갱신을 놓친다")

    # ---- F2. 접기 도중의 덧붙임은 유실되지 않는다 -----------------------
    def test_f2_append_during_compact_survives(self):
        self.m.CATALOG_DELTA_MAX = 2
        for i in range(40, 44):
            self.doc(f"REQ-20260902-9{i}-zzzz")
        self.assertEqual(
            self.ids(),
            {"REQ-20260902-901-zzzz", "REQ-20260902-902-zzzz",
             "REQ-20260902-940-zzzz", "REQ-20260902-941-zzzz",
             "REQ-20260902-942-zzzz", "REQ-20260902-943-zzzz"},
            "접기를 거치며 행이 사라졌다")

    def test_f2b_concurrent_writers_keep_every_row(self):
        """두 스레드가 함께 써도 줄이 섞이거나 사라지지 않는다."""
        def run(lo):
            for i in range(lo, lo + 8):
                self.doc(f"REQ-20260902-9{i}-zzzz")
        ts = [threading.Thread(target=run, args=(50,)),
              threading.Thread(target=run, args=(60,))]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        got = self.ids()
        for i in list(range(50, 58)) + list(range(60, 68)):
            self.assertIn(f"REQ-20260902-9{i}-zzzz", got,
                          "동시 쓰기에서 행이 유실됐다")

    # ---- F3. 락을 쥔 자리에서 불려도 죽지 않는다 ------------------------
    def test_f3_no_lock_reentry(self):
        self.m.acquire_lock()
        try:
            self.doc("REQ-20260902-908-zzzz")     # 락 안에서의 증분
        finally:
            self.m.release_lock()
        self.assertIn("REQ-20260902-908-zzzz", self.ids(),
                      "락을 쥔 채로 부른 증분이 반영되지 않았다")


class Regression(Base):
    # ---- R1. 전량 재생성 결과와 증분 결과가 같다 ------------------------
    def test_r1_incremental_equals_full(self):
        self.doc("REQ-20260902-909-zzzz", status="review", tags=["x"])
        self.doc("REQ-20260902-901-zzzz", status="done", user="other")
        incr = self.m.load_catalog()
        self.m.rebuild_index(quiet=True, full=True)
        full = self.m.load_catalog()
        self.assertEqual(incr, full,
                         "증분으로 만든 목록이 전량 재생성과 다르다")

    # ---- R2. 색인 md 도 전량과 같다 -------------------------------------
    def test_r2_index_files_equal_full(self):
        self.doc("REQ-20260902-910-zzzz", status="blocked", tags=["a", "b"])
        self.doc("REQ-20260902-901-zzzz", status="done", user="other")
        snap = self.index_snapshot()
        self.m.rebuild_index(quiet=True, full=True)
        self.assertEqual(snap, self.index_snapshot(),
                         "증분이 그린 색인 파일이 전량과 다르다")

    def index_snapshot(self):
        out = {}
        for dim in self.m.INDEX_DIMS:
            d = os.path.join(self.m.INDEX, dim)
            for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    out[dim + "/" + fn] = f.read()
        return out

    # ---- R3. 카탈로그는 여전히 원자 교체다 ------------------------------
    def test_r3_full_rebuild_is_still_atomic(self):
        ino = os.stat(self.m.CATALOG).st_ino
        self.m.rebuild_index(quiet=True, full=True)
        self.assertNotEqual(ino, os.stat(self.m.CATALOG).st_ino,
                            "전량 재생성이 제자리 덮어쓰기로 돌아갔다")

    # ---- R4. 지운 문서는 되살아나지 않는다 ------------------------------
    def test_r4_trash_rows_stay_out(self):
        did = "REQ-20260902-902-zzzz"
        self.m.do_rm(did, reason="시험", user="tester")
        self.m.rebuild_index(quiet=True, full=True)
        self.assertNotIn(did, self.ids(), "전량 재생성이 지운 문서를 되살렸다")


class Scale(unittest.TestCase):
    """goal 의 숫자를 그대로 잰다 — 쓰기 하나의 인덱스 갱신이 100ms 이내인가.

    이 요구가 여는 조건은 "3천 문서 전에" 였다. 그래서 그 문턱 위인 4,000건에서
    잰다. 전량 재생성은 문서 수에 정비례한다(894건 0.27s · 6,465건 1.0s 실측) —
    증분이 그 곡선에서 떨어져 나왔는지는 눈이 아니라 시계로 판정한다.

    측정이 드러낸 것 하나를 여기 적어 둔다(REQ-20260902-035 노트 참조):
    카탈로그 자체의 증분은 문서 수를 거의 안 따라가지만(1,000건 4.6ms →
    4,000건 8.5ms), **by-* 색인 md 다시 쓰기**는 여전히 따라간다 — 쓰기 비용의
    ~85%가 그것이다. 그 파일은 사람이 `cat`·`grep` 으로 읽는 자리이고 코드가
    읽는 곳은 없다(전수 확인). 아래 '분해' 줄이 그 몫을 매번 찍는다."""

    SIZES = (1000, 4000)
    BUDGET_MS = 100

    @classmethod
    def setUpClass(cls):
        # 문서 5,000건을 세우는 값비싼 측정이다 — 한 번 재고 두 판정이 나눠 쓴다
        cls.small, cls.big = [cls.measure(n) for n in cls.SIZES]

    @staticmethod
    def measure(n):
        """문서 n 건을 세우고 (전량 ms, 증분 ms, 색인 md 뺀 증분 ms) 를 잰다."""
        import time
        tmp = tempfile.mkdtemp(prefix="s9scale-")
        try:
            m = s9mod(tmp, "scale%d" % n)
            m.current_machine = lambda: "testbox"
            m.CATALOG_DELTA_MAX = 10 ** 6      # 접기가 이 측정에 끼지 않게
            os.makedirs(m.STATE, exist_ok=True)
            paths = []
            with m.index_defer():
                for i in range(n):
                    did = "REQ-20260902-%05d-zzzz" % i
                    p = os.path.join(m.VAULT, "requests", "2026", "09",
                                     did + ".md")
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    m.write_doc(p, {
                        "id": did, "type": "request", "title": "규모 " + did,
                        "summary": "s" * 80, "status": "open", "size": "S",
                        "user": "tester", "machine": "testbox",
                        "project": "section9", "tags": ["scale"],
                        "created": "2026-09-02T00:00:00+09:00",
                        "updated": "2026-09-02T00:00:00+09:00",
                        "priority": 50,
                    }, "\n## Notes\n\n" + "본문 " * 200 + "\n## History\n")
                    paths.append(p)
            t0 = time.time()
            m.rebuild_index(quiet=True, full=True)
            full_ms = (time.time() - t0) * 1000
            best = None
            for i in range(3):                 # 첫 회는 캐시가 아직 안 섰다
                t0 = time.time()
                m.index_upsert(paths[(n // 2) + i])
                ms = (time.time() - t0) * 1000
                best = ms if best is None else min(best, ms)
            # 남은 선형 항이 어디 있는지 매 실행이 스스로 말하게 한다:
            # by-* 색인 md 를 빼면 카탈로그 갱신만 남는다.
            real_w = m._index_files_write
            m._index_files_write = lambda *a, **k: None
            bare = None
            try:
                for i in range(3):
                    t0 = time.time()
                    m.index_upsert(paths[(n // 3) + i])
                    ms = (time.time() - t0) * 1000
                    bare = ms if bare is None else min(bare, ms)
            finally:
                m._index_files_write = real_w
            print(f"\n  [{n}건] 전량 {full_ms:.0f}ms · 증분 {best:.1f}ms "
                  f"(색인 md 빼면 {bare:.1f}ms) · catalog "
                  f"{os.path.getsize(m.CATALOG) / 1e6:.2f}MB")
            return full_ms, best, bare
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_x1_write_cost_is_within_budget(self):
        big = self.big
        self.assertLess(
            big[1], self.BUDGET_MS,
            f"{self.SIZES[1]}건에서 쓰기 하나가 {big[1]:.0f}ms — 예산 "
            f"{self.BUDGET_MS}ms 초과")
        self.assertLess(
            big[1], big[0] / 3,
            f"증분({big[1]:.0f}ms)이 전량({big[0]:.0f}ms)만큼 비싸다 — "
            "경계에 안 걸렸거나 전량으로 물러나고 있다")

    def test_x2_catalog_itself_breaks_off_the_linear_line(self):
        """카탈로그 갱신(색인 md 제외)이 전량의 직선에서 떨어져 나왔는가.

        이것이 §1·§2 가 고치려던 그 비용이다 — 델타 한 줄 덧붙임과 병합된
        읽기. 완전한 상수는 아니다: 델타를 얹은 병합이 아직 행 수를 한 번
        훑는다(실측 1,000건 2.9ms → 4,000건 6.5ms = 2.2배, 정비례면 4배).
        문서가 4배 늘 때 3배 아래면 그 직선 위가 아니다."""
        small, big = self.small, self.big
        ratio = self.SIZES[1] / self.SIZES[0]
        self.assertLess(
            big[2], small[2] * (ratio - 1),
            f"카탈로그 증분이 문서 수를 그대로 따라간다: {self.SIZES[0]}건 "
            f"{small[2]:.1f}ms → {self.SIZES[1]}건 {big[2]:.1f}ms")
        self.assertLess(
            big[2], self.BUDGET_MS / 5,
            f"카탈로그 증분만으로 {big[2]:.0f}ms — 예산의 5분의 1을 넘었다")


class PullRange(Base):
    """§3. pull 뒤에는 바뀐 파일만 — git 이 이미 아는 것을 다시 세지 않는다.

    pull 한 번이 들여오는 문서는 보통 몇 개인데, 그 뒤의 전량 재생성은 vault 를
    통째로 다시 읽었다. 여기서 재는 것은 '몇 개를 읽었나' 하나다."""

    def setUp(self):
        super().setUp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "tester")
        self.commit("base")

    def git(self, *argv):
        return subprocess.run(["git", "-C", self.tmp, *argv],
                              capture_output=True, text=True, timeout=30)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def count_reads(self, fn):
        """read_doc 을 세며 fn 을 돌린다 — 전량 재생성이면 이 수가 튄다."""
        reads = []
        real = self.m.read_doc
        self.m.read_doc = lambda p, *a, **k: (reads.append(p),
                                              real(p, *a, **k))[1]
        try:
            out = fn()
        finally:
            self.m.read_doc = real
        return out, reads

    # ---- P1. 바뀐 문서만 다시 읽는다 ------------------------------------
    def test_p1_only_changed_docs_are_reread(self):
        before = self.commit("before")
        with self.m.index_defer():       # pull 이 방금 얹은 자리를 흉내낸다
            self.doc("REQ-20260902-901-zzzz", status="in-progress")
            self.doc("REQ-20260902-905-zzzz")
        after = self.commit("pulled")
        n, reads = self.count_reads(
            lambda: self.m.index_sync_range(before, after))
        self.assertEqual(n, 2, f"바뀐 문서를 {n}건으로 셌다")
        self.assertEqual(len(reads), 2,
                         f"pull 뒤에 문서를 {len(reads)}번 읽었다 — 전량 회귀")
        rows = {r["id"]: r for r in self.m.load_catalog()}
        self.assertIn("REQ-20260902-905-zzzz", rows, "새 문서가 안 들어왔다")
        self.assertEqual(rows["REQ-20260902-901-zzzz"]["status"],
                         "in-progress", "바뀐 상태가 반영되지 않았다")

    # ---- P2. 변경이 너무 많으면 전량이 싸다 ------------------------------
    def test_p2_too_many_changes_falls_back_to_full(self):
        self.m.INDEX_SYNC_MAX = 1
        before = self.commit("before")
        with self.m.index_defer():
            self.doc("REQ-20260902-906-zzzz")
            self.doc("REQ-20260902-907-zzzz")
        after = self.commit("many")
        calls = []
        real = self.m.rebuild_index
        self.m.rebuild_index = lambda *a, **k: (calls.append(1),
                                                real(*a, **k))[1]
        try:
            n = self.m.index_sync_range(before, after)
        finally:
            self.m.rebuild_index = real
        self.assertEqual(n, -1, "전량으로 물러나지 않았다")
        self.assertEqual(len(calls), 1, "전량 재생성이 불리지 않았다")
        self.assertIn("REQ-20260902-906-zzzz", self.ids(),
                      "물러난 전량이 새 문서를 안 담았다")

    # ---- P3. 잴 수 없으면 전량으로 물러난다 ------------------------------
    def test_p3_unusable_range_falls_back(self):
        with self.m.index_defer():
            self.doc("REQ-20260902-908-zzzz")
        for base in ("", "nosuchrev"):
            self.assertEqual(self.m.index_sync_range(base), -1,
                             f"기준 '{base}' 에서 전량으로 안 물러났다")
        self.assertIn("REQ-20260902-908-zzzz", self.ids(),
                      "물러난 전량이 목록을 되찾지 못했다")

    # ---- P4. 범위 증분 결과가 전량과 같다 --------------------------------
    def test_p4_range_result_equals_full(self):
        before = self.commit("before")
        with self.m.index_defer():
            self.doc("REQ-20260902-909-zzzz", status="done", tags=["x"])
            self.doc("REQ-20260902-901-zzzz", status="in-progress",
                     user="other")
        after = self.commit("pulled")
        self.m.index_sync_range(before, after)
        incr = self.m.load_catalog()
        self.m.rebuild_index(quiet=True, full=True)
        self.assertEqual(incr, self.m.load_catalog(),
                         "pull 증분이 만든 목록이 전량 재생성과 다르다")

    # ---- P5. 남이 지운 문서는 내 목록에서도 내려간다 ---------------------
    def test_p5_deleted_doc_leaves_the_list(self):
        did = "REQ-20260902-902-zzzz"
        before = self.commit("before")
        with self.m.index_defer():
            os.remove(self.path_of(did))
        after = self.commit("removed")
        self.assertEqual(self.m.index_sync_range(before, after), 1)
        self.assertNotIn(did, self.ids(),
                         "남이 지운 문서가 목록에 남아 있다")


class Window(Base):
    """§4. 기본 응답 창 — 닫힌 요청만 최근 것으로 자른다.

    2만 문서에서 행당 ~920 바이트면 응답이 18MB 다. 보드는 어차피 하루 지난
    완료를 화면에서 내리므로 그 행들은 보내는 순간부터 버려지는 바이트다."""

    def rows(self, closed=6):
        out = [{"id": "DOC-k1", "type": "knowledge", "status": "published",
                "status_since": "2026-01-01T00:00:00+09:00"},
               {"id": "SES-s1", "type": "session", "status": "published",
                "status_since": "2026-01-01T00:00:00+09:00"},
               {"id": "REQ-open1", "type": "request", "status": "open",
                "status_since": "2026-01-01T00:00:00+09:00"},
               {"id": "REQ-open2", "type": "request", "status": "blocked",
                "status_since": "2026-01-01T00:00:00+09:00"}]
        for i in range(closed):
            out.append({"id": f"REQ-c{i}", "type": "request",
                        "status": "done" if i % 2 else "cancelled",
                        "status_since": f"2026-09-{i + 1:02d}T00:00:00+09:00"})
        return out

    # ---- W1. all 은 전량이다 --------------------------------------------
    def test_w1_all_window_sends_everything(self):
        rows = self.rows()
        self.assertEqual(self.m.catalog_window(rows, "all"), rows)

    # ---- W2. 기본 창은 진행 중인 일을 자르지 않는다 -----------------------
    def test_w2_board_window_keeps_every_open_request(self):
        self.m.CATALOG_BOARD_CLOSED = 2
        sent = {r["id"] for r in self.m.catalog_window(self.rows(), "board")}
        for keep in ("REQ-open1", "REQ-open2"):
            self.assertIn(keep, sent,
                          f"{keep} 가 잘렸다 — 진행 중인 일은 창 밖이 없다")
        # 나머지는 최근 것만: 오래된 knowledge·session 은 내려간다
        self.assertEqual(sent - {"REQ-open1", "REQ-open2"},
                         {"REQ-c5", "REQ-c4"},
                         "닫힌 것을 최근 것부터 남기지 않았다")
        self.assertNotIn("DOC-k1", sent, "창이 오래된 문서를 안 잘랐다 — "
                                         "응답이 vault 크기를 따라간다")

    # ---- W3. 선 아래에서는 아무것도 자르지 않는다 -------------------------
    def test_w3_below_the_line_is_a_no_op(self):
        self.m.CATALOG_BOARD_CLOSED = 400
        rows = self.rows()
        self.assertEqual(self.m.catalog_window(rows, "board"), rows,
                         "자를 것이 없는데 목록이 바뀌었다")


class WindowScreen(unittest.TestCase):
    """창을 고르는 쪽은 화면이다 — 그 계약을 원문에서 확인한다.

    실측한 결함 하나가 여기 붙어 있다: 첫 부팅은 카탈로그를 라우트보다 먼저
    부른다. `catalogWantsAll` 이 `tab` 만 보면 `#docs` 로 바로 들어온 화면이
    잘린 목록을 받아 문서 수를 419/929 로 적었다 — 15초 뒤 폴링이 고치지만
    그 사이 화면은 틀린 수를 사실처럼 말한다."""

    @staticmethod
    def read(name):
        with open(os.path.join(HERE, "..", "web", "app", name),
                  encoding="utf-8") as f:
            return f.read()

    def test_v1_the_belt_asks_for_a_window(self):
        src = self.read("app.js")
        self.assertIn("catalogWantsAll", src, "창을 고르는 자리가 없다")
        self.assertIn("window=all", src, "전량을 부르는 길이 없다")

    def test_v2_the_hash_is_read_before_the_route_lands(self):
        src = self.read("app.js")
        fn = src.split("function catalogWantsAll(")[1].split("\n}")[0]
        self.assertIn("location.hash", fn,
                      "주소를 안 본다 — 깊은 링크 첫 판이 잘린 목록을 받는다")
        self.assertIn("selectedDoc", fn,
                      "열려는 문서를 안 본다 — 첫 판에서 축약 참조가 안 풀린다")

    def test_v3_the_archive_is_never_windowed(self):
        src = self.read("tidy.js")
        line = [l for l in src.splitlines() if "archived=1" in l][0]
        self.assertIn("window=all", line,
                      "보관함이 창에 걸린다 — 오래 전에 치운 문서가 사라진다")


class WindowServed(unittest.TestCase):
    """§4 를 서버가 실제로 지키는가 — 창·헤더·창별 캐시.

    창을 씌우는 자리가 캐시 뒤에 있으면 두 창이 서로의 본문을 받는다. 그
    어긋남은 화면에서 '문서가 사라졌다'로만 보인다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9win-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_PORT_GUARD": "off", "S9_CATALOG_BOARD_CLOSED": "2"}
        cls.env.pop("S9_SESSION", None)
        cls.run9("init")
        cls.run9("user", "add", "alice")
        for i in range(5):
            cls.run9("new", "request", "--title", f"창 시험 {i}",
                     "--summary", "t", "--goal", "t", "--size", "S",
                     "--user", "alice", "--body", "x" * 200)
        # 넷을 닫는다(기본 창의 상한은 2) — open→cancelled 는 한 걸음이다
        for did in sorted(cls.doc_ids())[:4]:
            cls.run9("status", did, "cancelled", "--note", "창 시험",
                     "--user", "alice")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def run9(cls, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=cls.env, timeout=30)

    @classmethod
    def doc_ids(cls):
        out = []
        for dirpath, _, names in os.walk(os.path.join(cls.tmp, "vault")):
            out += [n[:-3] for n in names
                    if n.endswith(".md") and n.startswith("REQ-")]
        return out

    def get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, dict(r.headers), json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), None

    # ---- W4. 기본 응답은 창을 쓰고, 그 사실을 헤더로 말한다 ---------------
    def test_w4_default_response_is_windowed(self):
        code, hdr, body = self.get("/api/catalog")
        self.assertEqual(code, 200)
        self.assertIsInstance(body, list, "응답이 배열이 아니다 — 클라이언트 "
                                          "계약(Array.isArray)이 깨진다")
        win = hdr.get("X-S9-Catalog-Window", "")
        self.assertTrue(win.startswith("board "), f"창 헤더가 없다: {win!r}")
        sent, total = win.split()[1].split("/")
        self.assertEqual(len(body), int(sent))
        self.assertLess(int(sent), int(total), "아무것도 안 잘렸다")
        _, _, every = self.get("/api/catalog?window=all")
        openw = {r["id"] for r in every if self.is_open(r)}
        got = {r["id"] for r in body}
        self.assertTrue(openw, "시험 자료에 진행 중인 요청이 없다")
        self.assertTrue(openw <= got, "진행 중인 요청이 잘려 나갔다")
        self.assertEqual(len([r for r in body if not self.is_open(r)]), 2,
                         "기본 창이 상한(2)을 안 지켰다")

    @staticmethod
    def is_open(r):
        return (r.get("type") == "request"
                and r.get("status") not in ("done", "cancelled"))

    # ---- W5. window=all 은 전량이고, 두 창이 섞이지 않는다 ---------------
    def test_w5_all_window_and_no_cache_crosstalk(self):
        _, _, board1 = self.get("/api/catalog")
        _, hdr, everything = self.get("/api/catalog?window=all")
        _, _, board2 = self.get("/api/catalog")
        self.assertTrue(hdr.get("X-S9-Catalog-Window", "").startswith("all "))
        self.assertGreater(len(everything), len(board1),
                           "window=all 이 전량을 안 줬다")
        self.assertEqual(len(board1), len(board2),
                         "기본 창이 all 의 본문을 받았다 — 캐시 키에 창이 없다")


if __name__ == "__main__":
    unittest.main()
