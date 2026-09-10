"""탭과 화면이 어긋난다 (REQ-20260908-056-62x6).

사용자가 본 것: 헤더의 알약은 **Board** 인데 그려진 판은 **관계도**였다. 그리고
그 반대 — 관계도를 눌렀는데 화면에는 직전 보드가 그대로 남았다.

원인은 하나다. `renderGraph()` 는 관계도를 받으러 한 번 멈추는데, 깨어난 뒤
조건 없이 `#view` 를 덮었다. 그 사이 사람이 Board 로 옮겨 갔어도 마찬가지였다.
멈추는 동안 판은 직전 탭의 화면이었고, 깨어나면 지금 탭의 판을 덮었다.
게다가 15초 카탈로그 갱신이 바뀔 때마다 관계도 캐시를 버려서, 이 멈춤은 첫
진입만의 일이 아니라 **15초마다 새로 열리는 틈**이었다.

이 시험은 소스 글자를 대조하지 않는다. 실브라우저를 띄우고 `/api/graph` 응답을
일부러 늦춘 뒤 **실제로 탭을 눌러**, 알약과 판이 같은 것을 말하는지 잰다.

실행: python3 tests/ tab_pane_match
"""
import json
import os
import subprocess
import time
import unittest
import urllib.error
import urllib.request

from cdpreal import WS, chrome_path, reclaim, wait_ready
from portpool import free_port, wait_server

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")

# /api/graph 응답을 늦추거나 실패시키는 손잡이. 사고는 느린 응답에서만 드러나는데
# 느린 응답은 정상 서버로 만들 수 없다 — 그래서 브라우저 쪽에서 만든다.
HOOK = r"""
(() => {
  if (!window.__origFetch){
    window.__origFetch = window.fetch;
    window.__gdelay = 0; window.__gfail = false; window.__gdone = 0;
    window.fetch = function(u, o){
      if (String(u).indexOf("/api/graph") >= 0){
        if (window.__gfail)
          return Promise.resolve(new Response("no", {status: 500}));
        return new Promise(r => setTimeout(
          () => r(window.__origFetch(u, o).then(res => {
            window.__gdone++;   // 늦춘 응답이 실제로 도착한 때
            return res;
          })), window.__gdelay));
      }
      return window.__origFetch(u, o);
    };
  }
  return true;
})()
"""

# 알약이 말하는 것과 판이 말하는 것 — 한 번에 뜬다.
READ = r"""
(() => {
  const on = document.querySelector('header [data-tab].active');
  return {pill: on ? on.dataset.tab : "",
          canvas: !!document.querySelector('#gcanvas'),
          cols: document.querySelectorAll('#view .col').length,
          wait: !!document.querySelector('#view .gwait'),
          bad: !!document.querySelector('#view .gwait.bad')};
})()
""".strip()

CLICK = '(document.querySelector(\'header [data-tab="%s"]\').click(), true)'

# 고정 sleep 으로 기다리지 않는다 — 기계가 느린 날 그 숫자가 곧 간헐 실패다.
# 조건이 서면 바로 넘어가고, 안 서면 시한에서 끊는다.
WAIT_SEL = ('for (let i = 0; i < 160; i++){ '
            'if (document.querySelector(%s)) break; '
            'await new Promise(r => setTimeout(r, 50)); }')
# 늦춘 /api/graph 응답이 도착할 때까지 — 도착한 뒤에도 덮지 않는 것이 이 시험의
# 물음이므로, 도착을 기다린 다음 한 번 더 숨을 돌리고 잰다.
WAIT_GRAPH = ('for (let i = 0; i < 160; i++){ '
              'if (window.__gdone > n0) break; '
              'await new Promise(r => setTimeout(r, 50)); }\n'
              'await new Promise(r => setTimeout(r, 300));')


def js(body):
    """비동기 조각 — 브라우저 안에서 순서대로 실행하고 마지막 값을 돌려준다."""
    return "(async () => {\n%s\n})()" % body


SLEEP = "await new Promise(r => setTimeout(r, %d));"


