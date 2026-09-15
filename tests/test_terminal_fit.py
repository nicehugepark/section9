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
        chrome = chrome_path(pixel_contract=False)
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
        # 서버가 실제로 알림을 주면 줄은 이미 차 있다 — 바꿔치기가 아니라
        # **한 줄을 더해야** 「띠가 섰다」가 언제나 참이 된다.
        self.ws.eval("(function(){const el=document.getElementById('notices');"
                     " el.insertAdjacentHTML('beforeend', '<div class=\"nrow note\" id=\"fit-probe\">'"
                     " + '<span class=\"n-mark\"></span><span class=\"n-txt\">시험용 한 줄</span>'"
                     " + '<span class=\"n-act\"></span></div>'); return true;})()")
        time.sleep(0.6)
        b = self.fit()
        self.assertGreater(b["top"], a["top"], "띠를 세웠는데 판의 윗변이 안 내려갔다")
        self.assertLessEqual(b["scroll"], b["inner"] + 2, b)
        self.assertLessEqual(b["bottom"], b["inner"] + 2, "띠가 서자 판이 창 밖으로 밀렸다: %r" % b)
        self.ws.eval("(function(){const p=document.getElementById('fit-probe');"
                     " if(p) p.remove(); return true;})()")
        time.sleep(0.6)
        c = self.fit()
        self.assertLessEqual(c["bottom"], c["inner"] + 2, c)

    def skinfit(self, skin):
        """그 스킨으로 열고 판의 자리를 잰다 — 창 바닥까지가 판의 몫이고, 그 아래
           남아야 할 여백은 스킨이 정한다(main 의 아래 여백)."""
        self.ws.eval("location.href = 'http://127.0.0.1:%d/index.html?skin=%s&nosse#terminal'; true"
                     % (self.port, skin))
        time.sleep(0.5)
        wait_ready(self.ws, needs=("whoami", "users"), sels="#cc-root")
        time.sleep(1.0)
        return self.ws.eval(
            "(function(){const r=document.getElementById('cc-root').getBoundingClientRect();"
            "return {skin:document.documentElement.dataset.skin,"
            " bottom:Math.round(r.bottom), inner:window.innerHeight,"
            " scroll:document.documentElement.scrollHeight,"
            " pad:Math.round(parseFloat(getComputedStyle(document.querySelector('main')).paddingBottom))};})()")

    # F3. 머리 높이가 다른 스킨에서도 판의 바닥이 창 안이다 (REQ-20260909-079).
    #     grid 는 풀블리드(머리가 낮고 아래 여백 0), soft 는 왼쪽 메뉴 셸이다 —
    #     168px 같은 상수로는 둘 다 맞힐 수 없다.
    def test_f3_the_pane_fits_in_skins_with_a_different_head(self):
        for skin in ("grid", "soft"):
            m = self.skinfit(skin)
            self.assertEqual(m["skin"], skin, "스킨이 안 입혀졌다: %r" % m)
            self.assertLessEqual(m["bottom"], m["inner"] + 2,
                                 "%s: 판이 창 밖으로 밀렸다: %r" % (skin, m))
            self.assertLessEqual(m["scroll"], m["inner"] + 2,
                                 "%s: 문서가 창보다 길다: %r" % (skin, m))
            # 창 바닥까지 쓰되 스킨이 둔 아래 여백만 남긴다 — 상수로 잘라 낸 자리가 없다
            self.assertGreaterEqual(m["bottom"], m["inner"] - m["pad"] - 2,
                                    "%s: 판이 그만큼 짧다 — 아래가 비었다: %r" % (skin, m))

    # F4. 띠가 섰다가 사라져도 스킨 grid 에서 판은 창을 그대로 채운다.
    #     예전엔 다시 재는 신호가 머리에 닿지 않아, 띠가 사라진 뒤 판이 43px 짧은
    #     채로 남았다 (REQ-20260909-079).
    def test_f4_the_pane_refits_when_the_banner_comes_and_goes(self):
        self.skinfit("grid")
        show = ("(function(){const el=document.getElementById('notices');"
            " el.insertAdjacentHTML('beforeend', '<div class=\"nrow note\" id=\"fit-probe\">'"
            " + '<span class=\"n-mark\"></span><span class=\"n-txt\">시험용 한 줄</span>'"
            " + '<span class=\"n-act\"></span></div>'); return true;})()")
        hide = ("(function(){const p=document.getElementById('fit-probe');"
            " if(p) p.remove(); return true;})()")
        meas = ("(function(){const r=document.getElementById('cc-root').getBoundingClientRect();"
                "return {bottom:Math.round(r.bottom), inner:window.innerHeight,"
                " scroll:document.documentElement.scrollHeight};})()")
        self.ws.eval(show)
        time.sleep(0.9)
        b = self.ws.eval(meas)
        self.assertLessEqual(b["bottom"], b["inner"] + 2, "띠가 서자 판이 창 밖으로 밀렸다: %r" % b)
        self.assertLessEqual(b["scroll"], b["inner"] + 2, b)
        self.ws.eval(hide)
        time.sleep(0.9)
        c = self.ws.eval(meas)
        self.assertLessEqual(c["bottom"], c["inner"] + 2, c)
        self.assertGreaterEqual(c["bottom"], c["inner"] - 2,
                                "띠가 사라졌는데 판이 그 자리를 되찾지 못했다: %r" % c)

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
