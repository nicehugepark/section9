"""판의 열 바닥은 176px 하나다 (REQ-20260910-029).

종전 바닥(base 210 · calm 224 · grid 212)은 상태 열이 **다섯**이던 때 「다섯이 한
화면에 든다」를 맞춘 값이었다. 열이 여섯이 된 뒤로 그 값은 바닥이 아니라 가로
스크롤을 켜는 스위치가 됐다 — 1440 창에서 여섯 열의 합이 판보다 40px 넘쳐,
아무것도 얻지 못한 채 마지막 카드가 세로로 잘렸다(경과 시각이 반 글자로 남았다).

잘리는 자리는 판의 오른쪽 모서리이고 그 자리는 창 폭을 따라 아무 데나 오므로
**판에 오른쪽 안여백을 주어 겨눌 수 없다** — 안여백은 스크롤 맨 오른쪽에서만
보이고 처음 얼굴에서는 한 화소도 움직이지 않는다. 그래서 바닥을 내려 여섯 열이
판을 나눠 갖게 했다.

실행: python3 tests/ board_span
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "..", "web", "css")
FLOOR = 176

FILES = ("board.css", "calm.css", "skins.css", "density.css", "tablet.css")
SRC = {}
for _name in FILES:                      # 파일마다 한 번씩만 읽는다 (예산 기준선)
    with open(os.path.join(CSS, _name), encoding="utf-8") as _fh:
        SRC[_name] = _fh.read()


def _floors(text):
    """`.col` 을 고르는 규칙들이 적은 min-width 값."""
    out = []
    for m in re.finditer(r"([^{}]*\.col)\s*\{([^}]*)\}", text):
        sel, body = m.group(1), m.group(2)
        if ".cols" in sel:
            continue
        for w in re.findall(r"min-width\s*:\s*(\d+)px", body):
            out.append((sel.strip().splitlines()[-1].strip(), int(w)))
    return out


class TheColumnFloorIsOneValue(unittest.TestCase):
    def test_no_rule_puts_the_floor_above_176(self):
        """바닥을 더 높이 두는 규칙이 있으면 그 폭에서 판이 카드를 자른다."""
        bad = []
        for name, text in SRC.items():
            for sel, w in _floors(text):
                if w > FLOOR:
                    bad.append("%s: %s → %dpx" % (name, sel, w))
        self.assertEqual([], bad, "열 바닥은 %dpx 하나다 — 어긴 규칙: %s" % (FLOOR, bad))

    def test_the_base_rule_states_the_floor(self):
        """바닥은 기본 규칙에 적혀 있어야 한다 — 스킨이 저마다 정하면 다시 갈린다."""
        self.assertIn("min-width:%dpx" % FLOOR, SRC["board.css"])

    def test_the_tablet_band_uses_the_same_floor(self):
        """태블릿 구간이 다른 바닥을 쓰면 그 경계에서 판이 다시 자른다."""
        self.assertIn("min-width:%dpx" % FLOOR, SRC["tablet.css"])


if __name__ == "__main__":
    unittest.main()
