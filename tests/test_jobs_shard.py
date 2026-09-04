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


class ProgressWhileRunning(unittest.TestCase):
    """도는 중은 도는 것으로 보인다 (REQ-20260904-004).

    예전엔 `--jobs` 모드의 진행이 **샤드가 끝날 때만** 올라갔다. 샤드 하나가
    5분 넘게 도니 그동안 잡 파일의 mtime 이 멈췄고, 화면은 그 mtime 으로
    「N초 잠잠」을 그렸다 — 멀쩡히 도는 것과 멈춘 것이 같아 보이면, 진짜로
    멈춘 날에 아무도 알아채지 못한다. 2026-09-04 에 그 착각으로 1시간 41분.

    실행: python3 tests/ jobs_shard
    """

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    class _Out:
        def __init__(self, name):
            self.name = name

    def _pending(self, text, group):
        import tempfile
        fh = tempfile.NamedTemporaryFile(mode="w", suffix=".shard",
                                         delete=False, encoding="utf-8")
        fh.write(text)
        fh.close()
        self.addCleanup(lambda: os.path.exists(fh.name) and os.unlink(fh.name))
        return [(None, self._Out(fh.name), group)]

    def test_p2_progress_moves_before_a_shard_finishes(self):
        """P2. 샤드가 끝나기 전에도 시작된 파일이 세어진다."""
        out = ("test_a (test_alpha.A.test_a) ... ok\n"
               "test_b (test_alpha.A.test_b) ... ok\n"
               "test_c (test_beta.B.test_c) ... ok\n")
        pend = self._pending(out, ["test_alpha.py", "test_beta.py",
                                   "test_gamma.py"])
        self.assertEqual(self.m._started_in(pend, {}), 2)

    def test_p4_progress_never_exceeds_the_shard(self):
        """P4. 샤드에 담긴 파일 수를 넘지 않는다 — 화면의 분모가 깨진다."""
        out = "".join(f"t (test_x{i}.C.t) ... ok\n" for i in range(9))
        pend = self._pending(out, ["test_x0.py", "test_x1.py"])
        self.assertEqual(self.m._started_in(pend, {}), 2)

    def test_p5_an_unreadable_shard_is_zero_not_a_crash(self):
        """P5. 출력을 못 읽어도 러너가 죽지 않는다 — 표시가 실행을 죽이면 본말전도."""
        pend = [(None, self._Out(os.path.join(HERE, "no-such-shard.out")),
                 ["test_a.py"])]
        self.assertEqual(self.m._started_in(pend, {}), 0)

    def test_p6_only_the_new_bytes_are_read(self):
        """P6. 두 번째부터는 **늘어난 만큼만** 읽는다.

        처음엔 매번 통째로 읽었는데, 출력이 수 MB 로 자라는 후반에는 그것이
        초당 두 번씩 수십 MB 를 읽고 정규식을 다시 거는 일이 됐다 — 진행
        표시가 샤드에게서 CPU 를 뺏어 스위트가 420초에서 585초 밖으로 밀렸다
        (실측 2026-09-04, 같은 나무에서 두 번 시간 초과). 재는 행위가 재려는
        대상을 느리게 만들면 그 표시는 거짓말이 된다.
        """
        filler = "".join(f"t (test_alpha.A.t{i}) ... ok\n" for i in range(40))
        pend = self._pending(filler, ["test_alpha.py", "test_beta.py"])
        state = {}
        self.assertEqual(self.m._started_in(pend, state), 1)
        name = pend[0][1].name
        # 겹쳐 읽는 200자를 뺀 만큼은 이미 지나갔다 — 다음엔 통째로 안 읽는다.
        self.assertGreater(state[name][0], 0)
        with open(name, "a", encoding="utf-8") as fh:
            fh.write("t (test_beta.B.t) ... ok\n")
        # 이어서 읽어도 앞에서 본 것을 잊지 않는다.
        self.assertEqual(self.m._started_in(pend, state), 2)

    def test_p1_the_loop_bumps_every_turn_not_only_on_completion(self):
        """P1. 폴링 한 바퀴마다 진행을 올린다 — 잡 파일 mtime 이 끊기지 않는다.

        글자가 아니라 자리를 본다: `bump(` 호출이 `poll()` 을 보기 **전에**
        한 번 있어야 한다.
        """
        src = open(RUNNER, encoding="utf-8").read()
        body = src.split("def run_sharded", 1)[1]
        loop = body.split("while pending:", 1)[1].split("for pr, out, group", 1)[0]
        self.assertIn("bump(", loop,
                      "샤드 완료를 기다려야만 진행이 올라간다 — 「잠잠」이 다시 거짓말한다")
