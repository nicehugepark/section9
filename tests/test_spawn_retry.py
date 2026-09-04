"""워커 즉사 — 일시적이면 다시 걸고, 아니면 세운다 (REQ-20260903-018).

사용자: "무인 워커가 API 529 Overloaded 한 번에 그대로 죽는다 — 서버 쪽 일시
과부하인데 재시도가 없어 한 번의 딸꾹질이 작업 한 건을 통째로 끊는다."

값을 두 번 치렀다. 스폰은 이미 **성공으로 세어졌고**(하루 20·시간 6), 마커의
쿨다운 600초가 걸리고, 문서는 in-progress 인 채 **아무 사유도 안 남는다** —
사람에게는 「조용히 멈춘 요청」으로만 보인다.

규율은 `_sync_fail_kind` 에서 가져온다: **일시적인 것만 다시 걸고, 다시 걸어도
같은 답인 것은 재시도가 아니라 즉시 표면화다.**

실행: python3 tests/ spawn_retry
"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import time
import shutil
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load():
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    try:
        spec = importlib.util.spec_from_loader(
            "s9_retry", importlib.machinery.SourceFileLoader(
                "s9_retry", os.path.join(ROOT, "bin", "s9")))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if sys.path and sys.path[0] == os.path.join(ROOT, "bin"):
            sys.path.pop(0)


class TheKind(unittest.TestCase):
    """N1·F2·B2. 로그 꼬리 한 줄이 갈래를 정한다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_n1_overload_words_are_temporary(self):
        for line in ('API Error: 529 {"type":"overloaded_error"}',
                     "Error: 429 rate_limit_error",
                     "fetch failed: socket hang up",
                     "request timed out after 600s",
                     "503 Service Unavailable"):
            with self.subTest(line=line):
                self.assertEqual(self.m._spawn_fail_kind(line), "overload")

    def test_f2_same_answer_twice_is_fatal(self):
        """다시 걸어도 같은 답인 것 — sync 의 protected 와 같은 자리."""
        for line in ("Invalid API key · Please run /login",
                     "401 authentication_error",
                     "/bin/sh: 1: claude: command not found",
                     "Credit balance is too low"):
            with self.subTest(line=line):
                self.assertEqual(self.m._spawn_fail_kind(line), "fatal")

    def test_b2_unknown_stays_unknown(self):
        """모르는 것을 overload 로 세면 진짜 결함이 예산만 태우며 되풀이된다."""
        for line in ("", "   ", "done in 4m 12s", "wrote 3 files"):
            with self.subTest(line=repr(line)):
                self.assertEqual(self.m._spawn_fail_kind(line), "other")


