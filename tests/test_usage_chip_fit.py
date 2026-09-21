"""사용량 칩은 머리글 밖으로 나가지 않는다 (REQ-20260915-001-2n7g).

주인이 맥 Safari 26.4 에서 본 것: 창을 400px 로 줄이면 문서에 9px 가로 넘침이
생기고(innerWidth 400 · scrollWidth 409), 머리글 오른쪽의
「agent01.pfe@dev.example.com · 5h 29% · wk 34% · fable 37%」 끝이 잘렸다.

뿌리는 `.usagechip{white-space:nowrap}` 이다. nowrap 인 조각의 min-content 폭은
**글자 전체 폭**(393px)이고, flex 항목의 `min-width:auto` 가 그 아래로 줄이는
것을 막는다 — 머리글에 남은 폭(400 - 좌우 안여백 44 = 356px)보다 넓으니 상자가
판을 밀어내고, 문서 전체가 가로로 넘친다.

고침은 **접히는 단위**를 바꾸는 것이다. 칩 전체를 못 접게 하는 대신 덩이
(`.useg`)마다 nowrap 을 주어 「5h 29%」의 이름과 숫자는 갈리지 않게 하고, 덩이
사이에서만 접는다. 이어짐을 알리는 `·` 는 앞 덩이 **끝**에 붙어, 접힌 줄이
언제나 이름으로 시작한다.

**손전화 폭에서는 접는 대신 던다** (REQ-20260916-012-2n7g, 2026-09-16 개정).
접히기는 했으나 사용량 2줄 + 신원 2줄이 그 폭의 머리글에서 50px 을 먹었고,
머리글 전체가 428px(창 900 의 47%)이었다. 그래서 ≤560px 에서는 **다른 자리에
이미 있는 것**을 뺀다 — 메일은 칩을 눌러 여는 카드에, OS·저장소 경로는 신원
줄의 title 에, 권한은 Settings 에 있다. 남는 것은 한도 비율과 「이름 @ 컴퓨터」
뿐이고, 둘이 각각 한 줄로 서서 50px 이 26px 이 된다.

말줄임으로 자르지 않은 까닭이 이 파일의 머리말 그대로다 — `nowrap` 은 이
상자의 min-content 폭을 글자 전체 폭으로 못박는다. `min-width:0` 으로 막을
수는 있으나 그러면 값이 잘린다. 뺀 것은 볼 길이 남아 있고 잘린 것은 그렇지
않다.

여기서 재는 것은 규칙에 무엇이 적혔는지가 아니라 **브라우저가 실제로 앉힌
자리**다 — 넘침은 글자 폭·글꼴에 걸리는 일이라 그리지 않고는 잴 수 없다.
화소나 반화소를 재지 않으므로(재는 것은 넘쳤나·몇 줄인가) 맥 브라우저로도 잰다.

실행: python3 tests/ usage_chip_fit
"""
import json
import os
import re
import shutil
import subprocess
import time
import unittest
import urllib.request

from cdpreal import WS, chrome_path, reclaim, skip_reason
from webasset import anon_helper, parts

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")

MAIL = "agent01.pfe@dev.example.com"
# 실제로 온 적 있는 가장 긴 꼴 — 덩이 하나가 홀로 폭을 넘는 마지막 갈래
LONG_MAIL = "a-very-long-service-account-name@some.department.example.co.kr"
NARROW = (400, 820)    # 주인이 잰 그 창
# 같은 글자가 브라우저마다 다른 폭을 쓴다 — 맥 Safari 는 393px, Chrome 은 359px
# 이라 400px 툴바(안쪽 368px)에 Chrome 에서는 아직 들어간다. 접히는 갈래를
# Chrome 으로도 실제로 보려면 그 아래로 한 칸 더 내려가야 한다.
TIGHT = (340, 820)
WIDE = (1440, 900)


