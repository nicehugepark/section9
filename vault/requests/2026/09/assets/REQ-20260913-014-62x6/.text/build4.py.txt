# -*- coding: utf-8 -*-
"""section9 마스코트 — 9차 (REQ-20260913-014-62x6). 납작한 삽화풍 앱 아이콘.

앞 회차 반려: 원·타원 몇 개로 줄인 추상이 「눈 둘 달린 외계인」으로 읽혔다.
이번에는 **줄이지 않는다** — 참고판의 비율을 자로 재듯 옮긴다(트레이싱은 하지
않는다). 얼굴이 아니라 **계기**로 읽히게 하는 것이 핵심이다:
앞면 가운데에 큰 렌즈 **하나**, 그 위 좌우에 작은 센서 둘. 눈 둘을 크게 두면
얼굴이 되고, 얼굴이 되면 외계인이 된다.

  F 정면 · T 3/4 — 두 각도.
  큰 판(512·192·180·48) = 충실한 판, 작은 판(32·16) = 돔 + 큰 렌즈 + 발 자국.
"""
import os, struct, sys

INK   = "#141518"
PAPER = "#fafaf8"
BLUE  = "#5b8def"      # 몸
BLUE_D= "#3f6cc4"      # 그늘 · 패널 선
HERE = os.path.dirname(os.path.abspath(__file__))
BG = f'<rect width="64" height="64" fill="{INK}"/>'
def r2(v): return round(v, 2)

# ---- 부품 --------------------------------------------------------------
def dome(cx, cy, rx, ry, bot, fill=BLUE, corner=4):
    """옆으로 넓은 돔 — 위는 둥글고 아래는 평평하다."""
    return (f'\n  <path d="M{r2(cx-rx)} {cy} A{rx} {ry} 0 0 1 {r2(cx+rx)} {cy}'
            f' L{r2(cx+rx)} {r2(bot-corner)} Q{r2(cx+rx)} {bot} {r2(cx+rx-corner)} {bot}'
            f' L{r2(cx-rx+corner)} {bot} Q{r2(cx-rx)} {bot} {r2(cx-rx)} {r2(bot-corner)} Z"'
            f' fill="{fill}"/>')

def leg(a, k, f, w=4.6, foot=3.4, joint=True):
    """다리 — 몸통 옆에서 나와 관절에서 꺾이고 끝은 둥근 포드 발."""
    s = [f'\n  <path d="M{a[0]} {a[1]} L{k[0]} {k[1]} L{f[0]} {f[1]}" fill="none"'
         f' stroke="{BLUE}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>']
    if joint:
        s.append(f'\n  <circle cx="{k[0]}" cy="{k[1]}" r="{r2(w*0.56)}" fill="{BLUE_D}"/>')
    s.append(f'\n  <circle cx="{f[0]}" cy="{f[1]}" r="{foot}" fill="{BLUE}"/>')
    s.append(f'\n  <circle cx="{f[0]}" cy="{r2(f[1]+0.3)}" r="{r2(foot*0.44)}" fill="{BLUE_D}"/>')
    return "".join(s)

def arm(a, e, w=3.4):
    return (f'\n  <path d="M{a[0]} {a[1]} L{e[0]} {e[1]}" fill="none" stroke="{BLUE}"'
            f' stroke-width="{w}" stroke-linecap="round"/>'
            f'\n  <circle cx="{e[0]}" cy="{e[1]}" r="{r2(w*0.72)}" fill="{BLUE_D}"/>')

def big_lens(cx, cy, r, glint=True):
    """큰 렌즈 — 짙은 테 · 동심 테 · 밝은 유리 · 조리개 · 비스듬한 유리 빗금.
    동그란 하이라이트를 쓰면 눈동자로 읽혀 얼굴이 된다(실측). 빗금이라야 유리다."""
    s = [f'\n  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{INK}"/>',
         f'\n  <circle cx="{cx}" cy="{cy}" r="{r2(r*0.82)}" fill="{BLUE_D}"/>',
         f'\n  <circle cx="{cx}" cy="{cy}" r="{r2(r*0.68)}" fill="{PAPER}"/>',
         f'\n  <circle cx="{cx}" cy="{cy}" r="{r2(r*0.34)}" fill="{BLUE_D}"/>']
    if glint:
        # 빗금은 유리 고리 **안**에 둔다 — 조리개를 물면 조리개가 쉼표처럼 이지러진다
        s.append(f'\n  <rect x="{r2(cx-r*0.63)}" y="{r2(cy-r*0.085)}" width="{r2(r*0.26)}"'
                 f' height="{r2(r*0.17)}" rx="{r2(r*0.085)}" fill="{PAPER}"'
                 f' transform="rotate(-38 {cx} {cy})"/>')
    return "".join(s)


