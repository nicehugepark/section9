# -*- coding: utf-8 -*-
"""section9 마크 11차 — 입체 렌즈 (REQ-20260914-001-62x6). build5.py 를 이어받는다.

주인(10:24): 「저 타치코마 눈을 움직이게 할 수는 없나? 그냥 흰 원이 아니라 정말
타치코마의 눈처럼 입체감 있게 움직였으면」. 참고 영상(0:37)은 **참고**이지 사양이
아니다(주인 정정 10:31) — 색은 이 제품의 잉크·종이 안에서 쓴다.

바뀐 것 둘.
① **렌즈가 평면이 아니다.** 흰 원 하나였던 자리가 세 겹이다 — 얇은 테(rim) ·
   위가 밝고 아래로 어두워지는 돔 음영 · 왼쪽 위의 은은한 반사 하나. 색은
   종이(#fafaf8)에서 파생한 무채 계열뿐이고 새 색을 들이지 않는다.
② **mark.svg 가 작은 새김을 쓴다.** 이 파일은 index.html·guide.html 에서 **18px**
   로만 그려지는데 종전에는 큰 판(점 지름 8%)이 실려 있었다 — 18px 에서 점 하나가
   1.04 화소라 눈이 안 보였고, 그래서 「그냥 흰 원」으로 읽혔다. 파비콘과 같은
   새김(12.5%)으로 바꾸면 머리·탭·가이드가 한 얼굴이 된다.
   큰 판(8%)은 48px 이상으로만 그려지는 PNG 아이콘과 logo.svg 에 남는다.
"""
import os, struct, sys

INK, PAPER, RIM = "#141518", "#fafaf8", "#b9b6ac"
HERE = os.path.dirname(os.path.abspath(__file__))
def r2(v): return round(v, 2)

# 돔 — 위가 밝고 아래로 갈수록 어둡다. objectBoundingBox 라 크기가 달라도 한 벌로 쓴다.
DEFS = '''
  <defs>
    <radialGradient id="s9dome" cx="50%" cy="34%" r="74%">
      <stop offset="0" stop-color="#fdfcf8"/><stop offset=".46" stop-color="#f7f5ef"/>
      <stop offset=".78" stop-color="#e6e4db"/><stop offset="1" stop-color="#c6c4ba"/>
    </radialGradient>
    <radialGradient id="s9lit" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".85"/>
      <stop offset=".55" stop-color="#ffffff" stop-opacity=".30"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>'''


def lens(cx, cy, R, flat=False, rim=True):
    """렌즈 — 테 · 돔 음영 · 반사. flat 이면 종전의 평면 원(견주기용).

    rim=False 는 글자 속의 눈을 위한 것이다 — o 와 9 의 **획이 이미 테**라,
    거기에 테를 한 겹 더 두르면 5px 짜리 눈이 회색 고리로 흐려진다."""
    if flat:
        return '\n  <circle cx="%s" cy="%s" r="%s" fill="%s"/>' % (cx, cy, R, PAPER)
    rim = r2(R * 0.042) if rim else 0        # 테 — 반지름의 4.2%
    hx, hy = r2(cx - R * 0.28), r2(cy - R * 0.40)
    head = ('\n  <circle cx="%s" cy="%s" r="%s" fill="%s"/>' % (cx, cy, R, RIM)) if rim else ""
    return (head
            + '\n  <circle cx="%s" cy="%s" r="%s" fill="url(#s9dome)"/>'
            '\n  <ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="url(#s9lit)"'
            ' transform="rotate(-22 %s %s)"/>'
            % (cx, cy, r2(R - rim), hx, hy,
               r2(R * 0.40), r2(R * 0.26), hx, hy))


def pupil(cx, cy, dot, side, drop, wrap=False):
    """점 셋 — 정삼각, 무게중심이 렌즈 중심보다 drop 아래. 부모 014 의 값 그대로."""
    h = side * 0.8660254
    pts = [(cx - side / 2, cy + drop - h / 3), (cx + side / 2, cy + drop - h / 3),
           (cx, cy + drop + 2 * h / 3)]
    body = "".join('\n    <circle cx="%s" cy="%s" r="%s" fill="%s"/>'
                   % (r2(x), r2(y), dot, INK) for x, y in pts)
    if wrap:
        return '\n  <g class="pupil">%s\n  </g>' % body
    return body.replace("\n    ", "\n  ")


# 새김 둘 — 작은 판(16~32px 로 그려지는 것) · 큰 판(48px 이상)
SMALL = dict(R=24, dot=3.0, side=10.0, drop=6.80)    # 점 지름 12.5% · 무리 14.2% 아래
LARGE = dict(R=23, dot=1.85, side=5.6, drop=7.00)    # 점 지름 8.0% · 무리 15.2% 아래


def mark(small=True, flat=False, wrap=False):
    c = SMALL if small else LARGE
    return ('\n  <rect width="64" height="64" fill="%s"/>%s%s'
            % (INK, lens(32, 32, c["R"], flat),
               pupil(32, 32, c["dot"], c["side"], c["drop"], wrap)))