def _fn(src, name):
    """`function name(...)` 한 덩이를 통째로 — 흉내가 아니라 실물을 싣는다."""
    i = src.index("function %s(" % name)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise AssertionError(name)


def fixture_html():
    """실제 화면과 같은 캐스케이드 · 같은 머리글 · 같은 렌더 함수."""
    css_files, _ = parts()
    css = "\n".join(open(os.path.join(WEB, "css", f), encoding="utf-8").read()
                    for f in css_files)
    shell = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    header = shell[shell.index("<header"):shell.index("</header>") + len("</header>")]
    usage = open(os.path.join(WEB, "app", "usage.js"), encoding="utf-8").read()
    const = open(os.path.join(WEB, "app", "const.js"), encoding="utf-8").read()
    notice = open(os.path.join(WEB, "app", "notice.js"), encoding="utf-8").read()
    js = (anon_helper() + _fn(const, "mk") + "\n" + _fn(usage, "renderUsageChip") + "\n"
          + _fn(notice, "renderWhoami") + "\n" + r"""
const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const $ = sel => document.querySelector(sel);
const asUser = "";
const s9cmd = c => "s9 " + c;
window.__draw = (mail, stale) => {
  renderUsageChip(document.getElementById("usage-chip"), {email: mail, stale: !!stale, limits: [
    {kind: "session", percent: 29}, {kind: "weekly_all", percent: 34},
    {kind: "weekly_scoped", percent: 37, scope_name: "Fable"}]});
  // 신원 줄도 실물이 그린다 — 같은 기둥을 나눠 쓰는 이웃이고, 좁은 폭에서
  // 밀려 나가는 까닭도 같다. 흉내 낸 글자로 채우면 그 갈래를 못 잡는다.
  window.__whoami = {user: "hong", machine: "Mac-mini.local",
                     os: "macOS", root: "/Users/hgpark/section9", role: "owner"};
  renderWhoami();
};
""")
    return ('<!doctype html><html lang="ko" data-theme="light" data-skin="ledger"'
            ' data-density="normal"><head><meta charset="utf-8">'
            "<style>%s</style></head><body>%s"
            "<main><p class=\"count\" id=\"count\"></p><div id=\"view\"></div></main>"
            "<script>%s</script></body></html>" % (css, header, js))


# 재는 것 다섯: 문서가 가로로 넘쳤나 · 칩의 오른끝이 툴바 줄의 **안쪽** 오른변
# 안인가 · 덩이가 몇 줄에 걸쳐 있나(한 덩이가 둘이면 이름과 숫자가 갈린 것이다) ·
# 덩이의 글자 · 이웃한 신원 줄의 오른끝.
#
# 창이 아니라 **안쪽 오른변**(툴바의 오른쪽 안여백 앞)을 기준으로 재는 까닭:
# 좌우 22px 는 여백이지 남는 자리가 아니다. 창만 보면 안여백을 파먹고 들어온
# 상태가 통과하는데, 그 상태가 글꼴이 조금만 넓은 브라우저(맥 Safari 는 같은
# 글자가 393px, Chrome 은 360px)에서 곧바로 문서 넘침이 된다 — 이 건이 정확히
# 그렇게 Chrome 을 지나 Safari 에서 드러났다.
MEASURE_JS = """
(() => {
  const el = document.getElementById('usage-chip');
  const who = document.getElementById('whoami');
  const rail = document.querySelector('.hrow2');
  const se = document.documentElement;
  const rr = rail.getBoundingClientRect();
  const railRight = rr.right - parseFloat(getComputedStyle(rail).paddingRight);
  const rows = ns => {
    const t = [...ns].map(r => Math.round(r.top));
    return [...new Set(t)].length;
  };
  // `vis` 는 상자가 실제로 그려졌나다 — 규칙이 물린 덩이는 글자가 DOM 에
  // 남아 있어도(카드가 그 글자를 쓴다) 상자를 얻지 못한다.
  const seen = n => n.getClientRects().length > 0;
  const segs = [...el.querySelectorAll('.useg')].map(s => ({
    text: s.textContent.replace(/\\s+/g, ' ').trim(),
    vis: seen(s),
    lines: rows(s.getClientRects()),
    right: seen(s)
      ? +Math.max(...[...s.getClientRects()].map(r => r.right)).toFixed(1) : null}));
  const wsegs = [...who.querySelectorAll('.wseg')].map(s => ({
    text: s.textContent.replace(/\\s+/g, ' ').trim(),
    cls: s.className, vis: seen(s)}));
  const mark = el.querySelector('.mk-clock');
  const addr = el.querySelector('.useg.mail .addr');
  const r = el.getBoundingClientRect();
  return {innerWidth: window.innerWidth,
          scrollWidth: se.scrollWidth,
          railRight: +railRight.toFixed(1),
          chipRight: +r.right.toFixed(1),
          chipHeight: +r.height.toFixed(1),
          chipLines: rows([...el.querySelectorAll('.useg')]
                          .flatMap(s => [...s.getClientRects()])),
          whoRight: +who.getBoundingClientRect().right.toFixed(1),
          whoLines: rows([...who.querySelectorAll('.wseg')]
                         .flatMap(s => [...s.getClientRects()])),
          whoHeight: +who.getBoundingClientRect().height.toFixed(1),
          markVis: !!mark && seen(mark),
          addrVis: !!addr && seen(addr),
          segs, wsegs};
})()
"""

