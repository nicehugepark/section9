"""원격 전체 통과는 트리가 더러워도 commit 의 사실이다 (REQ-20260906-061).

지문 기록(mark_green)은 더러운 트리에서 생략해야 맞지만, 붉음 라쳇이 보는
「마지막 초록 시각」까지 없어지면 다음 code 커밋이 옛 붉음에 계속 막힌다
(실측 2026-09-06 12:19). 시각 기록은 따로 남긴다.

실행: python3 tests/ full_green_record
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "__main__.py")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9runner_fg", importlib.machinery.SourceFileLoader("s9runner_fg", RUNNER))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FullGreenRecord(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.d = tempfile.mkdtemp(prefix="s9fg-")
        self.m.REUSE_DIR = os.path.join(self.d, "state", "tests-green")
        self.m.FULL_GREEN = os.path.join(self.d, "state", "tests-full-green.json")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    # F1. 지문 기록이 없어도 시각 기록만으로 나이가 나온다 — sha 가 남는다
    def test_f1_time_record_alone_counts(self):
        self.assertIsNone(self.m.full_green_age())
        self.m.record_full_green("ae99971deadbeef")
        age = self.m.full_green_age()
        self.assertIsNotNone(age)
        self.assertLess(age, 5.0)
        rec = json.load(open(self.m.FULL_GREEN, encoding="utf-8"))
        self.assertEqual(rec["sha"], "ae99971")

    # F2. 둘 다 있으면 새것을 센다 — 옛 지문 기록이 새 통과를 가리지 않는다
    def test_f2_the_newer_of_the_two_wins(self):
        os.makedirs(self.m.REUSE_DIR, exist_ok=True)
        with open(self.m._reuse_path(self.m.patterns([])), "w", encoding="utf-8") as f:
            json.dump({"fingerprint": "x", "at": time.time() - 3600, "n": 0}, f)
        self.assertGreater(self.m.full_green_age(), 3000)
        self.m.record_full_green("abc1234")
        self.assertLess(self.m.full_green_age(), 5.0)

    # F3. 붉음 뒤의 시각 기록이면 라쳇이 열린다 — 게이트가 실제로 읽는 값
    def test_f3_a_red_older_than_the_time_record_does_not_block(self):
        self.m.LAST_RED = os.path.join(self.d, "state", "tests-last-red.json")
        self.m.record_last_red(["test_x.py"], "fp")
        time.sleep(0.05)
        self.m.record_full_green("abc1234")
        red = self.m.last_red()
        green_at = time.time() - self.m.full_green_age()
        self.assertGreaterEqual(green_at, float(red["at"]))


if __name__ == "__main__":
    unittest.main()
