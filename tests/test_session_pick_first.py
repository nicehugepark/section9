"""세션 고르는 창은 **먼저 뜨고** 목록은 뒤따라 온다 (REQ-20260902-065-62x6).

실사고 2026-09-02 22:18. 사용자: "터미널에서 이 화면에 붙어있는 세션을 클릭하면
팝업이 너무 늦게 뜬다. 늦게 뜰 이유가 없을거같은데 말이야."

실측한 것은 이렇다. `termSessionPick` 이 `/api/sessions` 를 **먼저** 받고 그
다음에 창을 그렸다. 그 응답은 찬 캐시에서 1.51초다(더운 캐시 0.04초, 3,019
바이트). 폴링 스냅샷 TTL 이 2초라 **2초 넘게 가만있다 누르면 매번** 그 값을
치른다. 누른 사람에게 그 1.5초는 통째로 "아무 일도 안 일어남"이고, 대조로
`/api/serveinfo` 는 0.04초다 — 서버가 느린 게 아니라 **누름과 뜸 사이에
네트워크가 있었던** 것이다.

고침은 순서를 바꾸는 것이다: 창을 즉시 세우고 목록은 도착하는 대로 채운다.
그러면 새 물음이 하나 생긴다 — 아직 아무것도 없는 그 짧은 동안 화면은 무엇을
말하는가. 이 저장소는 그 자리에 규율이 있다(빈 껍데기가 「받는 중」인지
「비어 있음」인지 화면이 스스로 말한다). 빈 자리 셋이 서로 다른 말을 해야
한다: 받는 중 · 고를 것이 없음 · 서버가 죽음.

계약을 코드 구조로 못박는다 — 문구만 고치면 다음 재작업이 순서를 되돌린다.

실행: python3 tests/ session_pick_first
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SESSION_JS = os.path.join(ROOT, "web", "app", "session.js")


def src():
    with open(SESSION_JS, encoding="utf-8") as f:
        return f.read()


def fn_body(text, name):
    """`async function <name>(` 부터 같은 들여쓰기의 닫는 중괄호까지."""
    m = re.search(r"^(?:async )?function " + re.escape(name) + r"\(", text,
                  re.M)
    if not m:
        raise AssertionError(f"{name} 을 못 찾았다")
    i, depth, started = m.start(), 0, False
    while i < len(text):
        if text[i] == "{":
            depth += 1
            started = True
        elif text[i] == "}":
            depth -= 1
            if started and depth == 0:
                return text[m.start():i + 1]
        i += 1
    raise AssertionError(f"{name} 의 끝을 못 찾았다")


class PickOpensFirst(unittest.TestCase):
    """S1·S3 — 누름과 뜸 사이에 네트워크를 두지 않는다."""

    def setUp(self):
        self.body = fn_body(src(), "termSessionPick")

    def test_s1_dialog_comes_before_the_fetch(self):
        dlg = self.body.find("s9dlg(")
        fetch = self.body.find("ccFetchTry(")
        self.assertGreater(dlg, -1, "창을 여는 자리가 없다")
        self.assertGreater(fetch, -1, "목록을 받는 자리가 없다")
        self.assertLess(
            dlg, fetch,
            "목록을 받은 **뒤에** 창을 연다 — 누른 사람에게 그 시간은 통째로 "
            "아무 일도 안 일어남이다 (REQ-20260902-065 회귀)")

    def test_s1b_the_first_dialog_is_not_awaited(self):
        first = self.body[:self.body.find("ccFetchTry(")]
        m = re.search(r"(\w*)\s*s9dlg\(", first)
        self.assertIsNotNone(m, "첫 창을 여는 자리를 못 읽었다")
        self.assertNotIn(
            "await", first[:m.start()].split("\n")[-1],
            "첫 창을 await 한다 — 사람이 답할 때까지 목록을 받으러 가지 못한다")

    def test_s3_the_list_fills_the_same_window(self):
        self.assertEqual(
            self.body.count("s9dlg("), 2,
            "창을 여는 자리가 둘이 아니다 — 먼저 세우고(빈 창) 채우는(목록) "
            "두 걸음이어야 한다")
        after = self.body[self.body.find("ccFetchTry("):]
        self.assertRegex(
            after, r"await s9dlg\(sessShape\(d,",
            "목록이 도착한 뒤 그 목록으로 창을 채우지 않는다")

    def test_r1_attach_still_asks_the_server_again(self):
        """고른 뒤 서버에 다시 묻고 붙는 순서가 그대로다."""
        i = self.body.find("/api/chat/target")
        j = self.body.find("termAttach(")
        self.assertGreater(i, -1, "붙기 전에 다시 묻는 자리가 사라졌다")
        self.assertLess(i, j, "묻기 전에 붙는다 — 죽은 세션에 붙는 결함이 돌아온다")


class ClosingIsRespected(unittest.TestCase):
    """B1·B2 — 사람이 닫은 것과 우리가 갈아 끼운 것을 가른다."""

    def setUp(self):
        self.body = fn_body(src(), "termSessionPick")

    def test_b1_a_closed_window_is_not_reopened(self):
        self.assertRegex(
            self.body, r"\.then\(\s*\(\s*\)\s*=>",
            "첫 창이 닫히는 것을 받아 두지 않는다")
        self.assertRegex(
            self.body, r"if \(closed\) return;",
            "사람이 닫았는데 목록이 도착하면 창을 되살린다 — 닫은 것을 다시 "
            "띄우는 화면은 제 말을 안 듣는 화면이다")

    def test_b2_refill_is_not_counted_as_a_close(self):
        fill = self.body.find("filling = true")
        second = self.body.rfind("s9dlg(")
        self.assertGreater(fill, -1,
                           "갈아 끼우기를 닫힘과 가르는 표가 없다")
        self.assertLess(
            fill, second,
            "표를 세우기 전에 갈아 끼운다 — 그 닫힘을 사람이 닫은 것으로 읽어 "
            "창이 영영 안 뜬다")


class TheEmptySeatSpeaks(unittest.TestCase):
    """S2·B3·F1·F2 — 빈 자리 셋이 서로 다른 말을 한다."""

    def setUp(self):
        self.text = src()
        self.shape = fn_body(self.text, "sessShape")

    def test_s2_waiting_has_its_own_words(self):
        m = re.search(r'const SESS_WAIT = "([^"]+)"', self.text)
        self.assertIsNotNone(m, "받는 중에 할 말이 없다")
        wait = m.group(1)
        empty = re.search(r'const SESS_EMPTY = "([^"]+)"', self.text).group(1)
        self.assertNotEqual(wait, empty,
                            "받는 중과 비어 있음이 같은 말을 한다")
        self.assertNotIn("없습니다", wait,
                         "받는 중인데 없다고 말한다 — 아직 모르는 사실이다")
        self.assertRegex(wait, r"(받는|여는|기다)",
                         "무엇을 하는 중인지 말하지 않는다")

    def test_s2b_shape_picks_the_waiting_words(self):
        self.assertRegex(
            self.shape, r"empty:\s*waiting \? SESS_WAIT",
            "기다리는 중일 때 그 말을 고르지 않는다")

    def test_f1_waiting_does_not_claim_there_is_nowhere_to_go(self):
        self.assertRegex(
            self.shape, r"desc:\s*waiting \|\| somewhere",
            "목록을 받기 전에 「옮겨 갈 수 있는 세션이 없습니다」라고 말한다 — "
            "화면이 모르는 것을 아는 척한다")

    def test_b3_waiting_shows_no_way_out_yet(self):
        self.assertRegex(
            self.shape, r"foot:\s*waiting \|\| somewhere \? \"\"",
            "받는 중에 「＋ 여기서 세션 시작」을 세운다 — 갈 곳이 있는지 "
            "확인되기 전의 나가는 문은 거짓 안내다")

    def test_f2_the_old_call_shape_still_works(self):
        """진단 창(?dlg=sessions)의 두 인자 호출이 그대로 산다."""
        self.assertRegex(
            self.text, r"function sessShape\(d, cur, waiting\)",
            "인자가 늘지 않았거나 이름이 다르다")
        for call in re.findall(r"sessShape\(([^)]*)\)", self.text):
            if call.startswith("d, cur"):
                continue
            self.assertNotIn(
                "undefined", call,
                "빠진 인자를 undefined 로 채워 넘긴다 — 기본값에 맡겨라")


if __name__ == "__main__":
    unittest.main()