class TheTabAndThePaneAgree(unittest.TestCase):
    """알약이 가리키는 탭과 그려진 판은 언제나 같은 것을 말한다."""

    out = None
    srv = None
    proc = None
    ws = None
    prof_wsl = None
    marker = None
    win = False

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path(pixel_contract=False)
        if chrome is None:
            raise unittest.SkipTest("실브라우저 미검증 — Chrome/Edge 를 찾지 못했다")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**os.environ, "S9_ROOT": ROOT, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.marker = "s9tabpane-%d" % os.getpid()
        cls.win = chrome.startswith("/mnt/")
        cls.prof_wsl = (("/mnt/c/Temp/" + cls.marker) if cls.win
                        else "/tmp/" + cls.marker)
        prof_arg = ("C:\\Temp\\" + cls.marker) if cls.win else cls.prof_wsl
        if cls.win:
            os.makedirs("/mnt/c/Temp", exist_ok=True)
        try:
            wait_server(cls.port)
            cls.proc = subprocess.Popen(
                [chrome, "--headless=new", "--disable-gpu",
                 "--user-data-dir=" + prof_arg, "--no-first-run",
                 "--no-default-browser-check", "--disable-extensions",
                 "--disable-background-networking", "--remote-debugging-port=0",
                 "--window-size=1440,900",
                 "http://127.0.0.1:%d/" % cls.port],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            dev = os.path.join(cls.prof_wsl, "DevToolsActivePort")
            cdp = None
            for _ in range(160):
                if os.path.exists(dev):
                    try:
                        with open(dev, encoding="utf-8") as f:
                            cdp = int(f.read().splitlines()[0])
                        break
                    except (ValueError, IndexError, OSError):
                        pass
                time.sleep(0.25)
            if cdp is None:
                raise ConnectionError("DevToolsActivePort 미출현")
            pages = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % cdp, timeout=10).read())
            page = next(p for p in pages if p.get("type") == "page")
            cls.ws = WS(page["webSocketDebuggerUrl"])
            wait_ready(cls.ws, needs=("whoami", "catalog"),
                       sels=("#view .col,#view .docs",))
            cls.ws.eval(HOOK)
            cls.out = {}
            cls.measure()
            unmeasured = [k for k, v in cls.out.items() if v is None]
        except (ConnectionError, StopIteration, OSError, RuntimeError,
                urllib.error.URLError) as e:
            cls.tearDownClass()
            raise unittest.SkipTest("실브라우저 미검증 — %r" % e)
        if unmeasured:
            cls.tearDownClass()
            raise AssertionError("판은 섰는데 재지 못했다: %s"
                                 % ", ".join(unmeasured))

    # ---- 재기 -------------------------------------------------------------
    @classmethod
    def await_(cls, expr):
        r = cls.ws.call("Runtime.evaluate", expression=expr,
                        returnByValue=True, awaitPromise=True)
        ex = r.get("exceptionDetails")
        if ex:
            # 브라우저 안에서 터진 것을 조용히 None 으로 삼키면 "못 쟀다"만 남고
            # 왜 못 쟀는지는 사라진다.
            raise RuntimeError("브라우저 안에서 실패: %s"
                               % (ex.get("exception", {}).get("description")
                                  or ex.get("text")))
        return r.get("result", {}).get("value")

    @classmethod
    def reset(cls, delay=0, fail=False):
        """관계도를 아직 한 번도 못 받은 상태로 되돌리고 보드에 선다."""
        return cls.await_(js(
            'window.__gdelay = %d; window.__gfail = %s;\n'
            'graph = null; graphStale = false;\n'
            % (delay, "true" if fail else "false")
            + (CLICK % "board") + ";\n" + (WAIT_SEL % "'#view .col'")
            + "\nreturn true;"))

    @classmethod
    def measure(cls):
        o = cls.out
        n0 = "const n0 = window.__gdone;\n"
        # S4 · S1 — 관계도를 누르면, 기다리는 동안에도 판은 보드가 아니고,
        #           받고 나면 관계도가 선다.
        cls.reset(delay=1200)
        o["going"] = cls.await_(js(
            (CLICK % "graph") + ";\n" + (SLEEP % 300) + "\nreturn " + READ + ";"))
        o["arrived"] = cls.await_(js(
            (WAIT_SEL % "'#gcanvas'") + "\nreturn " + READ + ";"))

        # S2 — 보드를 누르면 보드가 선다.
        o["board"] = cls.await_(js(
            (CLICK % "board") + ";\n" + (WAIT_SEL % "'#view .col'")
            + "\nreturn " + READ + ";"))

        # S3 — 늦게 온 관계도가 보드 판을 덮지 않는다 (이 REQ 의 실사고).
        cls.reset(delay=1200)
        o["late"] = cls.await_(js(
            n0 + (CLICK % "graph") + ";\n" + (SLEEP % 250) + "\n"
            + (CLICK % "board") + ";\n" + WAIT_GRAPH + "\nreturn " + READ + ";"))

        # S6 — 15초 벨트가 캐시를 낡았다고 표시한 뒤에도 같다.
        #      (a) 손에 든 판이 있으면 기다리지 않고 그대로 선다 — 화면이 안 비워진다.
        #      (b) 그 상태에서 보드로 옮겨도 늦게 온 관계도가 덮지 않는다.
        cls.reset(delay=0)
        cls.await_(js((CLICK % "graph") + ";\n" + (WAIT_SEL % "'#gcanvas'")
                      + "\nreturn true;"))
        o["stale_now"] = cls.await_(js(
            'const n0 = window.__gdone;\n'
            'window.__gdelay = 1200; graphStale = true; render();\n'
            + (SLEEP % 150) + "\nreturn " + READ + ";"))
        o["stale_late"] = cls.await_(js(
            n0 + (CLICK % "board") + ";\n" + WAIT_GRAPH
            + "\nreturn " + READ + ";"))

        # S5 — 관계도를 못 받아도 판이 다른 탭의 화면으로 남지 않는다.
        cls.reset(delay=0, fail=True)
        o["failed"] = cls.await_(js(
            (CLICK % "graph") + ";\n" + (WAIT_SEL % "'#view .gwait.bad'")
            + "\nreturn " + READ + ";"))
        cls.await_("(window.__gfail = false, true)")

    @classmethod
    def tearDownClass(cls):
        if cls.ws is not None:
            try:
                cls.ws.close()
            except OSError:
                pass
            cls.ws = None
        if cls.proc is not None:
            try:
                cls.proc.terminate()
            except OSError:
                pass
            cls.proc = None
        if cls.marker:
            reclaim(cls.marker, cls.win)
        if cls.srv is not None:
            cls.srv.terminate()
            try:
                cls.srv.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.srv.kill()
            cls.srv = None
        if cls.prof_wsl:
            import shutil
            shutil.rmtree(cls.prof_wsl, ignore_errors=True)

    # ---- 판정 -------------------------------------------------------------
    def test_the_tab_and_the_pane_agree(self):
        """알약이 가리키는 탭과 그려진 판은 언제나 같은 것을 말한다."""
        with self.subTest("waiting_pane_is_not_the_previous_tab"):   # S4
            d = self.out["going"]
            self.assertEqual(d["pill"], "graph", "알약이 관계도로 안 옮겨졌다")
            self.assertEqual(d["cols"], 0,
                             "관계도를 눌렀는데 판에는 보드 열이 그대로 남아 있다")
            self.assertTrue(d["wait"], "기다리는 동안 판이 아무 말도 하지 않는다")

        with self.subTest("the_graph_arrives"):                      # S1
            d = self.out["arrived"]
            self.assertEqual(d["pill"], "graph")
            self.assertTrue(d["canvas"], "관계도가 끝내 그려지지 않았다")
            self.assertFalse(d["wait"], "관계도가 왔는데 기다림 줄이 남아 있다")

        with self.subTest("the_board_stands"):                       # S2
            d = self.out["board"]
            self.assertEqual(d["pill"], "board")
            self.assertGreater(d["cols"], 0, "보드 열이 서지 않았다")
            self.assertFalse(d["canvas"], "보드인데 관계도 판이 남아 있다")

        with self.subTest("a_late_graph_does_not_cover_the_board"):   # S3
            d = self.out["late"]
            self.assertEqual(d["pill"], "board", "알약이 보드가 아니다")
            self.assertFalse(d["canvas"],
                             "늦게 온 관계도가 보드 판을 덮었다 — 이 REQ 의 사고")
            self.assertGreater(d["cols"], 0, "보드 열이 서지 않았다")
            self.assertFalse(d["wait"], "보드 판에 관계도 기다림 줄이 남았다")

        with self.subTest("a_stale_graph_is_not_blanked"):            # S6a
            d = self.out["stale_now"]
            self.assertEqual(d["pill"], "graph")
            self.assertTrue(d["canvas"],
                            "캐시가 낡았다고 판을 비웠다 — 15초마다 화면이 깜빡인다")
            self.assertFalse(d["wait"], "손에 든 판이 있는데 기다림 줄을 세웠다")

        with self.subTest("a_stale_refresh_does_not_cover_the_board"):  # S6b
            d = self.out["stale_late"]
            self.assertEqual(d["pill"], "board")
            self.assertFalse(d["canvas"],
                             "낡은 판을 갱신한 응답이 보드를 덮었다")
            self.assertGreater(d["cols"], 0)

        with self.subTest("a_failed_graph_says_so"):                  # S5
            d = self.out["failed"]
            self.assertEqual(d["pill"], "graph")
            self.assertEqual(d["cols"], 0,
                             "관계도를 못 받았는데 판에 보드가 남아 있다")
            self.assertTrue(d["bad"], "못 받은 사실을 화면이 말하지 않는다")


if __name__ == "__main__":
    unittest.main()
