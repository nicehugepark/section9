"""이 제품의 얼굴이 제자리에 있는가 (REQ-20260913-014-62x6).

로고·마크·파비콘은 「있으면 좋은 것」이 아니라 **주소가 있는 파일**이다.
브라우저는 링크를 안 걸어도 `/favicon.ico` 를 제 발로 부르고, 그 자리가
비어 있으면 방문마다 404 가 기록에 쌓인다. 그래서 이 파일이 지키는 것은
그림의 아름다움이 아니라 셋이다.

  ① 일곱 파일이 `web/assets/` 에 있다 — 마크·로고·파비콘 둘·앱 아이콘 셋.
  ② 그림이 **혼자 선다** — SVG 가 viewBox 를 갖고(크기를 부르는 쪽이 정한다)
     바깥 주소를 하나도 안 부른다. 대시보드는 오프라인에서도 도는 것이 규칙이라
     로고 한 줄 때문에 바깥으로 나가면 그 규칙이 깨진다.
  ③ 화면이 부르는 주소가 **실제로 온다** — 껍데기의 link 세 줄이 가리키는
     주소와 `/favicon.ico` 를 서버가 200 으로 낸다. 링크만 걸고 길이 없으면
     화면에는 아무 표도 안 나므로, 이것은 눈으로는 안 잡히는 종류의 결함이다.

그림이 어떻게 생겼는지(16px 에서 읽히는가·비정수 배율에서 획이 갈리는가)는
기계가 못 재는 것이라 사람이 캡처로 본다 — 그 근거는 REQ 문서의 첨부에 있다.

실행: python3 tests/ brand_assets
"""
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402

S9 = os.path.join(HERE, "..", "bin", "s9")
WEBDIR = os.path.join(HERE, "..", "web")
ASSETDIR = os.path.join(WEBDIR, "assets")

MARKS = ("mark.svg", "logo.svg", "favicon.svg")
ICONS = ("icon-192.png", "icon-512.png", "apple-touch-icon.png")
FACES = MARKS + ("favicon.ico",) + ICONS


def asset(name):
    return os.path.join(ASSETDIR, name)


class TheFacesExist(unittest.TestCase):
    """일곱 파일 — 하나라도 없으면 그 자리를 부르는 쪽이 404 를 받는다."""

    def test_the_seven_faces_are_on_disk(self):
        for name in FACES:
            with self.subTest(name):
                p = asset(name)
                self.assertTrue(os.path.isfile(p), f"web/assets/{name} 이 없다")
                self.assertGreater(os.path.getsize(p), 0,
                                   f"web/assets/{name} 이 비었다")

    def test_a_drawing_stands_alone(self):
        """viewBox 가 있어야 부르는 쪽이 크기를 정하고, 바깥 주소가 없어야
        오프라인에서도 그려진다."""
        # `url(#…)` 는 **같은 파일 안**의 그림 조각을 가리키는 것이다 (REQ-20260914-001-62x6:
        # 렌즈의 음영이 radialGradient 라 이 표기를 쓴다) — 바깥 주소가 아니므로 세지 않는다.
        # 바깥으로 나가는 `url(http…)`·`url(./a.png)` 는 그대로 걸린다.
        outside = re.compile(r'https?://|<image\b|@import|xlink:href|url\((?!#)')
        for name in MARKS:
            with self.subTest(name):
                with open(asset(name), encoding="utf-8") as f:
                    src = f.read()
                # xmlns 는 부르는 주소가 아니라 이름표다 — 그것만 빼고 본다
                src = re.sub(r'\sxmlns(?::\w+)?="[^"]*"', "", src)
                self.assertIn("viewBox=", src, f"{name} 에 viewBox 가 없다")
                m = outside.search(src)
                self.assertIsNone(
                    m, f"{name} 이 바깥을 부른다: {m.group(0) if m else ''}")

    def test_the_icon_container_holds_three_sizes(self):
        """favicon.ico 는 그릇이다 — 머리 6바이트 + 항목 16바이트씩,
        16·32·48 셋이 들고 각 항목의 알맹이가 PNG 여야 한다."""
        with open(asset("favicon.ico"), "rb") as f:
            blob = f.read()
        reserved, kind, count = struct.unpack("<HHH", blob[:6])
        self.assertEqual((reserved, kind), (0, 1), "ICO 머리가 아니다")
        self.assertEqual(count, 3, "16·32·48 셋이 아니다")
        sizes = []
        for i in range(count):
            w, h, _, _, _, _, size, off = struct.unpack(
                "<BBBBHHII", blob[6 + 16 * i:22 + 16 * i])
            sizes.append(w)
            self.assertEqual(w, h, f"{i}번째 항목이 정사각이 아니다")
            self.assertEqual(blob[off:off + 8], b"\x89PNG\r\n\x1a\n",
                             f"{i}번째 항목의 알맹이가 PNG 가 아니다")
            self.assertLessEqual(off + size, len(blob),
                                 f"{i}번째 항목이 파일 밖을 가리킨다")
        self.assertEqual(sizes, [16, 32, 48])


class TheServerHandsThemOut(unittest.TestCase):
    """화면이 부르는 주소가 실제로 오는가 — 임시 저장소·시험 포트로 띄워 본다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9brand-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "boss", "S9_REWORK_WATCH": "off",
                   "S9_PORT_GUARD": "off"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=120)
        web = os.path.join(cls.tmp, "web")
        os.makedirs(os.path.join(web, "assets"), exist_ok=True)
        for name in ("index.html", "guide.html"):
            shutil.copy(os.path.join(WEBDIR, name), os.path.join(web, name))
        for name in FACES:
            shutil.copy(asset(name), os.path.join(web, "assets", name))
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        try:
            cls.srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.srv.kill()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), e.read()

    def test_the_default_address_is_no_longer_empty(self):
        """브라우저가 제 발로 부르는 `/favicon.ico` — 종전에는 404 였다."""
        status, ctype, body = self.get("/favicon.ico")
        self.assertEqual(status, 200, "/favicon.ico 가 200 이 아니다")
        self.assertTrue(ctype.startswith("image/"),
                        f"그림이 아닌 종류로 온다: {ctype!r}")
        self.assertEqual(body[:4], b"\x00\x00\x01\x00", "ICO 머리가 아니다")

    def test_the_pages_link_their_faces_and_the_links_answer(self):
        """껍데기와 가이드가 link 세 줄을 갖고, 그 주소가 전부 200 으로 온다."""
        for page in ("/", "/guide.html"):
            status, _, body = self.get(page)
            self.assertEqual(status, 200, page)
            html = body.decode("utf-8", "replace")
            for rel in ('rel="icon"', 'rel="alternate icon"',
                        'rel="apple-touch-icon"'):
                with self.subTest(page=page, rel=rel):
                    self.assertIn(rel, html, f"{page} 에 {rel} 이 없다")
            for href in re.findall(r'<link rel="[^"]*icon[^"]*" href="([^"]+)"',
                                   html):
                with self.subTest(page=page, href=href):
                    st, ctype, _ = self.get("/" + href.lstrip("/"))
                    self.assertEqual(st, 200, f"{href} 가 200 이 아니다")
                    self.assertTrue(ctype.startswith("image/"), ctype)


if __name__ == "__main__":
    unittest.main(verbosity=2)