CASES = (
    ("wide", WIDE, "ledger", MAIL, False),
    ("narrow", NARROW, "ledger", MAIL, False),
    ("tight", TIGHT, "ledger", MAIL, False),
    ("narrow_long_mail", NARROW, "ledger", LONG_MAIL, False),
    ("narrow_soft", NARROW, "soft", MAIL, False),
    # 값이 낡은 갈래 — 마크는 메일 덩이에 얹혀 있어, 메일을 빼면서 함께 지워지기
    # 쉽다. 그 자리를 잰다 (REQ-20260916-012-2n7g).
    ("narrow_stale", NARROW, "ledger", MAIL, True),
)
# 손전화 폭 — 여기서는 덜어서 한 줄로 선다(접어서가 아니라)
PHONE = ("narrow", "tight", "narrow_long_mail", "narrow_soft", "narrow_stale")
# 신원 줄이 설 수 있는 줄 수. soft 만 2 인 까닭은 **셸이 다르기 때문**이다 —
# 이 스킨은 머리글이 창 폭이 아니라 왼쪽 세로 띠이고, 400px 창에서 그 띠가
# 232px 다(실측 2026-09-16, 맥 Safari · 안쪽 203px). 「hong」 79px +
# 「@ Mac-mini.local」 171px 은 그 안에 못 든다. 여기서 한 줄을
# 받아 내려면 컴퓨터 이름을 잘라야 하는데, 그러면 어느 컴퓨터의 화면인지가
# 사라진다 — 덩이 사이에서 접히는 것이 맞는 갈래다(REQ-20260915-001-2n7g).
WHO_LINES = {"narrow": 1, "tight": 1, "narrow_long_mail": 1,
             "narrow_stale": 1, "narrow_soft": 2}

_MEASURED = {}


def shared():
    if "err" in _MEASURED:
        raise unittest.SkipTest(_MEASURED["err"])
    if "data" in _MEASURED:
        return _MEASURED["data"]
    # 자리와 넘침만 잰다 — 화소 계약 밖의 브라우저(맥)로도 잰다 (REQ-20260910-003)
    chrome = chrome_path(pixel_contract=False)
    if not chrome:
        _MEASURED["err"] = skip_reason(pixel_contract=False)
        raise unittest.SkipTest(_MEASURED["err"])
    try:
        _MEASURED["data"] = measure(chrome)
    except (ConnectionError, RuntimeError, OSError, StopIteration) as e:
        _MEASURED["err"] = "CDP 실측 불가: %s" % e
        raise unittest.SkipTest(_MEASURED["err"])
    return _MEASURED["data"]


