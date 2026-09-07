"""판은 머리를 끌어 옮긴다 (REQ-20260907-001).

사용자: "팝업이 뜰 때 화면을 가리는데, 이동 시킬 수 있었으면 좋겠다."

이 창은 뒤를 잠그지 않는 판정 패널이라 사람은 창을 띄운 채 뒤의 카드·문서를
읽는다. 그런데 자리가 고정이라 하필 그 근거를 덮으면 닫았다 다시 여는 수밖에
없었다.

고정할 성질 넷:
① 끌기 전 화면은 여태 그대로다 — 가운데 잡기(left:50% + translateX)가 남는다.
② 세로 자리는 top 이 아니라 `--dlgtop` 으로 적는다 — 시작점과 최대 키가 그 한
   값을 나눠 쓰기 때문이다(REQ-20260901-015/-019). 자가 둘이 되면 바닥이 잘린다.
③ 가리키는 것은 Pointer Events 하나로 받는다 — 마우스와 손가락에 코드가 갈리지
   않는다. `touch-action:none` 은 머리에만 건다(본문은 태블릿에서 굴러야 한다).
④ 저장이 막혀도 창은 뜬다.

실행: python3 tests/ dialog_move
"""
import os
import re
import unittest

import websrc

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "..", "web", "css", "overlay.css")
JS = os.path.join(HERE, "..", "web", "app", "dialog.js")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class TheHeadIsTheHandle(unittest.TestCase):
    """머리를 끌면 판이 옮겨진다 — S1·S3·S8."""

    @classmethod
    def setUpClass(cls):
        cls.css = _read(CSS)
        cls.js = _read(JS)
        cls.head = re.search(r"\.dlghead\{[\s\S]*?\n  position:relative\}",
                             cls.css)

    def test_the_head_says_it_can_be_dragged(self):
        """S1 표시: 커서와 마크 하나 — 색면도 새 색도 두지 않는다."""
        self.assertIsNotNone(self.head, ".dlghead 규칙을 찾지 못했다")
        head = self.head.group(0).replace(" ", "")
        self.assertIn("cursor:move", head, "끌 수 있다는 표시가 없다")
        self.assertIn("touch-action:none", head,
                      "손가락으로 끌면 화면이 대신 굴러간다")
        grip = re.search(r"\.dlggrip\{[\s\S]*?\}", self.css)
        self.assertIsNotNone(grip, "손잡이 마크가 없다")
        websrc.no_hex(self, grip.group(0), "마크 색이 토큰이 아니다")
        self.assertIn("var(--faint)", grip.group(0),
                      "마크가 제 잉크(흐린 글자)를 안 쓴다")
        self.assertIn('class="dlggrip" aria-hidden="true"', self.js,
                      "마크가 화면 낭독기에서 숨지 않았다")

    def test_only_the_head_stops_the_touch_scroll(self):
        """S8: touch-action:none 은 머리에만 — 본문은 굴러야 한다."""
        for m in re.finditer(r"([.#][\w.\-]+)\{([^{}]*touch-action:none[^{}]*)\}",
                             self.css.replace("\n  ", "").replace("\n", "")):
            self.assertEqual(".dlghead", m.group(1),
                             "머리 아닌 곳에서 손가락 굴리기를 막았다")

    def test_one_code_path_for_mouse_and_finger(self):
        """S1·S8: Pointer Events 로만 받는다 — 손마다 코드가 갈리지 않는다."""
        self.assertIn('addEventListener("pointerdown"', self.js)
        for ev in ("pointermove", "pointerup", "pointercancel"):
            self.assertIn(ev, self.js, "%s 를 안 받는다" % ev)
        for old in ("mousedown", "touchstart", "touchmove"):
            self.assertNotIn(old, self.js,
                             "%s 로도 받으면 두 벌이 갈린다" % old)
        self.assertIn("setPointerCapture", self.js,
                      "빨리 끌면 포인터가 판 밖으로 새어 나간다")
        self.assertIn('closest("button, a, input, textarea, select")', self.js,
                      "머리 안의 누를 것 위에서도 끌기가 시작된다")


