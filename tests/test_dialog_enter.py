"""safe 확인 창의 맨 Enter 는 실행 쪽에 닿지 않는다 — 실제 Chrome 으로 잰다 (REQ-20260913-003-2n7g).

실사고 2026-09-13 (맥 Safari 26.4 · Chrome 152 실측, REQ-20260913-019-62x6): 초대 창은
`safe` 를 들고 있었지만 연 뒤 초점을 이메일 칸으로 옮겼고, 그 칸에서 Enter 를 치자
초대 메일이 나갔다. `safe` 가 처음 초점만 물러나는 버튼에 두고 키는 지키지 않았기
때문이다 — 바닥 힌트는 「Enter 로 닫기」였다.

계약 셋:
  E1 safe 창 본문의 칸에서 Enter → 실행(yes)이 아니라 물러나는 쪽(cancel)으로 닫힌다.
  E2 safe 창에서 초점이 실행 버튼 위면 Enter 는 그 버튼이 받는다(브라우저 기본).
  E3 safe 가 아닌 확인 창은 종전대로 Enter 한 번에 실행이다.

키와 초점만 재므로 화소 계약 밖의 브라우저(맥)로도 잰다 (cdpreal, REQ-20260910-003).
실행: python3 tests/ dialog_enter
"""
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cdpreal import WS, chrome_path, reclaim, skip_reason  # noqa: E402

WEB = os.path.normpath(os.path.join(HERE, "..", "web"))


def fixture_html():
    """dialog.js 를 그대로 싣는다 — 창의 키 규칙은 이 파일 하나가 정한다.
    esc 는 state.js 의 것과 같은 한 줄(판 전체를 싣지 않으려고)."""
    js = open(os.path.join(WEB, "app", "dialog.js"), encoding="utf-8").read()
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"></head><body>'
            # 판이 주는 전역 둘 — esc(state.js)와 현재 탭 이름(dlgScreen 이 창을 매는 화면)
            '<script>const esc = s => String(s ?? "").replace(/[&<>"]/g,'
            ' c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"})[c]);'
            ' let tab = "board";</script>'
            '<script>%s</script></body></html>' % js)


OPEN = ("window.__r = 'pending';"
        "s9dlg({kind:'confirm', safe:%s, cap:'t', title:'t',"
        " descHtml:'<input id=\"em\" type=\"email\">', ok:'보내기', cancel:'닫기'})"
        ".then(v => { window.__r = String(v); }, e => { window.__r = 'error: ' + e; });"
        "document.getElementById('em').focus(); document.activeElement.id")


def enter(ws):
    """사람의 Enter 와 같게 — text 를 실어야 keypress 가 생겨 버튼의 기본 동작이 난다."""
    ws.call("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter",
            windowsVirtualKeyCode=13, text="\r", unmodifiedText="\r")
    ws.call("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter",
            windowsVirtualKeyCode=13)


def settled(ws):
    for _ in range(40):
        v = ws.eval("window.__r")
        if v != "pending":
            return v
        time.sleep(0.1)
    return "pending"


_MEASURED = {}


def measured():
    if "err" in _MEASURED:
        raise unittest.SkipTest(_MEASURED["err"])
    if "data" in _MEASURED:
        return _MEASURED["data"]
    chrome = chrome_path(pixel_contract=False)
    if not chrome:
        _MEASURED["err"] = skip_reason(pixel_contract=False)
        raise unittest.SkipTest(_MEASURED["err"])
    try:
        _MEASURED["data"] = measure(chrome)
    except (ConnectionError, RuntimeError, OSError, StopIteration) as e:
        _MEASURED["err"] = "CDP 실측 불가: %s" % e
        raise unittest.SkipTest(_MEASURED["err"])
    return _MEASURED["data"]


def measure(chrome):
    marker = "s9req003-%d" % os.getpid()
    win = chrome.startswith("/mnt/c/")
    if win:
        os.makedirs("/mnt/c/Temp", exist_ok=True)
        prof_wsl, prof_arg = "/mnt/c/Temp/" + marker, "C:\\Temp\\" + marker
        fix = os.path.join("/mnt/c/Temp", marker + ".html")
        url = "file:///C:/Temp/%s.html" % marker
    else:
        base = os.environ.get("TMPDIR", "/tmp")
        prof_wsl = prof_arg = os.path.join(base, marker)
        fix = os.path.join(base, marker + ".html")
        url = "file://" + fix
    shutil.rmtree(prof_wsl, ignore_errors=True)
    with open(fix, "w", encoding="utf-8") as f:
        f.write(fixture_html())
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu",
         "--user-data-dir=" + prof_arg, "--no-first-run",
         "--no-default-browser-check", "--disable-extensions",
         "--remote-debugging-port=0", "--window-size=1280,800", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        port, dev = None, os.path.join(prof_wsl, "DevToolsActivePort")
        for _ in range(120):
            if os.path.exists(dev):
                try:
                    port = int(open(dev).read().splitlines()[0])
                    break
                except (ValueError, IndexError, OSError):
                    pass
            time.sleep(0.25)
        if port is None:
            raise ConnectionError("DevToolsActivePort 미출현")
        pages = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/json/list" % port, timeout=10).read())
        page = next(p for p in pages if p.get("type") == "page")
        ws = WS(page["webSocketDebuggerUrl"])
        for _ in range(80):
            if ws.eval("document.readyState") == "complete":
                break
            time.sleep(0.25)
        if ws.eval("typeof s9dlg") != "function":
            raise RuntimeError("dialog.js 가 서지 않았다")
        out = {}
        out["focus1"] = ws.eval(OPEN % "true")
        enter(ws)
        out["safe_input"] = settled(ws)
        ws.eval(OPEN % "true")
        out["focus2"] = ws.eval(
            "document.querySelector('.dlgyes').focus(); document.activeElement.className")
        enter(ws)
        out["safe_yes"] = settled(ws)
        ws.eval(OPEN % "false")
        enter(ws)
        out["plain_input"] = settled(ws)
        return out
    finally:
        if ws is not None:
            ws.close()
        try:
            proc.terminate()
        except OSError:
            pass
        reclaim(marker, win)
        shutil.rmtree(prof_wsl, ignore_errors=True)
        try:
            os.remove(fix)
        except OSError:
            pass


class SafeDialogEnter(unittest.TestCase):
    """safe 창의 맨 Enter 는 물러나는 쪽이다 — 초점이 칸에 있어도."""

    def test_e1_enter_in_a_box_of_a_safe_dialog_retreats(self):
        """E1. safe 창 본문의 칸에서 Enter → 실행이 아니라 물러나는 쪽으로 닫힌다."""
        d = measured()
        self.assertEqual(d["focus1"], "em")
        self.assertEqual(d["safe_input"], "false", d)

    def test_e2_enter_on_the_run_button_still_runs(self):
        """E2. 초점이 실행 버튼 위면 Enter 는 그 버튼이 받는다."""
        d = measured()
        self.assertEqual(d["focus2"], "dlgyes")
        self.assertEqual(d["safe_yes"], "true", d)

    def test_e3_a_plain_confirm_runs_on_enter(self):
        """E3. safe 가 아닌 확인 창은 Enter 한 번에 실행이다 (회귀)."""
        self.assertEqual(measured()["plain_input"], "true", measured())


if __name__ == "__main__":
    unittest.main()
