"""워처가 멎으면 보인다 (REQ-20260916-006-62x6).

실제 사고 2026-09-16: 서버가 멎어 **9시간 10분**(09-15 23:07 ~ 09-16 08:17)
동안 워처 회차가 한 번도 없었다. 그 사이 이 컴퓨터 몫 open 요청 아홉이 아무도
집지 않은 채 있었는데 **보드에도 doctor 에도 아무 표시가 없었다** — 조용한 것과
멎은 것이 밖에서 같아 보였고, 사람은 다음 날 아침에야 알았다.

그래서 회차마다 자취 한 줄을 덮어 쓰고(쌓지 않는다), doctor 가 그 나이를 읽는다.
**끈 것은 고장이 아니다** — 맡기기가 꺼져 있으면 「멎었다」가 아니라 「꺼져
있다」로 말한다. 끈 것을 고장이라 하면 그다음부터 아무도 이 줄을 안 읽는다.

실행: python3 tests/ watcher_beat
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TheWatcherLeavesATrace(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9beat-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.environ["S9_ROOT"] = self.root
        self.addCleanup(os.environ.pop, "S9_ROOT", None)
        self.m = _load("s9_beat", S9)
        os.makedirs(self.m._auto_dir(), exist_ok=True)
        self.d = _load("s9_doctor_beat", DOCTOR)

    def beat(self, at):
        with open(os.path.join(self.m._auto_dir(), "watch-beat.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"last": at}, f)

    def user(self, auto):
        p = os.path.join(self.root, "users", "someone")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"auto_resume": auto}, f)

    # w1 — 오래 지났으면 말한다
    def test_w1_a_long_silence_is_reported(self):
        self.user("on")
        self.beat(1_700_000_000.0)
        w = self.d.watcher_info(root=self.root, now=1_700_000_000.0 + 9 * 3600)
        self.assertEqual("critical", self.d.watcher_verdict(w).get("level"), w)
        self.assertIn("540분", self.d.watcher_verdict(w).get("line", ""))

    # w1' — 조금 지난 것은 경고까지
    def test_w1b_a_short_silence_is_only_a_warning(self):
        self.user("on")
        self.beat(1_700_000_000.0)
        w = self.d.watcher_info(root=self.root, now=1_700_000_000.0 + 600)
        self.assertEqual("warn", self.d.watcher_verdict(w).get("level"), w)

    # w2 — 방금 돌았으면 아무 일도 아니다
    def test_w2_a_fresh_round_says_nothing_is_wrong(self):
        self.user("on")
        self.beat(1_700_000_000.0)
        w = self.d.watcher_info(root=self.root, now=1_700_000_000.0 + 20)
        self.assertEqual("ok", self.d.watcher_verdict(w).get("level"), w)

    # w3 — 끈 것은 고장이 아니다
    def test_w3_a_switched_off_watcher_is_not_called_broken(self):
        self.user("off")
        self.beat(1_700_000_000.0)
        w = self.d.watcher_info(root=self.root, now=1_700_000_000.0 + 9 * 3600)
        v = self.d.watcher_verdict(w)
        self.assertEqual("ok", v.get("level"), v)
        self.assertIn("꺼져 있다", v.get("line", ""))

    # 경계 — 자취가 아예 없으면 「멎었다」가 아니라 「돈 적이 없다」
    def test_no_trace_at_all_is_told_apart_from_a_stall(self):
        self.user("on")
        v = self.d.watcher_verdict(self.d.watcher_info(root=self.root))
        self.assertEqual("warn", v.get("level"), v)
        self.assertIn("자취가 없다", v.get("line", ""))

    # 회차가 실제로 자취를 남긴다 — 그리고 쌓지 않는다
    def test_each_round_overwrites_one_line(self):
        self.m._watch_beat(1_700_000_000.0)
        self.m._watch_beat(1_700_000_030.0)
        p = os.path.join(self.m._auto_dir(), "watch-beat.json")
        with open(p, encoding="utf-8") as f:
            self.assertEqual(1_700_000_030.0, json.load(f)["last"])
        self.assertLess(os.path.getsize(p), 200, "자취가 쌓인다")

    def test_the_age_is_read_back(self):
        self.m._watch_beat(1_700_000_000.0)
        self.assertAlmostEqual(
            120.0, self.m.watch_beat_age(now=1_700_000_120.0), places=1)
        os.remove(os.path.join(self.m._auto_dir(), "watch-beat.json"))
        self.assertIsNone(self.m.watch_beat_age())


if __name__ == "__main__":
    unittest.main()
