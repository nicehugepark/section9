"""마크의 잉크 중심을 실화면 화소로 잰다 (REQ-20260910-009 5차 · 측정용).

시험이 아니라 **자**다. `tests/test_mark_swap.py`(리드가 쓴 회귀 계약)와 파일이
겹치지 않게 이 이름으로 둔다. 재는 것은 셋이다:

  ① 점의 여덟 얼굴(on·busy·off·sess·spawn·dot-stopped·mild·dot-held)과
     벨트의 두 얼굴(■ ▶)이 `.idmark` 13px 상자 안에서 **잉크 중심**을
     어디에 두는가 — 손이 얹히며 얼굴이 갈릴 때 자리가 뛰는지.
  ② 경과 시각의 시계 그림과 숫자가 세로로 같은 높이에 앉는가.
  ③ 마크와 식별자 사이의 잉크 틈.

상자(getBoundingClientRect)가 아니라 **그려진 화소**를 센다 — 상자가 대칭이어도
잉크는 한쪽에 몰릴 수 있고, 주인이 본 것은 잉크다.

실행: python3 tests/_probe_marks.py [스킨…]
"""
import base64
import json
import os
import struct
import subprocess
import sys
import time
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")

from cdpreal import WS, chrome_path, reclaim  # noqa: E402
from webasset import parts  # noqa: E402

OUT = os.path.join(REPO, "scratchpad", "r009marks")

FACES = [
    ("on", 'dot', 'livedot on'),
    ("busy", 'dot', 'livedot busy'),
    ("off", 'dot', 'livedot off'),
    ("sess", 'dot', 'livedot sess'),
    ("spawn", 'dot', 'livedot spawn'),
    ("stopped", 'dot', 'livedot dot-stopped'),
    ("mild", 'dot', 'livedot dot-stopped mild'),
    ("held", 'dot', 'livedot dot-held'),
    ("belt-stop", 'belt', 'stop'),
    ("belt-play", 'belt', 'play'),
]

GLY_STOP = ('<svg class="gly" viewBox="0 0 13 13" aria-hidden="true">'
            '<rect x="4" y="4" width="5" height="5" fill="currentColor"/></svg>')
GLY_PLAY = ('<svg class="gly" viewBox="0 0 13 13" aria-hidden="true">'
            '<path d="M4 2.5 L10 6.5 L4 10.5 Z" fill="currentColor"/></svg>')


def belt_html(kind):
    gly = GLY_STOP if kind == "stop" else GLY_PLAY
    return ('<span class="acts deedbelt"><button type="button"'
            ' class="deed %s ico" title="x">%s</button></span>'
            % ("stop" if kind == "stop" else "wake", gly))


def fixture_html():
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    rows = []
    for name, kind, cls in FACES:
        mark = ('<span class="%s"></span>' % cls) if kind == "dot" \
            else belt_html(cls)
        rows.append(
            '<div class="card" data-status="in-progress" data-face="%s"'
            ' style="--sc:var(--muted)">'
            '<div class="id"><span class="idmark">%s</span>'
            '<span class="idn">REQ-20260910-009</span>'
            '<span class="idr"><span class="idnow">'
            '<span class="elapsed">48m 25s</span>'
            '<span class="idact"><button type="button" class="pickdoc">'
            '이어 말하기</button></span></span></span></div></div>'
            % (name, mark))
    return ('<!doctype html><html lang="ko" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:8px;background:var(--bg)}'
            '.cards{width:320px}'
            # 손 얹힘 얼굴을 강제한다 — 캡처에는 포인터가 없다. visibility 는
            # 상자를 1px 도 안 옮기므로 재는 값이 달라지지 않는다.
            '.card .id .idmark .acts.deedbelt{visibility:visible}'
            # 맥박 링은 opacity 0 이 제 얼굴이다 — 애니메이션 중간 프레임이
            # 잉크로 잡히지 않게 멈춘다.
            '.livedot::after{animation:none!important}'
            '</style></head><body><div class="cards">%s</div></body></html>'
            % (css, "".join(rows)))


