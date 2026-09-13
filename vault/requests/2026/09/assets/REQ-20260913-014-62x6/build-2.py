# -*- coding: utf-8 -*-
"""section9 브랜드 마크 생성기 (REQ-20260913-014-62x6 · 2차 — 공안9과 · 타치코마).

정체성: section9 = 공안9과(Public Security Section 9), 타치코마 = 그 조직의
AI 다족 전차. 마크는 그 둘을 떠올리게 하되 원작 그림을 베끼지 않는다 —
실루엣을 옮기지 않고 16 눈금 위의 사각형·원으로만 짓는다.

기하는 16 눈금 위의 정수다. 16·32·48·180·192·512 가 전부 16 의 정수배라
어느 크기에서도 같은 모양이 나오고, 사각형 좌표는 전부 짝수라 비정수
배율(1.25·1.5)에서 반올림이 양쪽에 똑같이 걸린다.

도형: ("r", x, y, w, h, 색) 사각형 · ("c", cx, cy, r, 색) 원. 뒤가 앞을 덮는다.
"""
import os
import struct
import zlib

INK = (0x14, 0x15, 0x18)      # --text (잉크)
PAPER = (0xfa, 0xfa, 0xf8)    # --bg (종이)
# 강조색: 새 색을 짓지 않았다. 어두운 판 위의 --c-open 값(tokens.css 다크 블록)
# 그대로다 — 잉크 #141518 위 대비 5.8:1 로 16px 에서도 파랑으로 읽힌다.
BLUE = (0x5b, 0x8d, 0xef)

U = 16.0                       # 눈금
SUB = 4                        # 원의 세로 표본 (가로는 해석적으로 정확)


# --- 후보 셋 -------------------------------------------------------------
# 바탕은 셋 다 같다: 9 의 둥근 머리 자리를 렌즈 눈으로 본다. 9 는 9 로 읽히고,
# 그 속에 앉은 눈이 아는 사람에게만 말을 건다. 다리·몸통까지 그리면 노골적이
# 되므로 단서는 하나로 줄였다 — 기둥이 판 바닥 가까이 내려가 다리처럼 선다.
#
# A 「렌즈 9」(권고) — 속이 둥근 렌즈. 마크에서 둥근 것은 이 눈 하나뿐이다.
A = [
    ("r", 0, 0, 16, 16, INK),        # 잉크 판
    ("r", 4, 2, 8, 2, PAPER),        # 머리 윗변
    ("r", 4, 2, 2, 6, PAPER),        # 머리 왼변
    ("r", 4, 8, 8, 2, PAPER),        # 배 아래
    ("r", 10, 2, 2, 12, PAPER),      # 기둥 — 배를 지나 바닥까지 (다리)
    ("c", 8, 6, 2, BLUE),            # 렌즈 — 9 의 속에 앉은 눈
]

# B 「각진 렌즈 9」 — 같은 9, 속이 네모난 렌즈. 16px 에서 더 또렷한 대신
#   「눈」보다 「칸」으로 읽힐 위험이 있다.
B = [
    ("r", 0, 0, 16, 16, INK),
    ("r", 4, 2, 8, 2, PAPER),
    ("r", 4, 2, 2, 6, PAPER),
    ("r", 4, 8, 8, 2, PAPER),
    ("r", 10, 2, 2, 12, PAPER),
    ("r", 6, 4, 4, 4, BLUE),
]

# C 「눈 둘」 — 렌즈 눈 두 개와 다리 셋. 숫자가 없고 생김새만 남은 안.
#   선을 어디에 그을지 보려고 만든 대조군이다(노골적인 쪽 — 권고하지 않는다).
C = [
    ("r", 0, 0, 16, 16, INK),
    ("c", 5, 6, 3, PAPER), ("c", 5, 6, 1.5, BLUE),     # 왼 렌즈
    ("c", 11, 6, 3, PAPER), ("c", 11, 6, 1.5, BLUE),   # 오른 렌즈
    ("r", 2, 11, 2, 3, PAPER),                          # 다리 셋
    ("r", 7, 11, 2, 3, PAPER),
    ("r", 12, 11, 2, 3, PAPER),
]
CAND = {"a": A, "b": B, "c": C}


