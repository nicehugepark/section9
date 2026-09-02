"""계기를 부르는 자리에서 사람이 치는 말 (REQ-20260902-059).

`s9 metrics report --at now` 가 파이썬 트레이스백으로 죽었다. 이 명령은
**사고가 난 자리에서** 쓴다 — 그때 "지금"을 가리키려고 가장 먼저 치는 낱말이
now 인데 그것이 안 통하면, 계기가 사고를 하나 더 만든다.

두 계약을 시험한다: ① 받는 말이 넓다(now·지금·HH:MM·ISO) ② 못 알아들은 것에는
스택이 아니라 **받아들이는 형식**으로 답하고 종료코드로 그것을 말한다.

실행: python3 tests/ metrics_at
"""
import datetime
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class MetricsAt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9metat-")
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9metat", importlib.machinery.SourceFileLoader("s9metat", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.now = datetime.datetime(
            2026, 9, 2, 20, 19, 30).astimezone()

    # ---------------------------------------------------------------- 정상
    def test_n1_now_is_now(self):
        """N1. now·지금·현재 는 전부 '지금'이다."""
        for word in ("now", "NOW", " now ", "지금", "현재"):
            got = self.m._metrics_at(word, now=self.now)
            self.assertEqual(got, self.now, word)

    def test_n2_bare_time_is_today(self):
        """N2. `20:19` 는 오늘 20:19:00 이다 — 사고를 보는 창은 대개 오늘이다."""
        got = self.m._metrics_at("20:19", now=self.now)
        self.assertEqual((got.year, got.month, got.day), (2026, 9, 2))
        self.assertEqual((got.hour, got.minute, got.second), (20, 19, 0))
        self.assertEqual(got.tzinfo, self.now.tzinfo)

    def test_n3_iso_is_unchanged(self):
        """N3. ISO 는 종전 그대로 — 고치면서 옛 사용법을 깨지 않는다."""
        got = self.m._metrics_at("2026-09-02T19:30:00+09:00", now=self.now)
        self.assertEqual(got.isoformat(), "2026-09-02T19:30:00+09:00")

    # ---------------------------------------------------------------- 경계
    def test_b1_seconds_are_kept(self):
        """B1. `20:19:30` 은 초까지 그대로 선다."""
        got = self.m._metrics_at("20:19:30", now=self.now)
        self.assertEqual((got.hour, got.minute, got.second), (20, 19, 30))

    def test_b2_absent_is_now(self):
        """B2. --at 을 아예 안 주면 지금 — 종전과 같다."""
        self.assertEqual(self.m._metrics_at(None, now=self.now), self.now)
        self.assertEqual(self.m._metrics_at("", now=self.now), self.now)

    def test_b3_early_hour_stays_today(self):
        """B3. `00:05` 가 어제로 새지 않는다 (날짜는 기준일 그대로)."""
        got = self.m._metrics_at("00:05", now=self.now)
        self.assertEqual((got.year, got.month, got.day), (2026, 9, 2))
        self.assertEqual((got.hour, got.minute), (0, 5))

    def test_b4_naive_iso_gets_local_zone(self):
        """B4. 시간대 없는 ISO 는 이 기계의 시간대로 읽는다 — 표본이 그렇다."""
        got = self.m._metrics_at("2026-09-02T19:30:00", now=self.now)
        self.assertIsNotNone(got.tzinfo)

    # ---------------------------------------------------------------- 실패
    def test_f1_gibberish_raises_plain_error(self):
        """F1. 못 알아들은 말은 ValueError 로 — 부르는 쪽이 사람 말로 옮긴다."""
        with self.assertRaises(ValueError):
            self.m._metrics_at("아무말", now=self.now)

    def test_f2_impossible_clock_is_refused(self):
        """F2. `25:00` 은 모양은 맞아도 시각이 아니다 — 예외가 새지 않는다."""
        for bad in ("25:00", "20:75", "20:19:99"):
            with self.assertRaises(ValueError, msg=bad):
                self.m._metrics_at(bad, now=self.now)

    def test_f3_cli_never_shows_a_traceback(self):
        """F3. 실측 — CLI 가 스택을 내지 않고, 종료코드로 거절을 말한다.

        이 시험이 이 요청의 본체다. 사용자가 실제로 본 화면이 트레이스백이었다.
        """
        env = dict(os.environ, S9_ROOT=self.tmp)
        r = subprocess.run([sys.executable, S9, "metrics", "report",
                            "--at", "아무말"],
                           capture_output=True, text=True, env=env)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("Traceback", r.stdout)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("now", r.stderr)      # 받아들이는 형식을 알려 준다

    def test_f4_cli_accepts_now(self):
        """F4. 실측 — `--at now` 는 그냥 돈다 (rc 0, 스택 없음)."""
        env = dict(os.environ, S9_ROOT=self.tmp)
        r = subprocess.run([sys.executable, S9, "metrics", "report",
                            "--at", "now"],
                           capture_output=True, text=True, env=env)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
