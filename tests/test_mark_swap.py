"""마크가 교대해도 자리는 한 자다 — 점 ↔ 벨트 (REQ-20260910-009 5차 반려).

주인이 본 것 (2026-09-10 15:01, 캡처 넉 장):
  「문서 번호 좌측의 검정,빨강 네모가 마우스를 올릴 때 위치가 바뀐다.
    동그라미와 세모도 위치가 달라지고」

카드 식별자 줄의 왼쪽 상자(`.idmark`)는 **한 자리를 두 얼굴이 나눠 쓴다** —
쉼에는 상태를 말하는 점(`.livedot` 여덟 얼굴), 손이 얹히면 그 상태를 끝내는
손(`.acts.deedbelt` 의 ■ 또는 ▶). 나눠 쓰는 자리이므로 **두 얼굴의 중심이
같아야** 교대가 교대로 읽힌다. 중심이 갈리면 사람 눈에는 마크가 옆으로 뛴다.

뿌리였던 것: `.idmark` 는 13px 상자에 `justify-content:center` 인데 그 안의
`.livedot` 이 줄 안에서 쓰던 `margin-right` 를 그대로 들고 있었다. flex 의
가운데 맞춤은 margin 을 **포함해서** 재므로 점의 상자가 왼쪽으로 밀렸고,
벨트는 `left:50%`+`translate(-50%)` 라 상자 한가운데 그대로 섰다.

이 시험이 재는 것은 **자리 하나**다:

  · 점의 상자 중심과 벨트 그림(`svg.gly` 13px 격자)의 상자 중심이 x·y 둘 다
    한 자다. 얼굴 여덟 × 벨트 둘 × 스킨 열 × 밀도 둘 전수.
  · 그 자는 마크 상자(`.idmark`)의 한가운데다 — 어느 쪽도 상자를 벗어나
    식별자 쪽으로 기울지 않는다.

**격자 안쪽 잉크**의 대칭은 여기서 재지 않는다 — 그것은
`tests/test_hover_realscale.py` 가 실화소로 이미 잠그고 있고(▶ 는 무게중심
보정으로 왼쪽 4 : 오른쪽 2 라는 **의도된** 비대칭을 갖는다), 여기서 다시 재면
두 시험이 서로 다른 값을 요구하게 된다.

검증 환경이 없으면 조용히 지나가지 않고 skip 사유를 남긴다.

실행: python3 tests/ mark_swap
"""
import contextlib
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

SKINS = ("ledger", "slate", "cork", "grid", "soft", "calm",
         "glass", "cobalt", "field", "terminal")
DENSITIES = ("normal", "compact")

# 점의 여덟 얼굴 — actions.css 가 그리는 전부. 크기를 바꾸는 얼굴(.off 는
# `transform:scale(.78)`)까지 넣는 까닭은, 줄어들 때도 **중심에서** 줄어야
# 자리가 안 흔들리기 때문이다.
DOTS = ("on", "busy", "off", "sess", "spawn",
        "dot-stopped", "dot-stopped mild", "dot-held")

# 벨트의 두 얼굴 — card.js 의 GLYPH_STOP · GLYPH_PLAY 를 그대로 옮긴다.
# 좌표를 여기서 다시 적는 것은 픽스처가 화면과 어긋나지 않게 하기 위함이고,
# 그 어긋남이 REQ-20260910-009 4차 반려의 절반이었다(test_id_realscale 머리말).
BELTS = {
    "stop": '<rect x="4" y="4" width="5" height="5" fill="currentColor"/>',
    "play": '<path d="M4 3 L11 6.5 L4 10 Z" fill="currentColor"/>',
}

# 한도 — CSS px. 상자 좌표는 서브픽셀까지 나오므로 잡음이 거의 없다.
# 반려를 부른 어긋남은 3.0px 였고, 처방이 닿는 바닥은 0 이다. 0.5 는 스킨이
# 줄 높이·글꼴을 바꾸며 남길 수 있는 반올림만 통과시킨다.
TOL = 0.5

# 잉크가 서는 무대의 폭 — 점의 지름(`--dot-size:7px`)이다. 마크 상자 13px 의
# 왼쪽 7px 이 무대이고 남는 6px 은 식별자까지의 틈이다(web/css/board.css
# `.card .id .idmark`).
STAGE = 7.0


def _glyph(name):
    return ('<span class="acts deedbelt"><button type="button"'
            ' class="deed stop ico" data-stop="x" data-kind="session"'
            ' aria-label="중단하기" title="중단하기">'
            '<svg class="gly" viewBox="0 0 13 13" aria-hidden="true"'
            ' focusable="false">%s</svg></button></span>' % BELTS[name])


