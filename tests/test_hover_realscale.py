"""⏸·▶ hover 얼굴은 표시 배율이 바뀌어도 대칭이다 (REQ-20260831-006 3차 · -019).

사용자가 본 것: CSS 픽셀(배율 1) 수치로는 상하좌우 3.0px 균등이었는데, 실제
화면(Windows 표시 배율 125%)에서는 ⏸ hover 원이 여전히 비대칭으로 그려졌다.
뿌리는 상자가 둘이었던 것 — 원은 버튼의 content-box 배경, 그림은 그 안에 1px
들여 놓인 다른 상자의 SVG 라, 비정수 배율에서 그 1px(=1.25화소)이 반화소에
걸리며 배경 칠과 SVG 래스터가 서로 다른 쪽으로 반올림했다.

이 시험은 그 결함이 다시 올 수 없음을 **실제 렌더 화소**로 재서 지킨다:
진짜 브라우저(WSL 이면 Windows Chrome)를 `--force-device-scale-factor` 로
배율 1 · 1.25 · 1.5 세 벌로 띄우고, CDP `Input.dispatchMouseEvent` 로 실포인터를
얹은 뒤(CSS 로 hover 를 흉내 내지 않는다), 캡처의 **화소**에서 원과 잉크의
가장자리를 반값 교차(half-max crossing)로 소수점까지 읽는다.

계약(각 배율에서, 단위는 그 배율의 실화소):
  ① 원은 정원이다 — 가로 지름과 세로 지름의 차가 화소 반올림 한도 안이다.
  ② ⏸ 잉크는 원 한가운데 선다 — 좌/우 틈의 차, 상/하 틈의 차가 한도 안이다.
  ③ ▶ 는 상/하 틈이 같고, 가로는 무게중심 보정(의도된 왼쪽 4 : 오른쪽 2,
     CSS px)이 배율에 비례해 유지된다.

검증 환경이 없으면(브라우저·CDP 접속 불가) 조용히 지나가지 않고 skip 사유를
남긴다 — 통과처럼 보이는 미검증이 이 결함의 1차 원인이었다.

캡처는 scratchpad/hover-realscale/ 에 남는다(확대본 포함) — 수치는 눈의 보조지
대체가 아니므로(browser-verify), 판정자는 그 그림을 직접 본다.

실행: python3 tests/ hover_realscale
"""
import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import zlib

from webasset import parts

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")
OUT = os.path.join(REPO, "scratchpad", "hover-realscale")

SCALES = (1.0, 1.25, 1.5)
# 실화소 대칭 한도 — 역대 결함과 잡음 사이에 긋는다.
#   사용자가 반려로 잡아낸 크기: 글리프 치우침 0.5~0.63화소 (+ 원 17×16 찌그러짐),
#   16눈금 실패작의 배율1 붕괴: 0.95화소.
#   mask 처방 뒤의 바닥(계측 잡음 + AA 위상): 최악 패리티에서 0.30~0.37화소 —
#   반화소 원점(패리티) × 1.25 배율에서 원 mask 의 흐림 띠와 잉크 AA 가
#   서로 다른 화소 경계에 걸릴 때 남는 몫으로, CSS px 로는 0.3 아래라 눈은
#   원 크기(21화소)에서 못 가른다.
# 0.45 는 그 두 무리를 가른다: 반려를 부른 크기(≥0.5)는 전부 잡고, 처방이
# 도달할 수 있는 바닥은 통과시킨다.
TOL = 0.45


from cdpreal import WS, chrome_path, reclaim  # noqa: F401 — 공용 CDP 헬퍼

# ---- PNG (stdlib 해독 — 화소를 직접 읽기 위해) ------------------------------

def png_decode(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG 아님")
    pos, idat, w = 8, b"", None
    while pos + 8 <= len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if typ == b"IHDR":
            w, h, depth, ct, _c, _f, ilace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ilace or ct not in (2, 6):
                raise ValueError("지원 밖 PNG (depth=%s ct=%s)" % (depth, ct))
            ch = 3 if ct == 2 else 4
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    raw = zlib.decompress(idat)
    stride = w * ch
    out = bytearray(stride * h)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, ch, bytes(out)


def png_write(path, w, h, rgb):
    """rgb: 행 우선 RGB bytes — 확대 캡처 저장용."""
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3]
                   for y in range(h))

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw)))
        f.write(chunk(b"IEND", b""))