def lamp(cx, cy, w=9.6, h=6.4):
    """사각 램프 — 둥근 램프 둘은 「눈」으로 읽혀 얼굴이 된다. 사각이라야 계기다."""
    return (f'\n  <rect x="{r2(cx-w/2)}" y="{r2(cy-h/2)}" width="{w}" height="{h}"'
            f' rx="{r2(h*0.34)}" fill="{INK}"/>'
            f'\n  <rect x="{r2(cx-w/2+1.2)}" y="{r2(cy-h/2+1.2)}" width="{r2(w-2.4)}"'
            f' height="{r2(h-2.4)}" rx="{r2(h*0.22)}" fill="{PAPER}"/>')


def skirt(x0, x1, y0, bot, corner=4):
    """섀시 띠 — 몸통 아래를 곧은 띠로 끊는다(기계의 이음선)."""
    return (f'\n  <path d="M{x0} {y0} L{x1} {y0} L{x1} {r2(bot-corner)}'
            f' Q{x1} {bot} {r2(x1-corner)} {bot} L{r2(x0+corner)} {bot}'
            f' Q{x0} {bot} {x0} {r2(bot-corner)} Z" fill="{BLUE_D}"/>')


def hip(cx, cy, w=9, h=6.2):
    return (f'\n  <rect x="{r2(cx-w/2)}" y="{r2(cy-h/2)}" width="{w}" height="{h}"'
            f' rx="2.4" fill="{BLUE_D}"/>')

def sensor(cx, cy, r):
    return (f'\n  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{INK}"/>'
            f'\n  <circle cx="{cx}" cy="{cy}" r="{r2(r*0.72)}" fill="{PAPER}"/>'
            f'\n  <circle cx="{cx}" cy="{cy}" r="{r2(r*0.36)}" fill="{BLUE}"/>')

# ---- 정면 --------------------------------------------------------------
def front(simple=False):
    if simple:
        # 탭 새김. 48 의 충실한 판과 너무 벌어지지 않게 램프 둘과 섀시 띠는 남긴다 —
        # 32 에서 이 둘이 없으면 「외눈 버섯」으로 읽힌다.
        return (BG
            + f'\n  <path d="M14 44 L10 53" fill="none" stroke="{BLUE}" stroke-width="7.5"'
              f' stroke-linecap="round"/><circle cx="10" cy="53" r="4.2" fill="{BLUE}"/>'
            + f'\n  <path d="M50 44 L54 53" fill="none" stroke="{BLUE}" stroke-width="7.5"'
              f' stroke-linecap="round"/><circle cx="54" cy="53" r="4.2" fill="{BLUE}"/>'
            + dome(32, 30, 23, 15, 46, corner=8)
            + skirt(9, 55, 41, 46, corner=8)
            + f'\n  <rect x="13.6" y="21" width="9" height="5.2" rx="2" fill="{PAPER}"/>'
            + f'\n  <rect x="41.4" y="21" width="9" height="5.2" rx="2" fill="{PAPER}"/>'
            + f'\n  <circle cx="32" cy="33" r="9.6" fill="{PAPER}"/>'
            + f'\n  <circle cx="32" cy="33" r="4.4" fill="{BLUE_D}"/>')

    return (BG
        # 등 뒤의 포드 — 위에 얹으면 모자처럼 읽힌다. 어깨 뒤로 둘로 나눈다
        + f'\n  <circle cx="14" cy="22" r="6.4" fill="{BLUE_D}"/>'
        + f'\n  <circle cx="50" cy="22" r="6.4" fill="{BLUE_D}"/>'
        # 다리 넷 — 몸통 옆에서 나와 관절에서 꺾이고 끝은 둥근 포드 발
        + leg((14, 36), (7, 31), (10, 51))
        + leg((23, 41), (17, 38), (20, 55))
        + leg((41, 41), (47, 38), (44, 55))
        + leg((50, 36), (57, 31), (54, 51))
        # 팔 둘
        + arm((27, 41.5), (24, 47.5)) + arm((37, 41.5), (40, 47.5))
        # 몸통 — 가로 42 · 세로 26 (1.6 : 1)
        + dome(32, 29, 21, 13, 42)
        + skirt(11, 53, 36.6, 42)
        + hip(14.1, 33.6) + hip(49.9, 33.6)
        # 위 해치
        + f'\n  <ellipse cx="32" cy="21.5" rx="12" ry="5.2" fill="{BLUE_D}"/>'
        # 램프 둘 — 돔 위쪽에. 큰 렌즈와 한 줄에 두면 얼굴이 된다
        + lamp(17.5, 23) + lamp(46.5, 23)
        # 큰 렌즈 하나 — 앞면 가운데
        + big_lens(32, 32, 9.5))