def fixture_html():
    """card.js 가 짓는 그 구조 그대로 — 마크 상자 안에 점과 벨트가 함께 산다.

    화면에서는 둘 중 하나만 보이지만(`visibility` 로 교대한다) **자리는 둘 다
    같은 순간에 정해진다** — 그래서 포인터를 얹지 않고도 두 얼굴의 상자를 한
    번에 잴 수 있다. `visibility` 는 상자를 1px 도 옮기지 않는다.
    """
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    cards = []
    for dot in DOTS:
        for bname in BELTS:
            cards.append(
                # 얼굴 이름에 `-` 가 들어 있으므로(dot-stopped) id 를 쪼개
                # 읽지 않는다 — 이름은 제 속성으로 들고 다닌다.
                '<div class="card" data-status="in-progress"'
                ' data-face="%s" data-belt="%s" style="--sc:var(--muted)">'
                '<div class="id"><span class="idmark">'
                '<span class="livedot %s"></span>%s</span>'
                '<span class="idn">REQ-20260910-009</span>'
                '<span class="idr"><span class="idnow">'
                '<span class="elapsed">37m 5s</span>'
                '<span class="idact"><button type="button" class="pickdoc">'
                '이어 말하기</button></span></span></span></div>'
                '<div class="t">담당 머신을 화면에서 바꾼다</div>'
                '<div class="m"><span class="badge">nice</span></div></div>'
                % (dot, bname, dot, _glyph(bname)))
    return ('<!doctype html><html lang="ko" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:16px;background:var(--bg)}'
            '.card{width:220px;margin-bottom:6px}'
            # 두 얼굴을 함께 세워 둔다 — 재는 것은 상자이지 잉크가 아니다.
            '.card .id .idmark .acts.deedbelt{visibility:visible}'
            '.card .id .idmark .livedot{visibility:visible}'
            '</style></head><body>%s</body></html>' % (css, "".join(cards)))


MEASURE_JS = """
(() => {
  const mid = r => ({x: (r.left + r.right) / 2, y: (r.top + r.bottom) / 2});
  const out = [];
  for (const card of document.querySelectorAll('.card')) {
    const dot = card.dataset.face, belt = card.dataset.belt;
    const mk = card.querySelector('.idmark').getBoundingClientRect();
    const ld = card.querySelector('.livedot').getBoundingClientRect();
    const gl = card.querySelector('.deedbelt svg.gly').getBoundingClientRect();
    const idn = card.querySelector('.idn').getBoundingClientRect();
    out.push({dot, belt,
      mark: mid(mk), dot_c: mid(ld), gly: mid(gl),
      mark_l: mk.left, mark_r: mk.right, idn_l: idn.left});
  }
  return out;
})()
"""


@contextlib.contextmanager
def _page(chrome, marker, html):
    """헤드리스 창 하나를 띄워 CDP 연결을 넘긴다 — 띄우고 거두는 일은 여기 한 번.

    이 파일에는 브라우저를 쓰는 시험이 둘이다(상자를 재는 것 · 손을 얹는 것).
    배관을 두 벌로 적으면 한 벌만 고쳐진다.
    """
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
        f.write(html)
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu",
         "--user-data-dir=" + prof_arg, "--no-first-run",
         "--no-default-browser-check", "--disable-extensions",
         "--remote-debugging-port=0", "--window-size=900,1400", url],
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
        time.sleep(0.3)
        yield ws
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


def measure(chrome):
    rows = []
    with _page(chrome, "s9markswap-%d" % os.getpid(), fixture_html()) as ws:
        for skin in SKINS:
            for den in DENSITIES:
                ws.eval("document.documentElement.dataset.skin=%r;"
                        "document.documentElement.dataset.density=%r"
                        % (skin, den))
                time.sleep(0.1)
                for d in ws.eval(MEASURE_JS):
                    rows.append(dict(d, skin=skin, den=den))
    return rows


