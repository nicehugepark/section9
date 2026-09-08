"""캡처는 있으면 줄이고 없으면 그대로 둔다 (REQ-20260908-055-62x6).

주인 물음 2026-09-08 16:49: 「무조건 막는 게 아니라, 필요한 프로그램들을 이
section9 설치할 때 같이 설치하는 건 어때? 부담되는 건가?」

잰 것: 첨부 872개·142.2MB·중앙값 112KB 이고 1MB 를 넘는 것은 7개(전체의
15.6%)뿐이다 — **무게는 거인이 아니라 개수에 있다.** 그러니 파일 하나를 막는
것으로는 안 줄고, 모든 캡처에 일률로 듣는 축소라야 값이 있다. 그 점에서 주인
말씀이 맞다.

그런데 **필수로 설치하지는 않는다.** 지금 `s9-install` 은 `~/.claude` 와 저장소
밖으로 나가지 않는다 — pip·apt 를 부르는 순간 설치가 네트워크·프록시·잠긴
머신에서 실패할 수 있고, pyproject 가 명시한 「오프라인/부트스트랩에서 python3
하나로 동작」이 깨진다. 이 도구는 캡처를 줄이는 데만 쓰므로 없다고 하네스가
멈추지 않는다. 그래서 Chrome·Playwright 와 같은 모양으로 둔다: **있으면 쓰고
없으면 doctor 가 설치 절차를 찍어 준다.** 파이썬 import 가 아니라 외부 실행
파일이라 「의존성 0」 정책과 test_stdlib_only 도 건드리지 않는다.

지키는 것 셋.
1. **줄어들 때만 바꾼다** — 결과가 더 크거나 도구가 실패하면 원본이 남는다.
2. **크기(가로·세로)를 바꾸지 않는다** — 판정에 쓰는 그림이 잘리면 캡처가
   거짓말을 한다. 그래서 폭이 아니라 색을 줄인다.
3. **시한을 둔다** — 캡처마다 몇십 초가 붙으면 사람이 검증을 건너뛴다.

실행: python3 tests/ shot_shrink
"""
import importlib.machinery
import importlib.util
import io
import os
import shutil
import struct
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(HERE, "..", "bin", "s9")


def _png(path, w=8, h=6, fill=b"\x20\x40\x60"):
    """8비트 RGB PNG 한 장 — 필터 0, 진짜로 읽히는 것."""
    raw = b"".join(b"\x00" + fill * w for _ in range(h))
    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))
    return path


