"""화면이 조각으로 갈라진 뒤에도 한 장으로 선다 (REQ-20260829-027).

`web/index.html` 은 14,792 줄이었다. 오늘 하루에만 네 팀이 이 파일에 붙었고,
서로를 덮지 않으려고 줄을 세워야 했다 — 한 기능을 고치려면 남의 자리를 열어야
했기 때문이다. 그래서 갈랐다: 껍데기(`web/index.html`) + `web/css/` + `web/app/`.

가르기가 만드는 새 실패 모드는 셋이고, 셋 다 **화면은 멀쩡해 보이면서** 무너진다.

  ① 조각이 사라진다. 껍데기가 부르는 파일이 없으면 그 기능만 조용히 죽는다.
  ② 조각이 고아가 된다. 아무도 안 부르는 파일이 남으면 다음 사람은 그것을
     고치고 화면이 안 바뀐다고 한다 — 오늘 워크트리에서 이미 겪은 종류다.
  ③ 껍데기가 다시 붓는다. 급할 때 규칙 한 줄을 `index.html` 에 인라인으로
     끼워 넣기 시작하면, 몇 주 뒤 이 작업은 없던 일이 된다.

실행: python3 tests/ web_split
"""
import os
import re
import shutil
import subprocess
import time
import unittest
import urllib.error
import urllib.request

import webasset

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
WEB = os.path.join(ROOT, "web")
SHELL = os.path.join(WEB, "index.html")

from portpool import free_port, wait_server  # noqa: E402

# 껍데기의 천장. 넉넉하되 "판이 하나 더 들어갈 만큼"은 아니다 — 이 숫자를
# 올려야 통과하는 변경이라면, 그것은 조각으로 갔어야 할 변경이다.
#
# 220 -> 270 (REQ-20260829-039): 조각 목록이 `<template>` 안으로 들어가고
# 묶음이 죽었을 때 낱개로 되돌리는 길이 생겼다. 이 둘은 **조각으로 갈 수 없는**
# 유일한 종류다 — 조각을 어떻게 부르는지를 정하는 코드가 그 조각 안에 있으면
# 자기가 안 왔을 때 아무 일도 못 한다. 그 밖의 이유로 이 숫자를 올리지 마라.
#
# 세는 자리를 고친다 (REQ-20260901-022): **부르는 줄은 껍데기의 무게가 아니다.**
# 이 천장이 막으려는 것은 "규칙이 껍데기로 되돌아오는 것"인데, 조각을 하나
# 늘리면 `<link>`·`<script src>` 가 한 줄 늘어 **옳게 한 사람이 걸린다** —
# 실제로 조각 하나를 새로 낸 변경이 271줄로 걸렸다. 규칙을 껍데기에 인라인으로
# 끼워 넣는 것은 여전히 그대로 걸린다(그 줄은 부르는 줄이 아니다).
# 44줄이 지금 부르는 줄이므로 껍데기 제 무게는 227줄이고, 천장은 그대로 둔다.
SHELL_MAX_LINES = 270


def shell_own_lines():
    """껍데기가 **제 몸으로** 진 줄 — 조각을 부르는 줄은 빼고 센다."""
    out = 0
    for line in shell().splitlines(True):
        if webasset.LINK_RE.match(line) or webasset.SRC_RE.match(line):
            continue
        out += 1
    return out


def shell():
    with open(SHELL, encoding="utf-8") as f:
        return f.read()


