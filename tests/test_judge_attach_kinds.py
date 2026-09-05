"""반려에 붙이는 것이 그림만은 아니다 (REQ-20260829-015 재작업).

사용자 반려: "반려에 첨부할 수 있는 이미지가, 그림 이미지일수도, 문서
파일일수도, 영상파일일수도 있다."

1차는 판정 창에 **그림**을 붙일 수 있게 했다. 그런데 반려의 근거는 캡처만이
아니다 — 실패한 CSV, 로그 파일, 화면을 녹화한 영상이 그 자리에 온다. 지금
화면은 붙인 것을 **무조건** `[Image: …]` 로 적고, 문서 뷰어는 그 표기를 `<img>`
로 그린다. 영상을 붙이면 깨진 그림 한 칸이 남는다 — 붙지 않은 것보다 나쁘다.

세 자리를 여기서 잡는다.

**하나 — 무엇으로 적을지는 서버가 정한다.** `[Image:]` 냐 `[File:]` 이냐는
파일의 성질이지 화면의 취향이 아니다. 화면 두 곳(터미널 입력창·판정 창)이 각자
정규식을 들고 있으면 한 곳만 고쳐진다. 이미 터미널 쪽이 자기 판단을 갖고 있고,
판정 창은 아예 안 갖고 있어서 전부 `Image` 로 적혔다.

**둘 — 붙이기와 전이가 한 번에 간다.** 지금은 `/api/note` 로 붙이고 `/api/status`
로 옮기는 두 왕복이라, 앞이 성공하고 뒤가 실패하면 근거만 남고 상태는 안 옮겨진
어중간한 자리가 생긴다. 1차 designer 가 서버 몫으로 남긴 지점이다.

**셋 — 반려 근거가 '질문'으로 적히지 않는다.** `/api/note` 는 라벨을 `ask` 로
박아 둔다. 그래서 판정 창에서 댄 근거가 문서에 **질문**으로 남았다. 나중에 그
문서를 읽는 사람은 답해야 할 질문과 판정의 근거를 구별할 수 없다.

실행: python3 tests/ judge_attach_kinds
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def _load():
    spec = importlib.util.spec_from_loader(
        "s9jak", importlib.machinery.SourceFileLoader("s9jak", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TheMark(unittest.TestCase):
    """무엇으로 적을지는 파일이 정한다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        cls.fn = staticmethod(getattr(cls.m, "asset_mark", None))

    def test_the_mark(self):
        """무엇으로 적을지는 파일이 정한다."""
        with self.subTest("it_exists"):
            self.assertTrue(self.fn, "asset_mark() 이 없다 — 화면마다 자기 정규식을 "
                                     "들면 한 곳만 고쳐진다")
        with self.subTest("pictures_are_pictures"):
            for n in ("shot.png", "a.JPG", "b.jpeg", "c.gif", "d.webp", "e.svg",
                      "f.heic"):
                with self.subTest(n):
                    self.assertEqual(self.fn("/tmp/" + n), f"[Image: /tmp/{n}]")
        with self.subTest("a_video_is_not_a_picture"):
            for n in ("screen.mp4", "a.MOV", "b.webm", "c.mkv"):
                with self.subTest(n):
                    self.assertEqual(self.fn("/tmp/" + n), f"[File: /tmp/{n}]")
        with self.subTest("documents_and_data_are_files"):
            for n in ("report.pdf", "sheet.xlsx", "log.txt", "dump.csv",
                      "notes.hwp", "sound.mp3", "bundle.zip"):
                with self.subTest(n):
                    self.assertEqual(self.fn("/tmp/" + n), f"[File: /tmp/{n}]")
        with self.subTest("an_unknown_extension_is_a_file"):
            self.assertEqual(self.fn("/tmp/x.qqq"), "[File: /tmp/x.qqq]")
            self.assertEqual(self.fn("/tmp/noext"), "[File: /tmp/noext]")
        with self.subTest("it_reads_from_the_one_table"):
            src = open(S9_SRC, encoding="utf-8").read()
            i = src.find("def asset_mark(")
            self.assertGreater(i, 0)
            self.assertIn("TYPE_GROUPS", src[i:i + 900],
                          "확장자 목록을 두 벌로 만들었다")

class TheLabel(unittest.TestCase):
    """판정의 근거는 질문이 아니다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        cls.src = open(S9_SRC, encoding="utf-8").read()

    def test_the_label(self):
        """판정의 근거는 질문이 아니다."""
        with self.subTest("append_takes_a_label"):
            import inspect
            sig = inspect.signature(self.m.chat_append_doc)
            self.assertIn("label", sig.parameters,
                          "라벨이 'ask' 로 박혀 있다 — 반려 근거가 질문으로 적힌다")
            self.assertEqual(sig.parameters["label"].default, "ask",
                             "이어 말하기의 기존 뜻(질문)은 그대로여야 한다")
        with self.subTest("the_api_passes_it_through"):
            i = self.src.find('elif parsed.path == "/api/note":')
            self.assertGreater(i, 0)
            self.assertIn("label", self.src[i:i + 1500],
                          "/api/note 가 라벨을 받지 않는다")
        with self.subTest("a_made_up_label_is_refused"):
            self.assertTrue(getattr(self.m, "NOTE_LABELS", None),
                            "허용 라벨 목록이 없다")
            self.assertIn("response", self.m.NOTE_LABELS)
            self.assertIn("ask", self.m.NOTE_LABELS)

class OneTrip(unittest.TestCase):
    """붙이기와 전이는 한 번에 간다."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(S9_SRC, encoding="utf-8").read()

    def test_status_takes_attachments(self):
        i = self.src.find('if parsed.path == "/api/status":')
        self.assertGreater(i, 0)
        blk = self.src[i:i + 2000]
        self.assertIn("atts", blk,
                      "/api/status 가 첨부를 받지 않는다 — 화면이 두 번 두드린다")
        self.assertIn("asset_mark", blk, "표식을 화면이 짓게 두었다")

    def test_the_attachment_lands_before_the_transition(self):
        """반려는 무인 작업자를 깨운다 — 그가 문서를 읽을 때 근거가 이미 있어야
        한다. 순서가 뒤집히면 빈 문서를 읽고 시작한다."""
        i = self.src.find('if parsed.path == "/api/status":')
        blk = self.src[i:i + 2000]
        self.assertLess(blk.find("asset_mark"), blk.find("do_transition("),
                        "전이가 첨부보다 먼저다")


if __name__ == "__main__":
    unittest.main()
