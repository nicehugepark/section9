"""가이드의 그림을 다시 찍는 길 — `s9 guide` (REQ-20260918-013-62x6).

2026-09-18 에 「가이드 캡처를 0.9.2 로 다시 찍어라」를 집은 세션 셋이 모두 같은
자리에서 막혔다: 그림을 심고 `docs/guide.md` 를 다시 짓는 길(`bin/s9-guide-md`)이
`s9` **밖에** 서 있는데, 무인 작업자의 봉투에는 `s9` 하위명령만 들어 있다.
그래서 이 요청은 사람이 켠 세션만 할 수 있는 일이 되어 사흘을 기다렸다.

이 시험의 계약은 셋이다.

  ① 길이 `s9` 아래 서 있고 **작업자 봉투에 들어 있다** — 이것이 막혔던 자리다.
  ② 찍는 법이 **그림 옆**에 있다. 그림마다 주소와 뷰포트가 붙어 있어야
     다음 판의 재촬영이 한 줄이다(`s9 guide shots`). 그림을 하나 더하면서
     찍는 법을 안 적으면 여기서 먼저 깨진다.
  ③ 심기가 그 자리만 정확히 간다 — 번호는 문서에 선 차례이고
     (`docs/guide-assets/NN.png` 의 NN), 뒤에서부터 갈아 끼워 앞뒤가 안 밀린다.

실행: python3 tests/ guide_shots
"""
import argparse
import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
S9 = os.path.join(ROOT, "bin", "s9")
HTML = os.path.join(ROOT, "web", "guide.html")


def _load_s9():
    tmp = tempfile.mkdtemp(prefix="s9guideshot-")
    keys = ("S9_ROOT", "S9_MACHINE", "S9_USER")
    prev = {k: os.environ.get(k) for k in keys}
    os.environ.update({"S9_ROOT": tmp, "S9_MACHINE": "testbox",
                       "S9_USER": "tester"})
    try:
        spec = importlib.util.spec_from_loader(
            "s9_mod_guideshot",
            importlib.machinery.SourceFileLoader("s9_mod_guideshot", S9))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


S9MOD = _load_s9()


