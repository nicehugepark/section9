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

  · 묶음은 갈라지지 않는다 — 벨트와 시각은 어느 폭에서도 같은 줄에 있고,
    **그 사이가 벌어지지도 않는다.** 세로로 붙어 있어도 사이가 20px 벌어지면
    사람은 「⏸ 만 남고 시각은 저쪽」으로 읽는다(주인 반려 2026-09-09 17:09).
    빈 자리는 손잡이가 칸의 폭을 정하던 데서 왔다 — 이제 칸의 폭은 시각이
    정하고 손잡이는 그 칸 안에 떠 있다(web/css/board.css `.idnow`).
  · 흔한 폭(320px, 실제 Board 열은 최소 210px·보통 216~288px)에서는 묶음이
    식별자와 같은 첫 줄에 선다.
  · 그보다 좁으면 묶음째 내려가되 식별자의 왼끝은 그대로고, 내려간 묶음은
    줄의 오른끝에 선다 — 카드끼리 id 의 왼끝도 시각의 오른끝도 어긋나지 않는다.

진짜 브라우저(WSL 이면 Windows Chrome)를 배율 1 · 1.25 · 1.5 로 띄우고
(배율 불변 — 비정수 배율의 반올림 함정은 DOC-20260831-004), 스킨 열 개 ×
밀도 두 벌 × 폭 두 벌을 한 페이지에서 갈아 끼우며 카드 넷을 잰다:

  worst   점 없음 · 21자 전체형 식별자 · 최장 경과(999d 23h) — 신고된 결함의
          최악 조합. 점 없는 카드는 식별자가 flex 줄의 첫 항목이라 줄바꿈이
          안 되던 바로 그 카드다.
  plain   점 없음 · 16자 표준형 (같은 이름의 문서가 없으면 화면이 쓰는 형태)
  dotted  점 있음 · 21자 — 점이 식별자를 둘째 항목으로 만들어 주던 경우
  tiny    짧은 식별자 — 한 줄에 드는 카드가 공연히 내려가지 않는지
  live    주인 화면의 그 카드 — 점 있음 · 16자 · 분초 경과. 극단만 재던 것이
          084 를 통과시켰다.

폭 세 벌: 170px 은 신고된 결함의 그 폭(cork compact @1000px), 220px 은 주인
화면의 카드 폭(1440 창), 320px 은 넉넉한 Board 열이다.

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
    # 주인 화면에 실제로 서 있는 그 카드 (2026-09-09 캡처): 진행 중이라 점이
    # 있고, 같은 이름의 문서가 없어 식별자는 16자, 경과는 분·초다. 앞의 넷은
    # 극단을 재고 이것은 **흔한 것**을 잰다 — 084 가 통과했던 까닭이 흔한
    # 카드를 아무도 재지 않았기 때문이다.
    ("live", True, "REQ-20260909-099", "4m 55s"),
)
# 170px = 신고된 결함의 그 폭, 220px = 주인 화면의 카드 폭(1440 창 · Board 열
# 240px 에서 안여백을 뺀 값 · `.col{flex:1 1 252px;min-width:210px}`), 320px = 넉넉한 열.
# **REAL 을 재지 않았던 것이 084 를 통과시켰다** (주인 반려 2026-09-09 17:09):
# 320px 만 재면 화면이 실제로 쓰는 폭이 검사 밖에 있어, 그 폭에서 묶음이 통째로
# 아랫줄로 내려가는 것을 「계약대로」로 읽었다.
NARROW, REAL, COMMON = 170, 220, 320
WIDTHS = (NARROW, REAL, COMMON)

# 벨트(⏸)도 카드가 실제로 쓰는 마크업 그대로 — 손잡이가 있는 카드라야 묶음이
# 갈라지는지 잴 수 있다. 글리프는 화면과 같은 viewBox 를 쓴다.
BELT = ('<span class="acts deedbelt"><button type="button" class="deed stop ico"'
        ' data-stop="x" data-kind="session" aria-label="중단하기"'
        ' title="중단하기"><svg class="gly" viewBox="0 0 13 13" aria-hidden="true">'
        '<rect x="3" y="2" width="3" height="9"/>'
        '<rect x="7" y="2" width="3" height="9"/></svg></button></span>')


