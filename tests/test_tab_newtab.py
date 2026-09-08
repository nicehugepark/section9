"""상단 탭을 가운데 버튼·수정키로 누르면 새 브라우저 탭 (REQ-20260909-006).

탭은 <button> 이라 브라우저가 스스로 새 탭을 열지 못한다 — events.js 가 auxclick(가운데
버튼)과 Ctrl/⌘/Shift+클릭을 받아 지금 주소의 #<탭> 을 새 탭에 연다. 보통 클릭은 그대로.

실행: python3 tests/ tab_newtab
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "..", "web", "app", "events.js")


class TabNewTab(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(EV, encoding="utf-8") as f:
            cls.src = f.read()

    def test_m1_middle_button_opens_a_new_tab(self):
        self.assertIn('document.addEventListener("auxclick"', self.src)
        self.assertIn("e.button !== 1", self.src, "가운데 버튼만 받는다")
        self.assertIn('closest("header [data-tab]")', self.src, "헤더의 탭에만 건다")
        self.assertRegex(self.src, r'window\.open\(url, "_blank", "noopener"\)')

    def test_m2_modifier_click_opens_a_new_tab_and_plain_click_does_not(self):
        m = re.search(r'if \(tabBtn\.closest\("header"\) && \(e\.ctrlKey \|\| e\.metaKey \|\| e\.shiftKey\)\)\{\s*tabOpenNew', self.src)
        self.assertIsNotNone(m, "수정키 클릭이 새 탭으로 가지 않는다")
        # 보통 클릭의 갈래는 그대로 — 탭을 바꾸는 줄이 수정키 갈래 **뒤에** 남아 있다
        self.assertGreater(self.src.find("tab = tabBtn.dataset.tab;"), m.start())

    def test_m3_the_url_keeps_query_and_only_changes_the_hash(self):
        self.assertIn('location.pathname + location.search + "#" + name', self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