class Parts(unittest.TestCase):
    """① 부른 조각은 전부 있다 · ② 안 부른 조각은 없다."""

    def test_parts(self):
        """① 부른 조각은 전부 있다 · ② 안 부른 조각은 없다."""
        with self.subTest("s1_every_called_part_exists"):
            css, app = webasset.parts()
            self.assertTrue(css and app, "껍데기가 아무 조각도 부르지 않는다")
            missing = [f"css/{n}" for n in css
                       if not os.path.isfile(os.path.join(WEB, "css", n))]
            missing += [f"app/{n}" for n in app
                        if not os.path.isfile(os.path.join(WEB, "app", n))]
            self.assertEqual(missing, [], "껍데기가 없는 파일을 부른다")
        with self.subTest("s2_no_orphan_part"):
            css, app = webasset.parts()
            for sub, called in (("css", css), ("app", app)):
                on_disk = sorted(n for n in os.listdir(os.path.join(WEB, sub))
                                 if not n.startswith("."))
                self.assertEqual(sorted(called), on_disk,
                                 f"web/{sub}/ 의 파일과 껍데기가 부르는 목록이 다르다 "
                                 "— 아무도 안 부르는 조각은 고쳐도 화면이 안 바뀐다")
        with self.subTest("s2c_parts_are_declared_only_in_the_manifest"):
            src = shell()
            zones = re.findall(r"<template id=\"s9-parts-[\w-]+\">(.*?)</template>",
                               src, re.S)
            self.assertEqual(len(zones), 2,
                             "조각 목록 template 이 둘이 아니다 (css·app)")
            inside = "".join(zones)
            for m in re.finditer(r'^(<link rel="stylesheet" href="css/[\w.-]+">'
                                 r'|<script src="app/[\w.-]+"></script>)\s*$',
                                 src, re.M):
                self.assertIn(m.group(1), inside,
                              f"{m.group(1)} 이 목록 밖에 있다 — 이 조각만 두 번 돈다")
        with self.subTest("s2b_no_part_called_twice"):
            css, app = webasset.parts()
            for called in (css, app):
                self.assertEqual(len(called), len(set(called)),
                                 "같은 조각을 두 번 부른다 — 순서가 곧 계약인데 "
                                 "두 번 실행되면 그 계약이 깨진다")

class Assembled(unittest.TestCase):
    """이어 붙인 한 장이 가르기 전의 그 화면인가."""

    @classmethod
    def setUpClass(cls):
        cls.src = webasset.source()

    def test_s3_the_page_is_whole(self):
        for mark in ('"use strict";', ":root{", "boot();",
                     '<div id="view"></div>', "</html>"):
            self.assertIn(mark, self.src, f"이어 붙인 한 장에 {mark!r} 이 없다")

    def test_s3b_one_style_block_and_one_app_block(self):
        self.assertEqual(self.src.count("<style>"), 1)
        blocks = re.findall(r"<script[^>]*>(.*?)</script>", self.src, re.S)
        self.assertTrue(max(len(b) for b in blocks) > 300000,
                        "가장 큰 스크립트 덩어리가 화면 하나치가 안 된다")


class Shell(unittest.TestCase):
    """③ 껍데기가 다시 붓지 않는다."""

    def test_shell(self):
        """③ 껍데기가 다시 붓지 않는다."""
        with self.subTest("s4_shell_stays_thin"):
            n = shell_own_lines()
            self.assertLessEqual(
                n, SHELL_MAX_LINES,
                f"web/index.html 이 {n} 줄이다 — 규칙이 껍데기로 되돌아오고 있다. "
                "새 CSS 는 web/css/ 로, 새 JS 는 web/app/ 로 간다")
        with self.subTest("s4b_no_style_block_in_shell"):
            self.assertNotIn("<style>", shell(),
                             "껍데기에 <style> 이 생겼다 — 토큰·규칙의 자리는 "
                             "web/css/ 다 (스킨이 그 순서에 기대고 있다)")
        with self.subTest("s5_the_missing_parts_notice_is_inline"):
            src = shell()
            inline = re.findall(r"<script>(?!\s*</script>)(.*?)</script>", src, re.S)
            self.assertEqual(len(inline), 2,
                             "껍데기의 인라인 스크립트는 되찾기와 '조각을 못 받았다' "
                             "알림 둘뿐이어야 한다")
            retry, notice = inline
            self.assertIn("__S9_RETRY", retry, "첫 인라인은 되찾기여야 한다")
            self.assertLess(src.index("__S9_RETRY"), src.index('href="css/'),
                            "되찾기가 규칙 조각보다 뒤에 선다 — 그러면 <head> 에서 "
                            "잘린 규칙의 실패를 못 듣는다")
            self.assertIn("__S9_APP_READY", notice)
            self.assertIn("--bg", notice, "모양(css)이 왔는지도 함께 봐야 한다")
        with self.subTest("s5c_the_net_catches_both_kinds_and_gives_up_out_loud"):
            src = shell()
            for mark, why in (
                    ("120", "REQ-20260829-019 이 실측한 첫 간격(120ms)이 없다"),
                    ("320", "둘째 간격(320ms)이 없다"),
                    ("800", "셋째 간격(800ms)이 없다"),
                    ("Math.random", "지터가 없다 — 같은 순간에 다시 몰리면 또 무너진다"),
                    ('"?r=" + n', "재시도 주소를 안 가른다 — 실패한 응답이 물리면 "
                                  "다시 걸어도 같은 답이 온다"),
                    ('addEventListener("error"', "실패를 안 듣는다"),
                    ("R.lost", "끝내 못 받은 것을 안 남긴다 — 지킴이가 말할 것이 없어진다"),
                    ("boot()", "늦게 온 로직이 화면을 안 세운다 — 되찾아 놓고 사람이 "
                               "F5 를 눌러야 하면 되찾은 것이 아니다")):
                self.assertIn(mark, src, f"web/index.html: {why}")
        with self.subTest("s5d_css_is_retried_in_place"):
            src = shell()
            self.assertIn("el.href = raw", src,
                          "규칙 조각을 같은 <link> 에 다시 걸지 않는다")
            self.assertIn("insertBefore(s, el.nextSibling)", src,
                          "되찾은 로직 조각을 원래 자리 옆에 꽂지 않는다")
            self.assertIn("s.async = false", src,
                          "되찾은 조각끼리의 실행 순서를 안 지킨다")
        with self.subTest("s5e_a_dead_bundle_falls_back_to_the_parts"):
            src = shell()
            for mark, why in (
                    ('src="/app/all.js"', "껍데기가 묶음을 부르지 않는다"),
                    ('href="/css/all.css"', "껍데기가 규칙 묶음을 부르지 않는다"),
                    ("__S9_JS_CAME", "묶음이 **도착은 했는지**를 안 가른다 — 잘려서 "
                                     "안 온 것까지 낱개로 되돌리면 벼랑에 다시 던진다"),
                    ("__S9_OOPS", "일부라도 돌았는지를 안 본다 — 두 번 돌면 죽는다"),
                    ('getElementById("s9-parts-app")', "되돌릴 목록을 안 읽는다"),
                    ("R.pending", "되찾기가 도는 중에 말한다 — 200ms 뒤 돌아올 화면을 "
                                  "그 손으로 지운다")):
                self.assertIn(mark, src, f"web/index.html: {why}")
        with self.subTest("s5b_the_last_part_raises_the_flag"):
            _, app = webasset.parts()
            last = os.path.join(WEB, "app", app[-1])
            with open(last, encoding="utf-8") as f:
                self.assertIn("window.__S9_APP_READY = true;", f.read(),
                              f"마지막 조각({app[-1]})이 표식을 세우지 않는다 — "
                              "그러면 알림이 멀쩡한 화면을 지운다")

