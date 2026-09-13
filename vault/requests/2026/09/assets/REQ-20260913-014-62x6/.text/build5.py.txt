# -*- coding: utf-8 -*-
"""section9 마크 — 10차 (REQ-20260913-014-62x6). 주인이 직접 정한 설계.

「흰 원에 검은 점 3개. 그것을 section9 의 동그라미 부분 — o 와 9 의 원 안 — 에
채워 넣는다. 검은 점은 정중앙이 아니라 중앙에서 아래쪽으로.」 (2026-09-14 01:06)

  마크·파비콘 = 잉크 타일 + 종이 원 하나 + 잉크 점 셋(중앙보다 아래).
  워드마크    = 「section9」의 o 와 9 의 속을 그 눈으로 채운다.

점은 16 화소에서 붙어 버리지 않아야 한다 — 1 눈금 = 0.25 화소이므로 점 사이
틈이 4 눈금 이상이어야 화소 하나가 남는다. 그래서 새김이 둘이다.
"""
import os, struct, sys

INK, PAPER, BLUE = "#141518", "#fafaf8", "#5b8def"
HERE = os.path.dirname(os.path.abspath(__file__))
def r2(v): return round(v, 2)


def eye(cx, cy, r, dot, tri, spread, drop, fill=PAPER, dotfill=INK, plate=True):
    """눈 — 종이 원 하나 + 잉크 점 셋. 점 무리는 원의 중심보다 `drop` 만큼 아래.

    tri='down' 이면 위 둘 · 아래 하나(역삼각), 'up' 이면 위 하나 · 아래 둘.
    """
    s = []
    if plate:
        s.append(f'\n  <rect width="64" height="64" fill="{INK}"/>')
    s.append(f'\n  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>')
    cy2 = cy + drop                      # 점 무리의 중심
    h = spread * 0.86                    # 정삼각의 높이 비
    if tri == "down":
        pts = [(cx - spread, cy2 - h * 0.42), (cx + spread, cy2 - h * 0.42),
               (cx, cy2 + h * 0.84)]
    else:
        pts = [(cx, cy2 - h * 0.84), (cx - spread, cy2 + h * 0.42),
               (cx + spread, cy2 + h * 0.42)]
    for px, py in pts:
        s.append(f'\n  <circle cx="{r2(px)}" cy="{r2(py)}" r="{dot}" fill="{dotfill}"/>')
    return "".join(s)


# 큰 판(48 이상) / 작은 판(16·32) — 작은 판은 점을 굵히고 틈을 벌린다
def mark(small=False, tri="down"):
    if small:
        return eye(32, 32, 24, 5.0, tri, 8.6, 5.6)
    return eye(32, 32, 23, 4.4, tri, 7.6, 5.0)


def svg(body, size=64, note=""):
    n = f'\n  <!-- {note} -->' if note else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            f'width="{size}" height="{size}" role="img" aria-label="section9">'
            f'\n  <title>section9</title>{n}{body}\n</svg>\n')


# ---- 워드마크 ----------------------------------------------------------
# 글자 획은 잉크. o 와 9 는 속을 눈으로 채워야 하므로 도형으로 그린다 —
# 앞뒤의 글자 토막은 textLength 로 폭을 못박아, 글꼴이 달라도 자리가 안 밀린다.
FONT = ("system-ui,-apple-system,'Segoe UI',Roboto,"
        "'Helvetica Neue',Arial,sans-serif")

def wordmark(nine_blue=False):
    """o 와 9 의 속을 눈으로 채운다. 고리 굵기는 글자의 획과 같아야 한다 —
    얇으면 o 만 흐려 보인다. 속이 눈으로 읽힐 만큼은 커야 하므로 o 와 9 를
    본문 글자보다 조금 크게 세운다(로고의 자리이니 허용된다)."""
    c9 = BLUE if nine_blue else "currentColor"
    o_cx, o_cy, o_R, o_w = 196, 31, 16.0, 6.2      # o — 속 반지름 9.8
    # 9 는 숫자라 x 높이보다 위로 선다. 고리를 올리고 꼬리를 밑선까지 내려야
    # o 에 꼬리를 붙인 것이 아니라 9 로 읽힌다.
    n_cx, n_cy, n_R, n_w = 270, 25, 16.0, 6.2      # 9 의 고리 — 속 9.8
    tail_x = r2(n_cx + n_R - n_w / 2)
    return f'''
  <g class="wm" fill="currentColor">
    <text x="80" y="46" textLength="94" font-family="{FONT}" font-size="42"
          font-weight="700" letter-spacing="0.4">secti</text>
    <text x="218" y="46" textLength="26" font-family="{FONT}" font-size="42"
          font-weight="700">n</text>
  </g>
  <!-- o — 속을 눈으로 -->{eye(o_cx, o_cy, r2(o_R - o_w), 2.5, "down", 4.4, 2.9, plate=False)}
  <circle cx="{o_cx}" cy="{o_cy}" r="{r2(o_R - o_w / 2)}" fill="none"
          stroke="currentColor" stroke-width="{o_w}"/>
  <!-- 9 — 고리의 속을 눈으로, 꼬리는 밑선까지 -->
  <path d="M{tail_x} {n_cy} Q{tail_x} {n_cy + 16} {r2(n_cx - 4)} {n_cy + 22}"
        fill="none" stroke="{c9}" stroke-width="{n_w}" stroke-linecap="round"/>
  {eye(n_cx, n_cy, r2(n_R - n_w), 2.5, "down", 4.4, 2.9, plate=False)}
  <circle cx="{n_cx}" cy="{n_cy}" r="{r2(n_R - n_w / 2)}" fill="none"
          stroke="{c9}" stroke-width="{n_w}"/>'''


def logo_svg(nine_blue=False, tri="down"):
    m = mark(False, tri).replace('<rect width="64" height="64" fill="#141518"/>',
                                 '<rect width="64" height="64" rx="6" fill="#141518"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 302 64" width="302" height="64" role="img" aria-label="section9">
  <title>section9</title>
  <style>
    svg{{color:{INK}}}
    @media (prefers-color-scheme:dark){{svg{{color:#e8e8e4}}}}
  </style>
  <g>{m}
  </g>{wordmark(nine_blue)}
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
    for tri in ("down", "up"):
        for small in (False, True):
            tag = tri + ("s" if small else "")
            for n in (512, 192, 180, 48, 32, 16):
                open(os.path.join(HERE, f"e-{tag}-{n}.html"), "w", encoding="utf-8").write(
                    page(mark(small, tri), n))


def install(tri, assets, nine_blue=False):
    open(os.path.join(assets, "mark.svg"), "w", encoding="utf-8").write(
        svg(mark(False, tri), 64, "눈 — 종이 원 + 잉크 점 셋(중앙보다 아래). 큰 판(48 이상)"))
    open(os.path.join(assets, "favicon.svg"), "w", encoding="utf-8").write(
        svg(mark(True, tri), 64, "탭 크기(16~32)용 — 점을 굵히고 틈을 벌려 화소에서 붙지 않게"))
    open(os.path.join(assets, "logo.svg"), "w", encoding="utf-8").write(
        logo_svg(nine_blue, tri))
    print("svg 셋 실었다: 점 배치", tri, "· 9", "파랑" if nine_blue else "잉크")


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
                else os.path.expanduser("~/section9/web/assets"),
                nine_blue=(len(sys.argv) > 3 and sys.argv[3] == "blue"))
