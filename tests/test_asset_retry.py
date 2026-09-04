"""문서의 그림이 깨져 보인다 (REQ-20260829-019).

사용자: "문서에 이미지 렌더링이 깨진 것 처럼 보이는 문서가 있다. 제대로 된건지
아닌지 다시 점검해줘."

파일은 멀쩡했다. **잘린 것은 연결**이다 — 이 환경의 루프백이 같은 순간에 도착한
연결을 열 개쯤에서 자른다(DOC-20260827-004 에 측정과 배제 목록이 있다: 리슨
큐도, 핸들러 속도도, 우리 서버 코드도 아니다). 그 문서의 처방은 하나다 —
**클라이언트가 재시도한다.**

대시보드의 데이터 요청은 `ccFetch`·`loadSupply` 로 이미 그 처방을 받고 있었는데
**그림만 밖에 있었다**: `<img src>` 는 브라우저가 직접 부르고 실패하면 다시 걸지
않는다. 깨진 칸 하나를 남기고 끝이라, 그림이 많은 문서일수록 "가끔"이 아니라
**반드시** 깨졌다.

계약은 여섯이다.

  ① 그림을 짓는 곳은 한 곳(`attImg`)이다 — 두 곳이 지으면 한 곳만 다시 건다.
  ② 못 받은 자리가 그림과 **함께** 선다(나중에 짓지 않는다) — 실패한 순간
     DOM 을 짓느라 한 프레임을 흘리면 깨진 아이콘이 보인다.
  ③ 실패하면 백오프+지터로 다시 건다. 재시도 주소는 갈라진다(실패한 시도가
     캐시에 물리면 다시 걸어도 같은 실패가 온다).
  ④ 끝내 못 받으면 브라우저의 깨진 아이콘 대신 **파일 이름 · 다시 · 여는 길**.
     `다시` 는 링크 밖에 있다 — 안에 있으면 누르는 순간 링크가 먼저 열린다.
  ⑤ 문구에 내부 용어를 쓰지 않는다(루프백·SYN·소켓·ECONNREFUSED).
  ⑥ 손 없이 볼 수 있다 — `?attstat`(몇 장 왔나) · `?attfail=`(못 받은 자리).

**큐(동시 상한)를 두지 않은 것도 계약이다.** 짐작이 아니라 재서 정했다 —
상한을 4·6·8 로 걸어도 19장 중 1~5장이 여전히 잘렸고(벼랑은 "몇 개가 떠
있나"가 아니라 "같은 순간에 몇 개가 도착하나"다), 재시도만으로 5회 시도가 전부
19/19 였다. 그 측정을 소스에 적어 둔다 — 다음 사람이 "큐를 얹지 그랬어"로
되돌리지 않게.

실행: python3 tests/ asset_retry
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class TheRetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    # ---------- ① 짓는 곳은 하나 ----------

    def test_the_retry(self):
        """TheRetry 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("pictures_are_built_in_one_place"):
                self.assertIn("function attImg(", self.src, "attImg() 이 없다")
                self.assertEqual(self.src.count("const attImg"), 0,
                                 "md2html 안이 제 attImg 를 또 짓는다 — 그 그림은 "
                                 "실패해도 다시 걸지 않는다")
                self.assertEqual(self.src.count('class="attimg"'), 1,
                                 "`<img class=attimg>` 를 짓는 자리가 둘 이상이다")

            # ---------- ② 자리는 미리 선다 ----------
        with self.subTest("the_empty_seat_ships_with_the_picture"):
            fn = self._fn("attImg")
            self.assertIn("attbox", fn, "그림과 자리를 한 덩이로 내지 않는다")
            self.assertIn('class="attmiss" hidden', fn,
                          "못 받은 자리를 미리 세우지 않는다 — 실패한 순간 짓느라 "
                          "깨진 아이콘이 한 프레임 지나간다")
            # 되돌아올 주소를 그림이 들고 있어야 다시 걸 수 있다
            self.assertIn("data-attd=", fn)
            self.assertIn("data-attf=", fn)
        with self.subTest("hidden_actually_hides"):
                self.assertRegex(self.src, r"\.attbox \[hidden\]\{display:none\}",
                                 "감춘 것이 실제로 감춰지지 않는다")

            # ---------- ③ 다시 건다 ----------
        with self.subTest("it_backs_off_and_jitters"):
            self.assertRegex(self.src, r"const ATT_BACKOFF = \[[\d, ]+\]",
                             "백오프 표가 없다")
            fn = self._fn("attFail")
            self.assertIn("ATT_BACKOFF", fn, "재시도 간격이 없다")
            self.assertIn("Math.random", fn,
                          "지터가 없다 — 실패한 것들이 한꺼번에 다시 출발하면 "
                          "같은 벼랑을 또 만난다")
            self.assertRegex(fn, r"img\.src = attUrl", "다시 걸지 않는다")
        with self.subTest("the_retry_url_differs"):
            fn = self._fn("attUrl")
            self.assertRegex(fn, r"&r=", "재시도 주소가 첫 주소와 같다 — 실패가 "
                                         "캐시에 물리면 다시 걸어도 같은 답이 온다")
        with self.subTest("it_listens_once_on_the_document"):
                m = re.search(r'document\.addEventListener\("error",[\s\S]{0,200}?\}, true\)',
                              self.src)
                self.assertIsNotNone(m, "그림 실패를 문서에서 받지 않는다")
                self.assertIn("attFail", m.group(0))

            # ---------- ④ 사람의 자리 ----------
        with self.subTest("the_last_resort_is_a_place_for_a_person"):
            fn = self._fn("attMissHtml")
            self.assertIn("attf", fn, "어느 그림인지 이름이 없다")
            self.assertIn("data-attretry", fn, "다시 부를 손잡이가 없다")
            self.assertIn("target=\"_blank\"", fn, "직접 열어 볼 길이 없다")
            # 기다리는 중은 진행을 보여준다 — 가만한 문구는 멈춘 것으로 읽힌다
            self.assertRegex(fn, r"ATT_BACKOFF\.length", "몇 번째인지 안 적는다")
        with self.subTest("the_retry_button_is_outside_the_link"):
                fn = self._fn("attImg")
                i, j = fn.find("<a class="), fn.find("</a>")
                self.assertGreater(j, i)
                self.assertNotIn("attmiss", fn[i:j],
                                 "못 받은 자리가 링크 안에 있다")

            # ---------- ⑤ 사람의 말 ----------
        with self.subTest("it_speaks_plainly"):
                fn = self._fn("attMissHtml")
                for jargon in ("루프백", "SYN", "소켓", "ECONNREFUSED", "커넥션",
                               "타임아웃", "리셋"):
                    self.assertNotIn(jargon, fn, "내부 용어를 그대로 썼다: %s" % jargon)
                self.assertIn("그림을 받지 못했습니다", fn, "무엇이 안 됐는지 안 말한다")

            # ---------- ⑥ 손 없이 본다 ----------
        with self.subTest("it_can_be_seen_without_hands"):
                for p in ("attstat", "attfail", "attdead", "attslow"):
                    self.assertIn(p, self.src, "진단 파라미터 %s 가 없다" % p)

            # ---------- 큐를 두지 않은 근거 ----------
        with self.subTest("the_measurement_is_written_down"):
            i = self.src.find("const ATT_BACKOFF")
            head = self.src[max(0, i - 2600):i]
            self.assertIn("동시 상한", head, "큐를 재 본 기록이 없다")
            self.assertRegex(head, r"19|재시도",
                             "무엇을 얼마나 재 봤는지 적혀 있지 않다")
        with self.subTest("there_is_no_queue"):
            self.assertNotRegex(self.src, r"attQueue|attSem|ATT_MAX_INFLIGHT",
                                "재 보고 두지 않기로 한 큐가 들어왔다")

