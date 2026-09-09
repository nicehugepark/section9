"""식별자 줄의 「지금」 덩이를 실제 렌더에서 잰다 (REQ-20260831-021 · 084 개정).

정적 계약(test_id_clearance)은 규칙의 모양만 지킨다 — 좁은 열에서 정말로
갈라지지 않는지는 브라우저가 그린 상자만 안다. 사용자가 본 결함이 둘 다
실측이었으므로(cork compact·열 170px·-1.19px / 좁은 카드에서 벨트만 남고
시각이 아랫줄, 주인 캡처 2026-09-09 15:54) 지키는 것도 실측이어야 한다.

**계약이 바뀐 자리** — 종전에는 「경과시각은 늘 식별자와 같은 첫 줄에 있다」를
쟀다. 시각이 카드 모서리에 절대 위치로 떠 있었으니 그럴 수밖에 없었고, 그
떠 있음이 바로 084 가 고친 결함이다. 이제 벨트·시각·「이어 말하기」는 id 줄
안의 한 묶음(`.idr`)으로 흐름에 서므로, **못 서면 묶음째 다음 줄로 내려간다.**
그래서 재는 것도 셋으로 갈린다:

  · 묶음은 갈라지지 않는다 — 벨트와 시각은 어느 폭에서도 같은 줄에 있다.
  · 흔한 폭(320px, 실제 Board 열은 최소 210px·보통 216~288px)에서는 묶음이
    식별자와 같은 첫 줄에 선다.
  · 그보다 좁으면 묶음째 내려가되 식별자의 왼끝은 그대로다 — 카드끼리 id 의
    왼끝이 어긋나지 않는다.

진짜 브라우저(WSL 이면 Windows Chrome)를 배율 1 · 1.25 · 1.5 로 띄우고
(배율 불변 — 비정수 배율의 반올림 함정은 DOC-20260831-004), 스킨 열 개 ×
밀도 두 벌 × 폭 두 벌을 한 페이지에서 갈아 끼우며 카드 넷을 잰다:

  worst   점 없음 · 21자 전체형 식별자 · 최장 경과(999d 23h) — 신고된 결함의
          최악 조합. 점 없는 카드는 식별자가 flex 줄의 첫 항목이라 줄바꿈이
          안 되던 바로 그 카드다.
  plain   점 없음 · 16자 표준형 (같은 이름의 문서가 없으면 화면이 쓰는 형태)
  dotted  점 있음 · 21자 — 점이 식별자를 둘째 항목으로 만들어 주던 경우
  tiny    짧은 식별자 — 한 줄에 드는 카드가 공연히 내려가지 않는지

폭 두 벌: 170px 은 신고된 결함의 그 폭(cork compact @1000px), 320px 은 흔한
Board 열이다.

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
# 170px = 신고된 결함의 그 폭, 320px = 흔한 Board 열(기본 열은 최소 210 · 보통 216~288)
NARROW, COMMON = 170, 320
WIDTHS = (NARROW, COMMON)

# 벨트(⏸)도 카드가 실제로 쓰는 마크업 그대로 — 손잡이가 있는 카드라야 묶음이
# 갈라지는지 잴 수 있다. 글리프는 화면과 같은 viewBox 를 쓴다.
BELT = ('<span class="acts deedbelt"><button type="button" class="deed stop ico"'
        ' data-stop="x" data-kind="session" aria-label="중단하기"'
        ' title="중단하기"><svg class="gly" viewBox="0 0 13 13" aria-hidden="true">'
        '<rect x="3" y="2" width="3" height="9"/>'
        '<rect x="7" y="2" width="3" height="9"/></svg></button></span>')


def fixture_html():
    """실제 화면과 같은 캐스케이드·같은 마크업 — index.html 이 부르는 CSS 를 같은
    순서로, id 줄은 card.js 가 짓는 그 구조로: 식별자 · 묶음(.idr)[벨트 +
    .idnow[경과 시각 · 이어 말하기]]. 마크업이 화면과 어긋나면 이 시험은 화면이
    아니라 제 픽스처를 잰다 — 084 에서 시각을 카드 직계로 두었더니 「시각이 첫
    줄을 떠났다」로 82px 이 나왔는데, 화면에서는 그 자리가 아니었다."""
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    blocks = []
    for w in WIDTHS:
        cards = []
        for tag, dot, idn, ela in CARDS:
            dot_html = '<span class="livedot on"></span>' if dot else ""
            cards.append(
                '<div class="card" data-status="in-progress" id="c-%d-%s"'
                ' style="--sc:var(--muted)">'
                '<div class="id">%s<span class="idn">%s</span>'
                '<span class="idr">%s<span class="idnow">'
                '<span class="elapsed">%s</span>'
                '<button type="button" class="pickdoc">이어 말하기</button>'
                '</span></span></div>'
                '<div class="t">제목 줄은 아래에서 시작한다</div>'
                '<div class="m"><span class="badge">nice</span></div></div>'
                % (w, tag, dot_html, idn, BELT, ela))
        blocks.append('<div class="cards" style="width:%dpx">%s</div>'
                      % (w, "".join(cards)))
    return ('<!doctype html><html lang="ko" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:16px;background:var(--bg)}'
            '.cards{display:inline-block;vertical-align:top;margin-right:12px}'
            '</style></head><body>%s</body></html>' % (css, "".join(blocks)))


MEASURE_JS = """
(() => {
  const box = el => { const r = el.getBoundingClientRect();
    return {l: r.left, r: r.right, t: r.top, b: r.bottom}; };
  const out = [];
  for (const card of document.querySelectorAll('.card')) {
    const [, w, tag] = card.id.split('-');
    out.push({w: +w, tag,
      card: box(card),
      idn: box(card.querySelector('.idn')),
      idr: box(card.querySelector('.idr')),
      belt: box(card.querySelector('.deedbelt')),
      pick: box(card.querySelector('.pickdoc')),
      ela: box(card.querySelector('.elapsed'))});
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
         "--window-size=1100,900", url],
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
                for d in ws.eval(MEASURE_JS):
                    h, v = _overlap(d["idn"], d["ela"])
                    rows.append(dict(d, scale=scale, skin=skin, den=den,
                                     h=h, v=v,
                                     gap=d["ela"]["l"] - d["idn"]["r"]))
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

    def _where(self, r):
        return "%(skin)s/%(den)s@%(scale)g %(tag)s w=%(w)d" % r

    def test_the_id_and_the_clock_never_share_ink(self):
        """식별자 줄의 계약을 한 항목으로 — 갈래마다 재는 것이 다르다."""
        with self.subTest("no_pair_overlaps_anywhere"):
            # 종전 그대로: 식별자와 경과시각은 어느 조합에서도 잉크를 나눠 쓰지 않는다.
            self.maxDiff = None
            bad = [r for r in self.rows if r["h"] > 0.01 and r["v"] > 0.01]
            self.assertEqual(
                [], ["%s h=%.2f v=%.2f" % (self._where(r), r["h"], r["v"])
                     for r in bad],
                "식별자가 경과시각을 덮었다 — 캡처는 scratchpad/req021/")
        with self.subTest("the_group_never_splits"):
            # 084 의 계약: 벨트와 경과시각은 한 묶음이라 늘 같은 줄에 있다.
            # 갈라지면 좁은 카드에서 ⏸ 만 남고 시각이 아랫줄로 떨어진다.
            for r in self.rows:
                self.assertLess(
                    abs(r["belt"]["t"] - r["ela"]["t"]), 3.0,
                    "%s 에서 묶음이 갈라졌다: 벨트 t=%.1f · 시각 t=%.1f"
                    % (self._where(r), r["belt"]["t"], r["ela"]["t"]))
        with self.subTest("the_clock_shares_the_id_line_at_common_widths"):
            # 흔한 폭(320px)에서는 묶음이 식별자와 같은 첫 줄에 선다 — 스킨 예외
            # 없이. soft·calm 이 시각을 제 줄로 내리던 예외가 084 로 없어졌다.
            for r in self.rows:
                if r["w"] != COMMON:
                    continue
                self.assertLess(
                    abs(r["idr"]["t"] - r["idn"]["t"]), 3.0,
                    "%s 에서 묶음이 첫 줄을 떠났다: 식별자 t=%.1f · 묶음 t=%.1f"
                    % (self._where(r), r["idn"]["t"], r["idr"]["t"]))
        with self.subTest("the_narrow_card_drops_the_whole_group"):
            # 320px 보다 좁으면 내려가도 된다 — 다만 **묶음째** 내려가고,
            # 식별자의 왼끝은 그대로다(카드끼리 id 의 왼끝이 어긋나지 않는다).
            wide = {(r["scale"], r["skin"], r["den"], r["tag"]): r
                    for r in self.rows if r["w"] == COMMON}
            for r in self.rows:
                if r["w"] != NARROW:
                    continue
                ref = wide[(r["scale"], r["skin"], r["den"], r["tag"])]
                off = r["idn"]["l"] - r["card"]["l"]
                ref_off = ref["idn"]["l"] - ref["card"]["l"]
                # 왼끝은 오른쪽으로 밀리지 않는다 — 흔한 폭과 같은 자리에 서거나
                # (점이 있는 카드에서 식별자마저 내려가면) 줄머리에 선다. 밀린다면
                # 그것은 무언가가 식별자를 옆으로 떠민 것이다.
                self.assertTrue(
                    -0.5 <= off <= ref_off + 1.5,
                    "%s 에서 식별자의 왼끝이 밀렸다: 좁을 때 %.1f · 흔한 폭에서 "
                    "%.1f (카드 왼끝 기준)" % (self._where(r), off, ref_off))
                if abs(r["idr"]["t"] - r["idn"]["t"]) >= 3.0:
                    self.assertGreater(
                        r["idr"]["t"], r["idn"]["t"],
                        "%s 에서 묶음이 식별자 **위**로 갔다 — 내려갈 때는 "
                        "아랫줄이다" % self._where(r))
        with self.subTest("the_clock_and_the_handle_share_one_cell"):
            # 손이 얹히면 「이어 말하기」가 시각을 대신한다. 둘이 한 칸을 겹쳐
            # 쓰므로 칸 폭이 변하지 않고, 그래서 줄이 흔들리지 않는다.
            for r in self.rows:
                self.assertLess(
                    abs(r["pick"]["r"] - r["ela"]["r"]), 1.5,
                    "%s 에서 시각과 손잡이의 오른끝이 갈렸다: %.1f · %.1f — "
                    "겹친 칸이 아니면 손이 얹힐 때 줄이 흔들린다"
                    % (self._where(r), r["ela"]["r"], r["pick"]["r"]))
                self.assertLess(
                    abs(r["pick"]["t"] - r["ela"]["t"]), 3.0,
                    "%s 에서 시각과 손잡이가 다른 줄에 있다" % self._where(r))
        with self.subTest("the_long_id_goes_whole_not_cut"):
            by = {}
            for r in self.rows:
                by[(r["scale"], r["skin"], r["den"], r["w"], r["tag"])] = r
            for (sc, sk, dn, w, tag), r in by.items():
                if tag != "worst":
                    continue
                plain = by.get((sc, sk, dn, w, "plain"))
                self.assertIsNotNone(plain)
                w_worst = r["idn"]["r"] - r["idn"]["l"]
                w_plain = plain["idn"]["r"] - plain["idn"]["l"]
                self.assertGreater(
                    w_worst, w_plain + 10,
                    "%s/%s@%g w=%d 에서 21자 식별자(%.1f)가 16자(%.1f)만큼도 "
                    "안 넓다 — 잘렸다" % (sk, dn, sc, w, w_worst, w_plain))

if __name__ == "__main__":
    unittest.main()