def measure(chrome):
    marker = "s9req915001-%d" % os.getpid()
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
         "--remote-debugging-port=0", "--window-size=1440,900", url],
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
        for name, (w, h), skin, mail, stale in CASES:
            ws.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
                    deviceScaleFactor=1, mobile=False)
            ws.eval("document.documentElement.dataset.skin=%r" % skin)
            ws.eval("window.__draw(%r, %s)" % (mail, "true" if stale else "false"))
            time.sleep(0.25)
            out[name] = ws.eval(MEASURE_JS)
        ws.call("Emulation.clearDeviceMetricsOverride")
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


class TheChipStaysInsideTheHeader(unittest.TestCase):
    data = None

    @classmethod
    def setUpClass(cls):
        cls.data = shared()

    def test_no_case_overflows_the_document(self):
        """어느 폭에서도 문서가 가로로 넘치지 않는다 — 이 건의 증상 그 자체."""
        for name, *_ in CASES:
            d = self.data[name]
            self.assertLessEqual(
                d["scrollWidth"], d["innerWidth"],
                "%s: 문서가 가로로 %dpx 넘쳤다 (scrollWidth %d · innerWidth %d) — "
                "칩이 판을 밀어낸다"
                % (name, d["scrollWidth"] - d["innerWidth"],
                   d["scrollWidth"], d["innerWidth"]))

    def test_the_chip_ends_inside_the_toolbar(self):
        """칩의 오른끝이 툴바의 안쪽 오른변 안이다 — 안여백은 남는 자리가 아니다."""
        for name, *_ in CASES:
            d = self.data[name]
            self.assertLessEqual(
                d["chipRight"], d["railRight"] + 0.5,
                "%s: 칩의 오른끝이 %.1f 로 툴바의 안쪽 오른변(%.1f)을 %.1fpx "
                "넘었다 — 안여백을 파먹은 만큼이 글꼴 넓은 브라우저에서 곧 "
                "문서 넘침이 된다"
                % (name, d["chipRight"], d["railRight"],
                   d["chipRight"] - d["railRight"]))
            self.assertLessEqual(
                d["whoRight"], d["railRight"] + 0.5,
                "%s: 신원 줄의 오른끝이 %.1f 로 툴바의 안쪽 오른변(%.1f) 밖이다"
                % (name, d["whoRight"], d["railRight"]))

    def test_a_wide_window_keeps_one_line(self):
        """넓은 폭에서는 접지 않는다 — 접기는 자리가 모자랄 때만 하는 일이다."""
        d = self.data["wide"]
        self.assertEqual(d["chipLines"], 1,
                         "1440px 에서 칩이 %d 줄이다 — 자리가 남는데 접었다"
                         % d["chipLines"])

    def test_a_phone_width_stands_on_one_line_each(self):
        """손전화 폭에서는 칩도 신원도 한 줄이다 (REQ-20260916-012-2n7g).

        접어서가 아니라 **덜어서** 한 줄이다 — 이 폭에서 판단에 쓰지 않는
        덩이(메일·OS·권한)가 다른 자리로 물러났다. 여기서 두 줄이 나오면
        그 자리에서 머리글이 창의 절반을 먹던 상태로 돌아간 것이다.
        """
        for name in PHONE:
            d = self.data[name]
            self.assertEqual(
                d["chipLines"], 1,
                "%s: 사용량이 %d 줄이다 — 이 폭에서 서야 할 것은 한도 비율뿐이다"
                % (name, d["chipLines"]))
            self.assertLessEqual(
                d["whoLines"], WHO_LINES[name],
                "%s: 신원이 %d 줄이다 — 이 폭에서 서야 할 것은 「이름 @ 컴퓨터」뿐이다"
                % (name, d["whoLines"]))

    def test_a_phone_width_drops_what_lives_elsewhere(self):
        """뺀 것은 볼 길이 남아 있다 — 메일은 카드에, OS·권한은 title·Settings 에.

        글자를 지우는 것이 아니라 이 폭에서만 물리는 것이라, DOM 에는 그대로
        있고 상자만 얻지 못한다(카드가 같은 글자를 쓴다).
        """
        for name in PHONE:
            d = self.data[name]
            mail = [s for s in d["segs"] if "@" in s["text"]]
            self.assertTrue(mail, "%s: 메일 덩이가 DOM 에서 사라졌다 — 카드가 그 "
                                  "글자를 쓴다" % name)
            self.assertFalse(
                d["addrVis"],
                "%s: 이 폭에서 메일 글자가 서 있다 — 같은 글자가 칩을 눌러 여는 "
                "카드에 있다" % name)
            for w in d["wsegs"]:
                if "where" in w["cls"] or "role" in w["cls"]:
                    self.assertFalse(
                        w["vis"],
                        "%s: 신원 줄에 「%s」가 서 있다 — OS 는 줄의 title, 권한은 "
                        "Settings 에 있다" % (name, w["text"]))
                else:
                    self.assertTrue(
                        w["vis"],
                        "%s: 신원 줄에서 「%s」가 사라졌다 — 이름과 컴퓨터는 남는다"
                        % (name, w["text"]))

    def test_the_stale_mark_is_not_dropped_with_the_mail(self):
        """「값이 낡았다」 마크는 메일 덩이에 얹혀 있지만 함께 물러나지 않는다.

        마크가 사라지면 화면이 낡은 값을 방금 받은 값처럼 말한다.
        """
        self.assertTrue(
            self.data["narrow_stale"]["markVis"],
            "값이 낡았는데 마크가 서지 않는다 — 메일을 뺄 때 함께 지워졌다")
        self.assertFalse(
            self.data["narrow"]["markVis"],
            "낡지 않았는데 마크가 섰다")

    def test_a_dangling_separator_never_leads_the_line(self):
        """낡지 않은 갈래에서는 메일 덩이가 통째로 물러난다.

        글자만 빼고 덩이를 남기면 그 덩이의 이어짐 표시(`·`)가 줄 앞에 홀로
        서서, 앞에 무엇이 있었던 것처럼 읽힌다.
        """
        for name in PHONE:
            d = self.data[name]
            first = next((s for s in d["segs"] if s["vis"]), None)
            self.assertIsNotNone(first, "%s: 칩에 선 덩이가 하나도 없다" % name)
            self.assertFalse(
                first["text"].strip() == "·",
                "%s: 이어짐 표시만 남은 덩이가 줄 앞에 섰다" % name)

    def test_a_segment_never_splits(self):
        """「5h 29%」의 이름과 숫자가 갈리지 않는다 — 덩이 안은 nowrap 이다."""
        for name, _, _, mail, _ in CASES:
            for seg in self.data[name]["segs"]:
                if seg["text"].startswith(mail[:12]):
                    continue        # 메일 덩이는 마지막 수단으로 접힐 수 있다
                self.assertEqual(
                    seg["lines"], 1,
                    "%s: 덩이 「%s」가 %d 줄로 갈렸다 — 이름과 숫자가 다른 줄에 선다"
                    % (name, seg["text"], seg["lines"]))

    def test_the_separator_trails_its_segment(self):
        """이어짐 표시는 앞 덩이 끝에 붙는다 — 접힌 줄이 이름으로 시작하도록."""
        segs = self.data["tight"]["segs"]
        self.assertGreaterEqual(len(segs), 4, "덩이가 나뉘지 않았다 — 접힐 자리가 없다")
        for seg in segs[:-1]:
            self.assertTrue(seg["text"].endswith("·"),
                            "덩이 「%s」가 이어짐 표시로 끝나지 않는다 — 접히면 "
                            "다음 줄이 「· 」로 시작한다" % seg["text"])
        self.assertFalse(segs[-1]["text"].endswith("·"),
                         "마지막 덩이에 이어짐 표시가 붙었다 — 뒤에 올 것이 없다")

    def test_every_word_is_still_there(self):
        """넓은 폭에서는 글자를 하나도 버리지 않는다 — 계정·5h·wk·모델이 모두 선다."""
        text = " ".join(s["text"] for s in self.data["wide"]["segs"] if s["vis"])
        for want in (MAIL, "5h", "29%", "wk", "34%", "fable", "37%"):
            self.assertIn(want, text, "칩에서 「%s」가 사라졌다" % want)

    def test_a_phone_width_still_shows_every_limit(self):
        """좁은 폭에서 던 것은 계정뿐이다 — 한도 셋은 이름과 숫자가 다 선다.

        이 폭에서 사람이 칩을 보는 까닭이 한도이고, 계정은 이미 아는 값이다.
        """
        for name in ("narrow", "tight"):
            text = " ".join(s["text"] for s in self.data[name]["segs"] if s["vis"])
            for want in ("5h", "29%", "wk", "34%", "fable", "37%"):
                self.assertIn(want, text,
                              "%s: 칩에서 「%s」가 사라졌다 — 한도는 이 폭에서도 "
                              "판단에 쓴다" % (name, want))


