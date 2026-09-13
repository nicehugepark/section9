# -*- coding: utf-8 -*-
"""section9 브랜드 마크 — 6차 최종 (REQ-20260913-014-62x6).

P 「통통한 9」(권고·실은 안) : 살 붙은 덩어리 9, 속이 렌즈.
Q 「발 달린 9」(대안)        : 조금 날씬한 9, 꼬리 끝이 둥근 발.

렌즈는 **파란 원 + 흰 반사 둘**이다 — 흰자도 잉크 동공도 없다(5차의 안구가
반려된 자리). 반사가 둘이면 유리알로 읽혀 생기가 돌고, 렌즈를 머리 중심보다
1 아래에 앉히면 테가 위 9 · 옆 8 · 아래 7 이 되어 살짝 올려다보는 얼굴이 된다.

광학 새김 두 벌: 큰 판(48 이상, 반사 둘) · 작은 판(16·32, 반사 빼고 획을 굵힘).

    python3 build2.py P ~/section9/web/assets
"""
import os, struct, sys

INK, PAPER, BLUE = "#141518", "#fafaf8", "#5b8def"
HERE = os.path.dirname(os.path.abspath(__file__))
BG = f'<rect width="64" height="64" fill="{INK}"/>'
GLINT_BIG, GLINT_SML = (-3.4, -3.4, 3.2), (3.0, 2.6, 1.5)


def nine(br, tw, ex, ey, lr, foot=0, glints=True, bcx=32, bcy=24, ctrl=44, ldy=1):
    cx = round(bcx + br - tw / 2, 2)      # 꼬리 오른끝 = 머리 오른끝 (둘 다 종이라 이음매가 없다)
    ly = bcy + ldy
    s = [f'\n  {BG}',
         f'\n  <circle cx="{bcx}" cy="{bcy}" r="{br}" fill="{PAPER}"/>',
         f'\n  <path d="M{cx} {bcy} Q{cx} {ctrl} {ex} {ey}" fill="none" stroke="{PAPER}"'
         f' stroke-width="{tw}" stroke-linecap="round"/>']
    if foot:
        s.append(f'\n  <circle cx="{ex}" cy="{ey}" r="{foot}" fill="{PAPER}"/>')
    s.append(f'\n  <circle cx="{bcx}" cy="{ly}" r="{lr}" fill="{BLUE}"/>')
    if glints:
        for dx, dy, r in (GLINT_BIG, GLINT_SML):
            s.append(f'\n  <circle cx="{round(bcx+dx,2)}" cy="{round(ly+dy,2)}" r="{r}" fill="{PAPER}"/>')
    return "".join(s)


def body_P(small=False):
    """통통한 9 — 머리 r17.5, 살 붙은 획."""
    if small:   # 탭 새김: 획을 굵히고 꼬리를 세워 온전한 화소를 덮게, 반사는 뺀다
        return nine(17.5, 14, 26, 51, 10, glints=False)
    return nine(17.5, 12.5, 24, 52, 9.5)


def body_Q(small=False):
    """발 달린 9 — 조금 날씬하고 꼬리 끝이 둥근 발."""
    if small:
        return nine(17, 13, 26, 51, 10, foot=7.2, glints=False)
    return nine(17, 11, 24.5, 52, 9.5, foot=6.6)


BODY = {"P": body_P, "Q": body_Q}
NAME = {"P": "통통한 9", "Q": "발 달린 9"}


def svg(body, size=64, note=""):
    n = f'\n  <!-- {note} -->' if note else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            f'width="{size}" height="{size}" role="img" aria-label="section9">'
            f'\n  <title>section9</title>{n}{body}\n</svg>\n')


def logo_svg(pick):
    inner = BODY[pick](False).replace("\n  ", "\n    ")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 150 32" width="150" height="32" role="img" aria-label="section9">
  <title>section9</title>
  <style>
    .wm{{fill:{INK}}}
    @media (prefers-color-scheme:dark){{.wm{{fill:#e8e8e4}}}}
  </style>
  <g transform="scale(0.5)">{inner}
  </g>
  <text class="wm" x="40" y="23" font-family="system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif" font-size="21" font-weight="700" letter-spacing="0.3">section<tspan fill="{BLUE}">9</tspan></text>
</svg>
'''


def page(body, size):
    return ('<!doctype html><meta charset="utf-8">'
            '<style>html,body{margin:0;padding:0;background:#141518;overflow:hidden}'
            'svg{display:block}</style>' + svg(body, size))


def write_ico(pngs, out):
    imgs = [(n, open(p, "rb").read()) for n, p in pngs]
    off = 6 + 16 * len(imgs)
    ents, datas = [], []
    for n, data in imgs:
        ents.append(struct.pack("<BBBBHHII", n & 0xFF, n & 0xFF, 0, 0, 1, 32, len(data), off))
        off += len(data); datas.append(data)
    open(out, "wb").write(struct.pack("<HHH", 0, 1, len(imgs)) + b"".join(ents) + b"".join(datas))


def emit_pages():
    for pick in ("P", "Q"):
        for small in (False, True):
            tag = pick + ("s" if small else "")
            open(os.path.join(HERE, f"q-{tag}.svg"), "w", encoding="utf-8").write(svg(BODY[pick](small)))
            for n in (512, 192, 180, 48, 32, 16):
                open(os.path.join(HERE, f"q-{tag}-{n}.html"), "w", encoding="utf-8").write(
                    page(BODY[pick](small), n))


def install(pick, assets):
    open(os.path.join(assets, "mark.svg"), "w", encoding="utf-8").write(
        svg(BODY[pick](False), 64, f"{NAME[pick]} — 큰 판(48 이상). 작은 판은 favicon.svg"))
    open(os.path.join(assets, "favicon.svg"), "w", encoding="utf-8").write(
        svg(BODY[pick](True), 64, "탭 크기(16~32)용 광학 새김 — 획을 굵히고 반사를 뺐다"))
    open(os.path.join(assets, "logo.svg"), "w", encoding="utf-8").write(logo_svg(pick))
    print("svg 셋 실었다:", NAME[pick])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pages"
    if cmd == "pages":
        emit_pages(); print("pages ok")
    elif cmd == "ico":
        write_ico([(16, os.path.join(sys.argv[2], "ico16.png")),
                   (32, os.path.join(sys.argv[2], "ico32.png")),
                   (48, os.path.join(sys.argv[2], "ico48.png"))],
                  os.path.join(sys.argv[3], "favicon.ico"))
        print("ico ok")
    else:
        install(cmd, sys.argv[2] if len(sys.argv) > 2
                else os.path.expanduser("~/section9/web/assets"))