class Img:
    def __init__(self, png_bytes):
        self.w, self.h, self.ch, self.px = png_decode(png_bytes)

    def rgb(self, x, y):
        o = (y * self.w + x) * self.ch
        return self.px[o], self.px[o + 1], self.px[o + 2]

    def crop(self, x0, y0, x1, y1):
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.w, x1), min(self.h, y1)
        rows = []
        for y in range(y0, y1):
            rows.append([self.rgb(x, y) for x in range(x0, x1)])
        return rows


def save_zoom(path, rows, z=12):
    h, w = len(rows), len(rows[0])
    out = bytearray()
    for y in range(h):
        line = bytearray()
        for x in range(w):
            line += bytes(rows[y][x]) * z
        out += bytes(line) * z
    png_write(path, w * z, h * z, bytes(out))


# ---- 가장자리 읽기 (half-max crossing, 소수점 화소) -------------------------

def _cross(profile):
    """반값 교차점 (first, last). 값이 없으면 None."""
    peak = max(profile)
    if peak <= 0:
        return None
    half = peak / 2.0
    first = last = None
    for i in range(len(profile)):
        if profile[i] >= half:
            if i == 0:
                first = 0.0
            else:
                a, b = profile[i - 1], profile[i]
                first = i - 1 + (half - a) / (b - a)
            break
    for i in range(len(profile) - 1, -1, -1):
        if profile[i] >= half:
            if i == len(profile) - 1:
                last = float(i)
            else:
                a, b = profile[i], profile[i + 1]
                last = i + (a - half) / (a - b)
            break
    return first, last


def extents(field):
    """2차원 세기 field 의 (L, R, T, B) — 축별 최대 투영의 반값 교차."""
    h, w = len(field), len(field[0])
    px = [max(field[y][x] for y in range(h)) for x in range(w)]
    py = [max(field[y][x] for x in range(w)) for y in range(h)]
    cx, cy = _cross(px), _cross(py)
    if not cx or not cy:
        return None
    return cx[0], cx[1], cy[0], cy[1]


NOISE = 8    # 캡처 잡음·낱자 AA 꼬리의 바닥값 — 이 아래는 잉크로 안 센다


def diff_field(a, b):
    return [[(lambda v: v if v >= NOISE else 0)(
        max(abs(p[0] - q[0]), abs(p[1] - q[1]), abs(p[2] - q[2])))
        for p, q in zip(ra, rb)] for ra, rb in zip(a, b)]


