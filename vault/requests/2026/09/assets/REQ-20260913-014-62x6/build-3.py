# -*- coding: utf-8 -*-
"""section9 브랜드 마크 — 최종 두 안과 산출물 (REQ-20260913-014-62x6).

E 「눈 9」  : 파란 홍채가 9 의 고리, 잉크 동공이 속, 종이 꼬리.  (권고 · 실은 안)
F 「채운 9」: 획이 아니라 덩어리로 그린 9, 속(counter)이 렌즈.  (대안)

두 안 모두 **광학 크기 두 벌**이다 — 큰 판(48 이상, 캐치라이트 있음)과
작은 판(16·32, 획을 굵히고 캐치라이트를 뺌). 같은 마크의 두 새김이지
다른 마크가 아니다.

    python3 build.py E   # 또는 F — 그 안을 web/assets 에 싣는다
"""
import json, os, struct, sys

INK, PAPER, BLUE = "#141518", "#fafaf8", "#5b8def"
HERE = os.path.dirname(os.path.abspath(__file__))
BG = f'<rect width="64" height="64" fill="{INK}"/>'


def body_E(small=False):
    """눈 9 — 홍채 r17 이 고리, 동공이 속, 꼬리는 종이."""
    w  = 14 if small else 10            # 꼬리 획 — 큰 판은 10, 작은 판은 14.
    # 종이(흰)는 잉크 위에서 같은 폭이어도 파랑보다 굵어 보인다(irradiation).
    # 홍채의 테는 8 이므로 꼬리를 11 로 두면 꼬리가 마크를 끌어간다 — 10 에서 둘의
    # 잉크 무게가 같아 보인다. 작은 판은 판독이 먼저라 12.5 로 굵힌다.
    pr = 10 if small else 9             # 동공
    # 꼬리 오른끝을 홍채 오른끝(49)에 **맞닿게** 두면 둘이 접선으로 만나, 홍채를
    # 감싸는 실낱 같은 초승달이 생기고 그 끝이 0 으로 가늘어진다 — 48 이하에서
    # 회색 얼룩으로 뭉갠다(실측). 오른끝을 47.5 에 두면 홍채의 테두리를 24° 로
    # 가로질러 나오므로 꼬리가 처음부터 제 폭을 갖는다. 더 왼쪽(35°·43°)도
    # 실낱은 없어지지만 꼬리가 고리에서 떨어져 9 가 덜 읽힌다 — 24° 가 경계다.
    cx = round(47.5 - w / 2, 2)
    # 대각선 획은 화소를 반씩만 덮어 16 화소에서 회색으로 뭉갠다(실측: 획 12.5 는
    # 흰 속심이 없다). 작은 판은 획을 14 로 굵히고 꼬리 끝을 (28,51) 로 세워
    # 온전한 화소를 덮게 한다 — 같은 마크의 다른 새김이다.
    ex = 28 if small else 25.5
    ey = 51 if small else 51.5
    hi = "" if small else f'\n  <circle cx="28.9" cy="20.9" r="2.6" fill="{PAPER}"/>'
    return (f'\n  {BG}'
            f'\n  <path d="M{cx} 24 Q{cx} 44 {ex} {ey}" fill="none" stroke="{PAPER}"'
            f' stroke-width="{w}" stroke-linecap="round"/>'
            f'\n  <circle cx="32" cy="24" r="17" fill="{BLUE}"/>'
            f'\n  <circle cx="32" cy="24" r="{pr}" fill="{INK}"/>' + hi)


def body_F(small=False):
    """채운 9 — 원반 + 꼬리 덩어리의 합집합, 속이 렌즈."""
    w  = 12.5 if small else 11
    cr = 8.5  if small else 8
    cx = round(49 - w / 2, 2)
    ex = 25.0
    hi = "" if small else f'\n  <circle cx="28.8" cy="20.8" r="2.1" fill="{PAPER}"/>'
    return (f'\n  {BG}'
            f'\n  <circle cx="32" cy="24" r="17" fill="{PAPER}"/>'
            f'\n  <path d="M{cx} 24 Q{cx} 44 {ex} 51.5" fill="none" stroke="{PAPER}"'
            f' stroke-width="{w}" stroke-linecap="round"/>'
            f'\n  <circle cx="32" cy="24" r="{cr}" fill="{BLUE}"/>' + hi)


BODY = {"E": body_E, "F": body_F}
NAME = {"E": "눈 9", "F": "채운 9"}


def svg(body, size=64, note=""):
    n = f'\n  <!-- {note} -->' if note else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            f'width="{size}" height="{size}" role="img" aria-label="section9">'
            f'\n  <title>section9</title>{n}{body}\n</svg>\n')


def logo_svg(pick):
    """마크 + 워드마크. 9 만 파랑 — 마크의 렌즈와 같은 색."""
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
    """정확한 화소로 그리기 위한 한 장짜리 페이지 — s9 shot 이 이것을 찍는다."""
    return ('<!doctype html><meta charset="utf-8">'
            '<style>html,body{margin:0;padding:0;background:#141518;overflow:hidden}'
            'svg{display:block}</style>'
            + svg(body, size))


def write_ico(png_paths, out):
    """ICO = 머리 6바이트 + 항목 16바이트씩 + PNG 자료 그대로."""
    imgs = [(n, open(p, "rb").read()) for n, p in png_paths]
    head = struct.pack("<HHH", 0, 1, len(imgs))
    off = 6 + 16 * len(imgs)
    ents, datas = [], []
    for n, data in imgs:
        ents.append(struct.pack("<BBBBHHII", n & 0xFF, n & 0xFF, 0, 0, 1, 32,
                                len(data), off))
        off += len(data)
        datas.append(data)
    with open(out, "wb") as f:
        f.write(head + b"".join(ents) + b"".join(datas))


def emit_pages():
    """비교판과 크기별 페이지를 scratchpad 에 낸다."""
    for pick in ("E", "F"):
        for small in (False, True):
            tag = pick + ("s" if small else "")
            open(os.path.join(HERE, f"fin-{tag}.svg"), "w", encoding="utf-8").write(
                svg(BODY[pick](small)))
            for n in (512, 192, 180, 48, 32, 16):
                open(os.path.join(HERE, f"p-{tag}-{n}.html"), "w", encoding="utf-8").write(
                    page(BODY[pick](small), n))


def install(pick, assets):
    big, small = BODY[pick](False), BODY[pick](True)
    open(os.path.join(assets, "mark.svg"), "w", encoding="utf-8").write(
        svg(big, 64, f"{NAME[pick]} — 큰 판(48 이상). 작은 판은 favicon.svg"))
    open(os.path.join(assets, "favicon.svg"), "w", encoding="utf-8").write(
        svg(small, 64, "탭 크기(16~32)용 광학 새김 — 획을 굵히고 캐치라이트를 뺐다"))
    open(os.path.join(assets, "logo.svg"), "w", encoding="utf-8").write(logo_svg(pick))
    print("svg 셋 실었다:", NAME[pick])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pages"
    if cmd == "pages":
        emit_pages(); print("pages ok")
    elif cmd == "ico":
        shots = sys.argv[2]
        write_ico([(16, os.path.join(shots, "ico16.png")),
                   (32, os.path.join(shots, "ico32.png")),
                   (48, os.path.join(shots, "ico48.png"))],
                  os.path.join(sys.argv[3], "favicon.ico"))
        print("ico ok")
    else:
        install(cmd, sys.argv[2] if len(sys.argv) > 2 else
                os.path.expanduser("~/section9/web/assets"))
