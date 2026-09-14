# -*- coding: utf-8 -*-
"""section9 마크 v6 「또렷한 작은 새김」 (REQ-20260914-002-62x6 재작업 4).

주인(2026-09-14 14:47): 「첨부한 이미지를 봤을 때 선명함이 더 높아졌으면 좋겠다.」

작은 새김에서 셋을 고쳤다. 테 굵기(2.80)는 v5 그대로다 — 주인이 14:25 에 고른 값이다.

  · **돔 음영을 평평하게** — 종전에는 가운데에서 가장자리까지 부드럽게 어두워졌는데,
    18px 에서는 그 부드러움이 **흐림**으로 읽힌다(잉크가 없는 자리인데 회색이 깔린다).
    안쪽 74% 를 거의 한 색으로 두고 바깥 7% 에서만 떨어뜨렸다. 48px 이상에서는
    가장자리 음영과 반사가 그대로 있어 돔으로 읽힌다.
  · **점을 순검정으로** — #141518 → #000000. 18px 에서 점 하나가 1.7 화소라 대부분이
    가장자리 흐림이다. 한 칸의 대비가 그대로 또렷함이 된다.
  · **머리 마크를 18 → 20px** — 20 은 Windows 배율 125%·150% 에서 25·30 화소로
    **정수**가 된다(18 은 22.5 라 반 화소에 걸린다). 이웃 글자의 밑선은 그대로 두려고
    vertical-align 을 -4 → -5px 로 함께 옮겼다. 큰 새김(logo·앱 아이콘)은 v4 그대로다.

아래는 v5 의 머리말이다.
"""
"""v5 「재주 목록 · 가는 테」 (REQ-20260914-002-62x6 재작업 3).

주인(2026-09-14 14:25): 「테두리가 조금 두꺼운 것 같애. 조금 더 가늘게 해줘.」

테를 **3.60 → 2.80 눈금**(18px 화면에서 1.01 → 0.79 화소)으로 줄였다. 굵기를 줄이는
길과 잉크를 옅게 하는 길을 시안 여섯(3.60·2.80·2.20 잉크, 3.60·2.80 짙은 회색, 1.80
잉크)으로 18px 실물과 배율 1·1.25·1.5·2, 밝은·어두운 바탕에 찍어 눈으로 골랐다.
잉크를 옅게 한 것은 가늘어 보이지 않고 **뭉개져** 보였고, 2.20 아래로 내리면 v2 때처럼
흐린 띠로 번지기 시작했다. 그래서 굵기만 한 칸 줄였다.

머리 조각은 점 셋을 **하나씩** 움직일 수 있게 `<g class="d0|d1|d2">` 로 감쌌다 —
움직임은 web/app/mark.js 의 재주 표가 한다.

아래는 v4 의 머리말이다.
"""
"""v4 「뒤돌아보는 눈」 (REQ-20260914-002-62x6 재작업 2).

주인(2026-09-14 14:02): 「가끔 뒤(화면에서 보이지 않는 곳)도 돌아보고 훨씬 더 넓은
각으로 움직였으면 좋겠고, 또 아주 가끔씩 뱅그르르 돌아가는 효과도 있으면 좋겠다.」

**그림은 v3 그대로다 — 바뀐 것은 머리 조각의 뼈대와 움직임뿐이다.**
mark.svg·favicon.svg·logo.svg·favicon.ico·앱 아이콘 셋은 v3 의 파일과 바이트가 같다
(정지 그림에는 움직임이 없으니 바뀔 것이 없다). header.svg 에만 둘이 붙었다:

  · `<clipPath>` — 돔 원으로 오려 낸다. 점 셋이 테 뒤로 사라지려면 오려 내야 한다.
    오려 내지 않으면 테 밖 허공에 떠서 「뒤로 갔다」가 아니라 「밖으로 나갔다」다.
  · `<g class="spin">` — 회전은 **렌즈 중심**이 축이고 무리의 눌림은 **제 무게중심**이
    축이라, 한 그룹에 둘을 얹을 수 없다(축이 하나뿐이면 회전이 무리를 밖으로 던진다).

움직임 자체는 web/app/mark.js 에 있다.

아래는 v3 의 머리말이다.
"""
"""v3 「박스 없음 · 선명한 작은 새김」 (REQ-20260914-002-62x6 재작업).

주인 반려(13:46): 「버전마다 차이를 잘 모르겠다」 · 「작은 크기에서도 더 선명하게
할 수는 없나?」 — v2 의 테가 18px 에서 0.41 화소라 흐린 띠로 번졌고, 점도 1.4
화소여서 셋이 뭉쳐 보였다. **작은 새김을 화소에 맞춰 다시 깎는다.**

  · 테를 18px 화면에서 **1 화소**가 되게 (3.6 눈금 = 1.01px). 종전 1.44 눈금.
  · 점 지름 1.63px (5.8 눈금). 종전 1.40px.
  · 돔 가장자리를 더 짙게 (#a9a496 → #a59e8a) — 흰 배경에서 렌즈가 또렷하게.
큰 새김(logo·앱 아이콘)은 v2 그대로다 — 48px 이상에서는 이 굵기가 되레 무겁다.

아래는 v2 의 머리말이다.
"""
"""v2 「박스 없음」 (REQ-20260914-002-62x6). v1 의 build.py 를 이어받는다.

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
DOT_INK = "#000000"     # 작은 새김의 점 — 1.7 화소라 한 칸의 대비가 또렷함이 된다
HERE = os.path.dirname(os.path.abspath(__file__))
def r2(v): return round(v, 2)

# 큰 새김(logo·앱 아이콘)의 음영 — v2 그대로
DEFS_L = '''
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

# 작은 새김(16~32px)의 음영 — 가장자리를 짙게 해 흰 배경에서도 경계가 선다
# 작은 새김(16~32px)의 음영 — **평평하게**. 부드러운 그라데이션은 18px 에서 흐림으로
# 읽힌다(REQ-20260914-002-62x6, 주인 14:47). 안쪽은 거의 한 색, 바깥 7% 에서만 떨군다.
DEFS = (DEFS_L.replace('cx="50%" cy="32%" r="74%"', 'cx="50%" cy="40%" r="68%"')
        .replace('<stop offset="0" stop-color="#fdfcf8"/><stop offset=".44" stop-color="#f6f4ee"/>',
                 '<stop offset="0" stop-color="#fffefc"/><stop offset=".74" stop-color="#fbfaf5"/>')
        .replace('<stop offset=".76" stop-color="#e0ddd2"/><stop offset="1" stop-color="#a9a496"/>',
                 '<stop offset=".93" stop-color="#e4dfd0"/><stop offset="1" stop-color="#9c9480"/>'))

# 점 셋 — 돔 지름에 대한 비율. 무리의 꼴(정삼각·아래로 내린 정도)은 주인이 v1 에서
# 고른 그대로이고, v3 에서 바뀐 것은 **점의 굵기**뿐이다 — 18px 에서 1.63 화소가
# 되도록 잡았다(v2 는 1.40 화소여서 셋이 한 덩어리로 뭉쳐 보였다).
SMALL = dict(dot=.1058, side=.2175, drop=.1480)   # 16~32px 로 그려지는 자리
LARGE = dict(dot=.0840, side=.1271, drop=.1589)   # 48px 이상 (v2 그대로)

# 작은 새김의 치수 — 18px 로 그려지는 것을 전제로 눈금을 화소에 맞춘 값이다.
# 1 눈금 = 0.28125 화소이므로 테 3.6 눈금 = 1.01 화소다.
S_R, S_RIM_PCT = 31, .0451613     # 바깥 반지름 31 · 테 2.80 → 돔 반지름 28.20
L_RIM_PCT = .024                  # 큰 새김은 v2 그대로


def lens(cx, cy, R, rim_pct=L_RIM_PCT, rim=True):
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


def pupil(cx, cy, R, carve, rim_pct=L_RIM_PCT, rim=True, wrap=False, ink=INK):
    w = R * 2 * rim_pct if rim else 0
    dd = (R - w) * 2                       # 돔 지름 — 비율의 기준
    dot, side, drop = r2(dd * carve["dot"] / 2), dd * carve["side"], dd * carve["drop"]
    h = side * 0.8660254
    pts = [(cx - side / 2, cy + drop - h / 3), (cx + side / 2, cy + drop - h / 3),
           (cx, cy + drop + 2 * h / 3)]
    body = "".join('\n    <circle cx="%s" cy="%s" r="%s" fill="%s"/>'
                   % (r2(x), r2(y), dot, ink) for x, y in pts)
    if wrap:
        return '\n  <g class="pupil">%s\n  </g>' % body
    return body.replace("\n    ", "\n  ")


def mark(R=S_R, carve=None, tile=False, wrap=False, rim_pct=S_RIM_PCT):
    carve = carve or SMALL
    plate = ('\n  <rect width="64" height="64" fill="%s"/>' % INK) if tile else ""
    return (plate + lens(32, 32, R, rim_pct)
            + pupil(32, 32, R, carve, rim_pct, wrap=wrap,
                    ink=DOT_INK if carve is SMALL else INK))


def svg(body, size=64, note="", defs=None):
    n = '\n  <!-- %s -->' % note if note else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            'width="%d" height="%d" role="img" aria-label="section9">'
            '\n  <title>section9</title>%s%s%s\n</svg>\n' % (size, size, n, defs or DEFS, body))


FONT = ("system-ui,-apple-system,'Segoe UI',Roboto,"
        "'Helvetica Neue',Arial,sans-serif")

def logo_svg():
    """워드마크는 v2 그대로다 — 48px 이상으로 그려지므로 두꺼운 테가 되레 무겁다."""
    tile = (lens(32, 32, 30, L_RIM_PCT)
            + pupil(32, 32, 30, LARGE, L_RIM_PCT)).replace("\n  ", "\n    ")
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
            % (DEFS_L, tile, FONT, o, nine))


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
                page(mark(), n, bg))
    print("pages ok")


def install(assets):
    open(os.path.join(assets, "mark.svg"), "w", encoding="utf-8").write(
        svg(mark(), 64, "렌즈만 — 18px 에서 테가 1 화소, 점이 1.63 화소인 작은 새김"))
    open(os.path.join(assets, "favicon.svg"), "w", encoding="utf-8").write(
        svg(mark(), 64, "탭 크기(16~32)용 — 머리글 마크와 같은 얼굴"))
    open(os.path.join(assets, "logo.svg"), "w", encoding="utf-8").write(logo_svg())
    print("svg 셋 실었다 (v3 · 선명한 작은 새김)")


# 한 줄로 적는다 — 껍데기(web/index.html)는 제 무게에 천장이 있어(270줄,
# tests/test_web_split.py) 마크 조각이 줄을 헤프게 쓸 자리가 아니다.
CLIP = '\n    <clipPath id="s9lensclip"><circle cx="32" cy="32" r="%s"/></clipPath>' 


def header_svg():
    """머리글에 박히는 조각 — 이름은 옆의 글자가 이미 말하므로 **읽어 주지 않는다**
    (aria-hidden). role/aria-label 을 달면 화면낭독기가 「section9 section9」로 두 번
    읽고, 껍데기를 훑는 자리에서도 그 글자가 마크 안에 또 있게 된다."""
    dome = r2(S_R - S_R * 2 * S_RIM_PCT)
    out = (svg(mark(wrap=True), 20)
           .replace('<svg xmlns', '<svg class="mark" xmlns')
           .replace(' role="img" aria-label="section9"', ' aria-hidden="true" focusable="false"')
           .replace("\n  <title>section9</title>", "")
           .replace("\n  </defs>", (CLIP % dome) + "\n  </defs>"))
    # 점 셋을 `돔으로 오려 낸 칸 > 무리 > 회전 > 점 하나씩` 네 겹으로 감싼다. 여는
    # 셋과 닫는 셋은 각각 한 줄이다 — 껍데기(web/index.html)는 제 무게에 천장이
    # 있어(270줄, tests/test_web_split.py) 줄을 헤프게 쓸 자리가 아니다.
    # 점의 기준점은 그 점의 한가운데다 — 좌표에서 나오는 값이라 조각에 함께 적는다
    # (규칙 파일에 두면 같은 값을 두 곳에 적게 된다).
    i = out.index('  <g class="pupil">')
    j = out.index("  </g>\n</svg>")
    dots = [ln.strip() for ln in out[out.index("\n", i) + 1:j].strip().splitlines()]
    wrapped = ""
    for n, ln in enumerate(dots):
        cx = ln.split('cx="')[1].split('"')[0]
        cy = ln.split('cy="')[1].split('"')[0]
        wrapped += ('    <g class="d%d" style="transform-origin:%spx %spx">%s</g>\n'
                    % (n, cx, cy, ln))
    return (out[:i]
            + '  <g clip-path="url(#s9lensclip)"><g class="pupil"><g class="spin">\n'
            + wrapped + "  </g></g></g>\n</svg>\n")


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