# --- 래스터 (사각형은 정확 면적 · 원은 가로 해석적 + 세로 4표본) --------
def raster(shapes, n):
    """n x n RGB 바이트 행 목록."""
    px = U / n
    edges = [i * px for i in range(n + 1)]
    rows = []
    for j in range(n):
        y0, y1 = edges[j], edges[j + 1]
        buf = [[0.0, 0.0, 0.0] for _ in range(n)]
        for sp in shapes:
            col = sp[-1]
            if sp[0] == "r":
                _, rx, ry, rw, rh, _c = sp
                oy = min(y1, ry + rh) - max(y0, ry)
                if oy <= 0:
                    continue
                i_lo = max(0, int(rx / px) - 1)
                i_hi = min(n, int((rx + rw) / px) + 2)
                for i in range(i_lo, i_hi):
                    ox = min(edges[i + 1], rx + rw) - max(edges[i], rx)
                    if ox <= 0:
                        continue
                    a = (ox * oy) / (px * px)
                    if a > 1.0:
                        a = 1.0
                    b = buf[i]
                    b[0] += (col[0] - b[0]) * a
                    b[1] += (col[1] - b[1]) * a
                    b[2] += (col[2] - b[2]) * a
            else:
                _, cx, cy, r, _c = sp
                cov = {}
                for k in range(SUB):
                    yy = y0 + (k + 0.5) * (y1 - y0) / SUB
                    dy = yy - cy
                    if abs(dy) >= r:
                        continue
                    hx = (r * r - dy * dy) ** 0.5
                    xa, xb = cx - hx, cx + hx
                    i_lo = max(0, int(xa / px))
                    i_hi = min(n, int(xb / px) + 1)
                    for i in range(i_lo, i_hi):
                        ox = min(edges[i + 1], xb) - max(edges[i], xa)
                        if ox <= 0:
                            continue
                        cov[i] = cov.get(i, 0.0) + (ox / px) / SUB
                for i, a in cov.items():
                    if a > 1.0:
                        a = 1.0
                    b = buf[i]
                    b[0] += (col[0] - b[0]) * a
                    b[1] += (col[1] - b[1]) * a
                    b[2] += (col[2] - b[2]) * a
        row = bytearray()
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


def shapes_svg(shapes, indent="  "):
    out = []
    for sp in shapes:
        col = hexc(sp[-1])
        if sp[0] == "r":
            _, x, y, w, h, _c = sp
            out.append('%s<rect x="%g" y="%g" width="%g" height="%g"'
                       ' fill="%s"/>' % (indent, x, y, w, h, col))
        else:
            _, cx, cy, r, _c = sp
            out.append('%s<circle cx="%g" cy="%g" r="%g" fill="%s"/>'
                       % (indent, cx, cy, r, col))
    return "\n".join(out)


def svg_mark(shapes, size=16, label="section9"):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"'
            ' width="%d" height="%d" role="img" aria-label="%s">\n'
            '  <title>%s</title>\n%s\n</svg>\n'
            % (size, size, label, label, shapes_svg(shapes)))


def svg_logo(shapes):
    """마크 + 워드마크. 글꼴은 기기의 것을 쓰되 폭은 textLength 로 못박는다
    — 글꼴이 달라도 로고가 차지하는 자리는 같아야 한다. 워드마크의 잉크는
    어두운 화면에서 뒤집는다(README 를 어두운 화면으로 읽는 사람)."""
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
            % (hexc(INK), shapes_svg(shapes, "    "), hexc(BLUE)))


def build(key, outdir):
    sh = CAND[key]
    os.makedirs(outdir, exist_ok=True)

    def w(name, data):
        open(os.path.join(outdir, name), "wb").write(data)

    w("mark.svg", svg_mark(sh, 16).encode())
    w("favicon.svg", svg_mark(sh, 32).encode())
    w("logo.svg", svg_logo(sh).encode())
    pngs = [(n, png(raster(sh, n), n)) for n in (16, 32, 48)]
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