def fixture_html():
    """실제 화면과 같은 캐스케이드·같은 마크업 — index.html 이 부르는 CSS 를 같은
    순서로, id 줄은 card.js 가 짓는 그 구조 그대로:

        .id[ .idmark[점 · 벨트]? · .idn · .pkst · .idr[ .idnow[시각 · .idact[낱말]]]]

    **픽스처가 한 세대 뒤처져 있던 것이 4차 반려의 절반이다**
    (REQ-20260910-009, 주인 2026-09-10 13:44: 「들여쓰기도 안맞고, 가려지고」).
    3차에서 card.js 는 벨트를 `.idact` 에서 **점의 자리(`.idmark`)** 로 옮겼는데
    이 픽스처는 옛 자리에 그대로 두었다. 그래서 43건이 통과하는 동안 화면에서는
    아무도 재지 않은 마크업이 그려졌다 — 이 파일의 첫 줄이 경고하던 바로 그
    일(「마크업이 화면과 어긋나면 이 시험은 화면이 아니라 제 픽스처를 잰다」)이
    이 파일 안에서 일어났다. 마크업을 card.js 와 한 글자씩 맞춘다.

    `.idmark` 는 **점이나 벨트가 있을 때만** 선다 — card.js 가 그렇게 짓는다
    (없는 카드에 13px 상자를 세우던 것이 「들여쓰기」의 정체다)."""
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    blocks = []
    for w in WIDTHS:
        cards = []
        for tag, dot, idn, ela in CARDS:
            # 점이 있는 카드에만 벨트가 선다 — 화면에서도 벨트는 「지금 붙어
            # 있는 것」에 서는 손이라 조용한 카드에는 없다. 마크 상자는 그 둘
            # 중 하나라도 있을 때만 나온다(card.js 의 `idmark`).
            mark = (('<span class="livedot on"></span>' + BELT) if dot else "")
            mark_html = '<span class="idmark">%s</span>' % mark if mark else ""
            cards.append(
                # 모든 카드를 **집힌 상태**로 세운다 (REQ-20260910-009 3차):
                # 집힘 낱말과 행위가 어느 얼굴에서도 잉크를 안 나누는지 재려면
                # 그 낱말이 실제로 그려져 있어야 한다. 004 가 「손 얹히면
                # 감춘다」로 피하던 겹침을, 이제 **자리**로 피하는지 잰다.
                '<div class="card picked" data-status="in-progress" id="c-%d-%s"'
                ' style="--sc:var(--muted)">'
                '<div class="id">%s'
                '<span class="idn">%s</span><span class="pkst">대상</span>'
                '<span class="idr"><span class="idnow">'
                '<span class="elapsed">%s</span>'
                '<span class="idact">'
                '<button type="button" class="pickdoc">이어 말하기</button>'
                '</span></span></span></div>'
                '<div class="t">제목 줄은 아래에서 시작한다</div>'
                '<div class="m"><span class="badge">nice</span></div></div>'
                % (w, tag, mark_html, idn, ela))
        blocks.append('<div class="cards" style="width:%dpx">%s</div>'
                      % (w, "".join(cards)))
    return ('<!doctype html><html lang="ko" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:16px;background:var(--bg)}'
            '.cards{display:inline-block;vertical-align:top;margin-right:12px}'
            # 캡처는 **손 얹힘 얼굴**로 뜬다 (REQ-20260910-009 4차). 주인이 본
            # 결함(잘린 낱말 · 제 줄로 떨어진 손잡이)은 전부 이 얼굴에 있고,
            # 캡처에는 포인터가 없어 :hover 가 안 걸린다. `visibility` 는 상자를
            # 1px 도 안 옮기므로 **재는 값은 그대로**이고 보이는 것만 달라진다.
            # 손 얹힘 얼굴은 셋이 함께 바뀐다(board.css) — 시각이 비키고, 그
            # 자리에 낱말이 서고, 점이 ■ 로 바뀐다. 하나라도 빠뜨리면 캡처에
            # 화면에 없는 얼굴(시각과 낱말이 겹친 것)이 뜬다.
            '.card .elapsed{visibility:hidden}'
            '.card .idact{visibility:visible}'
            '.card .id .idmark .acts.deedbelt{visibility:visible}'
            '.card .id .idmark .livedot{visibility:hidden}'
            '</style></head><body>%s</body></html>' % (css, "".join(blocks)))


