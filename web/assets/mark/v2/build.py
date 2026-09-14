# -*- coding: utf-8 -*-
"""section9 마크 v2 「박스 없음」 (REQ-20260914-002-62x6). v1 의 build.py 를 이어받는다.

주인(2026-09-14 11:02): 「검은 색 네모칸이 배경과 어울리지 않는다. 사각형 박스를
없애보는 건 어때? 다른 스킨에서도 어울릴 수 있도록.」

**렌즈만 남긴다.** 잉크 타일이 하던 일 둘을 다른 것이 나눠 맡는다 —
  · 밝은 배경에서 렌즈를 세우는 일 → **잉크 테**(지름의 2.4%)와 짙어진 돔
    가장자리가 나눠 맡는다. 테만 굵히면 큰 크기에서 그린 윤곽선처럼 보인다
    (시안 A~D 를 18·32·64·110px 로 찍어 고른 값이다).
  · 어두운 배경에서 렌즈를 세우는 일 → **돔의 밝기**가 맡는다(테는 배경에 묻힌다).
타일이 없어진 만큼 렌즈를 키워(반지름 24 → 30) 머리글에서의 잉크 무게를 지킨다.

**얼굴의 비율은 v1 그대로다** — 점 셋은 돔 지름에 대한 비율로 잡으므로 렌즈가
커지면 같이 커진다(작은 새김 13.05% · 큰 새김 8.4%).

앱 아이콘(192·512·apple-touch)만 타일을 남긴다 — 플랫폼이 꽉 찬 사각을 기대하고,
홈 화면에서 배경이 무엇일지 우리가 모른다. 그 타일 위의 렌즈는 v2 의 큰 렌즈다.
"""
import os, struct, sys

INK = "#141518"
HERE = os.path.dirname(os.path.abspath(__file__))
def r2(v): return round(v, 2)

DEFS = '''
  <defs>
    <radialGradient id="s9dome" cx="50%" cy="32%" r="74%">
      <stop offset="0" stop-color="#fdfcf8"/><stop offset=".44" stop-color="#f6f4ee"/>
      <stop offset=".76" stop-color="#e0ddd2"/><stop offset="1" stop-color="#a9a496"/>
    </radialGradient>
    <radialGradient id="s9lit" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".85"/>
      <stop offset=".55" stop-color="#ffffff" stop-opacity=".30"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>'''

# 점 셋 — 돔 지름에 대한 비율(v1 에서 주인이 고른 얼굴을 그대로 옮긴 값)
SMALL = dict(dot=.1305, side=.2175, drop=.1479)   # 16~32px 로 그려지는 자리
LARGE = dict(dot=.0840, side=.1271, drop=.1589)   # 48px 이상


def lens(cx, cy, R, rim_pct=.024, rim=True):
    """렌즈 — 잉크 테 · 돔 음영 · 반사. rim=False 는 글자 속의 눈(획이 이미 테다)."""
    w = r2(R * 2 * rim_pct) if rim else 0
    d = r2(R - w)
    hx, hy = r2(cx - d * 0.28), r2(cy - d * 0.40)
    head = ('\n  <circle cx="%s" cy="%s" r="%s" fill="%s"/>' % (cx, cy, R, INK)) if rim else ""
    return (head
            + '\n  <circle cx="%s" cy="%s" r="%s" fill="url(#s9dome)"/>'
              '\n  <ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="url(#s9lit)"'
              ' transform="rotate(-22 %s %s)"/>'
              % (cx, cy, d, hx, hy, r2(d * 0.40), r2(d * 0.26), hx, hy))


def pupil(cx, cy, R, carve, rim_pct=.024, rim=True, wrap=False):
    w = R * 2 * rim_pct if rim else 0
    dd = (R - w) * 2                       # 돔 지름 — 비율의 기준
    dot, side, drop = r2(dd * carve["dot"] / 2), dd * carve["side"], dd * carve["drop"]
    h = side * 0.8660254
    pts = [(cx - side / 2, cy + drop - h / 3), (cx + side / 2, cy + drop - h / 3),
           (cx, cy + drop + 2 * h / 3)]
    body = "".join('\n    <circle cx="%s" cy="%s" r="%s" fill="%s"/>'
                   % (r2(x), r2(y), dot, INK) for x, y in pts)
    if wrap:
        return '\n  <g class="pupil">%s\n  </g>' % body
    return body.replace("\n    ", "\n  ")


