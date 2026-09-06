"""캡처를 경로가 아니라 그림으로 남긴다 (REQ-20260827-028-62x6).

판정을 청하는 노트가 캡처를 `\\\\wsl.localhost\\Ubuntu\\tmp\\...\\shots\\` 같은
경로로만 줬다. 사용자는 판정하라고 불려 왔는데 증거는 직접 열어야 했다.

렌더 경로는 원래 다 있었다 — 본문의 `[Image: assets/<id>/f.png]` 는 문서 가시성을
물려받는 `/api/asset` 로 `<img>` 가 된다. 없던 것은 **손잡이 하나**다: `s9 new` 는
`ingest_assets()` 를 부르는데 `s9 note` 는 안 불렀다. 그래서 노트에 캡처를 붙일
방법이 글자로 경로를 적는 것뿐이었다.

실행: python3 tests/ note_attach
"""
import datetime
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)      # 내용은 상관없다 — 확장자로 가른다


class NoteAttach(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9att-")
        self.env = {**os.environ, "S9_ROOT": self.tmp, "S9_MACHINE": "testbox"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")
        self.id = self.cli("new", "request", "--title", "t", "--summary", "s",
                           "--goal", "g", "--size", "S", "--user", "alice",
                           "--body", "x").split()[0]
        self.src = os.path.join(self.tmp, "src")
        os.makedirs(self.src, exist_ok=True)

    def cli(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=30)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def mk(self, name, data=PNG):
        p = os.path.join(self.src, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def body(self):
        return self.cli("show", self.id)

    def asset(self, name):
        # 달을 못박으면 달이 넘어가는 날 시험이 통째로 실패한다 (2026-09-01 실사고)
        ym = datetime.date.today()
        return os.path.join(self.tmp, "vault", "requests", "%04d" % ym.year,
                            "%02d" % ym.month, "assets", self.id, name)

    # N1. 이미지 첨부는 [Image: assets/<id>/f] 로 남고 파일이 실제로 놓인다
    def test_n1_image_attached_and_stored(self):
        self.cli("note", self.id, "확인 화면", "--attach", self.mk("shot.png"))
        self.assertIn(f"[Image: assets/{self.id}/shot.png]", self.body())
        self.assertTrue(os.path.exists(self.asset("shot.png")))

    # N2. 이미지가 아니면 [File: ...] — 문서 화면이 📎 칩으로 그린다
    def test_n2_non_image_is_file(self):
        self.cli("note", self.id, "로그", "--attach",
                 self.mk("run.log", b"hello"))
        self.assertIn(f"[File: assets/{self.id}/run.log]", self.body())

    # N3. 여러 개를 한 번에 (반복 지정)
    def test_n3_multiple(self):
        self.cli("note", self.id, "셋", "--attach", self.mk("a.png"),
                 "--attach", self.mk("b.png"))
        b = self.body()
        self.assertIn(f"[Image: assets/{self.id}/a.png]", b)
        self.assertIn(f"[Image: assets/{self.id}/b.png]", b)

    # B1. --attach 없이 본문에 손으로 쓴 절대경로도 이전된다 (같은 규칙, 두 입구)
    def test_b1_inline_abs_path_ingested(self):
        p = self.mk("inline.png")
        self.cli("note", self.id, f"보라 [Image: {p}]")
        self.assertIn(f"[Image: assets/{self.id}/inline.png]", self.body())

    # B2. 같은 이름을 두 번 붙여도 덮어쓰지 않는다
    def test_b2_same_name_not_overwritten(self):
        self.cli("note", self.id, "하나", "--attach", self.mk("dup.png"))
        self.cli("note", self.id, "둘", "--attach", self.mk("dup.png"))
        self.assertTrue(os.path.exists(self.asset("dup.png")))
        self.assertTrue(os.path.exists(self.asset("dup-2.png")),
                        os.listdir(os.path.dirname(self.asset("dup.png"))))

    # B3. 첨부만 있고 글이 없어도 노트가 선다 — 캡처 한 장만 남기는 것이 정상이다
    def test_b3_attach_only(self):
        self.cli("note", self.id, "--attach", self.mk("only.png"))
        self.assertIn(f"[Image: assets/{self.id}/only.png]", self.body())

    # F1. 없는 파일을 붙이면 죽는다 — 조용히 넘어가면 '붙였다고 믿는 노트'가 남는다
    def test_f1_missing_file_dies(self):
        out = self.cli("note", self.id, "x", "--attach",
                       os.path.join(self.src, "nope.png"), expect=1)
        self.assertIn("nope.png", out)

    # R1. --attach 없는 보통 노트는 예전 그대로 — 첨부 표기가 생기지 않는다
    def test_r1_plain_note_unchanged(self):
        self.cli("note", self.id, "그냥 기록", "--label", "response")
        b = self.body()
        self.assertIn("그냥 기록", b)
        self.assertNotIn("[Image:", b)
        self.assertNotIn("[File:", b)


if __name__ == "__main__":
    unittest.main()