class Shrink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_loader(
            "s9_shrink", importlib.machinery.SourceFileLoader("s9_shrink", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9shrink-")
        self.png = _png(os.path.join(self.tmp, "shot.png"))
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self._path = os.environ.get("PATH", "")

    def tearDown(self):
        os.environ["PATH"] = self._path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake(self, name, body):
        """PATH 앞에 서는 가짜 도구 — 진짜 도구가 이 머신에 없어도 잰다."""
        p = os.path.join(self.bin, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n" + body)
        os.chmod(p, 0o755)
        os.environ["PATH"] = self.bin + os.pathsep + self._path
        return p

    def _out_arg(self):
        """pngquant 의 `--output <dst>` 에서 dst 를 집어내는 셸 조각."""
        return ('while [ $# -gt 0 ]; do if [ "$1" = "--output" ]; then '
                'shift; DST="$1"; fi; shift; done\n')

    def _run(self):
        buf = io.StringIO()
        return self.m.shot_shrink(self.png, buf), buf.getvalue()

    # ── 정상 ────────────────────────────────────────────────
    def test_it_uses_the_tool_when_there_is_one(self):
        # 더 작은 PNG 를 내놓는 가짜 pngquant
        small = _png(os.path.join(self.tmp, "small.png"), w=2, h=2)
        self._fake("pngquant", self._out_arg() + f'cp "{small}" "$DST"\n')
        before = os.path.getsize(self.png)
        saved, said = self._run()
        self.assertGreater(saved, 0, "도구가 있는데 줄이지 않았다")
        self.assertLess(os.path.getsize(self.png), before)
        self.assertIn("pngquant", said, "무엇으로 줄였는지 안 말한다")

    def test_the_result_is_still_a_readable_png(self):
        small = _png(os.path.join(self.tmp, "small.png"), w=2, h=2)
        self._fake("pngquant", self._out_arg() + f'cp "{small}" "$DST"\n')
        self._run()
        self.assertIsNotNone(self.m._png_blank_rows(self.png),
                             "줄인 뒤 백지 판정이 못 읽는다 — 검증이 눈을 잃는다")

    # ── 경계 ────────────────────────────────────────────────
    def test_without_a_tool_nothing_happens(self):
        os.environ["PATH"] = self.bin      # 빈 자리 — 도구가 하나도 없다
        before = open(self.png, "rb").read()
        saved, said = self._run()
        self.assertEqual(saved, 0)
        self.assertEqual(said, "", "도구가 없는데 말을 얹었다")
        self.assertEqual(open(self.png, "rb").read(), before, "원본이 바뀌었다")

    def test_a_bigger_result_is_thrown_away(self):
        big = _png(os.path.join(self.tmp, "big.png"), w=64, h=64)
        self._fake("pngquant", self._out_arg() + f'cp "{big}" "$DST"\n')
        before = open(self.png, "rb").read()
        saved, _ = self._run()
        self.assertEqual(saved, 0, "더 큰 결과로 바꿨다")
        self.assertEqual(open(self.png, "rb").read(), before)

    def test_the_scratch_file_is_swept(self):
        small = _png(os.path.join(self.tmp, "small.png"), w=2, h=2)
        self._fake("pngquant", self._out_arg() + f'cp "{small}" "$DST"\n')
        self._run()
        self.assertFalse(os.path.exists(self.png + ".shrink"),
                         "중간 파일이 남았다")

    # ── 실패 ────────────────────────────────────────────────
    def test_a_failing_tool_keeps_the_original(self):
        self._fake("pngquant", "exit 1\n")
        before = open(self.png, "rb").read()
        saved, _ = self._run()
        self.assertEqual(saved, 0)
        self.assertEqual(open(self.png, "rb").read(), before)

    def test_a_broken_result_keeps_the_original(self):
        self._fake("pngquant", self._out_arg() + 'printf "PNG 가 아님" > "$DST"\n')
        before = open(self.png, "rb").read()
        saved, _ = self._run()
        self.assertEqual(saved, 0, "PNG 도 아닌 것으로 바꿨다")
        self.assertEqual(open(self.png, "rb").read(), before)

    def test_a_slow_tool_is_given_up_on(self):
        self._fake("pngquant", "sleep 30\n")
        self.m.SHOT_SHRINK_TIMEOUT = 1
        try:
            before = open(self.png, "rb").read()
            saved, _ = self._run()
        finally:
            self.m.SHOT_SHRINK_TIMEOUT = 20
        self.assertEqual(saved, 0)
        self.assertEqual(open(self.png, "rb").read(), before)

    def test_a_missing_file_is_not_measured(self):
        os.remove(self.png)
        self._fake("pngquant", "exit 0\n")
        self.assertEqual(self._run()[0], 0)

    # ── 회귀 ────────────────────────────────────────────────
    def test_the_tool_names_live_in_one_place(self):
        names = [n for n, _a, _g in self.m.SHOT_SHRINK_TOOLS]
        self.assertEqual(names, ["pngquant", "oxipng"])
        # doctor 는 s9 를 import 하지 않는다(s9 가 못 뜰 때도 써야 한다) —
        # 그래서 이름을 다시 적는다. 두 곳이 갈리면 여기서 잡힌다.
        doc = open(os.path.join(ROOT, "bin", "s9-doctor"), encoding="utf-8").read()
        for n in names:
            self.assertIn(n, doc, f"doctor 가 {n} 를 모른다")

    def test_every_tool_carries_its_install_line(self):
        for name, _a, guide in self.m.SHOT_SHRINK_TOOLS:
            self.assertTrue(str(guide).strip(),
                            f"{name} 에 설치 안내가 없다 — 없는 도구를 이름만 "
                            f"말하면 사람은 무엇을 해야 할지 모른다")
            self.assertIn(name, guide)

    def test_shot_calls_it_after_the_blank_check(self):
        # 판정은 **원본**으로 끝나고 남기는 것만 줄인다 — 순서가 뒤집히면
        # 백지 판정이 줄인 그림을 보게 된다.
        src = open(os.path.join(ROOT, "bin", "s9.py"), encoding="utf-8").read()
        for i in [m for m in range(len(src)) if src.startswith("shot_shrink(out)", m)]:
            head = src.rfind("_png_blank_rows(out)", 0, i)
            self.assertGreater(head, 0, "백지 판정보다 앞에서 줄인다")


if __name__ == "__main__":
    unittest.main()