MEASURE_JS = """
(() => {
  const box = el => { if (!el) return null; const r = el.getBoundingClientRect();
    return {l: r.left, r: r.right, t: r.top, b: r.bottom}; };
  return [...document.querySelectorAll('.card')].map(c => ({
    face: c.dataset.face,
    idmark: box(c.querySelector('.idmark')),
    idn: box(c.querySelector('.idn')),
    ela: box(c.querySelector('.elapsed')),
  }));
})()
"""


# ---- PNG 해독 (stdlib 만) --------------------------------------------------
def png_pixels(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h, ct = 8, [], 0, 0, 6
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, _bd, ct = struct.unpack(">IIBB", chunk[:10])
        elif typ == b"IDAT":
            idat.append(chunk)
        elif typ == b"IEND":
            break
    raw = zlib.decompress(b"".join(idat))
    nch = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    stride = w * nch
    out = bytearray(w * h * nch)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                c = prev[i - nch] if i >= nch else 0
                b = prev[i]
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, nch, bytes(out)


def ink_stats(img, rect, scale, pad=(0, 0, 0, 0)):
    """crop 안의 잉크 무게중심·경계를 CSS px 로 낸다 (상자 왼쪽·위 기준)."""
    w, h, nch, px = img
    x0 = max(0, int(round((rect["l"] - pad[0]) * scale)))
    x1 = min(w, int(round((rect["r"] + pad[1]) * scale)))
    y0 = max(0, int(round((rect["t"] - pad[2]) * scale)))
    y1 = min(h, int(round((rect["b"] + pad[3]) * scale)))
    if x1 <= x0 or y1 <= y0:
        return None
    # 배경 = crop 안에서 가장 흔한 색
    tally = {}
    for y in range(y0, y1):
        base = y * w * nch
        for x in range(x0, x1):
            i = base + x * nch
            key = px[i] << 16 | px[i + 1] << 8 | px[i + 2]
            tally[key] = tally.get(key, 0) + 1
    bg = max(tally.items(), key=lambda kv: kv[1])[0]
    br, bgc, bb = bg >> 16, (bg >> 8) & 255, bg & 255
    sw = sx = sy = 0.0
    lo_x, hi_x, lo_y, hi_y = None, None, None, None
    cols, pix = {}, []
    for y in range(y0, y1):
        base = y * w * nch
        for x in range(x0, x1):
            i = base + x * nch
            d = max(abs(px[i] - br), abs(px[i + 1] - bgc), abs(px[i + 2] - bb))
            if d < 20:
                continue
            wgt = min(1.0, d / 140.0)
            sw += wgt
            sx += wgt * (x + 0.5)
            sy += wgt * (y + 0.5)
            cols[x] = cols.get(x, 0.0) + wgt
            pix.append((x, y, wgt))
            lo_x = x if lo_x is None else min(lo_x, x)
            hi_x = x if hi_x is None else max(hi_x, x)
            lo_y = y if lo_y is None else min(lo_y, y)
            hi_y = y if hi_y is None else max(hi_y, y)
    if sw == 0:
        return None
    ox, oy = rect["l"] - pad[0], rect["t"] - pad[2]
    return {
        "cx": sx / sw / scale - ox, "cy": sy / sw / scale - oy,
        "x0": lo_x / scale - ox, "x1": (hi_x + 1) / scale - ox,
        "y0": lo_y / scale - oy, "y1": (hi_y + 1) / scale - oy,
        "cols": cols, "pix": pix, "scale": scale, "ox": ox, "oy": oy,
    }


def write_png(path, w, h, rgb):
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgb[y * w * 3:(y + 1) * w * 3]
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        f.write(chunk(b"IEND", b""))


def zoom(img, x0, y0, x1, y1, k, grid=True):
    """잘라서 k배로 키운다 — 화소를 눈으로 보려는 것이라 보간하지 않는다."""
    w, h, nch, px = img
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    cw, ch = (x1 - x0) * k, (y1 - y0) * k
    out = bytearray(cw * ch * 3)
    for j in range(y1 - y0):
        for i in range(x1 - x0):
            s = ((y0 + j) * w + (x0 + i)) * nch
            r, g, b = px[s], px[s + 1], px[s + 2]
            for dy in range(k):
                base = ((j * k + dy) * cw + i * k) * 3
                for dx in range(k):
                    # 화소 격자를 옅은 선으로 남긴다 — 몇 화소 어긋났는지 세려면
                    # 경계가 보여야 한다.
                    if grid and k >= 6 and (dx == 0 or dy == 0):
                        v = (r * 6 + 255) // 7, (g * 6 + 255) // 7, \
                            (b * 6 + 255) // 7
                    else:
                        v = (r, g, b)
                    out[base + dx * 3:base + dx * 3 + 3] = bytes(v)
    return cw, ch, bytes(out)


def clock_parts(st, rows_px, img, rect, pad):
    """경과 칸의 잉크를 시계 그림 / 숫자로 가르고 각각의 세로 중심을 낸다.

    가르는 자리는 **맨 왼쪽 덩이가 끝나는 곳**이다 — 가장 넓은 빈 열로 가르면
    「48m」과 「25s」사이의 빈칸이 이겨 버린다.
    """
    if not st:
        return None
    sc, ox, oy = st["scale"], st["ox"], st["oy"]
    xs = sorted(st["cols"])
    cut = xs[-1] + 1
    for a, b in zip(xs, xs[1:]):
        if b - a > 1:
            cut = a + 1
            break
    left = [(x, y, w) for (x, y, w) in st["pix"] if x < cut]
    right = [(x, y, w) for (x, y, w) in st["pix"] if x >= cut]

    def cen(pts):
        if not pts:
            return None
        sw = sum(w for _, _, w in pts)
        return {
            "cx": sum(w * (x + .5) for x, _, w in pts) / sw / sc - ox,
            "cy": sum(w * (y + .5) for _, y, w in pts) / sw / sc - oy,
            "x0": min(x for x, _, _ in pts) / sc - ox,
            "x1": (max(x for x, _, _ in pts) + 1) / sc - ox,
            "y0": min(y for _, y, _ in pts) / sc - oy,
            "y1": (max(y for _, y, _ in pts) + 1) / sc - oy,
        }
    return {"cut": cut / sc - ox, "clock": cen(left), "num": cen(right)}


def measure(scale, skins, out_prefix):
    chrome = chrome_path()
    if not chrome:
        raise SystemExit("크롬 없음")
    win = "/mnt/c/" in chrome
    # 이름은 **실행마다 갈라야 한다** (REQ-20260910-052). 이 한 이름에서
    # 프로파일(--user-data-dir)·픽스처 html·reclaim() 대상이 모두 나오므로,
    # 고정 이름이면 같은 자를 둘이 동시에 돌릴 때 서로를 지운다: 한쪽의
    # rmtree 가 남의 프로파일을 지우고, 같은 DevToolsActivePort 를 읽어 남의
    # 브라우저에 붙고, finally 의 reclaim(marker) 이 marker 를 명령줄에 가진
    # headless 크롬을 **전부** 죽이고, os.remove(fix) 가 남이 읽으려던 픽스처를
    # 지운다. 실측: 배율 1.0 과 1.5 를 동시에 돌리면 1.5 쪽이 parts=None 을 냈다.
    # 이 스위트의 다른 CDP 시험 일곱(test_id_realscale·test_mark_swap·
    # test_board_sticky·test_hover_realscale·test_link_newtab·
    # test_doc_head_handles·test_graph_type_axis)이 이미 이 꼴이다.
    marker = "s9probe-marks-%d-%g" % (os.getpid(), scale)
    if win:
        base = "/mnt/c/Temp"
        os.makedirs(base, exist_ok=True)
        prof_wsl = os.path.join(base, marker)
        prof_arg = "C:\\Temp\\" + marker
        fix = os.path.join(base, marker + ".html")
        url = "file:///C:/Temp/" + marker + ".html"
    else:
        # 러너는 실행마다 임시 루트를 세워 TMPDIR 을 그리로 돌린다 — /tmp 를
        # 박아 쓰면 프로파일이 그 루트 밖에 남아 회수되지 않는다.
        base = os.environ.get("TMPDIR", "/tmp")
        prof_wsl = prof_arg = os.path.join(base, marker)
        fix = os.path.join(base, marker + ".html")
        url = "file://" + fix
    import shutil
    shutil.rmtree(prof_wsl, ignore_errors=True)
    with open(fix, "w", encoding="utf-8") as f:
        f.write(fixture_html())
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu",
         "--user-data-dir=" + prof_arg, "--no-first-run",
         "--no-default-browser-check", "--disable-extensions",
         "--remote-debugging-port=0",
         "--force-device-scale-factor=%g" % scale,
         "--window-size=380,760", url],
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
        time.sleep(0.4)
        os.makedirs(OUT, exist_ok=True)
        for skin in skins:
            ws.eval("document.documentElement.dataset.skin=%r" % skin)
            time.sleep(0.15)
            boxes = ws.eval(MEASURE_JS)
            r = ws.call("Page.captureScreenshot", format="png",
                        fromSurface=True)
            raw = base64.b64decode(r["data"])
            with open(os.path.join(
                    OUT, "%s-%s-x%g.png" % (out_prefix, skin, scale)),
                    "wb") as f:
                f.write(raw)
            img = png_pixels(raw)
            # 눈으로 보는 자리 — 마크 열과 경과 칸을 8배로 떠 둔다.
            m0, mN = boxes[0]["idmark"], boxes[-1]["idmark"]
            zx0 = int((m0["l"] - 5) * scale)
            zx1 = int((m0["r"] + 5) * scale)
            zy0 = int((m0["t"] - 4) * scale)
            zy1 = int((mN["b"] + 4) * scale)
            cw, ch, buf = zoom(img, zx0, zy0, zx1, zy1, 8)
            write_png(os.path.join(
                OUT, "zoom-mark-%s-x%g.png" % (skin, scale)), cw, ch, buf)
            e0 = boxes[0]["ela"]
            cw, ch, buf = zoom(img, int((e0["l"] - 2) * scale),
                               int((e0["t"] - 4) * scale),
                               int((e0["r"] + 2) * scale),
                               int((e0["b"] + 4) * scale), 8)
            write_png(os.path.join(
                OUT, "zoom-ela-%s-x%g.png" % (skin, scale)), cw, ch, buf)
            for b in boxes:
                mk = ink_stats(img, b["idmark"], scale)
                ela = ink_stats(img, b["ela"], scale, pad=(1, 1, 3, 3))
                rows.append({
                    "skin": skin, "scale": scale, "face": b["face"],
                    "idmark": b["idmark"], "idn_l": b["idn"]["l"],
                    "mark": mk, "ela": ela,
                    "parts": clock_parts(ela, None, img, b["ela"], (1, 1, 3, 3)),
                })
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


