# -*- coding: utf-8 -*-
"""section9 브랜드 마크 생성기 (REQ-20260913-014-62x6).

기하는 전부 16 눈금 위의 정수다 — 16·32·48·192·512 는 16 의 정수배라
어느 크기에서도 같은 모양이 나오고, 비정수 배율(1.25·1.5)에서는 좌우가
대칭이라 반올림이 양쪽에 똑같이 걸린다. 색은 제품의 토큰 셋뿐이다.
"""
import os
import struct
import zlib

INK = (0x14, 0x15, 0x18)      # --text
PAPER = (0xfa, 0xfa, 0xf8)    # --bg
LIVE = (0x16, 0xa3, 0x4a)     # --dot-live

U = 16.0                       # 눈금

# --- 후보 셋 -------------------------------------------------------------
# (x, y, w, h, color)  — 뒤에 오는 것이 앞을 덮는다
A = [                                    # 「기록된 9」 — 네모난 속을 가진 9
    (0, 0, 16, 16, INK),
    (4, 2, 8, 2, PAPER),                 # 머리
    (4, 2, 2, 8, PAPER),                 # 왼쪽
    (4, 8, 8, 2, PAPER),                 # 배 아래
    (10, 2, 2, 10, PAPER),               # 오른쪽 — 배를 지나 꼬리까지
    (10, 12, 2, 2, LIVE),                # 꼬리 끝 — 지금 쓰이고 있는 자리
]
B = [                                    # 「칸 아홉」 — 3×3
    (0, 0, 16, 16, PAPER),
] + [(x, y, 4, 4, INK) for y in (0, 6, 12) for x in (0, 6, 12)
     if not (x == 12 and y == 12)] + [(12, 12, 4, 4, LIVE)]
C = [                                    # 「괘선 위의 9」
    (0, 0, 16, 16, INK),
    (4, 2, 8, 2, PAPER),
    (4, 2, 2, 8, PAPER),
    (4, 8, 8, 2, PAPER),
    (10, 2, 2, 10, PAPER),
    (2, 12, 12, 2, PAPER),               # 장부의 괘선
    (10, 12, 4, 2, LIVE),                # 기둥이 닿은 자리부터
]
CAND = {"a": A, "b": B, "c": C}


# --- 래스터 (정확 면적 커버리지) ----------------------------------------
def raster(shapes, n):
    """n×n RGB 바이트. 화소마다 각 사각형과 겹친 넓이로 섞는다."""
    s = n / U
    px = 1.0 / s
    rows = []
    # 행/열 경계를 미리 눈금 좌표로
    edges = [i * px for i in range(n + 1)]
    for j in range(n):
        y0, y1 = edges[j], edges[j + 1]
        row = bytearray()
        acc = [(0, 0, 0)] * n
        for i in range(n):
            acc[i] = (0.0, 0.0, 0.0)
        buf = [[0.0, 0.0, 0.0] for _ in range(n)]
        for (rx, ry, rw, rh, col) in shapes:
            oy = min(y1, ry + rh) - max(y0, ry)
            if oy <= 0:
                continue
            for i in range(n):
                x0, x1 = edges[i], edges[i + 1]
                ox = min(x1, rx + rw) - max(x0, rx)
                if ox <= 0:
                    continue
                a = (ox * oy) / (px * px)
                if a > 1:
                    a = 1.0
                b = buf[i]
                b[0] += (col[0] - b[0]) * a
                b[1] += (col[1] - b[1]) * a
                b[2] += (col[2] - b[2]) * a
        for i in range(n):
            b = buf[i]
            row += bytes((int(b[0] + 0.5), int(b[1] + 0.5), int(b[2] + 0.5)))
        rows.append(bytes(row))
    return rows


def png(rows, n):
    raw = b"".join(b"\x00" + r for r in rows)
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def ico(pngs):
    """PNG 들을 ICO 그릇에 담는다 — 머리 6바이트 + 항목 16바이트씩."""
    out = struct.pack("<HHH", 0, 1, len(pngs))
    off = 6 + 16 * len(pngs)
    body = b""
    for n, data in pngs:
        out += struct.pack("<BBBBHHII", n & 0xff, n & 0xff, 0, 0, 1, 32,
                           len(data), off)
        off += len(data)
        body += data
    return out + body


# --- SVG ------------------------------------------------------------------
def hexc(c):
    return "#%02x%02x%02x" % c


def svg_mark(shapes, size=16, label="section9"):
    r = "\n".join(
        '  <rect x="%g" y="%g" width="%g" height="%g" fill="%s"/>'
        % (x, y, w, h, hexc(c)) for (x, y, w, h, c) in shapes)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"'
            ' width="%d" height="%d" role="img" aria-label="%s">\n'
            '  <title>%s</title>\n%s\n</svg>\n'
            % (size, size, label, label, r))


def svg_logo(shapes):
    """마크 + 워드마크. 글꼴은 기기의 것을 쓰되 폭은 textLength 로 못박는다
    — 글꼴이 달라도 로고가 차지하는 자리는 같아야 한다. 워드마크의 잉크는
    어두운 화면에서 뒤집는다(README 를 어두운 화면으로 읽는 사람)."""
    r = "\n".join(
        '    <rect x="%g" y="%g" width="%g" height="%g" fill="%s"/>'
        % (x, y, w, h, hexc(c)) for (x, y, w, h, c) in shapes)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 130 32"'
            ' width="130" height="32" role="img" aria-label="section9">\n'
            '  <title>section9</title>\n'
            '  <style>\n'
            '    .wm{fill:%s}\n'
            '    @media (prefers-color-scheme:dark){.wm{fill:#e8e8e4}}\n'
            '  </style>\n'
            '  <g transform="translate(0 4) scale(1.5)">\n%s\n  </g>\n'
            '  <text class="wm" x="34" y="23" textLength="92"'
            ' lengthAdjust="spacing" font-family="system-ui,-apple-system,'
            "'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
            '" font-size="21" font-weight="700" letter-spacing="0.3"'
            '>section<tspan fill="%s">9</tspan></text>\n</svg>\n'
            % (hexc(INK), r, hexc(LIVE)))


def build(key, outdir):
    sh = CAND[key]
    os.makedirs(outdir, exist_ok=True)
    w = lambda name, data, mode="wb": open(
        os.path.join(outdir, name), mode).write(data)
    w("mark.svg", svg_mark(sh, 16).encode())
    w("favicon.svg", svg_mark(sh, 32).encode())
    w("logo.svg", svg_logo(sh).encode())
    pngs = []
    for n in (16, 32, 48):
        pngs.append((n, png(raster(sh, n), n)))
    w("favicon.ico", ico(pngs))
    for n, name in ((192, "icon-192.png"), (512, "icon-512.png"),
                    (180, "apple-touch-icon.png")):
        w(name, png(raster(sh, n), n))
    return outdir


if __name__ == "__main__":
    import sys
    key = sys.argv[1] if len(sys.argv) > 1 else "a"
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    print(build(key, out))
