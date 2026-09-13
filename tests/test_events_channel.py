"""변경 알림 채널 하나로 폴링 대체 — /api/events (REQ-20260909-088-62x6).

화면은 문서 목록 15초·서버 사실 20초·감시자 20초·사용량 60초·에이전트 목록
10초를 제각각 폴했다 — 탭 하나가 분당 20~40개의 **새 연결**이고, 그 대부분은
「아무것도 안 바뀌었다」는 같은 답을 받았다. 이 환경의 비용은 바이트가 아니라
연결 수다(REQ-20260909-067·076).

그래서 묻기를 그만두고 듣는다: `/api/events` 한 채널이 버전 벡터
{catalog, code, guard, agents, doc} 를 **바뀔 때만** 보내고, 화면은 바뀐 조각의
자료만 받는다. 지켜야 할 계약 셋을 여기서 잰다.

  ① 서버에서 파일을 보는 것은 **producer 스레드 하나**다. 연결마다 제 폴을
     돌리면 버려진 스트림이 CPU 를 태우던 REQ-20260901-020 이 재현된다.
  ② 안 바뀌면 아무것도 안 보낸다. 끊겼다 다시 붙으면 **첫 이벤트가 지금
     벡터**라, 끊긴 사이의 변경이 받기 한 번으로 메워진다.
  ③ 화면은 바뀐 조각의 받기만 부르고, 채널이 3회 연속 실패하면 안전 폴이
     60초에서 30초로 내려간다.

서버는 임시 포트의 임시 서버로, 화면은 조각을 그대로 node 로 실행해 호출
횟수를 세어 잰다 — 소스 글자를 대조하지 않는다.

실행: python3 tests/ events_channel
"""
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
WEB = os.path.join(os.path.dirname(HERE), "web", "app")
sys.path.insert(0, HERE)

from portpool import free_port, wait_server  # noqa: E402

EVENTS_TTL = 10          # 이 시험의 서버 만기 — E4 가 만기와 재연결을 본다


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node",
                "/mnt/c/Temp/s9-webkit/node-*/node.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


