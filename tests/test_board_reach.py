"""좁은 폭에서도 판의 열 전부에 닿는다 (REQ-20260916-010-2n7g).

주인이 실제 맥 Safari 26.4 에서 본 것(400x900, 2026-09-16 02:5x): Board 의 열
일곱 중 셋의 오른끝이 590·782·974 로 화면(400) 밖인데 **밀 수가 없었다.**
문서의 scrollWidth 는 400 이라 페이지는 가로로 안 움직이고, 열은 판 밖에 있다.
화면 밖의 열은 어떤 조작으로도 닿지 않는다.

여기서 재는 것은 규칙의 글자가 아니라 **닿을 수 있는가**다. 불변식 하나로 적는다:

    판이 가로로 밀리지 않는다면(scrollLeft 를 끝까지 밀어도 0),
    모든 열의 오른끝은 판의 안쪽 오른변 안에 있어야 한다.

밀 수 있으면 화면 밖이어도 닿고, 밀 수 없으면 화면 안에 있어야 닿는다 — 둘 중
어느 길로 풀든 이 식이 참이면 사용자는 모든 열을 볼 수 있다. 400px 에서는
열이 세로로 쌓이는 쪽을 골랐다(구현 근거는 board.css 의 그 자리 주석).

실행: python3 tests/ board_reach
"""
import json
import os
import shutil
import subprocess
import time
import unittest
import urllib.request

from cdpreal import WS, chrome_path, reclaim, skip_reason
from webasset import parts

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")

# 화면이 실제로 세우는 일곱 (web/app/const.js 의 STATUSES)
STATUSES = (("draft", "DRAFT"), ("open", "OPEN"), ("in-progress", "IN-PROGRESS"),
            ("blocked", "BLOCKED"), ("review", "REVIEW"), ("done", "DONE"),
            ("cancelled", "CANCELLED"))

# 재는 폭 — 손전화(400) · 쌓임 경계의 양쪽(560/561) · 데스크탑(1280)
VIEWPORTS = {"phone": (400, 900), "edge_on": (560, 900),
             "edge_off": (561, 900), "desktop": (1280, 800)}
STACKED = ("phone", "edge_on")

# 스킨마다 열에 제 폭·제 테두리를 적어 두었다(`[data-skin="slate"] .col` 은
# 네 변을 두르는 상자다). 쌓임은 그 전부에서 서야 하므로 400px 을 스킨 열 벌로 잰다.
SKINS = ("ledger", "slate", "cork", "grid", "soft", "calm",
         "glass", "cobalt", "field", "terminal")


def fixture_html():
    """실제 화면과 같은 캐스케이드 · 같은 상자 사슬 (test_board_sticky 와 같은 자)."""
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    cols = []
    for st, label in STATUSES:
        cards = "".join(
            '<div class="card" data-status="%s" style="--sc:var(--muted)">'
            '<div class="id"><span class="idn">REQ-20260916-%03d</span></div>'
            '<div class="t">좁은 폭에서도 읽히는지 보는 카드 %d</div></div>'
            % (st, i, i) for i in range(1, 6))
        cols.append(
            '<div class="col" style="--sc:var(--c-%s)" data-colstatus="%s">'
            '<h2><span class="cdot"></span>%s<span class="n">5</span></h2>'
            '<div class="cards">%s</div></div>'
            % (st.replace("-", ""), st, label, cards))
    return ('<!doctype html><html lang="ko" class="boardfit" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:0;background:var(--bg)}'
            '.top{height:120px;background:var(--panel);flex:none}</style></head>'
            '<body><div class="top">머리 자리(헤더·필터 줄)</div>'
            '<main><div id="view"><div class="board"><div class="cols">%s</div>'
            '</div></div></main></body></html>' % (css, "".join(cols)))


# 판을 양쪽 끝까지 밀어 보고 잰다 — 「밀리는가」는 규칙이 아니라 실측이다.
MEASURE_JS = """
(() => {
  const board = document.querySelector('.board');
  const cols = board.querySelector('.cols');
  board.scrollLeft = 99999;
  const maxScrollLeft = Math.round(board.scrollLeft);
  board.scrollLeft = 0;
  board.scrollTop = 99999;
  const maxScrollTop = Math.round(board.scrollTop);
  board.scrollTop = 0;
  const br = board.getBoundingClientRect();
  const cs = getComputedStyle(board);
  const innerLeft = br.left + board.clientLeft;
  const innerRight = innerLeft + board.clientWidth;
  return {
    innerWidth: window.innerWidth,
    overflowX: cs.overflowX,
    maxScrollLeft: maxScrollLeft,
    maxScrollTop: maxScrollTop,
    innerLeft: +innerLeft.toFixed(1), innerRight: +innerRight.toFixed(1),
    direction: getComputedStyle(cols).flexDirection,
    heads: [...board.querySelectorAll('.col h2')].map(
      h => getComputedStyle(h).position),
    cols: [...board.querySelectorAll('.col')].map(c => {
      const r = c.getBoundingClientRect();
      return {label: c.querySelector('h2').textContent.replace(/\\s+/g, ' ').trim(),
              left: +r.left.toFixed(1), right: +r.right.toFixed(1),
              top: +r.top.toFixed(1), width: +r.width.toFixed(1)};
    })};
})()
"""

_MEASURED = {}


