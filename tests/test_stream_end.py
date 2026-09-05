"""로그는 죽는 순간을 스스로 말하지 않는다 (REQ-20260901-006).

실사고 2026-09-01 12:49: 한도 소진(11:39)·Esc 중단(12:41)으로 죽은 세션들의
마지막 출력이 스트림·터미널에 일하던 모습 그대로 남아, 보드의 멈춤 표시와
어긋나 보였다 — "화면에서는 멈춘 것 같은데 터미널 로그를 보면 실행 중인 것
같다". 죽은 세션의 기록을 보여 주는 화면은 종료 사실을 함께 말해야 한다.

계약 셋:
  ① 서버 — 죽은 세션의 /api/stream 응답에 ended(+시각·판별된 사유)가 실린다.
  ② 스트림 뷰 — 머리와 꼬리 양쪽에서 종료를 말한다(읽는 눈이 어디서 시작하든).
  ③ 터미널 — ended 를 stale 로 뭉뚱그리지 않는다.

실행: python3 tests/ stream_end
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
WEB = os.path.join(ROOT, "web", "app")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_comments(src):
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    return re.sub(r"(?m)^\s*//.*$", "", src)


class TheServerCarriesTheEnd(unittest.TestCase):
    """① ended 는 서버가 기록에서 읽어 싣는다 — 화면이 짐작하지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.src = read(S9_SRC)

    def test_the_end_info_exists_and_reads_the_binding(self):
        m = re.search(r"def stream_end_info\(session, path\):([\s\S]{0,2200})",
                      self.src)
        self.assertTrue(m, "stream_end_info 가 없다")
        body = m.group(1)
        self.assertIn('b.get("ended")', body, "바인딩의 ended 를 안 읽는다")
        # 사유는 판별 가능한 서명만 — 짐작으로 문장을 짓지 않는다. 대입문이
        # 서명 검사(reached/limit) 안에서만 나오는지를 잰다(독스트링의 사례
        # 언급은 코드가 아니다).
        whys = re.findall(r'out\["end_why"\] = "([^"]+)"', body)
        self.assertEqual(whys, ["사용 한도 소진"],
                         "판별 서명 밖의 사유가 생겼다: %r" % whys)

    def test_stream_events_merges_it_for_dead_sessions_only(self):
        self.assertRegex(
            self.src,
            r'\{\} if live else stream_end_info\(session, path\)',
            "죽은 세션에만 종료 사실을 싣는 병합이 없다")


class TheScreensSpeakTheEnd(unittest.TestCase):
    """②·③ 화면 둘 다 종료를 말한다."""

    def test_the_stream_view_says_it_head_and_tail(self):
        audit = strip_comments(read(os.path.join(WEB, "audit.js")))
        self.assertIn("세션 종료", audit, "스트림 머리에 종료 표시가 없다")
        self.assertIn("세션이 여기서 끝났습니다", audit,
                      "스트림 꼬리에 끝난 자리 표시가 없다")
        self.assertIn("d.end_why", audit, "판별된 사유를 안 그린다")
        # 살아 있는 세션의 얼굴은 불변 — follow 체크박스가 그대로다
        self.assertIn('id="follow"', audit)

    def test_the_terminal_does_not_call_a_dead_session_stale(self):
        term = strip_comments(read(os.path.join(WEB, "terminal.js")))
        self.assertRegex(term, r'nt\.ended \? "세션 종료"',
                         "터미널이 ended 를 stale 로 뭉뚱그린다")
        self.assertIn("끝났습니다", term, "종료 안내 문장이 없다")


if __name__ == "__main__":
    unittest.main()
