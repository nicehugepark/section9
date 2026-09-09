"""Board 의 상태 머리는 스크롤해도 판 위에 남는다 (REQ-20260909-093).

주인이 본 것: 카드를 따라 아래로 내려가면 열 머리(OPEN 3 · IN-PROGRESS 4 …)가
위로 사라져, 지금 보고 있는 카드가 어느 상태의 것인지 알 수 없었다(캡처 16:36).

뿌리는 스크롤 상자였다. `.board` 는 `overflow-x:auto` 만 걸고 높이는 내용대로
두었는데, **가로 스크롤을 켠 상자는 세로도 스크롤 상자가 된다.** 그래서 세로로
움직이는 것은 문서인데 `position:sticky` 의 기준은 판이라, 머리는 붙을 곳이
없어 카드와 함께 위로 떠났다(s9-design 표 절 6 이 적어 둔 함정). 판에 높이를
주어 **판 자신이 세로로 스크롤**하게 하면 `top:0` 한 줄로 머리가 선다.

여기서 재는 것은 렌더다 — 규칙에 `position:sticky` 가 적혀 있는지가 아니라,
브라우저가 실제로 스크롤한 뒤 머리가 판의 윗변에 있는지.

  · 스크롤 뒤 머리의 top 이 판의 안쪽 윗변과 같다(스킨 열 개 전부).
  · 머리 아래로 지나가는 카드가 비쳐 보이지 않는다 — 머리에 색이 깔려 있다
    (투명이면 아래 글자가 그대로 겹쳐 읽힌다).
  · 판이 세로 스크롤 상자다(스크롤할 것이 있으면 scrollTop 이 실제로 움직인다).

실행: python3 tests/ board_sticky
"""
import json
import os
import shutil
import subprocess
import time
import unittest
import urllib.request

from cdpreal import WS, chrome_path, reclaim
from webasset import parts

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")

SKINS = ("ledger", "slate", "cork", "grid", "soft", "calm",
         "glass", "cobalt", "field", "terminal")
STATUSES = (("open", "OPEN"), ("in-progress", "IN-PROGRESS"),
            ("blocked", "BLOCKED"), ("done", "DONE"))


def fixture_html():
    """실제 화면과 같은 캐스케이드 · 같은 판 구조.

    판의 높이는 이제 재지 않는다 — `<html class="boardfit">` 이 붙으면 몸통부터
    판까지가 세로 flex 사슬이 되어 판이 남는 높이를 받는다(REQ-20260909-100).
    그래서 픽스처도 화면과 같은 상자 사슬(body > main > #view > .board)을 세운다."""
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    cols = []
    for st, label in STATUSES:
        cards = "".join(
            '<div class="card" data-status="%s" style="--sc:var(--muted)">'
            '<div class="id"><span class="idn">REQ-20260909-%03d</span></div>'
            '<div class="t">스크롤을 받아 낼 만큼 긴 목록의 카드 %d</div>'
            '<div class="m"><span class="badge">nice</span></div></div>'
            % (st, i, i) for i in range(1, 15))
        cols.append(
            '<div class="col" style="--sc:var(--c-%s)" data-colstatus="%s">'
            '<h2><span class="cdot"></span>%s<span class="n">14</span></h2>'
            '<div class="cards">%s</div></div>'
            % (st.replace("-", ""), st, label, cards))
    return ('<!doctype html><html lang="ko" class="boardfit" data-theme="light"'
            ' data-skin="ledger" data-density="normal"><head>'
            '<meta charset="utf-8"><style>%s</style>'
            '<style>body{margin:0;background:var(--bg)}'
            '.top{height:120px;background:var(--panel);flex:none}</style></head>'
            '<body><div class="top">머리 자리(헤더·필터 줄·띠)</div>'
            '<main><div id="view"><div class="board">%s</div></div></main>'
            "</body></html>" % (css, "".join(cols)))


MEASURE_JS = """
(() => {
  const board = document.querySelector('.board');
  board.scrollTop = 260;
  const b = board.getBoundingClientRect();
  const top = b.top + board.clientTop;
  const out = {scrollTop: board.scrollTop, scrollable: board.scrollHeight > board.clientHeight,
               heads: []};
  for (const h of board.querySelectorAll('.col h2')) {
    const r = h.getBoundingClientRect();
    const cs = getComputedStyle(h);
    out.heads.push({label: h.textContent.trim(), dy: r.top - top,
                    position: cs.position, bg: cs.backgroundColor});
  }
  return out;
})()
"""

TRANSPARENT = ("rgba(0, 0, 0, 0)", "transparent")

# 손을 얹을 자리 — 첫 열 첫 카드의 한가운데. 판을 맨 위로 되돌린 뒤 잰다.
POINT_JS = """
(() => {
  const board = document.querySelector('.board');
  board.scrollTop = 0;
  const c = board.querySelector('.col .card');
  const r = c.getBoundingClientRect();
  return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)};
})()
"""