HOVER_HTML_ROW = (
    '<div class="card" data-status="in-progress" data-face="hover"'
    ' style="--sc:var(--muted)">'
    '<div class="id"><span class="idmark">%s%s</span>'
    '<span class="idn">REQ-20260910-009</span>'
    '<span class="idr"><span class="idnow">'
    '<span class="elapsed">48m 25s</span>'
    '<span class="idact"><button type="button" class="pickdoc">'
    '이어 말하기</button></span></span></span></div>'
    '<div class="t">마크 자리 점검용 제목 줄</div>'
    '<div class="m"><span class="badge">nice</span></div></div>')


def _diff_box(a, b, rect, scale):
    """두 캡처가 달라진 자리의 경계를 `.idmark` 왼끝 기준 CSS px 로 낸다."""
    w, h, nch, pa = a
    _, _, _, pb = b
    lo_x = hi_x = lo_y = hi_y = None
    for y in range(h):
        base = y * w * nch
        for x in range(w):
            i = base + x * nch
            if max(abs(pa[i] - pb[i]), abs(pa[i + 1] - pb[i + 1]),
                   abs(pa[i + 2] - pb[i + 2])) < 8:
                continue
            lo_x = x if lo_x is None else min(lo_x, x)
            hi_x = x if hi_x is None else max(hi_x, x)
            lo_y = y if lo_y is None else min(lo_y, y)
            hi_y = y if hi_y is None else max(hi_y, y)
    if lo_x is None:
        return "달라진 화소 없음 (칠이 서지 않는다)"
    return "x %.2f..%.2f · y %.2f..%.2f (지름 %.2f×%.2f)" % (
        lo_x / scale - rect["l"], (hi_x + 1) / scale - rect["l"],
        lo_y / scale - rect["t"], (hi_y + 1) / scale - rect["t"],
        (hi_x + 1 - lo_x) / scale, (hi_y + 1 - lo_y) / scale)