class ThePress(unittest.TestCase):
    """눌러서 되찾는다 (REQ-20260830-003 · 부모 REQ-20260829-019).

    부모 건은 미검증 하나를 남기고 닫혔다 — "`다시` 를 실제 클릭으로 눌러 보지
    못했다(이 환경에 브라우저 조작 수단 없음)". **수단은 있었다**: 서버의
    `/[\\w.-]+\\.html` 길이 web/ 아래 정적 html 을 same-origin 으로 내주고,
    같은 출처면 iframe 안의 문서에 실제 좌표로 MouseEvent 를 던질 수 있다
    (verify-gempty-click.html 이 이미 그렇게 범례를 눌렀다).

    그 하니스(web/verify-attretry-click.html)로 눌러 봤다 — 못 받은 자리 3장,
    좌표 hit-test 통과, 클릭이 링크를 열지 않았고, 밀리던 것이 풀린 뒤 그
    단추를 눌러 3장이 전부 돌아왔다(배너: 뜸 40 · 다시 걸어서 3 · 못 받음 0).
    여기 계약은 그 클릭 경로가 나중에 조용히 바뀌지 않게 못박는다.
    """

    HARNESS = os.path.join(os.path.dirname(HERE), "web",
                           "verify-attretry-click.html")

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _press(self):
        """`다시` 를 받는 처리기 한 덩이."""
        i = self.src.find('closest("[data-attretry]")')
        self.assertNotEqual(i, -1, "다시 단추를 받는 곳이 없다")
        s = self.src.rfind('document.addEventListener("click"', 0, i)
        self.assertNotEqual(s, -1, "그 처리기가 문서에 달려 있지 않다")
        e = re.compile(r"\n\}, (?:true|false)\);").search(self.src, i)
        self.assertIsNotNone(e, "그 처리기의 끝을 찾지 못했다")
        return self.src[s:e.end()]

    def test_the_press(self):
        """눌러서 되찾는다 (REQ-20260830-003 · 부모 REQ-20260829-019)."""
        with self.subTest("the_press_is_caught_where_it_is_thrown"):
            self.assertRegex(self._press(), r"\}, true\);\s*$",
                             "다시 단추의 클릭을 잡는 단계에서 받지 않는다")
        with self.subTest("the_press_does_not_open_the_link"):
            fn = self._press()
            self.assertIn("preventDefault()", fn, "기본 동작을 막지 않는다")
            self.assertIn("stopPropagation()", fn, "누른 것이 위로 샌다")
        with self.subTest("the_press_is_a_fresh_try"):
            fn = self._press()
            self.assertRegex(fn, r"dataset\.atttry\s*=", "시도 수를 되돌리지 않는다")
            self.assertRegex(fn, r"src\s*=\s*attUrl\(", "다시 부르지 않는다")
            self.assertRegex(fn, r'attUrl\(img,\s*"u"', "재시도 주소로 갈리지 않는다")
        with self.subTest("the_harness_that_presses_it_is_kept"):
            self.assertTrue(os.path.isfile(self.HARNESS),
                            "눌러 보는 하니스가 없다: web/verify-attretry-click.html")
            with open(self.HARNESS, encoding="utf-8") as f:
                h = f.read()
            self.assertIn("MouseEvent", h, "실제 이벤트를 던지지 않는다")
            self.assertIn("elementFromPoint", h,
                          "덮여 있는지(좌표 hit-test)를 보지 않는다")
            self.assertIn("data-attretry", h, "그 단추를 누르지 않는다")
            # 손대는 것은 **빗나가게 하던 표식** 하나뿐이다. 클릭 경로를 대신
            # 실행해 버리면 "눌러 봤다"가 아니라 "함수를 불러 봤다"가 된다.
            self.assertIn('removeAttribute("data-attbad")', h,
                          "밀리던 것이 풀린 상황을 만들지 않는다")

if __name__ == "__main__":
    unittest.main()
