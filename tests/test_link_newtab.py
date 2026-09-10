"""주소가 있는 손잡이는 가운데 버튼·수정키로 새 탭에 열린다 (REQ-20260909-094).

주인: 「대시보드의 모든 http 링크 문구들은 마우스 가운데 버튼으로 새 탭 열기가
되길 바란다.」 손잡이는 두 갈래다 — 앵커(문서 링크·Jira 키·가이드)는 href 가
있어 브라우저가 스스로 열고, div 로 선 손잡이(카드·목록 행·세션 줄·설정 항목)는
브라우저가 주소를 모른다. 그 둘을 한 규칙(events.js navHashFor)이 가른다.

이 시험은 소스 글자를 대조하지 않는다. 실브라우저를 띄우고 실제로 눌러 무엇이
열렸는지 화면에서 잰다. 새 탭이 진짜로 뜨면 시험이 끝난 뒤에도 창이 남으므로,
화면 스스로가 여는 자리(window.open)만 기록하도록 바꿔 두고 잰다 — 앵커는 그
기록이 **비어 있어야** 옳다(브라우저가 열었고 우리가 두 번 열지 않았다는 뜻).

누르는 방법이 갈래마다 다른 이유(2026-09-09 실측): CDP 의 `Input.dispatchMouseEvent`
는 왼쪽 버튼의 누름·놓음에서 `click` 을 지어 주지만, 가운데 버튼에서는 `auxclick`
을 짓지 않는다(pointerdown·mousedown·pointerup·mouseup 넷만 온다). 그래서 수정키
클릭과 맨 클릭은 **진짜 입력**으로 누르고, 가운데 버튼은 그 자리에 `auxclick` 을
직접 보낸다 — 재는 것은 화면의 규칙(navHashFor)이고, 가운데 버튼이 auxclick 을
낸다는 것은 브라우저의 계약이다.

  S2 카드(div)를 가운데 버튼으로 누르면 그 문서 주소가 새 탭으로 열리고
     이 탭의 화면은 그대로다.
  S3 문서 링크(a.doclink)는 우리가 열지 않는다 — href 가 그 주소를 들고 있다.
  S4 Jira 키는 target=_blank 앵커다(브라우저 몫).
  S5 Ctrl + 왼쪽 클릭도 같은 주소를 새 탭으로 연다.
  S6 손잡이 안의 다른 손잡이(「이어 말하기」)는 새 탭을 열지 않는다 — 행동이다.
  S7 맨 왼쪽 클릭은 지금처럼 이 탭 안에서 연다(회귀).

실행: python3 tests/ link_newtab
"""
import json
import os
import re
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
APP = os.path.join(ROOT, "web", "app")

# 화면이 스스로 여는 자리만 기록한다 — 진짜 새 창을 띄우면 캡처 뒤에도 남는다.
RECORD = """(() => {
  window.__nt = [];
  if (!window.__ntPatched){
    window.__ntPatched = 1;
    window.open = (u) => { window.__nt.push(String(u)); return null; };
  }
  window.__nt.length = 0;
  return true;
})()"""

# 누를 자리 — 요소의 왼쪽 위 안쪽을 화면 좌표로 돌려준다. 한가운데를 잡으면
# 카드에서는 그 자리에 안쪽 손잡이(벨트)가 앉아 있어 엉뚱한 것을 누른다.
SPOT = """(() => {
  const el = document.querySelector(%s);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return null;
  const host = el.closest("[data-doc]");
  return {x: r.left + Math.min(20, r.width / 2),
          y: r.top + Math.min(8, r.height / 2),
          id: host ? host.dataset.doc : "", tag: el.tagName};
})()"""

# 가운데 버튼 — 그 자리에 auxclick 을 보낸다(머리말의 실측 참조).
AUX = """(() => {
  const el = document.querySelector(%s), r = el.getBoundingClientRect();
  el.dispatchEvent(new MouseEvent("auxclick", {button: 1, buttons: 4,
    bubbles: true, cancelable: true,
    clientX: r.left + 2, clientY: r.top + 2}));
  return {opened: window.__nt.slice(), hash: location.hash};
})()"""

