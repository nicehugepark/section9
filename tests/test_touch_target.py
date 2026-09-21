"""손전화 폭에서는 손끝이 과녁이다 — 44px (REQ-20260916-015-2n7g).

frontend-developer 가 REQ-20260916-012-2n7g 를 하며 곁에서 봤다: 400px 에서
`.usagechip` 의 누를 수 있는 높이가 12px 다. s9-design 7절이 스스로 정한 최소치
44x44 의 4분의 1 이고, 전부터 그랬다.

전과 달라진 것은 **그 칩이 이제 무엇을 여는 손잡이**라는 점이다. 012 에서
손전화 폭의 머리글이 두 줄로 줄면서 메일이 줄에서 물러났고, 메일을 보는 길은
그 칩을 누르는 것이 되었다. 누르기 어려운 12px 이 이제 그 글자에 닿는 단
하나의 손잡이다.

**한 자리만 키우면 그 자리만 다르게 보인다.** 그래서 이 시험이 재는 것은 칩
하나가 아니라 그 폭의 머리글에 선 손잡이 **전부**다 — 탭 여덟 · 검색 · 거르개
넷 · 체크 둘 · 칩.

---- 값을 바꾸지 않고 과녁만 얻는다 ----

control.css 가 이미 그 길을 놓았다(sm 급): 상자를 키우면 그 줄이 통째로 자라니
**겹판(`::after`, `position:absolute`)으로 과녁만 얹는다**. 겹판은 흐름 밖이라
줄 높이를 1px 도 안 건드린다. 그래서 44px 을 손전화 폭 전체에 주어도 012 가
26px 로 줄여 놓은 머리글은 그대로다 — 이 시험의 회귀 갈래가 그것을 지킨다.

재는 것은 규칙에 무엇이 적혔는지가 아니라 **브라우저가 실제로 앉힌 과녁**이다.
화소나 반화소를 재지 않으므로(재는 것은 과녁이 44 이상인가·줄이 늘었나) 맥
브라우저로도 잰다.

실행: python3 tests/ touch_target
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
CSS = os.path.join(WEB, "css")

MAIL = "agent01.pfe@dev.example.com"
PHONE = (400, 820)      # 주인이 잰 그 창
DESK = (1440, 900)

# s9-design 7절이 정한 최소치. iOS·Android 의 손끝 권고와 같은 값이다.
TOUCH = 44
# 손끝 눈금이 서는 폭 — 목록·판이 쌓이고 머리글이 두 줄로 주는 그 눈금과 같다
# (tablet.css). 눈금을 새로 만들지 않는다.
PHONE_MAX = 560
# 마우스 폭의 눈금 셋 — 여기는 부풀리지 않는다 (test_control_scale 과 같은 값).
DESK_GRADES = {"--ctl-lg": 36.0, "--ctl-md": 27.0, "--ctl-sm": 20.0}


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
window.__draw = () => {
  renderUsageChip(document.getElementById("usage-chip"), {email: %s, stale: false,
    limits: [{kind: "session", percent: 29}, {kind: "weekly_all", percent: 34},
             {kind: "weekly_scoped", percent: 37, scope_name: "Fable"}]});
  window.__whoami = {user: "hong", machine: "Mac-mini.local",
                     os: "macOS", root: "/Users/hgpark/section9", role: "owner"};
  renderWhoami();
};
""" % json.dumps(MAIL))
    return ('<!doctype html><html lang="ko" data-theme="light" data-skin="ledger"'
            ' data-density="normal"><head><meta charset="utf-8">'
            "<style>%s</style></head><body>%s"
            "<main><p class=\"count\" id=\"count\"></p><div id=\"view\"></div></main>"
            "<script>%s</script></body></html>" % (css, header, js))


