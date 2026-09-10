"""관계도는 Docs 의 종류 조건에 끌려가지 않는다 (REQ-20260910-003-62x6).

주인이 본 것(캡처 2026-09-10 08:06): 관계도 범례의 `request` 가 켜져 있는데
화면에는 질문 노드만 있었다. 범인은 헤더의 종류 조건 — Docs 에서 고른
`question` 이 탭을 가로질러 관계도에도 걸려 있었다.

어제(REQ-20260909-066)는 이것을 「의도된 동작」으로 두고 화면에 「지금 종류
조건이 걸려 있다」는 안내 줄만 세웠다. 주인의 판정은 반대였다 —
「docs탭과 연동하지 마라. 서로 다른 탭이잖아.」 조건을 설명해야 하는 화면은
이미 진 화면이고, 관계도에는 종류를 고르는 손잡이가 이미 있다(범례). 한 축에
손잡이가 둘이면 보이는 쪽을 켜도 안 보이는 쪽이 이긴다.

그래서 관계도에서는 그 조건이 **걸리지도 보이지도 않는다.** 값은 지우지
않는다 — Docs 로 돌아가면 고른 종류가 그대로 살아 있다(Board 가 이미 쓰는
규칙, REQ-20260826-006).

이 시험은 소스 글자를 대조하지 않는다. 실브라우저를 띄우고 Docs 에서 종류를
실제로 고른 뒤 관계도로 건너가, 무엇이 그려지고 무엇이 사라지는지 화면에서 잰다.

  G1 Docs 에서 종류를 고르면 목록이 그 종류로 좁혀진다 (조건은 살아 있다).
  G2 관계도로 가면 다른 종류의 노드가 그대로 보인다 — 조건이 걸리지 않는다.
  G3 관계도에서는 종류 고르개가 보이지 않는다 — 한 축에 손잡이 하나.
  G4 걸리지 않는 조건을 말하지 않는다 — 조건 안내 줄이 서지 않는다.
  G5 Docs 로 돌아가면 고른 종류가 그대로다 — 값은 지우지 않고 적용만 건너뛴다.

실행: python3 tests/ graph_type_axis
"""
import json
import os
import subprocess
import time
import unittest
import urllib.error
import urllib.request

from cdpreal import WS, chrome_path, reclaim, wait_ready
from portpool import free_port, wait_server

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")

# 화면이 지금 말하는 것 — 한 번에 뜬다. 줄의 글자는 사람이 읽는 그대로 본다.
READ = r"""
(() => {
  const ty = document.querySelector('#f-type');
  const rows = (typeof filtered === 'function') ? filtered() : [];
  const kinds = {};
  rows.forEach(r => { kinds[r.type] = (kinds[r.type] || 0) + 1; });
  const drawn = {};
  if (typeof gtypes !== 'undefined')
    rows.filter(r => gtypes.has(r.type))
        .forEach(r => { drawn[r.type] = (drawn[r.type] || 0) + 1; });
  return {typeVal: ty.value,
          typeShown: !ty.hidden,
          cond: !!document.querySelector('#view .gcond'),
          condText: (document.querySelector('#view .gcond') || {}).textContent || "",
          kinds: kinds,
          drawn: drawn,
          rows: rows.length,
          total: catalog.length,
          legendOn: [...document.querySelectorAll('#view [data-gtype]')]
            .filter(e => !/\boff\b/.test(e.className)).map(e => e.dataset.gtype),
          canvas: !!document.querySelector('#gcanvas')};
})()
""".strip()

# 고정 sleep 으로 기다리지 않는다 — 기계가 느린 날 그 숫자가 곧 간헐 실패다.
WAIT_SEL = ('for (let i = 0; i < 160; i++){ '
            'if (document.querySelector(%s)) break; '
            'await new Promise(r => setTimeout(r, 50)); }')
WAIT_GONE = ('for (let i = 0; i < 160; i++){ '
             'if (!document.querySelector(%s)) break; '
             'await new Promise(r => setTimeout(r, 50)); }')
SLEEP = "await new Promise(r => setTimeout(r, %d));"