def ink_field(rows):
    """쉬는 얼굴의 잉크(배경보다 어두운 정도). 배경은 테두리 화소의 중앙값."""
    lum = [[0.299 * r + 0.587 * g + 0.114 * b for r, g, b in row]
           for row in rows]
    edge = lum[0] + lum[-1] + [row[0] for row in lum] + [row[-1] for row in lum]
    edge.sort()
    bg = edge[len(edge) // 2]
    return [[(lambda v: v if v >= NOISE else 0.0)(max(0.0, bg - v))
             for v in row] for row in lum]


def moments(field):
    """세기 가중 (중심 x, 중심 y, 퍼짐 σx, σy).

    가장자리 반값 교차는 AA 의 위상(어느 화소에 걸쳤나)에 따라 ±0.5화소를
    오르내려 판정 잣대로 못 쓴다(첫 실행 실측). 무게중심과 2차 모멘트는 AA
    무게까지 통째로 세므로 위상에 둔감하다 — 대칭 도형이 실제로 치우쳤을 때만
    움직인다. 균일 원판의 σ 는 반지름/2 다."""
    tot = sx = sy = 0.0
    for y, row in enumerate(field):
        for x, v in enumerate(row):
            tot += v
            sx += v * x
            sy += v * y
    if tot <= 0:
        return None
    cx, cy = sx / tot, sy / tot
    vx = vy = 0.0
    for y, row in enumerate(field):
        for x, v in enumerate(row):
            vx += v * (x - cx) ** 2
            vy += v * (y - cy) ** 2
    return cx, cy, (vx / tot) ** 0.5, (vy / tot) ** 0.5


# ---- 본 시험 ---------------------------------------------------------------

def glyph_sources():
    """card.js 의 글리프 상수 원문 — {'GLYPH_PAUSE': svg, 'GLYPH_PLAY': svg}."""
    src = open(os.path.join(WEB, "app", "card.js"), encoding="utf-8").read()
    out = {}
    for name in ("GLYPH_PAUSE", "GLYPH_PLAY"):
        m = re.search(r"const %s =([^;]+);" % name, src)
        if not m:
            raise AssertionError("card.js 에서 %s 를 못 찾았다" % name)
        out[name] = "".join(re.findall(r"'([^']*)'", m.group(1)))
    return out


def grid():
    """눈금을 원천에서 읽는다 — 기대값을 시험에 굳혀 적으면 designer 가 눈금을
    옮길 때마다(13 → 16 실사고) 시험이 옛 눈금을 강요한다. 시험이 지키는 것은
    수가 아니라 **관계**다: 과녁 27 = 원 + 2×padding + 테두리2, viewBox 한 칸 =
    한 화소, 잉크는 원 가운데."""
    css = open(os.path.join(WEB, "css", "actions.css"),
               encoding="utf-8").read()
    css = re.sub(r"/\*[\s\S]*?\*/", " ", css)
    m = re.search(r"\.acts button\.deed\.ico \.gly\{[^}]*?"
                  r"width:(\d+(?:\.\d+)?)px", css)
    if not m:
        raise AssertionError("actions.css 에서 .gly 크기를 못 찾았다")
    g = float(m.group(1))
    m = re.search(r"\.acts\.deedbelt button\.deed\.ico\{[^}]*?"
                  r"padding:(\d+(?:\.\d+)?)px", css)
    if not m:
        raise AssertionError("actions.css 에서 벨트 버튼 padding 을 못 찾았다")
    pad = float(m.group(1))
    gs = glyph_sources()
    vb = {}
    ink = {}
    for name, svg in gs.items():
        mv = re.search(r'viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"', svg)
        vb[name] = (float(mv.group(1)), float(mv.group(2)))
        if name == "GLYPH_PAUSE":
            rects = re.findall(r'<rect x="([\d.]+)" y="([\d.]+)"'
                               r' width="([\d.]+)" height="([\d.]+)"', svg)
            ink[name] = [tuple(map(float, r)) for r in rects]
        else:
            pts = re.findall(r"([\d.]+)[ ,]([\d.]+)", re.search(
                r'd="([^"]+)"', svg).group(1))
            ink[name] = [tuple(map(float, p)) for p in pts]
    return {"gly": g, "pad": pad, "vb": vb, "ink": ink}


class TheGridKeepsItsContract(unittest.TestCase):
    """브라우저 없이도 지키는 정적 계약 — 눈금의 관계식."""

    @classmethod
    def setUpClass(cls):
        cls.g = grid()

    def test_the_target_stays_27(self):
        """원 + 2×padding + 테두리 2 = 과녁 27 (과녁은 1px 도 안 준다)."""
        got = self.g["gly"] + 2 * self.g["pad"] + 2
        self.assertAlmostEqual(got, 27.0, places=3,
                               msg="눈금 합이 과녁을 벗어났다: %.3f" % got)

    def test_one_cell_is_one_pixel(self):
        """viewBox 한 칸 = .gly 한 화소 — 어긋나면 획이 격자에 안 앉는다."""
        for name, (w, h) in self.g["vb"].items():
            self.assertEqual((w, h), (self.g["gly"], self.g["gly"]),
                             "%s 의 viewBox(%g×%g)가 그림 상자(%g)와 다르다"
                             % (name, w, h, self.g["gly"]))

    def test_the_pause_ink_is_mirror_symmetric_in_source(self):
        """⏸ 두 막대는 좌우 거울이고 상하 여백이 같다 — 좌표 원천에서."""
        vbw = self.g["vb"]["GLYPH_PAUSE"][0]
        (x1, y1, w1, h1), (x2, y2, w2, h2) = self.g["ink"]["GLYPH_PAUSE"]
        self.assertEqual((y1, h1), (y2, h2), "두 막대의 세로가 다르다")
        self.assertAlmostEqual(x1, vbw - (x2 + w2), places=3,
                               msg="두 막대가 좌우 거울이 아니다")
        self.assertAlmostEqual(y1, self.g["vb"]["GLYPH_PAUSE"][1] - (y1 + h1),
                               places=3, msg="상하 여백이 다르다")


def pause_expected_center(g):
    (x1, y1, w1, h1), (x2, y2, w2, h2) = g["ink"]["GLYPH_PAUSE"]
    return ((x1 + x2 + w2) / 2.0, y1 + h1 / 2.0)


def play_expected_center(g):
    pts = g["ink"]["GLYPH_PLAY"]
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


def fixture_html():
    """실제 화면과 같은 캐스케이드 — CSS 는 index.html 이 부르는 조각을 같은
    순서로 잇고(브라우저가 받는 all.css 와 동일), 글리프는 card.js 의 상수를
    원문에서 뽑아 쓴다. 흉내가 아니라 원본이다."""
    css_files, _apps = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    glyphs = glyph_sources()
    return ("<!doctype html>"
            '<html lang="ko" data-theme="light" data-skin="ledger"'
            ' data-density="normal"><head><meta charset="utf-8">'
            "<style>%s</style>"
            "<style>body{margin:24px;background:var(--bg)}</style></head>"
            "<body>%s%s</body></html>"
            % (css, _card_html("", "0px", glyphs),
               _card_html("h", "0.5px", glyphs)))


def _card_html(suffix, nudge, glyphs):
    """같은 카드 두 벌 — 두 번째는 0.5px 밀어 **반대 반화소 패리티**에 세운다.

    대칭은 카드가 화면 어디에 앉느냐와 무관해야 한다. 한 원점만 재면 그 원점의
    운(패리티)이 통과를 만든다 — 실제로 한쪽 패리티에서만 대칭이고 다른 쪽에서
    1화소 어긋나는 상태가 이 시험이 잡은 결함이다."""
    return ('<div class="cards" style="width:320px;margin-left:%s;'
            'margin-top:%s">'
            '<div class="card" data-status="in-progress"'
            ' style="--sc:var(--muted)">'
            '<div class="id"><span class="idn">REQ-20260831-006</span>'
            '<span class="acts deedbelt">'
            '<button type="button" class="deed stop ico" id="pp%s"'
            ' aria-label="중단해 두기">%s</button>'
            '<button type="button" class="deed wake ico" id="ww%s"'
            ' aria-label="이어가기">%s</button>'
            "</span></div></div></div>"
            % (nudge, nudge, suffix, glyphs["GLYPH_PAUSE"],
               suffix, glyphs["GLYPH_PLAY"]))


class Face:
    """한 배율에서 두 버튼의 실측치."""
    def __init__(self, scale):
        self.scale = scale
        self.metrics = {}


def _shoot(ws):
    r = ws.call("Page.captureScreenshot", format="png", fromSurface=True)
    return Img(base64.b64decode(r["data"]))


def _rect(ws, sel):
    return ws.eval(
        "(() => { const r = document.querySelector('%s')"
        ".getBoundingClientRect();"
        " return {x:r.x, y:r.y, w:r.width, h:r.height}; })()" % sel)


def measure_scale(chrome, win_mode, scale, tag):
    """브라우저 한 벌을 배율 scale 로 띄워 ⏸·▶ 를 재고 회수한다."""
    marker = "s9hover-%d-%s" % (os.getpid(), tag)
    if win_mode:
        os.makedirs("/mnt/c/Temp", exist_ok=True)
        prof_wsl = "/mnt/c/Temp/" + marker
        prof_arg = "C:\\Temp\\" + marker
        fix_wsl = os.path.join("/mnt/c/Temp", marker + "-fix.html")
        url = "file:///C:/Temp/%s-fix.html" % marker
    else:
        base = os.environ.get("TMPDIR", "/tmp")
        prof_wsl = prof_arg = os.path.join(base, marker)
        fix_wsl = os.path.join(base, marker + "-fix.html")
        url = "file://" + fix_wsl
    shutil.rmtree(prof_wsl, ignore_errors=True)
    with open(fix_wsl, "w", encoding="utf-8") as f:
        f.write(fixture_html())
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu",
         "--user-data-dir=" + prof_arg,
         "--no-first-run", "--no-default-browser-check",
         "--disable-extensions", "--disable-background-networking",
         "--remote-debugging-port=0",
         "--force-device-scale-factor=%g" % scale,
         "--window-size=420,240", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        port = None
        dev = os.path.join(prof_wsl, "DevToolsActivePort")
        for _ in range(120):
            if os.path.exists(dev):
                try:
                    port = int(open(dev, encoding="utf-8")
                               .read().splitlines()[0])
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
        time.sleep(0.4)
        face = Face(scale)
        os.makedirs(OUT, exist_ok=True)
        for name, sel in (("pause", "#pp"), ("play", "#ww"),
                          ("pause+h", "#pph"), ("play+h", "#wwh")):
            rect = _rect(ws, sel)
            # 실포인터를 카드 밖에 두고 쉬는 얼굴을 찍는다
            ws.call("Input.dispatchMouseEvent", type="mouseMoved",
                    x=5.0, y=5.0)
            time.sleep(0.3)
            rest = _shoot(ws)
            # 원만 따로 잰다: 글리프를 잠시 숨기면(visibility — 레이아웃 불변)
            # diff 가 순수한 원판이 된다. 글리프를 보이는 채로 재면 글리프
            # 반전(진한→밝은)의 diff 무게가 원의 무게중심을 끌어당겨, ▶ 처럼
            # 비대칭 그림에서 원 측정이 거짓으로 치우친다 (2차 실행 실측).
            ws.eval("document.querySelector('%s .gly')"
                    ".style.visibility='hidden'" % sel)
            time.sleep(0.15)
            bare = _shoot(ws)
            cx = rect["x"] + rect["w"] / 2.0
            cy = rect["y"] + rect["h"] / 2.0
            ws.call("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy)
            time.sleep(0.3)
            ring = _shoot(ws)
            ws.eval("document.querySelector('%s .gly')"
                    ".style.visibility=''" % sel)
            time.sleep(0.15)
            hov = _shoot(ws)          # 손 얹힌 온전한 얼굴 — 눈으로 볼 그림
            # 오려 내는 창은 버튼 중심 ± 9css — 원(반지름 6.5)은 여백을 두고
            # 다 담고, 27px 과녁의 가장자리는 버린다. 더 넓히면 이웃의 잉크가
            # 글리프 측정에 섞인다: 벨트는 식별자에 -2px 로 붙어 서므로 낱자의
            # AA 꼬리가 과녁 왼끝 밑에 실제로 들어와 있었다 (첫 실행 실측).
            half = 9
            x0 = int((cx - half) * scale)
            y0 = int((cy - half) * scale)
            x1 = int((cx + half) * scale) + 1
            y1 = int((cy + half) * scale) + 1
            crop_r = rest.crop(x0, y0, x1, y1)
            crop_h = hov.crop(x0, y0, x1, y1)
            dfield = diff_field(bare.crop(x0, y0, x1, y1),
                                ring.crop(x0, y0, x1, y1))
            ifield = ink_field(crop_r)
            circle, ink = extents(dfield), extents(ifield)
            cmom, imom = moments(dfield), moments(ifield)
            if not circle or not ink or not cmom or not imom:
                raise AssertionError("%s@%g: 원/잉크를 화소에서 못 찾았다"
                                     % (name, scale))
            face.metrics[name] = {"circle": circle, "ink": ink,
                                  "cmom": cmom, "imom": imom}
            save_zoom(os.path.join(
                OUT, "%s-%s-hover-x12.png" % (tag, name)), crop_h)
            save_zoom(os.path.join(
                OUT, "%s-%s-rest-x12.png" % (tag, name)), crop_r)
        return face
    finally:
        if ws is not None:
            ws.close()
        try:
            proc.terminate()
        except OSError:
            pass
        reclaim(marker, win_mode)
        shutil.rmtree(prof_wsl, ignore_errors=True)
        try:
            os.remove(fix_wsl)
        except OSError:
            pass


def gaps(m):
    cl, cr, ct, cb = m["circle"]
    il, ir, it, ib = m["ink"]
    return il - cl, cr - ir, it - ct, cb - ib


class TheHoverFaceIsSymmetricAtEveryScale(unittest.TestCase):
    faces = None

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path()
        if chrome is None:
            raise unittest.SkipTest(
                "실브라우저 미검증 — Chrome/Edge 를 찾지 못했다")
        win_mode = chrome.startswith("/mnt/")
        cls.faces = {}
        try:
            for i, s in enumerate(SCALES):
                cls.faces[s] = measure_scale(chrome, win_mode, s,
                                             "s%d" % int(s * 100))
        except (ConnectionError, StopIteration, OSError,
                urllib.error.URLError) as e:
            raise unittest.SkipTest(
                "실브라우저 미검증 — CDP 접속 실패: %r" % e)

    def _each(self):
        for s, face in sorted(self.faces.items()):
            for name in sorted(face.metrics):
                yield s, name, face.metrics[name]

    def test_the_circle_is_round(self):
        """① hover 원의 가로 퍼짐 = 세로 퍼짐 (17×16 으로 찌그러졌던 결함).

        균일 원판의 σ 는 반지름/2 다. 결함급 찌그러짐(0.65css 초과)은
        Δσ ≈ 0.2화소로 나타난다 — 한도는 그 아래, 잡음 위다."""
        g = grid()
        for s, name, m in self._each():
            _cx, _cy, sx, sy = m["cmom"]
            self.assertLessEqual(
                abs(sx - sy), 0.12,
                "%s@%g: 원의 퍼짐이 σx %.3f / σy %.3f — 찌그러졌다"
                % (name, s, sx, sy))
            want = g["gly"] / 4.0 * s      # 지름/4 — AA 가 조금 넓힌다
            for v in (sx, sy):
                self.assertLessEqual(
                    abs(v - want), 0.6,
                    "%s@%g: 원 크기가 %gcss 에서 벗어났다 (σ %.3f, 기대 %.2f)"
                    % (name, s, g["gly"], v, want))

    def _ink_offsets(self, m):
        return (m["imom"][0] - m["cmom"][0], m["imom"][1] - m["cmom"][1])

    def test_the_pause_ink_stands_centered(self):
        """② ⏸ 잉크의 무게중심이 원의 무게중심에 선다 (0.5화소 치우침이
        결함이었다 — 한도는 그 아래). 기대 중심은 좌표 원천에서 읽는다."""
        g = grid()
        ex, ey = pause_expected_center(g)
        vb = g["vb"]["GLYPH_PAUSE"]
        for s, name, m in self._each():
            if not name.startswith("pause"):
                continue
            dx, dy = self._ink_offsets(m)
            self.assertLessEqual(
                abs(dx - (ex - vb[0] / 2) * s), TOL,
                "pause@%g: 잉크가 원 중심에서 가로 %+.3f화소 치우쳤다"
                % (s, dx))
            self.assertLessEqual(
                abs(dy - (ey - vb[1] / 2) * s), TOL,
                "pause@%g: 잉크가 원 중심에서 세로 %+.3f화소 치우쳤다"
                % (s, dy))

    def test_the_play_ink_keeps_its_deliberate_lean(self):
        """③ ▶ 도 무게중심으로 가운데 선다 — 상자를 민 것이 무게중심을 원
        중심에 데려오는 보정이다. 설계 잔차(삼각형 꼭짓점 무게중심 − 상자
        중심)는 좌표 원천에서 유도한다."""
        g = grid()
        ex, ey = play_expected_center(g)
        vb = g["vb"]["GLYPH_PLAY"]
        for s, name, m in self._each():
            if not name.startswith("play"):
                continue
            dx, dy = self._ink_offsets(m)
            want = (ex - vb[0] / 2) * s
            self.assertLessEqual(
                abs(dy - (ey - vb[1] / 2) * s), TOL,
                "play@%g: 잉크가 원 중심에서 세로 %+.3f화소 치우쳤다"
                % (s, dy))
            self.assertLessEqual(
                abs(dx - want), TOL,
                "play@%g: 잉크 무게중심이 가로 %+.3f화소 — 설계 잔차 "
                "%+.3f 를 벗어났다" % (s, dx, want))

    def test_the_report_is_written(self):
        """실측치를 한 장으로 남긴다 — 판정자가 볼 수치와 그림의 색인."""
        lines = []
        for s, name, m in self._each():
            gl, gr, gt, gb = gaps(m)
            cl, cr, ct, cb = m["circle"]
            dx = m["imom"][0] - m["cmom"][0]
            dy = m["imom"][1] - m["cmom"][1]
            lines.append(
                "%5s @%.2f: 원 %.2f×%.2f σ %.3f/%.3f  중심차 %+.3f,%+.3f"
                "  틈 좌%.2f 우%.2f 상%.2f 하%.2f"
                % (name, s, cr - cl, cb - ct, m["cmom"][2], m["cmom"][3],
                   dx, dy, gl, gr, gt, gb))
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "report.txt"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.assertTrue(lines)


if __name__ == "__main__":
    unittest.main()