# 과녁은 상자가 아니라 **손끝이 닿는 자리**다. 겹판(`::after`, absolute)은
# 흐름 밖에서 상자보다 넓게 펴지고, 그 겹판이 이웃 손잡이 위에 얹히면 이웃의
# 과녁은 그만큼 **줄어든다** — 규칙만 읽어서는 어느 쪽도 안 보인다.
#
# 그래서 규칙 대신 **누른다**: 손잡이 한가운데에서 위아래로 한 화소씩 짚어
# 나가며 `elementFromPoint` 가 아직 그 손잡이를 주는지 본다. 한 점은 한
# 요소의 것이므로 겹침은 저절로 드러난다 — 남의 겹판에 덮인 손잡이는 제
# 과녁이 짧게 나온다. 체크 상자는 제 라벨(`.chk`)이 감싸므로 라벨이 과녁이고,
# 안의 input 은 따로 세지 않는다.
MEASURE_JS = """
(() => {
  const head = document.querySelector('header');
  const sel = ['.tabs button', '.hrow2 input[type="text"]', '.hrow2 select',
               '.hrow2 .chk', '#usage-chip'].join(',');
  const seen = n => n.getClientRects().length > 0;
  const REACH = 70;          // 44 를 넉넉히 넘는 자 — 값이 아니라 한계다
  // 가로로 미는 줄 안의 손잡이는 쉼 자리에서 줄 밖에 있을 수 있다
  // (REQ-20260916-009-62x6). 011 이 손전화 폭의 탭 줄을 미는 줄로 만들었고,
  // 400px 에서는 여덟 중 다섯만 줄 안에 선다 — 나머지 셋은 상자가 36px 인데
  // 과녁이 0 으로 나왔다. 0 은 「작다」가 아니라 「그 좌표에 없다」다:
  // elementFromPoint 는 잘려 나간 자리를 짚지 못한다. 손은 밀어서 만난다.
  // 그래서 재기 전에 그 줄을 밀어 손잡이를 안으로 들인다. 눈금은 그대로
  // 44px 이고, 밀어도 안 들어오는 손잡이는 여전히 0 이다 — 무를 것은 자
  // 가 아니라 자를 댈 자리다.
  const reveal = n => {
    for (let p = n.parentElement; p; p = p.parentElement) {
      if (p.scrollWidth > p.clientWidth + 1) {
        n.scrollIntoView({inline: 'nearest', block: 'nearest'});
        return;
      }
    }
  };
  const hit = n => {
    const r = n.getBoundingClientRect();
    const x = Math.round((r.left + r.right) / 2);
    const cy = Math.round((r.top + r.bottom) / 2);
    const mine = e => !!e && (e === n || n.contains(e));
    if (!mine(document.elementFromPoint(x, cy))) return 0;
    let top = cy, bot = cy;
    for (let y = cy - 1; y >= cy - REACH; y--) {
      if (!mine(document.elementFromPoint(x, y))) break;
      top = y;
    }
    for (let y = cy + 1; y <= cy + REACH; y++) {
      if (!mine(document.elementFromPoint(x, y))) break;
      bot = y;
    }
    return bot - top + 1;
  };
  const handles = [];
  for (const n of head.querySelectorAll(sel)) {
    if (!seen(n)) continue;
    reveal(n);
    const r = n.getBoundingClientRect();
    handles.push({
      name: (n.id ? '#' + n.id
             : (n.tagName.toLowerCase()
                + '.' + String(n.className || '').split(' ')[0])),
      text: (n.textContent || n.placeholder || '').replace(/\\s+/g, ' ')
              .trim().slice(0, 18),
      top: Math.round(r.top), box: +r.height.toFixed(1), target: hit(n)});
  }
  const chip = document.getElementById('usage-chip');
  const who = document.getElementById('whoami');
  const rows = ns => [...new Set([...ns].map(r => Math.round(r.top)))].length;
  const cs = getComputedStyle(document.documentElement);
  const grades = {};
  for (const k of ['--ctl-lg', '--ctl-md', '--ctl-sm'])
    grades[k] = parseFloat(cs.getPropertyValue(k));
  return {
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    headerHeight: +head.getBoundingClientRect().height.toFixed(1),
    chipBoxHeight: +chip.getBoundingClientRect().height.toFixed(1),
    chipLines: rows([...chip.querySelectorAll('.useg')]
                    .flatMap(s => [...s.getClientRects()])),
    whoLines: rows([...who.querySelectorAll('.wseg')]
                   .flatMap(s => [...s.getClientRects()])),
    grades, handles};
})()
"""

