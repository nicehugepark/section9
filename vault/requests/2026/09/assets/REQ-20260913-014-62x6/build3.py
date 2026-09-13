# -*- coding: utf-8 -*-
"""section9 마스코트 마크 — 8차 최종 (REQ-20260913-014-62x6).

참고 그림(타치코마)에서 읽은 형태 언어 넷을 원·타원·둥근 선으로 추상했다.
어떤 그림도 따라 그리지 않았다.
  ① 둥근 파란 몸통 — 키보다 폭이 넓고 위는 돔
  ② 앞면의 큰 렌즈 둘 — 종이 원 + 짙은 파랑 심 + 반사 하나
  ③ 짧고 벌어진 다리 — 몸통 **옆**에서 나와 무릎에서 꺾인다(거미 전차의 뼈대)
  ④ 통통한 아기 비율

A 「전신」(권고·실은 안) : 다리 넷으로 선 마스코트.
B 「얼굴」(대안)         : 몸통과 렌즈를 키워 판을 채우고 다리는 둘만.

광학 새김 두 벌 — 큰 판(48 이상: 다리 넷·심·반사)과 작은 판(16·32: 다리 둘·
민 렌즈·굵은 획). 16 화소에 남는 것은 몸통 + 큰 눈 둘 + 다리 자국이다.

    python3 build3.py A ~/section9/web/assets
"""
import os, struct, sys

INK, PAPER, BLUE = "#141518", "#fafaf8", "#5b8def"
BLUE_D = "#3f6cc4"                      # 렌즈 심에만 쓰는 짙은 파랑
HERE = os.path.dirname(os.path.abspath(__file__))
BG = f'<rect width="64" height="64" fill="{INK}"/>'


def _body(rx, ry, cy, sh, bot, fill=BLUE, r=7):
    """몸통 — 위는 돔, 아래 모서리는 r 만큼 둥글다."""
    return (f'\n  <path d="M{32-rx} {cy} A{rx} {ry} 0 0 1 {32+rx} {cy} L{32+rx} {sh}'
            f' Q{32+rx} {bot} {32+rx-r} {bot} L{32-rx+r} {bot} Q{32-rx} {bot} {32-rx} {sh} Z"'
            f' fill="{fill}"/>')


def _leg(pts, w, foot):
    d = "M" + " L".join(f"{x} {y}" for x, y in pts)
    return (f'\n  <path d="{d}" fill="none" stroke="{BLUE}" stroke-width="{w}"'
            f' stroke-linecap="round" stroke-linejoin="round"/>'
            f'\n  <circle cx="{pts[-1][0]}" cy="{pts[-1][1]}" r="{foot}" fill="{BLUE}"/>')


def _eyes(ex, cy, r, core=None, glint=0):
    s = []
    for sx in (-1, 1):
        cx = 32 + sx * ex
        s.append(f'\n  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{PAPER}"/>')
        if core:
            s.append(f'\n  <circle cx="{cx}" cy="{cy}" r="{core}" fill="{BLUE_D}"/>')
        if glint:
            # 반사는 **심 안에** 온전히 들어가야 한다. 심의 가장자리에 걸치면
            # 심이 베어 먹힌 모양이 된다(512 실측). 중심에서의 거리 + 반사 반지름이
            # 심의 반지름보다 작아야 한다.
            d = (core - glint) * 0.56
            s.append(f'\n  <circle cx="{round(cx-d,2)}" cy="{round(cy-d,2)}"'
                     f' r="{glint}" fill="{PAPER}"/>')
    return "".join(s)


def body_A(small=False):
    """전신 — 다리 넷으로 선 마스코트."""
    if small:
        # 탭 새김. 다리를 길게 두면 몸통 아래가 **검은 아치**로 갈라져 마크가
        # 둘로 읽힌다(16 화소 실측). 배를 둥글게 내리고 발 자국 둘만 남긴다 —
        # 16 화소에 남는 것은 몸통 + 큰 눈 둘 + 발 자국 둘이다.
        return (BG
                + _leg([(18, 42), (13, 51)], 7.5, 4.2)
                + _leg([(46, 42), (51, 51)], 7.5, 4.2)
                + _body(21, 16.5, 25, 34, 45, r=12)
                + _eyes(9.2, 25, 8.8))
    return (BG
            + _leg([(17, 29), (9, 25), (12, 50)], 6, 3.5)
            + _leg([(25, 35), (20, 32), (22, 53)], 6, 3.5)
            + _leg([(39, 35), (44, 32), (42, 53)], 6, 3.5)
            + _leg([(47, 29), (55, 25), (52, 50)], 6, 3.5)
            + _body(20, 15.5, 23, 30, 37)
            + _eyes(8.8, 23, 8.2, core=4.4, glint=1.7))


def body_B(small=False):
    """얼굴 — 몸통과 렌즈를 키워 판을 채운다."""
    if small:
        return (BG
                + _leg([(19, 44), (14, 54)], 8, 4.5)
                + _leg([(45, 44), (50, 54)], 8, 4.5)
                + _body(24, 19, 27, 37, 48, r=13)
                + _eyes(11.5, 27, 10.6))
    return (BG
            + _leg([(17, 39), (9, 35), (13, 53)], 7, 4)
            + _leg([(47, 39), (55, 35), (51, 53)], 7, 4)
            + _body(24, 19, 26, 35, 43)
            + _eyes(11.5, 26, 10.2, core=5.4, glint=2.1))


BODY = {"A": body_A, "B": body_B}
NAME = {"A": "전신", "B": "얼굴"}


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
    for pick in ("A", "B"):
        for small in (False, True):
            tag = pick + ("s" if small else "")
            for n in (512, 192, 180, 48, 32, 16):
                open(os.path.join(HERE, f"m-{tag}-{n}.html"), "w", encoding="utf-8").write(
                    page(BODY[pick](small), n))


def install(pick, assets):
    open(os.path.join(assets, "mark.svg"), "w", encoding="utf-8").write(
        svg(BODY[pick](False), 64, f"마스코트 「{NAME[pick]}」 — 큰 판(48 이상). 작은 판은 favicon.svg"))
    open(os.path.join(assets, "favicon.svg"), "w", encoding="utf-8").write(
        svg(BODY[pick](True), 64, "탭 크기(16~32)용 광학 새김 — 다리 둘·민 렌즈·굵은 획"))
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