MEASURE_JS = """
(() => {
  const box = el => { if (!el) return null; const r = el.getBoundingClientRect();
    return {l: r.left, r: r.right, t: r.top, b: r.bottom}; };
  const out = [];
  for (const card of document.querySelectorAll('.card')) {
    const [, w, tag] = card.id.split('-');
    const pick = card.querySelector('.pickdoc');
    const act = card.querySelector('.idact');
    out.push({w: +w, tag,
      card: box(card),
      idn: box(card.querySelector('.idn')),
      pkst: box(card.querySelector('.pkst')),
      idact: box(act),
      idr: box(card.querySelector('.idr')),
      idmark: box(card.querySelector('.idmark')),
      // 점이 서는 자리 — 벨트가 지켜야 하는 그 자다 (아래 the_belt_stands…).
      dot: box(card.querySelector('.livedot')),
      belt: box(card.querySelector('.deedbelt')),
      // 벨트는 **과녁과 칠이 다른 층**이다 (s9-design 7절): 버튼 상자는 27px
      // 과녁이고 그림은 13px 다. 자리를 재는 것은 그림 쪽이다 — 과녁은 일부러
      // 마크 상자 밖으로 나간다.
      beltInk: box(card.querySelector('.deedbelt svg.gly')),
      pick: box(pick),
      ela: box(card.querySelector('.elapsed')),
      title: box(card.querySelector('.t')),
      meta: box(card.querySelector('.m')),
      // 잘림은 상자로는 안 보인다 — 잘린 낱말도 상자는 온전하다. 그린 폭
      // (scrollWidth)과 보이는 폭(clientWidth)을 함께 실어야 잡힌다.
      pickInk: pick ? pick.scrollWidth : null,
      pickSeen: pick ? pick.clientWidth : null,
      actInk: act ? act.scrollWidth : null,
      actSeen: act ? act.clientWidth : null});
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
        with self.subTest("the_word_is_never_cut"):
            # **4차 반려가 세운 계약** (주인 2026-09-10 13:44: 「가려지고」 ·
            # 캡처에서 「이어 말하기」가 「기어 말하기」로 떴다).
            #
            # 3차는 행위 묶음을 흐름 밖에 두고 칸의 최소폭을 한 스킨에서 잰
            # 낱말 폭(55.9)에 맞춘 56px 로 못박은 뒤 `overflow:hidden` 으로
            # 넘침을 잘랐다. 다른 스킨의 mono 대체 글꼴이 한글을 더 넓게 그리면
            # 칸이 낱말보다 좁아지고, 오른끝 맞춤이라 잘려 나가는 것은 낱말의
            # **머리**였다. 상자만 재던 계약은 그것을 못 봤다 — 잘린 낱말도
            # 상자는 온전하기 때문이다. 그래서 **그린 폭과 보이는 폭**을 잰다.
            self.maxDiff = None
            self.assertEqual(
                [], ["%s 낱말이 %.1fpx 잘렸다 (그린 폭 %.1f · 보이는 폭 %.1f)"
                     % (self._where(r), r["pickInk"] - r["pickSeen"],
                        r["pickInk"], r["pickSeen"])
                     for r in self.rows
                     if r["pickInk"] - r["pickSeen"] > 0.5],
                "「이어 말하기」가 잘린다 — 칸이 낱말보다 좁다")
            self.assertEqual(
                [], ["%s 묶음이 %.1fpx 잘렸다"
                     % (self._where(r), r["actInk"] - r["actSeen"])
                     for r in self.rows
                     if r["actInk"] - r["actSeen"] > 0.5],
                "행위 묶음이 잘린다 — 칸이 묶음보다 좁다")
        with self.subTest("the_id_line_starts_where_the_card_does"):
            # **4차 반려가 세운 두 번째 계약** (주인: 「들여쓰기도 안맞고」).
            #
            # 3차는 벨트를 점의 자리로 보내며 그 자리를 13px 상자로 못박았는데,
            # **점도 벨트도 없는 카드에까지** 그 상자를 세웠다 — 화면의 대부분인
            # 그 카드들에서 식별자만 홀로 13px 안으로 들어가, 제목·메타와 왼끝이
            # 어긋났다. 마크가 없는 카드에서는 식별자가 카드의 다른 줄과 같은
            # 자리에서 시작해야 한다. 마크가 있는 카드는 마크가 그 자리에 서므로
            # **마크의 왼끝**이 그 자다.
            self.maxDiff = None
            bad = []
            for r in self.rows:
                head = r["idmark"] or r["idn"]
                for name in ("title", "meta"):
                    other = r[name]
                    if not other:
                        continue
                    off = head["l"] - other["l"]
                    if abs(off) > 1.0:
                        bad.append("%s id 줄의 왼끝이 %s 보다 %.1fpx 어긋났다"
                                   % (self._where(r), name, off))
            self.assertEqual([], bad,
                             "id 줄만 들여쓰였다 — 카드의 줄들이 한 자를 안 쓴다")
        with self.subTest("the_belt_stands_in_the_dot_place"):
            # 3차가 옮긴 자리를 **실측으로** 못박는다: 벨트는 점이 서는 자리에
            # 서고, 식별자와 같은 줄이며, 식별자의 잉크에 닿지 않는다.
            # 교대(점 ↔ ■)가 줄을 밀지 않는 근거가 이 셋이다.
            #
            # **재는 기준이 상자에서 점으로 바뀌었다** (REQ-20260910-009 5차 반려 —
            # 주인 2026-09-10 15:01: 「마우스를 올릴 때 위치가 바뀐다」). 종전에는
            # 마크 상자(`.idmark` 13px)의 한가운데를 자로 삼았는데, 정작 **점은
            # 그 한가운데에 선 적이 없다** — 점이 줄에서 쓰던 `margin-right:6px`
            # 를 들고 있어 잉크가 상자 왼쪽 7px 에 섰다. 그래서 이 항목이 통과하는
            # 동안에도 화면에서는 손을 얹을 때 마크가 3px 뛰었다. 자를 점으로
            # 바꾸면 그 어긋남이 이 항목에 잡힌다. 무대(상자 왼쪽 7px)가 왜 상자
            # 한가운데가 아닌지는 web/css/board.css 의 `.idmark` 주석에 있고,
            # 얼굴 여덟 × 벨트 둘 전수는 tests/test_mark_swap.py 가 잰다.
            self.maxDiff = None
            bad = []
            for r in self.rows:
                if not r["beltInk"] or not r["dot"]:
                    continue
                dt, bl = r["dot"], r["beltInk"]
                cx_dt = (dt["l"] + dt["r"]) / 2.0
                cx_bl = (bl["l"] + bl["r"]) / 2.0
                if abs(cx_dt - cx_bl) > 1.0:
                    bad.append("%s 벨트가 점의 자리를 벗어났다 "
                               "(%.1f vs %.1f)" % (self._where(r), cx_bl, cx_dt))
                # 좁은 폭에서 식별자가 아랫줄로 내려가는 것은 계약이다
                # (아래 the_narrow_card_drops_the_whole_group) — 그때는 벨트와
                # 식별자가 다른 줄인 것이 정상이라 같은 줄일 때만 잰다.
                if abs(bl["t"] - r["idn"]["t"]) < 3.0 \
                        and bl["r"] > r["idn"]["l"] + 0.5:
                    bad.append("%s 벨트의 그림이 식별자의 잉크로 %.1fpx 들어갔다"
                               % (self._where(r), bl["r"] - r["idn"]["l"]))
            self.assertEqual([], bad, "벨트가 점의 자리를 지키지 않는다")
        with self.subTest("the_group_drops_whole_at_real_columns"):
            # 주인 화면이 실제로 쓰는 폭(220px)에서 재는 갈래. 여기서 못 서는
            # 카드가 있다는 것 자체는 결함이 아니다 — 21자 식별자를 깎지 않는 한
            # 넣을 수 없는 폭이 있고(REQ-20260831-021), 그때는 묶음째 내려가는
            # 것이 계약이다. 결함은 **어떻게** 내려가느냐다: 내려간 묶음은 줄의
            # 오른끝(넉넉한 폭에서 서던 그 자리)에 서야 하고, 식별자의 왼끝은
            # 그대로여야 한다. 주인이 본 것은 이 자리이므로 여기서 잰다.
            self.maxDiff = None
            ref = {(r["scale"], r["skin"], r["den"], r["tag"]): r
                   for r in self.rows if r["w"] == COMMON}
            bad = []
            for r in self.rows:
                if r["w"] != REAL:
                    continue
                w = ref[(r["scale"], r["skin"], r["den"], r["tag"])]
                off = r["idn"]["l"] - r["card"]["l"]
                ref_off = w["idn"]["l"] - w["card"]["l"]
                if not -0.5 <= off <= ref_off + 1.5:
                    bad.append("%s 식별자의 왼끝이 밀렸다 (%.1f, 넉넉한 폭 %.1f)"
                               % (self._where(r), off, ref_off))
                if abs(r["idr"]["t"] - r["idn"]["t"]) < 3.0:
                    continue                    # 한 줄에 섰다 — 더 볼 것 없다
                if r["idr"]["t"] < r["idn"]["t"]:
                    bad.append("%s 묶음이 식별자 **위**로 갔다" % self._where(r))
                pad = r["card"]["r"] - r["idr"]["r"]
                ref_pad = w["card"]["r"] - w["idr"]["r"]
                if pad > ref_pad + 1.5:
                    bad.append("%s 내려간 묶음이 줄의 오른끝을 놓쳤다 (오른쪽 "
                               "여백 %.1f, 넉넉한 폭에서 %.1f)"
                               % (self._where(r), pad, ref_pad))
            self.assertEqual([], bad, "실제 열 폭에서 묶음이 제대로 안 내려갔다")
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
        with self.subTest("the_picked_word_keeps_its_ink"):
            # **004 의 「비켜서기」를 대신하는 계약** (REQ-20260910-009 3차).
            #
            # 그때는 손 얹히면 집힘 낱말을 감춰서 겹침을 피했다 — 낱말이 손잡이
            # 바로 왼쪽에 있었기 때문이다. 이제 낱말은 식별자 뒤(흐름 안)이고
            # 행위 묶음은 칸의 오른끝(흐름 밖)이라 **자리로** 겹치지 않는다.
            # 감추지 않고도 지켜지는지를 스킨·밀도·폭·배율 전수로 잰다.
            bad = []
            for r in self.rows:
                a, b = r.get("pkst"), r.get("idact")
                if not a or not b:
                    continue
                same_line = abs(a["t"] - b["t"]) < 8.0
                overlap = min(a["r"], b["r"]) - max(a["l"], b["l"])
                if same_line and overlap > 0.5:
                    bad.append("%s 집힘 낱말과 행위 묶음이 %.1fpx 겹친다"
                               % (self._where(r), overlap))
            self.maxDiff = None
            self.assertEqual([], bad,
                             "집힘 낱말이 손잡이에 덮인다 — 자리로 못 피하면 "
                             "004 처럼 감추는 수밖에 없어진다")
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