# 스킨을 둘 더 재는 까닭: 탭의 줄 틈은 스킨이 제 값을 적어 둔 자리다
# (`[data-skin="glass"] .tabs{gap:6px}` · soft 는 세로 메뉴라 `gap:3px`). 과녁이
# 겹치는지는 그 값에 걸리므로, 기본 스킨 하나만 재면 「고쳤다」가 한 스킨의
# 사실이 된다 — 벨트 글리프 때의 그 함정이다(s9-design).
# soft 도 이 폭에서는 다른 스킨과 같은 창으로 잰다 (REQ-20260916-009-62x6).
# 창을 1400px 로 길게 잡았던 까닭은 이 스킨의 셸이 왼쪽 세로 띠여서 탭 여덟이
# 세로로 쌓이고 사용량 칩이 400x820 의 밑끝에 걸렸기 때문인데, 이제 560px
# 이하에서는 그 셸을 접고 가로 머리글로 선다 — 쌓이는 것이 없으니 축을 열
# 까닭도 없다.
CASES = (("phone", PHONE, "ledger"), ("desk", DESK, "ledger"),
         ("phone_glass", PHONE, "glass"), ("phone_soft", PHONE, "soft"))
# 손끝이 오는 갈래 — 여기서만 눈금이 선다
TOUCH_CASES = ("phone", "phone_glass", "phone_soft")

_MEASURED = {}


def shared():
    if "err" in _MEASURED:
        raise unittest.SkipTest(_MEASURED["err"])
    if "data" in _MEASURED:
        return _MEASURED["data"]
    # 과녁 크기와 줄 수만 잰다 — 화소 계약 밖의 브라우저(맥)로도 잰다
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
    marker = "s9req916015-%d" % os.getpid()
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
        for name, (w, h), skin in CASES:
            ws.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
                    deviceScaleFactor=1, mobile=False)
            ws.eval("document.documentElement.dataset.skin=%r" % skin)
            ws.eval("window.__draw()")
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


