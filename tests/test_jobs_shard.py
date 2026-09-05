"""--jobs N 병렬 샤딩 — 느린 것부터, 실패는 숨지 않게 (REQ-20260830-027 2단계).

실행: python3 tests/ jobs_shard
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
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
        with self.subTest("p1_greedy_by_weight_covers_every_file_once"):
            files = ["test_wake.py", "test_graph_empty.py", "test_stall_pair.py",
                     "test_platform_live.py", "test_heartbeat.py"]
            bins = self.m.shard(files, 3)
            flat = [f for b in bins for f in b]
            self.assertEqual(sorted(flat), sorted(files), "빠지거나 겹친 파일")
            self.assertLessEqual(len(bins), 3)
            # 각 빈의 첫 파일은 그 빈에서 가장 **무겁다** — 느린 것부터 자리
            # 잡아야 꼬리가 짧다. 무게는 크기가 아니라 `_weights` 가 정한다
            # (실측 시간 > 크기, REQ-20260905-001) — 여기서 크기를 다시 못박으면
            # 무게를 고칠 때마다 이 시험이 헛되이 붉어진다.
            w = self.m._weights(files)
            for b in bins:
                self.assertEqual(w[b[0]], max(w[f] for f in b))
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

class PortSlotsFollowJobs(unittest.TestCase):
    """T4. 포트 칸 수가 샤드 수를 따라간다 (REQ-20260905-001).

    칸이 4 로 못박혀 있으면 다섯째 샤드부터 자기 칸이 없어 같은 포트를 두고
    다툰다 — 실측으로 4·6·10 샤드가 전부 ~520초로 평평했던 이유다. 칸을
    맞춘 뒤 6→343 · 8→317 · 10→295초.
    """

    def test_t4_the_pool_widens_with_the_slots(self):
        """칸을 10 으로 주면 풀도 따라 넓어지고, 칸마다 자리가 남는다."""
        code = ("import portpool as p; "
                "print(p.POOL_SLOTS, p.POOL_SIZE, p.SLOT_SIZE)")
        r = subprocess.run([sys.executable, "-c", code], cwd=HERE,
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "S9_TEST_PORT_SLOTS": "10"})
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        slots, size, slot = map(int, r.stdout.split())
        self.assertEqual(slots, 10)
        self.assertGreaterEqual(slot, 8, "칸 하나가 8포트보다 좁다")
        self.assertGreaterEqual(size, slots * slot)

    def test_t4b_the_runner_hands_its_jobs_to_the_pool(self):
        """러너가 샤드 자식에게 S9_TEST_PORT_SLOTS 를 샤드 수로 넘긴다."""
        src = open(RUNNER, encoding="utf-8").read()
        blk = src.split("def run_sharded", 1)[1].split("for group in shard", 1)[0]
        self.assertIn('"S9_TEST_PORT_SLOTS": str(max(4, jobs))', blk,
                      "샤드 수가 포트 칸으로 안 넘어간다 — 5샤드부터 포트를 다툰다")


class RedFilesRetryNarrowly(unittest.TestCase):
    """붉은 것만 좁혀서 다시 (REQ-20260905-009) — 전체를 되풀이하지 않는다."""

    def _runner(self):
        spec = importlib.util.spec_from_loader(
            "s9runner_retry", importlib.machinery.SourceFileLoader("s9runner_retry", RUNNER))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_r1_red_files_come_from_shard_output(self):
        """R1. 샤드 출력의 FAIL/ERROR 줄에서 파일을 뽑는다 — 중복 없이."""
        m = self._runner()
        text = ("ERROR: test_e3 (test_code_read_gate.CodeReadGate.test_e3)\n"
                "FAIL: test_x (test_close_last.Server.test_x)\n"
                "FAIL: test_y (test_code_read_gate.CodeReadGate.test_y)\n")
        self.assertEqual(m.red_files_from(text),
                         ["test_code_read_gate.py", "test_close_last.py"])

    def test_r2_only_a_few_red_files_are_retried(self):
        """R2. 붉은 파일 1~3개면 다시, 넷 이상이면 코드 결함이라 다시 안 돈다."""
        m = self._runner()
        os.environ.pop("S9_TEST_NO_RETRY", None)
        self.assertTrue(m.should_retry(["a.py"]))
        self.assertTrue(m.should_retry(["a.py", "b.py", "c.py"]))
        self.assertFalse(m.should_retry(["a.py", "b.py", "c.py", "d.py"]))
        self.assertFalse(m.should_retry([]))
        os.environ["S9_TEST_NO_RETRY"] = "1"
        try:
            self.assertFalse(m.should_retry(["a.py"]))
        finally:
            os.environ.pop("S9_TEST_NO_RETRY", None)

    def test_r3_a_red_full_run_leaves_a_record(self):
        """R3. 전체 실행이 붉으면 state/tests-last-red.json 에 붉은 파일과 시각이 남는다."""
        m = self._runner()
        import json, tempfile, time
        d = tempfile.mkdtemp(prefix="s9red-")
        m.LAST_RED = os.path.join(d, "state", "tests-last-red.json")
        t0 = time.time()
        m.record_last_red(["test_a.py", "test_b.py"], "fp1")
        rec = json.load(open(m.LAST_RED, encoding="utf-8"))
        self.assertEqual(rec["files"], ["test_a.py", "test_b.py"])
        self.assertGreaterEqual(rec["at"], t0)
        self.assertEqual(rec["fingerprint"], "fp1")


class ShardsHaveADeadline(unittest.TestCase):
    """샤드에 시간 상한 (REQ-20260905-021) — 러너는 절대 멈추지 않는다."""

    def test_r4_a_shard_over_the_limit_is_killed_and_counted_red(self):
        """R4. 상한을 넘긴 샤드는 죽이고 붉음으로 센다; 직렬 꼬리도 같은 상한."""
        spec = importlib.util.spec_from_loader(
            "s9runner_dl", importlib.machinery.SourceFileLoader("s9runner_dl", RUNNER))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertTrue(m.overdue(0.0, 901.0, limit=900.0))
        self.assertFalse(m.overdue(0.0, 100.0, limit=900.0))
        self.assertFalse(m.overdue(0.0, 10**9, limit=0))        # 0 = 상한 없음
        src = open(RUNNER, encoding="utf-8").read()
        blk = src.split("def run_sharded", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("overdue(t_start", blk, "샤드 대기 루프에 상한이 없다")
        self.assertIn("pr.kill()", blk, "상한을 넘긴 샤드를 죽이지 않는다")
        self.assertIn("timeout=SHARD_TIMEOUT_SEC", blk, "직렬 꼬리에 상한이 없다")


class QuarantineIsBoundedAndLoud(unittest.TestCase):
    """기한부 격리 (규약 18조) — 전체 실행에서만 빼고, 기한이 있고, 말한다."""

    def test_q1_full_runs_skip_quarantined_files_until_the_deadline(self):
        import json, tempfile, time, io, contextlib
        spec = importlib.util.spec_from_loader(
            "s9runner_q", importlib.machinery.SourceFileLoader("s9runner_q", RUNNER))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        d = tempfile.mkdtemp(prefix="s9q-"); m.QUARANTINE = os.path.join(d, "q.json")
        json.dump({"test_a.py": {"req": "REQ-x", "until": time.time() + 3600},
                   "test_b.py": {"req": "REQ-y", "until": time.time() - 1}},
                  open(m.QUARANTINE, "w", encoding="utf-8"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            kept, dropped = m.apply_quarantine(["test_a.py", "test_b.py", "test_c.py"], full=True)
        self.assertEqual((kept, dropped), (["test_b.py", "test_c.py"], ["test_a.py"]))   # 기한 지난 b 는 돈다
        self.assertIn("[격리] test_a.py — REQ-x", err.getvalue())
        kept, dropped = m.apply_quarantine(["test_a.py"], full=False)        # 지목한 실행은 그대로
        self.assertEqual((kept, dropped), (["test_a.py"], []))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class WeighByMeasuredTime(unittest.TestCase):
    """샤딩 무게는 크기가 아니라 **잰 시간** (REQ-20260905-001).

    종전 무게는 `os.path.getsize` — 「큰 파일이 오래 걸린다」는 가정인데 이
    저장소에서 거짓이다. 서버를 띄우는 작은 파일 하나가 큰 grep 시험 열 개보다
    비싸고, 실측 2026-09-05 에 43파일 선택이 297파일 전체보다 오래 걸렸다
    (757초 vs 514초). 무엇을 도느냐는 안 바뀌고 어느 빈에 넣느냐만 바뀐다.

    실행: python3 tests/ jobs_shard
    """

    def setUp(self):
        self.m = _load()
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="s9times-")
        self.m.TIMES_FILE = os.path.join(self.tmp, "test-times.json")
        self.m.TIMES_DIR = os.path.join(self.tmp, "times")
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)

    def _write(self, d):
        with open(self.m.TIMES_FILE, "w", encoding="utf-8") as f:
            __import__("json").dump(d, f)

    def _files(self, n=4):
        return [f for f in sorted(os.listdir(HERE))
                if f.startswith("test_") and f.endswith(".py")][:n]

    def test_t0_setupclass_cost_is_counted(self):
        """T0. 클래스 준비(setUpClass)에 든 시간이 그 파일에 얹힌다.

        시험 하나의 실행만 재면 이 저장소의 비싼 파일이 0 으로 보인다 — 비용은
        대부분 서버를 띄우는 `setUpClass` 에 있고 그 자리는 startTest~stopTest
        사이에 없다(실측 2026-09-05: 기록 0.0초 · 실제 3.3초). 그 무게로
        샤딩하면 가장 비싼 파일을 가장 가볍다고 믿는다.

        계약을 자리로 본다: 직전 시험이 끝난 때부터 재야 그 틈이 들어온다.
        """
        src = open(RUNNER, encoding="utf-8").read()
        blk = src.split("per_file = {}", 1)[1].split("try:", 1)[0]
        self.assertIn("last_ts", blk,
                      "직전 시험이 끝난 때를 안 들고 있다 — setUpClass 가 안 잡힌다")
        self.assertNotIn("def startTest", blk,
                         "시험 시작 시각부터 재면 클래스 준비가 빠진다")

    def test_t3_known_times_drive_the_weight(self):
        """T3. 기록이 있으면 잰 시간으로 균형을 잡는다 — 느린 것이 먼저 자리를 잡는다."""
        fs = self._files(4)
        self._write({fs[0]: 100.0, fs[1]: 1.0, fs[2]: 1.0, fs[3]: 1.0})
        w = self.m._weights(fs)
        self.assertEqual(w[fs[0]], 100.0)
        bins = self.m.shard(fs, 2)
        slow = [b for b in bins if fs[0] in b][0]
        self.assertEqual(slow, [fs[0]], "가장 느린 것이 혼자 한 빈을 못 잡았다")

    def test_b1_no_record_falls_back_to_size(self):
        """B1. 기록이 없으면 종전대로 크기 — 없는 값으로 판단하지 않는다."""
        fs = self._files(4)
        w = self.m._weights(fs)
        for f in fs:
            self.assertEqual(w[f], os.path.getsize(os.path.join(HERE, f)))

    def test_b2_a_new_file_gets_the_median_not_zero(self):
        """B2. 기록에 없는 새 파일은 아는 것들의 중앙값 — 0 이면 한 빈에 몰린다."""
        fs = self._files(5)
        self._write({fs[0]: 10.0, fs[1]: 20.0, fs[2]: 30.0, fs[3]: 40.0})
        w = self.m._weights(fs)
        self.assertGreater(w[fs[4]], 0)
        self.assertIn(w[fs[4]], (20.0, 30.0))

    def test_b3_a_broken_record_is_ignored(self):
        """B3. 기록이 깨졌으면 조용히 크기로 물러난다."""
        with open(self.m.TIMES_FILE, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(self.m.load_times(), {})
        fs = self._files(3)
        w = self.m._weights(fs)
        self.assertEqual(w[fs[0]], os.path.getsize(os.path.join(HERE, fs[0])))

    def test_t2b_the_parallel_path_merges_too(self):
        """T2b. **병렬 경로에도 합치는 자리가 있다** (실측으로 잡은 구멍).

        처음엔 순차 블록의 finally 에만 merge 를 뒀는데, `--jobs` 는 그 블록을
        아예 안 지난다 — 297파일을 돌고 4파일만 기록에 남았다. 재고도 안 쓰는
        기록은 없는 기록이다.
        """
        src = open(RUNNER, encoding="utf-8").read()
        branch = src.split("if jobs > 1 and not nested:", 1)[1].split(
            "\n        # 로컬 서버에", 1)[0]
        self.assertIn("merge_times()", branch,
                      "병렬 경로가 자식들의 기록을 안 합친다")

    def test_t1_t2_children_record_and_the_parent_merges(self):
        """T1·T2·B4. 자식이 pid 별로 남기고 부모가 합친다 — 서로 안 덮는다."""
        self.m.record_times({"test_a.py": 1.5})
        import json as _j
        # 다른 pid 가 남긴 것처럼 하나 더
        os.makedirs(self.m.TIMES_DIR, exist_ok=True)
        with open(os.path.join(self.m.TIMES_DIR, "999999.json"), "w",
                  encoding="utf-8") as f:
            _j.dump({"test_b.py": 2.5}, f)
        self.m.merge_times()
        got = self.m.load_times()
        self.assertEqual(got.get("test_a.py"), 1.5)
        self.assertEqual(got.get("test_b.py"), 2.5, "다른 실행의 기록을 덮었다")
        self.assertEqual(os.listdir(self.m.TIMES_DIR), [], "합친 뒤 안 치웠다")


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