def hover_fixture():
    """손이 실제로 얹히는 얼굴을 재는 판 — `visibility` 를 손으로 켜지 않는다.
    칠(13px 원)은 포인터가 손잡이 위에 있을 때만 서므로 CDP 로 얹어야 한다."""
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    rows = (HOVER_HTML_ROW % ('<span class="livedot on"></span>',
                              belt_html("stop"))
            + HOVER_HTML_ROW % ('<span class="livedot dot-stopped"></span>',
                                belt_html("play")))
    return ('<!doctype html><html lang="ko" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:10px;background:var(--bg)}'
            '.cards{width:300px}'
            '.livedot::after{animation:none!important}'
            '</style></head><body><div class="cards">%s</div></body></html>'
            % (css, rows))


def hover_shots(scale, skins):
    """실포인터를 마크 위에 얹고 그 얼굴을 8배로 뜬다."""
    import shutil
    chrome = chrome_path()
    if not chrome:
        raise SystemExit("크롬 없음")
    win = "/mnt/c/" in chrome
    marker = "s9probe-hover-%d-%g" % (os.getpid(), scale)   # measure() 와 같은 까닭
    if win:
        base = "/mnt/c/Temp"
        os.makedirs(base, exist_ok=True)
        prof_wsl, prof_arg = os.path.join(base, marker), "C:\\Temp\\" + marker
        fix = os.path.join(base, marker + ".html")
        url = "file:///C:/Temp/" + marker + ".html"
    else:
        base = os.environ.get("TMPDIR", "/tmp")
        prof_wsl = prof_arg = os.path.join(base, marker)
        fix = os.path.join(base, marker + ".html")
        url = "file://" + fix
    shutil.rmtree(prof_wsl, ignore_errors=True)
    with open(fix, "w", encoding="utf-8") as f:
        f.write(hover_fixture())
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu",
         "--user-data-dir=" + prof_arg, "--no-first-run",
         "--no-default-browser-check", "--disable-extensions",
         "--remote-debugging-port=0",
         "--force-device-scale-factor=%g" % scale,
         "--window-size=380,300", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws, out = None, []
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
        time.sleep(0.4)
        os.makedirs(OUT, exist_ok=True)
        for skin in skins:
            ws.eval("document.documentElement.dataset.skin=%r" % skin)
            time.sleep(0.15)
            boxes = ws.eval(MEASURE_JS)
            b = boxes[0]
            mx = (b["idmark"]["l"] + b["idmark"]["r"]) / 2
            my = (b["idmark"]["t"] + b["idmark"]["b"]) / 2
            # 실포인터 — CSS 를 흉내 내지 않는다. 좌표는 CSS px 다.
            # 먼저 **카드 위·손잡이 밖**에 얹는다(식별자 끝) — 벨트는 서고 칠은
            # 안 선 얼굴. 두 캡처의 화소 차이가 곧 칠의 경계다(색을 가정하지
            # 않는다 — browser-verify 「차이로 찾아라」).
            ws.call("Input.dispatchMouseEvent", type="mouseMoved",
                    x=b["idn"]["r"] - 2, y=my, buttons=0)
            time.sleep(0.3)
            base_img = png_pixels(base64.b64decode(ws.call(
                "Page.captureScreenshot", format="png",
                fromSurface=True)["data"]))
            ws.call("Input.dispatchMouseEvent", type="mouseMoved",
                    x=mx, y=my, buttons=0)
            time.sleep(0.35)
            raw = base64.b64decode(ws.call(
                "Page.captureScreenshot", format="png",
                fromSurface=True)["data"])
            img = png_pixels(raw)
            print("%-8s x%g  칠의 경계: %s" % (
                skin, scale, _diff_box(base_img, img, b["idmark"], scale)))
            card = ws.eval(
                "(()=>{const r=document.querySelector('.card')"
                ".getBoundingClientRect();"
                "return {l:r.left,r:r.right,t:r.top,b:r.bottom};})()")
            cw, ch, buf = zoom(img, int((card["l"] - 4) * scale),
                               int((card["t"] - 3) * scale),
                               int((card["l"] + 74) * scale),
                               int((card["b"] + 3) * scale), 6)
            path = os.path.join(
                OUT, "hover-%s-x%g.png" % (skin, scale))
            write_png(path, cw, ch, buf)
            out.append(path)
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