class TheFingerFindsTheHandle(unittest.TestCase):
    data = None

    @classmethod
    def setUpClass(cls):
        cls.data = shared()

    def test_the_usage_chip_is_wide_enough_to_press(self):
        """손전화 폭에서 사용량 칩의 과녁이 44px 이상이다 — 이 건 그 자체.

        012 뒤로 메일을 보는 길은 이 칩을 누르는 것뿐이라, 누를 수 없으면
        그 글자에 닿을 길이 화면에 없다.
        """
        for case in TOUCH_CASES:
            chip = next(h for h in self.data[case]["handles"]
                        if h["name"] == "#usage-chip")
            self.assertGreaterEqual(
                chip["target"], TOUCH,
                "%s: 400px 에서 사용량 칩의 과녁이 %.1fpx 다 (상자 %.1fpx) — "
                "메일에 닿는 단 하나의 손잡이인데 손끝 눈금 %dpx 아래다"
                % (case, chip["target"], chip["box"], TOUCH))

    def test_every_handle_in_the_header_meets_the_same_scale(self):
        """한 자리만 키우면 그 자리만 다르게 보인다 — 머리글 손잡이 전부를 잰다."""
        for case in TOUCH_CASES:
            handles = self.data[case]["handles"]
            small = [h for h in handles if h["target"] < TOUCH]
            # 떨어진 것만이 아니라 **전부**를 싣는다 — 다음 사람이 이 폭에서
            # 무엇이 몇 px 인지 다시 재지 않아도 되게, 그리고 「그 자리만 다르게
            # 보이나」를 한눈에 견주게.
            self.assertFalse(
                small,
                "%s: 400px 머리글에 손끝 눈금(%dpx) 아래인 손잡이가 %d 개다: %s\n"
                "  — 그 폭의 손잡이 전부: %s"
                % (case, TOUCH, len(small),
                   ", ".join("%s %.1fpx" % (h["name"], h["target"])
                             for h in small),
                   ", ".join("%s%s y%d 상자 %.1f/과녁 %.1f"
                             % (h["name"],
                                (" 「%s」" % h["text"]) if h["text"] else "",
                                h["top"], h["box"], h["target"])
                             for h in sorted(handles,
                                             key=lambda x: x["target"]))))

    def test_the_target_does_not_grow_the_header(self):
        """과녁을 얹어도 사용량 줄·신원 줄은 각각 한 줄이다 (REQ-20260916-012-2n7g).

        겹판은 흐름 밖이라 줄 높이를 안 건드린다 — 상자를 키워 과녁을 얻으면
        012 가 50px 에서 26px 로 줄여 놓은 그 자리가 도로 부푼다.
        """
        d = self.data["phone"]
        self.assertEqual(d["chipLines"], 1,
                         "사용량이 %d 줄이다 — 과녁을 상자로 얻어 줄이 늘었나"
                         % d["chipLines"])
        self.assertEqual(d["whoLines"], 1,
                         "신원이 %d 줄이다" % d["whoLines"])
        self.assertLessEqual(
            d["chipBoxHeight"], 20,
            "사용량 칩의 **상자**가 %.1fpx 다 — 과녁은 겹판이 받아야 하고 "
            "상자는 글자 높이 그대로여야 한다" % d["chipBoxHeight"])
        # 012 가 「창의 47%」를 결함으로 세운 그 자리다. 실측 2026-09-16 기준
        # 310px(38%)이고, 과녁을 상자로 얻으면 칩 하나에 32px 이 붙어 곧바로
        # 되부푼다. 40% 는 지금 값과 012 가 문제로 삼은 값 사이의 선이다.
        self.assertLessEqual(
            d["headerHeight"], 0.40 * PHONE[1],
            "400x820 머리글이 %.1fpx (창의 %.0f%%) 다 — 과녁을 상자로 얻어 "
            "012 가 끌어내린 자리가 되부풀었나"
            % (d["headerHeight"], 100.0 * d["headerHeight"] / PHONE[1]))

    def test_the_document_never_overflows_sideways(self):
        """400px 에서 문서가 가로로 넘치지 않는다 (REQ-20260915-001-2n7g).

        겹판은 `left:0;right:0` 으로 제 상자 안에만 펴진다 — 가로로 넓히면
        그 폭이 다시 머리글을 밀어낸다.
        """
        for name, _, _ in CASES:
            d = self.data[name]
            self.assertLessEqual(
                d["scrollWidth"], d["innerWidth"],
                "%s: 문서가 가로로 %dpx 넘쳤다 (scrollWidth %d · innerWidth %d)"
                % (name, d["scrollWidth"] - d["innerWidth"],
                   d["scrollWidth"], d["innerWidth"]))

    def test_a_mouse_width_keeps_the_three_grades(self):
        """마우스 폭의 눈금 셋은 그대로다 — 손끝 눈금은 손끝이 오는 폭의 것이다."""
        got = self.data["desk"]["grades"]
        for name, val in DESK_GRADES.items():
            with self.subTest(name):
                self.assertEqual(
                    got[name], val,
                    "1440px 에서 %s 가 %spx 다 — 마우스가 오는 폭까지 부풀렸다"
                    % (name, got[name]))


