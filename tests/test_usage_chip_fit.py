"""사용량 칩은 머리글 밖으로 나가지 않는다 (REQ-20260915-001-2n7g).

주인이 맥 Safari 26.4 에서 본 것: 창을 400px 로 줄이면 문서에 9px 가로 넘침이
생기고(innerWidth 400 · scrollWidth 409), 머리글 오른쪽의
「claude01.pfe@dev.itcen.com · 5h 29% · wk 34% · fable 37%」 끝이 잘렸다.

뿌리는 `.usagechip{white-space:nowrap}` 이다. nowrap 인 조각의 min-content 폭은
**글자 전체 폭**(393px)이고, flex 항목의 `min-width:auto` 가 그 아래로 줄이는
것을 막는다 — 머리글에 남은 폭(400 - 좌우 안여백 44 = 356px)보다 넓으니 상자가
판을 밀어내고, 문서 전체가 가로로 넘친다.

고침은 **접히는 단위**를 바꾸는 것이다. 칩 전체를 못 접게 하는 대신 덩이
(`.useg`)마다 nowrap 을 주어 「5h 29%」의 이름과 숫자는 갈리지 않게 하고, 덩이
사이에서만 접는다. 이어짐을 알리는 `·` 는 앞 덩이 **끝**에 붙어, 접힌 줄이
언제나 이름으로 시작한다.

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
from webasset import parts

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")

MAIL = "claude01.pfe@dev.itcen.com"
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
    js = (_fn(const, "mk") + "\n" + _fn(usage, "renderUsageChip") + "\n"
          + _fn(notice, "renderWhoami") + "\n" + r"""
const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const $ = sel => document.querySelector(sel);
const asUser = "";
const s9cmd = c => "s9 " + c;
window.__draw = mail => {
  renderUsageChip(document.getElementById("usage-chip"), {email: mail, limits: [
    {kind: "session", percent: 29}, {kind: "weekly_all", percent: 34},
    {kind: "weekly_scoped", percent: 37, scope_name: "Fable"}]});
  // 신원 줄도 실물이 그린다 — 같은 기둥을 나눠 쓰는 이웃이고, 좁은 폭에서
  // 밀려 나가는 까닭도 같다. 흉내 낸 글자로 채우면 그 갈래를 못 잡는다.
  window.__whoami = {user: "nicehugepark", machine: "Seongjinui-Macmini.local",
                     os: "macOS", root: "/Users/seongjinpark/section9", role: "owner"};
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
  const segs = [...el.querySelectorAll('.useg')].map(s => ({
    text: s.textContent.replace(/\\s+/g, ' ').trim(),
    lines: rows(s.getClientRects()),
    right: +Math.max(...[...s.getClientRects()].map(r => r.right)).toFixed(1)}));
  const r = el.getBoundingClientRect();
  return {innerWidth: window.innerWidth,
          scrollWidth: se.scrollWidth,
          railRight: +railRight.toFixed(1),
          chipRight: +r.right.toFixed(1),
          chipHeight: +r.height.toFixed(1),
          chipLines: rows([...el.querySelectorAll('.useg')]
                          .flatMap(s => [...s.getClientRects()])),
          whoRight: +who.getBoundingClientRect().right.toFixed(1),
          segs};
})()
"""

CASES = (
    ("wide", WIDE, "ledger", MAIL),
    ("narrow", NARROW, "ledger", MAIL),
    ("tight", TIGHT, "ledger", MAIL),
    ("narrow_long_mail", NARROW, "ledger", LONG_MAIL),
    ("narrow_soft", NARROW, "soft", MAIL),
)
# 자리가 모자라 실제로 접혀야 하는 갈래 — 넘치는 대신 접었는지 여기서 본다
MUST_FOLD = ("tight", "narrow_long_mail", "narrow_soft")

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
        for name, (w, h), skin, mail in CASES:
            ws.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
                    deviceScaleFactor=1, mobile=False)
            ws.eval("document.documentElement.dataset.skin=%r" % skin)
            ws.eval("window.__draw(%r)" % mail)
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
        for name, _, _, _ in CASES:
            d = self.data[name]
            self.assertLessEqual(
                d["scrollWidth"], d["innerWidth"],
                "%s: 문서가 가로로 %dpx 넘쳤다 (scrollWidth %d · innerWidth %d) — "
                "칩이 판을 밀어낸다"
                % (name, d["scrollWidth"] - d["innerWidth"],
                   d["scrollWidth"], d["innerWidth"]))

    def test_the_chip_ends_inside_the_toolbar(self):
        """칩의 오른끝이 툴바의 안쪽 오른변 안이다 — 안여백은 남는 자리가 아니다."""
        for name, _, _, _ in CASES:
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

    def test_a_narrow_window_folds_instead_of_clipping(self):
        """자리가 모자라면 잘리는 대신 접힌다 — goal 이 허용한 두 갈래 중 하나.

        한 줄인 채로 넘치지도 않았다면 글자가 상자 밖으로 새거나 잘린 것이다.
        """
        for name in MUST_FOLD:
            d = self.data[name]
            self.assertGreater(
                d["chipLines"], 1,
                "%s: 칩이 한 줄 그대로다 — 들어갈 자리가 없는데 접지 않았다"
                % name)

    def test_a_segment_never_splits(self):
        """「5h 29%」의 이름과 숫자가 갈리지 않는다 — 덩이 안은 nowrap 이다."""
        for name, _, _, mail in CASES:
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
        """접느라 글자를 버리지 않았다 — 계정·5h·wk·모델이 모두 선다."""
        text = " ".join(s["text"] for s in self.data["tight"]["segs"])
        for want in (MAIL, "5h", "29%", "wk", "34%", "fable", "37%"):
            self.assertIn(want, text, "칩에서 「%s」가 사라졌다" % want)


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


if __name__ == "__main__":
    unittest.main()
