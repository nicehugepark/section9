"""사고 뒤에 아무것도 남지 않으면 원인은 영영 짐작이다 (REQ-20260902-054).

"자꾸 api error 가 난다" 로 접수됐다가 "api error 가 아니고 request timeout
이었다"로 정정된 사건이 이 계기의 출처다. 두 증상은 뿌리가 다르다 — 하나는
**밖으로 못 나간 것**이고 하나는 **길은 열린 채 답이 늦은 것**이다. 사후에
그 둘을 가르려면 사고 시각에 무엇이 어땠는지가 남아 있어야 하고, 남기려면
사고 전부터 돌고 있어야 한다. 그래서 상시다.

가르는 힘은 갈래를 셋으로 나눈 데서 나온다:
  api  전 구간(dns→tcp→tls→http) — 멈춘 단계가 곧 사유
  ctl  IP 로 바로 — 이름 풀이를 건너뛴 대조군
  dns  이름 풀이 단독
셋이 함께 죽으면 회선, api 만 죽으면 저쪽, dns 만 죽으면 이름 풀이,
밖은 멀쩡한데 늦기만 하면 timeout 의 전조다.

실행: python3 tests/ metrics
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import socket
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _ok(label, **kw):
    d = {"label": label, "ok": True, "stage": "ok", "total_ms": 100.0}
    d.update(kw)
    return d


def _bad(label, stage, **kw):
    d = {"label": label, "ok": False, "stage": stage, "error": "boom",
         "total_ms": 5000.0}
    d.update(kw)
    return d


class Metrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9metrics-")
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9metrics", importlib.machinery.SourceFileLoader("s9metrics", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def setUp(self):
        d = self.m._metrics_paths(self.tmp)["dir"]
        if os.path.isdir(d):
            for n in os.listdir(d):
                if n.endswith(".jsonl"):
                    os.remove(os.path.join(d, n))

    def _lines(self, day=None):
        path = self.m._metrics_day_path(self.tmp, day)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    # ---------------------------------------------------------------- 정상
    def test_s1_sample_carries_three_lanes_and_system(self):
        """S1. 표본 한 줄에 네트워크 3갈래와 국소 자원이 함께 담긴다.

        따로 적으면 사고 시각에 둘을 맞춰 보는 일이 사람 몫이 된다. 같은
        줄에 있어야 "밖은 멀쩡한데 안이 바닥났다"가 한눈에 읽힌다.
        """
        s = self.m.metrics_sample(self.tmp)
        self.assertEqual(set(s["net"]), {"api", "ctl", "dns"})
        self.assertIn("ts", s)
        self.assertTrue(s["boot"] > 0)
        self.assertTrue(set(s["sys"]) >= {"load1", "mem_avail_mb"})
        path = self.m.metrics_append(s, self.tmp)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(any("net" in r for r in self._lines()))

    def test_s2_start_is_idempotent(self):
        """S2. 잠금을 쥔 자가 있으면 둘째는 뜨지 않는다.

        세션이 시작될 때마다 부르는 자리라 멱등이 아니면 세션 수만큼
        수집기가 쌓인다.
        """
        lock = self.m._metrics_lock(self.tmp)
        self.assertIsNotNone(lock)
        try:
            self.assertEqual(self.m._metrics_alive(self.tmp), os.getpid())
            self.assertFalse(self.m.metrics_detach(self.tmp))
        finally:
            lock.close()
        self.assertIsNone(self.m._metrics_alive(self.tmp))

    def test_s3_status_reports_count_and_last(self):
        """S3. status 가 표본 수와 마지막 시각을 낸다."""
        self.m.metrics_append(self.m.metrics_sample(self.tmp), self.tmp)
        import io
        import contextlib
        ns = type("A", (), {"action": "status", "json": False,
                            "interval": 15, "at": None, "window": 10})()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.m.cmd_metrics(ns)
        out = buf.getvalue()
        self.assertIn("오늘 표본", out)
        self.assertIn("멈춰 있다", out)

    # ---------------------------------------------------------------- 경계
    def test_s4_reboot_marks_a_boundary(self):
        """S4. 부팅 시각이 바뀌면 표본 앞에 경계 표식이 먼저 들어간다.

        재시작으로 생긴 공백과 진짜 단절은 눈으로 구별되지 않는다. 표식이
        없으면 "이 시간대에 기록이 없다"가 두 뜻을 갖는다.
        """
        base = self.m.metrics_sample(self.tmp)
        base["boot"] = 1000
        self.m.metrics_append(base, self.tmp)
        again = dict(base, boot=2000)
        self.m.metrics_append(again, self.tmp)
        recs = self._lines()
        marks = [r for r in recs if r.get("event") == "boot"]
        self.assertEqual(len(marks), 2)          # 첫 표식 + 재시작 표식
        self.assertTrue(marks[0]["first"])       # 첫 것은 재시작이 아니다
        self.assertFalse(marks[1]["first"])
        self.assertEqual(marks[1]["prev_boot"], 1000)
        # 첫 표식은 재시작으로 세지 않는다
        self.assertEqual(self.m.metrics_verdict(recs)["boots"], 1)

    def test_s5_day_rollover_and_prune(self):
        """S5. 날 파일로 나뉘고, 보존 기간 밖은 지운다."""
        d = self.m._metrics_paths(self.tmp)["dir"]
        os.makedirs(d, exist_ok=True)
        old = (datetime.date.today()
               - datetime.timedelta(days=self.m.METRICS_KEEP_DAYS + 2))
        keep = datetime.date.today() - datetime.timedelta(days=1)
        for day in (old, keep):
            with open(os.path.join(d, f"{day.isoformat()}.jsonl"), "w") as f:
                f.write("{}\n")
        gone = self.m.metrics_prune(self.tmp)
        self.assertIn(f"{old.isoformat()}.jsonl", gone)
        self.assertTrue(os.path.exists(
            os.path.join(d, f"{keep.isoformat()}.jsonl")))

    def test_s6_one_lane_failing_does_not_eat_the_sample(self):
        """S6. 한 갈래가 상해도 나머지 갈래와 국소 자원은 그대로 남는다.

        부분 실패가 표본 전체를 삼키면 정작 사고 시각의 기록만 비어 버린다 —
        가장 필요한 순간에 가장 없는 기록이 된다.
        """
        real = self.m._probe

        def flaky(label, host, **kw):
            if label == "api":
                raise RuntimeError("terminal probe blew up")
            return _ok(label)

        self.m._probe = flaky
        try:
            with self.assertRaises(RuntimeError):
                self.m.metrics_sample(self.tmp)
        finally:
            self.m._probe = real
        # 프로브 자신은 어떤 예외도 밖으로 내지 않는다 — 그것이 이 계약이다
        out = self.m._probe("api", "no-such-host.invalid.", timeout=1.0)
        self.assertFalse(out["ok"])
        self.assertIn("stage", out)
        self.assertIn("total_ms", out)

    # ---------------------------------------------------------------- 실패
    def test_s7_dead_network_records_the_stage(self):
        """S7. 밖이 전부 막혀도 수집기는 죽지 않고 **멈춘 단계**를 남긴다."""
        real_gai, real_conn = socket.getaddrinfo, socket.create_connection
        socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(
            OSError("Name or service not known"))
        try:
            out = self.m._probe("api", "api.anthropic.com", timeout=1.0)
            self.assertFalse(out["ok"])
            self.assertEqual(out["stage"], "dns")
            dns = self.m._probe_dns("api.anthropic.com", timeout=1.0)
            self.assertFalse(dns["ok"])
        finally:
            socket.getaddrinfo = real_gai
        socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(
            OSError("Network is unreachable"))
        try:
            out = self.m._probe("ctl", "1.1.1.1", ip="1.1.1.1", timeout=1.0)
            self.assertFalse(out["ok"])
            self.assertEqual(out["stage"], "tcp")
        finally:
            socket.create_connection = real_conn

    def test_s8_verdict_splits_line_name_server_and_slowness(self):
        """S8. 갈래의 조합이 곧 판정이다 — 회선·이름·저쪽·느려짐이 갈린다."""
        def sample(api, ctl, dns, tw=10):
            return {"ts": "2026-09-02T18:00:00+09:00", "boot": 1,
                    "net": {"api": api, "ctl": ctl, "dns": dns},
                    "sys": {"tcp_tw": tw}}

        v = self.m.metrics_verdict([sample(
            _bad("api", "tcp"), _bad("ctl", "tcp"), _bad("dns", "dns"))])
        self.assertIn("회선", v["verdict"])

        v = self.m.metrics_verdict([sample(
            _bad("api", "dns"), _ok("ctl"), _bad("dns", "dns"))])
        self.assertIn("이름 풀이", v["verdict"])

        v = self.m.metrics_verdict([sample(
            _bad("api", "http"), _ok("ctl"), _ok("dns"))])
        self.assertIn("저쪽", v["verdict"])
        self.assertEqual(v["stages"], {"http": 1})

        slow = self.m.METRICS_SLOW_MS + 1
        recs = [sample(_ok("api", total_ms=slow), _ok("ctl"), _ok("dns"))] * 5
        v = self.m.metrics_verdict(recs)
        self.assertIn("느려짐", v["verdict"])
        self.assertEqual(v["api_slow"], 5)

        v = self.m.metrics_verdict([sample(_ok("api"), _ok("ctl"), _ok("dns"))])
        self.assertIn("멀쩡", v["verdict"])

    # ---------------------------------------------------------------- 회귀
    def test_s9_lock_is_its_own(self):
        """S9. 계기의 잠금은 제 것뿐이다 — serve 감시자의 잠금·포트에 닿지 않는다.

        살아 있는 서버는 무슨 이유로도 건드리지 않는다는 것이 이 저장소의
        규율이다(REQ-20260825-096). 계기가 그 규율의 예외가 되면 안 된다.
        """
        p = self.m._metrics_paths(self.tmp)
        self.assertTrue(p["lock"].endswith("metrics/collector.lock"))
        guard = self.m._guard_paths(9909, self.tmp)
        self.assertNotEqual(os.path.dirname(p["lock"]),
                            os.path.dirname(guard["lock"]))
        src = open(S9, encoding="utf-8").read()
        i = src.index("def metrics_loop(")
        j = src.index("def _metrics_main(")
        self.assertNotIn("_guard_", src[i:j])

    def test_s10_session_start_stands_the_collector_up(self):
        """S10. 세션 시작이 계기를 세운다.

        바깥 스케줄러를 쓰지 않기로 한 저장소라, 기계가 재시작돼 수집기까지
        사라진 자리를 메우는 것은 이 훅뿐이다.
        """
        hook = open(os.path.join(HERE, "..", "bin", "s9-audit-session"),
                    encoding="utf-8").read()
        self.assertIn("def ensure_metrics(", hook)
        i = hook.index('if event == "start":')
        j = hook.index("\n", hook.index("ensure_metrics()", i))
        self.assertLess(i, j)                    # 세션 시작 갈래 안에 있다
        self.assertIn('"metrics", "start"', hook)


if __name__ == "__main__":
    unittest.main()
