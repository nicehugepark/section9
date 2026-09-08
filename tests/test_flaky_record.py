"""간헐 실패(flaky)를 삼키지 않고 남기는지 — 러너의 계측 (REQ-20260908-006).

러너는 실패한 파일이 셋 이하면 그것만 한 번 더 돈다. 예전에는 그 재실행이
**통째로** 통과했을 때만 기록했고, 그래서 셋 중 하나가 진짜 결함이면 나머지
둘의 간헐 실패는 한 줄도 남지 않았다. 여기서 재는 것은 셋이다: 무엇이
뒤집혔는지 고르는가 · 파일마다 한 줄씩 sha·시도 횟수와 함께 남는가 ·
읽는 자리(--flaky)가 옛 줄과 새 줄을 함께 세는가.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import shutil
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_runner = os.path.join(_here, "__main__.py")


def _load():
    """러너를 모듈로 읽어 들인다 — 부작용 없이 도우미만 부르려는 것이다."""
    sys.path.insert(0, _here)
    try:
        spec = importlib.util.spec_from_loader(
            "s9_runner_flaky", importlib.machinery.SourceFileLoader(
                "s9_runner_flaky", _runner))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if sys.path and sys.path[0] == _here:
            sys.path.pop(0)


class FlakyRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9flaky-")
        self.path = os.path.join(self.tmp, "state", "test-flaky.jsonl")
        self._keep = self.m.FLAKY_FILE
        self.m.FLAKY_FILE = self.path        # 실제 저장소의 기록을 더럽히지 않는다
        self.addCleanup(setattr, self.m, "FLAKY_FILE", self._keep)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _lines(self):
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    # ① 정상 — 파일마다 한 줄, sha·파일 이름·몇 번째 시도·어디서
    def test_record_writes_one_line_per_file(self):
        self.m.record_flaky(["test_a.py", "test_b.py"], "샤드에서 실패 · 단독 실행은 통과",
                            sha="abc1234deadbeef", attempt=2, where="원격")
        rows = self._lines()
        self.assertEqual([r["file"] for r in rows], ["test_a.py", "test_b.py"])
        for r in rows:
            self.assertEqual(r["sha"], "abc1234")      # 7자로 줄여 남긴다
            self.assertEqual(r["attempt"], 2)
            self.assertEqual(r["where"], "원격")
            self.assertGreater(float(r["ts"]), 0)

    # ② 정상 — 재실행 출력에서 뒤집힌 것만 고른다
    def test_flipped_picks_only_reversed(self):
        out = ("FAIL: test_x (test_b.TheCase.test_x)\n"
               "AssertionError: 1 != 2\n")
        self.assertEqual(
            self.m.flipped_files(["test_a.py", "test_b.py", "test_c.py"], out),
            ["test_a.py", "test_c.py"])
        self.assertEqual(self.m.flipped_files(["test_a.py"], ""), ["test_a.py"])

    # ③ 경계 — 재실행이 통째로는 실패해도 뒤집힌 것은 남는다 (삼키던 자리)
    def test_partial_flip_is_recorded(self):
        out = "ERROR: test_y (test_b.TheCase.test_y)\n"
        flipped = self.m.flipped_files(["test_a.py", "test_b.py"], out)
        self.m.record_flaky(flipped, "샤드에서 실패 · 단독 실행은 통과", sha="0000000")
        self.assertEqual([r["file"] for r in self._lines()], ["test_a.py"])

    # ④ 경계 — 옛 형식·새 형식을 함께 세고, 기간 밖은 뺀다
    def test_read_counts_old_and_new_within_window(self):
        now = time.time()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": now - 3600,
                                "files": ["test_a.py", "test_b.py"]}) + "\n")
            f.write(json.dumps({"ts": now - 7200, "file": "test_a.py",
                                "sha": "abc1234"}) + "\n")
            f.write(json.dumps({"ts": now - 40 * 86400, "file": "test_old.py"}) + "\n")
        rows = self.m.read_flaky(days=14, now=now, path=self.path)
        self.assertEqual([(r[0], r[1]) for r in rows],
                         [("test_a.py", 2), ("test_b.py", 1)])
        self.assertEqual(rows[0][3], ["abc1234"])

    # ⑤ 실패경로 — 깨진 줄·없는 파일에도 죽지 않는다
    def test_report_survives_broken_input(self):
        buf = io.StringIO()
        self.assertEqual(self.m.flaky_report(days=14, out=buf), 0)   # 파일 자체가 없다
        self.assertIn("기록 없음", buf.getvalue())
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{깨진 줄\n\n")
            f.write(json.dumps({"ts": time.time(), "file": "test_a.py"}) + "\n")
        buf = io.StringIO()
        self.assertEqual(self.m.flaky_report(days=14, out=buf), 0)
        self.assertIn("test_a.py", buf.getvalue())

    # ⑥ 회귀 — 원격이 찍는 표식의 글자와 걷는 쪽의 글자가 같다
    def test_mark_roundtrip_matches_remote(self):
        sys.path.insert(0, _here)
        try:
            import remote_run
        finally:
            if sys.path and sys.path[0] == _here:
                sys.path.pop(0)
        self.assertEqual(self.m.FLAKY_MARK, remote_run.FLAKY_MARK)
        files = ["test_a.py", "test_b.py"]
        line = self.m.FLAKY_MARK + " ".join(files)
        self.assertTrue(line.startswith(remote_run.FLAKY_MARK))
        self.assertEqual(line[len(remote_run.FLAKY_MARK):].split(), files)


if __name__ == "__main__":
    unittest.main()