# 붙은 머리가 손 얹은 첫 카드의 윗변을 덮는가. 재는 것은 **뜬 뒤의** 좌표다 —
# 카드가 translateY 로 떠오르면 윗변이 머리 상자 안으로 들어갈 수 있다.
HOVER_JS = """
(() => {
  const board = document.querySelector('.board');
  const col = board.querySelector('.col');
  const h2 = col.querySelector('h2'), card = col.querySelector('.card');
  const hr = h2.getBoundingClientRect(), cr = card.getBoundingClientRect();
  const cs = getComputedStyle(card);
  return {hovered: card.matches(':hover'),
          gap: +(cr.top - hr.bottom).toFixed(2),
          lift: cs.transform,
          borderTop: cs.borderTopWidth,
          headZ: getComputedStyle(h2).zIndex,
          cardZ: cs.zIndex};
})()
"""


class TheColumnHeadStaysOnTop(unittest.TestCase):
    data = None

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path()
        if not chrome:
            raise unittest.SkipTest("브라우저 없음 — 실측 불가 환경")
        try:
            cls.data = cls.measure(chrome)
        except (ConnectionError, RuntimeError, OSError, StopIteration) as e:
            raise unittest.SkipTest("CDP 실측 불가: %s" % e)

    @classmethod
    def measure(cls, chrome):
        marker = "s9req093-%d" % os.getpid()
        win = chrome.startswith("/mnt/c/")
        if win:
            os.makedirs("/mnt/c/Temp", exist_ok=True)
            prof_wsl, prof_arg = "/mnt/c/Temp/" + marker, "C:\\Temp\\" + marker
            fix = os.path.join("/mnt/c/Temp", marker + ".html")
            url = "file:///C:/Temp/%s.html" % marker
        else:
            base = os.environ.get("TMPDIR", "/tmp")
            prof_wsl = prof_arg = os.path.join(base, marker)
            fix = os.path.join(base, marker + ".html")
            url = "file://" + fix
        shutil.rmtree(prof_wsl, ignore_errors=True)
        with open(fix, "w", encoding="utf-8") as f:
            f.write(fixture_html())
        proc = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu",
             "--user-data-dir=" + prof_arg, "--no-first-run",
             "--no-default-browser-check", "--disable-extensions",
             "--remote-debugging-port=0", "--window-size=1280,800", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws, out = None, {}
        try:
            port, dev = None, os.path.join(prof_wsl, "DevToolsActivePort")
            for _ in range(120):
                if os.path.exists(dev):
                    try:
                        port = int(open(dev).read().splitlines()[0])
                        break
                    except (ValueError, IndexError, OSError):
                        pass
                time.sleep(0.25)
            if port is None:
                raise ConnectionError("DevToolsActivePort 미출현")
            pages = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % port, timeout=10).read())
            page = next(p for p in pages if p.get("type") == "page")
            ws = WS(page["webSocketDebuggerUrl"])
            for _ in range(80):
                if ws.eval("document.readyState") == "complete":
                    break
                time.sleep(0.25)
            time.sleep(0.3)
            for skin in SKINS:
                ws.eval("document.documentElement.dataset.skin=%r" % skin)
                time.sleep(0.12)
                out[skin] = ws.eval(MEASURE_JS)
                # 손 얹은 얼굴은 **실포인터**로만 나온다 (REQ-20260909-100 반려의
                # 교훈 — 정지 화면만 찍고 통과시킨 것이 그 반려를 불렀다).
                # CSS 를 복제해 흉내 내면 실제 캐스케이드와 갈릴 수 있다.
                pt = ws.eval(POINT_JS)
                ws.call("Input.dispatchMouseEvent", type="mouseMoved",
                        x=pt["x"], y=pt["y"], button="none", buttons=0)
                time.sleep(0.35)
                out[skin]["hover"] = ws.eval(HOVER_JS)
                ws.call("Input.dispatchMouseEvent", type="mouseMoved",
                        x=2, y=2, button="none", buttons=0)
                time.sleep(0.1)
            return out
        finally:
            if ws is not None:
                ws.close()
            try:
                proc.terminate()
            except OSError:
                pass
            reclaim(marker, win)
            shutil.rmtree(prof_wsl, ignore_errors=True)
            try:
                os.remove(fix)
            except OSError:
                pass

    def test_the_column_head_stays_on_top(self):
        """스크롤한 뒤에도 상태 머리가 판의 윗변에 남는다."""
        with self.subTest("the_board_scrolls_itself"):
            for skin, d in self.data.items():
                self.assertTrue(d["scrollable"],
                                "%s 에서 판이 세로 스크롤 상자가 아니다 — 높이가 "
                                "없으면 붙을 자리도 없다" % skin)
                self.assertGreater(d["scrollTop"], 0,
                                   "%s 에서 판이 스크롤되지 않았다" % skin)
        with self.subTest("every_head_sits_at_the_top_edge"):
            for skin, d in self.data.items():
                for h in d["heads"]:
                    self.assertEqual("sticky", h["position"],
                                     "%s / %s 머리가 붙지 않는다" % (skin, h["label"]))
                    self.assertLess(
                        abs(h["dy"]), 1.5,
                        "%s / %s 에서 머리가 판의 윗변을 떠났다: %.1fpx"
                        % (skin, h["label"], h["dy"]))
        with self.subTest("the_head_is_not_see_through"):
            for skin, d in self.data.items():
                for h in d["heads"]:
                    self.assertNotIn(
                        h["bg"], TRANSPARENT,
                        "%s / %s 머리가 투명하다 — 밑으로 지나가는 카드가 "
                        "비쳐 읽힌다" % (skin, h["label"]))

    def test_the_head_does_not_cover_the_lifted_card(self):
        """손을 얹어 떠오른 첫 카드의 윗변이 붙은 머리 뒤로 들어가지 않는다.

        주인 반려 2026-09-09 18:13 (REQ-20260909-100): calm 에서 카드가
        translateY(-2px) 로 뜨자 윗변의 1px 테두리가 머리(불투명·z-index 2) 안으로
        2px 들어가 **통째로 사라졌다** — 둥근 모서리가 위로 말리다 평평하게 잘렸다.
        먼저 판례(REQ-20260827-058, 첫 카드의 왼쪽 획)와 같은 원칙이다:
        **자르는 쪽이 양보한다.** 카드를 줄이지도, 머리 위로 올리지도 않는다.
        """
        for skin, d in self.data.items():
            h = d["hover"]
            self.assertTrue(h["hovered"],
                            "%s 에서 실포인터가 카드에 얹히지 않았다 — 잰 값이 "
                            "쉼 얼굴이면 이 계약은 아무것도 지키지 못한다" % skin)
            self.assertGreaterEqual(
                h["gap"], 0,
                "%s 에서 손 얹은 첫 카드의 윗변이 머리 상자 안으로 %.1fpx "
                "들어갔다 — 그만큼이 잘려 보인다 (lift=%s, border-top=%s)"
                % (skin, -h["gap"], h["lift"], h["borderTop"]))

    def test_a_card_passing_under_the_head_stays_behind_it(self):
        """머리 밑을 지나가는 카드는 여전히 머리 뒤다 — z-index 를 뒤집어 고치지 않는다.

        hover 카드를 머리 위로 올리면 잘림은 사라지지만, 스크롤해 지나가는 카드가
        머리를 덮어 「지금 어느 상태의 카드인가」를 잃는다 (REQ-20260909-093 이
        세운 것). 그래서 머리가 이기는 순서를 계약으로 못박는다.
        """
        for skin, d in self.data.items():
            h = d["hover"]
            self.assertEqual("2", h["headZ"],
                             "%s 에서 머리의 z-index 가 2 가 아니다: %s"
                             % (skin, h["headZ"]))
            self.assertEqual("auto", h["cardZ"],
                             "%s 에서 카드가 제 쌓임 순서를 갖는다(%s) — 머리 위로 "
                             "올라올 수 있다" % (skin, h["cardZ"]))

    def test_the_head_line_is_not_a_hand_written_colour(self):
        """붙은 머리의 아래 선은 그 스킨의 선 토큰에서 온다.

        주인: 「헤더 테두리 색상도 뭔가 안어울리고」. 머리가 레일이 된 뒤로 그 선은
        판의 다른 선들과 같은 계열이어야 한다 — 손으로 적은 색이 하나라도 있으면
        스킨·톤이 바뀌는 순간 그 선만 남의 색이 된다.
        """
        import re as _re
        bad = []
        for name in ("board.css", "skins.css", "calm.css"):
            src = open(os.path.join(WEB, "css", name), encoding="utf-8").read()
            for m in _re.finditer(r"\.col h2\{([^}]*)\}", src):
                for decl in _re.finditer(r"border(?:-bottom)?(?:-color)?\s*:([^;}]*)",
                                         m.group(1)):
                    val = decl.group(1)
                    if _re.search(r"#[0-9a-fA-F]{3,8}|\brgba?\(|\bhsla?\(", val):
                        bad.append("%s: %s" % (name, val.strip()))
        self.assertEqual([], bad,
                         "머리의 선에 손으로 적은 색이 있다 — var(--hairline)/"
                         "var(--border) 처럼 그 스킨의 선 토큰을 읽어야 한다: %s"
                         % bad)


if __name__ == "__main__":
    unittest.main()
