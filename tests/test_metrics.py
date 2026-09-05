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
import shutil
import socket
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


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
    def test_s1_sample_carries_four_lanes_and_system(self):
        """S1. 표본 한 줄에 네트워크 4갈래와 국소 자원이 함께 담긴다.

        따로 적으면 사고 시각에 둘을 맞춰 보는 일이 사람 몫이 된다. 같은
        줄에 있어야 "밖은 멀쩡한데 안이 바닥났다"가 한눈에 읽힌다.

        넷째 `link` 는 **국소 대조군**이다 (REQ-20260903-002) — 바깥 셋이 다
        죽었을 때 「회선이 없다」와 「밖으로 못 나간다」를 가른다. 바깥으로
        나가지 않으므로 비용이 0 이고, 그래서 매 표본에 넣는다.
        """
        s = self.m.metrics_sample(self.tmp)
        self.assertEqual(set(s["net"]), {"api", "ctl", "dns", "link"})
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
        # 시험 자리는 임시 자리라 REQ-20260902-062 의 관문에 먼저 걸린다.
        # 여기서 재려는 것은 **그 뒤의 멱등**이라 관문만 잠시 연다.
        was = self.m._metrics_transient_root
        self.m._metrics_transient_root = lambda root=None: False
        try:
            self.assertEqual(self.m._metrics_alive(self.tmp), os.getpid())
            self.assertFalse(self.m.metrics_detach(self.tmp))
        finally:
            self.m._metrics_transient_root = was
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

    def test_s4b_boot_jitter_is_still_one_boot(self):
        """S4b. btime 이 초 단위로 흔들려도 부팅은 하나다 (REQ-20260902-057).

        WSL2 는 부팅 직후 시계를 맞추며 btime 을 (현재시각 − uptime) 으로
        되계산해 초 단위로 흔든다. 「값이 다르면 재시작」 규칙이 그 흔들림마다
        표식을 세워 20:02~20:08 에 경계 9개를 만들었다 — 경계가 아홉 개면
        어느 것도 경계가 아니다. 아래는 그때 실측한 값 그대로다.
        """
        base = self.m.metrics_sample(self.tmp)
        for b in (1788346922, 1788346921, 1788346920, 1788346918,
                  1788346916, 1788346915, 1788346914, 1788346914):
            self.m.metrics_append(dict(base, boot=b), self.tmp)
        recs = self._lines()
        marks = [r for r in recs if r.get("event") == "boot"]
        self.assertEqual(len(marks), 1)          # 아홉이 아니라 하나
        self.assertTrue(marks[0]["first"])       # 그 하나는 수집의 시작이다
        self.assertEqual(self.m.metrics_verdict(recs)["boots"], 0)

    def test_s4c_a_real_restart_still_marks(self):
        """S4c. 흔들림을 눈감아도 진짜 재시작은 그대로 잡힌다.

        허용 오차의 값이 곧 이 계기의 감도라, 경계 양쪽을 함께 잰다.
        """
        slack = self.m.METRICS_BOOT_SLACK_SEC
        self.assertFalse(self.m._boot_changed(1000, 1000 + slack))
        self.assertTrue(self.m._boot_changed(1000, 1000 + slack + 1))
        self.assertFalse(self.m._boot_changed(1000, 1000 - slack))
        self.assertTrue(self.m._boot_changed(1000, 1000 - slack - 1))
        self.assertTrue(self.m._boot_changed(None, 1000))   # 수집의 시작
        base = self.m.metrics_sample(self.tmp)
        self.m.metrics_append(dict(base, boot=1788346922), self.tmp)
        self.m.metrics_append(dict(base, boot=1788350522), self.tmp)
        marks = [r for r in self._lines() if r.get("event") == "boot"]
        self.assertEqual(len(marks), 2)
        self.assertFalse(marks[1]["first"])

    def test_s4d_no_collector_stands_in_a_throwaway_copy(self):
        """S4d. 잠시 있다 사라질 사본에서는 수집기가 서지 않는다
        (REQ-20260902-062).

        멱등은 `state/metrics/collector.lock` 하나에 걸려 있는데 그 잠금은
        ROOT 마다 따로다. 시험·중계가 만든 임시 사본에서 수집기가 뜨면
        실저장소의 잠금을 **볼 수 없어** 겹쳐 살고, 그 사본이 지워진 뒤에도
        사라진 자리에 표본을 쓰며 영원히 남는다 (실측 2026-09-02 21:36).
        """
        throwaway = tempfile.mkdtemp(prefix="s9metgone-")
        try:
            self.assertTrue(self.m._metrics_transient_root(throwaway))
            self.assertFalse(self.m.metrics_detach(throwaway))
            self.assertFalse(os.path.exists(
                self.m._metrics_paths(throwaway)["lock"]))
        finally:
            shutil.rmtree(throwaway, ignore_errors=True)
        # 실저장소는 임시 자리가 아니다 — 관문이 정상 기동까지 막으면 안 된다.
        repo = os.path.join(HERE, "..")
        self.assertFalse(self.m._metrics_transient_root(repo))

    def test_s4d2_a_symlink_does_not_get_the_gate_around(self):
        """S4d-2. 임시 자리 판정은 **realpath** 로 잰다.

        경로 글자만 보면 집 안에 걸어 둔 링크 하나로 관문이 열린다 — 링크는
        임시 자리처럼 생기지 않았지만 가리키는 곳은 임시 자리다. 겹쳐 뜨는
        수집기를 막는 관문이 그렇게 우회되면 막은 적이 없는 것과 같다.
        """
        real = tempfile.mkdtemp(prefix="s9metlink-")
        link = os.path.join(HERE, ".s9metlink-probe")
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError):
            shutil.rmtree(real, ignore_errors=True)
            self.skipTest("이 파일 시스템은 심볼릭 링크를 만들 수 없다")
        try:
            # 글자만 보면 저장소 안이다 — 가리키는 곳이 임시 자리일 뿐이다.
            self.assertNotIn(os.path.realpath(tempfile.gettempdir()), link)
            self.assertTrue(self.m._metrics_transient_root(link))
            self.assertFalse(self.m.metrics_detach(link))
        finally:
            os.remove(link)
            shutil.rmtree(real, ignore_errors=True)

    def test_s4e_the_collector_leaves_when_its_place_is_gone(self):
        """S4e. 제 잠금이 사라진 수집기는 다음 바퀴에 스스로 물러난다.

        관문은 앞으로 뜰 것만 막는다 — 이미 떠 있던 것이 자리를 잃고도 계속
        도는 자리가 이 결함의 나머지 반이다.
        """
        p = self.m._metrics_paths(self.tmp)
        os.makedirs(p["dir"], exist_ok=True)
        if os.path.exists(p["lock"]):
            os.remove(p["lock"])
        self.assertEqual(self.m.metrics_loop(self.tmp, interval=0, limit=1),
                         "자리가 사라졌다")

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

    def test_s11_the_local_lane_splits_no_line_from_cannot_get_out(self):
        """S11. 국소 대조군이 「회선이 없다」와 「밖으로 못 나간다」를 가른다.

        실사고 2026-09-03: 세 갈래가 전부 바깥을 향해, 동시 불통을 보고 리드가
        WSL 네트워크 죽음의 재발로 보고했다. 사용자 정정 — "방금 출근길이어서
        네트웍이 끊긴건 정상이다." 사고 판정에서 그 둘은 정반대다: 하나는
        고칠 것이 없고 하나는 결함이다 (REQ-20260903-002).
        """
        def sample(link=None):
            net = {"api": _bad("api", "tcp"), "ctl": _bad("ctl", "tcp"),
                   "dns": _bad("dns", "dns")}
            if link is not None:
                net["link"] = link
            return {"ts": "2026-09-03T08:00:00+09:00", "boot": 1,
                    "net": net, "sys": {"tcp_tw": 10}}

        # L3. 링크도 죽었다 — 회선이 없다(고칠 것 없음).
        v = self.m.metrics_verdict(
            [sample({"label": "link", "ok": False, "backend": "proc"})])
        self.assertIn("회선이 없다", v["verdict"])
        self.assertEqual(v["link_fail"], 1)

        # L4. 링크는 살았다 — 밖으로 못 나갔다(결함).
        v = self.m.metrics_verdict(
            [sample({"label": "link", "ok": True, "backend": "proc"})])
        self.assertIn("밖으로 못 나갔다", v["verdict"])
        self.assertEqual(v["link_fail"], 0)

        # L5·L6. 링크를 모르거나(옛 표본·문 없는 판) 아예 없으면 종전 문구 —
        # 없는 근거로 판정하지 않는다.
        v = self.m.metrics_verdict([sample(None)])
        self.assertIn("회선 —", v["verdict"])
        self.assertNotIn("회선이 없다", v["verdict"])

    def test_s12_the_local_lane_answers_from_a_door(self):
        """S12. 국소 갈래는 **문** 안에서 판을 가른다 (DOC-20260903-004).

        원시 `/proc` 읽기를 늘리면 맥·윈도우가 같이 걸린다 — 그래서 읽는 자리를
        `link_backend()` 한 문에 두고, 문이 없는 판에서는 「모른다」고 답한다.
        모르는 것을 「붙어 있다」로 세면 이 갈래는 대조군이 아니라 거짓말이 된다.
        """
        be = self.m.link_backend()
        self.assertIn(be["backend"], ("proc", "none"))
        if be["backend"] == "none":
            self.assertIsNone(be["ok"], "모르는 판인데 붙어 있다고 답했다")
            self.assertEqual(self.m._probe_link()["stage"], "unknown")
            return
        # L1·L2. 이 판에서는 실제로 읽어 답한다.
        self.assertIsInstance(be["ok"], bool)
        lane = self.m._probe_link()
        self.assertEqual(lane["label"], "link")
        self.assertEqual(lane["backend"], "proc")
        if be["ok"]:
            self.assertTrue(lane["ok"])
            self.assertTrue(lane.get("iface"), "붙어 있다면서 인터페이스가 없다")

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
        src = open(S9_SRC, encoding="utf-8").read()
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

    # ---- 잠금·pid 파일의 단단함 (REQ-20260902-063, white-hacker 점검) -------
    # 이 호스트는 사용자가 하나라 실제 공격면이 0이지만, UID 가 섞이는 배치
    # (공유 빌드 기계)에서는 다르다. 막는 값이 공짜면 배치를 가정하지 않는다.

    def test_h1_lock_does_not_follow_a_symlink(self):
        """남이 심어 둔 링크를 따라가 그 파일에 pid 를 쓰지 않는다."""
        p = self.m._metrics_paths(self.tmp)
        os.makedirs(p["dir"], exist_ok=True)
        victim = os.path.join(self.tmp, "victim.txt")
        with open(victim, "w") as f:
            f.write("소중한 내용\n")
        if os.path.exists(p["lock"]):
            os.remove(p["lock"])
        os.symlink(victim, p["lock"])
        self.assertIsNone(self.m._metrics_lock(self.tmp),
                          "링크를 따라가 잠금을 잡았다")
        with open(victim) as f:
            self.assertEqual(f.read(), "소중한 내용\n", "남의 파일을 덮어썼다")
        os.remove(p["lock"])

    def test_h2_lock_is_not_world_readable(self):
        """0600 — 남이 읽을 이유가 없는 파일이다."""
        lock = self.m._metrics_lock(self.tmp)
        self.assertIsNotNone(lock)
        try:
            mode = os.stat(self.m._metrics_paths(self.tmp)["lock"]).st_mode
            self.assertEqual(mode & 0o077, 0, "잠금 파일이 남에게 열려 있다")
        finally:
            lock.close()

    def test_h3_stop_asks_who_that_pid_is(self):
        """죽이기 전에 그 pid 가 우리 수집기인지 묻는다.

        pid 파일의 숫자를 그대로 믿으면, 재사용된 pid 나 위조된 값이 가리키는
        남의 프로세스에 SIGTERM 이 간다."""
        self.assertFalse(self.m._metrics_is_collector(1),
                         "pid 1(init)을 수집기로 봤다")
        self.assertTrue(self.m._metrics_is_collector(10**9),
                        "/proc 에 없는 pid 는 판정을 미루지 않고 참으로 둔다")
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("_metrics_is_collector(pid)", src,
                      "stop 이 그 물음을 지나지 않는다")

    def test_h4_start_says_it_keeps_going_out_and_how_to_stop(self):
        """켜는 사람이 무엇을 켰는지 알아야 한다 — 비콘 고지."""
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        blk = src.split('if action == "start":', 1)[1][:1400]
        self.assertIn("밖으로 나간다", blk)
        self.assertIn("S9_NO_METRICS", blk)
        self.assertIn("metrics stop", blk)

    # ---- 봉우리를 놓치지 않는다 (REQ-20260903-004) ------------------------
    # 비용은 총량이 아니라 동시 최고치인데, 15초에 한 번 찍는 값은 그 사이의
    # 봉우리를 통째로 놓친다. 실제로 이 계기는 여덟 시간 동안 "몰린 순간"을
    # 한 번도 못 봤고, 그래서 리드가 원인을 못 짚었다.

    def test_p1_a_peak_between_samples_survives(self):
        """표본 사이에 솟은 값이 표본에 남는다."""
        self.m._PEAK.update({"tcp_inuse": 0, "sockets": 0})
        self.m._peak_tick()
        got = self.m._peak_take()
        self.assertIn("peak_tcp_inuse", got)
        self.assertGreater(got["peak_tcp_inuse"], 0)

    def test_p2_the_peak_is_emptied_each_time(self):
        """비우지 않으면 한 번 솟은 값이 영원히 따라붙어 계기가 거짓말한다."""
        self.m._PEAK.update({"tcp_inuse": 77, "sockets": 88})
        self.assertEqual(self.m._peak_take(),
                         {"peak_tcp_inuse": 77, "peak_sockets": 88})
        self.assertEqual(self.m._peak_take(), {},
                         "봉우리가 비워지지 않았다")

    def test_p3_zero_is_not_reported(self):
        """0 은 「한가하다」가 아니라 「모른다」다 — /proc 이 없는 판에서
        0 을 실으면 사람이 한가한 것으로 읽는다."""
        self.m._PEAK.update({"tcp_inuse": 0, "sockets": 0})
        self.assertEqual(self.m._peak_take(), {})

    def test_p4_windows_count_is_taken_once_a_minute(self):
        """powershell 왕복이 1~2초다 — 표본마다 재면 계기가 계기를 방해한다."""
        import time as _t
        self.m._WIN_BOUND.update({"at": _t.time(), "value": 4242})
        self.assertEqual(self.m._win_bound(), 4242)
        self.assertGreaterEqual(self.m.METRICS_WIN_EVERY, 30)

    def test_p5_no_windows_side_does_not_break_the_sample(self):
        """powershell 이 없거나 실패해도 그 키만 빠지고 표본은 산다."""
        was = self.m.shutil.which
        self.m._WIN_BOUND.update({"at": 0.0, "value": None})
        self.m.shutil.which = lambda *a, **k: None
        try:
            self.assertIsNone(self.m._win_bound())
            s = self.m._sys_sample()
        finally:
            self.m.shutil.which = was
        self.assertNotIn("win_bound", s)
        self.assertIn("open_files", s, "표본 전체가 죽었다")

    def test_p6_the_loop_looks_while_it_sleeps(self):
        """자는 동안에도 봐야 봉우리가 잡힌다 — 그냥 sleep(interval) 이면
        15초짜리 눈 감기다."""
        import inspect
        src = inspect.getsource(self.m.metrics_loop)
        self.assertIn("_peak_tick()", src)
        self.assertNotIn("time.sleep(interval)", src)