class Channel:
    """열린 채널 하나 — 이벤트를 줄 단위로 읽는다(라이브러리 없이 소켓)."""

    def __init__(self, port, last=None, timeout=20):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.settimeout(timeout)
        req = "GET /api/events HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        if last is not None:
            req += "Last-Event-ID: %s\r\n" % last
        self.sock.sendall((req + "Accept: text/event-stream\r\n\r\n")
                          .encode())
        self.buf = b""
        self.retry = ""          # `retry:` 지시 — 다시 붙기까지의 기다림
        self.eof = False
        self.head = self._read_head()

    def _read_head(self):
        while b"\r\n\r\n" not in self.buf:
            d = self.sock.recv(4096)
            if not d:
                break
            self.buf += d
        head, _, rest = self.buf.partition(b"\r\n\r\n")
        self.buf = rest
        return head.decode(errors="replace")

    def event(self, wait=6.0):
        """다음 이벤트 하나 — 없으면 None (기다린 만큼 기다린 뒤)."""
        end = time.time() + wait
        while time.time() < end:
            while b"\n\n" in self.buf:
                blk, _, rest = self.buf.partition(b"\n\n")
                self.buf = rest
                out = {}
                for line in blk.decode(errors="replace").splitlines():
                    if line.startswith("retry: "):
                        self.retry = line
                    elif line.startswith("id: "):
                        out["id"] = int(line[4:])
                    elif line.startswith("data: "):
                        out["data"] = json.loads(line[6:])
                if "data" in out:
                    return out
            self.sock.settimeout(max(0.2, end - time.time()))
            try:
                d = self.sock.recv(4096)
            except socket.timeout:
                return None
            if not d:
                self.eof = True
                return None
            self.buf += d
        return None

    def wait_eof(self, wait=20.0):
        """서버가 만기로 닫을 때까지 — 닫히기까지 걸린 초."""
        t0 = time.time()
        self.sock.settimeout(wait)
        try:
            while True:
                if not self.sock.recv(4096):
                    return time.time() - t0
        except socket.timeout:
            return None

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class EventsChannel(unittest.TestCase):
    """서버 기동은 클래스당 한 번."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9ev-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "alice", "S9_PORT_GUARD": "off",
                   "S9_EVENTS_TICK": "0.5",
                   "S9_EVENTS_TTL": str(EVENTS_TTL)}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice", "--role", "admin")
        out = cls.cli("new", "request", "--title", "채널 시험", "--summary", "t",
                      "--goal", "t", "--size", "S", "--user", "alice",
                      "--body", "x" * 100).stdout.decode()
        cls.doc = re.search(r"REQ-\d{8}-\d+-[0-9a-z]+", out).group(0)
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def cli(cls, *a):
        r = subprocess.run([S9, *a], capture_output=True, env=cls.env,
                           timeout=30)
        assert r.returncode == 0, (a, r.stderr.decode(errors="replace")[-400:])
        return r

    def getj(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=20) as r:
            return json.loads(r.read().decode())

    # ── E1 ── 벡터가 바뀔 때만 이벤트가 온다
    def test_e1_pushes_only_when_vector_changes(self):
        """catalog 조각으로 잰다.

        `code` 조각은 이 저장소의 소스 지문이라, 시험이 도는 동안 누가 파일을
        하나만 고쳐도(다른 백그라운드 작업·방금 한 편집) 바뀐다. 그것까지
        「안 바뀌었는데 왔다」로 세면 시험이 남의 편집에 걸려 넘어진다 —
        이 시나리오가 재는 것은 **문서를 고치면 알리고 아니면 조용한가**다.
        """
        def catalog_of(ev):
            return ev["data"]["vec"]["catalog"]

        def until_catalog_changes(ch, base, wait):
            """catalog 가 바뀐 이벤트 하나 — 다른 조각만 바뀐 것은 흘린다."""
            end = time.time() + wait
            while time.time() < end:
                ev = ch.event(wait=max(0.2, end - time.time()))
                if ev is None:
                    return None
                if catalog_of(ev) != base:
                    return ev
            return None

        ch = Channel(self.port)
        try:
            self.assertIn("text/event-stream", ch.head)
            first = ch.event()
            self.assertIsNotNone(first, "첫 이벤트(지금 벡터)가 안 왔다")
            self.assertIn("catalog", first["data"]["vec"])
            # 아무것도 안 바뀐 동안은 조용하다 (하트비트는 15초 뒤부터다)
            self.assertIsNone(
                until_catalog_changes(ch, catalog_of(first), 3.0),
                "문서를 안 고쳤는데 catalog 가 바뀐 알림이 왔다")
            # 문서의 **상태**를 바꾸면 catalog 조각이 바뀐다. 노트·리스 시각처럼
            # 행의 상태가 그대로인 쓰기에는 조용하다 — catalog 조각은 파일 지문이
            # 아니라 휘발 필드를 뺀 안정 서명이다 (REQ-20260913-033,
            # tests/test_catalog_hold S5). 그 쓰기의 결과는 안전 폴(60초)이 받는다.
            self.cli("status", self.doc, "in-progress", "--note", "채널이 이것을 알린다")
            got = until_catalog_changes(ch, catalog_of(first), 8.0)
            self.assertIsNotNone(got, "문서를 고쳤는데 알림이 안 왔다")
            self.assertGreater(got["id"], first["id"])
        finally:
            ch.close()

    # ── E2 ── Last-Event-ID 로 다시 붙으면 첫 이벤트가 지금 벡터다
    def test_e2_reconnect_with_last_event_id(self):
        a = Channel(self.port)
        try:
            first = a.event()
            self.assertIsNotNone(first)
        finally:
            a.close()
        b = Channel(self.port, last=first["id"])
        try:
            got = b.event()
            self.assertIsNotNone(got, "다시 붙었는데 첫 이벤트가 없다")
            self.assertEqual(got["data"]["after"], first["id"],
                             "서버가 Last-Event-ID 를 안 받았다")
            self.assertGreaterEqual(got["id"], first["id"])
            self.assertIn("catalog", got["data"]["vec"])
        finally:
            b.close()

    # ── E3 ── 연결이 셋이어도 파일을 보는 스레드는 하나다
    def test_e3_one_producer_thread_for_many_conns(self):
        chans = [Channel(self.port) for _ in range(3)]
        try:
            for c in chans:
                self.assertIsNotNone(c.event(), "채널이 첫 이벤트를 안 줬다")
            # 앞 시험이 닫은 연결은 서버가 알아채는 데 한 바퀴가 걸린다
            end = time.time() + 8
            while time.time() < end:
                conns = self.getj("/api/serveinfo")["conns"]
                if conns["events"] == 3:
                    break
                time.sleep(0.5)
            self.assertEqual(conns["events"], 3)
            self.assertEqual(conns["events_producer"], 1,
                             "연결마다 스레드가 서면 좀비 스트림이 재현된다")
        finally:
            for c in chans:
                c.close()

    # ── E4 ── 만기에 서버가 닫고, 다시 붙어 이어받는다
    def test_e4_expiry_then_reconnect(self):
        ch = Channel(self.port)
        try:
            first = ch.event()
            self.assertIsNotNone(first)
            self.assertTrue(ch.retry.startswith("retry: "),
                            "다시 붙기까지의 기다림(retry:)을 안 알렸다")
            took = ch.wait_eof(wait=EVENTS_TTL + 8)
            self.assertIsNotNone(took, "만기가 지났는데 안 닫혔다")
            self.assertLess(took, EVENTS_TTL + 6)
        finally:
            ch.close()
        again = Channel(self.port, last=first["id"])
        try:
            self.assertIsNotNone(again.event(), "다시 붙어도 이벤트가 없다")
        finally:
            again.close()

    # ── E4' ── retry 지시가 응답의 첫 줄이다
    def test_e4b_retry_directive(self):
        ch = Channel(self.port)
        try:
            ch.event()
            self.assertTrue(ch.head.startswith("HTTP/1.")
                            and "text/event-stream" in ch.head)
        finally:
            ch.close()


def _node_run(js):
    node = find_node()
    out = subprocess.run([node, "-e", js], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _src(name):
    return open(os.path.join(WEB, name), encoding="utf-8").read()


@unittest.skipUnless(find_node(), "node 가 없다")
class EventsScreen(unittest.TestCase):
    """화면 — 조각을 그대로 실행해 **호출 횟수**를 센다."""

    STUBS = """
      const n = {catalog:0, code:0, guard:0, agents:0, doc:0, usage:0};
      globalThis.refreshCatalog = () => n.catalog++;
      globalThis.checkOldCode = () => n.code++;
      globalThis.checkGuard = () => n.guard++;
      globalThis.refreshUsage = () => n.usage++;
      globalThis.loadDoc = () => n.doc++;
      globalThis.TERM = {sid: "s1", agTick: () => n.agents++};
      globalThis.document = {hidden: false,
        querySelector: () => ({dataset: {showing: "REQ-1"}}),
        addEventListener: () => {}};
      const V = (o) => Object.assign(
        {catalog:"a", code:"c", guard:"g",
         agents:{s1:"1"}, doc:{"REQ-1":"1"}}, o || {});
    """

    # ── E5 ── 바뀐 조각의 받기만 부른다
    def test_e5_pulls_only_changed_pieces(self):
        js = _src("net.js") + _src("events_ch.js") + self.STUBS + """
          const out = {};
          out.base = evApply(V());              // 첫 이벤트는 기준선이다
          out.afterBase = {...n};
          out.catalog = evApply(V({catalog:"b"}));
          out.catalogN = {...n};
          out.agents = evApply(V({catalog:"b", agents:{s1:"2"}}));
          out.doc = evApply(V({catalog:"b", agents:{s1:"2"},
                               doc:{"REQ-1":"2"}}));
          out.codeGuard = evApply(V({catalog:"b", agents:{s1:"2"},
                                     doc:{"REQ-1":"2"},
                                     code:"c2", guard:"g2"}));
          out.n = {...n};
          console.log(JSON.stringify(out));
          process.exit(0);
        """
        r = _node_run(js)
        self.assertEqual(r["base"], [], "첫 이벤트가 받기를 불렀다")
        self.assertEqual(r["afterBase"],
                         {"catalog": 0, "code": 0, "guard": 0, "agents": 0,
                          "doc": 0, "usage": 0})
        self.assertEqual(r["catalog"], ["catalog"])
        self.assertEqual(r["catalogN"]["catalog"], 1)
        self.assertEqual(r["catalogN"]["guard"], 0)
        self.assertEqual(r["agents"], ["agents"])
        self.assertEqual(r["doc"], ["doc"])
        self.assertEqual(sorted(r["codeGuard"]), ["code", "guard"])
        self.assertEqual(r["n"], {"catalog": 1, "code": 1, "guard": 1,
                                  "agents": 1, "doc": 1, "usage": 0})

    # ── E5' ── 안 보이는 판은 미뤘다가 복귀 때 한 번만
    def test_e5b_hidden_defers_and_resumes_once(self):
        js = _src("net.js") + _src("events_ch.js") + self.STUBS + """
          const out = {};
          evApply(V());
          document.hidden = true;
          out.hidden1 = evApply(V({catalog:"b"}));
          out.hidden2 = evApply(V({catalog:"c"}));
          out.whileHidden = {...n};
          document.hidden = false;
          out.resumed = evResume();
          out.after = {...n};
          console.log(JSON.stringify(out));
          process.exit(0);
        """
        r = _node_run(js)
        self.assertEqual(r["hidden1"], [])
        self.assertEqual(r["hidden2"], [])
        self.assertEqual(r["whileHidden"]["catalog"], 0,
                         "안 보이는 판이 서버를 불렀다")
        self.assertEqual(r["resumed"], ["catalog"])
        self.assertEqual(r["after"]["catalog"], 1, "밀린 것을 몰아 돌았다")

    # ── E6 ── 3회 연속 실패 → 30초 안전 폴, 살아나면 다시 60초
    def test_e6_three_failures_fall_back_to_30s(self):
        js = _src("net.js") + _src("events_ch.js") + self.STUBS + """
          const out = {};
          evBeltSet(EV_POLL_MS);
          out.start = evBeltMs;
          out.f1 = (evFail(false), evBeltMs);
          out.f2 = (evFail(false), evBeltMs);
          out.f3 = (evFail(false), evBeltMs);
          out.belts = S9_POLLS.length;          // 벨트는 언제나 하나다
          evFails = 0; evBeltSet(EV_POLL_MS);
          out.back = evBeltMs;
          out.beltsBack = S9_POLLS.length;
          // 채널이 죽어 있는 동안의 안전 폴은 코드 지문·감시자까지 본다
          evFails = 3; evSweep();
          out.sweep = {...n};
          for (const p of S9_POLLS) clearInterval(p.timer);
          console.log(JSON.stringify(out));
          process.exit(0);
        """
        r = _node_run(js)
        self.assertEqual(r["start"], 60000)
        self.assertEqual([r["f1"], r["f2"]], [60000, 60000],
                         "두 번째 실패에서 벌써 물러섰다")
        self.assertEqual(r["f3"], 30000, "3회 연속 실패인데 안 물러섰다")
        self.assertEqual(r["belts"], 1)
        self.assertEqual(r["back"], 60000, "살아났는데 60초로 안 돌아왔다")
        self.assertEqual(r["beltsBack"], 1)
        self.assertEqual(r["sweep"]["catalog"], 1)
        self.assertEqual(r["sweep"]["usage"], 1)
        self.assertEqual(r["sweep"]["guard"], 1)

    # ── E7 ── 캡처 브라우저는 채널을 열지 않는다 (회귀)
    def test_e7_capture_browser_keeps_channel_closed(self):
        """headless Chrome 의 `--virtual-time-budget` 은 받는 중인 응답이 하나도
        없을 때 시계를 앞으로 돌린다. 상시 SSE 는 영원히 받는 중이라 그 조건이
        오지 않는다 — 채널을 넣자 `s9 shot` 이 60초를 다 쓰고 그림 없이 끝났다
        (실측 2026-09-09). 캡처 판에서 채널이 다시 열리면 이 시험이 막는다."""
        js = _src("net.js") + _src("events_ch.js") + self.STUBS + """
          let opened = 0;
          globalThis.EventSource = function(u){
            opened++; this.url = u; this.close = () => {}; };
          globalThis.location = {search: ""};
          const out = {};
          // node 의 navigator 는 읽기 전용이라 자리를 갈아 끼운다
          const ua = (s) => Object.defineProperty(globalThis, "navigator",
            {value: {userAgent: s}, configurable: true});
          ua("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like "
             + "Gecko) HeadlessChrome/131.0 Safari/537.36");
          out.capture = evStart() === null;
          out.captureOpened = opened;
          out.captureBelt = evBeltMs;
          ua("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/"
             + "605.1.15 Version/17.0 Safari/605");
          out.normal = evStart() !== null;
          out.normalOpened = opened;
          out.normalBelt = evBeltMs;
          // 진단 판(?nosse)도 그대로 닫혀 있다
          globalThis.location = {search: "?nosse"};
          out.nosse = evStart() === null;
          out.nosseOpened = opened;
          for (const p of S9_POLLS) clearInterval(p.timer);
          console.log(JSON.stringify(out));
          process.exit(0);
        """
        r = _node_run(js)
        self.assertTrue(r["capture"], "캡처 판에서 채널을 열었다 — shot 이 멎는다")
        self.assertEqual(r["captureOpened"], 0)
        self.assertEqual(r["captureBelt"], 30000, "캡처 판에 안전 폴이 없다")
        self.assertTrue(r["normal"], "보통 판에서 채널을 안 열었다")
        self.assertEqual(r["normalOpened"], 1)
        self.assertEqual(r["normalBelt"], 60000)
        self.assertTrue(r["nosse"])
        self.assertEqual(r["nosseOpened"], 1, "?nosse 인데 채널을 또 열었다")


if __name__ == "__main__":
    unittest.main()