class TheTick(unittest.TestCase):
    """즉사 판정과 백오프 — 실제로 마커를 놓고 함수를 돌려서 잰다."""

    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.mkdtemp(prefix="s9retry-")
        os.makedirs(os.path.join(self.tmp, "auto"), exist_ok=True)
        self.m._auto_dir = lambda: os.path.join(self.tmp, "auto")
        self.calls = []
        self.m.do_transition = lambda *a, **k: self.calls.append((a, k))
        self.m._auto_log = lambda *a, **k: None
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _mark(self, **kw):
        p = {"pid": 999999, "spawn_at": time.time(), "count": 1,
             "last": time.time(), "reason": "rework"}
        p.update(kw)
        with open(os.path.join(self.tmp, "auto", "REQ-X.json"), "w",
                  encoding="utf-8") as f:
            json.dump(p, f)

    def _read(self):
        with open(os.path.join(self.tmp, "auto", "REQ-X.json"),
                  encoding="utf-8") as f:
            return json.load(f)

    def _log(self, text):
        with open(os.path.join(self.tmp, "auto", "REQ-X.log"), "w",
                  encoding="utf-8") as f:
            f.write(text + "\n")

    def _global(self, **kw):
        g = {"day": __import__("datetime").date.today().isoformat(),
             "day_count": 5, "hour_count": 3,
             "hour": int(time.time() // 3600)}
        g.update(kw)
        with open(os.path.join(self.tmp, "auto", "_global.json"), "w",
                  encoding="utf-8") as f:
            json.dump(g, f)

    # ------------------------------------------------------------ 정상
    def test_n2_an_early_overload_death_is_scheduled_again(self):
        """N2. 즉사 + overload → retry·next_at 이 적히고 그 전에는 안 뜬다."""
        self._mark()
        self._log('API Error: 529 {"type":"overloaded_error"}')
        self.assertEqual(self.m._spawn_retry_tick("REQ-X"), "wait")
        p = self._read()
        self.assertEqual(p["retry"], 1)
        self.assertGreater(p["next_at"], time.time())
        self.assertEqual(p["last"], 0, "쿨다운이 재시도를 막는다")
        self.assertEqual(self.calls, [], "첫 실패에 문서를 세웠다")

    def test_n3_the_backoff_grows_and_stops_at_three(self):
        """N3. 30·60·120초로 자라고 3회에서 멈춘다."""
        seen = []
        for n in range(3):
            self._mark(retry=n, next_at=0)
            self._log("529 overloaded_error")
            t0 = time.time()
            self.assertEqual(self.m._spawn_retry_tick("REQ-X"), "wait")
            seen.append(self._read()["next_at"] - t0)
        for base, got in zip(self.m.SPAWN_RETRY_DELAYS, seen):
            # 지터 ±20% 안 — 값을 못박지 않는다(못박으면 지터가 시험을 흔든다).
            self.assertGreaterEqual(got, base * 0.75, f"{base}초가 너무 짧다: {seen}")
            self.assertLessEqual(got, base * 1.25, f"{base}초가 너무 길다: {seen}")
        self.assertTrue(seen[0] < seen[1] < seen[2],
                        f"백오프가 자라지 않는다: {seen}")

    def test_n4_a_live_worker_clears_nothing_and_is_left_alone(self):
        """N4 인접. 살아 있는 pid 는 손대지 않는다."""
        self._mark(pid=os.getpid())
        self._log("529 overloaded_error")
        self.assertEqual(self.m._spawn_retry_tick("REQ-X"), "")
        self.assertNotIn("retry", self._read())

    # ------------------------------------------------------------ 실패
    def test_f1_after_three_tries_the_document_is_stood_up(self):
        """F1. 3회를 다 쓰면 blocked 로 전이하고 사유를 남긴다 — 조용히 멈추지 않는다."""
        self._mark(retry=3, next_at=0)
        self._log('API Error: 529 {"type":"overloaded_error"}')
        self.assertEqual(self.m._spawn_retry_tick("REQ-X"), "blocked")
        self.assertEqual(len(self.calls), 1)
        (doc, status), kw = self.calls[0]
        self.assertEqual((doc, status), ("REQ-X", "blocked"))
        self.assertIn("과부하", kw["note"])
        self.assertIn("3회", kw["note"])
        self.assertNotIn("retry", self._read())

    def test_f2_a_fatal_death_skips_the_retries(self):
        """F2. 인증 실패는 재시도 없이 곧바로 세운다."""
        self._mark()
        self._log("Invalid API key · Please run /login")
        self.assertEqual(self.m._spawn_retry_tick("REQ-X"), "blocked")
        self.assertEqual(len(self.calls), 1)
        self.assertIn("재시도 없음", self.calls[0][1]["note"])

    # ------------------------------------------------------------ 경계
    def test_b1_a_worker_that_lived_a_while_is_not_an_early_death(self):
        """B1. 오래 살다 죽은 것은 일하다 끊긴 것이다 — 이어받기 경로의 몫."""
        self._mark(spawn_at=time.time() - (self.m.SPAWN_EARLY_SEC + 5))
        self._log("529 overloaded_error")
        self.assertEqual(self.m._spawn_retry_tick("REQ-X"), "")
        self.assertNotIn("retry", self._read())

    def test_b2_an_unknown_tail_changes_nothing(self):
        self._mark()
        self._log("wrote 3 files")
        self.assertEqual(self.m._spawn_retry_tick("REQ-X"), "")
        self.assertNotIn("retry", self._read())
        self.assertEqual(self.calls, [])

    def test_b3_the_budget_slot_comes_back(self):
        """B3. 즉사는 예산을 먹지 않는다 — 과부하 20분이 하루치를 태우면 안 된다."""
        self._global(day_count=5, hour_count=3)
        self._mark(count=2)
        self._log("529 overloaded_error")
        self.m._spawn_retry_tick("REQ-X")
        with open(os.path.join(self.tmp, "auto", "_global.json"),
                  encoding="utf-8") as f:
            g = json.load(f)
        self.assertEqual((g["day_count"], g["hour_count"]), (4, 2))
        self.assertEqual(self._read()["count"], 1)

    def test_b3b_a_human_wake_refunds_the_human_budget(self):
        """B3b. 갈래마다 제 통에 돌려준다 — 워처가 사람 몫을 갉으면 안 된다."""
        self._global(wake_day_count=4, wake_hour_count=2)
        self._mark(reason="wake")
        self._log("529 overloaded_error")
        self.m._spawn_retry_tick("REQ-X")
        with open(os.path.join(self.tmp, "auto", "_global.json"),
                  encoding="utf-8") as f:
            g = json.load(f)
        self.assertEqual((g["wake_day_count"], g["wake_hour_count"]), (3, 1))
        self.assertEqual(g.get("day_count", 0), 5, "남의 통(워처 예산)을 건드렸다")

    def test_b4_the_backoff_window_holds_the_watcher_back(self):
        """B4. next_at 전에는 워처가 이 문서를 건너뛴다."""
        self._mark(next_at=time.time() + 300)
        self.assertEqual(self.m._spawn_retry_tick("REQ-X"), "wait")

    def test_b5_one_death_is_judged_once(self):
        """같은 죽음을 두 번 세지 않는다 — 예산이 두 번 돌아오면 그것도 거짓말이다."""
        self._global(day_count=5, hour_count=3)
        self._mark()
        self._log("529 overloaded_error")
        self.m._spawn_retry_tick("REQ-X")
        p = self._read()
        p["next_at"] = 0
        with open(os.path.join(self.tmp, "auto", "REQ-X.json"), "w",
                  encoding="utf-8") as f:
            json.dump(p, f)
        self.m._spawn_retry_tick("REQ-X")
        with open(os.path.join(self.tmp, "auto", "_global.json"),
                  encoding="utf-8") as f:
            g = json.load(f)
        self.assertEqual(g["day_count"], 4, "같은 죽음에 예산을 두 번 돌려줬다")

    def test_b6_no_marker_is_not_this_path(self):
        self.assertEqual(self.m._spawn_retry_tick("REQ-NONE"), "")


class TheWiring(unittest.TestCase):
    """R1. 스폰 경로는 여전히 하나다 — 재시도가 새 Popen 을 파지 않는다."""

    def test_r1_the_watcher_asks_before_it_spawns(self):
        src = open(os.path.join(ROOT, "bin", "s9"), encoding="utf-8").read()
        body = src.split("def rework_watch_tick", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_spawn_retry_tick", body,
                      "워처가 즉사를 묻지 않는다 — 529 한 번이 다시 10분을 잠근다")
        self.assertNotIn("subprocess.Popen", body,
                         "워처가 제 Popen 을 들었다 — 스폰 경로 이중화 금지")
        tick = src.split("def _spawn_retry_tick", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("Popen", tick, "재시도가 직접 띄웠다")


if __name__ == "__main__":
    unittest.main()