def _png(w, h):
    """가장 작은 진짜 PNG — 심기가 바이트를 그대로 옮기는지 보려면 실물이어야
    한다(머리 여덟 바이트로 png/jpeg 를 가르는 자리도 여기서 걸린다)."""
    def chunk(kind, data):
        c = kind + data
        return (len(data).to_bytes(4, "big") + c
                + zlib.crc32(c).to_bytes(4, "big"))
    ihdr = (w.to_bytes(4, "big") + h.to_bytes(4, "big")
            + bytes((8, 0, 0, 0, 0)))
    raw = b"".join(b"\x00" + b"\xff" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class TestGuideShots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(HTML, encoding="utf-8").read()
        cls.slots = S9MOD._guide_slots(cls.html)

    # ── ① 길이 열려 있는가 ────────────────────────────────────────────────
    def test_worker_can_call_it(self):
        """무인 작업자가 부를 수 있어야 한다 — 막혔던 자리가 여기다."""
        self.assertIn("guide", S9MOD.WORKER_ALLOWED_SUBCOMMANDS,
                      "`s9 guide` 가 작업자 봉투에 없다 — 그러면 재촬영 요청은 "
                      "또 사람이 켠 세션만 할 수 있는 일이 된다")
        self.assertNotIn("guide", S9MOD.WORKER_DENIED_SUBCOMMANDS)

    def test_registered_as_subcommand(self):
        """파서는 `main()` 안에서 지어진다 — 봉투 시험과 같은 방식으로 소스를 본다."""
        src = io.open(os.path.join(ROOT, "bin", "s9.py"), encoding="utf-8").read()
        i = src.index('sub.add_parser("guide"')
        block = src[i:src.index("set_defaults(fn=cmd_guide)", i)]
        self.assertTrue(callable(S9MOD.cmd_guide))
        for need in ("ls", "shots", "embed", "build"):
            self.assertIn('"%s"' % need, block, "`s9 guide %s` 가 없다" % need)
        for flag in ("--base", "--query", "--retry", "--no-build"):
            self.assertIn(flag, block, "`s9 guide` 에 %s 가 없다" % flag)

    # ── ② 찍는 법이 그림 옆에 있는가 ──────────────────────────────────────
    def test_every_picture_says_how_it_was_taken(self):
        self.assertTrue(self.slots, "guide.html 에 박힌 그림을 하나도 못 찾았다")
        for s in self.slots:
            with self.subTest("%02d %s" % (s["n"], s["alt"][:24])):
                self.assertTrue(
                    s["shot"],
                    "이 그림에 `data-shot` 이 없다 — 다음 판을 찍는 사람이 "
                    "주소를 다시 지어야 한다")
                self.assertRegex(
                    s["size"], r"^\d+,\d+$",
                    "`data-size` 가 없거나 「너비,높이」가 아니다 — Settings "
                    "판은 높이가 판마다 달라 기본값으로는 잘린다")
                self.assertTrue(s["alt"], "alt 가 비었다 — md 의 그림 설명이다")

    def test_numbers_follow_document_order(self):
        """번호는 문서에 선 차례 그대로 — `docs/guide-assets/NN.png` 의 NN 이다."""
        self.assertEqual([s["n"] for s in self.slots],
                         list(range(1, len(self.slots) + 1)))
        assets = os.path.join(ROOT, "docs", "guide-assets")
        if os.path.isdir(assets):
            pngs = sorted(f for f in os.listdir(assets) if f.endswith(".png"))
            self.assertEqual(len(pngs), len(self.slots),
                             "docs/guide-assets 의 장수가 html 의 그림 수와 "
                             "다르다 — `s9 guide build` 를 다시 돌려라")

    def test_shot_url_merges_the_common_query(self):
        u = S9MOD._guide_shot_url("?noscroll#settings/display",
                                  "http://127.0.0.1:9909", "anon&skin=calm")
        self.assertEqual(
            u, "http://127.0.0.1:9909/?noscroll&anon&skin=calm#settings/display")
        # 제 인자가 없는 그림도 공통 인자를 받는다
        self.assertEqual(
            S9MOD._guide_shot_url("#board", "http://x:1/", "anon"),
            "http://x:1/?anon#board")
        # 공통 인자가 비면 `?` 도 서지 않는다
        self.assertEqual(S9MOD._guide_shot_url("#board", "http://x:1", ""),
                         "http://x:1/#board")

    def test_a_picture_can_override_the_common_query(self):
        """알림 줄을 일부러 세워 찍는 그림이 공통값 `notices=0` 을 덮을 수 있어야
        한다 — 화면은 `/[?&]notices=(\\d+)/` 의 **첫 짝**을 읽는다."""
        u = S9MOD._guide_shot_url("?notices=3&nopen=1#board", "http://x:1",
                                  S9MOD.GUIDE_SHOT_QUERY)
        self.assertLess(u.index("notices=3"), u.index("notices=0"))

    def test_the_common_query_empties_the_notice_row(self):
        """알림 줄은 사고가 난 몇 분에만 선다 — 찍는 순간에 무엇이 떠 있었느냐로
        가이드의 그림이 갈리면 안 된다 (실측 2026-09-18: Settings 판에 「서버
        재시작 필요」가 함께 들어왔다)."""
        self.assertIn("notices=0", S9MOD.GUIDE_SHOT_QUERY)
        self.assertIn("anon", S9MOD.GUIDE_SHOT_QUERY)
        self.assertIn("skin=calm", S9MOD.GUIDE_SHOT_QUERY)
        js = io.open(os.path.join(ROOT, "web", "app", "notice.js"),
                     encoding="utf-8").read()
        self.assertIn("notices=(\\d+)", js,
                      "화면이 `?notices=` 를 더는 읽지 않는다 — 공통 인자도 "
                      "함께 고쳐야 한다")

    def test_session_placeholder_is_resolved(self):
        """Stream 판은 세션 하나를 골라야 오른쪽이 찬다 — 그 한 자리만 판마다
        달라서 `{session}` 으로 적어 두고 찍을 때 푼다."""
        url = S9MOD._guide_shot_url("#stream/{session}", "http://x:1", "")
        self.assertNotIn("{session}", url)

    # ── ③ 심기가 그 자리만 가는가 ────────────────────────────────────────
    def test_embed_touches_only_that_slot(self):
        with tempfile.TemporaryDirectory(prefix="s9guideembed-") as tmp:
            copy = os.path.join(tmp, "guide.html")
            shutil.copyfile(HTML, copy)
            one, two = os.path.join(tmp, "a.png"), os.path.join(tmp, "b.png")
            io.open(one, "wb").write(_png(3, 2))
            io.open(two, "wb").write(_png(5, 4))
            prev = S9MOD.GUIDE_HTML
            S9MOD.GUIDE_HTML = copy
            try:
                S9MOD._guide_embed({1: one, 3: two})
                after = S9MOD._guide_slots(io.open(copy, encoding="utf-8").read())
            finally:
                S9MOD.GUIDE_HTML = prev
            self.assertEqual(len(after), len(self.slots), "그림 수가 달라졌다")
            want = {1: _png(3, 2), 3: _png(5, 4)}
            body = io.open(copy, encoding="utf-8").read()
            for s in after:
                with self.subTest("%02d" % s["n"]):
                    a, b = s["span"]
                    uri = body[a:b]
                    if s["n"] in want:
                        self.assertEqual(
                            uri, "data:image/png;base64,"
                            + base64.b64encode(want[s["n"]]).decode("ascii"))
                    else:
                        self.assertEqual(s["bytes"], self.slots[s["n"] - 1]["bytes"],
                                         "심지 않은 자리가 밀렸다")
                    # 찍는 법은 심어도 그대로 남는다
                    self.assertEqual(s["shot"], self.slots[s["n"] - 1]["shot"])

    # ── 명령 자체가 도는가 (이 세션의 봉투로는 `s9 guide` 를 못 부른다) ──────
    def test_ls_prints_a_line_per_picture(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            S9MOD.cmd_guide(argparse.Namespace(action="ls"))
        lines = [ln for ln in buf.getvalue().splitlines()
                 if ln.startswith("  ")]
        self.assertEqual(len(lines), len(self.slots))
        self.assertIn("#board", buf.getvalue())

    def test_shots_walks_every_slot_and_embeds_what_it_got(self):
        """찍기는 실제 브라우저가 필요하니 그 한 걸음만 대신 세우고, 주소를
        짓고 심고 재생성을 미루는 나머지 전부를 실제로 돌린다."""
        asked = []

        def fake(url, out, size, wait, engine, tries):
            asked.append((url, size, wait, engine))
            io.open(out, "wb").write(_png(2, 2))
            return 1

        with tempfile.TemporaryDirectory(prefix="s9guideshots-") as tmp:
            copy = os.path.join(tmp, "guide.html")
            shutil.copyfile(HTML, copy)
            prev_html, prev_cap = S9MOD.GUIDE_HTML, S9MOD._guide_capture
            S9MOD.GUIDE_HTML, S9MOD._guide_capture = copy, fake
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    S9MOD.cmd_guide(argparse.Namespace(
                        action="shots", which="1,8", base="http://x:1",
                        query="anon&skin=calm", retry=2, no_build=True))
            finally:
                S9MOD.GUIDE_HTML, S9MOD._guide_capture = prev_html, prev_cap
            # 기대값은 **그림 옆의 찍는 법**에서 온다 — 여기에 숫자를 베껴
            # 두면 높이를 실측으로 한 칸 고칠 때마다 이 시험이 거짓으로 진다.
            want = [self.slots[0], self.slots[7]]
            self.assertEqual(
                [u for u, _s, _w, _e in asked],
                [S9MOD._guide_shot_url(s["shot"], "http://x:1",
                                       "anon&skin=calm") for s in want])
            self.assertEqual([s for _u, s, _w, _e in asked],
                             [s["size"] for s in want])
            self.assertIn("#board", asked[0][0])
            self.assertIn("#settings/display", asked[1][0])
            after = S9MOD._guide_slots(io.open(copy, encoding="utf-8").read())
            small = base64.b64encode(_png(2, 2)).decode("ascii")
            for s in after:
                if s["n"] in (1, 8):
                    self.assertEqual(s["bytes"], len("data:image/png;base64,")
                                     + len(small), "%02d 이 안 갈렸다" % s["n"])
                else:
                    self.assertEqual(s["bytes"],
                                     self.slots[s["n"] - 1]["bytes"])

    def test_embed_rejects_a_slot_that_is_not_there(self):
        with tempfile.TemporaryDirectory(prefix="s9guideembed2-") as tmp:
            copy = os.path.join(tmp, "guide.html")
            shutil.copyfile(HTML, copy)
            png = os.path.join(tmp, "a.png")
            io.open(png, "wb").write(_png(2, 2))
            prev = S9MOD.GUIDE_HTML
            S9MOD.GUIDE_HTML = copy
            try:
                with self.assertRaises(SystemExit):
                    S9MOD._guide_embed({len(self.slots) + 9: png})
            finally:
                S9MOD.GUIDE_HTML = prev


if __name__ == "__main__":
    unittest.main()