class TheMarkKeepsItsPlaceWhenTheFaceChanges(unittest.TestCase):
    rows = None

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path()
        if not chrome:
            raise unittest.SkipTest("브라우저 없음 — 실측 불가 환경")
        try:
            cls.rows = measure(chrome)
        except (ConnectionError, RuntimeError, OSError) as e:
            raise unittest.SkipTest("CDP 실측 불가: %s" % e)

    def _where(self, r):
        return "%(skin)s/%(den)s %(dot)s+%(belt)s" % r

    @staticmethod
    def _cut(bad, keep=8):
        """320 조합 전수라 어긋나면 전부 어긋난다 — 앞 몇 줄과 건수만 보인다.
        실패 목록이 화면을 덮으면 읽는 사람이 무엇이 틀렸는지를 못 찾는다."""
        if len(bad) <= keep:
            return bad
        return bad[:keep] + ["… 그리고 %d건 더 (전수 %d건)"
                             % (len(bad) - keep, len(bad))]

    def test_the_mark_keeps_its_place_when_the_face_changes(self):
        """교대하는 두 얼굴은 한 자에 선다 — 갈래마다 재는 것이 다르다."""
        self.maxDiff = None
        with self.subTest("the_dot_stands_where_the_belt_stands"):
            bad = []
            for r in self.rows:
                dx = r["dot_c"]["x"] - r["gly"]["x"]
                dy = r["dot_c"]["y"] - r["gly"]["y"]
                if abs(dx) > TOL or abs(dy) > TOL:
                    bad.append("%s 점과 벨트의 중심이 갈렸다 "
                               "(가로 %.2f · 세로 %.2f px)"
                               % (self._where(r), dx, dy))
            self.assertEqual([], self._cut(bad),
                             "손을 얹으면 마크가 옆으로 뛴다 — 한 자리를 "
                             "나눠 쓰는 두 얼굴은 중심이 같아야 한다")
        with self.subTest("the_stage_is_the_row_head"):
            # **무대는 상자가 아니라 상자 왼쪽의 7px 이다.**
            #
            # 마크 상자는 13px 이지만 잉크가 서는 자리는 그 왼쪽 7px(점의 지름)
            # 이고, 남는 6px 은 마크와 식별자 사이의 틈이다. 무대를 상자
            # 한가운데로 옮기면 id 줄의 왼끝만 3px 안으로 들어가 제목·메타와
            # 어긋난다 — 4차 반려(「들여쓰기도 안맞고」)가 세운 계약이고
            # test_id_realscale 의 `the_id_line_starts_where_the_card_does` 가
            # 그 자를 지킨다. 그래서 여기서 재는 것은 「상자의 한가운데」가
            # 아니라 **줄머리에서 3.5px** 이다.
            bad = []
            for r in self.rows:
                for who in ("dot_c", "gly"):
                    dx = r[who]["x"] - (r["mark_l"] + STAGE / 2.0)
                    dy = r[who]["y"] - r["mark"]["y"]
                    if abs(dx) > TOL or abs(dy) > TOL:
                        bad.append("%s %s 가 무대(줄머리+%.1fpx)를 벗어났다 "
                                   "(가로 %.2f · 세로 %.2f px)"
                                   % (self._where(r), who, STAGE / 2.0, dx, dy))
            self.assertEqual([], self._cut(bad),
                             "마크가 무대를 벗어났다 — 무대가 자리를 지고 "
                             "얼굴은 잉크만 진다")
        with self.subTest("the_id_keeps_one_left_edge"):
            # 얼굴이 무엇이든 식별자의 왼끝은 한 자다 — 마크가 상자만큼만
            # 자리를 먹고, 그 상자는 얼굴을 안 따라 커지지 않는다.
            by = {}
            for r in self.rows:
                by.setdefault((r["skin"], r["den"]), []).append(r)
            bad = []
            for (skin, den), rs in by.items():
                lefts = sorted({round(x["idn_l"] - x["mark_l"], 2) for x in rs})
                if len(lefts) > 1 and lefts[-1] - lefts[0] > TOL:
                    bad.append("%s/%s 식별자의 왼끝이 얼굴마다 다르다: %s"
                               % (skin, den, lefts))
            self.assertEqual([], self._cut(bad),
                             "마크의 얼굴이 식별자를 밀었다")


# ---------------------------------------------------------------------------
# 손을 얹었을 때 — 교대할 짝이 없으면 교대하지 않는다 (REQ-20260910-049)
#
# 위의 시험이 재는 것은 「두 얼굴이 같은 자리에 서는가」이고, 여기서 재는 것은
# 「언제 교대하는가」다. 벨트는 멈출 수 있거나 이어갈 수 있는 카드에만 선다
# (card.js deedBeltHTML 은 어느 쪽도 아니면 빈 문자열). 그런데 점을 숨기는
# 규칙이 카드에 손이 얹혔다는 것만 보고 걸려 있으면, 세울 것이 없는 카드는
# 점만 사라지고 13px 구멍이 남는다 — 주인이 본 것이 그것이다(2026-09-10 21:13).