class ThePlaceIsKeptInsideOneRuler(unittest.TestCase):
    """가둠·자·되돌림 — S3·S4·S6·S9."""

    @classmethod
    def setUpClass(cls):
        cls.css = _read(CSS)
        cls.js = _read(JS)

    def test_the_default_place_is_untouched(self):
        """S6 회귀: 끌기 전에는 여태 보던 그대로 가운데에 뜬다."""
        box = re.search(r"\.dlgbox\{[\s\S]*?\}", self.css).group(0)
        flat = box.replace(" ", "")
        self.assertIn("left:50%", flat, "기본 자리가 가운데를 잃었다")
        self.assertIn("transform:translateX(-50%)", flat)
        self.assertIn("top:var(--dlgtop)", flat)

    def test_the_moved_place_shares_the_same_ruler(self):
        """S6: 옮긴 세로 자리도 --dlgtop 에 적는다 — top 을 따로 박지 않는다."""
        fn = websrc.fn(self, self.js, "dlgPosApply")
        self.assertIn('setProperty("--dlgtop"', fn,
                      "세로 자리가 공용 자를 안 쓴다 — 바닥이 다시 잘린다")
        self.assertNotIn("style.top", fn,
                         "top 을 따로 박으면 시작점과 최대 키의 자가 갈린다")

    def test_the_box_cannot_leave_the_screen(self):
        """S3: 어디로 끌어도 가장자리 여백 안에 갇히고, 값은 정수다."""
        fn = websrc.fn(self, self.js, "dlgClamp")
        self.assertIn("innerWidth", fn)
        self.assertIn("innerHeight", fn)
        self.assertIn("DLG_EDGE", fn, "가장자리 여백이 이름을 잃었다")
        self.assertIn("Math.round", fn,
                      "반 화소에 걸린 판은 125% 배율에서 획이 갈린다")

    def test_a_place_that_no_longer_fits_falls_back_to_the_default(self):
        """S4: 화면이 좁아져 적어 둔 자리가 안 들어가면 기본 자리로."""
        fn = websrc.fn(self, self.js, "dlgPosPlaceFor")
        self.assertIn("dlgClamp", fn, "적어 둔 자리를 재 보지 않는다")
        self.assertRegex(fn.replace(" ", ""), r"cx!==p\.x\|\|cy!==p\.y",
                         "안 들어가는 자리를 그대로 쓴다")
        self.assertIn("dlgPosClear", fn, "옛 자리가 남는다")
        self.assertIn('addEventListener("resize", () => { if (dlgClose) dlgPosPlace(); })',
                      self.js,
                      "화면 크기가 바뀌어도 열린 판을 다시 재지 않는다")

    def test_moving_can_be_undone(self):
        """S9: 두 번 누르면 제자리로 오고 적어 둔 자리도 지운다."""
        self.assertIn('addEventListener("dblclick"', self.js,
                      "치워 둔 것을 무를 길이 없다")

    def test_the_head_is_not_a_tab_stop(self):
        """S7 회귀: 끌기는 곁들이는 기능이라 키보드 차례를 늘리지 않는다."""
        self.assertNotIn("tabindex", self.js.split("function s9dlg")[1],
                         "머리가 키보드 정거장이 됐다")


class TheStorageNeverBlocksTheDialog(unittest.TestCase):
    """S2·S5: 자리는 종류별로 남고, 저장이 막혀도 창은 뜬다."""

    @classmethod
    def setUpClass(cls):
        cls.js = _read(JS)

    def test_the_place_is_kept_per_kind(self):
        self.assertIn('const DLG_POS_KEY = "s9dlgpos"', self.js)
        self.assertIn("dlgKind", self.js, "창의 종류를 가릴 이름이 없다")
        self.assertIn("o.pos || o.cap", self.js,
                      "종류가 여는 쪽의 이름·눈썹 글자를 안 쓴다")

    def test_a_blocked_storage_still_opens_the_dialog(self):
        for name in ("dlgPosAll", "dlgPosSave"):
            fn = websrc.fn(self, self.js, name)
            self.assertIn("try{", fn,
                          "%s 가 저장 실패에 그대로 넘어진다" % name)


if __name__ == "__main__":
    unittest.main()