# ---- 3/4 ---------------------------------------------------------------
def three_q(simple=False):
    if simple:
        return (BG
            + f'\n  <path d="M13 43 L9 52" fill="none" stroke="{BLUE}" stroke-width="7.5"'
              f' stroke-linecap="round"/><circle cx="9" cy="52" r="4.2" fill="{BLUE}"/>'
            + f'\n  <path d="M48 45 L52 54" fill="none" stroke="{BLUE}" stroke-width="7.5"'
              f' stroke-linecap="round"/><circle cx="52" cy="54" r="4.2" fill="{BLUE}"/>'
            + f'\n  <circle cx="44" cy="20" r="10" fill="{BLUE_D}"/>'
            + dome(30, 30, 22, 15, 46, corner=8)
            + skirt(8, 52, 41, 46, corner=8)
            + f'\n  <rect x="10.5" y="22" width="8.4" height="5" rx="2" fill="{PAPER}"/>'
            + f'\n  <rect x="36" y="19.5" width="8.4" height="5" rx="2" fill="{PAPER}"/>'
            + f'\n  <circle cx="27" cy="33" r="9.6" fill="{PAPER}"/>'
            + f'\n  <circle cx="27" cy="33" r="4.4" fill="{BLUE_D}"/>')

    return (BG
        + f'\n  <circle cx="45" cy="19" r="9.2" fill="{BLUE_D}"/>'
        + leg((13, 36), (6, 32), (9, 50))
        + leg((22, 41), (16, 39), (19, 56))
        + leg((40, 40), (46, 37), (43, 52), w=4.2, foot=3.0)
        + leg((48, 35), (55, 31), (52, 47), w=4.2, foot=3.0)
        + arm((25, 41.5), (21, 47.5)) + arm((35, 42), (38, 48))
        + dome(30, 29, 21, 13, 42)
        + skirt(9, 51, 36.6, 42)
        + hip(12.1, 33.6) + hip(47.9, 33.2)
        + f'\n  <ellipse cx="33" cy="21" rx="11.5" ry="5" fill="{BLUE_D}"/>'
        + lamp(14.5, 24, 8.6, 6.0) + lamp(40, 21.5, 9.2, 6.2)
        + big_lens(27, 32, 9.5))


BODY = {"F": front, "T": three_q}
NAME = {"F": "정면", "T": "3/4"}

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
    off = 6 + 16 * len(imgs); ents, datas = [], []
    for n, data in imgs:
        ents.append(struct.pack("<BBBBHHII", n & 0xFF, n & 0xFF, 0, 0, 1, 32, len(data), off))
        off += len(data); datas.append(data)
    open(out, "wb").write(struct.pack("<HHH", 0, 1, len(imgs)) + b"".join(ents) + b"".join(datas))

def emit_pages():
    for pick in ("F", "T"):
        for simple in (False, True):
            tag = pick + ("s" if simple else "")
            for n in (512, 192, 180, 48, 32, 16):
                open(os.path.join(HERE, f"n-{tag}-{n}.html"), "w", encoding="utf-8").write(
                    page(BODY[pick](simple), n))

def install(pick, assets):
    open(os.path.join(assets, "mark.svg"), "w", encoding="utf-8").write(
        svg(BODY[pick](False), 64, f"마스코트 「{NAME[pick]}」 — 충실한 판(48 이상). 단순판은 favicon.svg"))
    open(os.path.join(assets, "favicon.svg"), "w", encoding="utf-8").write(
        svg(BODY[pick](True), 64, "탭 크기(16~32)용 단순판 — 돔 + 큰 렌즈 + 발 자국"))
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