def shared():
    if "err" in _MEASURED:
        raise unittest.SkipTest(_MEASURED["err"])
    if "data" in _MEASURED:
        return _MEASURED["data"]
    # 자리와 스크롤을 재는 시험이라 화소 계약 밖(맥)에서도 잰다 (REQ-20260910-003).
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
    marker = "s9req916010-%d" % os.getpid()
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
    ws, out = None, {}
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
        time.sleep(0.3)
        for name, (w, h) in VIEWPORTS.items():
            ws.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
                    deviceScaleFactor=1, mobile=False)
            time.sleep(0.3)
            out[name] = ws.eval(MEASURE_JS)
        # 400px 을 스킨 열 벌로 한 번 더 — 폭·테두리를 스킨이 다시 적는다.
        ws.call("Emulation.setDeviceMetricsOverride", width=400, height=900,
                deviceScaleFactor=1, mobile=False)
        skins = {}
        for skin in SKINS:
            ws.eval("document.documentElement.dataset.skin=%r" % skin)
            time.sleep(0.15)
            skins[skin] = ws.eval(MEASURE_JS)
        ws.eval("document.documentElement.dataset.skin='ledger'")
        ws.call("Emulation.clearDeviceMetricsOverride")
        out["skins"] = skins
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


class EveryColumnCanBeReached(unittest.TestCase):
    """어느 폭에서든 열 일곱에 닿을 길이 있다."""

    data = None

    @classmethod
    def setUpClass(cls):
        cls.data = shared()

    def reach(self, name, d):
        """닿을 길이 있는가 — 밀 수 있거나, 판 안에 있거나."""
        if d["maxScrollLeft"] > 0:
            return                # 밀 수 있으면 화면 밖이어도 닿는다
        out = [c for c in d["cols"] if c["right"] > d["innerRight"] + 0.5]
        self.assertEqual(
            [], [c["label"] for c in out],
            "%s(%dpx): 판이 가로로 밀리지 않는데 열 %d 개가 판 밖에 있다 — "
            "오른끝 %s · 판의 안쪽 오른변 %.1f. 닿을 길이 없다."
            % (name, d["innerWidth"], len(out),
               ", ".join("%.1f" % c["right"] for c in out), d["innerRight"]))

    def test_no_column_sits_where_nothing_can_reach_it(self):
        """판이 안 밀리면 열은 판 안에 있어야 한다 — 주인이 본 그 자리."""
        for name in VIEWPORTS:
            self.reach(name, self.data[name])

    def test_every_skin_stacks_at_the_phone_width(self):
        """스킨 열 벌 전부에서 400px 의 열이 쌓이고 판 안에 선다.

        스킨마다 열에 제 폭을 적어 두었고(`[data-skin="grid"] .col{min-width}`),
        slate·cobalt·field 는 네 변을 두르는 상자다 — 한 벌만 보고 넘기면
        나머지 아홉에서 같은 자리가 다시 열린다."""
        for skin, d in self.data["skins"].items():
            self.assertEqual(
                "column", d["direction"],
                "%s 스킨의 400px 에서 열 상자가 %s 다" % (skin, d["direction"]))
            self.assertEqual(0, d["maxScrollLeft"],
                             "%s 스킨의 400px 에서 판이 아직 가로로 밀린다" % skin)
            self.reach(skin + "(400px)", d)

    def test_the_narrow_board_stacks_its_columns(self):
        """손전화 폭에서는 열이 세로로 쌓인다 — 옆으로 미는 대신 내려 읽는다."""
        for name in STACKED:
            d = self.data[name]
            self.assertEqual(
                "column", d["direction"],
                "%s(%dpx) 에서 열 상자가 %s 다 — 쌓이지 않았다"
                % (name, d["innerWidth"], d["direction"]))
            tops = [c["top"] for c in d["cols"]]
            self.assertEqual(len(tops), len(set(tops)),
                             "%s 에서 열들이 같은 높이에 있다 — 쌓이지 않았다" % name)
            self.assertEqual(
                0, d["maxScrollLeft"],
                "%s 에서 쌓아 놓고도 가로로 밀린다 — 쌓임의 뜻이 없다" % name)
            self.assertGreater(
                d["maxScrollTop"], 0,
                "%s 에서 쌓인 열을 세로로 내려 볼 수 없다" % name)

    def test_the_wide_board_keeps_the_columns_side_by_side(self):
        """넓은 폭의 판은 그대로다 — 쌓임이 데스크탑까지 올라오지 않는다."""
        for name in ("edge_off", "desktop"):
            d = self.data[name]
            self.assertEqual(
                "row", d["direction"],
                "%s(%dpx) 에서 열 상자가 %s 다 — 데스크탑 배치가 바뀌었다"
                % (name, d["innerWidth"], d["direction"]))
            tops = set(c["top"] for c in d["cols"])
            self.assertEqual(1, len(tops),
                             "%s 에서 열들의 윗변이 갈렸다: %s" % (name, sorted(tops)))

    def test_the_column_head_still_sticks_when_stacked(self):
        """쌓인 뒤에도 상태 머리는 붙는다 (test_board_sticky 의 계약)."""
        for name in STACKED:
            for pos in self.data[name]["heads"]:
                self.assertEqual("sticky", pos,
                                 "%s 에서 열 머리가 붙지 않는다" % name)


if __name__ == "__main__":
    unittest.main()
