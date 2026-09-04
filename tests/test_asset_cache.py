"""첨부를 다시 그릴 때마다 다시 부르지 않는다 (REQ-20260829-019).

사용자: "문서에 이미지 렌더링이 깨진 것 처럼 보이는 문서가 있다."

파일은 멀쩡했다. 잘린 것은 **연결**이다 — 이 환경의 루프백이 같은 순간에
도착한 연결을 열 개쯤에서 자른다(DOC-20260827-004: 측정과 배제 목록이 거기
있다. 리슨 큐도, 핸들러 속도도, 우리 서버 코드도 아니다). 실측으로 같은 첨부를
동시에 16번 부르니 8건이 서버에 닿지도 못하고 거절됐다.

그 문서의 처방은 "클라이언트가 재시도한다"이고 그것은 화면의 몫이다. 서버가
할 수 있는 것은 다른 쪽이다 — **부르는 횟수 자체를 줄이는 것.** 지금 첨부
응답은 `Cache-Control: no-store` 라, 문서를 다시 그릴 때마다(폴링·탭 전환·
스크롤) 열다섯 장을 전부 새로 부른다. 벼랑 앞에서 매번 열다섯을 던지는 셈이다.

첨부는 문서 옆에 놓인 파일이고 내용이 스스로 바뀌지 않는다. 잠깐의 캐시와
검증 표식(ETag)을 주면 다시 그리기는 연결을 아예 안 쓴다. 다만 **영원히**는
아니다 — 같은 이름으로 갈아 끼우는 캡처가 이 저장소에 실제로 있다(designer 가
`n-model.png` 를 두 번 찍었다). 그래서 짧은 수명 + 검증이다.

실행: python3 tests/ asset_cache
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9ac", importlib.machinery.SourceFileLoader("s9ac", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TheTag(unittest.TestCase):
    """같은 파일은 같은 표식, 바뀌면 다른 표식."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        cls.fn = staticmethod(getattr(cls.m, "asset_etag", None))

    def test_the_tag(self):
        """같은 파일은 같은 표식, 바뀌면 다른 표식."""
        with self.subTest("it_exists"):
            self.assertTrue(self.fn, "asset_etag() 이 없다")
        with self.subTest("same_file_same_tag"):
            self.assertEqual(self.fn(S9), self.fn(S9))
        with self.subTest("it_is_a_quoted_token"):
            t = self.fn(S9)
            self.assertTrue(t.startswith('"') and t.endswith('"'), t)
            self.assertNotIn(" ", t)
        with self.subTest("a_missing_file_has_no_tag"):
            self.assertEqual(self.fn("/nope/nope/nope"), "")
        with self.subTest("it_moves_when_the_file_does"):
            import tempfile
            import time
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(b"a" * 10)
                p = f.name
            self.addCleanup(os.remove, p)
            first = self.fn(p)
            time.sleep(0.01)
            with open(p, "wb") as f:
                f.write(b"b" * 20)          # 크기도 시각도 달라진다
            self.assertNotEqual(first, self.fn(p))

class TheResponse(unittest.TestCase):
    """첨부 응답만 캐시된다 — 다른 답까지 캐시하면 낡은 화면이 남는다."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(S9, encoding="utf-8").read()

    def test_the_response(self):
        """첨부 응답만 캐시된다 — 다른 답까지 캐시하면 낡은 화면이 남는다."""
        with self.subTest("the_default_is_still_no_store"):
            i = self.src.find("def _send(self, code, ctype, data):")
            self.assertGreater(i, 0)
            self.assertIn('"Cache-Control", "no-store"', self.src[i:i + 400])
        with self.subTest("assets_are_sent_through_their_own_door"):
            i = self.src.find('elif parsed.path == "/api/asset":')
            self.assertGreater(i, 0)
            blk = self.src[i:i + 1400]
            self.assertIn("_send_asset", blk,
                          "첨부가 여전히 no-store 로 나간다 — 다시 그릴 때마다 "
                          "열다섯 장을 새로 부른다")
        with self.subTest("the_asset_door_revalidates"):
            i = self.src.find("def _send_asset(")
            self.assertGreater(i, 0, "_send_asset() 이 없다")
            blk = self.src[i:i + 1600]
            self.assertIn("If-None-Match", blk, "검증 요청을 읽지 않는다")
            self.assertIn("304", blk, "안 바뀌었다고 답할 줄 모른다")
            self.assertIn("ETag", blk)
            self.assertIn("max-age", blk, "잠깐의 수명이 없다 — 매번 다시 묻는다")
        with self.subTest("the_life_is_short_enough_to_notice_a_replaced_capture"):
            m = _load()
            life = getattr(m, "ASSET_CACHE_SEC", None)
            self.assertIsNotNone(life, "ASSET_CACHE_SEC 이 없다")
            self.assertGreater(life, 0)
            self.assertLessEqual(life, 600,
                                 "너무 길다 — 다시 찍은 캡처가 옛 그림으로 남는다")
        with self.subTest("a_304_carries_no_body"):
            i = self.src.find("def _send_asset(")
            blk = self.src[i:i + 1600]
            j = blk.find("304")
            self.assertGreater(j, 0)
            self.assertNotIn("wfile.write", blk[j:j + 320],
                             "304 에 본문을 실었다")

if __name__ == "__main__":
    unittest.main()