class TheTouchScaleLivesInOnePlace(unittest.TestCase):
    """손끝 눈금은 `--tap-min` 한 이름이고 그 값은 tablet.css 한 곳에서 켜진다.

    손잡이 높이가 16종이 된 길이 「저마다 제 값을 적은 것」이었다
    (control.css 머리말 · test_control_scale 과 같은 규율). 과녁 쪽에도 이미
    사전이 있었는데 — `--tap-min` 은 REQ-20260906-092 가 세웠다 — 사용량 칩만
    그 사전 밖에 있었다. 이 시험이 막는 것은 다음 손잡이가 또 밖에 서는 것이다.
    """

    def _read(self, name):
        with open(os.path.join(CSS, name), encoding="utf-8") as f:
            return f.read()

    def _strip(self, css):
        return re.sub(r"/\*[\s\S]*?\*/", "", css)

    def test_the_touch_scale_is_declared_once(self):
        """`--tap-min` 의 값은 tablet.css 에서만 갈리고 그 값이 44px 이다."""
        owner = []
        for fn in sorted(os.listdir(CSS)):
            if fn.endswith(".css") and "--tap-min:" in self._strip(self._read(fn)):
                owner.append(fn)
        self.assertEqual(
            owner, ["tablet.css"],
            "손끝 눈금의 값을 적은 파일이 %s 다 — 사전은 한 곳이다" % owner)
        tab = self._strip(self._read("tablet.css"))
        self.assertRegex(
            tab, r"--tap-min:\s*%dpx" % TOUCH,
            "손끝 눈금이 %dpx 로 서지 않는다 — s9-design 7절이 정한 값이다" % TOUCH)

    def test_the_new_rules_call_the_scale_by_name(self):
        """이번에 선 과녁 규칙들은 날 px 가 아니라 눈금 이름을 부른다.

        칩의 겹판·탭 줄 사이 틈이 그것이다. 값을 손으로 적으면 눈금이 바뀔 때
        이 자리만 옛 값에 남는다.
        """
        tab = self._strip(self._read("tablet.css"))
        chip = re.search(r"\.usagechip::after\{([^}]*)\}", tab)
        self.assertIsNotNone(chip, "사용량 칩의 과녁 규칙이 없다")
        self.assertIn(
            "height:var(--tap-min)", chip.group(1),
            "칩의 과녁이 눈금을 이름으로 부르지 않는다: %r" % chip.group(1))
        tabs = re.search(r"\.tabs,\[data-skin\] \.tabs\{([^}]*)\}", tab)
        self.assertIsNotNone(
            tabs, "탭 줄 사이의 규칙이 없다 — 스킨과 같은 급으로 서야 그 스킨의 "
                  "틈(soft 3px · glass 6px)을 이긴다")
        self.assertIn(
            "var(--tap-y)", tabs.group(1),
            "접힌 탭 줄 사이가 눈금을 이름으로 부르지 않는다: %r" % tabs.group(1))

    def test_no_skin_or_density_redefines_the_touch_scale(self):
        """스킨·밀도는 재질과 여백을 말하고 과녁은 말하지 않는다."""
        for fn in sorted(os.listdir(CSS)):
            if not fn.endswith(".css"):
                continue
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}",
                                 self._strip(self._read(fn))):
                sel, dec = m.group(1).strip(), m.group(2).strip()
                if not re.search(r"--(ctl-(lg|md|sm)|tap-(min|y))\s*:", dec):
                    continue
                with self.subTest(fn + " :: " + sel[:60]):
                    self.assertNotIn("[data-skin", sel,
                                     "스킨이 과녁을 다시 정한다 (%s)" % fn)
                    self.assertNotIn("[data-density", sel,
                                     "밀도가 과녁을 다시 정한다 (%s) — 밀도는 "
                                     "여백을 줄이는 축이지 과녁을 깎는 축이 "
                                     "아니다" % fn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
