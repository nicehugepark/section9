"""tombstone 문서 은닉 테스트 (REQ-20260825-051).

s9 rm은 문서를 지우지 않고 .trash로 옮긴다(발번 재사용 방지, REQ-031).
그 문서가 목록·보드에 되살아나면 안 된다 — 재생성 제외(walk_docs)에 더해
조회 단계(load_catalog)에서도 배제되는지, 즉 낡은 카탈로그가 섞여도
안전한지 검증한다.

실행: python3 tests/ tombstone_hidden
"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class TestTombstoneHidden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9tomb-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=20, stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    def catalog_ids(self):
        # 증분 카탈로그(REQ-20260902-035) 뒤로 base 파일 하나만 읽으면
        # 방금 만든 문서가 빠진다 — 병합된 문으로 묻는다.
        return [json.loads(x)["id"]
                for x in self.cli("index", "cat").splitlines() if x.strip()]

    def ls_ids(self):
        return self.cli("ls")

    # T1. rm된 문서는 카탈로그·목록에서 사라진다
    def test_t1_removed_hidden(self):
        rid = self.cli("new", "request", "--title", "삭제 대상", "--summary", "s",
                       "--size", "S", "--body", "b").split()[0]
        self.assertIn(rid, self.catalog_ids())
        self.cli("rm", rid, "--reason", "test")
        self.assertNotIn(rid, self.catalog_ids())
        self.assertNotIn(rid, self.ls_ids())

    # T2. 낡은 카탈로그에 tombstone 행이 섞여도 조회에서 배제된다(이중 방어)
    def test_t2_stale_catalog_row_ignored(self):
        rid = self.cli("new", "request", "--title", "좀비 후보", "--summary", "s",
                       "--size", "S", "--body", "b").split()[0]
        cat = os.path.join(self.tmp, "index", "catalog.jsonl")
        with open(cat, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f.read().splitlines() if x.strip()]
        self.cli("rm", rid, "--reason", "test")
        # 삭제 전 스냅샷(그 문서 행이 살아 있는 낡은 카탈로그)을 되돌려 놓는다
        with open(cat, "w", encoding="utf-8") as f:
            for r in rows:
                if r["id"] == rid:            # 낡은 경로(.trash 이전) 그대로
                    r["path"] = r["path"].replace(
                        os.path.basename(r["path"]),
                        ".trash/" + os.path.basename(r["path"]))
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        self.assertNotIn(rid, self.ls_ids())   # 조회 단계에서 배제


if __name__ == "__main__":
    unittest.main(verbosity=2)