def main():
    args = sys.argv[1:]
    if args and args[0] == "--hover":
        skins = args[1:] or ["ledger", "calm", "grid"]
        for sc in (1.0, 1.25):
            for p in hover_shots(sc, skins):
                print(p)
        return
    skins = args or ["ledger"]
    scales = [1.0, 1.25, 1.5]
    allrows = []
    for sc in scales:
        allrows += measure(sc, skins, "marks")
    print("face          skin      x    ink-cx  ink-cy   ink-x0..x1   "
          "ink-y0..y1  gap-to-id")
    for r in allrows:
        m = r["mark"]
        if not m:
            print("%-13s %-8s %.2f  (잉크 없음)" % (r["face"], r["skin"],
                                                 r["scale"]))
            continue
        gap = r["idn_l"] - (r["idmark"]["l"] + m["x1"])
        print("%-13s %-8s %.2f  %6.2f  %6.2f  %5.2f..%5.2f  %5.2f..%5.2f  %5.2f"
              % (r["face"], r["skin"], r["scale"], m["cx"], m["cy"],
                 m["x0"], m["x1"], m["y0"], m["y1"], gap))
    print()
    print("== 경과 시각 (첫 행) — 그림 · 숫자의 잉크 (경과 칸 왼/위 기준) ==")
    print("skin      x     clock cy  y0..y1        num cy  y0..y1        "
          "dy      clock x1  num x0  틈")
    for r in allrows:
        if r["face"] != "on":
            continue
        p = r["parts"]
        if not p or not p["clock"] or not p["num"]:
            continue
        c, n = p["clock"], p["num"]
        print("%-8s %.2f  %6.2f  %5.2f..%5.2f  %6.2f  %5.2f..%5.2f  %+5.2f   "
              "%5.2f  %5.2f  %5.2f"
              % (r["skin"], r["scale"], c["cy"], c["y0"], c["y1"],
                 n["cy"], n["y0"], n["y1"], c["cy"] - n["cy"],
                 c["x1"], n["x0"], n["x0"] - c["x1"]))
    with open(os.path.join(OUT, "rows.json"), "w") as f:
        json.dump([{k: v for k, v in r.items() if k not in ("mark", "ela")}
                   for r in allrows], f, default=str)


if __name__ == "__main__":
    main()
