"""식별자와 경과시각의 간격을 실제 렌더에서 잰다 (REQ-20260831-021-62x6).

정적 계약(test_id_clearance)은 규칙의 모양만 지킨다 — 좁은 열에서 정말로
겹치지 않는지는 브라우저가 그린 상자만 안다. 사용자가 본 결함이 실측
(cork compact·열 170px·-1.19px)이었으므로, 지키는 것도 실측이어야 한다.

진짜 브라우저(WSL 이면 Windows Chrome)를 배율 1 · 1.25 · 1.5 로 띄우고
(배율 불변 — 비정수 배율의 반올림 함정은 DOC-20260831-004), 스킨 열 개 ×
밀도 두 벌을 한 페이지에서 갈아 끼우며 카드 넷을 잰다:

  worst   점 없음 · 21자 전체형 식별자 · 최장 경과(999d 23h) — 신고된 결함의
          최악 조합. 점 없는 카드는 식별자가 flex 줄의 첫 항목이라 줄바꿈이
          안 되던 바로 그 카드다.
  plain   점 없음 · 16자 표준형
  dotted  점 있음 · 21자 — 점이 식별자를 둘째 항목으로 만들어 주던 경우
  tiny    짧은 식별자 — 한 줄에 드는 카드가 공연히 내려가지 않는지

계약: 어떤 조합에서도 식별자 상자와 경과시각 상자가 **동시에** 가로·세로로
겹치지 않는다(간격 ≥ 0). 식별자는 잘리는 대신 통째로 아랫줄에 선다.

검증 환경이 없으면 조용히 지나가지 않고 skip 사유를 남긴다.
캡처는 scratchpad/req021/ 에 남는다 — 수치는 눈의 보조다(browser-verify).

실행: python3 tests/ id_realscale
"""
import base64
import json
import os
import shutil
import subprocess
import time
import unittest
import urllib.request

from cdpreal import WS, chrome_path, reclaim
from webasset import parts

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")
OUT = os.path.join(REPO, "scratchpad", "req021")

SKINS = ("ledger", "slate", "cork", "grid", "soft", "calm",
         "glass", "cobalt", "field", "terminal")
DENSITIES = ("normal", "compact")
SCALES = (1.0, 1.25, 1.5)

CARDS = (
    ("worst", False, "REQ-20260831-021-62x6", "999d 23h"),
    ("plain", False, "REQ-20260831-021", "999d 23h"),
    ("dotted", True, "REQ-20260831-021-62x6", "48m 25s"),
    ("tiny", False, "REQ-1", "12s"),
)


def fixture_html():
    """실제 화면과 같은 캐스케이드 — index.html 이 부르는 CSS 를 같은 순서로.
    열 폭 170px 는 신고된 결함의 그 폭이다."""
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    cards = []
    for tag, dot, idn, ela in CARDS:
        dot_html = '<span class="livedot on"></span>' if dot else ""
        cards.append(
            '<div class="card" data-status="in-progress" id="c-%s"'
            ' style="--sc:var(--muted)">'
            '<div class="id">%s<span class="idn">%s</span></div>'
            '<div class="t">제목 줄은 아래에서 시작한다</div>'
            '<div class="m"><span class="badge">nice</span></div>'
            '<span class="elapsed">%s</span></div>'
            % (tag, dot_html, idn, ela))
    return ('<!doctype html><html lang="ko" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:16px;background:var(--bg)}</style></head>'
            '<body><div class="cards" style="width:170px">%s</div>'
            "</body></html>" % (css, "".join(cards)))


MEASURE_JS = """
(() => {
  const out = [];
  for (const tag of %s) {
    const card = document.querySelector('#c-' + tag);
    const idn = card.querySelector('.idn').getBoundingClientRect();
    const ela = card.querySelector('.elapsed').getBoundingClientRect();
    out.push({tag,
      idn: {l: idn.left, r: idn.right, t: idn.top, b: idn.bottom},
      ela: {l: ela.left, r: ela.right, t: ela.top, b: ela.bottom}});
  }
  return out;
})()
"""