def svg(body, size=64, note="", defs=True):
    n = '\n  <!-- %s -->' % note if note else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            'width="%d" height="%d" role="img" aria-label="section9">'
            '\n  <title>section9</title>%s%s%s\n</svg>\n'
            % (size, size, n, DEFS if defs else "", body))


# ---- 워드마크 — 글자는 건드리지 않는다 (부모 014 의 값 그대로) -------------
FONT = ("system-ui,-apple-system,'Segoe UI',Roboto,"
        "'Helvetica Neue',Arial,sans-serif")

def logo_svg():
    tile = mark(small=False).replace("\n  ", "\n    ")
    # o 와 9 의 속 — 같은 렌즈를 작게. 속이 작아 점도 작다(속 지름의 8%).
    o = lens(209.0, 39.0, 5.6, rim=False) + pupil(209.0, 39.0, 0.45, 3.36, 1.68)
    nine = lens(265.2, 30.0, 5.2, rim=False) + pupil(265.2, 30.0, 0.42, 3.12, 1.56)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 290 70" width="290" '
            'height="70" role="img" aria-label="section9">\n  <title>section9</title>\n'
            '  <style>\n'
            '    /* 밝은 쪽 색은 presentation attribute 로 둔다 — 인라인 SVG 의 style 은\n'
            '       문서 전체에 걸려, 한 쪽에 여러 벌이 실리면 마지막 것이 앞을 덮는다. */\n'
            '    @media (prefers-color-scheme:dark){.s9logo{color:#e8e8e4}}\n'
            '  </style>%s\n  <g class="s9logo" color="#141518">\n'
            '  <g transform="translate(8 7) scale(0.875)">%s\n  </g>\n'
            '  <text x="88" y="50" textLength="190" font-family="%s" font-size="48"\n'
            '        font-weight="700" fill="currentColor">section<tspan>9</tspan></text>\n'
            '  <!-- o 의 속을 눈으로 — 글자는 건드리지 않는다 -->%s\n'
            '  <!-- 9 의 고리 속을 눈으로 -->%s\n  </g>\n</svg>\n'
            % (DEFS, tile, FONT, o, nine))


def page(body, size, defs=True):
    return ('<!doctype html><meta charset="utf-8">'
            '<style>html,body{margin:0;padding:0;background:#141518;overflow:hidden}'
            'svg{display:block}</style>' + svg(body, size, defs=defs))


def write_ico(pngs, out):
    imgs = [(n, open(p, "rb").read()) for n, p in pngs]
    off = 6 + 16 * len(imgs); ents, datas = [], []
    for n, data in imgs:
        ents.append(struct.pack("<BBBBHHII", n & 0xFF, n & 0xFF, 0, 0, 1, 32, len(data), off))
        off += len(data); datas.append(data)
    open(out, "wb").write(struct.pack("<HHH", 0, 1, len(imgs)) + b"".join(ents) + b"".join(datas))


def emit_pages():
    """구울 그림의 원판 — 작은 판은 ico 16/32/48, 큰 판은 180/192/512."""
    for n in (16, 32, 48):
        open(os.path.join(HERE, "p-s-%d.html" % n), "w", encoding="utf-8").write(
            page(mark(True), n))
    for n in (180, 192, 512):
        open(os.path.join(HERE, "p-l-%d.html" % n), "w", encoding="utf-8").write(
            page(mark(False), n))
    print("pages ok")


def install(assets):
    open(os.path.join(assets, "mark.svg"), "w", encoding="utf-8").write(
        svg(mark(True), 64, "렌즈 — 테·돔 음영·반사 위에 잉크 점 셋. 18px 로 그려지므로 작은 새김"))
    open(os.path.join(assets, "favicon.svg"), "w", encoding="utf-8").write(
        svg(mark(True), 64, "탭 크기(16~32)용 — 머리글 마크와 같은 얼굴"))
    open(os.path.join(assets, "logo.svg"), "w", encoding="utf-8").write(logo_svg())
    print("svg 셋 실었다")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pages"
    if cmd == "pages":
        emit_pages()
    elif cmd == "ico":
        write_ico([(16, os.path.join(sys.argv[2], "ico16.png")),
                   (32, os.path.join(sys.argv[2], "ico32.png")),
                   (48, os.path.join(sys.argv[2], "ico48.png"))],
                  os.path.join(sys.argv[3], "favicon.ico"))
        print("ico ok")
    elif cmd == "inline":
        # 머리글에 넣을 인라인 SVG — 같은 얼굴, 점 셋만 <g class="pupil"> 로 묶는다
        print(svg(mark(True, wrap=True), 18).replace(
            '<svg xmlns', '<svg class="mark" xmlns'))
    else:
        install(sys.argv[2] if len(sys.argv) > 2
                else os.path.expanduser("~/section9/web/assets"))