HOVER_HTML_CARDS = (
    ("with_belt", '<span class="livedot on"></span>'
                  + _glyph("stop")),
    ("no_belt", '<span class="livedot on"></span>'),
)


def hover_fixture():
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                     for f in css_files)
    cards = "".join(
        '<div class="card" data-status="in-progress" data-kind="%s"'
        ' style="--sc:var(--muted)">'
        '<div class="id"><span class="idmark">%s</span>'
        '<span class="idn">REQ-20260910-049</span></div>'
        '<div class="t">손 올리면 점 자리가 빈다</div></div>' % (name, inner)
        for name, inner in HOVER_HTML_CARDS)
    return ('<!doctype html><html lang="ko" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:16px;background:var(--bg)}'
            '.card{width:220px;margin-bottom:24px}</style></head>'
            '<body>%s</body></html>' % (css, cards))


HOVER_JS = """
(() => {
  const out = {};
  for (const card of document.querySelectorAll('.card')) {
    const dot = card.querySelector('.livedot');
    const belt = card.querySelector('.acts.deedbelt');
    out[card.dataset.kind] = {
      dot: getComputedStyle(dot).visibility,
      belt: belt ? getComputedStyle(belt).visibility : null,
      at: (r => ({x: (r.left + r.right) / 2, y: (r.top + r.bottom) / 2}))(
        card.getBoundingClientRect()),
    };
  }
  return out;
})()
"""


def hover_states(chrome):
    """손을 얹기 전과 뒤의 `visibility` 를 카드별로 잰다 — 진짜 포인터로.

    `:hover` 를 흉내내지 않는다: CDP 로 마우스를 그 카드 위로 **옮긴다**.
    사람이 하는 것과 같은 사건이라야 CSS 가 같은 판정을 한다.
    """
    with _page(chrome, "s9hover-%d" % os.getpid(), hover_fixture()) as ws:
        before = ws.eval(HOVER_JS)
        after = {}
        for kind, v in before.items():
            ws.call("Input.dispatchMouseEvent", type="mouseMoved",
                    x=v["at"]["x"], y=v["at"]["y"], buttons=0)
            time.sleep(0.15)
            after[kind] = ws.eval(HOVER_JS)[kind]
        # 손을 치운다 — 다음 회차가 앞의 자국을 물려받지 않게.
        ws.call("Input.dispatchMouseEvent", type="mouseMoved", x=1, y=1,
                buttons=0)
        return before, after


class TheDotStaysWhenThereIsNothingToSwapWith(unittest.TestCase):
    """손잡이가 없는 카드는 손을 얹어도 점이 남는다 (REQ-20260910-049)."""

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path(pixel_contract=False)
        if not chrome:
            raise unittest.SkipTest("브라우저 없음 — 실측 불가 환경")
        try:
            cls.before, cls.after = hover_states(chrome)
        except (ConnectionError, RuntimeError, OSError) as e:
            raise unittest.SkipTest("CDP 실측 불가: %s" % e)

    def test_h1_a_card_with_a_handle_swaps_the_dot_for_it(self):
        """손잡이가 있으면 점이 물러나고 그 자리에 손잡이가 선다."""
        self.assertEqual("hidden", self.after["with_belt"]["dot"],
                         "손잡이가 섰는데 점도 함께 보인다 — 한 자리에 둘이다")
        self.assertEqual("visible", self.after["with_belt"]["belt"],
                         "손을 얹었는데 손잡이가 안 선다")

    def test_h2_a_card_without_a_handle_keeps_its_dot(self):
        """세울 것이 없으면 점이 그대로다 — 빈 자리를 남기지 않는다."""
        self.assertEqual("visible", self.after["no_belt"]["dot"],
                         "손잡이가 없는 카드에서 점만 사라졌다 — 식별자 "
                         "왼쪽이 아무것도 없는 자리가 된다 (주인 지적 "
                         "2026-09-10 21:13)")

    def test_h3_before_the_hand_both_cards_show_their_dot(self):
        """손을 얹기 전에는 둘 다 점이다 — 회귀 기준선."""
        for kind in ("with_belt", "no_belt"):
            self.assertEqual("visible", self.before[kind]["dot"], kind)
        self.assertEqual("hidden", self.before["with_belt"]["belt"],
                         "손을 얹지 않았는데 손잡이가 서 있다")


if __name__ == "__main__":
    unittest.main()
