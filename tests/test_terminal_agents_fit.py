"""터미널 하단 에이전트 목록은 상자 안에서 스크롤한다 (REQ-20260909-075).

사람이 보는 것은 출력이고 목록은 보조인데, 항목이 늘면 그만큼 줄을 가져가 출력
판이 그대로 줄었다. 실브라우저(CDP)로 잰다 — 열두 개일 때 목록 상자가 상한
(세 줄 반) 안이고 출력 판이 터미널 판의 60% 이상인지, 두 개일 때는 상자가 잘리지
않고 예전처럼 두 줄인지, 라벨이 아무리 길어도 행이 한 줄인지.
소스 글자를 세지 않고 렌더된 높이를 잰다. Chrome 이 없으면 건너뛴다.

실행: python3 tests/ terminal_agents_fit
"""
import json
import os
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
from cdpreal import WS, chrome_path, reclaim, wait_ready  # noqa: E402
from portpool import free_port, wait_server  # noqa: E402

VIS_ROWS = 3.5      # 상자가 보여 주는 줄 수 — 반 줄은 "더 있다"를 말하는 손잡이
OUT_FLOOR = 0.60    # 출력 판이 터미널 판에서 차지해야 하는 최소 몫


class TerminalAgentsFit(unittest.TestCase):
    srv = proc = ws = None

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path()
        if chrome is None:
            raise unittest.SkipTest("실브라우저 미검증 — Chrome/Edge 를 찾지 못했다")
        cls.port = free_port()
        cls.srv = subprocess.Popen([S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
                                   env={**os.environ, "S9_ROOT": ROOT, "S9_REWORK_WATCH": "off"},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.marker = "s9agfit-%d" % os.getpid()
        cls.win = chrome.startswith("/mnt/")
        cls.prof_wsl = ("/mnt/c/Temp/" + cls.marker) if cls.win else "/tmp/" + cls.marker
        prof_arg = ("C:\\Temp\\" + cls.marker) if cls.win else cls.prof_wsl
        if cls.win:
            os.makedirs("/mnt/c/Temp", exist_ok=True)
        try:
            wait_server(cls.port)
            cls.proc = subprocess.Popen(
                [chrome, "--headless=new", "--disable-gpu", "--user-data-dir=" + prof_arg,
                 "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                 "--disable-background-networking", "--remote-debugging-port=0",
                 "--window-size=1280,1000",
                 "http://127.0.0.1:%d/index.html#terminal" % cls.port],
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
            # 판의 높이는 내 화면 설정(skin·tone·density)이 정하고, 그 설정은 신원과
            # 사용자 목록이 둘 다 온 뒤에야 입혀진다 (test_terminal_fit 과 같은 자).
            wait_ready(cls.ws, needs=("whoami", "users"), sels="#cc-agents")
        except (ConnectionError, StopIteration, OSError, RuntimeError,
                urllib.error.URLError) as e:
            cls.tearDownClass()
            raise unittest.SkipTest("실브라우저 미검증 — %r" % e)

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
        reclaim(cls.marker, cls.win)
        if cls.srv is not None:
            cls.srv.terminate()
            try:
                cls.srv.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.srv.kill()
            cls.srv = None

    def draw(self, n):
        """에이전트 n개를 그린 뒤 판·상자·행의 실제 높이를 잰다 (?agdemo)."""
        js = ("(function(){history.replaceState(null,'','?agdemo=%d#terminal');"
              "termAgentsRender(TERM);"
              "const box=document.getElementById('cc-agents');"
              "const root=document.getElementById('cc-root');"
              "const out=document.querySelector('#cc-root .ccoutwrap');"
              "const rows=[...box.children].map(r=>r.getBoundingClientRect().height);"
              "return {rows:rows.length, tall:Math.max(0,...rows), line:rows[0]||0,"
              " box:box.getBoundingClientRect().height, inner:box.scrollHeight,"
              " top:box.scrollTop, seen:box.clientHeight,"
              " root:root.getBoundingClientRect().height,"
              " out:out.getBoundingClientRect().height,"
              " page:document.documentElement.scrollHeight, win:window.innerHeight};})()"
              % n)
        m = self.ws.eval(js)
        time.sleep(0.1)
        return m

    # A1. 열두 개여도 상자는 상한 안이고, 출력 판은 판의 60% 이상이며 하나도
    #     없을 때보다 세 줄 반 넘게 작지 않다.
    def test_a1_twelve_agents_never_eat_the_output_pane(self):
        none = self.draw(0)
        m = self.draw(12)
        self.assertEqual(m["rows"], 12, "열두 행이 다 서야 한다(버리지 않는다): %r" % m)
        # 판의 높이 자체는 위 띠가 서고 지는 데 따라 변한다 — 출력 판이 아닌
        # 몫(판 - 출력)이 목록 상자만큼만 늘었는지로 잰다.
        rest0, rest = none["root"] - none["out"], m["root"] - m["out"]
        self.assertLessEqual(rest - rest0, m["box"] + 2,
                             "에이전트가 열둘로 늘자 출력 판이 상자 높이보다 더 줄었다: %r %r"
                             % (none, m))
        self.assertLessEqual(m["box"], m["line"] * VIS_ROWS + 2,
                             "목록 상자가 정해진 높이를 넘었다: %r" % m)
        self.assertGreaterEqual(m["out"], m["root"] * OUT_FLOOR,
                                "출력 판이 판의 %d%% 아래로 줄었다: %r" % (OUT_FLOOR * 100, m))
        self.assertLessEqual(m["page"], m["win"] + 2, "판이 창 밖으로 밀렸다: %r" % m)

    # A2. 최신 항목이 보이게 상자는 바닥에 붙어 있다
    def test_a2_the_box_stays_at_the_newest_row(self):
        m = self.draw(12)
        self.assertGreater(m["inner"], m["seen"], "열둘인데 스크롤이 안 생겼다: %r" % m)
        self.assertLessEqual(m["inner"] - m["seen"] - m["top"], 2,
                             "다시 그린 뒤 상자가 맨 위로 튀었다 — 최신 행이 숨는다: %r" % m)

    # A3. 두 개일 때는 잘리지 않고 예전 그대로다
    def test_a3_a_short_list_looks_exactly_as_before(self):
        small = self.draw(2)
        self.assertEqual(small["rows"], 2, small)
        self.assertLessEqual(small["inner"] - small["seen"], 1,
                             "두 개인데 상자가 잘렸다: %r" % small)
        self.assertLessEqual(abs(small["box"] - small["line"] * 2), 2,
                             "두 개일 때 상자 높이가 두 줄이 아니다: %r" % small)
        big = self.draw(12)
        self.assertLess(big["box"] - small["box"], small["line"] * 2,
                        "항목이 열둘로 늘자 상자가 두 줄 넘게 자랐다: %r %r" % (small, big))

    # A4. 라벨이 아무리 길어도 한 행은 한 줄이다
    def test_a4_a_long_label_never_folds_a_row_into_two_lines(self):
        m = self.draw(12)
        tall = self.ws.eval(
            "(function(){const el=document.querySelector('#cc-agents .aglab');"
            " el.textContent='아주 긴 라벨 '.repeat(40);"
            " const r=el.closest('.ag').getBoundingClientRect().height;"
            " return r;})()")
        self.assertLessEqual(tall, m["line"] + 2,
                             "라벨이 길어지자 행이 두 줄로 접혔다: %.1f > %.1f"
                             % (tall, m["line"]))


if __name__ == "__main__":
    unittest.main()
