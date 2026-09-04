"""--jobs N 병렬 샤딩 — 느린 것부터, 실패는 숨지 않게 (REQ-20260830-027 2단계).

실행: python3 tests/ jobs_shard
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "__main__.py")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9runner_j", importlib.machinery.SourceFileLoader(
            "s9runner_j", RUNNER))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TheShard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_the_shard(self):
        """TheShard 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("p1_greedy_by_size_covers_every_file_once"):
            files = ["test_wake.py", "test_graph_empty.py", "test_stall_pair.py",
                     "test_platform_live.py", "test_heartbeat.py"]
            bins = self.m.shard(files, 3)
            flat = [f for b in bins for f in b]
            self.assertEqual(sorted(flat), sorted(files), "빠지거나 겹친 파일")
            self.assertLessEqual(len(bins), 3)
            # 각 빈의 첫 파일은 그 빈에서 가장 크다 — 느린 것부터 자리 잡는다
            for b in bins:
                sizes = [os.path.getsize(os.path.join(HERE, f)) for f in b]
                self.assertEqual(sizes[0], max(sizes))
        with self.subTest("p2_serial_files_stay_out_of_shards"):
            # SERIAL 은 공유 상태를 만진다 — 본대에 섞이면 서로 밟는다.
            for f in self.m.SERIAL:
                self.assertTrue(os.path.exists(os.path.join(HERE, f)),
                                f"SERIAL 목록의 파일이 실재하지 않는다: {f}")
            src = open(RUNNER, encoding="utf-8").read()
            self.assertIn('body = [f for f in files if f not in SERIAL]', src)
            self.assertIn('tail = [f for f in files if f in SERIAL]', src)
        with self.subTest("p3_children_are_nested"):
            src = open(RUNNER, encoding="utf-8").read()
            self.assertIn('"S9_TESTS_NESTED": "1"', src,
                          "자식이 nested 가 아니면 reap·잡파일을 부모와 다툰다")
        with self.subTest("p4_failed_shard_replays_its_output"):
            src = open(RUNNER, encoding="utf-8").read()
            self.assertIn("실패한 샤드", src)
            i = src.index("def run_sharded")
            j = src.index("\ndef ", i + 10)
            seg = src[i:j]
            self.assertIn("pr.returncode != 0", seg)
            self.assertIn("sys.stderr.write", seg,
                          "실패한 자식의 원출력을 재생하지 않는다 — 실패가 숨는다")
        with self.subTest("p5_jobs_gate_only_above_one"):
            src = open(RUNNER, encoding="utf-8").read()
            self.assertIn("if jobs > 1 and not nested:", src,
                          "--jobs 1 이 직렬 현행 경로를 벗어난다")
        with self.subTest("p1b_live_two_shards_run_green"):
            # 실제 자식 둘을 띄운다 — 아주 빠른 모듈 둘만.
            m = self.m
            ok, n = m.run_sharded(["test_*graph_empty*.py",
                                   "test_*doclink_keyboard*.py"], 2)
            self.assertTrue(ok, "빠른 두 샤드가 green 이 아니다")
            self.assertGreaterEqual(n, 2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