class CrossingLoad(unittest.TestCase):
    """계기가 경계-넘는 연결로 동적 포트에 얹는 부하 (REQ-20260904-012 · -020).

    로컬 127.0.0.1 연결은 윈도우 중계를 안 거치지만, 계기의 api·ctl 은 밖으로
    나가 경계를 넘고 그 매핑을 중계가 제 수명 동안 쥔다. 그래서 이 주기는
    「사고를 얼마나 빨리 보나」와 「하루에 포트를 얼마나 태우나」의 맞바꿈이다.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9mload-")
        spec = importlib.util.spec_from_loader(
            "s9mload", importlib.machinery.SourceFileLoader("s9mload", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_l1_interval_is_a_ratchet_down(self):
        """L1. 주기는 내려갈 때만 고친다 — 부하는 는 적이 없어야 한다.

        올려야 하면(사고 감지를 더 빨리) 그 까닭을 여기 적어라. 지금 30 은
        15 에서 내린 값이다(REQ-20260904-012: 15초면 하루 ~17,000 경계-넘기).
        """
        self.assertGreaterEqual(self.m.METRICS_INTERVAL_SEC, 30,
                                "주기를 줄이면 포트 부하가 는다 — 까닭을 이 시험에 적어라")

    def test_l2_peak_detection_is_independent_of_the_interval(self):
        """L2. 봉우리는 주기와 무관하게 1초로 본다 — 주기를 늘려도 안 놓친다.

        metrics_loop 이 표본과 표본 사이를 `min(1.0, left)` 로 훑으며 매초
        `_peak_tick` 을 부른다. 이 구조가 없으면 주기를 늘리는 순간 봉우리가
        통째로 사라진다(REQ-20260903-004 가 세운 것).
        """
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "s9.py"), encoding="utf-8").read()
        loop = src.split("def metrics_loop", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_peak_tick()", loop)
        self.assertIn("min(1.0, left)", loop,
                      "표본 사이를 1초로 안 훑는다 — 주기를 늘리면 봉우리를 놓친다")

    def test_l3_a_sample_opens_a_bounded_number_of_crossings(self):
        """L3. 한 표본이 여는 경계-넘는 갈래는 유계다(api·ctl) — 늘면 이 수를 고쳐라."""
        s = self.m.metrics_sample(self.tmp)
        crossing = [k for k in s["net"] if k in ("api", "ctl")]
        self.assertEqual(sorted(crossing), ["api", "ctl"],
                         "밖으로 나가는 갈래가 바뀌었다 — 부하 계산을 다시 하라")


if __name__ == "__main__":
    unittest.main()