def mark(R=30, carve=None, tile=False, wrap=False):
    carve = carve or SMALL
    plate = ('\n  <rect width="64" height="64" fill="%s"/>' % INK) if tile else ""
    return plate + lens(32, 32, R) + pupil(32, 32, R, carve, wrap=wrap)


def svg(body, size=64, note=""):
    n = '\n  <!-- %s -->' % note if note else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            'width="%d" height="%d" role="img" aria-label="section9">'
            '\n  <title>section9</title>%s%s%s\n</svg>\n' % (size, size, n, DEFS, body))


FONT = ("system-ui,-apple-system,'Segoe UI',Roboto,"
        "'Helvetica Neue',Arial,sans-serif")

def logo_svg():
    tile = (lens(32, 32, 30) + pupil(32, 32, 30, LARGE)).replace("\n  ", "\n    ")
    o = lens(209.0, 39.0, 5.6, rim=False) + pupil(209.0, 39.0, 5.6, LARGE, rim=False)
    nine = lens(265.2, 30.0, 5.2, rim=False) + pupil(265.2, 30.0, 5.2, LARGE, rim=False)
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


def page(body, size, bg="none"):
    fill = "background:%s" % bg if bg != "none" else "background:transparent"
    return ('<!doctype html><meta charset="utf-8">'
            '<style>html,body{margin:0;padding:0;%s;overflow:hidden}'
            'svg{display:block}</style>' % fill + svg(body, size))


def write_ico(pngs, out):
    imgs = [(n, open(p, "rb").read()) for n, p in pngs]
    off = 6 + 16 * len(imgs); ents, datas = [], []
    for n, data in imgs:
        ents.append(struct.pack("<BBBBHHII", n & 0xFF, n & 0xFF, 0, 0, 1, 32, len(data), off))
        off += len(data); datas.append(data)
    open(out, "wb").write(struct.pack("<HHH", 0, 1, len(imgs)) + b"".join(ents) + b"".join(datas))


def emit_pages():
    """탭 새김(16·32·48)은 흰 바탕·검은 바탕 두 벌로 굽는다 — 두 장에서 알파를
    되찾아 **투명한** PNG 를 만든다(브라우저 캡처에는 투명이 없다)."""
    for n in (16, 32, 48):
        for tag, bg in (("w", "#ffffff"), ("k", "#000000")):
            open(os.path.join(HERE, "p-%s-%d.html" % (tag, n)), "w", encoding="utf-8").write(
                page(mark(30, SMALL), n, bg))
    for n in (180, 192, 512):      # 앱 아이콘 — 타일을 남긴다
        open(os.path.join(HERE, "p-app-%d.html" % n), "w", encoding="utf-8").write(
            page(mark(27, LARGE, tile=True), n, INK))
    print("pages ok")


def install(assets):
    open(os.path.join(assets, "mark.svg"), "w", encoding="utf-8").write(
        svg(mark(30, SMALL), 64, "렌즈만 — 잉크 테와 돔 음영이 배경 없이도 렌즈를 세운다. 18px 새김"))
    open(os.path.join(assets, "favicon.svg"), "w", encoding="utf-8").write(
        svg(mark(30, SMALL), 64, "탭 크기(16~32)용 — 머리글 마크와 같은 얼굴, 박스 없음"))
    open(os.path.join(assets, "logo.svg"), "w", encoding="utf-8").write(logo_svg())
    print("svg 셋 실었다 (v2 · 박스 없음)")


def header_svg():
    """머리글에 박히는 조각 — 이름은 옆의 글자가 이미 말하므로 **읽어 주지 않는다**
    (aria-hidden). role/aria-label 을 달면 화면낭독기가 「section9 section9」로 두 번
    읽고, 껍데기를 훑는 자리에서도 그 글자가 마크 안에 또 있게 된다."""
    return (svg(mark(30, SMALL, wrap=True), 18)
            .replace('<svg xmlns', '<svg class="mark" xmlns')
            .replace(' role="img" aria-label="section9"', ' aria-hidden="true" focusable="false"')
            .replace("\n  <title>section9</title>", ""))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pages"
    if cmd == "pages":
        emit_pages()
    elif cmd == "ico":
        write_ico([(n, os.path.join(sys.argv[2], "ico%d.png" % n)) for n in (16, 32, 48)],
                  os.path.join(sys.argv[3], "favicon.ico"))
        print("ico ok")
    elif cmd == "header":
        print(header_svg())
    else:
        install(sys.argv[2] if len(sys.argv) > 2
                else os.path.expanduser("~/section9/web/assets"))