READ = '(() => ({opened: window.__nt.slice(), hash: location.hash}))()'


class LinksOpenInANewTab(unittest.TestCase):

    out = None
    srv = None
    proc = None
    ws = None
    prof_wsl = None
    marker = None
    win = False

    # ---- 준비 -------------------------------------------------------------
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(APP, "events.js"), encoding="utf-8") as f:
            cls.ev = f.read()
        with open(os.path.join(APP, "card.js"), encoding="utf-8") as f:
            cls.card = f.read()
        chrome = chrome_path(pixel_contract=False)
        if chrome is None:
            raise unittest.SkipTest("실브라우저 미검증 — Chrome/Edge 를 찾지 못했다")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**os.environ, "S9_ROOT": ROOT, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.marker = "s9ntab-%d" % os.getpid()
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
                       sels="#view .card[data-doc]")
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

    @classmethod
    def tearDownClass(cls):
        if cls.ws:
            cls.ws.close()
            cls.ws = None
        for p in (cls.proc, cls.srv):
            if p:
                try:
                    p.terminate()
                    p.wait(timeout=10)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
        cls.proc = cls.srv = None
        if cls.marker:
            reclaim(cls.marker, cls.win)

    # ---- 재기 -------------------------------------------------------------
    @classmethod
    def spot(cls, sel):
        s = cls.ws.eval(SPOT % json.dumps(sel))
        if not s:
            raise RuntimeError("누를 자리를 찾지 못했다: %s" % sel)
        return s

    @classmethod
    def press(cls, s, button="middle", modifiers=0):
        """사람이 누르는 그대로 — 왼쪽 버튼은 누름·놓음 한 짝이 click 을 낳는다."""
        buttons = 4 if button == "middle" else 1
        for kind, held in (("mousePressed", buttons), ("mouseReleased", 0)):
            cls.ws.call("Input.dispatchMouseEvent", type=kind,
                        x=s["x"], y=s["y"], button=button, buttons=held,
                        clickCount=1, modifiers=modifiers)
        time.sleep(0.12)
        return cls.ws.eval(READ)

    @classmethod
    def aux(cls, sel):
        cls.ws.eval(RECORD)
        return cls.ws.eval(AUX % json.dumps(sel))

    @classmethod
    def measure(cls):
        o = cls.out
        cls.ws.eval(RECORD)
        card = cls.spot("#view .card[data-doc] .t")   # 제목 자리 — 안쪽 손잡이가 없다
        o["cardId"] = card["id"] or None

        # S2 — Board 카드는 앵커가 아니다. 가운데 버튼으로 그 문서를 새 탭에.
        o["cardMid"] = cls.aux("#view .card[data-doc] .t")

        # S6 — 카드 안의 「이어 말하기」는 행동이지 주소가 아니다.
        o["pickMid"] = cls.aux("#view .card .pickdoc")

        # S3 — 문서 링크는 화면의 링크 헬퍼(dlink)가 짓는 그 HTML 그대로 세운다.
        #      어느 문서에 관계가 걸려 있느냐에 기대지 않으려고 직접 세운다.
        cls.ws.eval(RECORD)
        cls.ws.eval(
            '(() => { const id = catalog[0].id;'
            ' document.getElementById("ntprobe")?.remove();'
            ' const box = document.createElement("div");'
            ' box.id = "ntprobe";'
            ' box.style.cssText = "position:fixed;left:8px;top:8px;z-index:99999;'
            'background:#fff;padding:6px";'
            ' box.innerHTML = dlink(id, "probe");'
            ' document.body.appendChild(box); return true; })()')
        o["probeTag"] = cls.spot("#ntprobe a.doclink")["tag"]
        o["probeMid"] = cls.aux("#ntprobe a.doclink")
        o["probeAttrs"] = cls.ws.eval(
            '(() => { const a = document.querySelector("#ntprobe a.doclink");'
            ' return {href: a.getAttribute("href"), doc: a.dataset.doc,'
            ' want: docHash(a.dataset.doc)}; })()')
        cls.ws.eval('(document.getElementById("ntprobe").remove(), 1)')

        # S5 — Ctrl + 왼쪽 클릭은 **진짜 입력**으로 누른다 (CDP 수정키: Ctrl = 2).
        cls.ws.eval(RECORD)
        o["cardCtrl"] = cls.press(card, button="left", modifiers=2)

        # S7 — 맨 왼쪽 클릭은 지금처럼 이 탭 안에서 연다(회귀). 화면이 바뀌므로 끝에.
        cls.ws.eval(RECORD)
        o["cardPlain"] = cls.press(card, button="left")

    # ---- 판정 -------------------------------------------------------------
    def test_s2_middle_button_on_a_card_opens_that_document_in_a_new_tab(self):
        got = self.out["cardMid"]
        self.assertEqual(len(got["opened"]), 1,
                         "카드를 가운데 버튼으로 눌렀는데 새 탭이 하나가 아니다")
        self.assertTrue(got["opened"][0].endswith("#docs/" + self.out["cardId"])
                        or got["opened"][0].endswith(
                            "#projects/" + self.out["cardId"]),
                        "새 탭 주소가 그 문서를 열지 않는다: %r" % got["opened"])
        self.assertEqual(got["hash"], "#board",
                         "새 탭으로 여는 중에 이 탭의 화면까지 바뀌었다")

    def test_s3_a_document_link_is_left_to_the_browser(self):
        self.assertEqual(self.out["probeTag"], "A")
        self.assertEqual(self.out["probeMid"]["opened"], [],
                         "앵커까지 우리가 열면 탭이 둘 열린다")
        a = self.out["probeAttrs"]
        self.assertEqual(a["href"], a["want"],
                         "링크의 주소가 화면이 여는 자리와 다르다")
        self.assertEqual(a["href"].split("/")[-1], a["doc"])

    def test_s4_the_jira_key_is_an_anchor_the_browser_can_open(self):
        m = re.search(r'<a class="jkey" href=.{0,60}?target="_blank"\s+'
                      r'rel="noopener"', self.card, re.S)
        self.assertIsNotNone(
            m, "Jira 키가 앵커가 아니면 가운데 버튼이 아무 일도 하지 않는다")

    def test_s5_modifier_click_opens_the_same_address(self):
        got = self.out["cardCtrl"]
        self.assertEqual(len(got["opened"]), 1,
                         "Ctrl + 클릭이 새 탭을 열지 않았다")
        self.assertTrue(got["opened"][0].endswith(self.out["cardId"]),
                        "Ctrl + 클릭이 다른 주소를 열었다: %r" % got["opened"])
        self.assertEqual(got["hash"], "#board",
                         "Ctrl + 클릭이 이 탭의 화면까지 바꿨다")

    def test_s6_a_handle_inside_a_handle_stays_an_action(self):
        self.assertEqual(self.out["pickMid"]["opened"], [],
                         "「이어 말하기」는 주소가 아니라 행동이다")

    def test_s7_a_plain_click_still_opens_in_this_tab(self):
        got = self.out["cardPlain"]
        self.assertEqual(got["opened"], [], "맨 클릭이 새 탭을 열었다")
        self.assertEqual(got["hash"], "#docs/" + self.out["cardId"],
                         "맨 클릭이 이 탭에서 그 문서를 열지 않았다")

    def test_s8_the_rule_lives_in_one_place(self):
        """주소를 짓는 규칙이 손마다 흩어지면 언젠가 한 손만 고쳐진다."""
        self.assertEqual(self.ev.count("function navHashFor"), 1)
        self.assertIn("hashOpenNew", self.ev)
        self.assertIn('el.closest("a[href],button")', self.ev,
                      "앵커와 안쪽 버튼을 가르는 자리가 없다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
