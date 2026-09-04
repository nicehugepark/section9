"""카탈로그 원자적 갱신 테스트 (REQ-20260825-049).

rebuild_index는 catalog.jsonl을 제자리에서 truncate+재작성하면 안 된다 —
대시보드 폴링이 그 순간 읽으면 부분 목록(카드가 늘었다 사라짐)이 보인다.
tmp+os.replace로 항상 완전한 스냅샷만 노출되는지 동시 읽기로 검증한다.

실행: python3 tests/ catalog_atomic
"""
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class TestCatalogAtomic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9cat-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")
        for i in range(12):
            cls.cli("new", "request", "--title", f"문서 {i}", "--summary", "s",
                    "--size", "S", "--body", "b")
        cls.catalog = os.path.join(cls.tmp, "index", "catalog.jsonl")

    @classmethod
    def cli(cls, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=20, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    def read_rows(self):
        with open(self.catalog, encoding="utf-8") as f:
            return [json.loads(x) for x in f.read().splitlines() if x.strip()]

    # A1. 원자 교체 계약: 재생성은 새 파일로 갈아끼운다(inode 변경) —
    #     제자리 truncate면 inode가 그대로다. 경합 타이밍에 의존하지 않는
    #     결정적 검증(REQ-20260825-049).
    def test_test_catalog_atomic(self):
        """TestCatalogAtomic 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_atomic_replace_semantics"):
                before = os.stat(self.catalog).st_ino
                self.cli("index", "rebuild")
                after = os.stat(self.catalog).st_ino
                self.assertNotEqual(before, after,
                                    "catalog.jsonl이 제자리 재작성됐다 — 부분 읽기 창이 열린다")

            # A3. 동시 읽기 스모크: 재생성 중에도 파싱 실패·행 손실이 없다
        with self.subTest("a3_no_partial_snapshot"):
                full = len(self.read_rows())
                self.assertGreaterEqual(full, 12)
                seen, errs, stop = [], [], threading.Event()

                def reader():
                    while not stop.is_set():
                        try:
                            seen.append(len(self.read_rows()))
                        except Exception as ex:      # 부분 스냅샷 = 파싱 실패/행 손실
                            errs.append(repr(ex))
                        time.sleep(0.002)

                t = threading.Thread(target=reader)
                t.start()
                try:
                    for _ in range(5):
                        self.cli("index", "rebuild")
                finally:
                    stop.set()
                    t.join(timeout=5)
                self.assertFalse(errs, errs[:3])
                self.assertTrue(seen, "동시 읽기가 수행되지 않았다")
                self.assertEqual(set(seen), {full},
                                 f"부분 목록 관측: {sorted(set(seen))} (기대 {full})")

            # A2. 임시 파일이 남지 않는다
        with self.subTest("a2_no_tmp_leftover"):
            self.cli("index", "rebuild")
            self.assertFalse(os.path.exists(self.catalog + ".tmp"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