class TheRuleSaysSo(unittest.TestCase):
    """브라우저 없이도 도는 검사 — 계약을 규칙 한 줄로 못박는다."""

    @classmethod
    def setUpClass(cls):
        cls.css = open(os.path.join(WEB, "css", "header.css"), encoding="utf-8").read()

    def test_the_chip_itself_is_no_longer_nowrap(self):
        m = re.search(r"\.usagechip\{([^}]*)\}", self.css)
        self.assertIsNotNone(m, ".usagechip 규칙이 없다")
        self.assertNotIn("white-space:nowrap", m.group(1).replace(" ", ""),
                         "칩 전체가 nowrap 이다 — min-content 가 글자 전체 폭이라 "
                         "좁은 폭에서 판을 밀어낸다 (REQ-20260915-001-2n7g)")

    def test_the_segment_is_the_unbreakable_unit(self):
        self.assertRegex(self.css.replace(" ", ""),
                         r"\.usagechip\.useg\{[^}]*white-space:nowrap",
                         "덩이(.useg)가 nowrap 이 아니다 — 「5h」와 숫자가 갈린다")

    def test_the_mail_text_has_a_box_of_its_own(self):
        """메일 글자가 제 상자(`.addr`)에 든다 (REQ-20260916-012-2n7g).

        마크와 한 덩이에 살면서 따로 물리려면 글자에 상자가 있어야 한다.
        """
        js = open(os.path.join(WEB, "app", "usage.js"), encoding="utf-8").read()
        self.assertIn('class="addr"', js,
                      "메일 글자에 상자가 없다 — 좁은 폭에서 글자만 빼고 "
                      "「값이 낡았다」 마크를 남길 길이 없어진다")

    def test_the_phone_rule_is_not_a_clamp(self):
        """좁은 폭 규칙이 칩을 한 줄로 묶지 않는다 — 그 길이 이 파일의 사고였다."""
        tab = open(os.path.join(WEB, "css", "tablet.css"), encoding="utf-8").read()
        phone = tab[tab.index("@media (max-width:560px)"):]
        for bad in ("white-space:nowrap", "text-overflow:ellipsis"):
            self.assertNotIn(
                bad.replace(" ", ""),
                re.sub(r"/\*.*?\*/", "", phone, flags=re.S).replace(" ", ""),
                "손전화 폭 규칙에 「%s」가 있다 — 좁혀서 자르는 대신 다른 자리에 "
                "있는 것을 던다 (REQ-20260915-001-2n7g 의 뿌리)" % bad)


if __name__ == "__main__":
    unittest.main()
