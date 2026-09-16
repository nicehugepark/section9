"""같은 사유는 되풀이 적지 않는다 (REQ-20260916-006-62x6).

실측 2026-09-16 09시대, 한 시간: `state/auto_resume/spawn.log` 에 **1,090줄**이
쌓였고 그중 같은 글자가 **105번씩** 되풀이됐다(요청 다섯 × 105). 파일은
1.9MB · 19,806줄이었다. 워처가 30초마다 같은 거절을 다시 적는데 물러남이 없다.

접되 **입은 막지 않는다**: 되풀이가 이어져도 10분에 한 줄은 적는다 — 조용한
것과 멎은 것이 밖에서 같아 보이면, 사람은 워처가 죽은 것을 9시간 동안 모른다
(같은 요청의 결함 ①이 바로 그것이다).

바꾸는 것은 **적는 법**이고 스폰 판정은 한 글자도 바꾸지 않는다.

실행: python3 tests/ spawn_log_backoff
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class TheSameReasonIsNotWrittenTwice(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9spawnlog-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.environ["S9_ROOT"] = self.root
        self.addCleanup(os.environ.pop, "S9_ROOT", None)
        spec = importlib.util.spec_from_loader(
            "s9_spawnlog", importlib.machinery.SourceFileLoader("s9_spawnlog", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        os.makedirs(self.m._auto_dir(), exist_ok=True)
        self.t = 1_700_000_000.0

    def lines(self):
        p = os.path.join(self.m._auto_dir(), "spawn.log")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [ln for ln in f.read().splitlines() if ln.strip()]

    def log(self, msg, after=0.0):
        self.t += after
        self.m._auto_log(msg, now=self.t)

    CAP = "HERE-SKIP(capped) REQ-20260916-006-62x6 이번 시간에 다 썼습니다"

    # c1 — 잇따른 같은 글자는 접힌다
    def test_c1_a_repeated_reason_is_written_once(self):
        for _ in range(105):
            self.log(self.CAP, after=1)      # 한 숨 돌림 안(105초 < 10분)
        self.assertEqual(len(self.lines()), 1,
                         "105번 되풀이가 그대로 쌓였다:\n" + "\n".join(self.lines()[:3]))

    # c1' — 그날 그 모양 그대로: 30초마다 105번이면 105줄이 아니라 손에 꼽는다
    def test_c1b_the_measured_run_collapses_to_a_handful(self):
        for _ in range(105):
            self.log(self.CAP, after=30)     # 52분치 — 그날 요청 하나의 몫
        got = self.lines()
        self.assertLessEqual(len(got), 6,
                             "105줄이 %d줄로밖에 안 줄었다" % len(got))
        self.assertGreaterEqual(len(got), 2, "52분 동안 아무 말도 안 한다")

    # c2 — 10분마다 한 줄은 적는다 (조용한 것과 멎은 것을 가른다)
    def test_c2_a_long_run_still_says_something_every_ten_minutes(self):
        for _ in range(60):                      # 30초 × 60 = 30분
            self.log(self.CAP, after=30)
        got = self.lines()
        self.assertGreaterEqual(len(got), 3, got)
        self.assertLessEqual(len(got), 5, "10분마다보다 자주 적는다:\n" + "\n".join(got))
        self.assertIn("같은 사유", got[-1])
        self.assertIn("번째", got[-1])

    # c3 — 글자가 바뀌면 앞의 되풀이를 한 줄로 닫는다
    def test_c3_a_change_closes_the_run_with_a_count(self):
        for _ in range(4):
            self.log(self.CAP, after=30)
        self.log("HERE-SKIP(capped) REQ-20260916-006-62x6 다른 사유", after=30)
        got = self.lines()
        end = [ln for ln in got if "REPEAT-END" in ln]
        self.assertEqual(len(end), 1, got)
        self.assertIn("같은 사유 4번", end[0])
        self.assertIn("~", end[0], "언제부터 언제까지가 없다")
        self.assertTrue(got[-1].endswith("다른 사유"), got)

    # c4 — 요청이 다르면 서로 묻히지 않는다
    def test_c4_two_requests_are_counted_apart(self):
        a = "HERE-SKIP(capped) REQ-20260916-006-62x6 같은 사유"
        b = "HERE-SKIP(capped) REQ-20260916-007-62x6 같은 사유"
        for _ in range(5):
            self.log(a, after=30)
            self.log(b, after=1)
        got = self.lines()
        self.assertEqual(2, len(got), "요청 둘이 서로를 접었다:\n" + "\n".join(got))
        self.assertTrue(any("006" in ln for ln in got), got)
        self.assertTrue(any("007" in ln for ln in got), got)

    # c5 — 기록이 깨져도 로그는 적힌다 (로그가 일을 막지 않는다)
    def test_c5_a_broken_record_does_not_swallow_the_line(self):
        p = os.path.join(self.m._auto_dir(), "spawn-repeat.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{이건 json 이 아니다")
        self.log(self.CAP)
        self.assertEqual(len(self.lines()), 1, self.lines())

    # r1 — 다른 갈래의 줄은 그대로 적힌다
    def test_r1_other_kinds_of_lines_are_untouched(self):
        for msg in ("RUSH REQ-1 긴급이라 바로 띄웠다",
                    "PENDING REQ-2 워처가 유예 후 스폰",
                    "STOP REQ-3 pid=1 by=user:x",
                    "DEFER REQ-4 reason=busy"):
            self.log(msg, after=1)
        got = self.lines()
        self.assertEqual(4, len(got), got)
        for kind in ("RUSH", "PENDING", "STOP", "DEFER"):
            self.assertTrue(any(kind in ln for ln in got), (kind, got))

    # 경계 — 앞 두 낱말이 되풀이를 세는 단위다
    def test_the_key_is_the_first_two_words(self):
        self.assertEqual("HERE-SKIP(capped) REQ-20260916-006-62x6",
                         self.m._auto_log_key(self.CAP))


if __name__ == "__main__":
    unittest.main()
