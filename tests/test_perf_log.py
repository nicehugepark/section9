"""성능 로그·메트릭은 비동기로 쓰고 1시간만 둔다 (REQ-20260909-087).

기능 요소마다 타임스탬프 한 줄이 state/local/log/ 에 남되(git 밖), 쓰기가
요청을 막지 않고(큐+데몬 스레드, 넘치면 버림), 보존 시간(perf_log_keep_min)이
지난 파일은 워처 틱이 지운다. 계측 한 줄의 비용 상한(호출당 0.1ms)을 여기서 잰다.

실행: python3 tests/ perf_log
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9.py")


class PerfLog(unittest.TestCase):

    def setUp(self):
        self._root = os.environ.get("S9_ROOT")
        self._perf_env = os.environ.pop("S9_PERF", None)
        self.root = tempfile.mkdtemp(prefix="s9perf-")
        os.environ["S9_ROOT"] = self.root
        name = "s9perf_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.logdir = os.path.join(self.root, "state", "local", "log")

    def tearDown(self):
        self.m.perf_stop()
        if self._root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self._root
        if self._perf_env is not None:
            os.environ["S9_PERF"] = self._perf_env
        shutil.rmtree(self.root, ignore_errors=True)

    def _lines(self, prefix="perf"):
        out = []
        if not os.path.isdir(self.logdir):
            return out
        for fn in sorted(os.listdir(self.logdir)):
            if fn.startswith(prefix + "-") and fn.endswith(".jsonl"):
                with open(os.path.join(self.logdir, fn), encoding="utf-8") as f:
                    out += [json.loads(l) for l in f if l.strip()]
        return out

    def test_p1_ten_thousand_marks_under_a_second_and_the_thread_writes_them(self):
        m = self.m
        m.perf_start(root=self.root, maxsize=20000)
        n = 10000
        t0 = time.perf_counter()
        for i in range(n):
            m.perf_mark("api", "/api/x", 1.5, status=200, bytes=100)
        took = time.perf_counter() - t0
        self.assertLess(took, 1.0, f"perf_mark {n}회에 {took:.3f}s — 호출당 0.1ms 를 넘는다")
        self.assertTrue(m.perf_flush(timeout=10), "큐가 10초 안에 비지 않았다")
        rows = self._lines("perf")
        self.assertEqual(len(rows), n, "큐 스레드가 쓴 줄 수가 호출 수와 다르다")
        self.assertEqual(rows[0]["kind"], "api")
        self.assertEqual(rows[0]["name"], "/api/x")
        self.assertEqual(rows[0]["ms"], 1.5)
        self.assertIn("T", rows[0]["ts"], "ts 는 ISO 시각이어야 한다")
        names = [f for f in os.listdir(self.logdir) if f.startswith("perf-")]
        self.assertRegex(names[0], r"^perf-\d{8}-\d{2}\.jsonl$", "파일은 시각(시간)으로 회전한다")
        print(f"\n  perf_mark 호출당 {took / n * 1e6:.2f}µs (n={n})")

    def test_p2_a_full_queue_drops_and_counts_without_blocking(self):
        m = self.m
        m.perf_start(root=self.root, maxsize=50, writer=False)
        t0 = time.perf_counter()
        ok = [m.perf_mark("api", "/api/y", 1.0) for _ in range(200)]
        took = time.perf_counter() - t0
        self.assertLess(took, 0.5, "가득 찬 큐에서 호출이 막혔다")
        self.assertEqual(ok.count(True), 50)
        self.assertEqual(ok.count(False), 150)
        rec = m.perf_metrics_flush(root=self.root)
        self.assertEqual(rec["dropped"], 150, "버린 수가 메트릭에 실려야 한다")
        self.assertEqual(rec["queued"], 50)
        rec2 = m.perf_metrics_flush(root=self.root)
        self.assertEqual(rec2["dropped"], 0, "버린 수는 창마다 새로 센다")

    def test_p3_files_past_the_keep_window_are_pruned_by_the_tick(self):
        m = self.m
        os.makedirs(self.logdir)
        now = time.time()
        paths = {}
        for name, age_min in (("perf-20260909-10.jsonl", 90), ("metrics-20260909-10.jsonl", 90),
                              ("perf-20260909-11.jsonl", 30), ("metrics-20260909-11.jsonl", 30),
                              ("other.txt", 90)):
            p = os.path.join(self.logdir, name)
            open(p, "w").close()
            os.utime(p, (now - age_min * 60, now - age_min * 60))
            paths[name] = p
        self.assertEqual(m.perf_keep_min(), 60, "기본 보존은 60분")
        gone = m.perf_prune(now=now, root=self.root)
        self.assertEqual(sorted(os.path.basename(p) for p in gone),
                         ["metrics-20260909-10.jsonl", "perf-20260909-10.jsonl"])
        self.assertTrue(os.path.exists(paths["other.txt"]), "다른 파일은 건드리지 않는다")
        # 설정 perf_log_keep_min 이 반영된다 — 20분이면 30분 된 파일도 간다
        cpath = m.user_config_local_path(m.resolve_user(None))
        os.makedirs(os.path.dirname(cpath), exist_ok=True)
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump({"perf_log_keep_min": 20}, f)
        self.assertEqual(m.perf_keep_min(), 20)
        m._PERF["prune_t"] = 0.0
        self.assertEqual(m.perf_tick(now=now, root=self.root), 2, "틱이 설정 값으로 지운다")
        self.assertEqual(m.perf_tick(now=now + 10, root=self.root), 0, "틱은 1분에 한 번만 지운다")
        left = sorted(os.listdir(self.logdir))
        self.assertNotIn("perf-20260909-11.jsonl", left)
        self.assertIn("other.txt", left)

    def test_p4_metrics_summary_has_count_p50_p95_max_bytes(self):
        m = self.m
        m.perf_start(root=self.root, maxsize=1000)
        for i in range(1, 101):
            m.perf_mark("api", "/api/z", float(i), bytes=10)
        m.perf_mark("api", "/api/z", 3.0, err="ConnectionResetError")
        m.perf_mark("tick", "rework", 7.0)
        self.assertTrue(m.perf_flush(timeout=10))
        rec = m.perf_metrics_flush(root=self.root)
        z = rec["by"]["api"]["/api/z"]
        self.assertEqual(z["count"], 101)
        self.assertEqual(z["p50"], 50.0)
        self.assertEqual(z["p95"], 95.0)
        self.assertEqual(z["max"], 100.0)
        self.assertEqual(z["bytes"], 1000)
        self.assertEqual(rec["by"]["tick"]["rework"]["count"], 1)
        self.assertEqual(rec["resets"], 1, "리셋(연결 끊김) 수가 메트릭에 실린다")
        rows = self._lines("metrics")
        self.assertEqual(len(rows), 1, "요약은 metrics-YYYYMMDD-HH.jsonl 한 줄")
        self.assertEqual(rows[0]["by"]["api"]["/api/z"]["p95"], 95.0)
        self.assertEqual(m.perf_percentile([], 0.5), 0.0)

    def test_p5_the_log_directory_is_ignored_by_git(self):
        r = subprocess.run(["git", "-C", ROOT, "check-ignore", "-q",
                            "state/local/log/perf-20260909-16.jsonl"])
        self.assertEqual(r.returncode, 0, "state/local/log/ 가 .gitignore 에 걸리지 않는다")
        both = subprocess.run(["git", "-C", ROOT, "ls-files", "-ci", "--exclude-standard"],
                              capture_output=True, text=True).stdout.split()
        self.assertEqual(both, [], "추적됨∩무시됨 파일이 있다")

    def test_p6_s9_perf_prints_the_summary_and_the_tail(self):
        m = self.m
        m.perf_start(root=self.root, maxsize=1000)
        for i in range(1, 21):
            m.perf_mark("api", "/api/catalog", float(i), bytes=500)
        m.perf_mark("tick", "jira", 12.0)
        self.assertTrue(m.perf_flush(timeout=10))
        m.perf_metrics_flush(root=self.root)
        A = lambda **kw: type("A", (), kw)()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.cmd_perf(A(action="show", since="10m", by=None, json=False, n=20))
        out = buf.getvalue()
        self.assertIn("/api/catalog", out)
        self.assertIn("20", out)
        self.assertIn("보존 60분", out)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.cmd_perf(A(action="show", since="10m", by="endpoint", json=True, n=20))
        rep = json.loads(buf.getvalue())
        self.assertEqual(rep["by"]["api"]["/api/catalog"]["count"], 20)
        self.assertEqual(rep["by"]["api"]["/api/catalog"]["p50"], 10.0)
        self.assertEqual(rep["by"]["api"]["/api/catalog"]["bytes"], 10000)
        self.assertNotIn("tick", rep["by"], "--by endpoint 는 api 만")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.cmd_perf(A(action="tail", since="10m", by=None, json=False, n=5))
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 5)
        self.assertEqual(json.loads(lines[-1])["name"], "jira")
        with self.assertRaises(ValueError):
            m.perf_since_sec("ten")

    def test_p7_cli_entry_appends_one_line_without_a_queue_and_never_fails(self):
        m = self.m
        argv = sys.argv
        try:
            sys.argv = ["s9", "now"]
            with contextlib.redirect_stdout(io.StringIO()):
                m.main()
        finally:
            sys.argv = argv
        rows = [r for r in self._lines("perf") if r["kind"] == "cli"]
        self.assertEqual(len(rows), 1, "CLI 진입이 명령 한 줄을 남긴다")
        self.assertEqual(rows[0]["name"], "now")
        self.assertGreater(rows[0]["ms"], 0)
        # 로그 자리를 만들 수 없어도 명령은 그대로 끝난다
        shutil.rmtree(self.logdir)
        open(self.logdir, "w").close()          # 디렉토리 자리에 파일 — makedirs 가 실패한다
        self.assertFalse(m.perf_mark("cli", "x", 1.0))
        try:
            sys.argv = ["s9", "now"]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                m.main()
        finally:
            sys.argv = argv
        self.assertRegex(buf.getvalue(), r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                         "s9 now 가 로그 실패와 무관하게 답했다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