def _overlap(a, b):
    h = min(a["r"], b["r"]) - max(a["l"], b["l"])
    v = min(a["b"], b["b"]) - max(a["t"], b["t"])
    return h, v


def measure_scale(chrome, scale):
    """브라우저 한 벌을 배율 scale 로 띄워 전 조합을 재고 회수한다."""
    marker = "s9req021-%d-%g" % (os.getpid(), scale)
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
         "--remote-debugging-port=0",
         "--force-device-scale-factor=%g" % scale,
         "--window-size=280,720", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws, rows = None, []
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
        os.makedirs(OUT, exist_ok=True)
        for skin in SKINS:
            for den in DENSITIES:
                ws.eval("document.documentElement.dataset.skin=%r;"
                        "document.documentElement.dataset.density=%r"
                        % (skin, den))
                time.sleep(0.12)
                data = ws.eval(MEASURE_JS % json.dumps(
                    [c[0] for c in CARDS]))
                for d in data:
                    h, v = _overlap(d["idn"], d["ela"])
                    rows.append({"scale": scale, "skin": skin, "den": den,
                                 "tag": d["tag"], "h": h, "v": v,
                                 "gap": d["ela"]["l"] - d["idn"]["r"],
                                 "idn": d["idn"], "ela": d["ela"]})
                if scale == 1.25:
                    r = ws.call("Page.captureScreenshot", format="png",
                                fromSurface=True)
                    with open(os.path.join(
                            OUT, "%s-%s-x125.png" % (skin, den)), "wb") as f:
                        f.write(base64.b64decode(r["data"]))
        return rows
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


class TheIdAndTheClockNeverShareInk(unittest.TestCase):
    rows = None

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path()
        if not chrome:
            raise unittest.SkipTest("브라우저 없음 — 실측 불가 환경")
        try:
            cls.rows = []
            for sc in SCALES:
                cls.rows += measure_scale(chrome, sc)
        except (ConnectionError, RuntimeError, OSError) as e:
            raise unittest.SkipTest("CDP 실측 불가: %s" % e)

    def test_the_id_and_the_clock_never_share_ink(self):
        """TheIdAndTheClockNeverShareInk 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("no_pair_overlaps_anywhere"):
            self.maxDiff = None
            bad = [r for r in self.rows if r["h"] > 0.01 and r["v"] > 0.01]
            self.assertEqual(
                [], [("%(scale)g %(skin)s/%(den)s %(tag)s h=%(h).2f v=%(v).2f"
                      % r) for r in bad],
                "식별자가 경과시각을 덮었다 — 캡처는 scratchpad/req021/")
        with self.subTest("the_short_id_stays_on_the_first_line"):
            for r in self.rows:
                if r["tag"] != "tiny" or r["skin"] in ("soft", "calm"):
                    continue
                self.assertLess(
                    abs(r["idn"]["t"] - r["ela"]["t"]), 3.0,
                    "%(skin)s/%(den)s@%(scale)g 에서 짧은 식별자가 첫 줄을 "
                    "떠났다: idn.t=%(it).1f ela.t=%(et).1f" % dict(
                        r, it=r["idn"]["t"], et=r["ela"]["t"]))
        with self.subTest("the_long_id_goes_whole_not_cut"):
            by = {}
            for r in self.rows:
                by[(r["scale"], r["skin"], r["den"], r["tag"])] = r
            for (sc, sk, dn, tag), r in by.items():
                if tag != "worst":
                    continue
                plain = by.get((sc, sk, dn, "plain"))
                self.assertIsNotNone(plain)
                w_worst = r["idn"]["r"] - r["idn"]["l"]
                w_plain = plain["idn"]["r"] - plain["idn"]["l"]
                self.assertGreater(
                    w_worst, w_plain + 10,
                    "%s/%s@%g 에서 21자 식별자(%.1f)가 16자(%.1f)만큼도 "
                    "안 넓다 — 잘렸다" % (sk, dn, sc, w_worst, w_plain))

if __name__ == "__main__":
    unittest.main()
