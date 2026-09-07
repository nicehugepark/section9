"""터미널 판은 남은 화면을 정확히 차지하고, 미답 질문은 목록 맨 앞에 선다 (REQ-20260906-089 · 087).

실브라우저(CDP)로 잰다 — 「서버가 옛 코드」 띠를 억지로 세워도 body 에 세로 스크롤이
생기지 않고 터미널 판의 바닥이 창 안에 있는지, Docs 의 question 무리에서 미답이
맨 앞에 서는지. Chrome 이 없으면 건너뛴다.

실행: python3 tests/ terminal_fit
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


class TerminalFit(unittest.TestCase):
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
        cls.marker = "s9termfit-%d" % os.getpid()
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
                 "--window-size=1280,760", "http://127.0.0.1:%d/#terminal" % cls.port],
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
            pages = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % cdp, timeout=10).read())
            page = next(p for p in pages if p.get("type") == "page")
            cls.ws = WS(page["webSocketDebuggerUrl"])
            # 판의 높이는 내 화면 설정(skin·tone·density)이 정하고, 그 설정은
            # 신원과 사용자 목록이 **둘 다** 온 뒤에야 applyMyUI 가 입힌다
            # (web/app/boot.js) — 둘을 이름으로 적어 기다린다 (REQ-20260907-057).
            wait_ready(cls.ws, needs=("whoami", "users"), sels="#cc-root")
        except (ConnectionError, StopIteration, OSError, RuntimeError, urllib.error.URLError) as e:
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

    def fit(self):
        return self.ws.eval("(function(){const r=document.getElementById('cc-root').getBoundingClientRect();"
                            "return {scroll:document.documentElement.scrollHeight, inner:window.innerHeight,"
                            " bottom:Math.round(r.bottom), top:Math.round(r.top)};})()")

    # F1. 띠가 서든 말든 판의 바닥은 창 안이고 body 에 세로 스크롤이 없다
    def test_f1_the_pane_fits_the_window_with_and_without_the_banner(self):
        a = self.fit()
        self.assertLessEqual(a["scroll"], a["inner"] + 2, a)
        self.assertLessEqual(a["bottom"], a["inner"] + 2, a)
        self.ws.eval("(function(){const el=document.getElementById('oldcode'); el.hidden=false;"
                     " el.innerHTML='<b>시험용 띠 — 서버가 옛 코드로 실행 중입니다</b>'; return true;})()")
        time.sleep(0.6)
        b = self.fit()
        self.assertGreater(b["top"], a["top"], "띠를 세웠는데 판의 윗변이 안 내려갔다")
        self.assertLessEqual(b["scroll"], b["inner"] + 2, b)
        self.assertLessEqual(b["bottom"], b["inner"] + 2, "띠가 서자 판이 창 밖으로 밀렸다: %r" % b)
        self.ws.eval("(function(){const el=document.getElementById('oldcode'); el.hidden=true; el.innerHTML=''; return true;})()")
        time.sleep(0.6)
        c = self.fit()
        self.assertLessEqual(c["bottom"], c["inner"] + 2, c)

    # F2. Docs 의 question 무리는 미답이 맨 앞이다
    def test_f2_unanswered_questions_come_first(self):
        want = [ln.split()[0] for ln in subprocess.run(
            [S9, "ls", "--type", "question", "--unanswered"], capture_output=True, text=True,
            env={**os.environ, "S9_ROOT": ROOT}).stdout.splitlines() if ln.startswith("QST-")]
        if not want:
            self.skipTest("미답 질문이 없다 — 순서를 잴 재료가 없다")
        self.ws.eval("location.hash = '#docs'; true")
        for _ in range(80):
            if self.ws.eval("!!document.querySelector('[data-typef=\"question\"]')"):
                break
            time.sleep(0.25)
        else:
            self.fail("타입바에 question 무리가 안 섰다 — 순서를 잴 재료가 없다")
        self.ws.eval("document.querySelector('[data-typef=\"question\"]').click(); true")
        # 고정 대기(0.8초)는 부하가 걸린 판에서 짧다 — 목록이 다시 그려질 때까지
        # 기다리되, 안 오면 아래 판정이 그대로 실패한다 (REQ-20260907-057).
        rows, head = [], []
        for _ in range(40):
            time.sleep(0.25)
            rows = self.ws.eval(
                "[...document.querySelectorAll('.doclist .row')].map(r => r.dataset.doc)") or []
            head = rows[:len(want)]
            if rows and sorted(head) == sorted(want):
                break
        self.assertTrue(rows, "질문 목록이 비어 있다")
        self.assertEqual(sorted(head), sorted(want),
                         "타입바가 %d장 남았다는데 목록 맨 앞이 그 다섯이 아니다: %r" % (len(want), head))


if __name__ == "__main__":
    unittest.main()