class Served(unittest.TestCase):
    """서버가 조각을 실제로 내주는가 — 여기가 통과해야 화면이 뜬다.

    껍데기만 내주고 조각을 404 로 돌려주면 사용자는 흰 화면을 본다. 정적 서빙은
    `bin/s9` do_GET 의 몫이고, MIME 까지 맞아야 한다: `text/html` 로 내준
    스타일시트는 표준 모드 브라우저가 **거부한다**(그래서 조각을 `.html` 로
    위장하는 우회는 애초에 성립하지 않는다).
    """

    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            # `S9_ROOT` 를 **못박는다**. 다른 시험 모듈 여럿이
            # `os.environ["S9_ROOT"] = <임시자리>` 로 전역을 갈아 끼우는데,
            # 여기서 `os.environ` 을 그대로 물려받으면 서버가 `web/` 이 없는
            # 임시 자리를 뿌리로 삼아 조각을 404 로 돌려준다 — 혼자 돌리면
            # 통과하고 스위트에서만 깨지는, 가장 읽기 어려운 실패다.
            # 이 시험이 묻는 것은 **이 저장소의** 조각이 서빙되는가다.
            env={**os.environ, "S9_ROOT": ROOT, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    def get(self, path, tries=3):
        """**연결이 안 선 것과 서버가 아니라고 한 것은 다르다.**

        이 스위트가 묻는 것은 "서버가 그 조각을 내주는가"이고, 답은 상태 코드로
        온다 — 404·400 은 그대로 실패다. 그런데 WSL2 루프백은 동시 도착에서
        **연결 자체가 무너진다**: `ConnectionResetError [Errno 104]` 가
        `/app/<조각>` 42회 왕복 중 한 번씩 튀어나와, 서버가 멀쩡한데도 스위트가
        빨개졌다(2026-09-01 실측 — 단독 3/4 green, 전체 --jobs 에서도 같은 자리).
        화면 쪽은 이 사실을 이미 알고 껍데기에 되찾기 그물을 두고 있다
        (REQ-20260829-039: "404 가 아니라 연결이 안 선다"). 시험만 그 사실을
        모른 채 한 번 만에 판정하고 있었다.
        그래서 **연결 오류만** 짧게 다시 건다 — 상태 코드는 손대지 않는다."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        for i in range(tries):
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, r.headers.get("Content-Type", ""), r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.headers.get("Content-Type", ""), e.read()
            except (ConnectionError, urllib.error.URLError, OSError):
                if i == tries - 1:
                    raise
                time.sleep(0.12 * (i + 1))

    def test_served(self):
        """서버가 조각을 실제로 내주는가 — 여기가 통과해야 화면이 뜬다."""
        with self.subTest("s6_style_parts_are_served_as_css"):
            css, _ = webasset.parts()
            st, ctype, body = self.get(f"/css/{css[0]}")
            self.assertEqual(st, 200, f"/css/{css[0]} 를 못 받았다")
            self.assertTrue(ctype.startswith("text/css"),
                            f"스타일시트를 {ctype!r} 로 내준다 — 브라우저가 거부한다")
            self.assertIn(b":root{", body)
        with self.subTest("s6b_script_parts_are_served_as_js"):
            _, app = webasset.parts()
            st, ctype, body = self.get(f"/app/{app[0]}")
            self.assertEqual(st, 200, f"/app/{app[0]} 를 못 받았다")
            self.assertRegex(ctype, r"^(?:application|text)/javascript")
            self.assertIn(b'"use strict";', body)
        with self.subTest("s6c_every_part_is_reachable"):
            css, app = webasset.parts()
            bad = [f"/css/{n}" for n in css if self.get(f"/css/{n}")[0] != 200]
            bad += [f"/app/{n}" for n in app if self.get(f"/app/{n}")[0] != 200]
            self.assertEqual(bad, [], "못 받는 조각이 있다 — 그만큼 화면이 죽는다")
        with self.subTest("s7_the_bundle_is_served_with_the_right_mime"):
            st, ctype, body = self.get("/css/all.css")
            self.assertEqual(st, 200, "/css/all.css 를 못 받았다")
            self.assertTrue(ctype.startswith("text/css"),
                            f"규칙 묶음을 {ctype!r} 로 내준다 — 브라우저가 거부한다")
            st, ctype, body = self.get("/app/all.js")
            self.assertEqual(st, 200, "/app/all.js 를 못 받았다")
            self.assertRegex(ctype, r"^(?:application|text)/javascript")
        with self.subTest("s7b_the_bundle_is_the_parts_in_the_shell_order"):
            for sub, names in zip(("css", "app"), webasset.parts()):
                body = self.get(f"/{sub}/all.{sub if sub == 'css' else 'js'}")[2]
                want = []
                for n in names:
                    with open(os.path.join(WEB, sub, n), "rb") as f:
                        raw = f.read()
                    chunk = f"/* --- {sub}/{n} --- */\n".encode() + raw
                    want.append(chunk if chunk.endswith(b"\n") else chunk + b"\n")
                want = b"".join(want)
                self.assertTrue(body.endswith(want),
                                f"/{sub}/all.* 이 낱개를 이어 붙인 것과 다르다")
                head = body[:len(body) - len(want)]
                self.assertNotIn(b"/* --- ", head, "머리말이 조각을 삼켰다")
        with self.subTest("s7c_every_part_says_where_it_starts"):
            import json
            body = self.get("/app/all.js")[2].decode("utf-8")
            m = re.search(r"window\.__S9_BUNDLE = (\[.*?\]);\n", body, re.S)
            self.assertTrue(m, "/app/all.js 에 조각 줄 번호 표가 없다 — 그러면 "
                               "지킴이가 말하는 줄이 어느 조각의 것인지 못 찾는다")
            lines = body.split("\n")
            _, app = webasset.parts()
            table = json.loads(m.group(1))
            self.assertEqual([n for n, _ in table], [f"app/{n}" for n in app],
                             "표의 순서가 껍데기와 다르다")
            for name, ln in table:
                self.assertEqual(lines[ln - 1].strip(), f"/* --- {name} --- */",
                                 f"{name} 의 시작 줄({ln})이 표와 어긋난다")
        with self.subTest("s6d_no_side_door_out_of_web"):
            for path in ("/app/../../bin/s9", "/css/../../CLAUDE.md",
                         "/app/../index.html"):
                self.assertNotEqual(self.get(path)[0], 200, f"{path} 가 열린다")

class Auto(unittest.TestCase):
    """조각을 하나 더하면 묶음에도 자동으로 들어온다 — 목록은 한 벌뿐이다.

    서버가 자기 목록을 따로 들면 두 벌이 되고, 조각을 더한 사람은 자기 파일이
    왜 안 도는지 못 찾는다. 그래서 서버는 껍데기의 선언을 그때그때 읽는다.
    여기서는 그 함수를 **가짜 저장소**에 대고 직접 돌린다 — 살아 있는 web/ 을
    건드리지 않고 "더하면 들어오는가"를 물을 수 있는 유일한 자리다.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        spec = importlib.util.spec_from_loader(
            "s9_bundle", importlib.machinery.SourceFileLoader("s9_bundle", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def fake(self, css_names, app_names):
        import tempfile
        root = tempfile.mkdtemp(prefix="s9bundle-")
        self.addCleanup(shutil.rmtree, root, True)
        web = os.path.join(root, "web")
        for sub, names in (("css", css_names), ("app", app_names)):
            os.makedirs(os.path.join(web, sub))
            for n in names:
                with open(os.path.join(web, sub, n), "w", encoding="utf-8") as f:
                    f.write(f"/* {n} */")     # 줄바꿈 없이 끝난다 — 일부러
        lines = ['<template id="s9-parts-css">']
        lines += [f'<link rel="stylesheet" href="css/{n}">' for n in css_names]
        lines += ["</template>", '<link rel="stylesheet" href="/css/all.css">',
                  '<template id="s9-parts-app">']
        lines += [f'<script src="app/{n}"></script>' for n in app_names]
        lines += ["</template>", '<script src="/app/all.js"></script>']
        shell_path = os.path.join(web, "index.html")
        with open(shell_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return root, shell_path

    def test_auto(self):
        """조각을 하나 더하면 묶음에도 자동으로 들어온다 — 목록은 한 벌뿐이다."""
        with self.subTest("s8_a_new_part_joins_the_bundle_by_itself"):
            root, sh = self.fake(["a.css"], ["a.js"])
            first = self.m.web_bundle("app", sh, root).decode()
            self.assertNotIn("/* b.js */", first)
            with open(os.path.join(root, "web", "app", "b.js"), "w",
                      encoding="utf-8") as f:
                f.write("/* b.js */")
            with open(sh, encoding="utf-8") as f:
                src = f.read()
            with open(sh, "w", encoding="utf-8") as f:
                f.write(src.replace('<script src="app/a.js"></script>',
                                    '<script src="app/a.js"></script>\n'
                                    '<script src="app/b.js"></script>'))
            after = self.m.web_bundle("app", sh, root).decode()
            self.assertIn("/* b.js */", after,
                          "껍데기에 더한 조각이 묶음에 안 들어온다 — 목록이 두 벌이다")
            self.assertLess(after.index("/* a.js */"), after.index("/* b.js */"),
                            "묶음의 순서가 껍데기의 순서와 다르다")
        with self.subTest("s8b_parts_do_not_run_into_each_other"):
            root, sh = self.fake(["a.css"], ["a.js", "b.js"])
            with open(os.path.join(root, "web", "app", "b.js"), "w",
                      encoding="utf-8") as f:
                f.write("/* b.js */")
            out = self.m.web_bundle("app", sh, root).decode()
            self.assertNotIn("/* a.js *//* ---", out, "조각 사이에 줄바꿈이 없다")
        with self.subTest("s8c_a_missing_part_does_not_take_the_page_with_it"):
            root, sh = self.fake(["a.css"], ["a.js", "gone.js"])
            os.unlink(os.path.join(root, "web", "app", "gone.js"))
            out = self.m.web_bundle("app", sh, root).decode()
            self.assertIn("/* a.js */", out, "조각 하나가 없다고 나머지를 안 낸다")
            self.assertIn("app/gone.js", out, "없는 자리를 말하지 않는다")
        with self.subTest("s8d_an_unreadable_shell_yields_nothing"):
            self.assertIsNone(self.m.web_bundle("app", "/no/such/index.html", "/no"))
        with self.subTest("s8e_no_side_door_through_the_manifest"):
            root, sh = self.fake(["a.css"], ["a.js"])
            with open(sh, encoding="utf-8") as f:
                src = f.read()
            with open(sh, "w", encoding="utf-8") as f:
                f.write(src.replace('<script src="app/a.js"></script>',
                                    '<script src="app/a.js"></script>\n'
                                    '<script src="app/..."></script>'))
            out = self.m.web_bundle("app", sh, root).decode()
            self.assertNotIn("<template", out, "매니페스트로 web/ 밖이 열린다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