# 사람이 고르는 그대로 — 값을 넣고 컨트롤이 바뀌었다고 알린다.
PICK = ('(() => { const el = document.querySelector("%s"); el.value = %s;'
        ' el.dispatchEvent(new Event("input", {bubbles: true})); return true; })();')
CLICK = '(document.querySelector(%s).click(), true);'


def js(body):
    """비동기 조각 — 브라우저 안에서 순서대로 실행하고 마지막 값을 돌려준다."""
    return "(async () => {\n%s\n})()" % body


class TheGraphKeepsItsOwnTypeAxis(unittest.TestCase):
    """관계도의 종류는 범례가 정한다 — 다른 탭의 조건이 끼어들지 않는다."""

    out = None
    srv = None
    proc = None
    ws = None
    prof_wsl = None
    marker = None
    win = False

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path(pixel_contract=False)
        if chrome is None:
            raise unittest.SkipTest("실브라우저 미검증 — Chrome/Edge 를 찾지 못했다")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**os.environ, "S9_ROOT": ROOT, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.marker = "s9gtype-%d" % os.getpid()
        cls.win = chrome.startswith("/mnt/")
        cls.prof_wsl = (("/mnt/c/Temp/" + cls.marker) if cls.win
                        else "/tmp/" + cls.marker)
        prof_arg = ("C:\\Temp\\" + cls.marker) if cls.win else cls.prof_wsl
        if cls.win:
            os.makedirs("/mnt/c/Temp", exist_ok=True)
        try:
            wait_server(cls.port)
            cls.proc = subprocess.Popen(
                [chrome, "--headless=new", "--disable-gpu",
                 "--user-data-dir=" + prof_arg, "--no-first-run",
                 "--no-default-browser-check", "--disable-extensions",
                 "--disable-background-networking", "--remote-debugging-port=0",
                 "--window-size=1440,900",
                 "http://127.0.0.1:%d/" % cls.port],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            dev = os.path.join(cls.prof_wsl, "DevToolsActivePort")
            cdp = None
            for _ in range(160):
                if os.path.exists(dev):
                    try:
                        with open(dev, encoding="utf-8") as f:
                            cdp = int(f.read().splitlines()[0])
                        break
                    except (ValueError, IndexError, OSError):
                        pass
                time.sleep(0.25)
            if cdp is None:
                raise ConnectionError("DevToolsActivePort 미출현")
            pages = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % cdp, timeout=10).read())
            page = next(p for p in pages if p.get("type") == "page")
            cls.ws = WS(page["webSocketDebuggerUrl"])
            # 볼 자리는 관계도 판이다 — 그것을 measure() 가 눌러서 세운다.
            wait_ready(cls.ws, needs=("whoami", "catalog"))
            cls.out = {}
            cls.measure()
            unmeasured = [k for k, v in cls.out.items() if v is None]
        except (ConnectionError, StopIteration, OSError, RuntimeError,
                urllib.error.URLError) as e:
            cls.tearDownClass()
            raise unittest.SkipTest("실브라우저 미검증 — %r" % e)
        if unmeasured:
            cls.tearDownClass()
            raise AssertionError("판은 섰는데 재지 못했다: %s"
                                 % ", ".join(unmeasured))

    # ---- 재기 -------------------------------------------------------------
    @classmethod
    def await_(cls, expr):
        r = cls.ws.call("Runtime.evaluate", expression=expr,
                        returnByValue=True, awaitPromise=True)
        ex = r.get("exceptionDetails")
        if ex:
            raise RuntimeError("브라우저 안에서 실패: %s"
                               % (ex.get("exception", {}).get("description")
                                  or ex.get("text")))
        return r.get("result", {}).get("value")

    @classmethod
    def measure(cls):
        o = cls.out
        # Docs 에서 종류를 「질문」으로 고른다 — 사람이 하는 그대로.
        cls.await_(js('document.querySelector(\'header [data-tab="docs"]\').click();\n'
                      + (SLEEP % 250) + "\nreturn true;"))
        o["docs"] = cls.await_(js(
            (PICK % ("#f-type", '"question"')) + "\n" + (SLEEP % 300)
            + "\nreturn " + READ + ";"))

        # 그 상태로 관계도에 건너간다.
        o["graph"] = cls.await_(js(
            'document.querySelector(\'header [data-tab="graph"]\').click();\n'
            + (WAIT_SEL % "'#gcanvas'") + "\n" + (SLEEP % 250)
            + "\nreturn " + READ + ";"))

        # 되돌아오면 고른 값이 살아 있나.
        o["back"] = cls.await_(js(
            'document.querySelector(\'header [data-tab="docs"]\').click();\n'
            + (SLEEP % 350) + "\nconst r = " + READ + ";\n"
            + (PICK % ("#f-type", '""')) + "\nreturn r;"))

    @classmethod
    def tearDownClass(cls):
        if cls.ws is not None:
            try:
                cls.ws.close()
            except OSError:
                pass
            cls.ws = None
        if cls.proc is not None:
            try:
                cls.proc.terminate()
            except OSError:
                pass
            cls.proc = None
        if cls.marker:
            reclaim(cls.marker, cls.win)
        if cls.srv is not None:
            cls.srv.terminate()
            try:
                cls.srv.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.srv.kill()
            cls.srv = None
        if cls.prof_wsl:
            import shutil
            shutil.rmtree(cls.prof_wsl, ignore_errors=True)

    # ---- 판정 -------------------------------------------------------------
    def test_the_graph_keeps_its_own_type_axis(self):
        """관계도의 종류는 범례가 정한다 — Docs 의 조건이 끼어들지 않는다."""
        with self.subTest("the_condition_still_narrows_docs"):        # G1
            d = self.out["docs"]
            self.assertEqual(d["typeVal"], "question", "종류를 고르지 못했다")
            self.assertTrue(d["typeShown"], "Docs 에서 종류 고르개가 사라졌다")
            self.assertLess(d["rows"], d["total"],
                            "종류를 골랐는데 Docs 목록이 좁혀지지 않았다")
            self.assertEqual(set(d["kinds"]), {"question"},
                             "Docs 목록에 질문 아닌 것이 남았다: %r" % d["kinds"])

        with self.subTest("the_graph_ignores_it"):                     # G2
            d = self.out["graph"]
            self.assertTrue(d["canvas"], "관계도가 그려지지 않았다")
            self.assertEqual(d["typeVal"], "question",
                             "값이 지워졌다 — 적용만 건너뛰어야 한다")
            self.assertEqual(d["rows"], d["total"],
                             "관계도가 여전히 종류로 좁혀져 있다 (%d/%d)"
                             % (d["rows"], d["total"]))
            self.assertIn("request", d["drawn"],
                          "범례의 요청이 켜져 있는데 요청 노드가 그려지지 않았다: %r"
                          % d["drawn"])
            self.assertIn("request", d["legendOn"], "범례에서 요청이 꺼져 있어 잴 수 없다")

        with self.subTest("no_second_handle_for_the_same_axis"):       # G3
            self.assertFalse(self.out["graph"]["typeShown"],
                             "관계도에 종류 고르개가 남아 있다 — 한 축에 손잡이가 둘이면 "
                             "보이는 쪽(범례)을 켜도 안 보이는 쪽이 이긴다")

        with self.subTest("it_does_not_talk_about_a_condition_it_ignores"):  # G4
            d = self.out["graph"]
            self.assertFalse(d["cond"],
                             "걸리지도 않는 조건을 화면이 말한다: %r" % d["condText"])

        with self.subTest("docs_still_remembers_the_pick"):             # G5
            d = self.out["back"]
            self.assertEqual(d["typeVal"], "question",
                             "Docs 로 돌아왔더니 고른 종류가 사라졌다")
            self.assertTrue(d["typeShown"], "Docs 에서 종류 고르개가 돌아오지 않았다")
            self.assertLess(d["rows"], d["total"],
                            "값은 남았는데 목록이 다시 좁혀지지 않았다")


if __name__ == "__main__":
    unittest.main()
