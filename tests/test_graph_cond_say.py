"""관계도가 걸려 있는 종류 조건을 말한다 (REQ-20260909-066-62x6).

사용자가 본 것: Docs 목록에서 「질문」만 골라 읽다가 관계도로 오니 범례는 전부
켜져 있는데 질문만 그려졌다 — 「전체 노드를 다 보게 되어있는데도 질문 노드들만
나타나는것 같다. 의도된건가?」

의도된 것이 맞다. 헤더의 종류 조건은 탭을 가로질러 함께 걸리는 공용 조건이다.
다만 관계도에는 그 조건이 보이는 자리가 없었다 — Docs 목록에서는 고른 값이
목록 위에 그대로 보이지만 관계도에는 점만 있고, 빈 화면이 아니어서 이유를
말하는 안내(gempty)도 서지 않는다. 그래서 「전체를 보는데 질문만 나온다」로
읽혔다. 고칠 것은 조건이 아니라 **화면의 침묵**이다.

이 시험은 소스 글자를 대조하지 않는다. 실브라우저를 띄우고 헤더의 종류 조건을
실제로 바꾼 뒤, 그 줄이 서는지·눌러서 되돌아가는지를 화면에서 잰다.

  S1 종류 조건이 걸리면 범례 아래 한 줄이 선다 (종류·고른 값·지웠을 때의 건수·손잡이).
  S2 손잡이를 누르면 조건이 풀리고 줄이 사라지며 전체가 다시 보인다.
  S3 조건이 없으면 그 줄은 서지 않는다.
  S4 빈 화면 안내가 이미 같은 조건을 범인으로 지목했으면 같은 말을 두 번 하지 않는다.
  S5 이번에 말하는 조건은 종류 하나다 — 사용자 조건은 이 줄을 세우지 않는다.

실행: python3 tests/ graph_cond_say
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
  const el = document.querySelector('#view .gcond');
  const b = el ? el.querySelector('.gcondx') : null;
  const ef = document.querySelector('#view .gempty [data-gfix]');
  return {line: !!el,
          text: el ? el.textContent.replace(/\s+/g, " ").trim() : "",
          btn: b ? b.textContent.trim() : "",
          btnTag: b ? b.tagName : "",
          type: document.querySelector('#f-type').value,
          rows: filtered(false).length,
          total: catalog.length,
          empty: !!document.querySelector('#view .gempty'),
          efix: ef ? ef.textContent.trim() : "",
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


class TheGraphSaysWhatIsFiltering(unittest.TestCase):
    """조건이 걸린 채 열린 관계도는 그 조건을 화면에서 말하고 되돌릴 손을 준다."""

    out = None
    srv = None
    proc = None
    ws = None
    prof_wsl = None
    marker = None
    win = False

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path()
        if chrome is None:
            raise unittest.SkipTest("실브라우저 미검증 — Chrome/Edge 를 찾지 못했다")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**os.environ, "S9_ROOT": ROOT, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.marker = "s9gcond-%d" % os.getpid()
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
        # 관계도에 선다.
        cls.await_(js('document.querySelector(\'header [data-tab="graph"]\').click();\n'
                      + (WAIT_SEL % "'#gcanvas'") + "\nreturn true;"))

        # S3 — 조건이 없으면 줄이 없다.
        o["plain"] = cls.await_(js((SLEEP % 150) + "\nreturn " + READ + ";"))

        # S1 — 종류를 「질문」으로 좁히면 그 사실이 화면에 선다.
        o["typed"] = cls.await_(js(
            (PICK % ("#f-type", '"question"')) + "\n"
            + (WAIT_SEL % "'#view .gcond'") + "\nreturn " + READ + ";"))

        # S2 — 손잡이를 실제로 눌러 되돌린다.
        o["cleared"] = cls.await_(js(
            (CLICK % "'#view .gcond .gcondx'") + "\n"
            + (WAIT_GONE % "'#view .gcond'") + "\nreturn " + READ + ";"))

        # S4 — 빈 화면 안내가 이미 그 조건을 범인으로 지목한 자리.
        #      종류를 질문으로 좁힌 뒤 범례에서 질문을 끄면 그릴 것이 없어지고,
        #      거기서 요청을 켜면 안내가 「종류 조건이 걸려 있다」고 말한다.
        o["blamed"] = cls.await_(js(
            (PICK % ("#f-type", '"question"')) + "\n"
            + (WAIT_SEL % "'#view .gcond'") + "\n"
            + (CLICK % "'#view [data-gtype=\"question\"]'") + "\n" + (SLEEP % 120)
            + (CLICK % "'#view [data-gtype=\"request\"]'") + "\n" + (SLEEP % 120)
            + (CLICK % "'#view [data-gtype=\"request\"]'") + "\n"
            + (WAIT_SEL % "'#view .gempty'") + "\nreturn " + READ + ";"))
        # 범례를 원래대로 되돌리고 조건도 푼다.
        cls.await_(js(
            (CLICK % "'#view [data-gfix]'") + "\n" + (SLEEP % 200)
            + 'if (!gtypes.has("question")) '
            + 'document.querySelector(\'#view [data-gtype="question"]\').click();\n'
            + (WAIT_SEL % "'#gcanvas'") + "\nreturn true;"))

        # S5 — 사용자 조건은 이번에 말하지 않는다 (고를 사람이 있을 때만 잰다).
        o["user_only"] = cls.await_(js(
            'const u = document.querySelector("#f-user");\n'
            'const opt = [...u.options].map(o => o.value).filter(Boolean)[0];\n'
            'if (!opt) return {skip: true};\n'
            'u.value = opt; u.dispatchEvent(new Event("input", {bubbles: true}));\n'
            + (SLEEP % 250) + "\nconst r = " + READ + ";\n"
            'u.value = ""; u.dispatchEvent(new Event("input", {bubbles: true}));\n'
            "return r;"))

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
    def test_the_graph_says_the_type_condition(self):
        """종류 조건이 걸린 관계도는 그 조건과 되돌릴 손을 화면에 세운다."""
        with self.subTest("no_condition_no_line"):                    # S3
            d = self.out["plain"]
            self.assertTrue(d["canvas"], "관계도가 그려지지 않았다")
            self.assertFalse(d["line"],
                             "조건이 없는데 조건 줄이 섰다: %r" % d["text"])

        with self.subTest("the_condition_is_on_screen"):              # S1
            d = self.out["typed"]
            self.assertTrue(d["line"], "종류 조건을 걸었는데 화면이 아무 말도 없다")
            self.assertIn("종류 조건", d["text"])
            self.assertIn("question", d["text"], "고른 값이 그대로 보이지 않는다")
            self.assertIn("지우면", d["text"], "되돌리면 어떻게 되는지 말하지 않는다")
            self.assertIn(str(d["total"]), d["text"],
                          "지웠을 때의 건수(%d)를 말하지 않는다: %r"
                          % (d["total"], d["text"]))
            self.assertEqual(d["btn"], "종류 조건 지우기")
            self.assertEqual(d["btnTag"], "BUTTON",
                             "손잡이가 진짜 버튼이 아니면 키보드로 닿지 않는다")
            self.assertTrue(d["canvas"], "조건 줄이 관계도를 밀어냈다")
            self.assertLess(d["rows"], d["total"], "조건이 실제로 좁히지 않았다")

        with self.subTest("clearing_brings_everything_back"):         # S2
            d = self.out["cleared"]
            self.assertEqual(d["type"], "", "손잡이를 눌렀는데 조건이 남아 있다")
            self.assertFalse(d["line"], "조건을 지웠는데 줄이 남아 있다")
            self.assertEqual(d["rows"], d["total"],
                             "조건을 지웠는데 전체가 돌아오지 않았다")
            self.assertTrue(d["canvas"], "되돌린 뒤 관계도가 사라졌다")

        with self.subTest("no_saying_the_same_thing_twice"):           # S4
            d = self.out["blamed"]
            self.assertTrue(d["empty"], "빈 화면 안내가 서지 않아 잴 수가 없다")
            self.assertEqual(d["efix"], "종류 조건 지우기",
                             "안내가 종류 조건을 범인으로 지목하지 않았다")
            self.assertFalse(d["line"],
                             "안내가 이미 말한 조건을 줄이 또 말한다: %r" % d["text"])

        with self.subTest("only_the_type_condition_speaks"):            # S5
            d = self.out["user_only"]
            if d.get("skip"):
                self.skipTest("고를 사용자가 없어 재지 못했다")
            self.assertFalse(d["line"],
                             "이번에 말하는 조건은 종류뿐인데 사용자 조건이 줄을 세웠다: %r"
                             % d["text"])


if __name__ == "__main__":
    unittest.main()
